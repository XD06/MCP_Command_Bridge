import unittest

from mcp_command_bridge.auth import validate_authorization, validate_origin, validate_client_ip
from mcp_command_bridge.config import ServerConfig
from mcp_command_bridge.errors import AuthError


class AuthTests(unittest.TestCase):
    def test_accepts_expected_bearer_token(self):
        config = ServerConfig(token="abc")
        validate_authorization("Bearer abc", config)

    def test_rejects_invalid_bearer_token(self):
        config = ServerConfig(token="abc")
        with self.assertRaises(AuthError):
            validate_authorization("Bearer wrong", config)

    def test_rejects_disallowed_origin(self):
        config = ServerConfig(token="abc", allowed_origins=("http://localhost",))
        with self.assertRaises(AuthError):
            validate_origin("http://evil.example", config)


class ClientIpTests(unittest.TestCase):
    def test_empty_allowlist_allows_any_ip(self):
        config = ServerConfig(token="abc")
        validate_client_ip("1.2.3.4", config)
        validate_client_ip("9.8.7.6", config)

    def test_empty_allowlist_allows_none_ip(self):
        config = ServerConfig(token="abc")
        validate_client_ip(None, config)

    def test_allowed_ip_passes(self):
        config = ServerConfig(token="abc", ip_allowlist=("1.2.3.4", "5.6.7.8"))
        validate_client_ip("1.2.3.4", config)
        validate_client_ip("5.6.7.8", config)

    def test_blocked_ip_raises_auth_error(self):
        config = ServerConfig(token="abc", ip_allowlist=("1.2.3.4",))
        with self.assertRaises(AuthError) as ctx:
            validate_client_ip("9.8.7.6", config)
        self.assertEqual(ctx.exception.details.get("ip"), "9.8.7.6")

    def test_none_ip_with_allowlist_raises(self):
        config = ServerConfig(token="abc", ip_allowlist=("1.2.3.4",))
        with self.assertRaises(AuthError):
            validate_client_ip(None, config)

    def test_single_ip_allowlist(self):
        config = ServerConfig(token="abc", ip_allowlist=("203.0.113.50",))
        validate_client_ip("203.0.113.50", config)
        with self.assertRaises(AuthError):
            validate_client_ip("203.0.113.51", config)


if __name__ == "__main__":
    unittest.main()
