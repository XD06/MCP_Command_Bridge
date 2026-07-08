# Mobile MCP Command Bridge MVP Development Log

## Scope

Build a local MCP bridge that lets a LAN mobile MCP client call controlled programs on this machine without exposing a shell.

The MVP implements:

- Streamable HTTP MCP tool definitions for `get_policy` and `run_program`.
- Token and Origin checks as reusable HTTP helpers.
- Structured `program + args + cwd` execution with `shell=False`.
- Config-driven program allowlist.
- `cwd` restriction to configured roots.
- Workspace file operations restricted to configured writable roots.
- Task-oriented HTTP tools so models do not need to guess safe curl arguments.
- Query-only network tools for diagnostics without exposing raw shell commands.
- Program policies for `curl`, `npm`, `node`, and `python3`.
- Secret placeholder replacement and output/log masking.
- Timeout, output truncation, and JSONL audit logging.
- Standard-library tests for the policy, executor, secrets, audit, auth, and tool layer.

SSE compatibility, QR-code pairing, Web UI, public tunnel access, and destructive-operation approval are outside this MVP.

## Architecture

```text
MCP client
  -> server.py / app.py
  -> tools.py
  -> bridge.py
  -> policy.py
  -> secrets.py
  -> executor.py
  -> audit.py
```

## Development Slices

| Slice | Status | Notes | Test Result |
|---|---|---|---|
| 1. Development doc and package skeleton | Done | Created Python package, docs, sample config, and CLI entry point. | Pending |
| 2. Config and auth | Done | Loads YAML when PyYAML is installed, JSON as fallback; validates bearer token and Origin. | Pending |
| 3. Policy engine | Done | Enforces program allowlist, enabled flag, cwd roots, curl/npm/node/python rules. | Pending |
| 4. Secret masking and executor | Done | Replaces `${NAME}` placeholders, masks outputs, truncates stdout/stderr, runs with `shell=False`. | Pending |
| 5. Audit and tool facade | Done | Records allowed and denied calls to JSONL; exposes `get_policy` and `run_program`. | Passed |
| 6. MCP transport wiring | Done | FastMCP registers `get_policy` and `run_program`; ASGI wrapper enforces Bearer token and Origin checks. | Passed |
| 7. Test run and result record | Done | Ran `python -m unittest discover -s tests`; ran HTTP smoke test against `/mcp`. | Passed |
| 8. Workspace file tools | Done | Added `list_files`, `read_file`, `write_file`, `append_file`, and `make_directory`; restricted to `execution.writable_roots`. | Passed |
| 9. Expanded external curl allowlist | Done | Added selected external URL prefixes for Baidu, Google, GitHub, raw GitHub content, and httpbin. | Passed |
| 10. Task-oriented HTTP tools | Done | Added `http_probe` and `fetch_url`; added hints for common policy denials. | Passed |
| 11. Capability summary and network query tools | Done | `get_policy` now returns a short capability catalog; `get_capability_details` returns details on demand; added `ping_host`, `dns_lookup`, and `tcp_probe`. | Passed |
| 12. Script runner and enum schemas | Done | Added `run_workspace_script`; constrained several MCP parameters with literal choices to reduce model guessing. | Passed |
| 13. Hide advanced run_program and add trace_route | Done | `run_program` is hidden unless `server.expose_advanced_tools=true`; added `trace_route`; relative workspace scripts are normalized before execution. | Passed |
| 14. Linux compatibility and cross-platform ping | Done | `_build_ping_command` detects OS via `platform.system()`: Windows uses `-n`/`-w ms`, Linux uses `-c`/`-W s`. `traceroute` already auto-detects `tracert`. | Passed |
| 15. VPS security hardening | Done | Added `ip_allowlist` and `rate_limit_per_minute` to `ServerConfig`; `validate_client_ip` in `auth.py`; `RateLimiter` class in `rate_limit.py`; env var override for `MCB_TOKEN` and `MCB_SECRET_*` in `config.py`; enhanced middleware in `server.py` with IP check + rate limit + 429 response. | Passed |
| 16. VPS deployment infrastructure | Done | Dockerfile (Debian-slim + curl/ping/traceroute/node/npm/build-essential/git), docker-compose.yml (port 8765 exposed, host bind mounts, resource limits, `host.docker.internal`), `deploy/deploy.sh` (Docker + token + config only), reference Nginx config at `deploy/nginx/`, systemd service unit, `config.vps.yaml` template, `scripts/generate_token.py`. | Passed |
| 17. Comprehensive test suite | Done | Added `test_rate_limit.py` (9 tests), extended `test_auth.py` (+6 IP tests), `test_config.py` (+10 env var tests), `test_network_tools.py` (+7 ping command tests), `test_server.py` (+8 VPS config + middleware integration tests with Starlette TestClient). Total: 95 tests. | Passed |
| 18. Full container control mode | Done | Shifted from app-level restrictions to container-as-sandbox. Empty allowlists = unrestricted. Added `run_shell(command)` tool for direct shell command execution via `bash -c`. Removed DNS rebinding protection and Origin checks for mobile client compatibility. | Passed |
| 19. UTF-8 encoding fix | Done | Replaced `locale.getpreferredencoding()` with hardcoded `encoding="utf-8"` in `executor.py` and `network_tools.py`. Added `_UTF8_ENV` to inject `LANG=C.UTF-8` into subprocess env. Dockerfile and docker-compose.yml set `LANG`, `LC_ALL`, `PYTHONUTF8`, `PYTHONIOENCODING`. Fixes Chinese/non-ASCII text errors. | Passed |
| 20. Persistence & audit trail guidance | Done | Updated `config.py` capability descriptions to inform LLM about persistent paths (`/app/agent_workspace`, `/app/projects`) and audit logging (`/app/logs/audit.jsonl`). Added `persistence` block to `public_policy`. | Passed |

