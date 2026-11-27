"""Per-prompt routing: class, risk tier, plan, resident effort, agents, tests, security checks.

Deterministic rules first. When they do not settle the class, the route is marked
`unclear`; the mod may then ask Haiku for a label and call `route(..., label=...)`.
"""
import re

from .common import max_tier, paths_tier, tier_at_least

CLASSES = ["question", "trivial-edit", "local-fix", "feature", "bulk", "investigation", "high-risk"]

_EXT = ("py|pyi|js|mjs|cjs|ts|tsx|jsx|go|rs|java|kt|kts|rb|php|cs|c|h|cc|cpp|hpp|swift|m|mm|scala|sql|md|rst|"
        "json|ya?ml|toml|tf|tfvars|sh|bash|zsh|ps1|html?|css|scss|sass|less|vue|svelte|txt|cfg|ini|lock|proto|"
        "graphql|gql|xml|gradle|env|dockerfile|ipynb")
_PATH = re.compile(
    r"(?<![\w@:/.-])((?:\.{1,2}/)?(?:[\w.-]+/)+[\w.-]*|[\w.-]+\.(?:" + _EXT + r")|Dockerfile[\w.-]*)(?![\w/])",
    re.IGNORECASE)
_TRACE = re.compile(
    r"Traceback \(most recent call last\)|File \"[^\"]+\", line \d+|\bat [\w$.<>]+ \(?[^\s()]+:\d+(?::\d+)?\)?|"
    r"\b\w+(?:Error|Exception):|^panic:|\bSegmentation fault\b|\berror\[E\d+\]|\bFAILED\b .*::", re.MULTILINE)

_W = lambda *words: re.compile(r"\b(?:" + "|".join(words) + r")\b", re.IGNORECASE)  # noqa: E731

EDIT_VERBS = _W("add", "implement", "create", "fix", "change", "rename", "refactor", "update", "remove", "delete",
                "move", "migrate", "write", "build", "replace", "make", "convert", "port", "split", "extract",
                "introduce", "support", "upgrade", "bump", "edit", "rewrite", "set up", "setup", "wire", "hook up")
_VERBS = ("add|implement|create|fix|change|rename|refactor|update|remove|delete|move|migrate|write|build|replace|"
          "make|convert|port|split|extract|introduce|upgrade|bump|edit|rewrite|set up|wire|hook up")
# A request phrased as an instruction: an edit verb opening a sentence, or after "please" / "can you".
IMPERATIVE = re.compile(r"(?:^|[.!?;:]\s+|\n\s*|\bplease\s+|\b(?:can|could|would|will) you\s+(?:please\s+)?)"
                        r"(?:" + _VERBS + r")\b", re.IGNORECASE)
QUESTION_START = re.compile(
    r"^\s*(?:where|what|which|how|why|who|when|is|are|does|do|did|can|could|should|explain|describe|show me|"
    r"tell me|list|find|summari[sz]e|walk me through)\b", re.IGNORECASE)
TRIVIAL = _W("rename", "typo", "typos", "spelling", "reword", "rephrase", "comment", "comments", "docstring",
             "bump (?:the )?version", "format", "reformat", "lint fix", "whitespace", "wording")
BULK = re.compile(
    r"\b(?:all|every|each)\s+(?:the\s+)?(?:files?|call ?sites?|usages?|occurrences|modules|callers|imports|tests)\b|"
    r"\b\d{2,}\s+(?:files|modules|call ?sites|usages)\b|\bacross the (?:codebase|repo(?:sitory)?|project|monorepo)\b|"
    r"\beverywhere\b|\bcodemod\b|\bmass[- ]rename\b", re.IGNORECASE)
INVESTIGATE = _W("intermittent\\w*", "flaky", "flakes", "sometimes", "randomly", "slow", "slower", "performance",
                 "latency", "memory leak", "leaks?", "deadlocks?", "race", "races", "race condition", "hangs?",
                 "hanging", "times? out", "timeouts?", "investigate", "diagnose", "root cause", "profile",
                 "performance regression", "spikes?", "throughput")
FAILURE = _W("fix", "bug", "bugs", "error", "errors", "exception", "traceback", "crash\\w*", "fails?", "failing",
             "failed", "broken", "breaks", "doesn't work", "does not work", "not working", "wrong", "incorrect")
