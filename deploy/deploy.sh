#!/usr/bin/env bash
# ==========================================================================
#  MCP Command Bridge — One-Click VPS Deployment Script
#
#  Usage:
#    sudo bash deploy/deploy.sh --domain mcp.example.com
#    sudo bash deploy/deploy.sh --domain mcp.example.com --email you@example.com
#    sudo bash deploy/deploy.sh --domain mcp.example.com --force   # regenerate token
#    sudo bash deploy/deploy.sh --update                           # pull + rebuild + restart
#
#  What it does:
#    1. Installs Docker + Nginx + Certbot if missing
#    2. Generates a strong bearer token
#    3. Builds the Docker image and starts the container
#    4. Configures Nginx reverse proxy with rate limiting
#    5. Obtains Let's Encrypt SSL certificate
#    6. Sets up UFW firewall (SSH/HTTP/HTTPS only)
#    7. Prints connection info for your MCP client
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
EMAIL=""
FORCE=false
UPDATE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email)  EMAIL="$2";  shift 2 ;;
        --force)  FORCE=true;  shift ;;
        --update) UPDATE=true; shift ;;
        --help|-h)
            echo "Usage: sudo bash deploy/deploy.sh --domain mcp.example.com [--email you@example.com] [--force] [--update]"
            exit 0 ;;
        *) die "Unknown option: $1 (use --help)" ;;
    esac
done

# --- Pre-flight checks ---
[[ $EUID -ne 0 ]] && die "Run as root: sudo bash deploy/deploy.sh --domain $DOMAIN"

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

# For normal deploy, domain is required
[[ -z "$DOMAIN" ]] && die "Usage: sudo bash deploy/deploy.sh --domain mcp.example.com [--email you@example.com]"

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  MCP Command Bridge — VPS Deployment${NC}"
echo -e "${BOLD}  Domain: $DOMAIN${NC}"
echo -e "${BOLD}══════════════════════════════════════════════════${NC}"
echo ""

# ============================================================
#  Step 1: Install Docker
# ============================================================
info "Step 1/7: Checking Docker..."
if command -v docker &> /dev/null; then
    ok "Docker already installed: $(docker --version)"
else
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    ok "Docker installed: $(docker --version)"
fi

# ============================================================
#  Step 2: Install Nginx + Certbot
# ============================================================
info "Step 2/7: Checking Nginx + Certbot..."
NEED_PKG=false
command -v nginx  &> /dev/null || NEED_PKG=true
command -v certbot &> /dev/null || NEED_PKG=true
if [[ "$NEED_PKG" == "true" ]]; then
    info "Installing Nginx + Certbot..."
    apt-get update -qq
    apt-get install -y -qq nginx certbot python3-certbot-nginx ufw
    ok "Nginx + Certbot installed"
else
    ok "Nginx + Certbot already installed"
fi

# ============================================================
#  Step 3: Generate token + config
# ============================================================
info "Step 3/7: Generating token and config..."

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
sed "s/__DOMAIN__/$DOMAIN/g" config.vps.yaml > config.yaml
ok "config.yaml created (domain: $DOMAIN)"

# ============================================================
#  Step 4: Build + start Docker container
# ============================================================
info "Step 4/7: Building Docker image and starting container..."
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
#  Step 5: Configure Nginx
# ============================================================
info "Step 5/7: Configuring Nginx reverse proxy..."

NGINX_CONF="/etc/nginx/sites-available/mcp-command-bridge.conf"
cp deploy/nginx/mcp-command-bridge.conf "$NGINX_CONF"
sed -i "s/__DOMAIN__/$DOMAIN/g" "$NGINX_CONF"

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
# Remove default site if it conflicts
rm -f /etc/nginx/sites-enabled/default

# Test and reload
if nginx -t 2>&1 | tail -2; then
    systemctl reload nginx
    ok "Nginx configured and reloaded"
else
    die "Nginx config test failed"
fi

# ============================================================
#  Step 6: Obtain SSL certificate
# ============================================================
info "Step 6/7: Obtaining SSL certificate via Let's Encrypt..."

if [[ -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
    ok "SSL certificate already exists for $DOMAIN"
else
    CERTBOT_ARGS="--nginx -d $DOMAIN --non-interactive --agree-tos"
    if [[ -n "$EMAIL" ]]; then
        CERTBOT_ARGS="$CERTBOT_ARGS -m $EMAIL"
    else
        CERTBOT_ARGS="$CERTBOT_ARGS --register-unsafely-without-email"
        warn "No --email provided. Certificate renewal notices will not be sent."
    fi

    info "Running: certbot $CERTBOT_ARGS"
    if certbot $CERTBOT_ARGS; then
        ok "SSL certificate obtained for $DOMAIN"
    else
        warn "Certbot failed. You can obtain the certificate manually later:"
        warn "  sudo certbot --nginx -d $DOMAIN"
        warn "The server is running on HTTP (port 80) for now."
    fi
fi

# Ensure certbot renewal timer is enabled
systemctl enable --now certbot.timer 2>/dev/null || true

# ============================================================
#  Step 7: Configure firewall
# ============================================================
info "Step 7/7: Configuring UFW firewall..."
ufw allow 22/tcp  2>/dev/null || true
ufw allow 80/tcp  2>/dev/null || true
ufw allow 443/tcp 2>/dev/null || true
# Do NOT allow 8765 — it should only be reachable via Nginx on localhost
ufw --force enable 2>/dev/null || true
ok "Firewall configured (SSH/HTTP/HTTPS allowed, 8765 blocked)"

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
echo    "    URL:           https://$DOMAIN/mcp"
echo    "    Transport:     Streamable HTTP"
echo    "    Authorization: Bearer $TOKEN"
echo ""
echo -e "  ${BOLD}Data on host:${NC}"
echo ""
echo    "    Workspace:     $PROJECT_DIR/data/workspace/"
echo    "    Audit log:     $PROJECT_DIR/data/logs/audit.jsonl"
echo    "    Config:        $PROJECT_DIR/config.yaml"
echo    "    Token file:    $PROJECT_DIR/.env"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo ""
echo    "    docker compose logs -f        # View live logs"
echo    "    docker compose restart        # Restart container"
echo    "    docker compose down           # Stop container"
echo    "    docker compose up -d --build  # Rebuild after code change"
echo    "    sudo bash deploy/deploy.sh --update  # Pull + rebuild + restart"
echo    "    sudo certbot renew --dry-run  # Test cert renewal"
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
