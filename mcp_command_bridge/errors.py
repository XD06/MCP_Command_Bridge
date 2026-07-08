class BridgeError(Exception):
    """Base error for controlled bridge failures."""

    code = "bridge_error"

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_result(self) -> dict[str, object]:
        result: dict[str, object] = {
            "ok": False,
            "error": self.code,
            "reason": self.message,
        }
        result.update(self.details)
        return result


class ConfigError(BridgeError):
    code = "config_error"


class AuthError(BridgeError):
    code = "auth_error"


class PolicyError(BridgeError):
    code = "policy_denied"


class ExecutionError(BridgeError):
    code = "execution_error"
