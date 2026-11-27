// Claude Code Workflow script used for the Tierwise evaluation (run with the Workflow tool).
// args.model: 'tierwise' (each agent on its own model, as evaluated), 'opus' or 'fable' (every agent on that model).
// Prompts are as run, with the plugin's name updated to Tierwise.
// Local paths are replaced by placeholders: <starting-code>, <repository>, <scratch>.
export const meta = {
  name: 'tierwise-research-single-model',
  description: 'The same research and evaluation for every approach: args.model is tierwise (each agent on its own model), opus or fable',
  whenToUse: 'Finding external skills, agents, techniques and tools worth adapting into the tierwise plugin',
  phases: [
    { title: 'Research', detail: 'four researchers on the model each angle needs: Haiku x2 (catalogues), Sonnet (tooling), Opus (techniques)' },
    { title: 'Evaluate', detail: 'two independent evaluators: Fable (value and fit), Opus (reliability and risk)' },
  ],
}

const ROOT = args.root || '<repository>'
const CONTEXT = `
You are helping improve "tierwise", a Claude Code plugin at ${ROOT}/plugins/tierwise (read its README.md and ${ROOT}/docs/INVENTORY.md first; skim bin/mlib/*.py, hooks/*.js, agents/*.md, skills/*/SKILL.md as needed).
What tierwise does: routes each prompt to a class and risk tier (R0-R3); keeps the main session on Opus and delegates to pinned-model subagents (Haiku scout, Sonnet analyst/builder, Fable planner/principal, Opus reviewers/debugger); a guard enforces model, effort, caps and report format at every spawn; a Stop-hook gate runs selected checks (tests, secret scan, scanners) and requires reviews by tier; a debugging ladder escalates on failure; a ledger keeps state; a savings panel measures cost against single-model estimates. It ships its own process skills (brainstorm, tdd, root-cause, execute, finish, terse, commit-message, debt, compress-memory).
Constraints for anything tierwise adopts: it stays an INDEPENDENT plugin (no dependency on other plugins or third-party services, nothing sends user data elsewhere), scripts are Python 3 standard library, the mod is plain JavaScript, open-source licence to be chosen (MIT or Apache-2.0), so copied code must have a compatible licence; prefer adapting ideas over copying.
Tools: use WebSearch and WebFetch (load them with ToolSearch "select:WebSearch,WebFetch" if they are not already available). For a GitHub repository's health, fetch https://api.github.com/repos/<owner>/<repo> (stars, pushed_at, license, archived). Hugging Face: https://huggingface.co/api/models?search=<q> and model or dataset pages.
Honesty rules: only report what you actually opened or saw in a search result, and say which (evidence field). Record searches you ran and any page that failed to load. Never invent stars, dates or licences: use null when unknown.`

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          url: { type: 'string' },
          source: { type: 'string', enum: ['github', 'huggingface', 'paper', 'docs', 'other'] },
          kind: { type: 'string', enum: ['skill', 'agent', 'plugin', 'tool', 'technique', 'model', 'dataset', 'workflow', 'benchmark'] },
          summary: { type: 'string' },
          tierwise_value: { type: 'string', description: 'concretely what tierwise could adopt and where it would live' },
          license: { type: ['string', 'null'] },
          stars: { type: ['number', 'null'] },
          last_activity: { type: ['string', 'null'] },
          evidence: { type: 'string', description: 'opened the page / API, or search snippet only' },
          relevance: { type: 'integer', minimum: 1, maximum: 5 },
        },
        required: ['name', 'url', 'source', 'kind', 'summary', 'tierwise_value', 'license', 'stars', 'last_activity', 'evidence', 'relevance'],
      },
    },
    searches_run: { type: 'array', items: { type: 'string' } },
    not_loaded: { type: 'array', items: { type: 'string' } },
  },
  required: ['findings', 'searches_run', 'not_loaded'],
}

