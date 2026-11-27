// Claude Code Workflow script used for the Tierwise evaluation (run with the Workflow tool).
// args.model: 'tierwise' (each agent on its own model, as evaluated), 'opus' or 'fable' (every agent on that model).
// Prompts are as run, with the plugin's name updated to Tierwise.
// Local paths are replaced by placeholders: <starting-code>, <repository>, <scratch>.
export const meta = {
  name: 'tierwise-integrate-single-model',
  description: 'The same build for every approach, on its own copy of the plugin: args.model is tierwise (each agent on its own model), opus or fable',
  whenToUse: 'Integrating evaluated improvements into the tierwise plugin with independent testing and review',
  phases: [
    { title: 'Implement', detail: 'four units in sequence (shared files): Opus, Sonnet, Opus, Sonnet' },
    { title: 'Test', detail: 'Haiku runs all suites and digests the results', model: 'haiku' },
    { title: 'Review', detail: 'Opus reviews the diff against a snapshot, fresh context', model: 'opus' },
    { title: 'Fix', detail: 'Opus fixes confirmed findings; Haiku re-tests (at most two rounds)' },
  ],
}

const P = args.plugin
const SNAP = '<starting-code>'
const COMMON = `You are changing the tierwise Claude Code plugin at ${P} (read README.md and the files named below first). Rules: Python 3.8+ standard library only (no tomllib without a fallback, no third-party packages); the mod is plain JavaScript; keep the code's existing style and structure; write tests for every behaviour you add (Python: unittest in ${P}/tests, run with "cd ${P}/../.. && python3 -m unittest discover -s plugins/tierwise/tests"; mod: *.test.ts beside hooks, run with "claude plugin test ${P}"). Run the Python suite before you finish and make it pass. Do not touch files owned by other units unless your unit says so. Never run git commands that change state (this folder is not a git repository). Your final message: what you changed (files), the tests you added, and the test command results.`

