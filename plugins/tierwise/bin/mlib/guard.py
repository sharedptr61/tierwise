"""Spawn guard and subagent hooks.

pre_agent      PreToolUse on Agent: model map, effort floors and overrides, caps, task budget, depth, Fable fallback.
pre_write      PreToolUse on Write/Edit inside tierwise agents: planner writes only plans, readers only reports.
pre_handback   PreToolUse on SubagentHandback: the report contract.
subagent_stop  SubagentStop: log the model that actually ran, tally Fable output, record reviews, detect a
               planner that hit the Fable limit.
Each returns the hook's JSON output, or None for no output.
"""
import json
import os
import re
import time

from .common import (EFFORTS, git_root, ledger, main_root, load_config, load_state, locked_state, max_effort, mdir,
                     short, task_active, tier_at_least, week_key)
from .flow import REVIEW_EFFORT

POLICY = {
    "scout": {"models": ["haiku"], "efforts": ["low", "medium"], "writes": ".tierwise/reports/"},
    "analyst": {"models": ["sonnet"], "efforts": ["medium", "high"], "writes": ".tierwise/reports/"},
    "planner": {"models": ["fable", "opus"], "efforts": ["high", "xhigh", "max"], "writes": ".tierwise/plans/"},
    "builder": {"models": ["sonnet", "haiku", "opus"], "efforts": ["low", "medium", "high"]},
    "debugger": {"models": ["opus"], "efforts": ["high", "xhigh"]},
    "reviewer": {"models": ["opus"], "efforts": ["medium", "high", "xhigh"], "writes": ".tierwise/reports/"},
    "security-reviewer": {"models": ["opus"], "efforts": ["high", "xhigh"], "writes": ".tierwise/reports/"},
    "principal": {"models": ["fable", "opus"], "efforts": ["xhigh", "max"]},
}
REVIEW_KIND = {"reviewer": "code", "security-reviewer": "security", "principal": "principal"}
# Effort each agent's definition pins; the guard adds an effort to the call only when it must differ.
PINNED_EFFORT = {"scout": "low", "analyst": "high", "planner": "xhigh", "builder": "medium", "debugger": "xhigh",
                 "reviewer": "high", "security-reviewer": "high", "principal": "xhigh"}
# Built-in agent types that inherit the main session's model (Opus or Fable prices) for work tierwise routes cheaper.
# Superpowers' subagent-driven-development, requesting-code-review and dispatching-parallel-agents use them.
BUILTIN_INHERITORS = {"Explore", "general-purpose", "Plan"}
REPORT_FIELDS = ["STATUS", "CHANGED", "CHECKS", "RISKS", "REPORT"]
STATUSES = {"done", "partial", "blocked", "failed"}
MAX_REPORT_CHARS = 1500
# Spawns that escalate a task; past caps.taskBudgetUsd they wait for the user. Scouts, analysts, builders and
# reviewers stay allowed: the cap stops escalation, not verification.
BUDGET_CAPPED = {"planner", "principal", "debugger"}


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": f"tierwise: {reason}"}}


def rewrite(tool_input, updates, note):
    # No permissionDecision: the user's permission rules still decide whether the call runs.
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": {**tool_input, **updates},
                                   "additionalContext": f"tierwise: {note}"}}


def _fable_exhausted(state):
    return state.get("fable", {}).get("exhausted") == week_key()


