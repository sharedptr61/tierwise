// tierwise's savings accounting. Pure functions over plain JSON, so tests can drive them directly.
//
// Measured: every request the session makes (main session and every subagent), priced at list price for
// the model that served it, from the usage the API reported. On a subscription this is usage of your plan's
// limits expressed in dollars, not a bill.
//
// Estimated: what the same work would have cost done in ONE session on one model, given as a range.
//   low  = the same tokens at that model's prices, without each subagent's start-up context
//   high = low, plus what one growing session really pays: each subagent request re-reads the main
//          context, and what subagents read and wrote stays in context for every later main request.
// Not modelled: a different model's thinking length, retries or success rate.

// USD per million tokens: input, output, cache read. Claude API list prices, as cached on PRICES_AS_OF.
export const PRICES = {
  fable: [8, 40, 0.2],
  opus: [4, 20, 0.2],
  sonnet: [2, 10, 0.1],
  haiku: [0.1, 0.5, 0.01],
}
export const HAIKU_OVER_100K = [0.5, 2.5, 0.05]
export const PRICES_AS_OF = '2026-11-03'
export const NAMES = { fable: 'Fable', opus: 'Opus', sonnet: 'Sonnet', haiku: 'Haiku' }

export function family(model) {
  return Object.keys(PRICES).find((f) => String(model ?? '').includes(f))
}

export function parts(u = {}) {
  const w1 = u.ephemeral_1h_input_tokens ?? 0
  const written = u.cache_creation_input_tokens ?? (u.ephemeral_5m_input_tokens ?? 0) + w1
  return {
    input: u.input_tokens ?? 0,
    read: u.cache_read_input_tokens ?? 0,
    write5m: Math.max(written - w1, 0),
    write1h: w1,
    output: u.output_tokens ?? 0,
  }
}

const ZERO = () => ({ input: 0, read: 0, write5m: 0, write1h: 0, output: 0 })

function add(a, b) {
  for (const k of Object.keys(a)) a[k] += b[k]
  return a
}

export function tokens(p) {
  return p.input + p.read + p.write5m + p.write1h + p.output
}

// writeMult undefined: bill writes as recorded (5-minute 1.25x, 1-hour 2x); a number: bill all writes at it.
export function cost(p, fam, writeMult) {
  const base = PRICES[fam]
  if (!base) return 0
  const prompt = p.input + p.read + p.write5m + p.write1h
  const [i, o, r] = fam === 'haiku' && prompt > 100_000 ? HAIKU_OVER_100K : base
  const writes = writeMult === undefined ? p.write5m * 1.25 + p.write1h * 2 : (p.write5m + p.write1h) * writeMult
  return (p.input * i + p.read * r + writes * i + p.output * o) / 1e6
}

export function newTally() {
  return {
    requests: 0,
    mainFamily: undefined,
    mainSteps: 0,
    mainCtx: 0,
    main: ZERO(),
    byModel: {},
    byRole: {},
    agents: {},
    agentTypes: {},
  }
}

// Record one request. agentId undefined means the main session. Returns a new tally (input untouched).
export function addStep(tally, { agentId, model, usage }) {
  const t = JSON.parse(JSON.stringify(tally))
  const p = parts(usage)
  const fam = family(model) ?? 'other'
  const c = cost(p, fam)
  const n = tokens(p)
  t.requests += 1
  const m = (t.byModel[fam] ??= { requests: 0, cost: 0, tokens: 0, output: 0 })
  m.requests += 1
  m.cost += c
  m.tokens += n
  m.output += p.output
  const role = agentId ? (t.agentTypes[agentId] ?? 'other agent') : 'main session'
  const r = (t.byRole[role] ??= { requests: 0, cost: 0, tokens: 0 })
  r.requests += 1
  r.cost += c
  r.tokens += n
  if (!agentId) {
    t.mainFamily = fam
    t.mainSteps += 1
    t.mainCtx = p.input + p.read + p.write5m + p.write1h
    add(t.main, p)
    return t
  }
  const a = (t.agents[agentId] ??= {
    requests: 0,
    rest: ZERO(),
    content: 0,
    mainCtxAtStart: t.mainCtx,
    mainStepsAtEnd: t.mainSteps,
  })
  if (a.requests === 0) {
    a.rest.output += p.output // its start-up prompt is what one session would not have needed
  } else {
    add(a.rest, p)
    a.content += p.write5m + p.write1h
  }
  a.content += p.output
  a.requests += 1
  a.mainStepsAtEnd = t.mainSteps
  return t
}

// Add one priced request to a per-task usage record, { taskId: { cost, tokens, requests } }, which the mod
// keeps in .tierwise/usage.json for the spawn guard's task budget. Returns a new record (input untouched).
export function addTaskUsage(record, taskId, { model, usage }) {
  const isRecord = (x) => x !== null && typeof x === 'object' && !Array.isArray(x)
  const r = isRecord(record) ? JSON.parse(JSON.stringify(record)) : {}
  const p = parts(usage)
  const prev = isRecord(r[taskId]) ? r[taskId] : {}
  r[taskId] = {
    cost: (Number(prev.cost) || 0) + cost(p, family(model) ?? 'other'),
    tokens: (Number(prev.tokens) || 0) + tokens(p),
    requests: (Number(prev.requests) || 0) + 1,
  }
  return r
}

export function nameAgent(tally, agentId, type) {
  const t = JSON.parse(JSON.stringify(tally))
  t.agentTypes[agentId] = type
  return t
}

function mainWriteMult(t) {
  const w = t.main.write5m + t.main.write1h
  return w ? (t.main.write5m * 1.25 + t.main.write1h * 2) / w : 2
}

