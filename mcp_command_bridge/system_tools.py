from __future__ import annotations

import platform
import socket
import sys
from datetime import datetime, timezone

from .config import BridgeConfig


def system_snapshot(config: BridgeConfig) -> dict[str, object]:
    return {
        "ok": True,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "hostname": socket.gethostname(),
        "local_ipv4": _local_ipv4_addresses(),
        "workspace_roots": [str(path) for path in config.execution.writable_roots],
        "allowed_roots": [str(path) for path in config.execution.allowed_roots],
        "advanced_tools_exposed": config.server.expose_advanced_tools,
        "preflight_required": config.server.require_capability_preflight,
    }


def _local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    hostname = socket.gethostname()
    try:
        for result in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            addresses.add(result[4][0])
    except OSError:
        pass
    addresses.discard("127.0.0.1")
    return sorted(addresses)
