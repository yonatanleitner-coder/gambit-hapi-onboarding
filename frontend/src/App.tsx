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
  const { teams, teamAssets, messages, trade, sending, pendingTrace, allEvents, costTotal, send } = useTradeStream()

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__title">
          <img className="app-header__mark" src="/gambit-mark.png" alt="Gambit" />
          <div>
            <h1>Gambit Trade Machine</h1>
            <p>Chat-first NBA trades</p>
          </div>
        </div>
        <span className={`phase-badge phase-badge--${trade.phase}`}>{PHASE_LABEL[trade.phase]}</span>
      </header>

      <main className="app-body">
        <Chat teams={teams} messages={messages} sending={sending} pendingTrace={pendingTrace} onSend={send} />
        <TradePanel trade={trade} teams={teams} teamAssets={teamAssets} onSend={send} sending={sending} />
      </main>

      <TraceStrip events={allEvents} costTotal={costTotal} />
    </div>
  )
}
