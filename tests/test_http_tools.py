import http.server
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from mcp_command_bridge.bridge import CommandBridge
from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ProgramConfig, ServerConfig
from mcp_command_bridge.http_tools import _encode_url


# Track request headers for UA verification
_received_headers: dict[str, str] = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        _received_headers.clear()
        _received_headers.update({k.lower(): v for k, v in self.headers.items()})
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        _received_headers.clear()
        _received_headers.update({k.lower(): v for k, v in self.headers.items()})
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

    # ---- Tests for non-ASCII URL encoding ----

    def test_encode_url_ascii_passthrough(self):
        """Pure ASCII URLs should pass through unchanged."""
        url = "https://example.com/path?query=hello&lang=en"
        self.assertEqual(_encode_url(url), url)

    def test_encode_url_chinese_path(self):
        """Chinese characters in the path should be percent-encoded."""
        url = "https://example.com/精神与爱欲"
        encoded = _encode_url(url)
        self.assertNotEqual(url, encoded)
        self.assertIn("%E7%B2%BE%E7%A5%9E", encoded)  # 精 and 神
        self.assertIn("%E7%88%B1%E6%AC%B2", encoded)  # 爱 and 欲
        # Scheme and host should remain intact
        self.assertTrue(encoded.startswith("https://example.com/"))

    def test_encode_url_chinese_query(self):
        """Chinese characters in query parameters should be encoded."""
        url = "https://example.com/search?q=精神&lang=zh"
        encoded = _encode_url(url)
        self.assertNotEqual(url, encoded)
        self.assertIn("%E7%B2%BE%E7%A5%9E", encoded)
        # Query structure (=?&) should be preserved
        self.assertIn("q=", encoded)
        self.assertIn("lang=zh", encoded)

    def test_encode_url_mixed(self):
        """Mixed ASCII and non-ASCII in URL should only encode non-ASCII."""
        url = "https://example.com/api/v2/搜索?q=test&page=1"
        encoded = _encode_url(url)
        self.assertNotEqual(url, encoded)
        self.assertIn("api/v2/", encoded)
        self.assertIn("q=test", encoded)
        self.assertIn("page=1", encoded)
        # 搜索 should be encoded
        self.assertNotIn("搜索", encoded)

    def test_encode_url_already_encoded(self):
        """Already percent-encoded URLs (pure ASCII) should not be double-encoded."""
        url = "https://example.com/%E7%B2%BE%E7%A5%9E"
        self.assertEqual(_encode_url(url), url)

    def test_encode_url_emoji(self):
        """Emoji characters should be encoded."""
        url = "https://example.com/😀"
        encoded = _encode_url(url)
        self.assertNotEqual(url, encoded)
        self.assertNotIn("😀", encoded)
        self.assertIn("%", encoded)

    # ---- Tests for HTTP tools with non-ASCII URLs ----

    def test_http_probe_chinese_url_no_crash(self):
        """http_probe should not crash on a Chinese URL, even if the encoded URL
        is outside the allowed prefixes (should get policy_denied, not UnicodeEncodeError)."""
        url = f"{self.base_url}精神"
        result = self.bridge.http_probe(url)
        # The encoded URL should still match the allowed prefix, so it should succeed
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], 204)
        # encoded_url should be present and differ from original
        self.assertIsNotNone(result.get("encoded_url"))
        self.assertNotEqual(result["encoded_url"], url)

    def test_fetch_url_chinese_url_no_crash(self):
        """fetch_url should not crash on a Chinese URL."""
        url = f"{self.base_url}搜索?q=测试"
        result = self.bridge.fetch_url(url)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], 200)
        self.assertIsNotNone(result.get("encoded_url"))
        self.assertNotEqual(result["encoded_url"], url)

    # ---- Tests for User-Agent header ----

    def test_http_probe_sends_browser_ua(self):
        """http_probe should send a browser-like User-Agent."""
        result = self.bridge.http_probe(self.base_url)
        self.assertTrue(result["ok"], result)
        ua = _received_headers.get("user-agent", "")
        self.assertIn("Mozilla", ua)
        self.assertNotIn("Python-urllib", ua)

    def test_fetch_url_sends_browser_ua(self):
        """fetch_url should send a browser-like User-Agent."""
        result = self.bridge.fetch_url(self.base_url)
        self.assertTrue(result["ok"], result)
        ua = _received_headers.get("user-agent", "")
        self.assertIn("Mozilla", ua)
        self.assertNotIn("Python-urllib", ua)


if __name__ == "__main__":
    unittest.main()
