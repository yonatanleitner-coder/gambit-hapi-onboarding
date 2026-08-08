import { useState } from 'react'
import { formatMoney, formatSignedMoney } from './format'
import type { Verdict } from './types'

const CAP_STATUS_TONE: Record<string, string> = {
  'Under Cap': 'neutral',
  'Over Cap': 'caution',
  'Over Luxury Tax': 'caution',
  'Over First Apron': 'warning',
  'Over Second Apron': 'danger',
}

export function VerdictCard({ verdict }: { verdict: Verdict }) {
  const [showRules, setShowRules] = useState(false)

  return (
    <div className={`verdict-card verdict-card--${verdict.isValid ? 'legal' : 'illegal'}`}>
      <div className="verdict-card__header">
        <span className="verdict-card__status">
          {verdict.isValid ? (
            <>
              <span className="verdict-card__icon" aria-hidden>✓</span> Legal trade
            </>
          ) : (
            <>
              <span className="verdict-card__icon" aria-hidden>✗</span> Illegal trade
            </>
          )}
        </span>
        {verdict.source === 'mock' && <span className="pill pill--mock">mock data</span>}
      </div>

      <p className="verdict-card__summary">{verdict.summary}</p>

      <div className="verdict-card__teams">
        {verdict.teams.map((t) => (
          <div key={t.teamId} className={`team-money${t.isValid ? '' : ' team-money--failing'}`}>
            <div className="team-money__header">
              <span className="team-money__name">{t.teamName}</span>
              <span className={`pill pill--${CAP_STATUS_TONE[t.newCapStatus] ?? 'neutral'}`}>
                {t.newCapStatus}
              </span>
            </div>
            <div className="team-money__figures">
              <div>
                <span className="team-money__label">Out</span>
                <span className="team-money__value">{formatMoney(t.salaryOut)}</span>
              </div>
              <div>
                <span className="team-money__label">In</span>
                <span className="team-money__value">{formatMoney(t.salaryIn)}</span>
              </div>
              <div>
                <span className="team-money__label">Net</span>
                <span className={`team-money__value team-money__value--${t.netSalaryChange >= 0 ? 'up' : 'down'}`}>
                  {formatSignedMoney(t.netSalaryChange)}
                </span>
              </div>
              <div>
                <span className="team-money__label">New total</span>
                <span className="team-money__value">{formatMoney(t.newTotalSalary)}</span>
              </div>
            </div>
            {t.violations.length > 0 && (
              <ul className="team-money__violations">
                {t.violations.map((v, i) => (
                  <li key={i}>{v}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      {verdict.appliedRules.length > 0 && (
        <div className="verdict-card__rules">
          <button type="button" className="link-button" onClick={() => setShowRules((s) => !s)}>
            {showRules ? 'Hide' : 'Show'} CBA citations
          </button>
          {showRules && (
            <ul className="verdict-card__rules-list">
              {verdict.appliedRules.map((rule, i) => (
                <li key={i}>{rule}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