const UNITS = [
  { key: 'checks', model: 'opus', effort: 'high', prompt: `UNIT 1 (you own bin/mlib/checks.py and a new tests/test_checks_research.py).
1. Built-in syntax check, id "syntax", command "builtin:syntax": select() adds it first whenever code or config files changed. For each changed file that exists and is under 2 MB: .py -> compile(source, path, "exec") in-process (never py_compile; no __pycache__); .json -> json.loads; .toml -> tomllib only if importable (Python 3.11+), otherwise skip; .js/.mjs/.cjs -> "node --check <file>" only when shutil.which("node"), otherwise skip. Failure output lists "path:line: message" per broken file. A file that does not parse fails the check.
2. Secrets: the built-in scan always runs as id "secrets" (cmd "builtin:secrets"), whatever detect() finds. Remove detect()'s gitleaks entry (its "protect --staged" scans only staged files, and tierwise never stages, so it silently disabled scanning). Add a Shannon-entropy filter (stdlib math) to the "assigned-secret" pattern: require entropy >= 3.0 bits per character of the captured value, on top of the placeholder filter. Support user rules from config: cfg["secrets"] = {"rules": [{"id", "regex", "minEntropy" optional}], "allow": {"paths": [globs], "regexes": [patterns]}}; user rules add to the built-in ones; an allowlisted hit is not a failure but is listed in the output as "allowed: ...". Use glob_match from common.py for paths.
3. Changed files for check commands: run_selected() exports TIERWISE_CHANGED_FILES (newline-separated relative paths) in the environment of every command check.
4. Optional fast check, id "affected": when cfg["checks"]["affected"] is set and code or tests changed, select() adds it just before "unit". In run_selected(), when "syntax" or "affected" fails, the remaining non-security checks after it are not run and get status "skipped" with reason "an earlier check failed" ("secrets" always runs). summary() prints SKIPPED lines.
Keep select()'s existing behaviour otherwise; update existing tests only where the behaviour above changes them.` },
  { key: 'gate', model: 'sonnet', effort: 'medium', prompt: `UNIT 2 (you own bin/mlib/flow.py, templates/tierwise.json and a new tests/test_flow_research.py). Unit 1 already added checks "syntax", "affected" (optional), status "skipped", and rules for secrets in bin/mlib/checks.py; read it.
1. In gate(): failures of "syntax" or "secrets" do not count toward the debugging ladder (they do not raise task attempts or the rung). The block message for them says what to do instead of a ladder rung: syntax -> "fix the file named"; secrets -> "remove the secret, or allowlist it in .claude/tierwise.json under secrets.allow if it is not one". Other failing checks keep the ladder as now. A "skipped" check is neither a pass nor a failure.
2. Escalation audit: whenever the rung goes up, write a ledger line "ladder: task <id> rung <old> -> <new> on <failed check ids>: <the action RUNG_ACTION names, first sentence>".
3. templates/tierwise.json: add "affected": null to checks, a "secrets": {"rules": [], "allow": {"paths": [], "regexes": []}} block, and caps.taskBudgetUsd: 25 (list-price equivalent USD of one task; null turns it off).
Tests for each.` },
  { key: 'budget', model: 'opus', effort: 'high', prompt: `UNIT 3 (you own hooks/savings.js, hooks/register.js, bin/mlib/guard.py and their tests). Add a per-task usage cap.
1. The mod already prices every request (hooks/savings.js addStep/cost; hooks/register.js record()). Add to savings.js a pure function that adds one priced request to a per-task usage record {taskId: {cost, tokens, requests}} (returns a new object; never mutates). In register.js record(): read the active task id from .tierwise/state.json (readState already exists) and, when there is one, update and write ${'$'}{root}/.tierwise/usage.json (read it first if it exists; keep other tasks' entries). Failures must never break a turn.
2. bin/mlib/guard.py pre_agent: for spawns of tierwise:planner, tierwise:principal and tierwise:debugger, when the active task's usage in .tierwise/usage.json is at or above cfg["caps"]["taskBudgetUsd"] (skip when null or the file is missing), deny with a reason telling the main session to stop and ask the user, stating usage and cap in list-price-equivalent dollars ("on a subscription this is usage of your limits, not a bill"). Scouts, analysts, builders and reviewers stay allowed: the cap stops escalation, not verification.
3. Tests: a mod test for the pure function (in hooks/savings.test.ts or a new hooks/usage.test.ts) and Python tests for the guard (new tests/test_budget_research.py).
Unit 2 adds caps.taskBudgetUsd = 25 to templates/tierwise.json; read it with load_config.` },
  { key: 'docs', model: 'sonnet', effort: 'medium', prompt: `UNIT 4 (you own skills/execute/SKILL.md, templates/dossier.md, templates/brief.md, skills/orchestrate/reference/checks.md, README.md). Text only; keep skills short (the consistency test fails a skill body over 100 lines) and in the same plain style.
1. skills/execute/SKILL.md fix loop: rounds 1-2 go back to the same builder (SendMessage); rounds 3-5 go to a fresh builder from a short failure summary, one model up from round 4. Reason in one clause: success decays after two or three attempts in one context.
2. templates/dossier.md: add a line stating whether the failed attempts are still applied in the working tree or were reverted (with the diff or commit), and the rule "one line per attempt; no patch bodies or transcripts".
3. templates/brief.md: add a "Plan unit" line (plan path and unit number: read its behaviour, interfaces and steps) and an optional "Approach" (two sentences on where and how to change the code, filled by the main session at R2 and above when there is no plan unit).
4. skills/orchestrate/reference/checks.md and README.md: document the syntax check, the always-on built-in secret scan with entropy filter, secrets.rules and secrets.allow in .claude/tierwise.json, the optional "affected" check with TIERWISE_CHANGED_FILES, skipped checks, caps.taskBudgetUsd (stops planner, principal and debugger spawns and asks the user; needs the mod), and the ledger's ladder audit line. Add to README Credits one line naming the sources of these ideas: SWE-agent's lint-on-edit interface, Gitleaks' rule format, Agentless's test selection, the debugging-decay study (arXiv 2506.18403), Aider's architect/editor split, and a review of routing versus cascades. No code from them is included.` },
]

phase('Implement')
const done = []
for (const u of UNITS) {
  const r = await agent(`${COMMON}\n\n${u.prompt}`, { label: `implement: ${u.key} (${args.model === 'tierwise' ? ((args.override || {})[u.key] || u.model) : args.model})`, phase: 'Implement', model: args.model === 'tierwise' ? ((args.override || {})[u.key] || u.model) : args.model, effort: u.effort })
  done.push({ unit: u.key, report: r })
  log(`unit ${u.key} finished`)
}

