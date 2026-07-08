import time
import unittest

from mcp_command_bridge.rate_limit import RateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_disabled_limiter_allows_everything(self):
        rl = RateLimiter(0)
        self.assertTrue(rl.check("1.2.3.4"))
        self.assertTrue(rl.check("1.2.3.4"))
        self.assertEqual(rl.remaining("1.2.3.4"), -1)

    def test_allows_under_limit(self):
        rl = RateLimiter(5)
        for _ in range(5):
            self.assertTrue(rl.check("a"))
        self.assertEqual(rl.remaining("a"), 0)

    def test_blocks_over_limit(self):
        rl = RateLimiter(3)
        self.assertTrue(rl.check("a"))
        self.assertTrue(rl.check("a"))
        self.assertTrue(rl.check("a"))
        self.assertFalse(rl.check("a"))
        self.assertFalse(rl.check("a"))

    def test_different_keys_are_independent(self):
        rl = RateLimiter(2)
        self.assertTrue(rl.check("a"))
        self.assertTrue(rl.check("a"))
        self.assertFalse(rl.check("a"))
        self.assertTrue(rl.check("b"))
        self.assertTrue(rl.check("b"))
        self.assertFalse(rl.check("b"))

    def test_window_expiry_allows_after_60s(self):
        rl = RateLimiter(1)
        self.assertTrue(rl.check("x"))
        self.assertFalse(rl.check("x"))
        # Simulate passage of time by backdating the bucket
        with rl._lock:
            rl._buckets["x"] = [time.monotonic() - 61.0]
        self.assertTrue(rl.check("x"))
        self.assertEqual(rl.remaining("x"), 0)

    def test_remaining_counts_correctly(self):
        rl = RateLimiter(10)
        self.assertEqual(rl.remaining("k"), 10)
        rl.check("k")
        self.assertEqual(rl.remaining("k"), 9)
        rl.check("k")
        self.assertEqual(rl.remaining("k"), 8)

    def test_remaining_unlimited_when_disabled(self):
        rl = RateLimiter(0)
        self.assertEqual(rl.remaining("any"), -1)

    def test_unknown_key_has_full_remaining(self):
        rl = RateLimiter(5)
        self.assertEqual(rl.remaining("never_seen"), 5)

    def test_concurrent_access_does_not_crash(self):
        import threading
        rl = RateLimiter(100)
        results = []

        def worker():
            for _ in range(20):
                results.append(rl.check("shared"))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 100 requests allowed, rest blocked — all should be True or False, no crash
        self.assertEqual(len(results), 100)
        self.assertTrue(all(isinstance(r, bool) for r in results))


if __name__ == "__main__":
    unittest.main()
