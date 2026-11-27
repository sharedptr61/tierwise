import unittest

from notify import formatter, sender
from notify.settings import SETTINGS


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.saved = dict(SETTINGS)

    def tearDown(self):
        SETTINGS.clear()
        SETTINGS.update(self.saved)

    def test_prefix_and_cut(self):
        SETTINGS.update(prefix="[x]", max_len=10)
        self.assertEqual(formatter.format_message("hello"), "[x] hello")
        self.assertEqual(formatter.format_message("hello world"), "[x] hello…")

    def test_retries(self):
        calls = []
        SETTINGS.update(retries=3, dry_run=False)
        self.assertEqual(sender.send("m", lambda m: calls.append(m) or len(calls) == 2), 2)
        with self.assertRaises(sender.DeliveryError):
            sender.send("m", lambda m: False)

    def test_dry_run_sends_nothing(self):
        SETTINGS.update(dry_run=True)
        self.assertEqual(sender.send("m", lambda m: self.fail("sent")), 0)
