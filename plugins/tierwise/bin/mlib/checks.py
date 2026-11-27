"""Check catalogue: auto-detection, selection per change, running, digests, secret scan, red-green."""
import contextlib
import json
import math
import os
import re
import shutil
import tempfile
import time
import traceback

from .common import git, glob_match, load_config, mdir, run, tier_at_least

# ---------------------------------------------------------------- file kinds

KINDS = {
    "docs": ["**/*.md", "**/*.rst", "**/*.txt", "**/docs/**", "**/doc/**", "**/LICENSE*", "**/CHANGELOG*"],
    "test": ["**/tests/**", "**/test/**", "**/__tests__/**", "**/*_test.*", "**/*.test.*", "**/*.spec.*",
             "**/test_*.py"],
    "manifest": ["**/package.json", "**/package-lock.json", "**/yarn.lock", "**/pnpm-lock.yaml",
                 "**/requirements*.txt", "**/pyproject.toml", "**/poetry.lock", "**/uv.lock", "**/Pipfile*",
                 "**/go.mod", "**/go.sum", "**/Cargo.toml", "**/Cargo.lock", "**/Gemfile*", "**/pom.xml",
                 "**/build.gradle*"],
    "iac": ["**/*.tf", "**/*.tfvars", "**/terraform/**", "**/k8s/**", "**/kubernetes/**", "**/helm/**",
            "**/Dockerfile*", "**/docker-compose*.yml", "**/.github/workflows/**", "**/.gitlab-ci.yml"],
    "migration": ["**/migrations/**", "**/migrate/**", "**/*.sql"],
}


def file_kinds(files):
    kinds = set()
    for f in files:
        matched = {k for k, pats in KINDS.items() if any(glob_match(f, p) for p in pats)}
        kinds |= matched
        if not matched or matched == {"migration"}:
            kinds.add("code")
    if "test" in kinds:
        kinds.add("code-or-test")
    if "code" in kinds:
        kinds.add("code-or-test")
    return kinds


# ---------------------------------------------------------------- detection

def detect(root):
    """Best-effort commands for each check type in this repository. Unknown stays None."""
    has = lambda *p: os.path.exists(os.path.join(root, *p))  # noqa: E731
    which = shutil.which
    found = {}
    if has("package.json"):
        try:
            with open(os.path.join(root, "package.json")) as f:
                scripts = json.load(f).get("scripts", {})
        except (OSError, ValueError):
            scripts = {}
        runner = "pnpm" if has("pnpm-lock.yaml") else "yarn" if has("yarn.lock") else "npm"
        if "test" in scripts:
            found["unit"] = f"{runner} test --silent" if runner == "npm" else f"{runner} test"
        if "lint" in scripts:
            found["lint"] = f"{runner} run lint"
        if "typecheck" in scripts:
            found["typecheck"] = f"{runner} run typecheck"
        elif has("tsconfig.json"):
            found["typecheck"] = "npx --no-install tsc --noEmit"
        found["sca"] = f"{runner} audit --audit-level=high" if runner != "yarn" else "yarn npm audit"
    if has("pyproject.toml") or has("setup.py") or has("requirements.txt") or _any_py_tests(root):
        code, _, _ = run(["python3", "-c", "import pytest"], timeout=20)
        found.setdefault("unit", "python3 -m pytest -q -x" if code == 0 else "python3 -m unittest discover -q")
        if which("mypy"):
            found.setdefault("typecheck", "mypy .")
        if which("ruff"):
            found.setdefault("lint", "ruff check .")
        if which("pip-audit"):
            found.setdefault("sca", "pip-audit")
    if has("go.mod"):
        found.setdefault("unit", "go test ./...")
        found.setdefault("typecheck", "go vet ./...")
        found.setdefault("race", "go test -race ./...")
        if which("govulncheck"):
            found.setdefault("sca", "govulncheck ./...")
    if has("Cargo.toml"):
        found.setdefault("unit", "cargo test --quiet")
        found.setdefault("lint", "cargo clippy --quiet -- -D warnings")
        if which("cargo-audit"):
            found.setdefault("sca", "cargo audit")
    # Only a project's own rules: "--config auto" fetches rules from the Semgrep registry and sends metrics.
    local = next((c for c in (".semgrep.yml", ".semgrep.yaml", ".semgrep") if os.path.exists(os.path.join(root, c))), None)
    if which("semgrep") and local:
        found["sast"] = f"semgrep scan --metrics off --config {local} --error --quiet"
    if which("checkov"):
        found["iac"] = "checkov -d . --quiet --compact"
    elif which("hadolint") and has("Dockerfile"):
        found["iac"] = "hadolint Dockerfile"
    if which("markdownlint"):
        found["docs"] = "markdownlint '**/*.md'"
    return found


