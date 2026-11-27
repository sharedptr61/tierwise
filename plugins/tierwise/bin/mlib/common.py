"""Shared helpers for tierwise's scripts: config, state, ledger, git, hook I/O.

Standard library only: the scripts run as Claude Code command hooks.
"""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES = os.path.join(PLUGIN_ROOT, "templates")
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
TIERS = ["R0", "R1", "R2", "R3"]


# ---------------------------------------------------------------- ordering

def max_effort(*levels):
    """Highest of the given effort levels; None entries are ignored."""
    known = [lvl for lvl in levels if lvl in EFFORTS]
    return max(known, key=EFFORTS.index) if known else None


def max_tier(*tiers):
    known = [t for t in tiers if t in TIERS]
    return max(known, key=TIERS.index) if known else None


def tier_at_least(tier, floor):
    return TIERS.index(tier or "R0") >= TIERS.index(floor)


# ---------------------------------------------------------------- processes

def run(argv, cwd=None, timeout=60, stdin=None):
    """Run argv; return (exit code, stdout, stderr). Never raises for a failed command."""
    try:
        p = subprocess.run(argv, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError as e:
        return 127, "", str(e)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return 124, out, f"timed out after {timeout}s"


def git(root, *args, timeout=30):
    return run(["git", "-C", root, *args], timeout=timeout)


def git_root(cwd):
    code, out, _ = run(["git", "-C", cwd or ".", "rev-parse", "--show-toplevel"], timeout=10)
    return out.strip() if code == 0 and out.strip() else None


def main_root(cwd):
    """The main working tree of the repository that holds cwd.

    In a linked worktree (a builder's, or the session's own) this is the main checkout, where tierwise keeps
    .tierwise/; elsewhere it is the same as git_root.
    """
    root = git_root(cwd)
    if not root:
        return None
    code, out, _ = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    common = out.strip()
    if code == 0 and common and os.path.basename(common) == ".git":
        main = os.path.dirname(common)
        if os.path.isdir(main):
            return main
    return root


def snapshot(root):
    """A base for "what changed in this task": a commit of the working tree, plus untracked files.

    `git stash create` records the current tree without touching it; a clean tree gives HEAD.
    """
    code, out, _ = git(root, "stash", "create")
    base = out.strip()
    if code != 0 or not base:
        code, out, _ = git(root, "rev-parse", "--verify", "HEAD")
        base = out.strip() if code == 0 else None
    return base, untracked(root)


def untracked(root):
    code, out, _ = git(root, "ls-files", "--others", "--exclude-standard")
    return sorted(line for line in out.splitlines() if line and not line.startswith(".tierwise/")) if code == 0 else []


def changed_files(root, base, untracked_at_start=()):
    """Files that differ from the task base, plus files untracked since the task started."""
    files = set()
    if base:
        code, out, _ = git(root, "diff", "--name-only", base)
        if code == 0:
            files.update(out.split("\n"))
    else:  # repository without commits: every tracked or untracked file counts
        code, out, _ = git(root, "ls-files")
        files.update(out.split("\n"))
    files.update(set(untracked(root)) - set(untracked_at_start))
    return sorted(f for f in files if f and not _ignored(f))


# tierwise's own files, and build debris a repository without a .gitignore would otherwise count as changes.
_IGNORED = re.compile(r"^\.tierwise/|^\.claude/(?:tierwise\.json|settings\.local\.json)$|(?:^|/)__pycache__/|\.py[co]$|"
                      r"(?:^|/)node_modules/|(?:^|/)\.DS_Store$")


def _ignored(path):
    return bool(_IGNORED.search(path))


# ---------------------------------------------------------------- globs

_glob_cache = {}


def glob_regex(pattern):
    """Translate a path glob with ** into a regex. `**/` also matches nothing."""
    if pattern in _glob_cache:
        return _glob_cache[pattern]
    i, out = 0, ""
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    rx = re.compile(f"^{out}$", re.IGNORECASE)
    _glob_cache[pattern] = rx
    return rx


def glob_match(path, pattern):
    return bool(glob_regex(pattern).match(path[2:] if path.startswith("./") else path))


def path_tier(path, cfg):
    """R3/R2 when a pattern matches, R0 for docs and tests, otherwise R1."""
    risk = cfg.get("risk", {})
    for tier in ("R3", "R2", "R0"):
        if any(glob_match(path, p) for p in risk.get(tier, [])):
            return tier
    return "R1"


def paths_tier(paths, cfg):
    return max_tier(*(path_tier(p, cfg) for p in paths)) if paths else None


# ---------------------------------------------------------------- config

def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def default_config():
    with open(os.path.join(TEMPLATES, "tierwise.json")) as f:
        return json.load(f)


def config_path(root):
    return os.path.join(root, ".claude", "tierwise.json")


def load_config(root):
    cfg = default_config()
    path = config_path(root) if root else None
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                cfg = deep_merge(cfg, json.load(f))
        except (OSError, ValueError) as e:
            cfg["_error"] = f"{path}: {e}"
    return cfg


# ---------------------------------------------------------------- state and ledger

def mdir(root, *parts):
    return os.path.join(root, ".tierwise", *parts)


def ensure_layout(root):
    """Create .tierwise/ and keep it out of git through .git/info/exclude (never a tracked file)."""
    for sub in ("plans", "briefs", "reports", "specs", "backups"):
        os.makedirs(mdir(root, sub), exist_ok=True)
    for name, head in (("ledger.md", "# tierwise ledger\n\nAppend-only. One to three lines per event.\n\n"),
                       ("decisions.md", "# Decisions\n\nDecision · reason · options rejected · who decided.\n\n")):
        if not os.path.exists(mdir(root, name)):
            with open(mdir(root, name), "w") as f:
                f.write(head)
    code, out, _ = git(root, "rev-parse", "--git-path", "info/exclude")
    if code == 0 and out.strip():
        exclude = out.strip() if os.path.isabs(out.strip()) else os.path.join(root, out.strip())
        try:
            text = ""
            if os.path.exists(exclude):
                with open(exclude) as f:
                    text = f.read()
            if ".tierwise/" not in text.split("\n"):
                os.makedirs(os.path.dirname(exclude), exist_ok=True)
                with open(exclude, "a") as f:
                    f.write(("" if text.endswith("\n") or not text else "\n") + ".tierwise/\n")
        except OSError:
            pass


def load_state(root):
    try:
        with open(mdir(root, "state.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


@contextlib.contextmanager
def locked_state(root):
    """Read-modify-write state.json under an exclusive lock; written atomically."""
    os.makedirs(mdir(root), exist_ok=True)
    with open(mdir(root, ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state(root)
        yield state
        tmp = mdir(root, f".state.{os.getpid()}.tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)
        os.replace(tmp, mdir(root, "state.json"))


def task_active(state):
    return bool(state.get("task")) and state["task"].get("phase") not in ("closed", None)


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def ledger(root, text):
    if not root or not os.path.isdir(mdir(root)):
        return
    with open(mdir(root, "ledger.md"), "a") as f:
        f.write(f"- {now_iso()} {text}\n")


def week_key(ts=None):
    y, w, _ = datetime.date.fromtimestamp(ts or time.time()).isocalendar()
    return f"{y}-W{w:02d}"


def prompt_hash(text):
    return hashlib.sha256((text or "").strip().encode()).hexdigest()[:16]


# ---------------------------------------------------------------- hook I/O

def hook_input():
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def short(name):
    """`tierwise:builder` -> `builder`; other plugins' agents keep their full name."""
    return name.split(":", 1)[1] if name and name.startswith("tierwise:") else name
