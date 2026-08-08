// Mirrors backend/contracts.py + backend/schemas.py -- kept minimal and
// hand-written rather than generated, since the backend surface is small
// and stable at this stage.

export type Phase = 'empty' | 'teams_set' | 'has_assets'

export interface Asset {
  kind: 'player' | 'pick'
  id: number
  name: string
  from_team_id: number
  to_team_id: number
}

export interface TradeSnapshot {
  teams: number[]
  assets: Asset[]
  phase: Phase
}

export interface TeamInfo {
  id: number
  name: string
  city: string
  abbreviation: string
  fullName: string
}

export interface TeamVerdict {
  teamId: number
  teamName: string
  salaryOut: number
  salaryIn: number
  netSalaryChange: number
  newTotalSalary: number
  newCapStatus: string
  allowances: string[]
  violations: string[]
  isValid: boolean
}

export interface Verdict {
  isValid: boolean
  summary: string
  appliedRules: string[]
  teams: TeamVerdict[]
  source: 'api' | 'mock'
}

export type ErrorKind = 'api_400' | 'provider_down' | 'resolution' | 'validation' | 'server_error'

export interface ErrorInfo {
  kind: ErrorKind
  message: string
}

export type SSEEventName = 'tool_call' | 'state_diff' | 'verdict' | 'assistant' | 'cost' | 'error'

export interface TraceEvent {
  id: string
  event: SSEEventName
  data: Record<string, unknown>
  ts: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  verdict?: Verdict
  error?: ErrorInfo
  trace?: TraceEvent[]
}