def _any_py_tests(root):
    for d in ("tests", "test"):
        p = os.path.join(root, d)
        if os.path.isdir(p) and any(n.endswith(".py") for n in os.listdir(p)):
            return True
    return False


TOOLS_TO_SUGGEST = {
    "sast": "semgrep (pipx install semgrep) with your own .semgrep.yml (tierwise never uses the online registry)",
    "sca": "pip-audit / npm audit / govulncheck / cargo-audit, by language",
    "iac": "checkov (pipx install checkov) or hadolint",
}


# ---------------------------------------------------------------- selection

BUILTIN_CMDS = {"syntax": "builtin:syntax", "secrets": "builtin:secrets"}
SECURITY_CHECKS = {"secrets", "sast", "sca", "iac"}  # always run, even after a failed syntax or affected check
FAIL_FAST_CHECKS = ("syntax", "affected")

def plan_checks(root, plan_path):
    """Check ids a plan lists on `Checks:` lines (one per unit)."""
    ids = set()
    if not plan_path:
        return ids
    path = plan_path if os.path.isabs(plan_path) else os.path.join(root, plan_path)
    try:
        with open(path) as f:
            lines = f.readlines()
        for line in lines:
            m = re.match(r"\s*[-*]?\s*\**checks\s*:\s*\**\s*(.+)", line, re.IGNORECASE)
            if m:
                ids.update(x.strip(" *`").lower() for x in re.split(r"[,;]", m.group(1)) if x.strip(" *`"))
    except OSError:
        pass
    return ids


def select(cfg, files, tier, cls=None, extra=()):
    """Checks this change needs: [{id, cmd, reason}]. cmd None means the tool is missing."""
    kinds = file_kinds(files)
    cmds = cfg.get("checks", {})
    want = {}

    def add(cid, reason):
        want.setdefault(cid, reason)

    if not files:
        return []
    if kinds & {"code-or-test", "manifest", "iac"} or any(_ext(f) in SYNTAX_EXTS for f in files):
        add("syntax", "code or config changed")
    add("secrets", "every change")
    if "code-or-test" in kinds:
        if cmds.get("affected"):
            add("affected", "code or tests changed: fast check of the affected tests")
        add("unit", "code or tests changed")
        for cid in ("typecheck", "lint"):
            if cmds.get(cid):
                add(cid, "code changed")
    elif "docs" in kinds:
        add("docs", "docs-only change")
    if "manifest" in kinds:
        add("sca", "manifest or lockfile changed")
    if "iac" in kinds:
        add("iac", "infrastructure, container or CI config changed")
    if "migration" in kinds:
        add("migration", "migration changed: up, down, rollback on a scratch database")
    if tier_at_least(tier, "R2") and "code" in kinds:
        add("sast", f"{tier} code change")
    if tier == "R3" and "code" in kinds and cmds.get("mutation"):
        add("mutation", "R3 core logic")
    if cmds.get("race") and cls in ("investigation", "high-risk") and "code" in kinds:
        add("race", "concurrency-sensitive task")
    for cid in extra:
        cid = cid.split()[0].strip("`*").lower()
        if cid in cmds or cid in ("unit", "integration", "sast", "sca", "iac", "race", "mutation", "docs"):
            add("unit" if cid == "integration" and not cmds.get("integration") else cid, "listed in the plan")
    out = []
    for cid, reason in want.items():
        cmd = BUILTIN_CMDS.get(cid) or cmds.get(cid)
        out.append({"id": cid, "cmd": cmd, "reason": reason})
    return out


# ---------------------------------------------------------------- secret scan

SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b")),
    ("assigned-secret", re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\b"
        r"\s*[:=]\s*['\"]([^'\"\s]{12,})['\"]")),
]
_PLACEHOLDER = re.compile(r"(?i)example|placeholder|changeme|dummy|fake|xxx+|\*{3,}|<[^>]+>|\$\{|\{\{|test|sample")
ASSIGNED_MIN_ENTROPY = 3.0  # bits per character of the assigned value


def entropy(text):
    """Shannon entropy of text in bits per character (0.0 for empty text)."""
    if not text:
        return 0.0
    n = len(text)
    return -sum(c / n * math.log2(c / n) for c in (text.count(ch) for ch in set(text)))


