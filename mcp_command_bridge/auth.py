from __future__ import annotations

from .config import ServerConfig
from .errors import AuthError


def validate_authorization(header_value: str | None, config: ServerConfig) -> None:
    expected = f"Bearer {config.token}"
    if header_value != expected:
        raise AuthError("invalid bearer token")


def validate_origin(origin: str | None, config: ServerConfig) -> None:
    if not origin or not config.allowed_origins:
        return
    if origin not in config.allowed_origins:
        raise AuthError("origin is not allowed", origin=origin)


def validate_client_ip(client_ip: str | None, config: ServerConfig) -> None:
    if not config.ip_allowlist:
        return
    if not client_ip:
        raise AuthError("client IP could not be determined")
    if client_ip not in config.ip_allowlist:
        raise AuthError("client IP is not allowed", ip=client_ip)
