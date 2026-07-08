import sys
import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.bridge import CommandBridge
from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ProgramConfig, ServerConfig


class FileOpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.audit = self.root / "audit.jsonl"
        self.config = BridgeConfig(
            server=ServerConfig(token="abc", expose_advanced_tools=True),
            execution=ExecutionConfig(
                default_cwd=self.root,
                allowed_roots=(self.root,),
                writable_roots=(self.workspace,),
                audit_log=self.audit,
            ),
            programs={
                "python3": ProgramConfig(
                    enabled=True,
                    executable=sys.executable,
                    denied_args=("-c", "-m"),
                    allowed_script_roots=(self.workspace,),
                    timeout_seconds=10,
                )
            },
        )
        self.bridge = CommandBridge(self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_reads_and_appends_inside_workspace(self):
        write = self.bridge.write_file("note.txt", "hello", overwrite=False)
        self.assertTrue(write["ok"], write)
        append = self.bridge.append_file("note.txt", "\nworld")
        self.assertTrue(append["ok"], append)
        read = self.bridge.read_file("note.txt")
        self.assertEqual(read["content"], "hello\nworld")

    def test_refuses_to_overwrite_without_flag(self):
        self.bridge.write_file("note.txt", "hello")
        result = self.bridge.write_file("note.txt", "replace")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "policy_denied")

    def test_refuses_path_traversal(self):
        result = self.bridge.write_file("../outside.txt", "no")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "policy_denied")

    def test_can_write_script_then_run_it(self):
        script = self.bridge.write_file("probe.py", "print('workspace-ok')\n")
        self.assertTrue(script["ok"], script)
        result = self.bridge.run_program("python3", [str(self.workspace / "probe.py")])
        self.assertTrue(result["ok"], result)
        self.assertIn("workspace-ok", result["stdout"])

    def test_run_program_finds_relative_script_in_workspace(self):
        self.bridge.write_file("relative_probe.py", "print('relative-ok')\n")
        result = self.bridge.run_program("python3", ["relative_probe.py"])
        self.assertTrue(result["ok"], result)
        self.assertIn("relative-ok", result["stdout"])

    def test_can_run_workspace_script_by_relative_path(self):
        self.bridge.write_file("probe.py", "print('workspace-script-ok')\n")
        result = self.bridge.run_workspace_script("python3", "probe.py")
        self.assertTrue(result["ok"], result)
        self.assertIn("workspace-script-ok", result["stdout"])

    def test_run_workspace_script_rejects_bad_runtime(self):
        result = self.bridge.run_workspace_script("powershell", "probe.ps1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "policy_denied")

    def test_lists_workspace_files(self):
        self.bridge.write_file("a.txt", "a")
        result = self.bridge.list_files(".")
        self.assertTrue(result["ok"], result)
        self.assertIn("a.txt", [entry["name"] for entry in result["entries"]])

    def test_lists_workspace_files_recursively(self):
        self.bridge.make_directory("nested")
        self.bridge.write_file("nested/a.txt", "a")
        result = self.bridge.list_files(".", recursive=True)
        self.assertTrue(result["ok"], result)
        self.assertIn("nested\\a.txt", [entry["relative_path"] for entry in result["entries"]])

    def test_accepts_workspace_directory_name_as_root_alias(self):
        self.bridge.write_file("a.txt", "a")
        result = self.bridge.list_files("workspace")
        self.assertTrue(result["ok"], result)
        self.assertIn("a.txt", [entry["name"] for entry in result["entries"]])


if __name__ == "__main__":
    unittest.main()
