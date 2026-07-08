# VPS Deployment Guide — MCP Command Bridge

## Quick Deployment

The deploy script handles Docker setup, token generation, and container startup. Nginx/TLS/firewall are left for you to configure — a reference Nginx config is provided.

### Prerequisites

- A VPS running Ubuntu 22.04+ or Debian 12+
- Root/sudo access
- Docker installed (or let the script install it)

### Steps

```bash
# 1. SSH into your VPS
ssh root@your-vps-ip

# 2. Clone the project
git clone https://github.com/XD06/MCP_Command_Bridge.git
cd MCP_Command_Bridge

# 3. Run the deploy script
sudo bash deploy/deploy.sh --domain mcp.yourdomain.com
```

The script will:

1. Install Docker if missing
2. Generate a strong bearer token (saved to `.env`)
3. Build the Docker image and start the container (port 8765 exposed)
4. Print your connection URL and token

That's it. Port 8765 is now listening on your VPS. Set up your own reverse proxy (Nginx/Caddy/etc.) for TLS and domain routing.

### After Deployment

Configure your MCP client (e.g., RikkaHub) with:

- **URL**: `https://mcp.yourdomain.com/mcp` (after setting up your reverse proxy)
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

---

## Nginx Reverse Proxy (Reference)

A complete Nginx config is at `deploy/nginx/mcp-command-bridge.conf`. It includes TLS termination, rate limiting, connection limiting, and security headers.

### Quick Setup

```bash
# Install Nginx + Certbot
apt install -y nginx certbot python3-certbot-nginx

# Copy the reference config
cp deploy/nginx/mcp-command-bridge.conf /etc/nginx/sites-available/
sed -i 's/YOUR_DOMAIN/mcp.yourdomain.com/g' /etc/nginx/sites-available/mcp-command-bridge.conf
ln -sf /etc/nginx/sites-available/mcp-command-bridge.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and reload
nginx -t && systemctl reload nginx

# Obtain SSL certificate
certbot --nginx -d mcp.yourdomain.com
```

### Key Settings in the Config

- `upstream mcp_bridge` — points to `127.0.0.1:8765` (same host) or your VPS IP (remote Nginx)
- `limit_req_zone` — 10 req/s per IP with burst of 20
- `limit_conn_zone` — max 10 concurrent connections per IP
- `proxy_buffering off` — required for Streamable HTTP / SSE streaming
- `proxy_read_timeout 300s` — long timeout for MCP sessions
- Security headers: HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy

### Using Caddy Instead

If you prefer Caddy, the equivalent is simple:

```Caddyfile
mcp.yourdomain.com {
    reverse_proxy 127.0.0.1:8765
}
```

Caddy handles TLS automatically with Let's Encrypt.

---

## Architecture

```
Phone (RikkaHub)
  → HTTPS (443) → Your reverse proxy (Nginx/Caddy, TLS + rate limit)
    → VPS:8765 → Docker container (MCP Bridge)
      → subprocess: curl, ping, traceroute, node, python3, ...
```

The bridge runs inside a Docker container based on Debian-slim (not Alpine, because the bridge dispatches real system commands that Alpine lacks). The container runs as root so the agent can `apt-get install` additional tools at runtime if needed — isolation comes from Docker itself, and resource limits are enforced via docker-compose.

The container is configured with full UTF-8 locale (`LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`) to ensure Chinese and other non-ASCII text works without encoding errors.

### Available Tools in Full-Control Mode

| Tool | Description |
|---|---|
| `run_shell(command)` | PREFERRED. Execute shell command string via `bash -c`. Pipes, redirects, chaining, inline code. |
| `run_program(program, args)` | Structured argv execution (`shell=False`). Precise control. |
| `write_file` / `read_file` | Create and read files in the workspace. |
| `list_files` / `append_file` / `make_directory` | Workspace file management. |
| `http_probe` / `fetch_url` | Quick HTTP status check / text fetch. |
| `ping_host` / `dns_lookup` / `tcp_probe` / `trace_route` | Network diagnostics. |
| `system_snapshot` | OS, IP, Python version info. |
| `run_workspace_script(runtime, path)` | Run a script file from the workspace. |
| `get_policy` / `get_capability_details` | Capability discovery for the LLM. |