export function summarize(t) {
  const measured = {
    cost: Object.values(t.byModel).reduce((s, m) => s + m.cost, 0),
    tokens: Object.values(t.byModel).reduce((s, m) => s + m.tokens, 0),
    requests: t.requests,
  }
  const agents = Object.values(t.agents)
  const sameTokens = tokens(t.main) + agents.reduce((s, a) => s + tokens(a.rest), 0)
  const oneSessionExtra = agents.reduce(
    (s, a) => s + a.requests * a.mainCtxAtStart + a.content * Math.max(t.mainSteps - a.mainStepsAtEnd, 0),
    0,
  )
  const W = mainWriteMult(t)
  const baselines = {}
  for (const fam of ['opus', 'fable']) {
    const low = cost(t.main, fam, W) + agents.reduce((s, a) => s + cost(a.rest, fam, W), 0)
    const high = low + (oneSessionExtra * PRICES[fam][2]) / 1e6
    baselines[fam] = { low, high, savingLow: low - measured.cost, savingHigh: high - measured.cost }
  }
  return {
    measured,
    byModel: t.byModel,
    byRole: t.byRole,
    agentCount: agents.length,
    mainFamily: t.mainFamily,
    tokensOneSession: { low: sameTokens, high: sameTokens + oneSessionExtra },
    baselines,
  }
}

export function money(x) {
  return x >= 100 ? `$${x.toFixed(0)}` : `$${x.toFixed(2)}`
}

export function compact(n) {
  return n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : `${Math.round(n)}`
}

// The verdict against one baseline, never rounding a loss into a saving.
export function verdict(b) {
  const pct = (s, base) => (base > 0 ? Math.round((s / base) * 100) : 0)
  const lo = pct(b.savingLow, b.low)
  const hi = pct(b.savingHigh, b.high)
  const range = (x, y) => (x === y ? `~${x}%` : `${Math.min(x, y)}–${Math.max(x, y)}%`)
  if (lo >= 0 && hi >= 0) return `saves ${range(lo, hi)}`
  if (lo < 0 && hi < 0) return `costs ${range(-lo, -hi)} more`
  return `saves between ${Math.min(lo, hi)}% and ${Math.max(lo, hi)}% (too close to call)`
}

export function statusLine(s, baseline) {
  if (!s.measured.requests) return undefined
  const fam = baseline === 'main' || !baseline ? s.mainFamily ?? 'opus' : baseline
  const b = s.baselines[fam]
  const measured = `Tierwise ${money(s.measured.cost)} measured`
  if (!b) return measured
  if (s.agentCount === 0 && fam === s.mainFamily) return `${measured} · no delegation yet`
  return `${measured} · all-${NAMES[fam]} est. ${money(b.low)}–${money(b.high)} · ${verdict(b)}`
}

// The panel, as lines of text. `strong` marks headings, `dim` marks notes.
export function panelLines(s) {
  const lines = [
    { text: 'Tierwise savings · this session', strong: true },
    { text: `List-price equivalent (prices of ${PRICES_AS_OF}). On a subscription this is usage of your plan's limits, not a bill.`, dim: true },
  ]
  if (!s.measured.requests) return [...lines, { text: 'No requests recorded yet.', dim: true }]
  const m = s.measured
  lines.push({ text: '' }, { text: `Measured: ${money(m.cost)} · ${compact(m.tokens)} tokens · ${m.requests} requests`, strong: true })
  lines.push({ text: 'By model', strong: true })
  const models = Object.entries(s.byModel).sort((a, b) => b[1].cost - a[1].cost)
  for (const [fam, x] of models) {
    const share = m.cost ? x.cost / m.cost : 0
    const bar = '█'.repeat(Math.round(share * 12)).padEnd(12, '·')
    lines.push({
      text: `  ${(NAMES[fam] ?? fam).padEnd(7)} ${money(x.cost).padStart(7)}  ${bar} ${Math.round(share * 100)}% of cost · ${compact(x.tokens)} tokens (${Math.round((x.tokens / m.tokens) * 100)}%) · ${x.requests} req`,
    })
  }
  lines.push({ text: 'By agent', strong: true })
  for (const [role, x] of Object.entries(s.byRole).sort((a, b) => b[1].cost - a[1].cost)) {
    lines.push({ text: `  ${role.padEnd(26)} ${money(x.cost).padStart(7)} · ${compact(x.tokens)} tokens · ${x.requests} req` })
  }
  lines.push({ text: '' }, { text: 'Estimated: the same work on one model, in one session', strong: true })
  for (const fam of ['opus', 'fable']) {
    const b = s.baselines[fam]
    const mine = fam === s.mainFamily ? ' (your main model)' : ''
    lines.push({ text: `  all-${NAMES[fam]}${mine}: ${money(b.low)}–${money(b.high)} → Tierwise ${verdict(b)}` })
  }
  lines.push({
    text: `  Tokens: ${compact(m.tokens)} measured · one session est. ${compact(s.tokensOneSession.low)}–${compact(s.tokensOneSession.high)}`,
  })
  lines.push(
    { text: '' },
    { text: 'How the estimate works', strong: true },
    { text: '  "The same work" means one model doing everything Tierwise did here, reviews included.', dim: true },
    { text: '  Low end: the same tokens at that model\'s prices, without the start-up context of each subagent.', dim: true },
    { text: '  High end: also what one growing session re-reads: the main context for each subagent request,', dim: true },
    { text: '  and everything subagents read and wrote, again on every later request.', dim: true },
    { text: '  Not modelled: another model\'s thinking length, retries or success rate.', dim: true },
  )
  return lines
}
