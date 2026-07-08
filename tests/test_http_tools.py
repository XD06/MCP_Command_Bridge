import http.server
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from mcp_command_bridge.bridge import CommandBridge
from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ProgramConfig, ServerConfig


class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        body = b"hello from test server"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class HttpToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        self.config = BridgeConfig(
            server=ServerConfig(token="abc"),
            execution=ExecutionConfig(
                default_cwd=self.root,
                allowed_roots=(self.root,),
                audit_log=self.root / "audit.jsonl",
            ),
            programs={
                "curl": ProgramConfig(
                    enabled=True,
                    executable="curl",
                    allowed_methods=("GET", "HEAD"),
                    denied_methods=("DELETE",),
                    allowed_url_prefixes=(self.base_url,),
                    denied_schemes=("file", "ftp"),
                    denied_args=("-o",),
                )
            },
        )
        self.bridge = CommandBridge(self.config)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_http_probe_returns_status(self):
        result = self.bridge.http_probe(self.base_url)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], 204)

    def test_fetch_url_returns_text(self):
        result = self.bridge.fetch_url(self.base_url)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], 200)
        self.assertIn("hello from test server", result["content"])

    def test_disallowed_url_returns_policy_hint(self):
        result = self.bridge.http_probe("https://example.com/")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "policy_denied")
        self.assertIn("hint", result)


if __name__ == "__main__":
    unittest.main()
