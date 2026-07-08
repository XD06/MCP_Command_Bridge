from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigError


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = ""
    allowed_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    expose_advanced_tools: bool = False
    require_capability_preflight: bool = False
    compact_toolset: bool = False
    ip_allowlist: tuple[str, ...] = ()
    rate_limit_per_minute: int = 0


@dataclass(frozen=True)
class ExecutionConfig:
    default_cwd: Path
    allowed_roots: tuple[Path, ...]
    writable_roots: tuple[Path, ...] = ()
    timeout_seconds: int = 30
    max_output_bytes: int = 200_000
    audit_log: Path = Path("logs/audit.jsonl")


@dataclass(frozen=True)
class ProgramConfig:
    enabled: bool = False
    executable: str = ""
    allowed_methods: tuple[str, ...] = ()
    denied_methods: tuple[str, ...] = ()
    allowed_url_prefixes: tuple[str, ...] = ()
    denied_schemes: tuple[str, ...] = ()
    denied_args: tuple[str, ...] = ()
    allowed_subcommands: tuple[str, ...] = ()
    allowed_script_roots: tuple[Path, ...] = ()
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class BridgeConfig:
    server: ServerConfig
    execution: ExecutionConfig
    secrets: dict[str, str] = field(default_factory=dict)
    programs: dict[str, ProgramConfig] = field(default_factory=dict)


def load_config(path: str | Path) -> BridgeConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError("config file does not exist", path=str(config_path))
    raw = _load_mapping(config_path)
    return parse_config(raw, base_dir=config_path.parent)


def parse_config(raw: dict[str, Any], base_dir: str | Path = ".") -> BridgeConfig:
    base = Path(base_dir)
    server_raw = _require_mapping(raw, "server")
    execution_raw = _require_mapping(raw, "execution")
    programs_raw = _require_mapping(raw, "programs")

    token = str(server_raw.get("token", ""))
    env_token = os.environ.get("MCB_TOKEN")
    if env_token:
        token = env_token
    if not token:
        raise ConfigError("server.token is required (set in config or via MCB_TOKEN env var)")

    allowed_roots = tuple(
        _resolve_path(root, base) for root in _require_list(execution_raw, "allowed_roots")
    )
    if not allowed_roots:
        raise ConfigError("execution.allowed_roots must not be empty")

    writable_roots = tuple(
        _resolve_path(root, base) for root in execution_raw.get("writable_roots", ())
    )
    default_cwd = _resolve_path(execution_raw.get("default_cwd", "."), base)
    audit_log = _resolve_path(execution_raw.get("audit_log", "logs/audit.jsonl"), base)

    execution = ExecutionConfig(
        default_cwd=default_cwd,
        allowed_roots=allowed_roots,
        writable_roots=writable_roots,
        timeout_seconds=int(execution_raw.get("timeout_seconds", 30)),
        max_output_bytes=int(execution_raw.get("max_output_bytes", 200_000)),
        audit_log=audit_log,
    )

    server = ServerConfig(
        host=str(server_raw.get("host", "127.0.0.1")),
        port=int(server_raw.get("port", 8765)),
        token=token,
        allowed_origins=tuple(str(item) for item in server_raw.get("allowed_origins", ())),
        allowed_hosts=tuple(str(item) for item in server_raw.get("allowed_hosts", ())),
        expose_advanced_tools=bool(server_raw.get("expose_advanced_tools", False)),
        require_capability_preflight=bool(server_raw.get("require_capability_preflight", False)),
        compact_toolset=bool(server_raw.get("compact_toolset", False)),
        ip_allowlist=tuple(str(item) for item in server_raw.get("ip_allowlist", ())),
        rate_limit_per_minute=int(server_raw.get("rate_limit_per_minute", 0)),
    )

    programs: dict[str, ProgramConfig] = {}
    for name, value in programs_raw.items():
        if not isinstance(value, dict):
            raise ConfigError("program config must be a mapping", program=str(name))
        programs[str(name)] = _parse_program(value, base)

    secrets = {str(key): str(value) for key, value in raw.get("secrets", {}).items()}
    for env_key, env_value in os.environ.items():
        if env_key.startswith("MCB_SECRET_"):
            secret_name = env_key[len("MCB_SECRET_"):]
            if secret_name:
                secrets[secret_name] = env_value
    return BridgeConfig(server=server, execution=execution, secrets=secrets, programs=programs)


def public_policy(config: BridgeConfig) -> dict[str, object]:
    return {
        "summary": "Mobile MCP Command Bridge exposes safe task tools first; use get_capability_details(name) for detailed policy.",
        "capabilities": [
            {
                "name": "http",
                "tools": ["http_request"] if config.server.compact_toolset else ["http_probe", "fetch_url"],
                "description": "Check status or fetch text from allowed HTTP/HTTPS URLs.",
            },
            {
                "name": "network",
                "tools": ["network_check"] if config.server.compact_toolset else ["ping_host", "dns_lookup", "tcp_probe", "trace_route"],
                "description": "Query-only connectivity diagnostics.",
            },
            {
                "name": "workspace",
                "tools": ["workspace"] if config.server.compact_toolset else ["list_files", "read_file", "write_file", "append_file", "make_directory"],
                "description": "Read and write files only inside configured writable roots.",
            },
            {
                "name": "system",
                "tools": ["system_snapshot"],
                "description": "Safe read-only system context without environment variables or secrets.",
            },
            {
                "name": "programs",
                "tools": ["run_program"] if config.server.expose_advanced_tools else [],
                "description": "Advanced structured argv execution. Hidden unless expose_advanced_tools=true.",
            },
        ],
        "recommended_tools": {
            "check_http_status": "Use http_probe(url) instead of curl -o /dev/null -w %{http_code}.",
            "fetch_web_text": "Use fetch_url(url, max_bytes) instead of raw curl when you need page text.",
            "diagnose_connectivity": "Use ping_host, dns_lookup, tcp_probe, or trace_route instead of raw network commands.",
            "workspace_files": "Use list_files/read_file/write_file/append_file/make_directory for files under writable_roots.",
            "inspect_system": "Use system_snapshot instead of writing ad hoc system inspection scripts.",
            "run_scripts": "Write scripts into writable_roots first, then run them with python3 or node.",
        },
        "detail_names": ["http", "network", "workspace", "system", "programs", *sorted(config.programs.keys())],
        "advanced_tools_exposed": config.server.expose_advanced_tools,
        "preflight_required": config.server.require_capability_preflight,
        "compact_toolset": config.server.compact_toolset,
    }


