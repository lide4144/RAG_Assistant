import { expect, test } from '@playwright/test';

test('home redirects to chat and shell navigation works', async ({ page }) => {
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: true })
    });
  });
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4.1-mini', configured: true },
          embedding: { provider: 'siliconflow', model: 'bge', configured: true },
          rerank: { provider: 'siliconflow', model: 'rerank', configured: true },
          rewrite: { provider: 'siliconflow', model: 'rewrite', configured: true },
          graph_entity: { provider: 'siliconflow', model: 'graph', configured: true }
        },
        pipeline: {
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          },
          effective_source: {
            marker_tuning: {
              recognition_batch_size: 'default',
              detector_batch_size: 'default',
              layout_batch_size: 'default',
              ocr_error_batch_size: 'default',
              table_rec_batch_size: 'default',
              model_dtype: 'default'
            }
          }
        },
        status: { level: 'READY', reasons: [] }
      })
    });
  });

  await page.goto('http://127.0.0.1:3000/chat');
  await expect(page.getByTestId('global-runtime-status')).toContainText('运行正常');

  await expect(page.locator('[data-testid="nav-chat-link"]:visible').first()).toBeVisible();
  await expect(page.locator('[data-testid="nav-pipeline-link"]:visible').first()).toBeVisible();
  await expect(page.locator('[data-testid="nav-settings-link"]:visible').first()).toBeVisible();
  await expect(page.locator('[data-testid="nav-chat-link"]:visible').first()).toHaveClass(/bg-slate-900/);
  await expect(page.locator('[data-testid="nav-settings-link"]:visible').first()).not.toHaveClass(/bg-slate-900/);

  await page.locator('[data-testid="nav-settings-link"]:visible').first().click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByText('统一配置 LLM 连接')).toBeVisible();
  await expect(page.locator('[data-testid="nav-settings-link"]:visible').first()).toHaveClass(/bg-slate-900/);
  await expect(page.locator('[data-testid="nav-chat-link"]:visible').first()).not.toHaveClass(/bg-slate-900/);
});

test('shell keeps usable when runtime-overview returns html 404', async ({ page }) => {
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'text/html',
      body: '<!DOCTYPE html><html><body>not found</body></html>'
    });
  });

  await page.goto('http://127.0.0.1:3000/chat');

  await expect(page.getByTestId('global-runtime-status')).toContainText('运行态概览加载失败');
  await expect(page.locator('[data-testid="nav-chat-link"]:visible').first()).toBeVisible();
  await expect(page.locator('[data-testid="nav-settings-link"]:visible').first()).toBeVisible();
});