### Data Layout on Host

```
MCP_Command_Bridge/
├── .env                  # MCB_TOKEN (bearer token)
├── config.yaml           # Generated from config.vps.yaml (domain filled in)
├── config.vps.yaml       # Template (don't edit directly)
├── data/
│   ├── workspace/        # Agent's writable workspace (mapped to /app/agent_workspace)
│   ├── projects/         # Cloned repos and project files (mapped to /app/projects)
│   └── logs/
│       └── audit.jsonl   # JSONL audit log of all tool calls (mapped to /app/logs/)
├── docker-compose.yml    # Container config (port 8765, volumes, limits, UTF-8 env)
├── Dockerfile            # Image definition (Debian-slim + tools + UTF-8 locale)
├── deploy/
│   ├── deploy.sh         # Deployment script (Docker + token + config)
│   └── nginx/
│       └── mcp-command-bridge.conf  # Reference Nginx config
└── ...
```

### Resource Limits

The container is constrained by docker-compose:

- CPU: 1 core max, 0.1 reserved (tuned for 1-vCPU VPS)
- Memory: 512MB max, 32MB reserved
- Log rotation: 10MB per file, 3 files max

### Encoding

The container and all subprocesses use UTF-8 encoding. This is enforced at three levels:
1. Dockerfile `ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 PYTHONIOENCODING=utf-8`
2. docker-compose.yml environment variables (same as above)
3. Python code: `executor.py` and `network_tools.py` hardcode `encoding="utf-8"` and inject `LANG=C.UTF-8` into subprocess env

This ensures Chinese text, emoji, and other non-ASCII content works without `UnicodeEncodeError`.

### Security Layers

1. **Your reverse proxy**: TLS 1.2/1.3, rate limiting, security headers, HSTS
2. **App middleware**: IP allowlist (optional), app-level rate limiting (60 req/min), origin check, bearer token
3. **Policy engine**: program allowlist, argument denylist, path containment, secret masking

### Accessing Host Services from Container

The container has `host.docker.internal` mapped to the host gateway. To access a service on the host (e.g., SiYuan at port 6806), use `host.docker.internal:6806` instead of `127.0.0.1:6806`. The default `config.vps.yaml` already uses this.

---

## Manual Deployment (Alternative)

If you prefer not to use the deploy script:

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
# Or without a domain:
sed 's/__DOMAIN__/*/g' config.vps.yaml > config.yaml
# Edit config.yaml if needed (allowed_url_prefixes, etc.)
nano config.yaml
```

### Build and Start

```bash
mkdir -p data/workspace data/logs
docker compose up -d --build
```

### Verify

```bash
# Container running?
docker compose ps

# Health check
curl -sf http://127.0.0.1:8765/mcp/ && echo "OK"

# From another machine (should get 401 without token)
curl http://your-vps-ip:8765/mcp/
```

---

## Troubleshooting

### Container won't start

```bash
docker compose logs --tail 50
```

Common causes: `.env` missing `MCB_TOKEN`, `config.yaml` not generated, port 8765 already in use.

### 502 Bad Gateway

The container isn't running or your reverse proxy can't reach it. Check:

```bash
docker compose ps
curl http://127.0.0.1:8765/mcp/   # Should return 401 (not connection refused)
```

If Nginx is on a different host, make sure port 8765 is reachable and the upstream in the Nginx config points to the right IP.

### 401 Unauthorized

Token mismatch. Verify the token in your MCP client matches `.env`:

```bash
grep MCB_TOKEN .env
```

The header must be exactly: `Authorization: Bearer <token>` (with space after Bearer).

### 429 Too Many Requests

Rate limited. Reduce request frequency, or adjust `rate_limit_per_minute` in `config.yaml` and the `limit_req` settings in your Nginx config.

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
