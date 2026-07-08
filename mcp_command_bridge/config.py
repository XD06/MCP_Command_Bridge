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

    allowed_roots_list = execution_raw.get("allowed_roots", [])
    if not isinstance(allowed_roots_list, list):
        raise ConfigError("execution.allowed_roots must be a list")
    # Empty allowed_roots = allow any directory (container sandbox mode)
    allowed_roots = tuple(
        _resolve_path(root, base) for root in allowed_roots_list
    )

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
    # Build dynamic descriptions based on actual config
    unrestricted = config.server.expose_advanced_tools and not config.execution.allowed_roots
    if unrestricted:
        summary = (
            "MCP Command Bridge — full container control mode. "
            "You can run programs (bash, curl, python3, node, git, apt-get, pip, wget, npm), "
            "read/write files, make HTTP requests with any method/headers via curl, "
            "and execute scripts. The container is your sandbox.\n"
            "IMPORTANT: Always save files under /app/agent_workspace (maps to host data/workspace/) "
            "or /app/projects (maps to host data/projects/) for persistence across container restarts. "
            "All operations are audit-logged to /app/logs/audit.jsonl (maps to host data/logs/)."
        )
    else:
        summary = (
            "Mobile MCP Command Bridge exposes safe task tools first; "
            "use get_capability_details(name) for detailed policy."
        )

    http_tools = ["http_request"] if config.server.compact_toolset else ["http_probe", "fetch_url"]
    if config.server.expose_advanced_tools and "curl" in config.programs:
        http_tools.append("run_program(curl)")

    return {
        "summary": summary,
        "capabilities": [
            {
                "name": "http",
                "tools": http_tools,
                "description": (
                    "http_probe: check URL status. fetch_url: fetch page text. "
                    "run_program('curl'): full HTTP with any method, headers, POST body — no restrictions."
                    if config.server.expose_advanced_tools
                    else "Check status or fetch text from allowed HTTP/HTTPS URLs."
                ),
            },
            {
                "name": "network",
                "tools": ["network_check"] if config.server.compact_toolset else ["ping_host", "dns_lookup", "tcp_probe", "trace_route"],
                "description": "Query-only connectivity diagnostics: ping, DNS, TCP probe, traceroute.",
            },
            {
                "name": "workspace",
                "tools": ["workspace"] if config.server.compact_toolset else ["list_files", "read_file", "write_file", "append_file", "make_directory"],
                "description": (
                    f"Read/write files in: {[str(p) for p in config.execution.writable_roots]}. "
                    "Use write_file to create scripts, then run_program to execute them.\n"
                    "PERSISTENCE: /app/agent_workspace → host data/workspace/, /app/projects → host data/projects/. "
                    "Files saved elsewhere in the container will be LOST on restart."
                ),
            },
            {
                "name": "system",
                "tools": ["system_snapshot"],
                "description": "Read-only OS/kernel/Python/IP info. For env vars use run_program('bash', ['-c', 'env']).",
            },
            {
                "name": "programs",
                "tools": ["run_program"] if config.server.expose_advanced_tools else [],
                "description": (
                    f"Execute any configured program with structured argv (shell=False). "
                    f"Available: {sorted(config.programs.keys())}. "
                    f"Each has its own timeout. No URL/method/path restrictions in full-control mode."
                    if config.server.expose_advanced_tools
                    else "Advanced structured argv execution. Hidden unless expose_advanced_tools=true."
                ),
            },
        ],
        "recommended_tools": {
            "check_http_status": "Use http_probe(url) for quick status check, or run_program('curl', [...]) for full control.",
            "fetch_web_text": "Use fetch_url(url, max_bytes) for page text, or run_program('curl', [...]) for POST/custom headers.",
            "diagnose_connectivity": "Use ping_host, dns_lookup, tcp_probe, or trace_route.",
            "workspace_files": "Use write_file to create scripts, then run_program to execute them.",
            "inspect_system": "Use system_snapshot for basic info, or run_program('bash', ['-c', '...']) for detailed inspection.",
            "run_scripts": "Write scripts with write_file, then run via run_program('python3', ['script.py']) or run_program('node', ['script.js']).",
            "install_packages": "run_program('pip', ['install', 'pkg']) or run_program('apt-get', ['install', '-y', 'pkg']).",
            "git_operations": "run_program('git', ['clone', 'url', 'path']) etc.",
            "persistence": "IMPORTANT: Save files under /app/agent_workspace or /app/projects — these map to host and survive restarts. Other paths are ephemeral.",
            "audit_trail": "All run_program calls are logged to /app/logs/audit.jsonl (host: data/logs/). Check with read_file('../logs/audit.jsonl').",
        },
        "persistence": {
            "workspace": "/app/agent_workspace → host: data/workspace/",
            "projects": "/app/projects → host: data/projects/",
            "logs": "/app/logs/audit.jsonl → host: data/logs/audit.jsonl",
            "warning": "Files saved outside these paths are EPHEMERAL and will be lost on container restart.",
        },
        "detail_names": ["http", "network", "workspace", "system", "programs", *sorted(config.programs.keys())],
        "advanced_tools_exposed": config.server.expose_advanced_tools,
        "preflight_required": config.server.require_capability_preflight,
        "compact_toolset": config.server.compact_toolset,
        "mode": "full_control" if unrestricted else "restricted",
    }


