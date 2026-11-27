// tierwise's session state, kept by the engine across mod reloads (see hooks/savings.js).
export type Usage = { input: number; read: number; write5m: number; write1h: number; output: number }
export type ModelTotals = { requests: number; cost: number; tokens: number; output: number }
export type RoleTotals = { requests: number; cost: number; tokens: number }
export type AgentRecord = { requests: number; rest: Usage; content: number; mainCtxAtStart: number; mainStepsAtEnd: number }
export type Tally = {
  requests: number
  mainFamily?: string
  mainSteps: number
  mainCtx: number
  main: Usage
  byModel: Record<string, ModelTotals>
  byRole: Record<string, RoleTotals>
  agents: Record<string, AgentRecord>
  agentTypes: Record<string, string>
}

declare module 'claude-code' {
  interface PluginState {
    tierwise: { tally: Shaped<Tally> }
  }
}
