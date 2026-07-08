from __future__ import annotations

from pathlib import Path

from .config import BridgeConfig
from .errors import PolicyError


def list_files(
    config: BridgeConfig,
    path: str = ".",
    recursive: bool = False,
    max_entries: int = 200,
) -> dict[str, object]:
    target = _resolve_readable(config, path)
    if not target.exists():
        raise PolicyError("path does not exist", path=str(target))
    if not target.is_dir():
        raise PolicyError("path is not a directory", path=str(target))
    entries = []
    max_entries = max(1, min(int(max_entries), 500))
    iterator = target.rglob("*") if recursive else target.iterdir()
    for child in sorted(iterator, key=lambda item: str(item).lower()):
        if len(entries) >= max_entries:
            break
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "relative_path": str(child.relative_to(target)),
                "type": "dir" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else None,
            }
        )
    return {
        "ok": True,
        "path": str(target),
        "recursive": recursive,
        "max_entries": max_entries,
        "truncated": len(entries) >= max_entries,
        "entries": entries,
    }


def read_file(config: BridgeConfig, path: str) -> dict[str, object]:
    target = _resolve_readable(config, path)
    if not target.exists():
        raise PolicyError("path does not exist", path=str(target))
    if not target.is_file():
        raise PolicyError("path is not a file", path=str(target))
    text = target.read_text(encoding="utf-8")
    truncated = False
    encoded = text.encode("utf-8")
    if len(encoded) > config.execution.max_output_bytes:
        text = encoded[: config.execution.max_output_bytes].decode("utf-8", errors="replace")
        truncated = True
    return {"ok": True, "path": str(target), "content": text, "truncated": truncated}


def write_file(config: BridgeConfig, path: str, content: str, overwrite: bool = False) -> dict[str, object]:
    target = _resolve_writable(config, path)
    if target.exists() and not overwrite:
        raise PolicyError("file already exists; set overwrite=true to replace it", path=str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(target), "bytes": len(content.encode("utf-8"))}


def append_file(config: BridgeConfig, path: str, content: str) -> dict[str, object]:
    target = _resolve_writable(config, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(content)
    return {"ok": True, "path": str(target), "bytes": len(content.encode("utf-8"))}


def make_directory(config: BridgeConfig, path: str) -> dict[str, object]:
    target = _resolve_writable(config, path)
    target.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": str(target)}


def _resolve_readable(config: BridgeConfig, path: str) -> Path:
    target = _resolve_against_roots(config.execution.writable_roots, path)
    if target is None:
        raise PolicyError("path is outside writable roots", path=path)
    return target


def _resolve_writable(config: BridgeConfig, path: str) -> Path:
    if not config.execution.writable_roots:
        raise PolicyError("no writable roots are configured")
    target = _resolve_against_roots(config.execution.writable_roots, path)
    if target is None:
        raise PolicyError("path is outside writable roots", path=path)
    return target


def _resolve_against_roots(roots: tuple[Path, ...], path: str) -> Path | None:
    raw = Path(path).expanduser()
    if raw.is_absolute():
        candidates = [raw.resolve()]
    else:
        candidates = []
        for root in roots:
            parts = raw.parts
            if parts and parts[0] == root.name:
                candidates.append(root.joinpath(*parts[1:]).resolve())
            candidates.append((root / raw).resolve())
    for candidate in candidates:
        if any(_is_relative_to(candidate, root) for root in roots):
            return candidate
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
