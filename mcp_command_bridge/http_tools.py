from __future__ import annotations

import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit, quote

from .config import BridgeConfig
from .policy import validate_request
from .secrets import mask_text

# Use a common browser User-Agent to avoid being blocked by anti-bot systems.
# Python-urllib/3.x is commonly blocked (e.g. Douban returns 418).
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _encode_url(url: str) -> str:
    """Percent-encode non-ASCII characters in a URL.

    urllib.request.Request does not handle non-ASCII URLs automatically.
    This function encodes the path and query segments while preserving
    the scheme, netloc, and fragment structure.
    """
    try:
        # If URL is already ASCII, return as-is
        url.encode("ascii")
        return url
    except UnicodeEncodeError:
        pass
    parts = urlsplit(url)
    # Encode path: safe chars include /, @, :, etc. for path semantics
    path = quote(parts.path, safe="/@:%!$&'()*+,;=") if parts.path else ""
    # Encode query: safe chars include =, &, etc.
    query = quote(parts.query, safe="/@:%!$&'()*+,;=?") if parts.query else ""
    # Encode fragment
    fragment = quote(parts.fragment, safe="/@:%!$&'()*+,;=?") if parts.fragment else ""
    return urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def http_probe(config: BridgeConfig, url: str, timeout_seconds: int | None = None) -> dict[str, object]:
    requested_timeout = timeout_seconds or 10
    encoded_url = _encode_url(url)
    _, _, timeout = validate_request(config, "curl", ["-I", encoded_url], None, requested_timeout)
    started = time.perf_counter()
    request = urllib.request.Request(encoded_url, method="HEAD")
    request.add_header("User-Agent", _BROWSER_UA)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "ok": True,
                "url": url,
                "encoded_url": encoded_url if encoded_url != url else None,
                "status": response.status,
                "reason": response.reason,
                "duration_ms": _elapsed_ms(started),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": True,
            "url": url,
            "encoded_url": encoded_url if encoded_url != url else None,
            "status": exc.code,
            "reason": exc.reason,
            "duration_ms": _elapsed_ms(started),
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": url,
            "encoded_url": encoded_url if encoded_url != url else None,
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
    encoded_url = _encode_url(url)
    _, _, timeout = validate_request(config, "curl", [encoded_url], None, requested_timeout)
    limit = min(max_bytes or config.execution.max_output_bytes, config.execution.max_output_bytes)
    started = time.perf_counter()
    request = urllib.request.Request(encoded_url, method="GET")
    request.add_header("User-Agent", _BROWSER_UA)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(limit + 1)
            truncated = len(body) > limit
            text = body[:limit].decode("utf-8", errors="replace")
            text = mask_text(text, config.secrets)
            return {
                "ok": True,
                "url": url,
                "encoded_url": encoded_url if encoded_url != url else None,
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
            "encoded_url": encoded_url if encoded_url != url else None,
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
            "encoded_url": encoded_url if encoded_url != url else None,
            "error": "fetch_url_failed",
            "reason": str(exc),
            "duration_ms": _elapsed_ms(started),
        }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
