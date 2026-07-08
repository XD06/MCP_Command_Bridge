from __future__ import annotations

import argparse
from typing import Any, Literal

from .bridge import CommandBridge
from .auth import validate_authorization, validate_origin
from .config import BridgeConfig, load_config


def build_mcp(config: BridgeConfig) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.server import TransportSecuritySettings
    except ImportError as exc:
        raise RuntimeError("Install dependencies first: pip install -e .") from exc

    bridge = CommandBridge(config)
    mcp = FastMCP(
        "Mobile MCP Command Bridge",
        host=config.server.host,
        port=config.server.port,
        streamable_http_path="/mcp",
        sse_path="/sse",
        # Disable DNS rebinding protection — Nginx + Bearer token already protect the endpoint.
        # This allows mobile MCP clients (RikkaHub etc.) to connect without Host/Origin issues.
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
            allowed_hosts=[],
            allowed_origins=[],
        ),
    )

    @mcp.tool()
    def get_policy() -> dict[str, object]:
        """Return a short capability summary. Use get_capability_details(name) for detailed rules."""
        return bridge.get_policy()

    @mcp.tool()
    def get_capability_details(
        name: Literal["http", "network", "workspace", "system", "programs", "curl", "npm", "node", "python3"]
    ) -> dict[str, object]:
        """Return detailed policy for one capability: http, network, workspace, system, programs, curl, npm, node, or python3."""
        return bridge.get_capability_details(name)

    @mcp.tool()
    def system_snapshot() -> dict[str, object]:
        """Return safe read-only system context such as OS, hostname, local IPv4, and workspace roots."""
        return bridge.system_snapshot()

    if config.server.compact_toolset:
        @mcp.tool()
        def http_request(
            mode: Literal["probe", "fetch"],
            url: str,
            timeout_seconds: int | None = None,
            max_bytes: int | None = None,
        ) -> dict[str, object]:
            """HTTP capability: mode=probe returns status; mode=fetch returns allowed URL text."""
            return bridge.http_request(mode, url, timeout_seconds, max_bytes)

        @mcp.tool()
        def network_check(
            mode: Literal["ping", "dns", "tcp", "trace"],
            host: str,
            port: int | None = None,
            count: int = 4,
            max_hops: int = 8,
            timeout_seconds: int | None = None,
        ) -> dict[str, object]:
            """Network capability: ping, dns, tcp port probe, or trace route."""
            return bridge.network_check(mode, host, port, count, max_hops, timeout_seconds)

        @mcp.tool()
        def workspace(
            action: Literal["list", "read", "write", "append", "mkdir"],
            path: str = ".",
            content: str | None = None,
            overwrite: bool = False,
            recursive: bool = False,
            max_entries: int = 200,
        ) -> dict[str, object]:
            """Workspace capability: list/read/write/append/mkdir inside the fixed workspace."""
            return bridge.workspace(action, path, content, overwrite, recursive, max_entries)
    else:
        @mcp.tool()
        def http_probe(url: str, timeout_seconds: int | None = None) -> dict[str, object]:
            """Check an allowed HTTP/HTTPS URL and return status. Prefer this over curl -o/-w."""
            return bridge.http_probe(url, timeout_seconds)

        @mcp.tool()
        def fetch_url(
            url: str,
            timeout_seconds: int | None = None,
            max_bytes: int | None = None,
        ) -> dict[str, object]:
            """Fetch text from an allowed HTTP/HTTPS URL. Use max_bytes to keep output small."""
            return bridge.fetch_url(url, timeout_seconds, max_bytes)

        @mcp.tool()
        def ping_host(host: str, count: int = 4, timeout_seconds: int = 10) -> dict[str, object]:
            """Ping a hostname or IP for connectivity diagnostics. Query-only; count is capped at 4."""
            return bridge.ping_host(host, count, timeout_seconds)

        @mcp.tool()
        def dns_lookup(host: str) -> dict[str, object]:
            """Resolve a hostname to IP addresses using local DNS."""
            return bridge.dns_lookup(host)

        @mcp.tool()
        def tcp_probe(host: str, port: int, timeout_seconds: int = 5) -> dict[str, object]:
            """Check whether a TCP host:port is reachable without sending application data."""
            return bridge.tcp_probe(host, port, timeout_seconds)

        @mcp.tool()
        def trace_route(host: str, max_hops: int = 8, timeout_seconds: int = 60) -> dict[str, object]:
            """Trace network hops to a host. Query-only; max_hops is capped at 12."""
            return bridge.trace_route(host, max_hops, timeout_seconds)

        @mcp.tool()
        def list_files(path: str = ".", recursive: bool = False, max_entries: int = 200) -> dict[str, object]:
            """List files inside the fixed workspace. Use recursive=true for a capped tree view."""
            return bridge.list_files(path, recursive, max_entries)

        @mcp.tool()
        def read_file(path: str) -> dict[str, object]:
            """Read a UTF-8 text file inside the fixed workspace. Paths are relative to the workspace root."""
            return bridge.read_file(path)

        @mcp.tool()
        def write_file(path: str, content: str, overwrite: bool = False) -> dict[str, object]:
            """Write a UTF-8 text file inside the fixed workspace. Set overwrite=true to replace an existing file."""
            return bridge.write_file(path, content, overwrite)

        @mcp.tool()
        def append_file(path: str, content: str) -> dict[str, object]:
            """Append text to a UTF-8 file inside the fixed workspace."""
            return bridge.append_file(path, content)

        @mcp.tool()
        def make_directory(path: str) -> dict[str, object]:
            """Create a directory inside the fixed workspace."""
            return bridge.make_directory(path)

    if config.server.expose_advanced_tools:
        @mcp.tool()
        def run_program(
            program: str,
            args: list[str],
            cwd: str | None = None,
            timeout_seconds: int | None = None,
        ) -> dict[str, object]:
            """Advanced tool: run a configured program with structured argv arguments.

            program must be one of the configured programs (see get_policy).
            args are passed as individual argv elements (shell=False).
            cwd must be inside allowed_roots (or any directory if unrestricted).
            """
            return bridge.run_program(program, args, cwd, timeout_seconds)

    @mcp.tool()
    def run_workspace_script(
        runtime: Literal["python3", "node"],
        path: str,
        args: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, object]:
        """Run a script from the fixed workspace. Use write_file first to create the script."""
        return bridge.run_workspace_script(runtime, path, args, timeout_seconds)

    return mcp