def _secret_rules(cfg):
    """Built-in rules plus the user's cfg["secrets"]["rules"]: ([(id, regex, minEntropy)], [config errors])."""
    rules = [(name, rx, None) for name, rx in SECRET_PATTERNS]
    errors = []
    user = (cfg or {}).get("secrets")
    for rule in (user.get("rules") or []) if isinstance(user, dict) else []:
        try:
            min_entropy = rule.get("minEntropy")
            if min_entropy is not None:
                min_entropy = float(min_entropy)
                if not math.isfinite(min_entropy) or min_entropy < 0:  # "nan" or "inf" would disable the rule
                    raise ValueError("minEntropy must be a finite number of bits per character, 0 or more")
            rules.append((str(rule["id"]), re.compile(rule["regex"]), min_entropy))
        except (KeyError, TypeError, ValueError, AttributeError, re.error) as e:
            errors.append(f"secrets config: bad rule {rule!r}: {e}")
    return rules, errors


def _secret_allow(cfg):
    """The user's cfg["secrets"]["allow"]: ([path globs], [compiled regexes], [config errors])."""
    user = (cfg or {}).get("secrets")
    allow = user.get("allow") if isinstance(user, dict) else None
    allow = allow if isinstance(allow, dict) else {}
    regexes, errors = [], []
    for pattern in allow.get("regexes") or []:
        try:
            regexes.append(re.compile(pattern))
        except (TypeError, re.error) as e:
            errors.append(f"secrets config: bad allow regex {pattern!r}: {e}")
    return list(allow.get("paths") or []), regexes, errors


def _is_secret(name, m, min_entropy):
    value = m.group(1) if m.re.groups else m.group(0)
    if name == "assigned-secret":
        return not _PLACEHOLDER.search(value) and entropy(value) >= ASSIGNED_MIN_ENTROPY
    return min_entropy is None or entropy(value) >= float(min_entropy)


def scan_secrets(root, base, files, cfg=None, allowed=None):
    """Scan added lines of the diff (and whole new files) for credentials. Returns findings.

    Every match on a line is judged, so a placeholder earlier on the line cannot hide a real value after it.
    A hit on an allowlisted path, or whose matched text an allow regex finds (cfg["secrets"]["allow"]), is not a
    finding; it is appended to `allowed` (when given) as an "allowed: ..." line. Allow regexes see only the matched
    text, never the rest of the line, so a comment cannot allowlist a real credential beside it.
    """
    rules, findings = _secret_rules(cfg)
    allow_paths, allow_regexes, errors = _secret_allow(cfg)
    findings += errors
    added = {}
    if base:
        code, out, _ = git(root, "diff", "-U0", "--no-color", base, "--", *files, timeout=60)
        current = None
        for line in out.splitlines():
            if line.startswith("+++ "):
                current = line[6:] if line.startswith("+++ b/") else None
            elif line.startswith("+") and current:
                added.setdefault(current, []).append(line[1:])
    for f in files:
        if f not in added:
            p = os.path.join(root, f)
            try:
                if os.path.isfile(p) and os.path.getsize(p) < MAX_FILE_BYTES:
                    with open(p, errors="replace") as fh:
                        added[f] = fh.read().splitlines()
            except OSError:
                pass
    for f, lines in added.items():
        path_ok = any(glob_match(f, g) for g in allow_paths)
        for i, line in enumerate(lines, 1):
            for name, rx, min_entropy in rules:
                hits = [m for m in rx.finditer(line) if _is_secret(name, m, min_entropy)]
                if not hits:
                    continue
                hit = f"{f}: {name} (added line {i})"
                if path_ok or all(any(r.search(m.group(0)) for r in allow_regexes) for m in hits):
                    if allowed is not None:
                        allowed.append(f"allowed: {hit}")
                else:
                    findings.append(hit)
    return findings


# ---------------------------------------------------------------- syntax check

MAX_FILE_BYTES = 2_000_000
SYNTAX_EXTS = {".py", ".json", ".toml", ".js", ".mjs", ".cjs"}
# JSON with comments is legal in these
_JSONC = re.compile(r"(?:^|/)(?:tsconfig|jsconfig)[^/]*\.json$|(?:^|/)\.vscode/|(?:^|/)\.?devcontainer[^/]*\.json$"
                    r"|(?:^|/)\.devcontainer/")
_JSX_ERROR = "Unexpected token '<'"  # node on a .js file written in JSX: valid for the project's bundler


