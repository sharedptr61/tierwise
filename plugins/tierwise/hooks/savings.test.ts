import { expect, test } from 'claude-code/testing'
import bugfix from './fixtures/bugfix-run.js'
import planner from './fixtures/planner-run.js'
import { addStep, addTaskUsage, cost, nameAgent, newTally, panelLines, parts, statusLine, summarize, verdict } from './savings.js'

function replay(run) {
  let t = newTally()
  for (const s of run.steps) {
    if (s.agentId && !(s.agentId in t.agentTypes)) t = nameAgent(t, s.agentId, s.agentType)
    t = addStep(t, s)
  }
  return summarize(t)
}

test('measured cost reproduces what Claude Code reported for real runs', async () => {
  for (const run of [planner, bugfix]) {
    const s = replay(run)
    expect(Math.abs(s.measured.cost - run.reportedCostUsd) < 0.001).toBe(true)
  }
})

test('model and role breakdowns add up to the total', async () => {
  const s = replay(planner)
  expect(Object.keys(s.byModel).sort()).toEqual(['fable', 'haiku', 'opus'])
  const byModel = Object.values(s.byModel).reduce((a, m) => a + m.cost, 0)
  const byRole = Object.values(s.byRole).reduce((a, r) => a + r.cost, 0)
  expect(Math.abs(byModel - s.measured.cost) < 1e-9).toBe(true)
  expect(Math.abs(byRole - s.measured.cost) < 1e-9).toBe(true)
  expect(Object.keys(s.byRole).sort()).toEqual(['main session', 'tierwise:planner', 'tierwise:scout'])
  expect(s.agentCount).toBe(2)
})

test('baseline ranges are ordered and the one-session end adds re-reads', async () => {
  for (const run of [planner, bugfix]) {
    const s = replay(run)
    for (const fam of ['opus', 'fable']) {
      const b = s.baselines[fam]
      expect(b.low <= b.high).toBe(true)
      expect(b.low > 0).toBe(true)
    }
    expect(s.baselines.fable.low > s.baselines.opus.low).toBe(true)
    expect(s.tokensOneSession.low <= s.tokensOneSession.high).toBe(true)
  }
})

test('a session with no subagents equals its own single-model baseline', async () => {
  const mainOnly = { steps: bugfix.steps.filter((s) => !s.agentId) }
  const s = replay(mainOnly)
  const b = s.baselines.opus
  expect(Math.abs(b.low - s.measured.cost) < 1e-9).toBe(true)
  expect(Math.abs(b.high - s.measured.cost) < 1e-9).toBe(true)
  expect(statusLine(s, 'main')).toBe(`Tierwise $${s.measured.cost.toFixed(2)} measured · no delegation yet`)
  expect(statusLine(s, 'fable')?.includes('all-Fable est.')).toBe(true)
})

test('real runs: the Fable plan costs more than all-Opus, less than all-Fable', async () => {
  // Measured $1.30: Opus main session, Haiku scout, Fable planner.
  const s = replay(planner)
  expect(s.baselines.opus.savingLow < 0 && s.baselines.opus.savingHigh < 0).toBe(true)
  expect(s.baselines.fable.savingLow > 0 && s.baselines.fable.savingHigh > 0).toBe(true)
  expect(statusLine(s, 'main')).toBe('Tierwise $1.30 measured · all-Opus est. $0.81–$0.87 · costs 49–62% more')
  expect(statusLine(s, 'fable')).toBe('Tierwise $1.30 measured · all-Fable est. $1.56–$1.62 · saves 16–20%')
  // Same work on one Opus session, review included, would have cost a little more than tierwise's $0.37.
  expect(statusLine(replay(bugfix), 'main')).toBe('Tierwise $0.37 measured · all-Opus est. $0.38–$0.41 · saves 2–10%')
})

test('verdict wording never turns a loss into a saving', async () => {
  expect(verdict({ low: 10, high: 12, savingLow: -1, savingHigh: -2 })).toBe('costs 10–17% more')
  expect(verdict({ low: 10, high: 12, savingLow: 2, savingHigh: 4 })).toBe('saves 20–33%')
  expect(verdict({ low: 10, high: 12, savingLow: -1, savingHigh: 2 })).toBe('saves between -10% and 17% (too close to call)')
})

test('cache writes are billed by their lifetime, and long Haiku prompts at the higher rate', async () => {
  const p = parts({ input_tokens: 0, cache_creation_input_tokens: 1000, ephemeral_5m_input_tokens: 400, ephemeral_1h_input_tokens: 600, output_tokens: 0 })
  expect(Math.abs(cost(p, 'opus') - (400 * 1.25 + 600 * 2) * 4 / 1e6) < 1e-12).toBe(true)
  const long = parts({ input_tokens: 0, cache_read_input_tokens: 150_000, output_tokens: 1000 })
  expect(Math.abs(cost(long, 'haiku') - (150_000 * 0.05 + 1000 * 2.5) / 1e6) < 1e-12).toBe(true)
  expect(cost(parts({ output_tokens: 1000 }), 'unknown')).toBe(0)
})

test('recording never changes the tally it was given', async () => {
  const t = newTally()
  addStep(t, { model: 'claude-opus-5-5', usage: { output_tokens: 5 } })
  expect(t.requests).toBe(0)
})

test('the panel shows measured figures, both baselines and the method', async () => {
  const text = panelLines(replay(planner)).map((l) => l.text).join('\n')
  expect(text.includes('Measured: $1.30')).toBe(true)
  expect(text.includes('all-Opus (your main model): $0.81–$0.87 → Tierwise costs 49–62% more')).toBe(true)
  expect(text.includes('all-Fable: $1.56–$1.62 → Tierwise saves 16–20%')).toBe(true)
  expect(text.includes('tierwise:planner')).toBe(true)
  expect(text.includes('reviews included')).toBe(true)
  expect(panelLines(summarize(newTally())).at(-1)?.text).toBe('No requests recorded yet.')
})

test('task usage adds each priced request to its task and keeps the others', async () => {
  const step = { model: 'claude-opus-5-5', usage: { input_tokens: 1000, cache_read_input_tokens: 2000, output_tokens: 500 } }
  const price = cost(parts(step.usage), 'opus')
  const before = { t1: { cost: 1, tokens: 10, requests: 2 } }
  const once = addTaskUsage(before, 't2', step)
  expect(once.t1).toEqual({ cost: 1, tokens: 10, requests: 2 })
  expect(once.t2).toEqual({ cost: price, tokens: 3500, requests: 1 })
  const twice = addTaskUsage(once, 't1', step)
  expect(Math.abs(twice.t1.cost - (1 + price)) < 1e-12).toBe(true)
  expect(twice.t1.tokens).toBe(3510)
  expect(twice.t1.requests).toBe(3)
  expect(before).toEqual({ t1: { cost: 1, tokens: 10, requests: 2 } }) // never mutated
  expect(once.t1.requests).toBe(2)
})

test('task usage prices each request by its own model and starts over from a bad record', async () => {
  const usage = { output_tokens: 1000 }
  expect(addTaskUsage({}, 't', { model: 'claude-fable-5', usage }).t.cost).toBe(0.04)
  expect(addTaskUsage(undefined, 't', { model: 'claude-haiku-5', usage }).t.cost).toBe(0.0005)
  expect(addTaskUsage([], 't', { model: 'unknown', usage }).t).toEqual({ cost: 0, tokens: 1000, requests: 1 })
  expect(addTaskUsage({ t: 'junk' }, 't', { model: 'claude-opus-5-5', usage }).t.requests).toBe(1)
})
