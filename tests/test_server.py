import os
import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.config import load_config
from mcp_command_bridge.server import build_asgi_app, build_mcp


def _starlette_testclient_available() -> bool:
    try:
        from starlette.testclient import TestClient  # noqa: F401
        import httpx  # noqa: F401
        return True
    except ImportError:
        return False


_STARLETTE_TC = _starlette_testclient_available()


class ServerTests(unittest.TestCase):
    def test_builds_mcp_and_asgi_app_from_yaml_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            config_path.write_text(
                """
server:
  host: "127.0.0.1"
  port: 8765
  token: "abc"
  allowed_origins: ["http://localhost"]
execution:
  default_cwd: "."
  allowed_roots: ["."]
  audit_log: "audit.jsonl"
programs:
  python3:
    enabled: true
    executable: "python"
    denied_args: ["-c", "-m"]
    allowed_script_roots: ["."]
""",
                encoding="utf-8",
            )
            config = load_config(config_path)
            self.assertEqual(type(build_mcp(config)).__name__, "FastMCP")
            self.assertTrue(callable(build_asgi_app(str(config_path))))


class ServerVpsConfigTests(unittest.TestCase):
    """Test ASGI app builds with VPS-specific security fields."""

    def _write_config(self, root, server_extra=""):
        config_path = root / "config.yaml"
        config_path.write_text(
            f"""
server:
  host: "127.0.0.1"
  port: 8765
  token: "test-token"
  compact_toolset: true
  {server_extra}
execution:
  default_cwd: "."
  allowed_roots: ["."]
  audit_log: "audit.jsonl"
programs:
  curl:
    enabled: true
    executable: "curl"
    allowed_url_prefixes: ["https://example.com/"]
""",
            encoding="utf-8",
        )
        return str(config_path)

    def test_builds_with_ip_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(root, 'ip_allowlist: ["1.2.3.4"]')
            app = build_asgi_app(config_path)
            self.assertTrue(callable(app))

    def test_builds_with_rate_limiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(root, "rate_limit_per_minute: 30")
            app = build_asgi_app(config_path)
            self.assertTrue(callable(app))

    def test_builds_with_ip_allowlist_and_rate_limiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(
                root,
                'ip_allowlist: ["1.2.3.4"]\n  rate_limit_per_minute: 60',
            )
            app = build_asgi_app(config_path)
            self.assertTrue(callable(app))

    def test_mcb_token_env_var_overrides_yaml_in_asgi_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self._write_config(root)  # token is "test-token"
            old = os.environ.pop("MCB_TOKEN", None)
            try:
                os.environ["MCB_TOKEN"] = "env-override-token"
                config = load_config(config_path)
                self.assertEqual(config.server.token, "env-override-token")
                app = build_asgi_app(config_path)
                self.assertTrue(callable(app))
            finally:
                if old is not None:
                    os.environ["MCB_TOKEN"] = old
                else:
                    os.environ.pop("MCB_TOKEN", None)

    def test_config_vps_yaml_parses_correctly(self):
        """config.vps.yaml in the repo should parse without errors."""
        repo_root = Path(__file__).resolve().parent.parent
        vps_config = repo_root / "config.vps.yaml"
        if vps_config.exists():
            config = load_config(str(vps_config))
            self.assertEqual(config.server.host, "0.0.0.0")
            self.assertEqual(config.server.port, 8765)
            # VPS config uses full-control mode (non-compact, advanced tools exposed)
            self.assertFalse(config.server.compact_toolset)
            self.assertTrue(config.server.expose_advanced_tools)
            self.assertGreater(config.server.rate_limit_per_minute, 0)