def _ext(path):
    return os.path.splitext(path)[1].lower()


def _node_error(err):
    """(line, message) from the stderr of `node --check`."""
    lines = [ln for ln in err.splitlines() if ln.strip()]
    m = next((re.search(r":(\d+)$", ln) for ln in lines if re.search(r":(\d+)$", ln)), None)
    msg = next((ln for ln in lines if "Error" in ln), lines[-1] if lines else "syntax error")
    return int(m.group(1)) if m else 1, msg.strip()


def _syntax_exclude(cfg):
    """The user's cfg["syntax"]["exclude"]: a list of path globs the syntax check leaves alone."""
    user = (cfg or {}).get("syntax")
    exclude = user.get("exclude") if isinstance(user, dict) else None
    return [g for g in exclude if isinstance(g, str)] if isinstance(exclude, list) else []


def syntax_check(root, files, cfg=None):
    """Parse each changed .py/.json/.toml/.js/.mjs/.cjs file without running or writing anything.

    Returns (broken, checked): "path:line: message" per broken file, and how many files were parsed.
    TOML needs Python 3.11+ (tomllib) and JavaScript needs node on PATH; without them those files are skipped.
    Files matching cfg["syntax"]["exclude"] are skipped, and so is a .js file node rejects as JSX.
    """
    exclude = _syntax_exclude(cfg)
    try:
        import tomllib
    except ImportError:
        tomllib = None
    node = shutil.which("node")
    broken, checked = [], 0
    for f in files:
        ext = _ext(f)
        p = os.path.join(root, f)
        if ext not in SYNTAX_EXTS or not os.path.isfile(p) or os.path.getsize(p) >= MAX_FILE_BYTES \
                or any(glob_match(f, g) for g in exclude):
            continue
        if (ext == ".toml" and not tomllib) or (ext in (".js", ".mjs", ".cjs") and not node) \
                or (ext == ".json" and _JSONC.search(f)):
            continue
        checked += 1
        line, msg = 1, None
        try:
            if ext in (".js", ".mjs", ".cjs"):
                code, _, err = run([node, "--check", p], cwd=root, timeout=30)
                if code != 0:
                    line, msg = _node_error(err)
                    if ext == ".js" and _JSX_ERROR in msg:
                        line, msg = 1, None
                        checked -= 1
            else:
                with open(p, "rb") as fh:
                    data = fh.read()
                if ext == ".py":
                    compile(data, f, "exec", dont_inherit=True)
                elif ext == ".json":
                    json.loads(data)
                else:
                    tomllib.loads(data.decode("utf-8"))
        except SyntaxError as e:
            line, msg = e.lineno or 1, e.msg
        except json.JSONDecodeError as e:
            line, msg = e.lineno, e.msg
        except OSError:
            checked -= 1
        except (ValueError, RecursionError, MemoryError) as e:  # null bytes, bad encoding, TOML errors
            m = re.search(r"line (\d+)", str(e))
            line, msg = int(m.group(1)) if m else 1, str(e) or type(e).__name__
        if msg:
            broken.append(f"{f}:{line}: {msg}")
    return broken, checked


# ---------------------------------------------------------------- running

ERRORISH = re.compile(r"(?i)\b(fail\w*|error\w*|exception|traceback|assert\w*|panic|undefined|cannot|not found|"
                      r"expected|vulnerab\w*|critical|high)\b|✗|✘|^E\s")