## Run

Install runtime dependencies for the MCP server:

```powershell
pip install -e .
```

Run the server:

```powershell
python -m mcp_command_bridge.server --config config.example.yaml
```

Run tests:

```powershell
python -m unittest discover -s tests
```

Smoke-test auth:

```powershell
# Start the server, then request http://127.0.0.1:8765/mcp without Authorization.
# Expected result: HTTP 401.
```

## Security Notes

- `run_shell` executes commands via `bash -c` — it is the PREFERRED tool for command-line operations.
- `run_program` validates policy before secrets are replaced and before the process starts. Execution uses argv mode with `shell=False`.
- Audit logs and returned outputs are masked so configured secret values are not exposed to the model.
- All subprocess I/O uses hardcoded UTF-8 encoding with `errors="replace"` to prevent `UnicodeEncodeError` on Chinese/non-ASCII text.
- Subprocess env includes `LANG=C.UTF-8` and `LC_ALL=C.UTF-8` to ensure child processes also use UTF-8.
- File writes are allowed only under `execution.writable_roots`.
- Script execution roots include `agent_workspace`, so the MCP client can write a script into the fixed workspace and run it through `python3` or `node`.
- `http_probe` and `fetch_url` reuse the same URL allowlist as `curl`; they are easier for models to call correctly.
- `get_policy` intentionally avoids returning every detailed rule. Detailed rules are available through `get_capability_details(name)`.
- Network diagnostics are exposed as task tools instead of raw commands.
- `run_workspace_script` lets models run workspace scripts without constructing low-level `run_program` calls.
- `run_shell` and `run_program` are advanced tools, hidden by default unless `server.expose_advanced_tools=true`.
- Stale client calls to hidden tools are rejected by `CommandBridge` unless the call is internal.
- Relative script paths are resolved against script roots, so `python3 check.py` can find `agent_workspace/check.py` internally.
- `server.require_capability_preflight=true` forces models to inspect a capability before using its task tools.
- `system_snapshot` replaces ad hoc environment-inspection scripts with a safe read-only tool.
- `list_files` supports capped recursive listing to reduce repeated directory calls.
- `server.compact_toolset=true` exposes grouped tools (`http_request`, `network_check`, `workspace`) instead of many granular tools.
- In full-control mode, the container IS the sandbox — Docker resource limits provide isolation, not application-level restrictions.

