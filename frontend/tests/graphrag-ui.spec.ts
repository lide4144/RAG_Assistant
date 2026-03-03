import { test, expect } from '@playwright/test';

test('graphrag panel supports top-n and citation/node linking', async ({ page }) => {
  await page.goto('http://127.0.0.1:3000/chat');

  await expect(page.getByText('Chat Workspace')).toBeVisible();

  // This test assumes a running gateway that can return sources.
  await page.getByPlaceholder('Ask a question...').fill('show graph evidence');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('GraphRAG Subgraph')).toBeVisible({ timeout: 20000 });

  const expandButton = page.getByRole('button', { name: /Expand|Collapse/ });
  if (await expandButton.count()) {
    await expandButton.first().click();
  }

  const citationButton = page.locator('button').filter({ hasText: '[1]' }).first();
  await expect(citationButton).toBeVisible();
  await citationButton.click();

  const selectedSourceCard = page.locator('button').filter({ hasText: '[1]' }).nth(1);
  await expect(selectedSourceCard).toHaveClass(/border-accent/);

  await expect(page.getByText('traceId')).toHaveCount(0);
  await page.getByRole('button', { name: 'Developer View' }).click();
  await expect(page.getByText('traceId')).toBeVisible();
  await expect(page.getByText(/path:/)).toBeVisible();

  await page.getByRole('button', { name: 'User View' }).click();
  await expect(page.getByText('traceId')).toHaveCount(0);
});
