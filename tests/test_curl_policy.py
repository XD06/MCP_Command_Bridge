import tempfile
import unittest
from pathlib import Path

from mcp_command_bridge.config import BridgeConfig, ExecutionConfig, ProgramConfig, ServerConfig
from mcp_command_bridge.policy import validate_request


class CurlPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.config = BridgeConfig(
            server=ServerConfig(token="abc"),
            execution=ExecutionConfig(default_cwd=root, allowed_roots=(root,)),
            programs={
                "curl": ProgramConfig(
                    enabled=True,
                    executable="curl",
                    allowed_methods=("GET", "HEAD"),
                    denied_methods=("DELETE",),
                    allowed_url_prefixes=("https://www.baidu.com/",),
                    denied_schemes=("file", "ftp"),
                    denied_args=("-o",),
                )
            },
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_allows_exact_host_without_trailing_slash_when_prefix_has_slash(self):
        validate_request(self.config, "curl", ["https://www.baidu.com"], None, None)

    def test_treats_curl_head_flag_as_head_method(self):
        validate_request(self.config, "curl", ["-I", "https://www.baidu.com"], None, None)


if __name__ == "__main__":
    unittest.main()
