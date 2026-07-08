from __future__ import annotations

from pathlib import Path

from .audit import write_audit
from .config import BridgeConfig, capability_details, public_policy
from .errors import BridgeError
from .executor import run_process
from .file_ops import append_file, list_files, make_directory, read_file, write_file
from .http_tools import fetch_url, http_probe
from .network_tools import dns_lookup, ping_host, tcp_probe, trace_route
from .policy import validate_request
from .secrets import mask_args, replace_secret_placeholders
from .system_tools import system_snapshot


class CommandBridge:
    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self._acknowledged_capabilities: set[str] = set()

    def get_policy(self) -> dict[str, object]:
        return public_policy(self.config)

    def get_capability_details(self, name: str) -> dict[str, object]:
        result = capability_details(self.config, name)
        if result.get("ok", True):
            self._acknowledged_capabilities.add(name)
        return result

    def system_snapshot(self) -> dict[str, object]:
        preflight = self._require_capability("system", "system_snapshot", {})
        if preflight:
            return preflight
        return self._tool_call("system_snapshot", {}, lambda: system_snapshot(self.config))

    def http_request(
        self,
        mode: str,
        url: str,
        timeout_seconds: int | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        if mode == "probe":
            return self.http_probe(url, timeout_seconds)
        if mode == "fetch":
            return self.fetch_url(url, timeout_seconds, max_bytes)
        result: dict[str, object] = {
            "ok": False,
            "error": "invalid_mode",
            "reason": "mode must be 'probe' or 'fetch'",
            "mode": mode,
        }
        self._audit("http_request", [str({"mode": mode, "url": url})], "", result)
        return result

    def network_check(
        self,
        mode: str,
        host: str,
        port: int | None = None,
        count: int = 4,
        max_hops: int = 8,
        timeout_seconds: int | None = None,
    ) -> dict[str, object]:
        if mode == "ping":
            return self.ping_host(host, count, timeout_seconds or 10)
        if mode == "dns":
            return self.dns_lookup(host)
        if mode == "tcp":
            if port is None:
                result: dict[str, object] = {
                    "ok": False,
                    "error": "missing_port",
                    "reason": "port is required when mode='tcp'",
                }
                self._audit("network_check", [str({"mode": mode, "host": host})], "", result)
                return result
            return self.tcp_probe(host, port, timeout_seconds or 5)
        if mode == "trace":
            return self.trace_route(host, max_hops, timeout_seconds or 60)
        result = {"ok": False, "error": "invalid_mode", "reason": "mode must be ping, dns, tcp, or trace", "mode": mode}
        self._audit("network_check", [str({"mode": mode, "host": host})], "", result)
        return result

    def workspace(
        self,
        action: str,
        path: str = ".",
        content: str | None = None,
        overwrite: bool = False,
        recursive: bool = False,
        max_entries: int = 200,
    ) -> dict[str, object]:
        if action == "list":
            return self.list_files(path, recursive, max_entries)
        if action == "read":
            return self.read_file(path)
        if action == "write":
            if content is None:
                return self._workspace_missing_content(action, path)
            return self.write_file(path, content, overwrite)
        if action == "append":
            if content is None:
                return self._workspace_missing_content(action, path)
            return self.append_file(path, content)
        if action == "mkdir":
            return self.make_directory(path)
        result: dict[str, object] = {
            "ok": False,
            "error": "invalid_action",
            "reason": "action must be list, read, write, append, or mkdir",
            "action": action,
        }
        self._audit("workspace", [str({"action": action, "path": path})], "", result)
        return result

    def http_probe(self, url: str, timeout_seconds: int | None = None) -> dict[str, object]:
        preflight = self._require_capability("http", "http_probe", {"url": url})
        if preflight:
            return preflight
        return self._tool_call(
            "http_probe",
            {"url": url, "timeout_seconds": timeout_seconds},
            lambda: http_probe(self.config, url, timeout_seconds),
        )

    def fetch_url(
        self,
        url: str,
        timeout_seconds: int | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        preflight = self._require_capability("http", "fetch_url", {"url": url})
        if preflight:
            return preflight
        return self._tool_call(
            "fetch_url",
            {"url": url, "timeout_seconds": timeout_seconds, "max_bytes": max_bytes},
            lambda: fetch_url(self.config, url, timeout_seconds, max_bytes),
        )

    def ping_host(self, host: str, count: int = 4, timeout_seconds: int = 10) -> dict[str, object]:
        preflight = self._require_capability("network", "ping_host", {"host": host})
        if preflight:
            return preflight
        return self._tool_call(
            "ping_host",
            {"host": host, "count": count, "timeout_seconds": timeout_seconds},
            lambda: ping_host(host, count, timeout_seconds),
        )

    def dns_lookup(self, host: str) -> dict[str, object]:
        preflight = self._require_capability("network", "dns_lookup", {"host": host})
        if preflight:
            return preflight
        return self._tool_call("dns_lookup", {"host": host}, lambda: dns_lookup(host))

    def tcp_probe(self, host: str, port: int, timeout_seconds: int = 5) -> dict[str, object]:
        preflight = self._require_capability("network", "tcp_probe", {"host": host, "port": port})
        if preflight:
            return preflight
        return self._tool_call(
            "tcp_probe",
            {"host": host, "port": port, "timeout_seconds": timeout_seconds},
            lambda: tcp_probe(host, port, timeout_seconds),
        )

    def trace_route(self, host: str, max_hops: int = 8, timeout_seconds: int = 60) -> dict[str, object]:
        preflight = self._require_capability("network", "trace_route", {"host": host})
        if preflight:
            return preflight
        return self._tool_call(
            "trace_route",
            {"host": host, "max_hops": max_hops, "timeout_seconds": timeout_seconds},
            lambda: trace_route(host, max_hops, timeout_seconds),
        )

    def run_workspace_script(
        self,
        runtime: str,
        path: str,
        args: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, object]:
        preflight = self._require_capability("workspace", "run_workspace_script", {"path": path})
        if preflight:
            return preflight
        if runtime not in {"python3", "node"}:
            result = {
                "ok": False,
                "error": "policy_denied",
                "reason": "runtime must be python3 or node",
                "runtime": runtime,
                "hint": "Use runtime='python3' for .py scripts or runtime='node' for .js scripts.",
            }
            self._audit("run_workspace_script", [str({"runtime": runtime, "path": path})], "", result)
            return result
        script = self._workspace_script_path(path)
        if script is None:
            result = {
                "ok": False,
                "error": "policy_denied",
                "reason": "script path is outside writable roots",
                "runtime": runtime,
                "path": path,
                "hint": "Use write_file to create scripts inside the fixed workspace, then run them by relative path.",
            }
            self._audit("run_workspace_script", [str({"runtime": runtime, "path": path})], "", result)
            return result
        return self.run_program(runtime, [str(script), *(args or [])], None, timeout_seconds, _internal=True)

    def list_files(
        self,
        path: str = ".",
        recursive: bool = False,
        max_entries: int = 200,
    ) -> dict[str, object]:
        preflight = self._require_capability("workspace", "list_files", {"path": path})
        if preflight:
            return preflight
        return self._file_call(
            "list_files",
            {"path": path, "recursive": recursive, "max_entries": max_entries},
            lambda: list_files(self.config, path, recursive, max_entries),
        )

    def read_file(self, path: str) -> dict[str, object]:
        preflight = self._require_capability("workspace", "read_file", {"path": path})
        if preflight:
            return preflight
        return self._file_call("read_file", {"path": path}, lambda: read_file(self.config, path))

    def write_file(self, path: str, content: str, overwrite: bool = False) -> dict[str, object]:
        preflight = self._require_capability("workspace", "write_file", {"path": path})
        if preflight:
            return preflight
        return self._file_call(
            "write_file",
            {"path": path, "overwrite": overwrite, "bytes": len(content.encode("utf-8"))},
            lambda: write_file(self.config, path, content, overwrite),
        )

    def append_file(self, path: str, content: str) -> dict[str, object]:
        preflight = self._require_capability("workspace", "append_file", {"path": path})
        if preflight:
            return preflight
        return self._file_call(
            "append_file",
            {"path": path, "bytes": len(content.encode("utf-8"))},
            lambda: append_file(self.config, path, content),
        )

    def make_directory(self, path: str) -> dict[str, object]:
        preflight = self._require_capability("workspace", "make_directory", {"path": path})
        if preflight:
            return preflight
        return self._file_call("make_directory", {"path": path}, lambda: make_directory(self.config, path))

    def run_program(
        self,
        program: str,
        args: list[str],
        cwd: str | None = None,
        timeout_seconds: int | None = None,
        _internal: bool = False,
    ) -> dict[str, object]:
        masked_original_args = mask_args(args, self.config.secrets)
        if not _internal and not self.config.server.expose_advanced_tools:
            result: dict[str, object] = {
                "ok": False,
                "error": "advanced_tool_hidden",
                "reason": "run_program is hidden by server.expose_advanced_tools=false.",
                "program": program,
                "args": masked_original_args,
                "hint": "Use task tools such as http_probe, trace_route, workspace file tools, or run_workspace_script.",
            }
            self._audit(program, masked_original_args, cwd or "", result)
            return result
        try:
            args = self._normalize_script_args(program, args)
            program_config, resolved_cwd, timeout = validate_request(
                self.config, program, args, cwd, timeout_seconds
            )
            replaced_args = replace_secret_placeholders(args, self.config.secrets)
            result = run_process(
                program_config.executable or program,
                replaced_args,
                resolved_cwd,
                timeout,
                self.config,
            )
            response = {
                "program": program,
                "args": masked_original_args,
                "cwd": str(resolved_cwd),
                **result,
            }
            self._audit(program, masked_original_args, str(resolved_cwd), response)
            return response
        except BridgeError as exc:
            result = exc.to_result()
            result.update({"program": program, "args": masked_original_args})
            self._audit(program, masked_original_args, cwd or "", result)
            return result

    def _audit(self, program: str, args: list[str], cwd: str, result: dict[str, object]) -> None:
        write_audit(
            self.config.execution.audit_log,
            {
                "program": program,
                "args": args,
                "cwd": cwd,
                "ok": result.get("ok", False),
                "exit_code": result.get("exit_code"),
                "duration_ms": result.get("duration_ms"),
                "error": result.get("error"),
                "reason": result.get("reason"),
            },
        )

    def _file_call(self, operation: str, inputs: dict[str, object], call: object) -> dict[str, object]:
        try:
            result = call()
            self._audit(operation, [str(inputs)], "", result)
            return result
        except BridgeError as exc:
            result = exc.to_result()
            result.update({"operation": operation})
            self._audit(operation, [str(inputs)], "", result)
            return result

    def _tool_call(self, operation: str, inputs: dict[str, object], call: object) -> dict[str, object]:
        try:
            result = call()
            self._audit(operation, [str(inputs)], "", result)
            return result
        except BridgeError as exc:
            result = exc.to_result()
            result.update({"operation": operation})
            self._audit(operation, [str(inputs)], "", result)
            return result

    def _require_capability(
        self,
        capability: str,
        operation: str,
        inputs: dict[str, object],
    ) -> dict[str, object] | None:
        if not self.config.server.require_capability_preflight:
            return None
        if capability in self._acknowledged_capabilities:
            return None
        result: dict[str, object] = {
            "ok": False,
            "error": "preflight_required",
            "reason": f"Call get_capability_details('{capability}') before using {operation}.",
            "capability": capability,
            "operation": operation,
            "required_call": {
                "tool": "get_capability_details",
                "arguments": {"name": capability},
            },
        }
        self._audit(operation, [str(inputs)], "", result)
        return result

    def _workspace_missing_content(self, action: str, path: str) -> dict[str, object]:
        result: dict[str, object] = {
            "ok": False,
            "error": "missing_content",
            "reason": f"content is required when action='{action}'",
            "action": action,
            "path": path,
        }
        self._audit("workspace", [str({"action": action, "path": path})], "", result)
        return result

    def _workspace_script_path(self, path: str) -> Path | None:
        raw = Path(path).expanduser()
        candidates = []
        if raw.is_absolute():
            candidates.append(raw.resolve())
        else:
            for root in self.config.execution.writable_roots:
                parts = raw.parts
                if parts and parts[0] == root.name:
                    candidates.append(root.joinpath(*parts[1:]).resolve())
                candidates.append((root / raw).resolve())
        for candidate in candidates:
            for root in self.config.execution.writable_roots:
                try:
                    candidate.relative_to(root)
                    return candidate
                except ValueError:
                    continue
        return None

    def _normalize_script_args(self, program: str, args: list[str]) -> list[str]:
        if program not in {"python3", "node"} or not args:
            return args
        raw = Path(args[0]).expanduser()
        if raw.is_absolute() or raw.exists():
            return args
        program_config = self.config.programs.get(program)
        if program_config is None:
            return args
        for root in program_config.allowed_script_roots:
            candidate = (root / raw).resolve()
            if candidate.exists() and candidate.is_file():
                return [str(candidate), *args[1:]]
        return args
