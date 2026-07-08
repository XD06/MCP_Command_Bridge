import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.bridge import CommandBridge
from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ServerConfig


class SystemToolTests(unittest.TestCase):
    def test_system_snapshot_is_read_only_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config = BridgeConfig(
                server=ServerConfig(token="abc"),
                execution=ExecutionConfig(
                    default_cwd=root,
                    allowed_roots=(root,),
                    writable_roots=(root,),
                    audit_log=root / "audit.jsonl",
                ),
            )
            result = CommandBridge(config).system_snapshot()
            self.assertTrue(result["ok"], result)
            self.assertIn("platform", result)
            self.assertIn("workspace_roots", result)
            self.assertNotIn("env", result)

    def test_system_snapshot_requires_preflight_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config = BridgeConfig(
                server=ServerConfig(token="abc", require_capability_preflight=True),
                execution=ExecutionConfig(
                    default_cwd=root,
                    allowed_roots=(root,),
                    writable_roots=(root,),
                    audit_log=root / "audit.jsonl",
                ),
            )
            bridge = CommandBridge(config)
            blocked = bridge.system_snapshot()
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["error"], "preflight_required")
            bridge.get_capability_details("system")
            allowed = bridge.system_snapshot()
            self.assertTrue(allowed["ok"], allowed)


if __name__ == "__main__":
    unittest.main()
