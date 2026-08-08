import { AssetPicker } from './AssetPicker'
import type { TeamAssets, TeamInfo, TradeSnapshot } from './types'

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

function TeamColumn({
  team,
  otherTeam,
  trade,
  teamAssets,
  onSend,
  sending,
}: {
  team: TeamInfo
  otherTeam: TeamInfo | undefined
  trade: TradeSnapshot
  teamAssets: Record<number, TeamAssets>
  onSend: (text: string) => void
  sending: boolean
}) {
  const sendingAssets = trade.assets.filter((a) => a.from_team_id === team.id)
  const receiving = trade.assets.filter((a) => a.to_team_id === team.id)
  const alreadyAddedIds = new Set(sendingAssets.map((a) => `${a.kind}:${a.id}`))

  return (
    <div className="team-column">
      <h3 className="team-column__name">{team.fullName}</h3>
      <div className="team-column__section">
        <span className="team-column__section-label">Sending</span>
        {sendingAssets.length === 0 ? (
          <p className="team-column__empty">Nothing yet</p>
        ) : (
          <ul className="asset-list">
            {sendingAssets.map((a) => (
              <AssetRow key={`${a.kind}-${a.id}`} name={a.name} kind={a.kind} />
            ))}
          </ul>
        )}
        {otherTeam && (
          <AssetPicker
            team={team}
            otherTeam={otherTeam}
            assets={teamAssets[team.id]}
            alreadyAddedIds={alreadyAddedIds}
            onSend={onSend}
            disabled={sending}
          />
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

export function TradePanel({
  trade,
  teams,
  teamAssets,
  onSend,
  sending,
}: {
  trade: TradeSnapshot
  teams: Record<number, TeamInfo>
  teamAssets: Record<number, TeamAssets>
  onSend: (text: string) => void
  sending: boolean
}) {
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
          {trade.teams.map((id) => {
            const otherId = trade.teams.find((t) => t !== id)
            const team = teams[id] ?? { id, name: `Team ${id}`, city: '', abbreviation: '', fullName: `Team ${id}` }
            const otherTeam = otherId !== undefined ? teams[otherId] : undefined
            return (
              <TeamColumn
                key={id}
                team={team}
                otherTeam={otherTeam}
                trade={trade}
                teamAssets={teamAssets}
                onSend={onSend}
                sending={sending}
              />
            )
          })}
        </div>
      )}
    </aside>
  )
}