const TEST = {
  type: 'object',
  properties: {
    python: { type: 'object', properties: { ok: { type: 'boolean' }, ran: { type: 'integer' }, digest: { type: 'string' } }, required: ['ok', 'ran', 'digest'] },
    mod: { type: 'object', properties: { ok: { type: 'boolean' }, ran: { type: 'integer' }, digest: { type: 'string' } }, required: ['ok', 'ran', 'digest'] },
    validate: { type: 'object', properties: { ok: { type: 'boolean' }, digest: { type: 'string' } }, required: ['ok', 'digest'] },
  },
  required: ['python', 'mod', 'validate'],
}
const testPrompt = `Run these three commands from ${P}/../.. and report each result exactly (counts, and for failures the failing test names and the first error lines). Change nothing.
1. python3 -W error::ResourceWarning -m unittest discover -s plugins/tierwise/tests
2. claude plugin test plugins/tierwise
3. claude plugin validate plugins/tierwise
Then delete any __pycache__ folders under plugins/tierwise.`
const runTests = (label) => agent(testPrompt, { label, phase: 'Test', schema: TEST, model: args.model === 'tierwise' ? 'haiku' : args.model, effort: 'low' })

phase('Test')
let tests = await runTests(`test: all suites (${args.model})`)

const REVIEW = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      file: { type: 'string' }, line: { type: 'integer' }, severity: { type: 'string', enum: ['Critical', 'Important', 'Minor'] },
      problem: { type: 'string' }, failing_case: { type: 'string' }, fix: { type: 'string' } },
      required: ['file', 'line', 'severity', 'problem', 'failing_case', 'fix'] } },
    verdict: { type: 'string', enum: ['ready', 'fix first'] },
    summary: { type: 'string' },
  },
  required: ['findings', 'verdict', 'summary'],
}
phase('Review')
const reviewPrompt = (scope) => `You are reviewing a change to the tierwise plugin in a fresh context. Compare the current plugin with the snapshot taken before the change: run "diff -ru ${SNAP} ${P} -x __pycache__ -x .claude-plugin" (read-only; change nothing). The change implemented these four units:\n${UNITS.map(u => u.prompt).join('\n\n')}\n\nTest results: ${JSON.stringify(tests)}\n\n${scope}\nCheck in order: correct (does each unit do what it says, edge cases, broken callers), safe (could a secret slip through that used to be caught? could a check now pass that should fail?), holds up (timeouts, large files), tested (is each behaviour covered), lean. Every finding needs a concrete failing case; no style findings; zero findings is a valid result. Severity: Critical (wrong result, a security regression), Important (fix before shipping), Minor.`
let review = await agent(reviewPrompt('Review the whole change.'), { label: `review: whole diff (${args.model})`, phase: 'Review', schema: REVIEW, model: args.model === 'tierwise' ? 'opus' : args.model, effort: 'high' })

phase('Fix')
let round = 0
const blocking = () => (review ? review.findings.filter(f => f.severity !== 'Minor') : [])
while (round < 2 && (blocking().length > 0 || !(tests && tests.python.ok && tests.mod.ok && tests.validate.ok))) {
  round += 1
  const items = blocking()
  log(`fix round ${round}: ${items.length} blocking finding(s), tests ${tests && tests.python.ok && tests.mod.ok ? 'pass' : 'FAIL'}`)
  await agent(`${COMMON}\n\nFix round ${round}. Check each finding against the code before changing anything; fix the real ones at the root, one at a time, each with a test; if a finding is wrong, say why in your final message instead of changing code. Also make every failing test pass.\nFindings:\n${JSON.stringify(items, null, 1)}\nTest results:\n${JSON.stringify(tests)}`,
    { label: `fix: round ${round} (${args.model === 'tierwise' ? ((args.override || {}).fix || 'opus') : args.model})`, phase: 'Fix', model: args.model === 'tierwise' ? ((args.override || {}).fix || 'opus') : args.model, effort: 'high' })
  tests = await runTests(`test: after fix ${round} (${args.model})`)
  review = await agent(reviewPrompt(`Review only whether these earlier findings are now fixed, and anything the fix itself broke: ${JSON.stringify(items)}`),
    { label: `review: fix ${round} (${args.model})`, phase: 'Fix', schema: REVIEW, model: args.model === 'tierwise' ? 'opus' : args.model, effort: 'medium' })
}

return { units: done, tests, review, fixRounds: round }
