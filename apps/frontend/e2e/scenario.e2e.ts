import { readFileSync } from 'node:fs'
import { test, expect } from './fixtures.ts'

const alice = JSON.parse(readFileSync(
  new URL('../src/replay/scenarios/alice-pigeon-grounding-and-spoilers--muse-librarian-provenance--2026-09-03.json', import.meta.url),
  'utf8',
))
const firstRecordedReply: string = alice.runs[0].scenes[0].turns[0].reply

test('user opens a saved scenario, inspects its turns, and returns to the gallery', async ({ page, apiRequests }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Replay a scenario', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Replay a recorded evaluation' })).toBeVisible()
  await page.getByRole('button', { name: /^Alice Pigeon grounding and spoilers/ }).click()
  await expect(page.getByRole('heading', { name: 'Alice Pigeon grounding and spoilers', exact: true })).toBeVisible()
  const conversation = page.getByRole('region', { name: 'Recorded conversation' })
  await expect(conversation.locator('.bubble.user')).toHaveCount(3)
  await expect(conversation.locator('.bubble.assistant')).toHaveCount(3)
  await expect(conversation.locator('.bubble.user').first()).toContainText('the Pigeon calls her a serpent')
  const firstReply = conversation.locator('.bubble.assistant').first()
  for (const paragraph of firstRecordedReply.split(/\n\s*\n/)) await expect(firstReply).toContainText(paragraph.trim())
  await expect(conversation.getByText('Recorded run · read-only. Replies are exactly what this build said; nothing is sent.', { exact: true })).toBeVisible()
  await expect(page.getByRole('textbox')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Turn', exact: true }).selectOption('0')
  await expect(page.getByRole('region', { name: 'This turn', exact: true })).toContainText('the Pigeon calls her a serpent')
  await page.getByRole('button', { name: 'All turns and contracts', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('dialog')).toContainText('the Pigeon calls her a serpent')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: 'All scenarios', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Replay a recorded evaluation' })).toBeVisible()
  expect(apiRequests, 'Replay must work without authentication or API calls').toHaveLength(0)
})
