from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .config import BridgeConfig, ProgramConfig
from .errors import PolicyError


def validate_request(
    config: BridgeConfig,
    program: str,
    args: list[str],
    cwd: str | None,
    timeout_seconds: int | None,
) -> tuple[ProgramConfig, Path, int]:
    if program not in config.programs:
        raise PolicyError("program is not in allowlist", program=program)
    program_config = config.programs[program]
    if not program_config.enabled:
        raise PolicyError("program is disabled", program=program)
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise PolicyError("args must be an array of strings", program=program)

    resolved_cwd = resolve_allowed_cwd(config, cwd)
    effective_timeout = _resolve_timeout(config, program_config, timeout_seconds)
    _deny_args(program_config, args, program)

    if program == "curl":
        _validate_curl(program_config, args)
    elif program == "npm":
        _validate_npm(program_config, args)
    elif program in {"node", "python3"}:
        _validate_script_program(program_config, args, program)

    return program_config, resolved_cwd, effective_timeout


def resolve_allowed_cwd(config: BridgeConfig, cwd: str | None) -> Path:
    target = Path(cwd).expanduser() if cwd else config.execution.default_cwd
    target = target.resolve()
    if not target.exists() or not target.is_dir():
        raise PolicyError("cwd does not exist or is not a directory", cwd=str(target))
    # Empty allowed_roots = allow any directory (container sandbox mode)
    if config.execution.allowed_roots and not any(
        _is_relative_to(target, root) for root in config.execution.allowed_roots
    ):
        raise PolicyError("cwd is outside allowed roots", cwd=str(target))
    return target


def _resolve_timeout(
    config: BridgeConfig,
    program_config: ProgramConfig,
    requested: int | None,
) -> int:
    maximum = program_config.timeout_seconds or config.execution.timeout_seconds
    if requested is None:
        return maximum
    if requested < 1:
        raise PolicyError("timeout_seconds must be at least 1", timeout_seconds=requested)
    if requested > maximum:
        raise PolicyError(
            "timeout_seconds exceeds configured maximum",
            timeout_seconds=requested,
            maximum=maximum,
        )
    return requested


def _deny_args(program_config: ProgramConfig, args: list[str], program: str) -> None:
    for arg in args:
        if arg in program_config.denied_args:
            hint = None
            if program == "curl" and arg in {"-o", "--output", "-O", "--remote-name"}:
                hint = "Use http_probe(url) for status checks, or fetch_url(url) for page text. File output flags are blocked."
            raise PolicyError("program argument denied", program=program, denied_arg=arg, hint=hint)


def _validate_curl(program_config: ProgramConfig, args: list[str]) -> None:
    method = "GET"
    urls: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"-X", "--request"}:
            if i + 1 >= len(args):
                raise PolicyError("curl request method flag requires a value", program="curl")
            method = args[i + 1].upper()
            i += 2
            continue
        if arg.startswith("-X") and len(arg) > 2:
            method = arg[2:].upper()
        if arg in {"-I", "--head"}:
            method = "HEAD"
        if "://" in arg:
            urls.append(arg)
        i += 1

    if method in program_config.denied_methods:
        raise PolicyError("curl method denied", program="curl", method=method)
    if program_config.allowed_methods and method not in program_config.allowed_methods:
        raise PolicyError("curl method is not allowed", program="curl", method=method)
    if not urls:
        raise PolicyError(
            "curl URL is required",
            program="curl",
            hint="Use get_capability_details('curl') instead of curl --help, or pass an allowed URL.",
        )

    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme.lower() in program_config.denied_schemes:
            raise PolicyError("curl URL scheme denied", program="curl", url=url)
        # Empty allowed_url_prefixes = allow all URLs
        if program_config.allowed_url_prefixes and not any(
            _url_matches_prefix(url, prefix) for prefix in program_config.allowed_url_prefixes
        ):
            raise PolicyError(
                "curl URL prefix is not allowed",
                program="curl",
                url=url,
                hint="Call get_policy to inspect allowed_url_prefixes, or use an allowed URL with http_probe/fetch_url.",
            )


def _validate_npm(program_config: ProgramConfig, args: list[str]) -> None:
    if not args:
        raise PolicyError("npm subcommand is required", program="npm")
    subcommand = args[0]
    # Empty allowed_subcommands = allow all subcommands
    if program_config.allowed_subcommands and subcommand not in program_config.allowed_subcommands:
        raise PolicyError("npm subcommand is not allowed", program="npm", subcommand=subcommand)
    if subcommand == "run" and len(args) < 2:
        raise PolicyError("npm run requires a script name", program="npm")


def _validate_script_program(program_config: ProgramConfig, args: list[str], program: str) -> None:
    if not args:
        raise PolicyError("script path is required", program=program)
    # If first arg is a flag (e.g. -c, -m, -e), skip script path validation
    if args[0].startswith("-"):
        return
    script = Path(args[0]).expanduser().resolve()
    if not script.exists() or not script.is_file():
        raise PolicyError(
            "script path does not exist",
            program=program,
            script=str(script),
            hint="Use write_file to create scripts inside the fixed workspace, then run_workspace_script(runtime, path).",
        )
    # Empty allowed_script_roots = allow all paths (container sandbox mode)
    if program_config.allowed_script_roots and not any(
        _is_relative_to(script, root) for root in program_config.allowed_script_roots
    ):
        raise PolicyError("script path is outside allowed roots", program=program, script=str(script))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _url_matches_prefix(url: str, prefix: str) -> bool:
    if url.startswith(prefix):
        return True
    if prefix.endswith("/") and url == prefix[:-1]:
        return True
    return False