def capability_details(config: BridgeConfig, name: str) -> dict[str, object]:
    name = name.strip()
    if name == "http":
        curl = config.programs.get("curl")
        curl_unrestricted = curl and not curl.allowed_url_prefixes and not curl.allowed_methods and not curl.denied_args
        return {
            "name": "http",
            "tools": {
                "http_probe": "Check a URL and return HTTP status (HEAD request).",
                "fetch_url": "Fetch page text from a URL (GET, with output size limit).",
            },
            "curl_via_run_program": {
                "available": config.server.expose_advanced_tools and curl is not None,
                "description": (
                    "Full HTTP client: any method (GET/POST/PUT/DELETE/PATCH), custom headers, "
                    "POST body, cookies, etc. No URL/method/header restrictions."
                    if curl_unrestricted
                    else "HTTP client with configured restrictions."
                ),
                "example": "run_program('curl', ['-X', 'POST', '-H', 'Content-Type: application/json', '-d', '{\"key\":\"val\"}', 'https://api.example.com/'])",
            },
            "allowed_url_prefixes": (
                "(empty = all URLs allowed)" if curl and not curl.allowed_url_prefixes
                else list(curl.allowed_url_prefixes) if curl else []
            ),
            "allowed_methods": (
                "(empty = all methods allowed)" if curl and not curl.allowed_methods
                else list(curl.allowed_methods) if curl else []
            ),
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
            "tip": "Use write_file to create Python/Node scripts, then run_program to execute them.",
            "persistence": {
                "persistent_paths": [
                    "/app/agent_workspace → host: data/workspace/",
                    "/app/projects → host: data/projects/",
                    "/app/logs/audit.jsonl → host: data/logs/audit.jsonl",
                ],
                "ephemeral_warning": "Files saved to other paths (e.g. /tmp, /root) will be LOST on container restart. Always use /app/agent_workspace for important files.",
            },
            "audit_log": "All run_program calls are recorded to /app/logs/audit.jsonl. Read it with read_file('../logs/audit.jsonl') to review operation history.",
        }
    if name == "system":
        return {
            "name": "system",
            "tools": {"system_snapshot": "Read-only OS, hostname, local IPv4, Python version, and workspace roots."},
            "note": (
                "system_snapshot does not return env vars. "
                "For env vars or detailed system info, use run_program('bash', ['-c', 'env']) "
                "or run_program('bash', ['-c', 'cat /proc/cpuinfo']) etc."
                if config.server.expose_advanced_tools
                else "Does not return environment variables, tokens, or secret values."
            ),
        }
    if name == "programs":
        programs_info = {}
        for pname, pconfig in config.programs.items():
            programs_info[pname] = {
                "enabled": pconfig.enabled,
                "timeout_seconds": pconfig.timeout_seconds or config.execution.timeout_seconds,
                "restrictions": _program_restrictions_summary(pconfig),
            }
        return {
            "name": "programs",
            "programs": programs_info,
            "run_program_exposed": config.server.expose_advanced_tools,
            "cwd_rule": (
                "Any directory in the container (allowed_roots is empty = unrestricted)."
                if not config.execution.allowed_roots
                else f"Must be inside: {[str(p) for p in config.execution.allowed_roots]}"
            ),
            "note": (
                "Full-control mode: all programs enabled with no arg/method/URL/path restrictions. "
                "Use run_program(program, args, cwd, timeout_seconds)."
                if config.server.expose_advanced_tools and not config.execution.allowed_roots
                else "Use task tools first. run_program is an advanced fallback."
            ),
            "audit": "Every run_program call is logged to /app/logs/audit.jsonl (host: data/logs/audit.jsonl) with timestamp, program, args, exit code, and duration.",
            "persistence_reminder": "Save important outputs under /app/agent_workspace or /app/projects for persistence.",
        }
    if name in config.programs:
        program = config.programs[name]
        result = {"name": name, "program": _program_policy(program)}
        result["restrictions_summary"] = _program_restrictions_summary(program)
        return result
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
        "allowed_methods": list(program.allowed_methods) if program.allowed_methods else "(empty = all allowed)",
        "denied_methods": list(program.denied_methods),
        "allowed_url_prefixes": list(program.allowed_url_prefixes) if program.allowed_url_prefixes else "(empty = all URLs)",
        "denied_schemes": list(program.denied_schemes),
        "denied_args": list(program.denied_args) if program.denied_args else "(empty = no args blocked)",
        "allowed_subcommands": list(program.allowed_subcommands) if program.allowed_subcommands else "(empty = all subcommands)",
        "allowed_script_roots": [str(path) for path in program.allowed_script_roots] if program.allowed_script_roots else "(empty = any path)",
        "timeout_seconds": program.timeout_seconds,
    }


def _program_restrictions_summary(program: ProgramConfig) -> str:
    """Return a human-readable summary of what's restricted for this program."""
    if not program.enabled:
        return "disabled"
    parts = []
    if not program.denied_args and not program.denied_methods and not program.allowed_url_prefixes and not program.allowed_subcommands and not program.allowed_script_roots:
        return "no restrictions (full access)"
    if program.denied_args:
        parts.append(f"denied args: {list(program.denied_args)}")
    if program.denied_methods:
        parts.append(f"denied methods: {list(program.denied_methods)}")
    if program.allowed_url_prefixes:
        parts.append(f"URL whitelist: {list(program.allowed_url_prefixes)}")
    if program.allowed_subcommands:
        parts.append(f"subcommand whitelist: {list(program.allowed_subcommands)}")
    if program.allowed_script_roots:
        parts.append(f"script path restricted to: {[str(p) for p in program.allowed_script_roots]}")
    return "; ".join(parts) if parts else "no restrictions"


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
