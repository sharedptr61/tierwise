import { expect, test } from 'claude-code/testing'
import { isUserPrompt, isoWeek, maxEffort, spawnModel } from './policy.js'

test('only prompts the person typed are routed', async () => {
  expect(isUserPrompt({ text: 'add x', origin: { kind: 'composer' } })).toBe(true)
  expect(isUserPrompt({ text: 'add x', origin: { kind: 'sdk' } })).toBe(true)
  expect(isUserPrompt({ text: 'x', origin: { kind: 'task-notification' } })).toBe(false)
  expect(isUserPrompt({ text: '<agent-message from="a1">\n[Subagent hand-back] ok', origin: { kind: 'composer' } }))
    .toBe(false)
  expect(isUserPrompt({ text: '/compact', command: { name: 'compact' }, origin: { kind: 'composer' } })).toBe(false)
  expect(isUserPrompt({ text: 'x', isMeta: true, origin: { kind: 'composer' } })).toBe(false)
})

test('effort only rises', async () => {
  expect(maxEffort('low', undefined, 'high', 'medium')).toBe('high')
  expect(maxEffort(undefined, 'bogus')).toBe(undefined)
  expect(maxEffort('xhigh', 'max')).toBe('max')
})

test('the model map keeps pinned models and falls back off Fable', async () => {
  expect(spawnModel('scout', 'opus', false)).toBe(undefined) // not allowed: back to pinned haiku
  expect(spawnModel('builder', 'haiku', false)).toBe('haiku')
  expect(spawnModel('planner', undefined, false)).toBe(undefined)
  expect(spawnModel('planner', undefined, true)).toBe('opus')
  expect(spawnModel('principal', 'fable', true)).toBe('opus')
  expect(spawnModel('security-reviewer', 'fable', false)).toBe(undefined)
  expect(spawnModel('not-tierwise', 'opus', true)).toBe('opus')
})

test('ISO weeks match Python isocalendar()', async () => {
  expect(isoWeek(new Date(2026, 10, 26).getTime())).toBe('2026-W48')
  expect(isoWeek(new Date(2027, 0, 1).getTime())).toBe('2026-W53')
  expect(isoWeek(new Date(2024, 11, 30).getTime())).toBe('2025-W01')
  expect(isoWeek(new Date(2026, 0, 1).getTime())).toBe('2026-W01')
})

test('a tierwise spawn naming a model off its map is sent with the pinned model', async ($, on) => {
  const seen: (string | undefined)[] = []
  on('clock.now', () => ({ value: new Date(2026, 10, 26).getTime() }))
  on('agent.spawn', (_, e) => {
    seen.push(e.model)
    return { model: e.model ?? 'pinned', agentId: 'a1' }
  })
  await $.agent.spawn({ prompt: 'go', subagentType: 'tierwise:scout', model: 'opus' })
  await $.agent.spawn({ prompt: 'go', subagentType: 'tierwise:builder', model: 'haiku' })
  await $.agent.spawn({ prompt: 'go', subagentType: 'Explore', model: 'opus' })
  expect(seen).toEqual([undefined, 'haiku', 'opus'])
})
