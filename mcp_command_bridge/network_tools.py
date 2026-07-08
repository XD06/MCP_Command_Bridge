from __future__ import annotations

import ipaddress
import os
import re
import socket
import subprocess
import time
import shutil
import platform

from .errors import PolicyError

HOST_PATTERN = re.compile(r"^[A-Za-z0-9.-]{1,253}$")

# Force UTF-8 for subprocess I/O in minimal containers.
_UTF8_ENV = {
    **os.environ,
    "LANG": os.environ.get("LANG", "C.UTF-8"),
    "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
}


def _build_ping_command(host: str, count: int, timeout_seconds: int) -> list[str]:
    """Build platform-correct ping argument list (Windows: -n/-w ms, Linux: -c/-W s)."""
    if platform.system() == "Windows":
        return ["ping", "-n", str(count), "-w", str(timeout_seconds * 1000), host]
    return ["ping", "-c", str(count), "-W", str(timeout_seconds), host]


def ping_host(host: str, count: int = 4, timeout_seconds: int = 10) -> dict[str, object]:
    _validate_host(host)
    count = max(1, min(int(count), 4))
    timeout_seconds = max(1, min(int(timeout_seconds), 15))
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            _build_ping_command(host, count, timeout_seconds),
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds + 2,
            env=_UTF8_ENV,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "host": host,
            "error": "timeout",
            "reason": "ping timed out",
            "duration_ms": _elapsed_ms(started),
        }
    except OSError as exc:
        return {
            "ok": False,
            "host": host,
            "error": "ping_failed",
            "reason": str(exc),
            "duration_ms": _elapsed_ms(started),
        }
    return {
        "ok": completed.returncode == 0,
        "host": host,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "duration_ms": _elapsed_ms(started),
    }


def dns_lookup(host: str) -> dict[str, object]:
    _validate_host(host)
    started = time.perf_counter()
    try:
        results = socket.getaddrinfo(host, None)
    except OSError as exc:
        return {
            "ok": False,
            "host": host,
            "error": "dns_lookup_failed",
            "reason": str(exc),
            "duration_ms": _elapsed_ms(started),
        }
    addresses = sorted({item[4][0] for item in results})
    return {"ok": True, "host": host, "addresses": addresses, "duration_ms": _elapsed_ms(started)}


def tcp_probe(host: str, port: int, timeout_seconds: int = 5) -> dict[str, object]:
    _validate_host(host)
    port = int(port)
    if port < 1 or port > 65535:
        raise PolicyError("port must be between 1 and 65535", port=port)
    timeout_seconds = max(1, min(int(timeout_seconds), 15))
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {
                "ok": True,
                "host": host,
                "port": port,
                "open": True,
                "duration_ms": _elapsed_ms(started),
            }
    except OSError as exc:
        return {
            "ok": True,
            "host": host,
            "port": port,
            "open": False,
            "reason": str(exc),
            "duration_ms": _elapsed_ms(started),
        }


def trace_route(host: str, max_hops: int = 8, timeout_seconds: int = 60) -> dict[str, object]:
    _validate_host(host)
    max_hops = max(1, min(int(max_hops), 12))
    timeout_seconds = max(5, min(int(timeout_seconds), 60))
    executable = "tracert" if shutil.which("tracert") else "traceroute"
    if executable == "tracert":
        command = [executable, "-d", "-h", str(max_hops), "-w", "1000", host]
    else:
        command = [executable, "-n", "-m", str(max_hops), "-w", "1", host]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            env=_UTF8_ENV,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "host": host,
            "error": "timeout",
            "reason": "trace route timed out",
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": (exc.stderr or "")[-4000:],
            "duration_ms": _elapsed_ms(started),
        }
    except OSError as exc:
        return {
            "ok": False,
            "host": host,
            "error": "trace_route_failed",
            "reason": str(exc),
            "duration_ms": _elapsed_ms(started),
        }
    return {
        "ok": completed.returncode == 0,
        "host": host,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "duration_ms": _elapsed_ms(started),
    }


def _validate_host(host: str) -> None:
    if not host or len(host) > 253:
        raise PolicyError("host is required and must be at most 253 characters", host=host)
    try:
        ipaddress.ip_address(host)
        return
    except ValueError:
        pass
    if not HOST_PATTERN.fullmatch(host) or ".." in host or host.startswith("-"):
        raise PolicyError("host contains unsupported characters", host=host)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
