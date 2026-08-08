import type { TeamInfo, TradeSnapshot } from './types'

const PHASE_LABEL: Record<TradeSnapshot['phase'], string> = {
  empty: 'No teams yet',
  teams_set: 'Teams set — add players or picks',
  has_assets: 'Building trade',
}

function AssetRow({ name, kind }: { name: string; kind: 'player' | 'pick' }) {
  return (
    <li className="asset-row">
      <span className={`asset-row__icon asset-row__icon--${kind}`} aria-hidden>
        {kind === 'player' ? '●' : '◆'}
      </span>
      {name}
    </li>
  )
}

function TeamColumn({ teamId, teamName, trade }: { teamId: number; teamName: string; trade: TradeSnapshot }) {
  const sending = trade.assets.filter((a) => a.from_team_id === teamId)
  const receiving = trade.assets.filter((a) => a.to_team_id === teamId)

  return (
    <div className="team-column">
      <h3 className="team-column__name">{teamName}</h3>
      <div className="team-column__section">
        <span className="team-column__section-label">Sending</span>
        {sending.length === 0 ? (
          <p className="team-column__empty">Nothing yet</p>
        ) : (
          <ul className="asset-list">
            {sending.map((a) => (
              <AssetRow key={`${a.kind}-${a.id}`} name={a.name} kind={a.kind} />
            ))}
          </ul>
        )}
      </div>
      <div className="team-column__section">
        <span className="team-column__section-label">Receiving</span>
        {receiving.length === 0 ? (
          <p className="team-column__empty">Nothing yet</p>
        ) : (
          <ul className="asset-list">
            {receiving.map((a) => (
              <AssetRow key={`${a.kind}-${a.id}`} name={a.name} kind={a.kind} />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

export function TradePanel({ trade, teams }: { trade: TradeSnapshot; teams: Record<number, TeamInfo> }) {
  return (
    <aside className="trade-panel">
      <div className="trade-panel__header">
        <h2>Trade</h2>
        <span className={`phase-badge phase-badge--${trade.phase}`}>{PHASE_LABEL[trade.phase]}</span>
      </div>

      {trade.teams.length === 0 ? (
        <div className="trade-panel__empty">
          <p>This mirrors the trade as you build it in chat — nothing to show yet.</p>
          <p className="trade-panel__hint">
            Try: <em>"Set up a trade between the Celtics and the Knicks"</em>
          </p>
        </div>
      ) : (
        <div className="trade-panel__teams">
          {trade.teams.map((id) => (
            <TeamColumn key={id} teamId={id} teamName={teams[id]?.fullName ?? `Team ${id}`} trade={trade} />
          ))}
        </div>
      )}
    </aside>
  )
}
