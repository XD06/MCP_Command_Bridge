# Mobile MCP Command Bridge

Controlled local program execution bridge for mobile MCP clients.

This project exposes MCP tools that let a client call configured local programs through structured arguments. It does not expose a shell and does not accept full command strings.

Works on Windows and Linux (VPS). Deploy to a VPS with the one-click script for secure remote access from your phone.

## Implemented MVP

- Streamable HTTP MCP server at `/mcp`.
- Optional SSE app construction for `/sse`.
- Bearer token auth for HTTP transports.
- Origin allowlist checks.
- IP allowlist (optional, for VPS deployment).
- App-level rate limiting (requests per minute per IP).
- Environment variable override for token and secrets (`MCB_TOKEN`, `MCB_SECRET_*`).
- Cross-platform ping support (Windows `-n`/`-w` ms, Linux `-c`/`-W` s).
- `get_policy` tool.
- `run_program` tool.
- Task-oriented HTTP tools: `http_probe`, `fetch_url`.
- Query-only network tools: `ping_host`, `dns_lookup`, `tcp_probe`, `trace_route`.
- Read-only system context tool: `system_snapshot`.
- Workspace file tools: `list_files`, `read_file`, `write_file`, `append_file`, `make_directory`.
- Workspace script runner: `run_workspace_script`.
- Program allowlist for `curl`, `npm`, `node`, and `python3`.
- Per-program policy checks.
- `cwd` allowed-root checks.
- Secret placeholder replacement and masking.
- Timeout, output truncation, and JSONL audit logging.

## Install

```powershell
pip install -e .
```

## Configure

Start from `config.example.yaml` (LAN) or `config.vps.yaml` (VPS).

Important fields:

- `server.token`: required Bearer token (or set `MCB_TOKEN` env var).
- `server.allowed_origins`: accepted browser/client origins.
- `server.ip_allowlist`: optional IP restriction (empty = allow all).
- `server.rate_limit_per_minute`: app-level rate limit (0 = unlimited).
- `server.compact_toolset`: expose compact grouped tools instead of many granular tools.
- `execution.allowed_roots`: directories commands may run inside.
- `execution.writable_roots`: directories MCP clients may create and edit files inside.
- `programs.<name>.enabled`: whether a program is callable.
- `secrets`: values available through `${NAME}` placeholders (or `MCB_SECRET_<NAME>` env vars).

## Run

```powershell
python -m mcp_command_bridge.server --config config.example.yaml
```

The default sample config listens on:

```text
http://127.0.0.1:8765/mcp
```

For LAN use, keep `server.host: "0.0.0.0"` in the config and connect from the phone to:

```text
http://<computer-lan-ip>:8765/mcp
```

## VPS Deployment

Deploy to a VPS with Docker — port 8765 is exposed for your own reverse proxy setup:

```bash
git clone https://github.com/XD06/MCP_Command_Bridge.git
cd MCP_Command_Bridge
sudo bash deploy/deploy.sh --domain mcp.yourdomain.com
```

The script installs Docker, generates a strong token, builds the container, and exposes port 8765. A reference Nginx config (TLS + rate limiting + security headers) is at `deploy/nginx/mcp-command-bridge.conf` — set up your own Nginx/Caddy for TLS and domain routing. Data (workspace, audit logs) is mapped to the host for easy access.

See [docs/vps-deployment.md](docs/vps-deployment.md) for full details.

Send:

```http
Authorization: Bearer <server.token>
```

## Test

```powershell
python -m unittest discover -s tests
```

Current result:

```text
95 tests passed
```

## Security Model

`run_program` validates policy before secrets are replaced and before the process starts. Execution uses argv mode with `shell=False`. Audit logs and returned outputs are masked so configured secret values are not exposed to the model.

File tools are restricted to `execution.writable_roots`. The default sample config uses:

```text
agent_workspace
```

This lets a mobile Agent create a script in the fixed workspace and then run it through the configured `python3` or `node` policy, without giving it arbitrary filesystem access.

Prefer task-oriented tools over raw command execution:

- Use `http_probe(url)` to check whether a URL is reachable.
- Use `fetch_url(url, max_bytes)` to fetch text from an allowed URL.
- Use `ping_host(host)`, `dns_lookup(host)`, `tcp_probe(host, port)`, or `trace_route(host)` for connectivity diagnostics.
- Use `system_snapshot()` for safe OS, local IP, Python version, and workspace context.
- Use workspace file tools to create files.
- Use `run_workspace_script(runtime, path, args)` to run scripts created in the workspace.
- Use `run_program` only when a lower-level program call is actually needed.

`get_policy()` returns a short capability summary. Use `get_capability_details(name)` for detailed rules about one capability, such as `http`, `network`, `workspace`, `programs`, or a specific program like `curl`.

`run_program` is hidden by default through `server.expose_advanced_tools: false`. Keep it hidden unless you deliberately want the model to use low-level argv execution.
Cached or stale external calls to `run_program` are rejected server-side when advanced tools are hidden.

`server.require_capability_preflight: true` forces models to call `get_capability_details(name)` before task tools in that capability can run. For example, `write_file` returns `preflight_required` until `get_capability_details("workspace")` has been called.

With `server.compact_toolset: true`, the default tool surface is intentionally small:

```text
get_policy
get_capability_details
system_snapshot
http_request
network_check
workspace
run_workspace_script
```
