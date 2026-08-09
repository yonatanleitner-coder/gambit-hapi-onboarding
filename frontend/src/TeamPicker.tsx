import { useState } from 'react'
import type { TeamInfo } from './types'

// A closed-list alternative to typing team names, for anyone who doesn't
// know the exact ones in this dataset -- mirrors bball-GM's own "pick a
// team" step. Selecting still only drafts a chat utterance and sends it
// through the normal composer path (App's onSend -> POST /api/chat); the
// tool-calling loop is still the only thing that ever mutates trade state.
export function TeamPicker({
  teams,
  onSend,
  disabled,
}: {
  teams: Record<number, TeamInfo>
  onSend: (text: string) => void
  disabled: boolean
}) {
  const [teamAId, setTeamAId] = useState('')
  const [teamBId, setTeamBId] = useState('')
  const options = Object.values(teams).sort((a, b) => a.fullName.localeCompare(b.fullName))
  const canStart = teamAId && teamBId && teamAId !== teamBId

  const start = () => {
    if (!canStart) return
    onSend(`Set up a trade between the ${teams[Number(teamAId)].fullName} and the ${teams[Number(teamBId)].fullName}.`)
    setTeamAId('')
    setTeamBId('')
  }

  if (options.length === 0) return null

  return (
    <div className="team-picker">
      <p className="team-picker__label">Not sure of the exact names? Pick two teams from the list:</p>
      <div className="team-picker__row">
        <select value={teamAId} onChange={(e) => setTeamAId(e.target.value)} disabled={disabled} aria-label="First team">
          <option value="">Choose a team…</option>
          {options.map((t) => (
            <option key={t.id} value={t.id} disabled={String(t.id) === teamBId}>
              {t.fullName}
            </option>
          ))}
        </select>
        <span className="team-picker__vs">vs</span>
        <select value={teamBId} onChange={(e) => setTeamBId(e.target.value)} disabled={disabled} aria-label="Second team">
          <option value="">Choose a team…</option>
          {options.map((t) => (
            <option key={t.id} value={t.id} disabled={String(t.id) === teamAId}>
              {t.fullName}
            </option>
          ))}
        </select>
        <button type="button" onClick={start} disabled={!canStart || disabled}>
          Start trade
        </button>
      </div>
    </div>
  )
}
