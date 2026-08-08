import { useCallback, useEffect, useRef, useState } from 'react'
import { parseSSE } from './sse'
import type { ChatMessage, ErrorInfo, TeamAssets, TeamInfo, TradeSnapshot, TraceEvent, Verdict } from './types'

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

// If the backend process dies or a proxy drops the connection mid-stream
// (observed live: a backend restart mid-turn left the UI showing a
// half-written assistant message with the "thinking" indicator stuck on
// forever, since no `done` event -- or any further bytes -- ever arrives
// to end the loop below). An inactivity timeout, reset on every frame,
// aborts the fetch so the turn always resolves to *something* -- a
// visible error the user can retry from -- instead of hanging silently.
const STREAM_IDLE_TIMEOUT_MS = 30_000

export function useTradeStream() {
  const [teams, setTeams] = useState<Record<number, TeamInfo>>({})
  const [teamAssets, setTeamAssets] = useState<Record<number, TeamAssets>>({})
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

  // Feeds AssetPicker's closed-list player/pick pickers. Fetched lazily
  // per team (only once teams are actually in the trade) and cached for
  // the session -- rosters don't change mid-conversation.
  useEffect(() => {
    for (const teamId of trade.teams) {
      if (teamAssets[teamId]) continue
      fetch(`/api/teams/${teamId}/assets`)
        .then((r) => r.json())
        .then((data: TeamAssets) => setTeamAssets((prev) => ({ ...prev, [teamId]: data })))
        .catch(() => {
          /* AssetPicker just stays hidden for this team -- typing still works */
        })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trade.teams.join(',')])

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return

    setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', text: trimmed }])
    setSending(true)
    setPendingTrace([])

    const turnEvents: TraceEvent[] = []
    let turnVerdict: Verdict | undefined
    let turnError: ErrorInfo | undefined

    const controller = new AbortController()
    let idleTimer: ReturnType<typeof setTimeout> | undefined
    const armIdleTimer = () => {
      clearTimeout(idleTimer)
      idleTimer = setTimeout(() => controller.abort(), STREAM_IDLE_TIMEOUT_MS)
    }

    try {
      armIdleTimer()
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.current, message: trimmed }),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        throw new Error(`chat request failed (HTTP ${resp.status})`)
      }

      for await (const frame of parseSSE(resp.body)) {
        armIdleTimer() // any frame at all counts as life -- reset the clock
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
      const timedOut = err instanceof Error && err.name === 'AbortError'
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          text: timedOut
            ? "Lost the connection mid-response (nothing arrived for a while). The reply above may be incomplete -- try again."
            : "Couldn't reach the trade assistant. Check that the backend is running and try again.",
          error: { kind: 'server_error', message: err instanceof Error ? err.message : String(err) },
        },
      ])
    } finally {
      clearTimeout(idleTimer)
      setSending(false)
      setPendingTrace([])
    }
  }, [])

  return { teams, teamAssets, messages, trade, sending, pendingTrace, allEvents, costTotal, send }
}
