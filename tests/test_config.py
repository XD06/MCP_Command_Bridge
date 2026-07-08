import os
import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.config import ServerConfig, parse_config


class ConfigTests(unittest.TestCase):
    def test_parse_config_resolves_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw = {
                "server": {"token": "abc"},
                "execution": {
                    "default_cwd": ".",
                    "allowed_roots": ["."],
                    "audit_log": "logs/audit.jsonl",
                },
                "programs": {
                    "python3": {
                        "enabled": True,
                        "executable": "python",
                        "allowed_script_roots": ["."],
                    }
                },
                "secrets": {"A": "B"},
            }
            config = parse_config(raw, base)
            self.assertEqual(config.execution.default_cwd, base.resolve())
            self.assertEqual(config.execution.allowed_roots[0], base.resolve())
            self.assertEqual(config.programs["python3"].allowed_script_roots[0], base.resolve())


class ServerConfigDefaultsTests(unittest.TestCase):
    def test_default_ip_allowlist_is_empty(self):
        config = ServerConfig(token="abc")
        self.assertEqual(config.ip_allowlist, ())

    def test_default_rate_limit_is_zero(self):
        config = ServerConfig(token="abc")
        self.assertEqual(config.rate_limit_per_minute, 0)

    def test_ip_allowlist_can_be_set(self):
        config = ServerConfig(token="abc", ip_allowlist=("1.2.3.4",))
        self.assertEqual(config.ip_allowlist, ("1.2.3.4",))

    def test_rate_limit_can_be_set(self):
        config = ServerConfig(token="abc", rate_limit_per_minute=60)
        self.assertEqual(config.rate_limit_per_minute, 60)


class EnvVarOverrideTests(unittest.TestCase):
    def _base_raw(self):
        return {
            "server": {"token": "yaml-token"},
            "execution": {
                "default_cwd": ".",
                "allowed_roots": ["."],
            },
            "programs": {},
            "secrets": {"EXISTING": "yaml-secret"},
        }

    def setUp(self):
        # Clean any leftover env vars from other tests
        for key in list(os.environ.keys()):
            if key.startswith("MCB_TOKEN") or key.startswith("MCB_SECRET_"):
                del os.environ[key]

    def tearDown(self):
        for key in list(os.environ.keys()):
            if key.startswith("MCB_TOKEN") or key.startswith("MCB_SECRET_"):
                del os.environ[key]

    def test_mcb_token_env_var_overrides_yaml(self):
        os.environ["MCB_TOKEN"] = "env-token-123"
        config = parse_config(self._base_raw(), base_dir=".")
        self.assertEqual(config.server.token, "env-token-123")

    def test_yaml_token_used_when_no_env_var(self):
        config = parse_config(self._base_raw(), base_dir=".")
        self.assertEqual(config.server.token, "yaml-token")

    def test_mcb_token_required_if_not_in_yaml_or_env(self):
        raw = self._base_raw()
        raw["server"]["token"] = ""
        with self.assertRaises(Exception):
            parse_config(raw, base_dir=".")

    def test_mcb_secret_env_vars_merged_into_secrets(self):
        os.environ["MCB_SECRET_NEW_KEY"] = "env-secret-value"
        config = parse_config(self._base_raw(), base_dir=".")
        self.assertEqual(config.secrets["NEW_KEY"], "env-secret-value")
        self.assertEqual(config.secrets["EXISTING"], "yaml-secret")

    def test_mcb_secret_env_var_overrides_yaml_secret(self):
        os.environ["MCB_SECRET_EXISTING"] = "overridden-by-env"
        config = parse_config(self._base_raw(), base_dir=".")
        self.assertEqual(config.secrets["EXISTING"], "overridden-by-env")

    def test_multiple_mcb_secret_env_vars(self):
        os.environ["MCB_SECRET_API_KEY"] = "key1"
        os.environ["MCB_SECRET_DB_PASSWORD"] = "pass2"
        config = parse_config(self._base_raw(), base_dir=".")
        self.assertEqual(config.secrets["API_KEY"], "key1")
        self.assertEqual(config.secrets["DB_PASSWORD"], "pass2")

    def test_empty_secret_name_ignored(self):
        os.environ["MCB_SECRET_"] = "should-be-ignored"
        config = parse_config(self._base_raw(), base_dir=".")
        self.assertNotIn("", config.secrets)

    def test_ip_allowlist_and_rate_limit_parsed_from_yaml(self):
        raw = self._base_raw()
        raw["server"]["ip_allowlist"] = ["1.2.3.4", "5.6.7.8"]
        raw["server"]["rate_limit_per_minute"] = 30
        config = parse_config(raw, base_dir=".")
        self.assertEqual(config.server.ip_allowlist, ("1.2.3.4", "5.6.7.8"))
        self.assertEqual(config.server.rate_limit_per_minute, 30)

    def test_env_var_and_secret_works_together(self):
        os.environ["MCB_TOKEN"] = "token-from-env"
        os.environ["MCB_SECRET_FOO"] = "bar"
        config = parse_config(self._base_raw(), base_dir=".")
        self.assertEqual(config.server.token, "token-from-env")
        self.assertEqual(config.secrets["FOO"], "bar")
        self.assertEqual(config.secrets["EXISTING"], "yaml-secret")


if __name__ == "__main__":
    unittest.main()