FEATURE = _W("add", "implement", "create", "build", "support", "introduce", "new", "refactor", "redesign",
             "restructure", "extract", "rewrite", "split", "port", "migrate", "convert", "integrate", "enable")

R3_WORDS = re.compile(
    r"\b(?:auth\w*|log ?in|log ?out|sign ?in|password\w*|passwd|credentials?|secrets?|api ?keys?|tokens?|"
    r"sessions?|oauth|jwt|saml|sso|crypt\w*|encrypt\w*|decrypt\w*|signing|signature|hash(?:ing)? passwords?|"
    r"payments?|billing|invoices?|checkout|stripe|refunds?|pii|personal data|gdpr|hipaa|"
    r"terraform|kubernetes|k8s|helm|deploy\w*|infrastructure|iam|rbac|permissions?|privileges?|"
    r"drop (?:table|column|database)|delete (?:all|data|users|records)|rm -rf|truncate|production data)\b|"
    r"\b(?:table|schema|database|db|columns?|data)\b[^.]{0,40}\bmigrat\w*|\bmigrat\w*\b[^.]{0,40}\b(?:table|schema|"
    r"database|db|columns?|data)\b", re.IGNORECASE)
R2_WORDS = _W("endpoints?", "request handlers?", "handlers?", "routes?", "router", "middleware", "public api",
              "public interface", "concurren\\w*", "threads?", "threading", "locks?", "mutex", "async", "await",
              "cache", "caching", "performance", "dependenc(?:y|ies)", "upgrade", "shared", "sql", "queries",
              "deserializ\\w*", "templates?", "file paths?", "uploads?", "webhooks?")

# Effort words aimed at the main session; "pass effort low to the reviewer" is not one.
OVERRIDE_EFFORT = re.compile(r"(?:^|[.,;!]\s*|\b(?:and|then)\s+)(?:use|at|with|run at|think at)\s+(low|medium|high|xhigh|max)\b"
                             r"(?:\s+effort)?|\beffort\s*[:=]\s*(low|medium|high|xhigh|max)\b|"
                             r"(?:^|[.,;!]\s*|\buse\s+)(max|xhigh) effort\b|"
                             r"\b(?:at|with)\s+(low|medium|high|xhigh|max)(?:\s+effort)?\s*(?:[.!;]|$)", re.IGNORECASE)
OVERRIDE_NO_PLAN = re.compile(r"\b(?:no plan|skip (?:the )?plan(?:ning)?|without (?:a )?plan|don'?t plan)\b", re.I)
OVERRIDE_PLAN = re.compile(r"\b(?:make|write|with) a plan\b|\bplan (?:it|this) first\b", re.I)
OVERRIDE_NO_BUILDERS = re.compile(r"\b(?:skip|no|without) (?:the )?builders?\b", re.I)

BASE_EFFORT = {"question": "low", "trivial-edit": "low", "local-fix": "medium", "feature": "medium",
               "bulk": "medium", "investigation": "high", "high-risk": "xhigh"}
CODE_CLASSES = {"trivial-edit", "local-fix", "feature", "bulk", "investigation", "high-risk"}


def named_paths(prompt):
    out = []
    for m in _PATH.finditer(prompt or ""):
        p = m.group(1).rstrip(".,;:)")
        if p and not p.lower().startswith(("http", "www.")) and p not in out and not re.fullmatch(r"\d+(\.\d+)+", p):
            out.append(p)
    return out


# An error the requested behaviour produces ("prints an error to stderr") is a requirement, not a bug report.
SPECIFIED_ERROR = re.compile(r"\b(?:print|prints|show|shows|return|returns|raise|raises|log|logs|emit|emits|write|"
                             r"writes|output|outputs|exit|exits|fail|fails)\s+(?:with\s+)?(?:an?\s+|the\s+|a\s+clear\s+)?"
                             r"(?:error|errors|exception)(?:\s+message)?\b", re.IGNORECASE)


