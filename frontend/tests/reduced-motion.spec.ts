import { expect, test } from '@playwright/test';

test('reduced motion disables key animations', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });

  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.route('**/api/library/import-latest', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        added: 1,
        skipped: 0,
        failed: 0,
        total_papers: 1,
        failure_reasons: [],
        pipeline_stages: [{ stage: 'index', state: 'running', updated_at: '2026-03-06T00:00:02Z' }]
      })
    });
  });

  await page.route('**/api/library/import-history?limit=10', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  const magicAnimation = await page.locator('.magic-card').first().evaluate((node) => getComputedStyle(node).animationName);
  expect(magicAnimation).toBe('none');
  const shimmerAnimation = await page
    .locator('.shimmer-btn')
    .evaluate((node) => getComputedStyle(node, '::after').animationName);
  expect(shimmerAnimation).toBe('none');

  await page.goto('http://127.0.0.1:3000/pipeline');
  await expect(page.getByRole('heading', { name: '知识库构建流水线' })).toBeVisible();
});
