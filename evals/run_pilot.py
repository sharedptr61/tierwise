#!/usr/bin/env python3
"""Tierwise against single-model Claude Code on small tasks: the same prompt, the same repository, hidden acceptance tests.

Each run gets a fresh git copy of evals/tasks/<task>/repo and the prompt in prompt.md. Afterwards the hidden
tests in evals/tasks/<task>/hidden (never shown to the agent) and the project's own tests are run.

  python3 evals/run_pilot.py [--tasks shop-export,pricing-stale,notify-config] [--arms fable,tierwise]
                             [--runs 1] [--jobs 3] [--out evals/results/<timestamp>]

Sides ("arms"):
  fable    Claude Code on Fable for the whole task, no tierwise.
  opus     Claude Code on Opus for the whole task, no tierwise.
  tierwise  Claude Code on Opus as the main session, with tierwise routing (loaded with --plugin-dir).
Plugins synced from your claude.ai account are switched off in each run's own project settings, so both
sides run in the same plain environment. Nothing outside the run directories is changed.

Writes results.json, summary.md, one diff per run, and blind/<task>/{A,B,...}.diff (one letter per arm) with the key in blind/key.json.
Costs are Claude Code's own list-price figures; on a subscription they are usage of your limits, not a bill.
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TIERWISE = os.path.join(ROOT, "plugins", "tierwise")
TOOLS = ["Agent", "Skill", "Read", "Edit", "Write", "Grep", "Glob", "Bash(python3:*)", "Bash(git:*)", "Bash(ls:*)",
         "Bash(mkdir:*)", "Bash(cat:*)"]
ARMS = {
    "fable": ["--model", "fable"],
    "opus": ["--model", "opus"],
    "tierwise": ["--model", "opus", "--plugin-dir", TIERWISE],
}
GIT = {"GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "eval@example.invalid",
       "GIT_COMMITTER_NAME": "eval", "GIT_COMMITTER_EMAIL": "eval@example.invalid"}


def sh(argv, cwd, timeout=600, env=None, stdin=None):
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **GIT, **(env or {})}, input=stdin)
    return p.returncode, p.stdout, p.stderr


def synced_plugins():
    _, out, _ = sh(["claude", "plugin", "list"], cwd=ROOT, timeout=60)
    return sorted(set(re.findall(r"([a-z0-9][\w.-]*@synced)", out)))


def run_tests(work, start, top=None):
    argv = [sys.executable, "-m", "unittest", "discover", "-s", start] + (["-t", top] if top else [])
    code, out, err = sh(argv, cwd=work, timeout=300)
    text = out + err
    m = re.search(r"Ran (\d+) tests?", text)
    ran = int(m.group(1)) if m else 0
    bad = sum(int(x) for x in re.findall(r"(?:failures|errors)=(\d+)", text))
    return {"ok": code == 0 and ran > 0, "ran": ran, "failed": bad if ran else None, "tail": text.strip()[-600:]}


def one_run(task, arm, n, out, plugins_off):
    tdir = os.path.join(HERE, "tasks", task)
    name = f"{task}-{arm}-{n}"
    work = os.path.join(out, "work", name)
    shutil.copytree(os.path.join(tdir, "repo"), work)
    os.makedirs(os.path.join(work, ".claude"), exist_ok=True)
    with open(os.path.join(work, ".claude", "settings.json"), "w") as f:
        json.dump({"enabledPlugins": {p: False for p in plugins_off}}, f, indent=2)
    sh(["git", "init", "-q", "-b", "main"], work)
    sh(["git", "add", "-A"], work)
    sh(["git", "commit", "-qm", "task start"], work)
    with open(os.path.join(tdir, "prompt.md")) as f:
        prompt = f.read()
    started = time.time()
    try:
        code, stdout, stderr = sh(["claude", "-p", "--output-format", "json", "--allowedTools", *TOOLS, *ARMS[arm]],
                                  work, timeout=45 * 60, stdin=prompt)
    except subprocess.TimeoutExpired:
        code, stdout, stderr = 124, "", "timed out after 45 minutes"
    seconds = round(time.time() - started)
    try:
        result = json.loads(stdout)
    except ValueError:
        result = {"is_error": True, "result": (stdout + stderr)[-2000:]}
    sh(["git", "add", "-A", "--", ".", ":!.tierwise", ":!**/__pycache__"], work)
    _, diff, _ = sh(["git", "diff", "--cached", "--", ".", ":!.claude/tierwise.json", ":!.claude/settings.local.json"], work)
    os.makedirs(os.path.join(out, "diffs"), exist_ok=True)
    with open(os.path.join(out, "diffs", name + ".diff"), "w") as f:
        f.write(diff)
    shutil.copytree(os.path.join(tdir, "hidden"), os.path.join(work, "hidden_eval"))
    hidden = run_tests(work, "hidden_eval")
    expected = sum(open(os.path.join(tdir, "hidden", f)).read().count("    def test_")
                   for f in os.listdir(os.path.join(tdir, "hidden")) if f.endswith(".py"))
    passed = hidden["ran"] - (hidden["failed"] or 0) if hidden["ran"] else 0
    visible = run_tests(work, "tests", ".")
    ledger = ""
    if os.path.exists(os.path.join(work, ".tierwise", "ledger.md")):
        with open(os.path.join(work, ".tierwise", "ledger.md")) as f:
            ledger = "".join(f.readlines()[4:])
    usage = {m.replace("claude-", ""): {"cost": round(u.get("costUSD", 0), 4), "output": u.get("outputTokens", 0),
                                        "tokens": sum(u.get(k, 0) for k in ("inputTokens", "outputTokens",
                                                                             "cacheReadInputTokens",
                                                                             "cacheCreationInputTokens"))}
             for m, u in (result.get("modelUsage") or {}).items()}
    return {"task": task, "arm": arm, "run": n, "exit": code, "seconds": seconds,
            "cost": round(result.get("total_cost_usd", 0) or 0, 4), "models": usage,
            "error": bool(result.get("is_error")), "hidden_passed": passed, "hidden_total": expected,
            "hidden_tail": hidden["tail"], "visible_ok": visible["ok"], "visible_ran": visible["ran"],
            "diff_lines": diff.count("\n"), "answer": (result.get("result") or "")[:1500], "ledger": ledger}


def summary_md(rows):
    lines = ["| Task | Side | Hidden tests | Own tests | Cost (list) | Minutes | Models (cost) |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in sorted(rows, key=lambda r: (r["task"], r["arm"], r["run"])):
        models = ", ".join(f"{m} ${u['cost']:.2f}" for m, u in sorted(r["models"].items(), key=lambda kv: -kv[1]["cost"]))
        lines.append(f"| {r['task']} | {r['arm']} | {r['hidden_passed']}/{r['hidden_total']} | "
                     f"{'pass' if r['visible_ok'] else 'FAIL'} ({r['visible_ran']}) | ${r['cost']:.2f} | "
                     f"{r['seconds'] / 60:.1f} | {models} |")
    by_arm = {}
    for r in rows:
        a = by_arm.setdefault(r["arm"], {"cost": 0.0, "passed": 0, "total": 0, "seconds": 0})
        a["cost"] += r["cost"]
        a["passed"] += r["hidden_passed"]
        a["total"] += r["hidden_total"]
        a["seconds"] += r["seconds"]
    lines += ["", "| Side | Hidden tests passed | Total cost (list) | Total minutes |", "| --- | --- | --- | --- |"]
    for arm, a in sorted(by_arm.items()):
        lines.append(f"| {arm} | {a['passed']}/{a['total']} | ${a['cost']:.2f} | {a['seconds'] / 60:.1f} |")
    return "\n".join(lines) + "\n"


def blind_packet(rows, out):
    key = {}
    for task in sorted({r["task"] for r in rows}):
        runs = [r for r in rows if r["task"] == task and r["run"] == 1]
        random.shuffle(runs)
        os.makedirs(os.path.join(out, "blind", task), exist_ok=True)
        for label, r in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", runs):  # every arm gets a letter
            shutil.copy(os.path.join(out, "diffs", f"{task}-{r['arm']}-1.diff"),
                        os.path.join(out, "blind", task, f"{label}.diff"))
            key[f"{task}/{label}"] = r["arm"]
    with open(os.path.join(out, "blind", "key.json"), "w") as f:
        json.dump(key, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="shop-export,pricing-stale,notify-config")
    ap.add_argument("--arms", default="fable,tierwise")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(HERE, "results", time.strftime("%Y%m%d-%H%M%S")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    plugins_off = synced_plugins()
    jobs = [(t, arm, n) for n in range(1, a.runs + 1) for t in a.tasks.split(",") for arm in a.arms.split(",")]
    rows = []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures = {pool.submit(one_run, t, arm, n, a.out, plugins_off): (t, arm, n) for t, arm, n in jobs}
        for fut in cf.as_completed(futures):
            r = fut.result()
            rows.append(r)
            print(f"done {r['task']} {r['arm']} #{r['run']}: hidden {r['hidden_passed']}/{r['hidden_total']}, "
                  f"${r['cost']:.2f}, {r['seconds'] / 60:.1f} min", flush=True)
            with open(os.path.join(a.out, "results.json"), "w") as f:
                json.dump(sorted(rows, key=lambda r: (r["task"], r["arm"], r["run"])), f, indent=1)
    with open(os.path.join(a.out, "summary.md"), "w") as f:
        f.write(summary_md(rows))
    if "," in a.arms:
        blind_packet(rows, a.out)
    print(summary_md(rows))
    print("results:", a.out)


if __name__ == "__main__":
    main()
