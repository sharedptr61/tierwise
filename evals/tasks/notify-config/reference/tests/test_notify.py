import unittest

from notify.config import Config
from notify.formatter import format_message
from notify.sender import DeliveryError, send


class NotifyTest(unittest.TestCase):
    def test_prefix_and_cut(self):
        c = Config(prefix="[x]", max_len=10)
        self.assertEqual(format_message("hello", c), "[x] hello")
        self.assertEqual(format_message("hello world", c), "[x] hello…")

    def test_retries(self):
        calls = []
        self.assertEqual(send("m", lambda m: calls.append(m) or len(calls) == 2, Config()), 2)
        with self.assertRaises(DeliveryError):
            send("m", lambda m: False, Config())

    def test_dry_run_sends_nothing(self):
        self.assertEqual(send("m", lambda m: self.fail("sent"), Config(dry_run=True)), 0)
