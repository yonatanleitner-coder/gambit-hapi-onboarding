const moneyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  maximumFractionDigits: 1,
})

export function formatMoney(value: number): string {
  return moneyFormatter.format(value)
}

/** e.g. +$16.2M / −$7.0M, matching human-plan.md's illustrative output. */
export function formatSignedMoney(value: number): string {
  if (value === 0) return formatMoney(0)
  const sign = value > 0 ? '+' : '−'
  return `${sign}${formatMoney(Math.abs(value))}`
}

export function formatUsd(value: number): string {
  if (value === 0) return '$0.00'
  if (value < 0.01) return '<$0.01'
  return `$${value.toFixed(value < 1 ? 4 : 2)}`
}
