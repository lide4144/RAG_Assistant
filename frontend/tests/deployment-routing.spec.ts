import { expect, test, type Page } from '@playwright/test';

async function installSocketRecorder(page: Page) {
  await page.addInitScript(() => {
    class RecordingSocket {
      static OPEN = 1;
      readyState = 1;
      onopen: ((ev: Event) => void) | null = null;
      onmessage: ((ev: MessageEvent<string>) => void) | null = null;
      onclose: ((ev: CloseEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;

      constructor(url: string | URL) {
        const bucket = ((window as typeof window & { __wsUrls?: string[] }).__wsUrls ??= []);
        bucket.push(String(url));
        window.setTimeout(() => this.onopen?.(new Event('open')), 0);
      }

      send(_raw: string) {}

      close() {
        this.readyState = 3;
        this.onclose?.(new CloseEvent('close'));
      }
    }

    // @ts-expect-error test-time override
    window.WebSocket = RecordingSocket;
  });
}

test('chat page derives websocket url from current origin instead of localhost', async ({ page }) => {
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4.1-mini', configured: true },
          embedding: { provider: 'ollama', model: 'bge', configured: true },
          rerank: { provider: 'ollama', model: 'rerank', configured: true },
          rewrite: { provider: 'ollama', model: 'rewrite', configured: true },
          graph_entity: { provider: 'ollama', model: 'graph', configured: true }
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

  await installSocketRecorder(page);
  await page.goto('http://127.0.0.1:3000/chat');

  await expect(page.getByText('🟢 已连接').first()).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as typeof window & { __wsUrls?: string[] }).__wsUrls ?? [])).toEqual([
    'ws://127.0.0.1:3000/ws'
  ]);
});

test('pipeline page derives websocket url from current origin instead of localhost', async ({ page }) => {
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4.1-mini', configured: true },
          embedding: { provider: 'ollama', model: 'bge', configured: true },
          rerank: { provider: 'ollama', model: 'rerank', configured: true },
          rewrite: { provider: 'ollama', model: 'rewrite', configured: true },
          graph_entity: { provider: 'ollama', model: 'graph', configured: true }
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
  await page.route('**/api/library/import-latest', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        added: 0,
        skipped: 0,
        failed: 0,
        total_papers: 0,
        failure_reasons: [],
        pipeline_stages: []
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
  await page.route('**/api/library/marker-artifacts', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] })
    });
  });

  await installSocketRecorder(page);
  await page.goto('http://127.0.0.1:3000/pipeline');

  await expect(page.locator('[data-testid="nav-pipeline-link"]:visible').first()).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as typeof window & { __wsUrls?: string[] }).__wsUrls ?? [])).toEqual([
    'ws://127.0.0.1:3000/ws'
  ]);
});
