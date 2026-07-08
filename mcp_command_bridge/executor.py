from __future__ import annotations

import subprocess
import time
from pathlib import Path
import locale

from .config import BridgeConfig
from .errors import ExecutionError
from .secrets import mask_text


def run_process(
    executable: str,
    args: list[str],
    cwd: Path,
    timeout_seconds: int,
    config: BridgeConfig,
) -> dict[str, object]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [executable, *args],
            cwd=str(cwd),
            shell=False,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout = _truncate(mask_text(exc.stdout or "", config.secrets), config.execution.max_output_bytes)
        stderr = _truncate(mask_text(exc.stderr or "", config.secrets), config.execution.max_output_bytes)
        return {
            "ok": False,
            "error": "timeout",
            "reason": "process timed out",
            "exit_code": None,
            "stdout": stdout.text,
            "stderr": stderr.text,
            "duration_ms": duration_ms,
            "truncated": stdout.truncated or stderr.truncated,
        }
    except OSError as exc:
        raise ExecutionError("failed to start process", detail=str(exc)) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    stdout = _truncate(mask_text(completed.stdout, config.secrets), config.execution.max_output_bytes)
    stderr = _truncate(mask_text(completed.stderr, config.secrets), config.execution.max_output_bytes)
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": stdout.text,
        "stderr": stderr.text,
        "duration_ms": duration_ms,
        "truncated": stdout.truncated or stderr.truncated,
    }


class TruncatedText:
    def __init__(self, text: str, truncated: bool) -> None:
        self.text = text
        self.truncated = truncated


def _truncate(value: str, max_bytes: int) -> TruncatedText:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return TruncatedText(value, False)
    clipped = encoded[:max_bytes].decode("utf-8", errors="replace")
    return TruncatedText(clipped, True)
