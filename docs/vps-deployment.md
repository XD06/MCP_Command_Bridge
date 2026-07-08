# VPS Deployment Guide — MCP Command Bridge

## One-Click Deployment (Recommended)

The fastest way to deploy. Run one command on your VPS and everything is set up: Docker, Nginx, SSL certificate, firewall, and the MCP Bridge container.

### Prerequisites

- A VPS running Ubuntu 22.04+ or Debian 12+
- Root/sudo access
- A domain name pointing to your VPS IP (A record)
- Ports 80 and 443 open

### Steps

```bash
# 1. SSH into your VPS
ssh root@your-vps-ip

# 2. Clone the project
git clone https://github.com/XD06/MCP_Command_Bridge.git
cd MCP_Command_Bridge

# 3. Run the deploy script
sudo bash deploy/deploy.sh --domain mcp.yourdomain.com --email you@example.com
```

That's it. The script will:

1. Install Docker, Nginx, and Certbot if missing
2. Generate a strong bearer token (saved to `.env`)
3. Build the Docker image and start the container
4. Configure Nginx reverse proxy with rate limiting and security headers
5. Obtain a Let's Encrypt SSL certificate
6. Set up UFW firewall (SSH/HTTP/HTTPS only)
7. Print your connection URL and token

### After Deployment

Configure your MCP client (e.g., RikkaHub) with:

- **URL**: `https://mcp.yourdomain.com/mcp`
- **Authorization**: `Bearer <your-token>`
- **Transport**: Streamable HTTP

The token is printed at the end of the deploy script output and saved in `.env`.

### Updating

```bash
cd MCP_Command_Bridge
sudo bash deploy/deploy.sh --update
```

This pulls the latest code, rebuilds the Docker image, and restarts the container. Your token, config, and data are preserved.

### Regenerating Token

```bash
sudo bash deploy/deploy.sh --domain mcp.yourdomain.com --force
```

This generates a new token. Update your MCP client with the new one.

---

## Architecture

```
Phone (RikkaHub)
  → HTTPS (443) → Nginx (TLS + rate limit + security headers)
    → 127.0.0.1:8765 → Docker container (MCP Bridge)
      → subprocess: curl, ping, traceroute, node, python3, ...
```

The bridge runs inside a Docker container based on Debian-slim (not Alpine, because the bridge dispatches real system commands that Alpine lacks). The container runs as root so the agent can `apt-get install` additional tools at runtime if needed — isolation comes from Docker itself, and resource limits are enforced via docker-compose.

### Data Layout on Host

```
MCP_Command_Bridge/
├── .env                  # MCB_TOKEN (bearer token)
├── config.yaml           # Generated from config.vps.yaml (domain filled in)
├── config.vps.yaml       # Template (don't edit directly)
├── data/
│   ├── workspace/        # Agent's writable workspace (mapped into container)
│   └── logs/
│       └── audit.jsonl   # JSONL audit log of all tool calls
├── docker-compose.yml    # Container config (volumes, limits, env)
└── Dockerfile            # Image definition (Debian-slim + tools)
```

### Resource Limits

The container is constrained by docker-compose:

- CPU: 2 cores max, 0.25 reserved
- Memory: 512MB max, 64MB reserved
- Log rotation: 10MB per file, 3 files max

### Security Layers

1. **Nginx**: TLS 1.2/1.3, rate limiting (10 req/s burst 20), security headers, HSTS
2. **App middleware**: IP allowlist (optional), app-level rate limiting (60 req/min), origin check, bearer token
3. **Policy engine**: program allowlist, argument denylist, path containment, secret masking

### Accessing Host Services from Container

The container has `host.docker.internal` mapped to the host gateway. To access a service on the host (e.g., SiYuan at port 6806), use `host.docker.internal:6806` instead of `127.0.0.1:6806`. The default `config.vps.yaml` already uses this.

---

## Manual Deployment (Alternative)

If you prefer not to use the one-click script, or need more control:

### Install Docker

```bash
curl -fsSL https://get.docker.com | sh
```

### Generate Token

```bash
python3 scripts/generate_token.py --write
```

### Configure

```bash
cp .env.example .env
# Edit .env: set MCB_TOKEN
nano .env

# Generate config from template
sed 's/__DOMAIN__/mcp.yourdomain.com/g' config.vps.yaml > config.yaml
# Edit config.yaml if needed (allowed_url_prefixes, etc.)
nano config.yaml
```

### Build and Start

```bash
mkdir -p data/workspace data/logs
docker compose up -d --build
```

### Nginx + SSL

```bash
apt install -y nginx certbot python3-certbot-nginx
cp deploy/nginx/mcp-command-bridge.conf /etc/nginx/sites-available/
sed -i 's/__DOMAIN__/mcp.yourdomain.com/g' /etc/nginx/sites-available/mcp-command-bridge.conf
ln -sf /etc/nginx/sites-available/mcp-command-bridge.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
certbot --nginx -d mcp.yourdomain.com
```

### Firewall

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

---

## Troubleshooting

### Container won't start

```bash
docker compose logs --tail 50
```

Common causes: `.env` missing `MCB_TOKEN`, `config.yaml` not generated, port 8765 already in use.

### 502 Bad Gateway

The container isn't running or Nginx can't reach it. Check:

```bash
docker compose ps
curl http://127.0.0.1:8765/mcp/   # Should return 401 (not connection refused)
```

### 401 Unauthorized

Token mismatch. Verify the token in your MCP client matches `.env`:

```bash
grep MCB_TOKEN .env
```

The header must be exactly: `Authorization: Bearer <token>` (with space after Bearer).

### 429 Too Many Requests

Rate limited. Reduce request frequency, or adjust `rate_limit_per_minute` in `config.yaml`.

### SSL certificate issues

```bash
sudo certbot renew --dry-run   # Test renewal
sudo certbot certificates       # Check status
```

### Viewing audit logs

```bash
cat data/logs/audit.jsonl | python3 -m json.tool  # Pretty print
tail -20 data/logs/audit.jsonl                      # Last 20 entries
```

### Installing more tools in the container

The container runs as root. You can install tools at runtime:

```bash
docker compose exec mcp-bridge apt-get update
docker compose exec mcp-bridge apt-get install -y jq httpie
```

Note: tools installed this way are lost when the container is recreated. For permanent additions, edit the Dockerfile and rebuild with `docker compose up -d --build`.
