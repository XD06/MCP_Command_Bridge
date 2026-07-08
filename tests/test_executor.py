import sys
import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ServerConfig
from mcp_command_bridge.executor import run_process


class ExecutorTests(unittest.TestCase):
    def test_truncates_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = BridgeConfig(
                server=ServerConfig(token="abc"),
                execution=ExecutionConfig(
                    default_cwd=root,
                    allowed_roots=(root,),
                    max_output_bytes=5,
                    audit_log=root / "audit.jsonl",
                ),
            )
            result = run_process(
                sys.executable,
                ["-c", "print('abcdefghij')"],
                root,
                5,
                config,
            )
            self.assertTrue(result["truncated"])
            self.assertLessEqual(len(result["stdout"].encode("utf-8")), 5)


if __name__ == "__main__":
    unittest.main()