def capability_details(config: BridgeConfig, name: str) -> dict[str, object]:
    name = name.strip()
    if name == "http":
        curl = config.programs.get("curl")
        return {
            "name": "http",
            "tools": {
                "http_probe": "Check an allowed URL and return status.",
                "fetch_url": "Fetch text from an allowed URL with output limit.",
            },
            "allowed_url_prefixes": list(curl.allowed_url_prefixes) if curl else [],
            "allowed_methods": list(curl.allowed_methods) if curl else [],
        }
    if name == "network":
        return {
            "name": "network",
            "tools": {
                "ping_host": {"count_max": 4, "timeout_seconds_max": 15},
                "dns_lookup": "Resolve hostname using local DNS.",
                "tcp_probe": {"port_range": "1-65535", "timeout_seconds_max": 15},
                "trace_route": {"max_hops_max": 12, "timeout_seconds_max": 60},
            },
            "host_rules": "Host must be an IP address or DNS name; shell metacharacters and leading '-' are denied.",
        }
    if name == "workspace":
        return {
            "name": "workspace",
            "tools": ["list_files", "read_file", "write_file", "append_file", "make_directory"],
            "writable_roots": [str(path) for path in config.execution.writable_roots],
            "path_rule": "Use paths relative to the workspace root. '.' or the workspace directory name refers to the root.",
            "list_files": {"recursive": "Optional boolean", "max_entries": "Capped at 500"},
        }
    if name == "system":
        return {
            "name": "system",
            "tools": {"system_snapshot": "Read-only OS, hostname, local IPv4, Python version, and workspace roots."},
            "privacy": "Does not return environment variables, tokens, or secret values.",
        }
    if name == "programs":
        return {
            "name": "programs",
            "programs": sorted(config.programs.keys()),
            "run_program_exposed": config.server.expose_advanced_tools,
            "note": "Use task tools first. run_program is an advanced fallback and may be hidden.",
        }
    if name in config.programs:
        program = config.programs[name]
        return {"name": name, "program": _program_policy(program)}
    return {
        "ok": False,
        "error": "unknown_capability",
        "name": name,
        "available": ["http", "network", "workspace", "system", "programs", *sorted(config.programs.keys())],
    }


def full_policy(config: BridgeConfig) -> dict[str, object]:
    programs: dict[str, object] = {}
    for name, program in config.programs.items():
        programs[name] = _program_policy(program)
    return {
        "programs": programs,
        "execution": {
            "allowed_roots": [str(path) for path in config.execution.allowed_roots],
            "writable_roots": [str(path) for path in config.execution.writable_roots],
            "timeout_seconds": config.execution.timeout_seconds,
            "max_output_bytes": config.execution.max_output_bytes,
        },
    }


def _program_policy(program: ProgramConfig) -> dict[str, object]:
    return {
        "enabled": program.enabled,
        "allowed_methods": list(program.allowed_methods),
        "denied_methods": list(program.denied_methods),
        "allowed_url_prefixes": list(program.allowed_url_prefixes),
        "denied_schemes": list(program.denied_schemes),
        "denied_args": list(program.denied_args),
        "allowed_subcommands": list(program.allowed_subcommands),
        "allowed_script_roots": [str(path) for path in program.allowed_script_roots],
        "timeout_seconds": program.timeout_seconds,
    }


def _parse_program(raw: dict[str, Any], base: Path) -> ProgramConfig:
    return ProgramConfig(
        enabled=bool(raw.get("enabled", False)),
        executable=str(raw.get("executable", "")),
        allowed_methods=tuple(str(item).upper() for item in raw.get("allowed_methods", ())),
        denied_methods=tuple(str(item).upper() for item in raw.get("denied_methods", ())),
        allowed_url_prefixes=tuple(str(item) for item in raw.get("allowed_url_prefixes", ())),
        denied_schemes=tuple(str(item).lower() for item in raw.get("denied_schemes", ())),
        denied_args=tuple(str(item) for item in raw.get("denied_args", ())),
        allowed_subcommands=tuple(str(item) for item in raw.get("allowed_subcommands", ())),
        allowed_script_roots=tuple(
            _resolve_path(item, base) for item in raw.get("allowed_script_roots", ())
        ),
        timeout_seconds=int(raw["timeout_seconds"]) if "timeout_seconds" in raw else None,
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise ConfigError("PyYAML is required to read YAML config", path=str(path)) from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping", path=str(path))
    return data


def _require_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a mapping")
    return value


def _require_list(raw: dict[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ConfigError(f"{key} must be a list")
    return value


def _resolve_path(value: object, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()
