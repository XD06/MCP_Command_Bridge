# MCP Command Bridge

Full container control bridge for mobile MCP clients (RikkaHub, etc.).

This project exposes MCP tools that let an AI agent run shell commands, execute programs, manage files, make HTTP requests, and install packages inside a Docker container sandbox. The container IS the sandbox — the agent has full control inside it, with all operations audit-logged and workspace data persisted to the host.

Works on Windows and Linux (VPS). Deploy to a VPS with the one-click script for secure remote access from your phone.

## Features

### Core Tools

- **`run_shell(command)`** — PREFERRED tool. Execute shell command strings directly via `bash -c`. Supports pipes (`|`), redirects (`>`), chaining (`&&`, `||`), env vars (`$HOME`), globs (`*`), and all bash syntax. No need to write scripts to files first.
- **`run_program(program, args)`** — Structured argv execution (`shell=False`). Use when you need precise control without shell interpretation.
- **`run_workspace_script(runtime, path)`** — Run a script file from the workspace.
- `get_policy()` / `get_capability_details(name)` — Capability discovery for the LLM.

### Task Tools

- HTTP: `http_probe(url)`, `fetch_url(url)`
- Network: `ping_host`, `dns_lookup`, `tcp_probe`, `trace_route`
- System: `system_snapshot()`
- Files: `list_files`, `read_file`, `write_file`, `append_file`, `make_directory`

### Security & Infrastructure

- Streamable HTTP MCP server at `/mcp` (mobile-compatible: no DNS rebinding / Origin checks).
- Bearer token auth + optional IP allowlist + rate limiting.
- Environment variable override for token and secrets (`MCB_TOKEN`, `MCB_SECRET_*`).
- Full UTF-8 encoding support — Chinese and other non-ASCII text works out of the box.
- JSONL audit logging of all operations to `data/logs/audit.jsonl` (host-mapped).
- Secret placeholder replacement and masking in outputs and logs.
- Timeout and output truncation.

### Data Persistence

| Container path | Host path | Purpose |
|---|---|---|
| `/app/agent_workspace` | `data/workspace/` | Agent's writable workspace |
| `/app/projects` | `data/projects/` | Cloned repos and project files |
| `/app/logs/audit.jsonl` | `data/logs/audit.jsonl` | Audit log of all operations |

Files saved outside these paths are **ephemeral** and will be lost on container restart.

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

### Container Full-Control Mode (VPS)

In VPS/Docker deployment, the container IS the sandbox:
- `run_shell` and `run_program` are exposed with no restrictions on URLs, methods, paths, or arguments.
- The agent can `apt-get install`, `pip install`, `git clone`, write scripts, and execute them.
- Isolation comes from Docker resource limits, not application-level restrictions.
- All operations are audit-logged to `data/logs/audit.jsonl` (host-mapped).

### Restricted Mode (LAN)

`run_program` and `run_shell` are hidden by default (`server.expose_advanced_tools: false`). File tools are restricted to `execution.writable_roots`. This mode is for local development.

### Encoding

All subprocess I/O uses hardcoded UTF-8 encoding (`encoding="utf-8"`, `errors="replace"`). The Docker container sets `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`. Chinese and other non-ASCII text works without errors.

### Tool Selection Guide

- **`run_shell(command)`** — PREFERRED for most tasks. Pipes, redirects, chaining, inline code.
- `http_probe(url)` / `fetch_url(url)` — Quick HTTP status / text fetch.
- `ping_host`, `dns_lookup`, `tcp_probe`, `trace_route` — Network diagnostics.
- `system_snapshot()` — OS, IP, Python version info.
- `write_file` / `read_file` — Create and read workspace files.
- `run_workspace_script(runtime, path)` — Run a workspace script file.
- `run_program(program, args)` — Precise argv control without shell interpretation.

`get_policy()` returns a capability summary. `get_capability_details(name)` returns detailed rules.

`server.require_capability_preflight: true` forces models to call `get_capability_details(name)` before task tools in that capability can run.

With `server.compact_toolset: true`, the default tool surface is:

```text
get_policy
get_capability_details
system_snapshot
http_request
network_check
workspace
run_workspace_script
```
