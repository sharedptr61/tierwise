"""Test fixtures: a throwaway git repository and access to the plugin's scripts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(PLUGIN, "bin")
sys.path.insert(0, BIN)

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


class RepoTest(unittest.TestCase):
    """Each test gets a fresh git repo with one commit, and a private Claude config dir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tierwise-test-")
        self.root = os.path.realpath(os.path.join(self.tmp, "repo"))
        os.makedirs(self.root)
        self.old_env = dict(os.environ)
        os.environ.update(GIT_ENV)
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.tmp, "claude-config")
        self.git("init", "-q", "-b", "main")
        self.write("app/core.py", "def add(a, b):\n    return a + b\n")
        self.write("README.md", "# demo\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", "-C", self.root, *args], check=True, capture_output=True, text=True).stdout

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def config(self, cfg):
        self.write(".claude/tierwise.json", json.dumps(cfg))

    def script(self, name, *args, stdin=None, cwd=None):
        p = subprocess.run([sys.executable, os.path.join(BIN, name), *args], cwd=cwd or self.root,
                           input=stdin, capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout, p.stderr
