"""Task lifecycle: recording routes, starting tasks, the completion gate."""
import hashlib
import json
import os
import re
import time

from . import checks as C
from .common import (PLUGIN_ROOT, config_path, changed_files, git_root, ensure_layout, ledger, load_config, load_state, locked_state,
                     max_tier, mdir, now_iso, prompt_hash, snapshot, task_active)

REQUIRED_REVIEWS = {"R0": [], "R1": ["code"], "R2": ["code", "security"], "R3": ["principal", "security"]}
# When Fable wrote the code, an R3 code review goes to Opus (tierwise:reviewer at xhigh), never Fable reviewing itself.
REQUIRED_REVIEWS_FABLE_AUTHOR = {**REQUIRED_REVIEWS, "R3": ["code", "security"]}
# security-guidance passes this value to the API as a model ID with a claude.ai sign-in; an alias is not accepted there.
SG_REVIEW_MODEL = "claude-sonnet-5-5"
REVIEW_AGENT = {"code": "tierwise:reviewer", "security": "tierwise:security-reviewer", "principal": "tierwise:principal"}
REVIEW_EFFORT = {"R1": "medium", "R2": "high", "R3": "xhigh"}

RUNG_ACTION = {
    1: "Retry yourself under the tierwise:debug skill (effort high): read the digest and the log, one hypothesis at a "
       "time.",
    2: "Write a failure dossier (templates/dossier.md, saved under .tierwise/briefs/) and spawn tierwise:debugger "
       "(Opus, xhigh) with it.",
    3: "Spawn tierwise:principal (Fable, xhigh) with the dossier. If the failure shows the plan is wrong, replan with "
       "tierwise:planner instead of climbing.",
    4: "Last attempt: spawn tierwise:principal with effort: max.",
    5: "Stop and ask the user, with the diagnosis so far.",
}
# Failures that are not a debugging problem: the block message says what to do, and the ladder does not climb.
NO_LADDER_ACTION = {
    "syntax": "Fix the file named in the syntax failure above.",
    "secrets": "Remove the secret, or allowlist it in .claude/tierwise.json under secrets.allow if it is not one.",
}


def sg_installed():
    """Whether the security-guidance plugin is enabled in the user's settings (read-only check)."""
    path = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude")), "settings.json")
    try:
        with open(path) as f:
            enabled = json.load(f).get("enabledPlugins", {})
    except (OSError, ValueError):
        return None
    return any(k.startswith("security-guidance@") and v for k, v in enabled.items())


def sg_env_set(root):
    """Whether the project already sets SECURITY_REVIEW_MODEL for security-guidance (read-only)."""
    for name in ("settings.json", "settings.local.json"):
        try:
            with open(os.path.join(root, ".claude", name)) as f:
                if json.load(f).get("env", {}).get("SECURITY_REVIEW_MODEL") is not None:
                    return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


def ensure_config(root):
    """Write .claude/tierwise.json from auto-detection when the project has none. Returns a note, or None.

    Tierwise never changes Claude Code's settings files. When security-guidance is installed and the project
    does not choose a model for its end-of-turn review, the note suggests one for the user to add.
    """
    path = config_path(root)
    if os.path.exists(path):
        return None
    found = C.detect(root)
    cfg = {"confirmed": False, "checks": found}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    listed = ", ".join(f"{k}: `{v}`" for k, v in sorted(found.items())) or "nothing detected"
    suggest = sg_installed() and not sg_env_set(root)
    return (f"Tierwise wrote .claude/tierwise.json from auto-detection ({listed}). Show the user these check commands "
            "once, ask them to confirm or correct them, then set \"confirmed\": true."
            + (f" Also tell the user, once, that security-guidance's end-of-turn review can run on Sonnet if they add "
               f"\"env\": {{\"SECURITY_REVIEW_MODEL\": \"{SG_REVIEW_MODEL}\"}} to .claude/settings.local.json; "
               "Tierwise does not change settings files itself." if suggest else ""))


def new_task_id():
    """t<date>-<time>-<milliseconds>: two tasks started within the same second still get different ids."""
    now = time.time()
    return time.strftime("t%Y%m%d-%H%M%S", time.localtime(now)) + f"-{int(now * 1000) % 1000:03d}"