@unittest.skipUnless(_STARLETTE_TC, "starlette[testclient] + httpx required")
class MiddlewareIntegrationTests(unittest.TestCase):
    """Test the ASGI middleware behavior using Starlette TestClient."""

    def _make_app(self, tmp, token="test-token", ip_allowlist=None, rate_limit=0):
        import yaml
        from starlette.testclient import TestClient

        root = Path(tmp)
        config_path = root / "config.yaml"
        server_section = {
            "host": "127.0.0.1",
            "port": 8765,
            "token": token,
            "compact_toolset": True,
        }
        if ip_allowlist:
            server_section["ip_allowlist"] = ip_allowlist
        if rate_limit:
            server_section["rate_limit_per_minute"] = rate_limit
        data = {
            "server": server_section,
            "execution": {
                "default_cwd": ".",
                "allowed_roots": ["."],
                "audit_log": str(root / "audit.jsonl"),
            },
            "programs": {},
        }
        config_path.write_text(yaml.dump(data), encoding="utf-8")
        app = build_asgi_app(str(config_path))
        # Don't raise on MCP-internal exceptions — we only care about middleware behavior
        return TestClient(app, raise_server_exceptions=False)

    def setUp(self):
        self._old_token = os.environ.pop("MCB_TOKEN", None)
        for key in list(os.environ.keys()):
            if key.startswith("MCB_SECRET_"):
                del os.environ[key]

    def tearDown(self):
        if self._old_token is not None:
            os.environ["MCB_TOKEN"] = self._old_token
        else:
            os.environ.pop("MCB_TOKEN", None)

    def test_missing_token_returns_401(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._make_app(tmp, token="secret-token")
            resp = client.post("/mcp", json={})
            self.assertEqual(resp.status_code, 401)
            self.assertIn("auth_error", resp.json().get("error", ""))

    def test_wrong_token_returns_401(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._make_app(tmp, token="secret-token")
            resp = client.post(
                "/mcp",
                json={},
                headers={"Authorization": "Bearer wrong-token"},
            )
            self.assertEqual(resp.status_code, 401)

    def test_valid_token_passes_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._make_app(tmp, token="secret-token")
            resp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0.1"},
                    },
                },
                headers={"Authorization": "Bearer secret-token"},
            )
            # Should NOT be 401 — it got past auth
            self.assertNotEqual(resp.status_code, 401)

    def test_rate_limiting_returns_429(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._make_app(tmp, token="secret-token", rate_limit=2)
            headers = {"Authorization": "Bearer secret-token"}
            # First 2 requests pass the rate limiter (may return any status)
            client.post("/mcp", json={}, headers=headers)
            client.post("/mcp", json={}, headers=headers)
            # Third request should be rate-limited
            resp = client.post("/mcp", json={}, headers=headers)
            self.assertEqual(resp.status_code, 429)
            self.assertEqual(resp.json()["error"], "rate_limited")
            self.assertIn("Retry-After", resp.headers)

    def test_rate_limiting_per_ip(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._make_app(tmp, token="secret-token", rate_limit=1)
            headers = {"Authorization": "Bearer secret-token"}
            # First request passes
            resp1 = client.post("/mcp", json={}, headers=headers)
            self.assertNotEqual(resp1.status_code, 429)
            # Second request from same IP is blocked
            resp2 = client.post("/mcp", json={}, headers=headers)
            self.assertEqual(resp2.status_code, 429)

    def test_ip_allowlist_blocks_unauthorized_ip(self):
        with tempfile.TemporaryDirectory() as tmp:
            # TestClient's client host is typically "testclient" — won't match "9.9.9.9"
            client = self._make_app(
                tmp, token="secret-token", ip_allowlist=["9.9.9.9"]
            )
            resp = client.post(
                "/mcp",
                json={},
                headers={"Authorization": "Bearer secret-token"},
            )
            self.assertEqual(resp.status_code, 401)

    def test_no_rate_limit_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._make_app(tmp, token="secret-token", rate_limit=0)
            headers = {"Authorization": "Bearer secret-token"}
            # Send many requests — none should be 429
            for _ in range(10):
                resp = client.post("/mcp", json={}, headers=headers)
                self.assertNotEqual(resp.status_code, 429)

    def test_options_request_bypasses_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._make_app(tmp, token="secret-token")
            resp = client.options("/mcp")
            # OPTIONS should pass through (CORS preflight)
            self.assertNotEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
