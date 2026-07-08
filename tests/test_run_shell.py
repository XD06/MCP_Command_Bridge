"""Tests for run_shell tool — shell command execution, UTF-8 encoding, and persistence guidance."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.bridge import CommandBridge
from mcp_command_bridge.config import (
    BridgeConfig,
    ExecutionConfig,
    ProgramConfig,
    ServerConfig,
)


def _make_config(tmp, expose_advanced=True, allowed_roots=None, denied_args=None):
    root = Path(tmp).resolve()
    bash_denied = denied_args or ()
    return BridgeConfig(
        server=ServerConfig(token="token", expose_advanced_tools=expose_advanced),
        execution=ExecutionConfig(
            default_cwd=root,
            allowed_roots=allowed_roots or (root,),
            writable_roots=(root,),
            timeout_seconds=10,
            max_output_bytes=10_000,
            audit_log=root / "audit.jsonl",
        ),
        secrets={},
        programs={
            "bash": ProgramConfig(
                enabled=True,
                executable="bash" if sys.platform != "win32" else "cmd.exe",
                denied_args=bash_denied,
                timeout_seconds=10,
            ),
            "python3": ProgramConfig(
                enabled=True,
                executable=sys.executable,
                timeout_seconds=10,
            ),
        },
    )


class RunShellBasicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = _make_config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_shell_echo(self):
        """run_shell executes a simple echo command."""
        if sys.platform == "win32":
            self.skipTest("run_shell uses bash, not available on Windows test env")
        bridge = CommandBridge(self.config)
        result = bridge.run_shell("echo 'hello world'")
        self.assertTrue(result["ok"], result)
        self.assertIn("hello world", result["stdout"])

    def test_run_shell_with_pipe(self):
        """run_shell supports pipe syntax."""
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        result = bridge.run_shell("echo 'apple\nbanana\ncherry' | grep 'banana'")
        self.assertTrue(result["ok"], result)
        self.assertIn("banana", result["stdout"])

    def test_run_shell_with_redirect(self):
        """run_shell supports output redirection."""
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        root = Path(self.tmp.name).resolve()
        outfile = root / "redirect_test.txt"
        result = bridge.run_shell(f"echo 'redirected' > '{outfile}'")
        self.assertTrue(result["ok"], result)
        self.assertTrue(outfile.exists())
        self.assertIn("redirected", outfile.read_text(encoding="utf-8"))

    def test_run_shell_with_chaining(self):
        """run_shell supports && chaining."""
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        result = bridge.run_shell("echo 'first' && echo 'second'")
        self.assertTrue(result["ok"], result)
        self.assertIn("first", result["stdout"])
        self.assertIn("second", result["stdout"])

    def test_run_shell_with_env_var(self):
        """run_shell supports environment variable expansion."""
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        result = bridge.run_shell("echo $HOME")
        self.assertTrue(result["ok"], result)
        # $HOME should expand to something non-empty
        self.assertTrue(len(result["stdout"].strip()) > 0)


class RunShellEncodingTests(unittest.TestCase):
    """Verify that Chinese / non-ASCII text works without encoding errors."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = _make_config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_shell_chinese_echo(self):
        """run_shell handles Chinese text in stdout."""
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        result = bridge.run_shell("echo '你好世界'")
        self.assertTrue(result["ok"], result)
        self.assertIn("你好世界", result["stdout"])

    def test_run_shell_chinese_redirect(self):
        """run_shell handles Chinese text in file output."""
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        root = Path(self.tmp.name).resolve()
        outfile = root / "chinese_test.txt"
        result = bridge.run_shell(f"echo '你好世界' > '{outfile}'")
        self.assertTrue(result["ok"], result)
        content = outfile.read_text(encoding="utf-8")
        self.assertIn("你好世界", content)

    def test_run_shell_python_chinese(self):
        """run_shell handles Chinese text from Python inline code."""
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        result = bridge.run_shell(f"{sys.executable} -c \"print('你好，Python！')\"")
        self.assertTrue(result["ok"], result)
        self.assertIn("你好", result["stdout"])

    def test_run_shell_emoji(self):
        """run_shell handles emoji in stdout."""
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        result = bridge.run_shell("echo 'Hello 🌍 World 🚀'")
        self.assertTrue(result["ok"], result)
        self.assertIn("🌍", result["stdout"])


class RunShellHiddenTests(unittest.TestCase):
    """run_shell is hidden when expose_advanced_tools=False."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = _make_config(self.tmp.name, expose_advanced=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_shell_hidden_returns_error(self):
        bridge = CommandBridge(self.config)
        result = bridge.run_shell("echo hi")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "advanced_tool_hidden")

    def test_run_shell_hidden_writes_audit_log(self):
        bridge = CommandBridge(self.config)
        bridge.run_shell("echo hi")
        audit_path = Path(self.tmp.name) / "audit.jsonl"
        self.assertTrue(audit_path.exists())
        log_line = audit_path.read_text(encoding="utf-8").strip()
        entry = json.loads(log_line)
        self.assertEqual(entry["program"], "run_shell")
        self.assertFalse(entry["ok"])


class RunShellAuditTests(unittest.TestCase):
    """run_shell calls are audit-logged."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = _make_config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_audit_log_records_run_shell(self):
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        bridge.run_shell("echo 'test audit'")
        audit_path = Path(self.tmp.name) / "audit.jsonl"
        self.assertTrue(audit_path.exists())
        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
        entry = json.loads(lines[-1])
        self.assertEqual(entry["program"], "run_shell")
        self.assertIn("echo 'test audit'", entry["args"])
        self.assertTrue(entry["ok"])


class RunShellFullControlTests(unittest.TestCase):
    """In full-control mode (empty allowed_roots), run_shell works from any cwd."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Empty allowed_roots = unrestricted
        self.config = _make_config(
            self.tmp.name,
            allowed_roots=(),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_shell_unrestricted_cwd(self):
        if sys.platform == "win32":
            self.skipTest("bash not available on Windows test env")
        bridge = CommandBridge(self.config)
        # Should work from /tmp which is outside the workspace root
        result = bridge.run_shell("echo 'unrestricted'", cwd="/tmp")
        self.assertTrue(result["ok"], result)
        self.assertIn("unrestricted", result["stdout"])


if __name__ == "__main__":
    unittest.main()