def build_asgi_app(config_path: str, transport: str = "streamable-http") -> Any:
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
    except ImportError as exc:
        raise RuntimeError("Install dependencies first: pip install -e .") from exc

    from .auth import validate_authorization, validate_origin, validate_client_ip
    from .rate_limit import RateLimiter

    config = load_config(config_path)
    mcp = build_mcp(config)
    app = mcp.sse_app() if transport == "sse" else mcp.streamable_http_app()
    rate_limiter = RateLimiter(config.server.rate_limit_per_minute)

    def _get_client_ip(request: Any) -> str | None:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None

    class BearerTokenMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            if request.method == "OPTIONS":
                return await call_next(request)
            client_ip = _get_client_ip(request)
            try:
                validate_client_ip(client_ip, config.server)
                if not rate_limiter.check(client_ip or "unknown"):
                    remaining = rate_limiter.remaining(client_ip or "unknown")
                    return JSONResponse(
                        {
                            "ok": False,
                            "error": "rate_limited",
                            "reason": "Too many requests. Please slow down.",
                            "limit_per_minute": config.server.rate_limit_per_minute,
                            "remaining": remaining,
                        },
                        status_code=429,
                        headers={
                            "Retry-After": "60",
                            "X-RateLimit-Limit": str(config.server.rate_limit_per_minute),
                            "X-RateLimit-Remaining": str(remaining),
                        },
                    )
                validate_authorization(request.headers.get("authorization"), config.server)
            except Exception as exc:
                return JSONResponse(
                    {"ok": False, "error": "auth_error", "reason": str(exc)},
                    status_code=401,
                )
            return await call_next(request)

    app.add_middleware(BearerTokenMiddleware)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Mobile MCP Command Bridge")
    parser.add_argument("--config", default="config.example.yaml")
    parser.add_argument(
        "--transport",
        default="streamable-http",
        choices=("streamable-http", "sse", "stdio"),
    )
    args = parser.parse_args()
    config = load_config(args.config)
    if args.transport == "stdio":
        build_mcp(config).run(transport="stdio")
        return

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install dependencies first: pip install -e .") from exc
    uvicorn.run(
        build_asgi_app(args.config, args.transport),
        host=config.server.host,
        port=config.server.port,
    )


if __name__ == "__main__":
    main()
