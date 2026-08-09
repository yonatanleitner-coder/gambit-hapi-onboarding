import { expect, test } from '@playwright/test'

// AI Plan §12 task 10 -- the brief's "bonus: one automated browser test on
// the happy path". Derived directly from golden/cases.yaml's
// `legal_two_team` case: same utterance, same expected tool sequence
// (set_teams -> add_player -> request_verdict), same expected outcome
// (legal). Where the golden-case eval proves the tool-calling loop works
// against the graph directly, this proves the same scenario renders
// correctly through the real browser: chat AND the GUI mirror must agree,
// which is the thing a graph-level test structurally cannot see.
test('chat-built trade renders a legal verdict in both chat and the GUI mirror', async ({ page }) => {
  await page.goto('/')

  const composer = page.getByPlaceholder('Set up a trade between two teams…')
  await composer.fill(
    'Set up a trade between the Boston Celtics and the New York Knicks: ' +
      'Boston sends Neemias Queta to New York for Andre Drummond. Then get me a verdict.'
  )
  await page.getByRole('button', { name: 'Send', exact: true }).click()

  // The turn does 3 tool calls + a real narration call -- generous timeout
  // for a real (non-mocked) Anthropic round trip.
  const verdictCard = page.locator('.verdict-card').first()
  await expect(verdictCard).toBeVisible({ timeout: 30_000 })

  // Verdict in chat: legal, not raw JSON anywhere in the bubble.
  await expect(verdictCard).toHaveClass(/verdict-card--legal/)
  await expect(verdictCard).toContainText('Legal trade')
  const chatBubble = page.locator('.chat-bubble--assistant').last()
  await expect(chatBubble).not.toContainText('{')

  // GUI mirror: same state, reached independently through state_diff
  // events rather than the verdict event -- proves sync, not just that
  // the verdict happened to render somewhere.
  const tradePanel = page.locator('.trade-panel')
  await expect(tradePanel).toContainText('Boston Celtics')
  await expect(tradePanel).toContainText('New York Knicks')
  await expect(tradePanel).toContainText('Neemias Queta')
  await expect(tradePanel).toContainText('Andre Drummond')
  await expect(tradePanel.locator('.phase-badge')).toContainText('Building trade')
})
