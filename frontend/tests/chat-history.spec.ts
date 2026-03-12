import { expect, test } from '@playwright/test';

test('chat page loads grouped local history and can switch or create sessions', async ({ page }) => {
  await page.addInitScript(() => {
    class MockSocket {
      static OPEN = 1;
      readyState = 1;
      onopen: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;

      constructor(_url: string) {
        setTimeout(() => this.onopen?.(new Event('open')), 0);
      }

      send() {}

      close() {
        this.readyState = 3;
        this.onclose?.(new CloseEvent('close'));
      }
    }

    // @ts-expect-error test-time override
    window.WebSocket = MockSocket;
  });

  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4.1-mini', configured: true },
          embedding: { provider: 'siliconflow', model: 'bge-m3', configured: true },
          rerank: { provider: 'siliconflow', model: 'Qwen/Qwen3-Reranker-8B', configured: true },
          rewrite: { provider: 'ollama', model: 'qwen2.5:3b', configured: true },
          graph_entity: { provider: 'siliconflow', model: 'DeepSeek-V3.2', configured: true }
        },
        pipeline: {
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          }
        },
        status: { level: 'READY', reasons: [] }
      })
    });
  });

  await page.goto('http://127.0.0.1:3000/chat');
  await page.evaluate(() => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9, 30).toISOString();
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 20, 15).toISOString();
    const earlier = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 3, 14, 0).toISOString();

    localStorage.setItem(
      'rag-workbench-chat-history-v1',
      JSON.stringify({
        sessions: [
          {
            id: 'session-today',
            title: '今天的研究会话',
            createdAt: today,
            updatedAt: today,
            preview: '今天的回答摘要',
            messageCount: 2,
            messages: [
              { id: 'today-user', role: 'user', content: '今天的问题', mode: 'local', status: 'done' },
              { id: 'today-assistant', role: 'assistant', content: '今天的回答摘要', mode: 'local', status: 'done', sources: [] }
            ]
          },
          {
            id: 'session-yesterday',
            title: '昨天的研究会话',
            createdAt: yesterday,
            updatedAt: yesterday,
            preview: '昨天的回答摘要',
            messageCount: 2,
            messages: [
              { id: 'y-user', role: 'user', content: '昨天的问题', mode: 'local', status: 'done' },
              { id: 'y-assistant', role: 'assistant', content: '昨天的回答摘要', mode: 'local', status: 'done', sources: [] }
            ]
          },
          {
            id: 'session-earlier',
            title: '更早的研究会话',
            createdAt: earlier,
            updatedAt: earlier,
            preview: '更早的回答摘要',
            messageCount: 2,
            messages: [
              { id: 'e-user', role: 'user', content: '更早的问题', mode: 'local', status: 'done' },
              { id: 'e-assistant', role: 'assistant', content: '更早的回答摘要', mode: 'local', status: 'done', sources: [] }
            ]
          }
        ]
      })
    );
  });
  await page.reload();

  await expect(page.getByTestId('chat-shell-title')).toBeVisible();
  await expect(page.getByTestId('chat-history-groups')).toContainText('今天');
  await expect(page.getByTestId('chat-history-groups')).toContainText('昨天');
  await expect(page.getByTestId('chat-history-groups')).toContainText('更早');
  await expect(page.locator('[data-testid^="chat-delete-session-"]')).toHaveCount(3);

  await page.getByRole('button', { name: /昨天的研究会话/ }).click();
  await expect(page.getByRole('article').filter({ hasText: '昨天的回答摘要' })).toBeVisible();

  await page.getByTestId('chat-new-session-btn').click();
  await expect(page.getByText('向你的研究知识库提问')).toBeVisible();
  await expect(page.getByText('新对话')).toBeVisible();
  await expect(page.locator('[data-testid^="chat-delete-session-"]')).toHaveCount(3);

  await page.getByTestId('chat-delete-session-session-yesterday').click();
  await expect(page.getByTestId('chat-history-groups')).not.toContainText('昨天的研究会话');
  await expect(page.locator('[data-testid^="chat-delete-session-"]')).toHaveCount(2);

  const stored = await page.evaluate(() => localStorage.getItem('rag-workbench-chat-history-v1'));
  expect(stored).toBeTruthy();
  const parsed = JSON.parse(stored ?? '{"sessions":[]}') as { sessions: Array<{ id: string }> };
  expect(parsed.sessions.map((item) => item.id)).not.toContain('session-yesterday');
});
