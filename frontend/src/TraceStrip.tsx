import { useState } from 'react'
import { formatUsd } from './format'
import type { TraceEvent } from './types'

const EVENT_ICON: Record<TraceEvent['event'], string> = {
  tool_call: '🔧',
  state_diff: '📋',
  verdict: '⚖️',
  assistant: '💬',
  cost: '💰',
  error: '⚠️',
}

export function describeEvent(e: TraceEvent): string {
  const d = e.data as any
  switch (e.event) {
    case 'tool_call': {
      const args = Object.entries(d.args ?? {})
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
        .join(', ')
      return `Called ${d.name}(${args})`
    }
    case 'state_diff': {
      const parts: string[] = []
      if (d.added?.length) parts.push(`added ${d.added.map((a: any) => a.name).join(', ')}`)
      if (d.removed?.length) parts.push(`removed ${d.removed.map((a: any) => a.name).join(', ')}`)
      if (d.rerouted?.length) parts.push(`rerouted ${d.rerouted.map((a: any) => a.name).join(', ')}`)
      return parts.length > 0 ? `State updated — ${parts.join('; ')}` : 'State updated'
    }
    case 'verdict':
      return d.isValid ? 'Verdict: legal' : 'Verdict: illegal'
    case 'assistant':
      return 'Assistant replied'
    case 'cost':
      return (
        `${d.model} · ${d.input_tokens} in / ${d.output_tokens} out tokens · ${formatUsd(d.usd)}` +
        (d.cached_tokens ? ` (${d.cached_tokens} cached)` : '')
      )
    case 'error':
      return `Error (${d.kind}): ${d.message}`
    default:
      return e.event
  }
}

export function TraceStrip({ events, costTotal }: { events: TraceEvent[]; costTotal: number }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`trace-strip${expanded ? ' trace-strip--expanded' : ''}`}>
      <button type="button" className="trace-strip__toggle" onClick={() => setExpanded((e) => !e)}>
        <span className="trace-strip__chevron" aria-hidden>{expanded ? '▾' : '▸'}</span>
        <span>Trace</span>
        <span className="trace-strip__summary">
          {events.length} event{events.length === 1 ? '' : 's'} · {formatUsd(costTotal)} total
        </span>
      </button>
      {expanded && (
        <div className="trace-strip__log">
          {events.length === 0 ? (
            <p className="trace-strip__empty">Nothing yet — send a message to get started.</p>
          ) : (
            events.map((e) => (
              <div key={e.id} className={`trace-strip__row trace-strip__row--${e.event}`}>
                <span className="trace-strip__icon" aria-hidden>
                  {EVENT_ICON[e.event] ?? '•'}
                </span>
                <span>{describeEvent(e)}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