## Test Results

- 2026-06-03: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 18 tests
  - Duration: 0.939s
- 2026-06-03: `python -c "from mcp_command_bridge.server import build_asgi_app; app=build_asgi_app('config.example.yaml'); print(type(app).__name__)"`
  - Result: Passed
  - Output: `Starlette`
- 2026-06-03: HTTP smoke test
  - Command: start `python -m mcp_command_bridge.server --config config.example.yaml`, request `http://127.0.0.1:8765/mcp` without token, stop process.
  - Result: Passed
  - Observed status: `401`
- 2026-06-03: Workspace/file-tool expansion
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 23 tests
  - Duration: 1.355s
- 2026-06-03: Task-oriented HTTP tool expansion
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 29 tests
  - Duration: 2.581s
- 2026-06-03: Capability summary and network query tools
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 34 tests
  - Duration: 2.582s
- 2026-06-03: Script runner and enum schemas
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 36 tests
  - Duration: 2.674s
- 2026-06-03: Hide advanced tool and add trace route
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 38 tests
  - Duration: 3.235s
- 2026-06-03: Capability preflight gate
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 39 tests
  - Duration: 2.704s
- 2026-06-03: Hidden run_program hard gate and subprocess encoding
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 40 tests
  - Duration: 2.703s
- 2026-06-03: System snapshot and recursive listing
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 43 tests
  - Duration: 2.763s
- 2026-06-03: Compact grouped toolset
  - Command: `python -m unittest discover -s tests`
  - Result: Passed
  - Count: 47 tests
  - Duration: 3.467s
- 2026-07-09: Linux compatibility and VPS security hardening
  - Command: `python -m pytest tests/ -q`
  - Result: Passed
  - Count: 95 tests
  - Duration: 4.92s
  - New test files: `test_rate_limit.py` (9 tests), extended `test_auth.py` (+6), `test_config.py` (+10), `test_network_tools.py` (+7), `test_server.py` (+8 VPS config + middleware integration)

## VPS Security Notes

- `MCB_TOKEN` environment variable overrides `server.token` in YAML config — secrets never need to be in config files.
- `MCB_SECRET_<NAME>` environment variables are merged into the secrets dict, overriding YAML values.
- `ip_allowlist` restricts access to specified client IPs (empty = allow all, Nginx + token still protect).
- `rate_limit_per_minute` enforces app-level rate limiting per client IP (0 = unlimited). Nginx also has its own `limit_req` for a first line of defense.
- Rate-limited responses include `Retry-After`, `X-RateLimit-Limit`, and `X-RateLimit-Remaining` headers.
- `_get_client_ip` reads `X-Forwarded-For` first (for Nginx proxy), falls back to `request.client.host`.
- Docker container runs as root with full toolset installed (curl, ping, traceroute, node, npm, git, build-essential) — isolation comes from Docker, resource limits from docker-compose (2 CPU / 512MB max).
- `host.docker.internal` is mapped to the host gateway so the container can access host services (e.g., SiYuan at `host.docker.internal:6806`).
- Nginx reference config at `deploy/nginx/mcp-command-bridge.conf` includes TLS 1.2/1.3, HSTS, security headers, and rate limiting (10 req/s burst 20). Set up your own reverse proxy.
- Port 8765 is exposed by Docker — use your reverse proxy (Nginx/Caddy) for TLS and firewall protection.
- `deploy/deploy.sh` handles Docker + token + config only. Nginx/TLS/firewall are left to the user. Idempotent — `--force` regenerates the token, `--update` pulls code and rebuilds.
