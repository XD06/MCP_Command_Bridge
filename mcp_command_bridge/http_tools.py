from __future__ import annotations

import time
import urllib.error
import urllib.request

from .config import BridgeConfig
from .policy import validate_request
from .secrets import mask_text


def http_probe(config: BridgeConfig, url: str, timeout_seconds: int | None = None) -> dict[str, object]:
    requested_timeout = timeout_seconds or 10
    _, _, timeout = validate_request(config, "curl", ["-I", url], None, requested_timeout)
    started = time.perf_counter()
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "ok": True,
                "url": url,
                "status": response.status,
                "reason": response.reason,
                "duration_ms": _elapsed_ms(started),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": True,
            "url": url,
            "status": exc.code,
            "reason": exc.reason,
            "duration_ms": _elapsed_ms(started),
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": url,
            "error": "http_probe_failed",
            "reason": str(exc),
            "duration_ms": _elapsed_ms(started),
        }


def fetch_url(
    config: BridgeConfig,
    url: str,
    timeout_seconds: int | None = None,
    max_bytes: int | None = None,
) -> dict[str, object]:
    requested_timeout = timeout_seconds or 10
    _, _, timeout = validate_request(config, "curl", [url], None, requested_timeout)
    limit = min(max_bytes or config.execution.max_output_bytes, config.execution.max_output_bytes)
    started = time.perf_counter()
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(limit + 1)
            truncated = len(body) > limit
            text = body[:limit].decode("utf-8", errors="replace")
            text = mask_text(text, config.secrets)
            return {
                "ok": True,
                "url": url,
                "status": response.status,
                "reason": response.reason,
                "content": text,
                "truncated": truncated,
                "duration_ms": _elapsed_ms(started),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(limit + 1)
        truncated = len(body) > limit
        text = body[:limit].decode("utf-8", errors="replace")
        text = mask_text(text, config.secrets)
        return {
            "ok": False,
            "url": url,
            "status": exc.code,
            "reason": exc.reason,
            "content": text,
            "truncated": truncated,
            "duration_ms": _elapsed_ms(started),
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": url,
            "error": "fetch_url_failed",
            "reason": str(exc),
            "duration_ms": _elapsed_ms(started),
        }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