def rule_class(prompt, paths):
    """Class from the rules, or None when they do not settle it."""
    text = SPECIFIED_ERROR.sub(" ", prompt or "")
    edits = bool(EDIT_VERBS.search(text))
    trace = bool(_TRACE.search(text))
    words = len(text.split())
    asks = QUESTION_START.search(text) or text.rstrip().endswith("?")
    if asks and not trace and not IMPERATIVE.search(text) and \
            (not edits or QUESTION_START.search(text) and not re.match(r"\s*(?:can|could|would|will)\b", text, re.I)):
        return "question"
    if BULK.search(text):
        return "bulk"
    if TRIVIAL.search(text) and len(paths) <= 1 and words <= 30 and not FAILURE.search(text.replace("fix typo", "")):
        return "trivial-edit"
    if INVESTIGATE.search(text) and not trace:
        return "investigation"
    if FAILURE.search(text):
        if trace or 1 <= len(paths) <= 2:
            return "local-fix"
        if FEATURE.search(text) and not re.search(r"\bfix\b", text, re.I):
            return "feature"
        return "investigation"
    if FEATURE.search(text):
        return "feature"
    if not edits and QUESTION_START.search(text):
        return "question"
    return None


def prompt_tier(prompt):
    if R3_WORDS.search(prompt or ""):
        return "R3"
    if R2_WORDS.search(prompt or ""):
        return "R2"
    return None


def route(prompt, cfg, changed=(), label=None, sg_installed=None):
    """Build the route for one prompt. `changed`: files already modified in the working tree."""
    paths = named_paths(prompt)
    cls = rule_class(prompt, paths)
    source = "rules"
    if cls is None and label in CLASSES:
        cls, source = label, "model"
        # A model label alone never opens a code task: it needs a sign of a change in the prompt itself.
        if cls != "question" and not (EDIT_VERBS.search(prompt or "") or FAILURE.search(prompt or "")
                                      or paths or _TRACE.search(prompt or "")):
            cls = "question"
    unclear = cls is None
    if unclear:
        cls = "feature" if EDIT_VERBS.search(prompt or "") else "question"
        source = "default"

    # Risk tier: paths named in the prompt, files already changed, words. The prompt can raise it, never lower it.
    tier = max_tier(paths_tier(paths, cfg), paths_tier(list(changed), cfg), prompt_tier(prompt))
    if cls == "question":
        tier = tier or "R0"
    elif cls == "trivial-edit":
        tier = tier if tier in ("R2", "R3") else "R0"
    else:
        tier = max_tier(tier, "R1")
    if tier == "R3" and cls in ("feature", "local-fix", "trivial-edit"):
        cls = "high-risk"
    elif cls == "high-risk" and tier != "R3":
        # A model label of high-risk with no R3 signal in the prompt or files: raise the risk, keep it consistent.
        cls, tier = "feature", max_tier(tier, "R2")

    plan = cls in cfg.get("planner", {}).get("planClasses", [])
    if OVERRIDE_NO_PLAN.search(prompt or ""):
        plan = False
    elif OVERRIDE_PLAN.search(prompt or "") and cls in CODE_CLASSES:
        plan = True

    effort = BASE_EFFORT[cls]
    if cls == "feature" and tier_at_least(tier, "R2"):
        effort = "high"
    if tier == "R3" and cls in CODE_CLASSES:
        effort = "xhigh"
    m = OVERRIDE_EFFORT.search(prompt or "")
    effort_override = next((g.lower() for g in (m.groups() if m else ()) if g), None)
    if effort_override:
        effort = effort_override

    underspecified = cls in ("feature", "high-risk") and len((prompt or "").split()) < \
        cfg.get("classifier", {}).get("underspecifiedWords", 8)

    agents = _agents(cls, tier, plan, prompt)
    tests, security = _checks(cls, tier, paths)
    skills = _skills(cls, tier, plan, underspecified)
    pcfg = cfg.get("planner", {})
    planner_effort = "max" if effort_override == "max" else (
        pcfg.get("effortR3", "max") if tier == "R3" else pcfg.get("effort", "xhigh"))

    r = {
        "class": cls, "tier": tier, "source": source, "unclear": unclear, "plan": plan,
        "plannerEffort": planner_effort, "residentEffort": effort, "agents": agents, "tests": tests,
        "security": security, "skills": skills, "paths": paths, "underspecified": underspecified,
        "startsTask": cls in CODE_CLASSES, "effortOverride": effort_override,
    }
    r["card"] = card_text(r, sg_installed)
    return r


