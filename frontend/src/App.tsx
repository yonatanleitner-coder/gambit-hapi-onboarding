import { Chat } from './Chat'
import { TradePanel } from './TradePanel'
import { TraceStrip } from './TraceStrip'
import { useTradeStream } from './useTradeStream'
import './index.css'

const PHASE_LABEL: Record<string, string> = {
  empty: 'No teams yet',
  teams_set: 'Teams set',
  has_assets: 'Building trade',
}

export default function App() {
  const { teams, messages, trade, sending, pendingTrace, allEvents, costTotal, send } = useTradeStream()

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__title">
          <span className="app-header__mark" aria-hidden>
            🏀
          </span>
          <div>
            <h1>Trade Machine</h1>
            <p>Chat-first NBA trades</p>
          </div>
        </div>
        <span className={`phase-badge phase-badge--${trade.phase}`}>{PHASE_LABEL[trade.phase]}</span>
      </header>

      <main className="app-body">
        <Chat messages={messages} sending={sending} pendingTrace={pendingTrace} onSend={send} />
        <TradePanel trade={trade} teams={teams} />
      </main>

      <TraceStrip events={allEvents} costTotal={costTotal} />
    </div>
  )
}
