import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { describeEvent } from './TraceStrip'
import { VerdictCard } from './VerdictCard'
import type { ChatMessage, TraceEvent } from './types'

const EXAMPLE_PROMPTS = [
  'Set up a trade between the Celtics and the Knicks',
  "Send Boston's 2027 first to New York for Julius Randle",
  'Why is that illegal?',
]

function MessageTrace({ trace }: { trace: TraceEvent[] }) {
  const [open, setOpen] = useState(false)
  // cost/assistant events ride along on every turn (even ones that changed
  // nothing) -- the toggle should only appear when there's something a
  // user would actually call "what changed".
  const meaningful = trace.filter((e) => e.event !== 'cost' && e.event !== 'assistant')
  const toolCalls = trace.filter((e) => e.event === 'tool_call').length
  if (meaningful.length === 0) return null

  return (
    <div className="message-trace">
      <button type="button" className="link-button" onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide' : 'Show'} what changed ({toolCalls} tool call{toolCalls === 1 ? '' : 's'})
      </button>
      {open && (
        <ul className="message-trace__list">
          {trace.map((e) => (
            <li key={e.id}>{describeEvent(e)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Bubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="chat-message chat-message--user">
        <div className="chat-bubble chat-bubble--user">{message.text}</div>
      </div>
    )
  }

  return (
    <div className={`chat-message chat-message--assistant${message.error ? ' chat-message--has-error' : ''}`}>
      <div className="chat-bubble chat-bubble--assistant">
        <ReactMarkdown>{message.text}</ReactMarkdown>
        {message.verdict && <VerdictCard verdict={message.verdict} />}
        {message.trace && <MessageTrace trace={message.trace} />}
      </div>
    </div>
  )
}

function PendingBubble({ trace }: { trace: TraceEvent[] }) {
  const toolCalls = trace.filter((e) => e.event === 'tool_call')
  return (
    <div className="chat-message chat-message--assistant">
      <div className="chat-bubble chat-bubble--assistant chat-bubble--pending">
        {toolCalls.length === 0 ? (
          <span className="typing-dots" aria-label="Thinking">
            <span />
            <span />
            <span />
          </span>
        ) : (
          toolCalls.map((e) => (
            <div key={e.id} className="pending-step">
              {describeEvent(e)}…
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export function Chat({
  messages,
  sending,
  pendingTrace,
  onSend,
}: {
  messages: ChatMessage[]
  sending: boolean
  pendingTrace: TraceEvent[]
  onSend: (text: string) => void
}) {
  const [draft, setDraft] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pendingTrace])

  const submit = () => {
    if (!draft.trim() || sending) return
    onSend(draft)
    setDraft('')
  }

  return (
    <section className="chat">
      <div className="chat__list" ref={listRef}>
        {messages.length === 0 && (
          <div className="chat__empty">
            <p>Describe a trade in plain English — the mouse is optional.</p>
            <div className="chat__examples">
              {EXAMPLE_PROMPTS.map((p) => (
                <button key={p} type="button" className="chat__example" onClick={() => onSend(p)}>
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} message={m} />
        ))}
        {sending && <PendingBubble trace={pendingTrace} />}
      </div>

      <form
        className="chat__composer"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          placeholder="Set up a trade between two teams…"
          rows={1}
          disabled={sending}
        />
        <button type="submit" disabled={sending || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  )
}
