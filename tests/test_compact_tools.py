import socket
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from mcp_command_bridge.bridge import CommandBridge
from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ProgramConfig, ServerConfig


class CompactToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir()
        self.config = BridgeConfig(
            server=ServerConfig(token="abc"),
            execution=ExecutionConfig(
                default_cwd=self.root,
                allowed_roots=(self.root,),
                writable_roots=(self.workspace_root,),
                audit_log=self.root / "audit.jsonl",
            ),
            programs={
                "curl": ProgramConfig(
                    enabled=True,
                    executable="curl",
                    allowed_methods=("GET", "HEAD"),
                    allowed_url_prefixes=("http://127.0.0.1:",),
                    denied_schemes=("file", "ftp"),
                )
            },
        )
        self.bridge = CommandBridge(self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def test_workspace_compact_write_and_read(self):
        write = self.bridge.workspace("write", "a.txt", "hello")
        self.assertTrue(write["ok"], write)
        read = self.bridge.workspace("read", "a.txt")
        self.assertEqual(read["content"], "hello")

    def test_network_compact_tcp_probe(self):
        server = socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = self.bridge.network_check("tcp", "127.0.0.1", port=server.server_address[1])
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["open"], result)
        finally:
            server.shutdown()
            server.server_close()

    def test_network_compact_requires_port_for_tcp(self):
        result = self.bridge.network_check("tcp", "127.0.0.1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "missing_port")

    def test_http_compact_rejects_invalid_mode(self):
        result = self.bridge.http_request("bad", "http://127.0.0.1/")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_mode")


if __name__ == "__main__":
    unittest.main()
