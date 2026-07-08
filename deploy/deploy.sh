#!/usr/bin/env bash
# ==========================================================================
#  MCP Command Bridge — VPS Deployment Script
#
#  Usage:
#    sudo bash deploy/deploy.sh                          # deploy with default config
#    sudo bash deploy/deploy.sh --domain mcp.example.com # fill in domain for allowed_origins
#    sudo bash deploy/deploy.sh --force                  # regenerate token
#    sudo bash deploy/deploy.sh --update                 # pull + rebuild + restart
#
#  What it does:
#    1. Installs Docker if missing
#    2. Generates a strong bearer token
#    3. Builds the Docker image and starts the container (port 8765 exposed)
#    4. Prints connection info for your MCP client
#
#  Nginx / TLS / Firewall: NOT handled by this script.
#  See deploy/nginx/mcp-command-bridge.conf for a reference Nginx config.
# ==========================================================================
set -euo pipefail

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
die()   { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# --- Parse args ---
DOMAIN=""
FORCE=false
UPDATE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --domain) DOMAIN="$2"; shift 2 ;;
        --force)  FORCE=true;  shift ;;
        --update) UPDATE=true; shift ;;
        --help|-h)
            echo "Usage: sudo bash deploy/deploy.sh [--domain mcp.example.com] [--force] [--update]"
            echo ""
            echo "  --domain  Fill in allowed_origins in config (optional)"
            echo "  --force   Regenerate token"
            echo "  --update  Pull latest code + rebuild + restart"
            exit 0 ;;
        *) die "Unknown option: $1 (use --help)" ;;
    esac
done

# --- Pre-flight checks ---
[[ $EUID -ne 0 ]] && die "Run as root: sudo bash deploy/deploy.sh"

# Resolve project directory (parent of deploy/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Detect OS
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    info "OS: $ID $VERSION_ID"
else
    die "Cannot detect OS. This script supports Ubuntu 22.04+ and Debian 12+."
fi

# ============================================================
#  UPDATE MODE: skip setup, just rebuild + restart
# ============================================================
if [[ "$UPDATE" == "true" ]]; then
    info "Update mode: pulling latest code + rebuilding..."
    [[ -f .env ]] || die ".env not found. Run without --update first."
    git pull 2>/dev/null || warn "git pull failed (not a git repo?)"
    docker compose up -d --build 2>&1 | tail -5
    sleep 2
    docker compose ps
    ok "Update complete!"
    exit 0
fi

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  MCP Command Bridge — VPS Deployment${NC}"
if [[ -n "$DOMAIN" ]]; then
    echo -e "${BOLD}  Domain: $DOMAIN${NC}"
fi
echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
echo ""

# ============================================================
#  Step 1: Install Docker
# ============================================================
info "Step 1/3: Checking Docker..."
if command -v docker &> /dev/null; then
    ok "Docker already installed: $(docker --version)"
else
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    ok "Docker installed: $(docker --version)"
fi

# ============================================================
#  Step 2: Generate token + config
# ============================================================
info "Step 2/3: Generating token and config..."

# Create data directories on host
mkdir -p data/workspace data/logs

# Generate or reuse token
if [[ -f .env && "$FORCE" == "false" ]]; then
    TOKEN=$(grep -E '^MCB_TOKEN=' .env | head -1 | cut -d= -f2-)
    if [[ -n "$TOKEN" ]]; then
        info "Reusing existing token from .env (use --force to regenerate)"
    fi
fi
if [[ -z "${TOKEN:-}" ]]; then
    info "Generating strong token (32 bytes, URL-safe)..."
    # Try Python first, fall back to openssl
    if command -v python3 &> /dev/null; then
        TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    elif command -v openssl &> /dev/null; then
        TOKEN=$(openssl rand -base64 32 | tr -d '/+=' | head -c 43)
    else
        die "Need python3 or openssl to generate token"
    fi
    # Write .env
    if [[ -f .env ]]; then
        # Remove old MCB_TOKEN line, append new
        sed -i '/^MCB_TOKEN=/d' .env
        echo "MCB_TOKEN=$TOKEN" >> .env
    else
        echo "MCB_TOKEN=$TOKEN" > .env
    fi
    ok "Token generated and saved to .env"
fi

# Generate config.yaml from template
info "Generating config.yaml from template..."
if [[ -n "$DOMAIN" ]]; then
    sed "s/__DOMAIN__/$DOMAIN/g" config.vps.yaml > config.yaml
    ok "config.yaml created (domain: $DOMAIN)"
else
    # No domain provided — replace placeholder with a wildcard
    sed 's/__DOMAIN__/*/g' config.vps.yaml > config.yaml
    warn "No --domain provided. allowed_origins set to '*' — edit config.yaml to restrict"
fi

# ============================================================
#  Step 3: Build + start Docker container
# ============================================================
info "Step 3/3: Building Docker image and starting container..."
docker compose up -d --build 2>&1 | tail -5
sleep 3

# Verify container is running
if docker compose ps --status running 2>/dev/null | grep -q mcp-bridge; then
    ok "Container is running"
else
    warn "Container may not be running. Check: docker compose logs"
    docker compose ps
    docker compose logs --tail 20
    die "Container failed to start"
fi

# Quick health check
info "Waiting for server to be ready..."
for i in $(seq 1 10); do
    if curl -sf http://127.0.0.1:8765/mcp/ &> /dev/null; then
        ok "Server is responding on port 8765"
        break
    fi
    [[ $i -eq 10 ]] && warn "Server not responding yet (may need a moment)"
    sleep 1
done

# ============================================================
#  Summary
# ============================================================
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Connection info for your MCP client:${NC}"
echo ""
if [[ -n "$DOMAIN" ]]; then
    echo    "    URL:           https://$DOMAIN/mcp"
    echo    "    (after you set up Nginx + TLS)"
else
    echo    "    URL:           http://<your-vps-ip>:8765/mcp"
    echo    "    (or set up Nginx + TLS, see deploy/nginx/ for reference config)"
fi
echo    "    Transport:     Streamable HTTP"
echo    "    Authorization: Bearer $TOKEN"
echo    "    Port:          8765 (exposed)"
echo ""
echo -e "  ${BOLD}Data on host:${NC}"
echo ""
echo    "    Workspace:     $PROJECT_DIR/data/workspace/"
echo    "    Audit log:     $PROJECT_DIR/data/logs/audit.jsonl"
echo    "    Config:        $PROJECT_DIR/config.yaml"
echo    "    Token file:    $PROJECT_DIR/.env"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo ""
echo    "    1. Set up your reverse proxy (Nginx/Caddy) for TLS"
echo    "       Reference config: deploy/nginx/mcp-command-bridge.conf"
echo    "    2. Configure your MCP client with the URL + token above"
echo    ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo ""
echo    "    docker compose logs -f        # View live logs"
echo    "    docker compose restart        # Restart container"
echo    "    docker compose down           # Stop container"
echo    "    docker compose up -d --build  # Rebuild after code change"
echo    "    sudo bash deploy/deploy.sh --update  # Pull + rebuild + restart"
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