const ANGLES = [
  { key: 'claude-code-ecosystem', model: 'sonnet', effort: 'low', prompt: 'Search GitHub for Claude Code plugins, skills, subagent definitions, hooks and slash-command collections (for example anthropics/skills, anthropics/claude-code plugins, awesome-claude-code style lists, popular community plugin marketplaces). Look for capabilities tierwise lacks or does worse: verification, test generation, code review, context and memory management, cost or usage tracking, safety guards, planning formats, evaluation harnesses. Aim for 8-12 findings.' },
  { key: 'orchestration-routing', model: 'opus', effort: 'high', prompt: 'Search GitHub and papers for multi-agent coding orchestration and model-routing techniques: model cascades and routers (RouteLLM, FrugalGPT, LLM routers), architect/editor splits (Aider), SWE-agent, OpenHands, Agentless, self-consistency or best-of-n with verifiers, critique/repair loops, test-time compute allocation, effort or budget controllers. Extract techniques tierwise could implement inside its own routing, ladder, guard or gate. Aim for 8-12 findings.' },
  { key: 'huggingface', model: 'sonnet', effort: 'low', prompt: 'Search Hugging Face for router or complexity-classifier models, prompt-difficulty classifiers, routing datasets and benchmarks, and coding-agent benchmarks or datasets (SWE-bench variants and similar) that tierwise could use for routing decisions or for its evaluation suite. Note size, licence, and whether it could run locally with the Python standard library alone (most cannot: then say what idea tierwise could still take, e.g. features or thresholds). Aim for 6-10 findings.' },
  { key: 'dev-tooling', model: 'sonnet', effort: 'medium', prompt: 'Search GitHub for development workflow tools and techniques tierwise could fold into its gate or skills: mutation testing, property-based testing, test-impact analysis (running only affected tests), flaky-test detection, secret scanners and SAST rule sets, prompt-caching and token-optimisation techniques for agents, context compaction strategies, structured failure dossiers. Prefer things tierwise can reimplement in Python stdlib or invoke when installed. Aim for 8-12 findings.' },
]

phase('Research')
const research = await parallel(ANGLES.map(a => () =>
  agent(`${CONTEXT}\n\nYour research angle: ${a.key}.\n${a.prompt}`,
    { label: `research: ${a.key} (${args.model === 'tierwise' ? ((args.override || {})[a.key] || a.model) : args.model})`, phase: 'Research', schema: FINDINGS, model: args.model === 'tierwise' ? ((args.override || {})[a.key] || a.model) : args.model, effort: a.effort })
    .then(r => r && { ...r, angle: a.key })))

const ok = research.filter(Boolean)
log(`${ok.length}/${ANGLES.length} researchers returned; ${ok.reduce((n, r) => n + r.findings.length, 0)} findings before de-duplication`)

// De-duplicate across all angles (needs every result: a genuine barrier), then shortlist by relevance.
const norm = u => (u || '').toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/+$/, '').replace(/\.git$/, '')
const byUrl = new Map()
for (const r of ok) for (const f of r.findings) {
  const k = norm(f.url) || f.name.toLowerCase()
  const prev = byUrl.get(k)
  if (!prev || f.relevance > prev.relevance) byUrl.set(k, { ...f, angles: [...new Set([...(prev ? prev.angles : []), r.angle])] })
  else prev.angles = [...new Set([...prev.angles, r.angle])]
}
const all = [...byUrl.values()].sort((a, b) => b.relevance - a.relevance || (b.stars || 0) - (a.stars || 0))
const SHORT = 14
const shortlist = all.slice(0, SHORT)
log(`${all.length} unique findings; shortlist of ${shortlist.length} goes to evaluation, ${Math.max(0, all.length - SHORT)} lower-relevance findings not evaluated (kept in the output)`)

const ASSESS = {
  type: 'object',
  properties: {
    assessments: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          usefulness: { type: 'integer', minimum: 1, maximum: 5 },
          compatibility: { type: 'integer', minimum: 1, maximum: 5 },
          reliability: { type: 'integer', minimum: 1, maximum: 5 },
          maintenance: { type: 'integer', minimum: 1, maximum: 5 },
          impact: { type: 'integer', minimum: 1, maximum: 5 },
          recommendation: { type: 'string', enum: ['adopt', 'adapt-idea', 'reject'] },
          integration: { type: 'string', description: 'where in tierwise and how, concretely (files, hooks, skills); empty if reject' },
          risks: { type: 'string' },
          reason: { type: 'string' },
          verified: { type: 'string', description: 'what you checked yourself (opened repo, API, read tierwise code)' },
        },
        required: ['name', 'usefulness', 'compatibility', 'reliability', 'maintenance', 'impact', 'recommendation', 'integration', 'risks', 'reason', 'verified'],
      },
    },
  },
  required: ['assessments'],
}

