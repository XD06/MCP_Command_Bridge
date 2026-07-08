from __future__ import annotations

import re

SECRET_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
MASK = "[REDACTED]"


def replace_secret_placeholders(args: list[str], secrets: dict[str, str]) -> list[str]:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return secrets.get(name, match.group(0))

    return [SECRET_PATTERN.sub(replace, arg) for arg in args]


def mask_text(value: str, secrets: dict[str, str]) -> str:
    masked = value
    for secret in sorted(secrets.values(), key=len, reverse=True):
        if secret:
            masked = masked.replace(secret, MASK)
    return SECRET_PATTERN.sub(MASK, masked)


def mask_args(args: list[str], secrets: dict[str, str]) -> list[str]:
    return [mask_text(arg, secrets) for arg in args]
