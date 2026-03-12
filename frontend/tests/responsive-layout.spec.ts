import { expect, test } from '@playwright/test';

test('core pages remain usable on mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });

  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4o-mini', configured: true },
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
          effective_source: { marker_tuning: {} }
        },
        status: { level: 'READY', reasons: [] }
      })
    });
  });

  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ configured: false }) });
  });
  await page.route('**/api/admin/pipeline-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        saved: { marker_tuning: { recognition_batch_size: 2, detector_batch_size: 2, layout_batch_size: 2, ocr_error_batch_size: 1, table_rec_batch_size: 1, model_dtype: 'float16' } },
        effective: { marker_tuning: { recognition_batch_size: 2, detector_batch_size: 2, layout_batch_size: 2, ocr_error_batch_size: 1, table_rec_batch_size: 1, model_dtype: 'float16' } },
        effective_source: { marker_tuning: {} }
      })
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
        pipeline_stages: [{ stage: 'import', state: 'succeeded', updated_at: '2026-03-06T00:00:01Z' }]
      })
    });
  });

  await page.route('**/api/library/import-history?limit=10', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
  });

  await page.goto('http://127.0.0.1:3000/chat');
  await expect(page.locator('[data-testid="nav-chat-link"]:visible').first()).toBeVisible();
  await expect(page.getByTestId('chat-shell-title')).toBeVisible();

  await page.locator('[data-testid="nav-pipeline-link"]:visible').first().click();
  await expect(page.getByRole('heading', { name: '知识库处理进度中心' })).toBeVisible();

  await page.locator('[data-testid="nav-settings-link"]:visible').first().click();
  await expect(page.getByTestId('settings-shell-title')).toBeVisible();
});