def failure_signature(result):
    """What a failing check said, with numbers (line numbers, timings, counts, addresses) masked: the same
    failure seen again has the same signature, a different failure a different one."""
    text = re.sub(r"0x[0-9a-fA-F]+|\d+(?:\.\d+)?", "#", result.get("digest") or "")
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def record_route(root, r, prompt, by):
    """Write the route to state.json; start a task when the prompt changes code. Returns extra notes."""
    notes = []
    ensure_layout(root)
    if r.get("startsTask"):
        note = ensure_config(root)
        if note:
            notes.append(note)
    with locked_state(root) as s:
        s["card"] = {k: r[k] for k in ("class", "tier", "plan", "residentEffort", "plannerEffort", "source")}
        s["cardHash"], s["cardBy"], s["cardAt"] = prompt_hash(prompt), by, time.time()
        s["effortOverride"] = r.get("effortOverride")
        if r.get("startsTask"):
            t = s.get("task")
            untouched = task_active(s) and t.get("phase") == "route" and not changed_files(
                root, t.get("base"), t.get("untracked", []))
            if untouched:
                ledger(root, f"task {t['id']} replaced: nothing had changed when a new task was routed")
            if not task_active(s) or untouched or t.get("phase") in ("verified", "blocked"):
                base, untracked = snapshot(root)
                s["task"] = {"id": new_task_id(), "class": r["class"], "tier": r["tier"],
                             "phase": "route", "base": base, "untracked": untracked, "started": now_iso(),
                             "prompt": (prompt or "")[:200], "plan": None, "counters": {}, "attempts": {},
                             "rung": 0, "gateBlocks": 0, "reviews": {}}
                s["inflight"] = {}
                ledger(root, f"task {s['task']['id']} started: {r['class']} · {r['tier']} · by {by} "
                             f"({r['source']}) · \"{(prompt or '')[:80]}\"")
            else:
                t["tier"] = max_tier(t["tier"], r["tier"])  # the prompt can raise the tier, never lower it
                ledger(root, f"task {t['id']} continues: prompt routed {r['class']} · {r['tier']}")
    return notes


# ---------------------------------------------------------------- the gate

def last_change_time(root, files):
    times = [os.path.getmtime(os.path.join(root, f)) for f in files if os.path.exists(os.path.join(root, f))]
    return max(times) if times else time.time()


