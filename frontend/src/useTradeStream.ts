import { useCallback, useEffect, useRef, useState } from 'react'
import { parseSSE } from './sse'
import type { ChatMessage, ErrorInfo, TeamInfo, TradeSnapshot, TraceEvent, Verdict } from './types'

const SESSION_KEY = 'trade-chat-session-id'

function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

const EMPTY_TRADE: TradeSnapshot = { teams: [], assets: [], phase: 'empty' }

export function useTradeStream() {
  const [teams, setTeams] = useState<Record<number, TeamInfo>>({})
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [trade, setTrade] = useState<TradeSnapshot>(EMPTY_TRADE)
  const [pendingTrace, setPendingTrace] = useState<TraceEvent[]>([])
  const [allEvents, setAllEvents] = useState<TraceEvent[]>([])
  const [costTotal, setCostTotal] = useState(0)
  const [sending, setSending] = useState(false)
  const sessionId = useRef(getSessionId())

  useEffect(() => {
    fetch('/api/teams')
      .then((r) => r.json())
      .then((list: TeamInfo[]) => setTeams(Object.fromEntries(list.map((t) => [t.id, t]))))
      .catch(() => {
        /* trade panel falls back to "Team {id}" -- non-fatal, chat still works */
      })
  }, [])

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return

    setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', text: trimmed }])
    setSending(true)
    setPendingTrace([])

    const turnEvents: TraceEvent[] = []
    let turnVerdict: Verdict | undefined
    let turnError: ErrorInfo | undefined

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.current, message: trimmed }),
      })
      if (!resp.ok || !resp.body) {
        throw new Error(`chat request failed (HTTP ${resp.status})`)
      }

      for await (const frame of parseSSE(resp.body)) {
        if (frame.event === 'done') continue

        const traceEvent: TraceEvent = {
          id: crypto.randomUUID(),
          event: frame.event as TraceEvent['event'],
          data: frame.data as Record<string, unknown>,
          ts: Date.now(),
        }
        turnEvents.push(traceEvent)
        setPendingTrace((p) => [...p, traceEvent])
        setAllEvents((all) => [...all, traceEvent])

        const data = frame.data as Record<string, any>
        switch (frame.event) {
          case 'state_diff':
            setTrade(data.snapshot as TradeSnapshot)
            break
          case 'verdict':
            turnVerdict = data as Verdict
            break
          case 'cost':
            setCostTotal((c) => c + (data.usd as number))
            break
          case 'error':
            turnError = { kind: data.kind, message: data.message }
            break
          case 'assistant':
            setMessages((m) => [
              ...m,
              {
                id: crypto.randomUUID(),
                role: 'assistant',
                text: data.text as string,
                verdict: turnVerdict,
                error: turnError,
                trace: [...turnEvents],
              },
            ])
            break
        }
      }
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          text: "Couldn't reach the trade assistant. Check that the backend is running and try again.",
          error: { kind: 'server_error', message: err instanceof Error ? err.message : String(err) },
        },
      ])
    } finally {
      setSending(false)
      setPendingTrace([])
    }
  }, [])

  return { teams, messages, trade, sending, pendingTrace, allEvents, costTotal, send }
}
