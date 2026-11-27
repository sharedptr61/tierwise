"""Hidden acceptance tests for notify-config. Not shown to the agent."""
import dataclasses
import os
import pathlib
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.getcwd())

from notify.config import Config  # noqa: E402
from notify.formatter import format_message  # noqa: E402
from notify.sender import DeliveryError, send  # noqa: E402


class ConfigTest(unittest.TestCase):
    def test_defaults_and_frozen(self):
        c = Config()
        self.assertEqual((c.prefix, c.max_len, c.retries, c.dry_run), ("[notify]", 140, 3, False))
        self.assertTrue(dataclasses.is_dataclass(c))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            c.prefix = "x"

    def test_from_env(self):
        c = Config.from_env({"NOTIFY_PREFIX": "[p]", "NOTIFY_MAX_LEN": "20", "NOTIFY_RETRIES": "5", "NOTIFY_DRY_RUN": "Yes"})
        self.assertEqual((c.prefix, c.max_len, c.retries, c.dry_run), ("[p]", 20, 5, True))
        self.assertEqual(Config.from_env({}), Config())
        for value, expected in (("1", True), ("TRUE", True), ("no", False), ("", False), ("0", False)):
            self.assertEqual(Config.from_env({"NOTIFY_DRY_RUN": value}).dry_run, expected, value)

    def test_does_not_read_os_environ_directly(self):
        os.environ["NOTIFY_PREFIX"] = "[env]"
        try:
            self.assertEqual(Config.from_env({}).prefix, "[notify]")
        finally:
            del os.environ["NOTIFY_PREFIX"]


class BehaviourTest(unittest.TestCase):
    def test_format_unchanged(self):
        c = Config(prefix="[x]", max_len=10)
        self.assertEqual(format_message("hello", c), "[x] hello")
        self.assertEqual(format_message("  hello  ", c), "[x] hello")
        self.assertEqual(format_message("hello world", c), "[x] hello…")
        self.assertEqual(len(format_message("a" * 500, Config())), 140)

    def test_send_unchanged(self):
        calls = []
        self.assertEqual(send("m", lambda m: calls.append(m) or len(calls) == 2, Config(retries=3)), 2)
        with self.assertRaises(DeliveryError) as e:
            send("m", lambda m: False, Config(retries=4))
        self.assertIn("4 attempts", str(e.exception))
        self.assertEqual(send("m", lambda m: self.fail("sent"), Config(dry_run=True)), 0)

    def run_cli(self, env, *args):
        full = {k: v for k, v in os.environ.items() if not k.startswith("NOTIFY_")}
        full.update(env)
        return subprocess.run([sys.executable, "-m", "notify", *args], capture_output=True, text=True, env=full)

    def test_cli_unchanged(self):
        p = self.run_cli({}, "hello", "there")
        self.assertEqual((p.returncode, p.stdout), (0, "[notify] hello there\n"))
        p = self.run_cli({"NOTIFY_DRY_RUN": "true", "NOTIFY_PREFIX": "[t]"}, "hi")
        self.assertEqual((p.returncode, p.stdout), (0, "[t] hi (dry run)\n"))
        p = self.run_cli({})
        self.assertEqual(p.returncode, 2)
        self.assertIn("usage", p.stderr)


class NoGlobalState(unittest.TestCase):
    def test_settings_module_removed(self):
        self.assertFalse(pathlib.Path("notify/settings.py").exists())
        with self.assertRaises(ImportError):
            __import__("notify.settings")

    def test_no_settings_global_left(self):
        for f in pathlib.Path("notify").glob("*.py"):
            self.assertIsNone(re.search(r"\bSETTINGS\b", f.read_text()), f"SETTINGS still in {f}")


if __name__ == "__main__":
    unittest.main()
