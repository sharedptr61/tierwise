import { expect, test } from 'claude-code/testing'
import { activeTaskId } from './register.js'

const ROOT = '/repo'
const STATE = `${ROOT}/.tierwise/state.json`
const USAGE = `${ROOT}/.tierwise/usage.json`
const OPUS_1K_OUT = { model: 'claude-opus-5-5', input_tokens: 0, output_tokens: 1000 } // $0.02 at Opus prices

// A project held in memory: answers the mod's file reads and writes, and routes a prompt to ROOT.
function project(on, files: Record<string, string>, opts: { failWrites?: boolean } = {}) {
  const writes: string[] = []
  const logs: string[] = []
  on('prompt.submit', (_, e) => ({ text: e.text }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.log', (_, e) => {
    logs.push(JSON.stringify(e))
    return { value: undefined }
  })
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify({ root: ROOT, card: 'tierwise: route' }), stderr: '' } }))
  on('fs.exists', (_, e) => ({ value: e.path in files }))
  on('fs.read', (_, e) => {
    if (!(e.path in files)) throw new Error(`read ${e.path} failed: ENOENT`)
    return { value: files[e.path] }
  })
  on('fs.write', (_, e) => {
    if (opts.failWrites) throw new Error('write failed: EACCES')
    files[e.path] = e.text
    writes.push(e.path)
    return { value: undefined }
  })
  on('turn.step', async function* (_, e) {
    return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'end_turn', usage: OPUS_1K_OUT }
  })
  return { writes, logs }
}

async function route($) {
  await $.prompt.submit({ text: 'Add a CSV exporter', origin: { kind: 'composer' } } as never)
}

async function step($, agentId?: string) {
  const s = $.turn.step({ turnId: 'turn-1', index: 0, model: 'claude-opus-5-5', messageCount: 1, ...(agentId ? { agentId } : {}) })
  for (;;) {
    const n = await s.next()
    if (n.done) return n.value
  }
}

const state = (task) => JSON.stringify({ task })

test('the active task is the one task_active() sees', async () => {
  expect(activeTaskId({ task: { id: 't1', phase: 'build' } })).toBe('t1')
  expect(activeTaskId({ task: { id: 't1', phase: 'closed' } })).toBe(undefined)
  expect(activeTaskId({ task: { id: 't1' } })).toBe(undefined)
  expect(activeTaskId({})).toBe(undefined)
})

test('each request, main or subagent, is added to the active task in usage.json; other tasks are kept', async ($, on) => {
  const files = { [STATE]: state({ id: 't2', phase: 'build' }), [USAGE]: JSON.stringify({ t1: { cost: 3, tokens: 9, requests: 1 } }) }
  project(on, files)
  await route($)
  await step($)
  await step($, 'agent-1')
  const usage = JSON.parse(files[USAGE])
  expect(usage.t1).toEqual({ cost: 3, tokens: 9, requests: 1 })
  expect(usage.t2).toEqual({ cost: 0.04, tokens: 2000, requests: 2 })
})

test('usage.json is created on the first request of a task', async ($, on) => {
  const files = { [STATE]: state({ id: 't1', phase: 'plan' }) }
  project(on, files)
  await route($)
  await step($)
  expect(JSON.parse(files[USAGE])).toEqual({ t1: { cost: 0.02, tokens: 1000, requests: 1 } })
})

test('nothing is written without an active task or a routed project', async ($, on) => {
  const { writes } = project(on, { [STATE]: state({ id: 't1', phase: 'closed' }) })
  await step($) // no prompt routed yet: no project root
  await route($)
  await step($)
  expect(writes).toEqual([])
})

test('a usage file that does not parse is left alone and never breaks the turn', async ($, on) => {
  const files = { [STATE]: state({ id: 't1', phase: 'build' }), [USAGE]: '{ not json' }
  const { writes, logs } = project(on, files)
  await route($)
  expect((await step($))?.stopReason).toBe('end_turn')
  expect(logs.some((l) => l.includes('could not record task usage'))).toBe(true) // caught and logged by the mod
  expect(writes).toEqual([])
  expect(files[USAGE]).toBe('{ not json') // left alone, never clobbered
})

test('a write that fails never breaks the turn', async ($, on) => {
  const { logs } = project(on, { [STATE]: state({ id: 't1', phase: 'build' }) }, { failWrites: true })
  await route($)
  expect((await step($))?.stopReason).toBe('end_turn')
  expect((await step($))?.stopReason).toBe('end_turn') // the queue of writes goes on after a failure
  expect(logs.filter((l) => l.includes('could not record task usage')).length).toBe(2)
})