def task_usage(root, task_id):
    """List-price dollars the task has used so far, from .tierwise/usage.json (the mod keeps it); None if unknown."""
    try:
        with open(mdir(root, "usage.json")) as f:
            used = json.load(f)[task_id]["cost"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return float(used) if isinstance(used, (int, float)) and not isinstance(used, bool) else None


def over_budget(root, task, caps):
    """(used, cap) when the task's usage is at or past caps.taskBudgetUsd, else None (also with no cap or no file)."""
    cap = caps.get("taskBudgetUsd")
    if cap is None or isinstance(cap, bool) or not isinstance(cap, (int, float)) or not task.get("id"):
        return None
    used = task_usage(root, task["id"])
    return (used, cap) if used is not None and used >= cap else None


def pre_agent(inp):
    ti = inp.get("tool_input") or {}
    target = ti.get("subagent_type") or ""
    caller = inp.get("agent_type") or ""
    root = main_root(inp.get("cwd") or ".")
    state = load_state(root) if root else {}
    active = task_active(state)

    if caller.startswith("tierwise:"):
        return deny("tierwise agents do not spawn agents; delegation depth stays at one. Report back instead.")
    if target == "caveman:cavecrew-builder" and active:
        return deny("use tierwise:builder, which pins its model and effort; cavecrew-builder inherits Opus.")
    if target in BUILTIN_INHERITORS and root and os.path.isdir(os.path.join(root, ".tierwise")) and \
            not load_config(root).get("allowBuiltinAgents"):
        return deny(f"the built-in {target} agent runs on your main model's prices. Send the same prompt to the "
                    f"tierwise agent for the job: {suggest_agent(ti)}. (tierwise:scout for lookups and exploration, "
                    "tierwise:analyst for explanations and impact maps, tierwise:builder for an implementation unit, "
                    "tierwise:reviewer for a review, tierwise:planner for a plan.)")
    if not target.startswith("tierwise:"):
        return None
    name = short(target)
    pol = POLICY.get(name)
    if pol is None:
        return None
    cfg = load_config(root) if root else load_config(None)
    task = state.get("task") or {}
    tier = task.get("tier") if active else (state.get("card") or {}).get("tier") or "R1"
    counters = task.get("counters", {})
    caps = cfg["caps"]
    model, effort = ti.get("model"), ti.get("effort")
    updates, notes = {}, []

    # Budget (per task): checked first, so a capped spawn is never asked to be re-issued.
    if active and root and name in BUDGET_CAPPED:
        over = over_budget(root, task, caps)
        if over:
            return deny(f"task budget reached: this task has used ${over[0]:.2f} of its ${over[1]:.2f} "
                        "(caps.taskBudgetUsd; list-price equivalent: on a subscription this is usage of your limits, "
                        f"not a bill). Do not spawn {name}. Stop and ask the user whether to continue, with what is "
                        "done and what is left; they can raise caps.taskBudgetUsd in .claude/tierwise.json. Scouts, "
                        "analysts, builders and reviewers are still allowed: the cap stops escalation, not "
                        "verification.")

    # Haiku locates; it does not judge. Research, evaluation and recommendations go to the analyst (Sonnet).
    if name == "scout" and SCOUT_JUDGMENT.search(ti.get("prompt") or ""):
        return deny("tierwise:scout (Haiku) locates and digests; this brief asks for judgment "
                    f"(\"{SCOUT_JUDGMENT.search(ti.get('prompt') or '').group(0)}\"). Send it to tierwise:analyst, "
                    "or split it: the scout finds the files, the analyst weighs them.")

    # Models
    if name in ("planner", "principal") and model in (None, "fable") and _fable_exhausted(state):
        updates["model"] = cfg["planner"].get("fallbackModel", "opus")
        notes.append(f"Fable limit reached this week; {name} runs on {updates['model']} instead")
        if name == "planner":
            updates["effort"] = "max"
    elif model and model not in pol["models"]:
        return deny(f"{name} runs on {' or '.join(pol['models'])}, not {model}.")
    if name == "builder":
        m = model or "sonnet"
        if tier == "R3" and m != "opus":
            return deny("R3 core logic is not delegated below Opus: implement it inline, or spawn the builder "
                        "with model: opus.")
        if m == "haiku" and tier_at_least(tier, "R2"):
            return deny(f"no Haiku edits at {tier}; use the default (Sonnet).")

    # Efforts
    if name in ("reviewer", "security-reviewer"):
        floor = REVIEW_EFFORT.get(tier, "high") if name == "reviewer" else max_effort(REVIEW_EFFORT.get(tier), "high")
        if effort is None or EFFORTS.index(effort) < EFFORTS.index(floor):
            updates["effort"] = floor
            if effort:
                notes.append(f"{name} effort raised to {floor} for {tier}; reviews are never lowered")
    if name == "planner" and effort is None and "effort" not in updates:
        replan = active and counters.get("planner", 0) >= 1
        want = cfg["planner"].get("replanEffort", "max") if replan else \
            (state.get("card") or {}).get("plannerEffort") or cfg["planner"].get("effort", "xhigh")
        if want != PINNED_EFFORT["planner"]:
            updates["effort"] = want
            notes.append(f"planner at {want}" + (" for a replan" if replan else ""))
    if name == "principal" and effort == "max" and task.get("rung", 0) < 4 and state.get("effortOverride") != "max":
        updates["effort"] = "xhigh"
        notes.append("principal runs at max only on the last debugging rung; using xhigh")
    final_effort = updates.get("effort", effort)
    if final_effort and final_effort not in pol["efforts"]:
        return deny(f"{name} effort must be one of {', '.join(pol['efforts'])}, not {final_effort}.")

    # In auto mode a hook may not change a call's input after auto mode reviewed it (Claude Code refuses
    # the call), so the guard names the exact fix and the caller re-issues it. Nothing is counted yet.
    if updates and inp.get("permission_mode") == "auto":
        fix = ", ".join(f"{k}: {v}" for k, v in updates.items())
        return deny(f"re-issue this Agent call with {fix}" + (f" ({'; '.join(notes)})" if notes else "") +
                    ". Same subagent_type and prompt.")

    # Caps (per task)
    if active:
        if name == "planner" and counters.get("planner", 0) >= 1 + caps.get("replansPerTask", 1):
            return deny("replan cap reached for this task; ask the user before planning again.")
        if name == "principal" and counters.get("principal", 0) >= caps.get("principalCallsPerTask", 2):
            return deny("principal cap reached for this task; stop and ask the user with the diagnosis.")
        running = (state.get("inflight") or {}).get("builder", 0)
        if name == "builder" and running >= caps.get("parallelBuilders", 3):
            return deny(f"{running} builders already running (cap {caps.get('parallelBuilders', 3)}); wait for one.")
        with locked_state(root) as s:
            c = s["task"].setdefault("counters", {})
            c[name] = c.get(name, 0) + 1
            if name == "builder":
                s.setdefault("inflight", {})["builder"] = s.get("inflight", {}).get("builder", 0) + 1
    if root:
        ledger(root, f"spawn {target} model={updates.get('model', model or 'pinned')} "
                     f"effort={updates.get('effort', effort or 'pinned')}{' · ' + '; '.join(notes) if notes else ''}")
    return rewrite(ti, updates, "; ".join(notes) or "input adjusted") if updates else None


def suggest_agent(tool_input):
    """The tierwise agent a built-in agent's job most likely belongs to, from its description and prompt."""
    text = f"{tool_input.get('description', '')} {tool_input.get('prompt', '')}".lower()
    if re.search(r"\breview|audit|critique|second opinion|check (the|this) (diff|change|code)", text):
        return "tierwise:reviewer"
    if re.search(r"\bplan\b|design the|architecture for", text) and tool_input.get("subagent_type") == "Plan":
        return "tierwise:planner"
    if re.search(r"\b(find|search|locate|where|list|explore|look for|grep|inventory|which files)\b", text):
        return "tierwise:scout"
    if re.search(r"\b(explain|how does|understand|impact|map)\b", text):
        return "tierwise:analyst"
    return "tierwise:scout" if tool_input.get("subagent_type") == "Explore" else "tierwise:builder"


def r3_plan_first(inp):
    """At R3 the main session edits nothing until tierwise:planner has written the plan (unless the user said no plan)."""
    root = main_root(inp.get("cwd") or ".")
    state = load_state(root) if root else {}
    task = state.get("task") or {}
    if not task_active(state) or task.get("tier") != "R3" or task.get("plan") or \
            not (state.get("card") or {}).get("plan"):
        return None
    ti = inp.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    rel = os.path.relpath(os.path.abspath(os.path.join(inp.get("cwd") or ".", path)), root)
    if rel.startswith(".tierwise" + os.sep) or rel == ".tierwise":
        return None
    return deny("R3 task: the plan comes first (threat model, rollback, irreversible steps). Spawn tierwise:planner; "
                "your edits are allowed once its plan is written. If the user said no plan, say so in your next "
                "prompt to tierwise.")


def pre_write(inp):
    caller = inp.get("agent_type") or ""
    if not caller:
        return r3_plan_first(inp)
    name = short(caller) if caller.startswith("tierwise:") else None
    allowed = POLICY.get(name, {}).get("writes") if name else None
    if not allowed:
        return None
    ti = inp.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
    cwd = inp.get("cwd") or "."
    root = git_root(cwd) or cwd
    rel = os.path.relpath(os.path.abspath(os.path.join(cwd, path)), root)
    if rel.startswith(allowed) and ".." not in rel.split(os.sep):
        return None
    return deny(f"{name} may write only under {allowed} (tried {rel}).")


# Read-only agents may run commands that read (git diff/log/show/status, grep, tests); never ones that change
# the working tree, the index, refs or files. Checked on each segment of a compound command.
SCOUT_JUDGMENT = re.compile(
    r"\b(?:evaluate|evaluation|assess(?:ment)?|recommend\w*|research|which (?:is|would be) better|pros and cons|"
    r"trade-?offs?|judge|rank (?:them|these|the)|should we|decide|best approach|review (?:the|this) (?:design|code))\b",
    re.I)
READ_ONLY_AGENTS = {"scout", "analyst", "reviewer", "security-reviewer"}
MUTATING = re.compile(
    r"^\s*(?:sudo\s+)?(?:git\s+(?:-C\s+\S+\s+)?(?:stash|checkout|switch|reset|restore|commit|push|pull|merge|rebase|"
    r"cherry-pick|revert|clean|rm|mv|apply|am|add|tag|worktree\s+(?:add|remove|prune)|branch\s+-[dDmM]|"
    r"update-ref|config\s+(?!--get|-l|--list))|rm|mv|cp|chmod|chown|truncate|dd|mkfs|tee|"
    r"pip3?\s+install|npm\s+(?:install|i|ci|uninstall)|yarn\s+add|sed\s+-i|perl\s+-p?i)\b")
REDIRECT = re.compile(r"(?<![0-9&])>>?\s*(?!/dev/null|&)\S")


def pre_bash(inp):
    caller = inp.get("agent_type") or ""
    if short(caller) not in READ_ONLY_AGENTS or not caller.startswith("tierwise:"):
        return None
    cmd = (inp.get("tool_input") or {}).get("command") or ""
    for part in re.split(r"&&|\|\||;|\||\n|\$\(|`", cmd):
        if MUTATING.search(part) or REDIRECT.search(part):
            return deny(f"{short(caller)} is read-only: `{part.strip()[:80]}` would change files, the index or git "
                        "state. Read the diff with `git diff` / `git show <rev>:<path>` instead, and write findings "
                        "only to your report file.")
    return None


def check_report(message):
    """Problems with a hand-back report, or [] when it meets the contract."""
    problems = []
    fields = {}
    for line in (message or "").splitlines():
        m = re.match(r"\s*\**([A-Z]+)\**\s*:\s*\**\s*(.*)", line)
        if m and m.group(1) in REPORT_FIELDS:
            fields[m.group(1)] = m.group(2).strip()
    absent = [f for f in REPORT_FIELDS if f not in fields]
    if absent:
        problems.append(f"missing field(s): {', '.join(absent)}")
    status = fields.get("STATUS", "").split()[0].lower().strip(".") if fields.get("STATUS") else ""
    if "STATUS" in fields and status not in STATUSES:
        problems.append(f"STATUS must start with one of {', '.join(sorted(STATUSES))}")
    if len(message or "") > MAX_REPORT_CHARS:
        problems.append(f"report is {len(message)} characters; keep it under {MAX_REPORT_CHARS} and put detail in "
                        "the REPORT file")
    return problems


def pre_handback(inp):
    caller = inp.get("agent_type") or ""
    if not caller.startswith("tierwise:"):
        return None
    problems = check_report((inp.get("tool_input") or {}).get("message", ""))
    if not problems:
        return None
    return deny("report rejected: " + "; ".join(problems) + ". Resend it in this form:\nSTATUS: done|partial|"
                "blocked|failed — one line\nCHANGED: files, or none\nCHECKS: what ran and the result\nRISKS: open "
                "risks, or none\nREPORT: path of the full report under .tierwise/reports/, or none")


def read_transcript(path):
    """Models, output tokens, whether a report was handed back, and any error text, from a subagent transcript."""
    info = {"models": [], "output": 0, "handback": False, "errors": []}
    try:
        with open(path) as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                msg = row.get("message") or {}
                if row.get("type") != "assistant" or not isinstance(msg, dict):
                    continue
                model = msg.get("model")
                if model and model not in info["models"] and model != "<synthetic>":
                    info["models"].append(model)
                info["output"] += (msg.get("usage") or {}).get("output_tokens", 0) or 0
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and \
                            block.get("name") == "SubagentHandback":
                        info["handback"] = True
                    if isinstance(block, dict) and block.get("type") == "text" and row.get("isApiErrorMessage"):
                        info["errors"].append(block.get("text", "")[:300])
    except OSError:
        pass
    return info


LIMIT_TEXT = re.compile(r"(?i)fable limit|usage credits|weekly limit|rate.?limit|limit reached")


def subagent_stop(inp):
    agent = inp.get("agent_type") or ""
    if not agent.startswith("tierwise:"):
        return None
    root = main_root(inp.get("cwd") or ".")  # a builder runs in its own worktree
    if not root or not os.path.isdir(os.path.join(root, ".tierwise")):
        return None
    name = short(agent)
    info = read_transcript(inp.get("agent_transcript_path") or "")
    effort = (inp.get("effort") or {}).get("level") if isinstance(inp.get("effort"), dict) else inp.get("effort")
    fable_out = info["output"] if any("fable" in m for m in info["models"]) else 0
    message = None
    cfg = load_config(root)
    with locked_state(root) as s:
        if name == "builder":
            inflight = s.setdefault("inflight", {})
            inflight["builder"] = max(0, inflight.get("builder", 0) - 1)
        fab = s.setdefault("fable", {})
        if fab.get("week") != week_key():
            fab.clear()
            fab["week"], fab["output"] = week_key(), 0
        before = fab.get("output", 0)
        fab["output"] = before + fable_out
        warn_at = cfg["caps"].get("fableWeeklyOutputTokensWarn", 1500000)
        if before < warn_at <= fab["output"]:
            message = (f"tierwise: Fable output this week is {fab['output']:,} tokens, past the warning level "
                       f"({warn_at:,}). Plans may soon fall back to Opus.")
        if name in ("planner", "principal") and not info["handback"] and \
                LIMIT_TEXT.search(" ".join(info["errors"])):
            fab["exhausted"] = week_key()
            message = (f"tierwise: {name} stopped on a Fable limit. The next {name} spawn runs on "
                       f"{cfg['planner'].get('fallbackModel', 'opus')} and the ledger records it.")
        if info["handback"] and name in REVIEW_KIND and task_active(s):
            s["task"].setdefault("reviews", {})[REVIEW_KIND[name]] = time.time()
        if name == "planner" and info["handback"] and task_active(s):
            plans = sorted((os.path.join(root, ".tierwise", "plans", p) for p in
                            os.listdir(os.path.join(root, ".tierwise", "plans")) if p.endswith(".md")),
                           key=os.path.getmtime)
            if plans:
                s["task"]["plan"] = os.path.relpath(plans[-1], root)
                s["task"]["phase"] = "plan"
    ran = ", ".join(info["models"]) or "unknown model"
    surprise = ""
    if name in ("planner", "principal") and info["models"] and not any("fable" in m for m in info["models"]):
        surprise = " · NOTE: did not run on Fable"
    if name == "security-reviewer" and info["models"] and not any("opus-5" in m for m in info["models"]):
        surprise = " · NOTE: re-routed off Opus 5.5 (safety classifier?)"
    ledger(root, f"return {agent} ran on {ran} · effort {effort or '?'} · {info['output']:,} output tokens · "
                 f"{'report delivered' if info['handback'] else 'NO report'}{surprise}")
    return {"systemMessage": message} if message else None
