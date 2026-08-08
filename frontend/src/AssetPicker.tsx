import { useState } from 'react'
import type { TeamAssets, TeamInfo } from './types'

// The closed-list counterpart to typing a player/pick name in chat -- for
// anyone who doesn't know exactly what's on a roster. Picking an item here
// only drafts a chat utterance and sends it through the same composer path
// as free text; the tool-calling loop still does the actual resolution and
// mutation, so this can never drift from what typing would have produced.
export function AssetPicker({
  team,
  otherTeam,
  assets,
  alreadyAddedIds,
  onSend,
  disabled,
}: {
  team: TeamInfo
  otherTeam: TeamInfo
  assets: TeamAssets | undefined
  alreadyAddedIds: Set<string>
  onSend: (text: string) => void
  disabled: boolean
}) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<'player' | 'pick'>('player')
  const [assetId, setAssetId] = useState('')

  const players = (assets?.players ?? []).filter((p) => !alreadyAddedIds.has(`player:${p.id}`))
  const picks = (assets?.picks ?? []).filter((p) => !alreadyAddedIds.has(`pick:${p.id}`))
  const activeKind = players.length === 0 && picks.length > 0 ? 'pick' : kind
  const list = activeKind === 'player' ? players : picks

  if (!assets) return null // still loading -- nothing to pick from yet
  if (players.length === 0 && picks.length === 0) return null

  if (!open) {
    return (
      <button type="button" className="link-button asset-picker__toggle" onClick={() => setOpen(true)} disabled={disabled}>
        + Add from list
      </button>
    )
  }

  const submit = () => {
    const item = list.find((i) => String(i.id) === assetId)
    if (!item) return
    const label = 'name' in item ? item.name : item.descriptor
    const phrase = 'name' in item ? label : `their ${label}`
    onSend(`The ${team.fullName} send ${phrase} to the ${otherTeam.fullName}.`)
    setAssetId('')
    setOpen(false)
  }

  return (
    <div className="asset-picker">
      {players.length > 0 && picks.length > 0 && (
        <div className="asset-picker__kind">
          <button
            type="button"
            className={activeKind === 'player' ? 'is-active' : ''}
            onClick={() => {
              setKind('player')
              setAssetId('')
            }}
          >
            Player
          </button>
          <button
            type="button"
            className={activeKind === 'pick' ? 'is-active' : ''}
            onClick={() => {
              setKind('pick')
              setAssetId('')
            }}
          >
            Pick
          </button>
        </div>
      )}
      <div className="asset-picker__row">
        <select value={assetId} onChange={(e) => setAssetId(e.target.value)} disabled={disabled} aria-label={`${team.fullName} asset`}>
          <option value="">Choose…</option>
          {list.map((item) => (
            <option key={item.id} value={item.id}>
              {'name' in item ? item.name : item.descriptor}
            </option>
          ))}
        </select>
        <button type="button" onClick={submit} disabled={!assetId || disabled}>
          Add
        </button>
        <button type="button" className="link-button" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  )
}
