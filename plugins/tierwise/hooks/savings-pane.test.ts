import { expect, test } from 'claude-code/testing'
import planner from './fixtures/planner-run.js'
import { addStep, nameAgent, newTally } from './savings.js'

const PANE = {
  plugin: 'tierwise',
  component: 'Pane',
  requestId: 'tierwise-savings',
  props: { title: 'Tierwise savings', isFocused: false, bodyColumns: 100, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

function seeded() {
  let t = newTally()
  for (const s of planner.steps) {
    if (s.agentId && !(s.agentId in t.agentTypes)) t = nameAgent(t, s.agentId, s.agentType)
    t = addStep(t, s)
  }
  return t
}

test('the pane shows the session measured and against both baselines, on every surface', async ($, on) => {
  // Stored as an atom with a shape keeps it: { shape, value }.
  on('state.get', () => ({ value: { value: { shape: 'tally-1', value: seeded() }, version: 1 } }))
  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ type: 'Text', text: /^Measured: \$1\.30/ }))?.text).toBe('Measured: $1.30 · 364K tokens · 12 requests')
    expect((await ui.find({ type: 'Text', text: /all-Fable/ }))?.text).toBe('  all-Fable: $1.56–$1.62 → Tierwise saves 16–20%')
    await ui.unmount()
  }
})

test('an empty session says so', async ($) => {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /No requests/ }))?.text).toBe('No requests recorded yet.')
  await ui.unmount()
})

test('the command opens the pane', async ($, on) => {
  const opened: string[] = []
  on('ui.open', (_, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  const r = await $.command.run({ command: 'tierwise-savings', args: '', origin: { kind: 'composer' }, presentation: 'prompt' } as never)
  expect(opened).toEqual(['tierwise-savings'])
  expect(r?.text).toBe('Tierwise savings pane opened.')
})
