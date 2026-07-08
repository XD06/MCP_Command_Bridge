# ==========================================================================
#  MCP Command Bridge — Dockerfile (slim build for small VPS)
#
#  Base: python:3.12-slim-bookworm (~150MB)
#  Only installs what the bridge actually dispatches to:
#    - curl        → run_program("curl"), http health check
#    - iputils-ping → ping_host()
#    - traceroute  → trace_route()
#    - nodejs/npm  → run_program("node"/"npm"), run_workspace_script
#    - git         → agent may clone repos
#    - ca-certificates → HTTPS
#
#  Removed (not used by code, saves ~280MB):
#    wget, dnsutils, net-tools, build-essential,
#    vim, less, procps, openssh-client
#
#  NOT Alpine: musl libc breaks some Python wheels + node native modules.
#  slim-bookworm is the sweet spot: small + compatible.
# ==========================================================================
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="MCP Command Bridge"
LABEL org.opencontainers.image.description="Controlled program execution MCP Bridge for mobile AI agents"
LABEL org.opencontainers.image.source="https://github.com/XD06/MCP_Command_Bridge"

# Install only the tools the bridge actually calls — nothing else.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    iputils-ping \
    traceroute \
    nodejs \
    npm \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY pyproject.toml ./
COPY mcp_command_bridge/ ./mcp_command_bridge/
RUN pip install --no-cache-dir -e .

# Copy default config and workspace placeholder
COPY config.vps.yaml ./
RUN mkdir -p logs agent_workspace

# Streamable HTTP is the default transport (MCP recommended standard)
EXPOSE 8765

# Health check: verify the server is listening
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://127.0.0.1:8765/mcp/ || exit 1

# Token is provided via MCB_TOKEN environment variable.
# Config file can be overridden via docker-compose volume mount.
CMD ["python", "-m", "mcp_command_bridge.server", "--config", "config.vps.yaml"]
