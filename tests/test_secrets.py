import unittest

from mcp_command_bridge.secrets import mask_args, mask_text, replace_secret_placeholders


class SecretTests(unittest.TestCase):
    def test_replaces_known_placeholder(self):
        args = replace_secret_placeholders(["Token ${A}"], {"A": "secret"})
        self.assertEqual(args, ["Token secret"])

    def test_leaves_unknown_placeholder(self):
        args = replace_secret_placeholders(["Token ${MISSING}"], {"A": "secret"})
        self.assertEqual(args, ["Token ${MISSING}"])

    def test_masks_secret_values_and_placeholders(self):
        self.assertEqual(mask_text("Token secret ${A}", {"A": "secret"}), "Token [REDACTED] [REDACTED]")
        self.assertEqual(mask_args(["secret"], {"A": "secret"}), ["[REDACTED]"])


if __name__ == "__main__":
    unittest.main()
