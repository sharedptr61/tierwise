// Pure rules the mod applies. No engine calls here, so the tests can drive them directly.

export const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max']
export const LABELS = ['question', 'trivial-edit', 'local-fix', 'feature', 'bulk', 'investigation', 'high-risk']

// Models each tierwise agent may run on; the first is its pinned model.
export const MODELS = {
  scout: ['haiku'],
  analyst: ['sonnet'],
  planner: ['fable', 'opus'],
  builder: ['sonnet', 'haiku', 'opus'],
  debugger: ['opus'],
  reviewer: ['opus'],
  'security-reviewer': ['opus'],
  principal: ['fable', 'opus'],
}

// Prompts the person typed (or an SDK host sent); hand-backs and notifications are not routed.
export function isUserPrompt(e) {
  if (e.command || e.isMeta) return false
  const kind = e.origin?.kind
  if (kind !== undefined && !['composer', 'bridge', 'sdk'].includes(kind)) return false
  return !/^\s*<(agent-message|task-notification|command-|local-command|system-reminder)/.test(e.text ?? '')
}

export function maxEffort(...levels) {
  const known = levels.filter((l) => EFFORTS.includes(l))
  return known.length ? known.reduce((a, b) => (EFFORTS.indexOf(b) > EFFORTS.indexOf(a) ? b : a)) : undefined
}

// The model a tierwise spawn should name: undefined keeps the agent's pinned model.
export function spawnModel(agent, requested, fableExhausted, fallback = 'opus') {
  const allowed = MODELS[agent]
  if (!allowed) return requested
  if (fableExhausted && allowed.includes('fable') && (requested === undefined || requested === 'fable')) {
    return fallback
  }
  if (requested !== undefined && !allowed.includes(requested)) return undefined
  return requested
}

// ISO 8601 week, as Python's date.isocalendar() gives it: "2026-W48".
export function isoWeek(ms) {
  const d = new Date(ms)
  const day = (d.getDay() + 6) % 7 // Monday = 0
  const thursday = new Date(d.getFullYear(), d.getMonth(), d.getDate() - day + 3)
  const firstThursday = new Date(thursday.getFullYear(), 0, 4)
  const week = 1 + Math.round(((thursday - firstThursday) / 86400000 - 3 + ((firstThursday.getDay() + 6) % 7)) / 7)
  return `${thursday.getFullYear()}-W${String(week).padStart(2, '0')}`
}