def _agents(cls, tier, plan, prompt):
    a = []
    if cls == "question":
        return ["scout"]
    if cls == "trivial-edit":
        return []
    if cls in ("local-fix", "feature", "bulk", "investigation", "high-risk"):
        a.append("scout")
    if cls in ("feature", "high-risk") or (cls == "investigation" and tier_at_least(tier, "R2")):
        a.append("analyst")
    if plan:
        a.append("planner")
        if tier_at_least(tier, "R2"):
            a.append("reviewer(plan)")
    if cls == "feature" and not OVERRIDE_NO_BUILDERS.search(prompt or ""):
        a.append("builder(sonnet, independent units)")
    if cls == "bulk" and not OVERRIDE_NO_BUILDERS.search(prompt or ""):
        a.append("builder(haiku, per-file check)" if not tier_at_least(tier, "R2") else "builder(sonnet)")
    if cls in ("local-fix", "investigation"):
        a.append("debugger(if checks fail twice)")
    if tier == "R1" and cls != "trivial-edit":
        a.append("reviewer(medium, final)")
    if tier == "R2":
        a += ["reviewer(high)", "security-reviewer(high)"]
    if tier == "R3":
        a += ["security-reviewer(xhigh)", "principal(xhigh review)"]
    return a


def _checks(cls, tier, paths):
    tests = []
    if cls in ("local-fix", "investigation"):
        tests += ["regression test (red-green)"]
    if cls in ("feature", "high-risk"):
        tests += ["unit", "integration at new boundaries"]
    if cls == "bulk":
        tests += ["per-file check", "full suite"]
    if cls == "trivial-edit":
        tests += ["typecheck", "affected tests"]
    if tier == "R3":
        tests += ["mutation (if available)"]
    security = ["secrets"] if cls != "question" else []
    if tier_at_least(tier, "R2") and cls != "question":
        security += ["sast"]
    if tier == "R3" and cls != "question":
        security += ["threat model (STRIDE)", "/security-review"]
    return tests, security


def _skills(cls, tier, plan, underspecified):
    """tierwise's own process skills this prompt needs (evidence-before-claims is enforced by the gate)."""
    s = []
    if cls in ("feature", "high-risk") and (underspecified or tier == "R3"):
        s.append("tierwise:brainstorm")
    if cls in ("local-fix", "investigation"):
        s.append("tierwise:root-cause")
    if cls in CODE_CLASSES:
        s.append("tierwise:tdd")
    if plan:
        s.append("tierwise:execute")
    return s


def card_text(r, sg_installed=None):
    plan = f"planner (Fable, {r['plannerEffort']})" if r["plan"] else "none"
    parts = [
        f"route: {r['class']} · {r['tier']}",
        f"plan: {plan}",
        f"resident: {r['residentEffort']}",
        "agents: " + (", ".join(r["agents"]) or "none"),
        "tests: " + (", ".join(r["tests"]) or "none"),
        "security: " + (", ".join(r["security"]) or "none"),
    ]
    if r["skills"]:
        parts.append("skills: " + ", ".join(r["skills"]))
    line = "[tierwise] " + " · ".join(parts)
    notes = []
    if r["class"] != "question":
        notes.append("Delegate only to tierwise:<agent> agents; the gate runs the checks at Stop.")
    # Other plugins' session bootstraps may ask for every skill that might apply; the card narrows that per prompt.
    notes.append(f"Use the Skill tool now, once each, for: {', '.join(r['skills'])}. Load no other process skills."
                 if r["skills"] else "No process skill is needed for this prompt.")
    if r["plan"] or any(a.split("(")[0] in ("builder", "analyst", "debugger") for a in r["agents"]):
        notes.append("Load tierwise:orchestrate before you delegate or plan.")
    if r["plan"] and r["tier"] in ("R1", "R2"):
        notes.append("You may skip the plan only for a small, fully specified change (about three files or fewer): "
                     "record `Ruling: no plan - <why>` with the state script first. The tier's reviews still run.")
    elif r["plan"] and r["tier"] == "R3":
        notes.append("R3: the plan comes first; the guard refuses your edits until tierwise:planner has written it.")
    if r["plan"] and r["plannerEffort"] != "xhigh":
        notes.append(f"Spawn tierwise:planner with effort: {r['plannerEffort']}.")
    if r["unclear"]:
        notes.append("Class was unclear; re-route in plain words if this is wrong.")
    if r["tier"] == "R3":
        notes.append("R3: recommend the user signs off before any irreversible step.")
    if sg_installed is False and r["class"] != "question":
        notes.append("Recommended: install security-guidance for per-edit security warnings.")
    return line + ("\n" + " ".join(notes) if notes else "")

