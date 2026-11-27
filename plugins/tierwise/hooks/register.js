// tierwise's mod: routes each prompt you type, sets the main session's effort for that turn, keeps
// tierwise agents on their model map, and measures what the session costs against a one-model baseline.
// Rule logic lives in ../bin (Python), shared with the settings-hook fallback, so both routes agree.
import { atom, read, update } from 'claude-code'
import { EFFORTS, LABELS, isUserPrompt, isoWeek, maxEffort, spawnModel } from './policy.js'
import { addStep, addTaskUsage, nameAgent, newTally, panelLines, statusLine, summarize } from './savings.js'

const PANE = 'tierwise-savings'
// Change the shape tag when the tally's fields change: it declines what an earlier version stored.
const tally = atom({ plugin: 'tierwise', key: 'tally' }, newTally(), { shape: 'tally-1' })

async function classify($, prompt, label) {
  const argv = ['python3', `${$.plugin.root}/bin/classify-risk`, '--mod', ...(label ? ['--label', label] : [])]
  const r = await $.process.run(argv, { stdin: JSON.stringify({ prompt, cwd: '.' }), timeoutMs: 20000 })
  if (r.exitCode !== 0) throw new Error(`classify-risk exited ${r.exitCode}: ${r.stderr.slice(0, 300)}`)
  return JSON.parse(r.stdout)
}

async function readState($, root) {
  if (!root) return {}
  try {
    return JSON.parse(await $.fs.read(`${root}/.tierwise/state.json`))
  } catch {
    return {}
  }
}

// The active task's id, as task_active() in bin/mlib/common.py decides it; undefined when there is none.
export function activeTaskId(state) {
  const task = state?.task
  return task && task.phase != null && task.phase !== 'closed' ? task.id || undefined : undefined
}

// Add one request to the active task's entry in .tierwise/usage.json, which the spawn guard reads for
// caps.taskBudgetUsd. Other tasks' entries are kept; a file that does not parse is left alone.
async function recordTaskUsage($, root, step) {
  const taskId = activeTaskId(await readState($, root))
  if (!taskId) return
  const path = `${root}/.tierwise/usage.json`
  const current = (await $.fs.exists(path)) ? JSON.parse(await $.fs.read(path)) : {}
  await $.fs.write(path, JSON.stringify(addTaskUsage(current, taskId, step), null, 1))
}

let usageWrites = Promise.resolve() // one read-modify-write of usage.json at a time

async function record($, root, step) {
  try {
    const t = await update($, tally, (value) => addStep(value ?? newTally(), step))
    $.ui.status(statusLine(summarize(t), 'main'))
  } catch (err) {
    $.ui.log(`tierwise: could not record usage (${String(err).slice(0, 200)})`)
  }
  usageWrites = usageWrites
    .then(() => recordTaskUsage($, root, step))
    .catch((err) => $.ui.log(`tierwise: could not record task usage (${String(err).slice(0, 200)})`))
    .catch(() => {}) // never break the turn, nor the writes queued after this one
  await usageWrites
}

export const register = (on) => {
  let root // the project's git root, once a prompt has been routed
  let cardEffort // the resident's effort for the current prompt
  let skillFloor // effort a skill (tierwise:amend, tierwise:debug) raised for this prompt

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: PANE,
      description: "Show what this session cost with Tierwise, by model and agent, against one-model estimates",
    })
    return next(e)
  })

  on('command.run', { command: PANE }, async ($) => {
    await $.ui.open({ id: PANE, title: 'Tierwise savings' })
    return { text: 'Tierwise savings pane opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const lines = panelLines(summarize((await read($, tally)) ?? newTally()))
    return h(Box, { flexDirection: 'column' }, ...lines.map((l) => h(Text, { bold: !!l.strong, dimColor: !!l.dim }, l.text || ' ')))
  })

  on('prompt.submit', async ($, e, next) => {
    if (!isUserPrompt(e)) return next(e)
    skillFloor = undefined
    let r
    try {
      r = await classify($, e.text)
      if (r.unclear && r.allowModel) {
        let label
        try {
          label = await $.model.classify(e.text, LABELS, { model: r.classifierModel })
        } catch {
          label = undefined // the rules' default class stands
        }
        r = await classify($, e.text, label ?? 'none')
      }
    } catch (err) {
      // The UserPromptSubmit fallback beneath routes this prompt instead.
      $.ui.log(`tierwise: routing failed, the hook fallback routes this prompt (${String(err).slice(0, 200)})`)
      return next(e)
    }
    root = r.root ?? root
    cardEffort = r.residentEffort
    const context = [r.card, ...(r.notes ?? [])].join('\n')
    return next({ ...e, context: [...(e.context ?? []), context] })
  }).catch(($, e, next) => next(e)) // fail open: the prompt goes on, the hook fallback routes it

  // A skill that asks for more effort (tierwise:amend, tierwise:debug) keeps it for the rest of the prompt.
  on('skill.prompt', async ($, e, next) => {
    const asked = e.frontmatter?.effort
    if (EFFORTS.includes(asked)) skillFloor = maxEffort(skillFloor, asked)
    return next(e)
  })

  // Every request, main session and subagents: the main session gets the card's effort (subagents keep
  // their pinned effort), and every response's usage is recorded for the savings bar.
  on('turn.step', async function* ($, e, next) {
    let request = e
    if (!e.agentId && e.effort !== undefined && cardEffort) {
      const state = await readState($, root)
      const want = maxEffort(cardEffort, skillFloor, state.effortFloor)
      if (want && want !== e.effort) request = { ...e, effort: want }
    }
    const response = yield* next(request)
    if (response?.usage) await record($, root, { agentId: e.agentId, model: response.usage.model ?? e.model, usage: response.usage })
    return response
  })

  // The model map, enforced at every tierwise spawn, and the Fable-limit fallback; every spawn is named
  // so the savings panel can show cost by agent.
  on('agent.spawn', async ($, e, next) => {
    let request = e
    if (e.subagentType?.startsWith('tierwise:') && !e.resume && !e.fork) {
      const state = await readState($, root)
      const exhausted = state.fable?.exhausted === isoWeek(await $.clock.now())
      const model = spawnModel(e.subagentType.slice('tierwise:'.length), e.model, exhausted)
      if (model !== e.model) request = { ...e, model }
    }
    const started = await next(request)
    if (started?.agentId) {
      await update($, tally, (value) => nameAgent(value ?? newTally(), started.agentId, e.subagentType || 'agent'))
    }
    return started
  }).catch(($, e, next) => next(e)) // fail open: the PreToolUse guard still checks the spawn

  // Leave the session's measured totals in the project's ledger.
  on('session.end', async ($, e, next) => {
    try {
      const s = summarize((await read($, tally)) ?? newTally())
      const line = statusLine(s, 'main')
      if (root && line) {
        await $.process.run(['python3', `${$.plugin.root}/bin/state`, 'ledger', `session usage: ${line}`], { cwd: root, timeoutMs: 5000 })
      }
    } catch {
      // the session is closing; a missing ledger line is not worth delaying it
    }
    return next(e)
  })
}
