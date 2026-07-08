import socket
import socketserver
import threading
import unittest
from unittest.mock import patch

from mcp_command_bridge.errors import PolicyError
from mcp_command_bridge.network_tools import (
    _build_ping_command,
    dns_lookup,
    ping_host,
    tcp_probe,
    trace_route,
)


class PingCommandBuilderTests(unittest.TestCase):
    @patch("mcp_command_bridge.network_tools.platform.system", return_value="Windows")
    def test_windows_ping_uses_n_and_w_flags(self, _mock):
        cmd = _build_ping_command("8.8.8.8", 4, 10)
        self.assertIn("-n", cmd)
        self.assertIn("-w", cmd)
        self.assertIn("10000", cmd)  # 10s * 1000 = 10000ms
        self.assertIn("8.8.8.8", cmd)
        self.assertNotIn("-c", cmd)
        self.assertNotIn("-W", cmd)

    @patch("mcp_command_bridge.network_tools.platform.system", return_value="Linux")
    def test_linux_ping_uses_c_and_W_flags(self, _mock):
        cmd = _build_ping_command("8.8.8.8", 4, 10)
        self.assertIn("-c", cmd)
        self.assertIn("-W", cmd)
        self.assertIn("4", cmd)  # count
        self.assertIn("10", cmd)  # timeout in seconds (not ms)
        self.assertIn("8.8.8.8", cmd)
        self.assertNotIn("-n", cmd)
        # -w should NOT be present (Windows-only flag)
        self.assertNotIn("-w", cmd)

    @patch("mcp_command_bridge.network_tools.platform.system", return_value="Linux")
    def test_linux_ping_timeout_is_seconds_not_milliseconds(self, _mock):
        cmd = _build_ping_command("example.com", 2, 5)
        # On Linux, -W takes seconds, so "5" not "5000"
        self.assertIn("5", cmd)
        self.assertNotIn("5000", cmd)

    @patch("mcp_command_bridge.network_tools.platform.system", return_value="Windows")
    def test_windows_ping_timeout_is_milliseconds(self, _mock):
        cmd = _build_ping_command("example.com", 2, 5)
        # On Windows, -w takes milliseconds, so "5000" not "5"
        self.assertIn("5000", cmd)

    @patch("mcp_command_bridge.network_tools.platform.system", return_value="Darwin")
    def test_macos_uses_linux_style_flags(self, _mock):
        # macOS (Darwin) is not Windows, so falls through to Linux branch
        cmd = _build_ping_command("8.8.8.8", 3, 7)
        self.assertIn("-c", cmd)
        self.assertIn("-W", cmd)
        self.assertNotIn("-n", cmd)

    def test_ping_command_first_element_is_ping(self):
        with patch("mcp_command_bridge.network_tools.platform.system", return_value="Linux"):
            cmd = _build_ping_command("1.1.1.1", 1, 1)
        self.assertEqual(cmd[0], "ping")

    def test_ping_command_last_element_is_host(self):
        with patch("mcp_command_bridge.network_tools.platform.system", return_value="Linux"):
            cmd = _build_ping_command("192.168.1.1", 1, 1)
        self.assertEqual(cmd[-1], "192.168.1.1")


class NetworkToolTests(unittest.TestCase):
    def test_dns_lookup_localhost(self):
        result = dns_lookup("localhost")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["addresses"])

    def test_tcp_probe_open_local_port(self):
        server = socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = tcp_probe("127.0.0.1", server.server_address[1])
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["open"], result)
        finally:
            server.shutdown()
            server.server_close()

    def test_tcp_probe_rejects_bad_port(self):
        with self.assertRaises(PolicyError):
            tcp_probe("127.0.0.1", 70000)

    def test_ping_rejects_shell_like_host(self):
        with self.assertRaises(PolicyError):
            ping_host("-n 1 127.0.0.1")

    def test_trace_route_rejects_shell_like_host(self):
        with self.assertRaises(PolicyError):
            trace_route("8.8.8.8 && whoami")


if __name__ == "__main__":
    unittest.main()
