# ==========================================================================
#  MCP Command Bridge — Dockerfile
#  Debian-slim base (NOT Alpine) because the bridge dispatches real system
#  commands: curl, ping, traceroute, node, npm, git, etc.
#  Runs as root inside the container so the agent can apt-get install
#  additional tools at runtime. Isolation comes from Docker itself.
# ==========================================================================
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="MCP Command Bridge"
LABEL org.opencontainers.image.description="Controlled program execution MCP Bridge for mobile AI agents"
LABEL org.opencontainers.image.source="https://github.com/XD06/MCP_Command_Bridge"

# Install a comprehensive set of system tools the bridge can dispatch to.
# - Network:   curl, wget, iputils-ping, traceroute, dnsutils, net-tools
# - Runtimes:  nodejs, npm
# - Build:     build-essential, git (so the agent can clone repos / compile)
# - Utils:     vim, less, procps, ca-certificates, openssh-client
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    iputils-ping \
    traceroute \
    dnsutils \
    net-tools \
    nodejs \
    npm \
    build-essential \
    git \
    vim \
    less \
    procps \
    ca-certificates \
    openssh-client \
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