def main_model(transcript_path):
    """The model of the main session's latest response, read from the end of its transcript; None if unknown."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 2_000_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return None
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        model = (row.get("message") or {}).get("model") if row.get("type") == "assistant" else None
        if model and model != "<synthetic>":
            return model
    return None


def missing_reviews(task, files, root):
    changed_at = last_change_time(root, files)
    done = task.get("reviews", {})
    fable_author = "fable" in (task.get("authorModel") or "")
    need = []
    for kind in (REQUIRED_REVIEWS_FABLE_AUTHOR if fable_author else REQUIRED_REVIEWS).get(task.get("tier", "R1"), []):
        ts = done.get(kind)
        if kind == "code" and not fable_author and done.get("principal", 0) >= changed_at:
            continue
        if not ts or ts < changed_at:
            need.append(kind)
    return need


def gate(root, inp):
    """The Stop hook: run the selected checks; block while they fail or required reviews are missing."""
    state = load_state(root)
    if not task_active(state):
        return None
    task = state["task"]
    running = [t for t in (inp.get("background_tasks") or [])
               if t.get("status") == "running" and str(t.get("agent_type", "")).startswith("tierwise:")]
    if running:
        ledger(root, f"gate deferred: {len(running)} tierwise agent(s) still running")
        return None
    work = git_root(inp.get("cwd") or root) or root  # the session may work in its own worktree
    files = changed_files(work, task.get("base"), task.get("untracked", []))
    if not files:
        return None
    changed_at = last_change_time(work, files)
    if task.get("phase") == "verified" and changed_at <= state.get("verification", {}).get("changedAt", 0):
        return None  # nothing changed since the last pass
    cfg = load_config(root)
    selected = C.select(cfg, files, task["tier"], task["class"], C.plan_checks(root, task.get("plan")))
    results, logdir = C.run_selected(work, selected, task.get("base"), files,
                                     timeout=cfg["caps"].get("checkTimeoutSeconds", 300), log_root=root)
    failed = [r["id"] for r in results if r["status"] == "fail"]  # "skipped" is neither a pass nor a failure
    laddered = [c for c in failed if c not in NO_LADDER_ACTION]
    missing_tools = [r["id"] for r in results if r["status"] == "missing"]
    text = C.summary(results)
    cap = cfg["caps"].get("gateBlocksPerTask", 8)

    author = main_model(inp.get("transcript_path"))
    with locked_state(root) as s:
        t = s["task"]
        if author and "fable" in author:
            t["authorModel"] = author  # once Fable has written code in this task, the rule holds for the task
        elif author and not t.get("authorModel"):
            t["authorModel"] = author
        s["verification"] = {"status": "fail" if failed else "pass", "at": now_iso(), "failed": failed,
                             "missing": missing_tools, "logs": os.path.relpath(logdir, root), "files": len(files),
                             "changedAt": changed_at}
        # A new attempt is a stop after the code changed. A stop with nothing changed since the last block
        # (the session is asking the user something, or giving up) is let through with a message, not looped.
        new_attempt = changed_at != t.get("lastBlockChangedAt")
        escalated = None
        if laddered and new_attempt:
            old_rung = t["rung"]
            seen = t.setdefault("signatures", {})
            for cid in laddered:
                # The ladder climbs on a failure seen before. A failure never seen for this check is progress
                # (the last one is fixed, a new one surfaced): it restarts at one attempt instead of escalating.
                sig = failure_signature(next(r for r in results if r["id"] == cid))
                if sig in seen.get(cid, []):
                    t["attempts"][cid] = t["attempts"].get(cid, 0) + 1
                else:
                    t["attempts"][cid] = 1
                    seen[cid] = (seen.get(cid, []) + [sig])[-20:]
            t["rung"] = min(5, max(t["attempts"][c] for c in laddered))
            if t["rung"] > old_rung:
                escalated = (old_rung, t["rung"])
        elif not failed:
            t["attempts"], t["rung"], t["signatures"] = {}, 0, {}
        s["effortFloor"] = "high" if laddered and t["rung"] >= 1 else None
        need = [] if failed else missing_reviews(t, files, work)
        capped = t["gateBlocks"] >= cap or (laddered and t["rung"] >= 5)
        if (failed or need) and new_attempt and not capped:
            t["gateBlocks"] += 1
            t["lastBlockChangedAt"] = changed_at
            t["phase"], outcome = ("verify" if failed else "review"), "block"
        elif failed or need:
            t["phase"], outcome = ("blocked" if capped else "verify" if failed else "review"), "release"
        else:
            t["phase"], t["gateBlocks"], outcome = "verified", 0, "pass"
        rung, tier, phase = t["rung"], t["tier"], t["phase"]
        task_id = t["id"]
        fable_author = "fable" in (t.get("authorModel") or "")

    if escalated:
        ledger(root, f"ladder: task {task_id} rung {escalated[0]} -> {escalated[1]} on {', '.join(laddered)}: "
                     f"{RUNG_ACTION[escalated[1]].split('. ')[0].rstrip('.')}.")
    ledger(root, f"gate: {'FAIL ' + ', '.join(failed) if failed else 'checks pass'}"
                 f"{' · missing tools ' + ', '.join(missing_tools) if missing_tools else ''}"
                 f"{' · reviews needed ' + ', '.join(need) if need else ''} · phase {phase}")
    if outcome == "block" and failed:
        todo = [f"{NO_LADDER_ACTION[c]}" for c in failed if c in NO_LADDER_ACTION]
        if laddered:
            todo.append(f"Ladder rung {rung}: {RUNG_ACTION[rung]}")
        return {"decision": "block", "reason": f"tierwise gate: required checks fail.\n{text}\n\n" + "\n".join(todo)}
    if outcome == "block":
        how = "; ".join(f"{REVIEW_AGENT[k]} at {REVIEW_EFFORT.get(tier, 'high') if k != 'principal' else 'xhigh'}"
                        for k in need)
        return {"decision": "block", "reason": (
            f"tierwise gate: checks pass ({', '.join(r['id'] for r in results if r['status'] == 'pass')}). "
            f"{tier} needs these reviews of the current diff before completion: {how}"
            f"{' (Fable wrote this code, so Opus reviews it, not the principal)' if fable_author and tier == 'R3' else ''}"
            ". Build the package with "
            f"`python3 {PLUGIN_ROOT}/bin/review-package` and give each reviewer only its path. "
            "Confirm each finding against the code before fixing; then the checks run again.")}
    if outcome == "release":
        why = (f"checks still fail ({', '.join(failed)})" if failed else
               f"required review(s) not run: {', '.join(REVIEW_AGENT[k] for k in need)}")
        tail = (" The debugging ladder or the gate cap is exhausted; the diagnosis is in .tierwise/ledger.md."
                if phase == "blocked" else " Nothing changed since the last block, so tierwise is not blocking "
                "again; the task is not verified.")
        return {"systemMessage": f"tierwise: {why}.{tail}" + (f"\n{text}" if failed else "")}
    msg = f"tierwise: checks pass ({', '.join(r['id'] for r in results if r['status'] == 'pass')})."
    if missing_tools:
        msg += f" Not run, no tool configured: {', '.join(missing_tools)}."
    if tier == "R3":
        msg += " R3 change: please review and sign off before merging or running anything irreversible."
    return {"systemMessage": msg}