const LENSES = [
  { key: 'value-fit', model: 'fable', effort: 'high', prompt: 'Your lens: VALUE and FIT. For each finding, judge how much it would improve tierwise\'s results or cost, and how well it fits tierwise\'s architecture and constraints. Read the relevant tierwise code before judging fit; say which files it would touch. Be skeptical: many ideas tierwise already has in some form (check INVENTORY.md and the code) and score those low on usefulness.' },
  { key: 'reliability-risk', model: 'opus', effort: 'high', prompt: 'Your lens: RELIABILITY, MAINTENANCE and RISK. For each finding, verify the source yourself (open the repository or page; GitHub API for stars, pushed_at, licence, archived), judge whether it is maintained and trustworthy, whether its licence is compatible with an MIT or Apache-2.0 plugin if code were adapted, and what could go wrong (privacy, third-party services, heavy dependencies, unproven claims). Default to reject when a claim cannot be verified.' },
]

phase('Evaluate')
const evals = await parallel(LENSES.map(l => () =>
  agent(`${CONTEXT}\n\nIndependently assess each of these ${shortlist.length} findings for tierwise. ${l.prompt}\nScore 1-5 on every dimension (5 best; for maintenance 5 = actively maintained) and recommend adopt (take the capability, reimplemented in tierwise), adapt-idea (take the idea in a different form) or reject.\n\nFindings:\n${JSON.stringify(shortlist.map(({ name, url, kind, summary, tierwise_value, license, stars, last_activity, evidence }) => ({ name, url, kind, summary, tierwise_value, license, stars, last_activity, evidence })), null, 1)}`,
    { label: `evaluate: ${l.key} (${args.model === 'tierwise' ? l.model : args.model})`, phase: 'Evaluate', schema: ASSESS, model: args.model === 'tierwise' ? l.model : args.model, effort: l.effort })
    .then(r => r && { ...r, lens: l.key })))

const lensResults = evals.filter(Boolean)
const scored = shortlist.map(f => {
  const views = lensResults.map(l => ({ lens: l.lens, a: l.assessments.find(x => x.name.toLowerCase() === f.name.toLowerCase()) })).filter(v => v.a)
  const dims = ['usefulness', 'compatibility', 'reliability', 'maintenance', 'impact']
  const avg = d => views.length ? views.reduce((s, v) => s + v.a[d], 0) / views.length : 0
  const scores = Object.fromEntries(dims.map(d => [d, Math.round(avg(d) * 10) / 10]))
  const total = Math.round(dims.reduce((s, d) => s + scores[d], 0) * 10) / 10
  const recs = views.map(v => v.a.recommendation)
  const agreed = recs.length === 2 && recs[0] === recs[1]
  return { ...f, scores, total, recommendations: Object.fromEntries(views.map(v => [v.lens, v.a.recommendation])), agreed,
    integration: views.map(v => `[${v.lens}] ${v.a.integration}`).filter(s => !s.endsWith('] ')),
    risks: views.map(v => `[${v.lens}] ${v.a.risks}`), reasons: views.map(v => `[${v.lens}] ${v.a.reason}`) }
}).sort((a, b) => b.total - a.total)
log(`evaluated ${scored.length}; both evaluators agree on ${scored.filter(s => s.agreed).length}; adopt or adapt by both: ${scored.filter(s => s.agreed && s.recommendations['value-fit'] !== 'reject').length}`)

return {
  shortlist: scored,
  unevaluated: all.slice(SHORT).map(({ name, url, kind, relevance, tierwise_value }) => ({ name, url, kind, relevance, tierwise_value })),
  searches: ok.map(r => ({ angle: r.angle, searches_run: r.searches_run, not_loaded: r.not_loaded, found: r.findings.length })),
}
