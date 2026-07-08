import json
import sys
import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.bridge import CommandBridge
from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ProgramConfig, ServerConfig


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.script = self.root / "hello.py"
        self.script.write_text("print('hello token-secret')\n", encoding="utf-8")
        self.audit = self.root / "audit.jsonl"
        self.config = BridgeConfig(
            server=ServerConfig(token="token", expose_advanced_tools=True),
            execution=ExecutionConfig(
                default_cwd=self.root,
                allowed_roots=(self.root,),
                timeout_seconds=10,
                max_output_bytes=100,
                audit_log=self.audit,
            ),
            secrets={"TEST_TOKEN": "token-secret"},
            programs={
                "python3": ProgramConfig(
                    enabled=True,
                    executable=sys.executable,
                    denied_args=("-c", "-m"),
                    allowed_script_roots=(self.root,),
                    timeout_seconds=10,
                ),
                "npm": ProgramConfig(
                    enabled=True,
                    executable="npm",
                    denied_args=("install",),
                    allowed_subcommands=("test", "run"),
                ),
                "curl": ProgramConfig(
                    enabled=True,
                    executable="curl",
                    allowed_methods=("GET", "POST"),
                    denied_methods=("DELETE",),
                    allowed_url_prefixes=("http://127.0.0.1:6806/",),
                    denied_schemes=("file", "ftp"),
                    denied_args=("-o", "--output"),
                ),
            },
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_policy_does_not_include_secret_values(self):
        policy = CommandBridge(self.config).get_policy()
        self.assertNotIn("token-secret", json.dumps(policy))

    def test_runs_allowed_script_and_masks_secret_in_output(self):
        result = CommandBridge(self.config).run_program("python3", [str(self.script)])
        self.assertTrue(result["ok"], result)
        self.assertIn("hello [REDACTED]", result["stdout"])
        self.assertNotIn("token-secret", json.dumps(result))

    def test_rejects_program_not_in_allowlist(self):
        result = CommandBridge(self.config).run_program("cmd", ["/c", "echo hi"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "policy_denied")

    def test_rejects_cwd_outside_allowed_roots(self):
        outside = Path(tempfile.gettempdir()).resolve()
        result = CommandBridge(self.config).run_program("python3", [str(self.script)], cwd=str(outside))
        if outside == self.root:
            self.skipTest("temp root unexpectedly equals allowed root")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "policy_denied")

    def test_rejects_python_eval_flag(self):
        result = CommandBridge(self.config).run_program("python3", ["-c", "print('x')"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["denied_arg"], "-c")

    def test_rejects_npm_install(self):
        result = CommandBridge(self.config).run_program("npm", ["install"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["denied_arg"], "install")

    def test_rejects_curl_delete_method(self):
        result = CommandBridge(self.config).run_program(
            "curl", ["-X", "DELETE", "http://127.0.0.1:6806/api/filetree/removeDoc"]
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["method"], "DELETE")

    def test_rejects_curl_unlisted_url_prefix(self):
        result = CommandBridge(self.config).run_program("curl", ["http://127.0.0.1:9999/"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "policy_denied")
        self.assertIn("hint", result)

    def test_writes_audit_log_for_denied_call(self):
        bridge = CommandBridge(self.config)
        bridge.run_program("python3", ["-c", "print('token-secret')"])
        text = self.audit.read_text(encoding="utf-8")
        self.assertIn("policy_denied", text)
        self.assertNotIn("token-secret", text)

    def test_run_program_is_rejected_when_advanced_tools_are_hidden(self):
        config = BridgeConfig(
            server=ServerConfig(token="token", expose_advanced_tools=False),
            execution=self.config.execution,
            programs=self.config.programs,
        )
        result = CommandBridge(config).run_program("python3", [str(self.script)])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "advanced_tool_hidden")


if __name__ == "__main__":
    unittest.main()
