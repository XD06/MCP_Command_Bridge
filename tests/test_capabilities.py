import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.bridge import CommandBridge
from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ProgramConfig, ServerConfig


class CapabilityTests(unittest.TestCase):
    def test_policy_is_summary_and_details_are_on_demand(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            config = BridgeConfig(
                server=ServerConfig(token="abc"),
                execution=ExecutionConfig(
                    default_cwd=root,
                    allowed_roots=(root,),
                    writable_roots=(root,),
                ),
                programs={
                    "curl": ProgramConfig(
                        enabled=True,
                        executable="curl",
                        allowed_methods=("GET", "HEAD"),
                        allowed_url_prefixes=("https://www.baidu.com/",),
                    )
                },
            )
            bridge = CommandBridge(config)
            summary = bridge.get_policy()
            self.assertIn("capabilities", summary)
            self.assertIn("detail_names", summary)
            self.assertNotIn("programs", summary)

            details = bridge.get_capability_details("http")
            self.assertEqual(details["name"], "http")
            self.assertIn("https://www.baidu.com/", details["allowed_url_prefixes"])

            unknown = bridge.get_capability_details("missing")
            self.assertFalse(unknown["ok"])

    def test_preflight_requires_capability_details_before_task_tool(self):
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
            blocked = bridge.write_file("note.txt", "hello")
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["error"], "preflight_required")
            self.assertEqual(blocked["required_call"]["arguments"]["name"], "workspace")

            bridge.get_capability_details("workspace")
            allowed = bridge.write_file("note.txt", "hello")
            self.assertTrue(allowed["ok"], allowed)


if __name__ == "__main__":
    unittest.main()