def digest(text, limit=25):
    """The error lines of a check's output, first and last: the first error is usually the cause, the last the
    summary. Without error lines, the last lines."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    hits = [ln for ln in lines if ERRORISH.search(ln)]
    if not hits:
        pick = lines[-limit:]
    elif len(hits) <= limit:
        pick = hits
    else:
        head = limit // 2
        pick = hits[:head] + [f"... {len(hits) - limit + 1} more error lines ..."] + hits[-(limit - head - 1):]
    return "\n".join(ln[:300] for ln in pick)


def _changed_env(files, limit=120_000):
    """TIERWISE_CHANGED_FILES for check commands: newline-separated relative paths, kept under the OS limit."""
    text = "\n".join(files)
    if len(text.encode()) <= limit:  # the OS limit is on bytes: non-ASCII paths take more than one each
        return text
    return text.encode()[:limit].decode(errors="ignore").rsplit("\n", 1)[0]


@contextlib.contextmanager
def _environ(**extra):
    old = {k: os.environ.get(k) for k in extra}
    os.environ.update(extra)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_selected(root, selected, base, files, timeout=300, log_root=None, cfg=None):
    """Run each selected check in root; save full logs under log_root's .tierwise/; return (results, log dir).

    Command checks see TIERWISE_CHANGED_FILES. After a failed "syntax" or "affected" check the remaining
    non-security checks are skipped. cfg (default: the project's config) supplies the secret scan's rules.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_root = log_root or root
    cfg = cfg if cfg is not None else load_config(log_root)
    logdir = mdir(log_root, "reports", "checks", stamp)
    os.makedirs(logdir, exist_ok=True)
    results = []
    stopped = False
    for c in selected:
        log = os.path.join(logdir, f"{c['id']}.log")
        if stopped and c["id"] not in SECURITY_CHECKS:
            results.append({**c, "status": "skipped", "reason": "an earlier check failed", "log": None, "digest": "",
                            "selectedFor": c.get("reason")})
            continue
        if c["cmd"] is None:
            results.append({**c, "status": "missing", "log": None, "digest": ""})
            continue
        started = time.time()
        builtin = c["cmd"].startswith("builtin:")
        try:
            if c["cmd"] == "builtin:secrets":
                allowed = []
                found = scan_secrets(root, base, files, cfg, allowed)
                code, out = (1 if found else 0), "\n".join(found + allowed) if found else \
                    "\n".join(["no secrets found in the change"] + allowed)
            elif c["cmd"] == "builtin:syntax":
                broken, checked = syntax_check(root, files, cfg)
                code, out = (1 if broken else 0), "\n".join(broken) or \
                    f"no syntax errors in {checked} file(s) checked"
            else:
                with _environ(TIERWISE_CHANGED_FILES=_changed_env(files)):
                    code, out, err = run(["bash", "-c", c["cmd"]], cwd=root, timeout=timeout)
                out = out + ("\n" + err if err else "")
        except Exception as e:  # a crashing check is a failed check, never a gate that lets the change through
            code, out, builtin = 1, f"check {c['id']} crashed: {type(e).__name__}: {e}\n{traceback.format_exc()}", True
        with open(log, "w") as f:
            f.write(f"$ {c['cmd']}\n{out}\n[exit {code}]\n")
        shown = "\n".join(ln[:300] for ln in out.splitlines()[:25]) if builtin else digest(out)
        results.append({**c, "status": "pass" if code == 0 else "fail", "exit": code, "log": os.path.relpath(log, log_root),
                        "seconds": round(time.time() - started, 1), "digest": "" if code == 0 else shown})
        if code != 0 and c["id"] in FAIL_FAST_CHECKS:
            stopped = True
    return results, logdir


def summary(results):
    lines = []
    for r in results:
        if r["status"] == "pass":
            lines.append(f"PASS {r['id']}")
        elif r["status"] == "skipped":
            lines.append(f"SKIPPED {r['id']}: {r['reason']}")
        elif r["status"] == "missing":
            hint = TOOLS_TO_SUGGEST.get(r["id"], "set a command in .claude/tierwise.json")
            lines.append(f"MISSING {r['id']} ({r['reason']}): no command configured; {hint}")
        else:
            lines.append(f"FAIL {r['id']} (exit {r.get('exit')}, log {r['log']}):\n{r['digest']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- red-green

def red_green(root, cmd, base, tests, timeout=300):
    """The regression test must fail on the base and pass on the change.

    Copies the given test files from the working tree into a temporary worktree at `base`.
    """
    tmp = tempfile.mkdtemp(prefix="tierwise-redgreen-")
    os.rmdir(tmp)
    code, _, err = git(root, "worktree", "add", "--detach", tmp, base, timeout=120)
    if code != 0:
        return {"ok": False, "error": f"git worktree add failed: {err.strip()}"}
    try:
        for t in tests:
            src, dst = os.path.join(root, t), os.path.join(tmp, t)
            if not os.path.isfile(src):
                return {"ok": False, "error": f"test file not found: {t}"}
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        rc_base, out_base, err_base = run(["bash", "-c", cmd], cwd=tmp, timeout=timeout)
        rc_head, out_head, err_head = run(["bash", "-c", cmd], cwd=root, timeout=timeout)
    finally:
        git(root, "worktree", "remove", "--force", tmp, timeout=120)
        shutil.rmtree(tmp, ignore_errors=True)
    red, green = rc_base != 0, rc_head == 0
    return {"ok": red and green, "red": red, "green": green, "base": base,
            "baseDigest": digest(out_base + err_base, 10), "headDigest": "" if green else digest(out_head + err_head)}
