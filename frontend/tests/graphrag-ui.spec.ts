import { expect, test } from '@playwright/test';

test('chat page shows empty state and blocks usage when model is not configured', async ({ page }) => {
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: '', model: '', configured: false },
          embedding: { provider: 'siliconflow', model: 'bge', configured: true },
          rerank: { provider: '', model: '', configured: false },
          rewrite: { provider: '', model: '', configured: false },
          graph_entity: { provider: '', model: '', configured: false }
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
        status: { level: 'BLOCKED', reasons: ['answer stage is not configured'] }
      })
    });
  });

  await page.addInitScript(() => {
    class BlockedStateSocket {
      static OPEN = 1;
      readyState = 1;
      listeners: Record<string, Array<(ev: Event | MessageEvent<string>) => void>> = {};
      onopen: ((ev: Event) => void) | null = null;
      onmessage: ((ev: MessageEvent<string>) => void) | null = null;
      onclose: ((ev: CloseEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;

      constructor(_url: string) {
        setTimeout(() => this.emitEvent('open', new Event('open')), 0);
      }

      addEventListener(type: string, listener: (ev: Event | MessageEvent<string>) => void) {
        this.listeners[type] = this.listeners[type] ?? [];
        this.listeners[type].push(listener);
      }

      removeEventListener(type: string, listener: (ev: Event | MessageEvent<string>) => void) {
        this.listeners[type] = (this.listeners[type] ?? []).filter((item) => item !== listener);
      }

      emitEvent(type: string, event: Event | MessageEvent<string>) {
        if (type === 'open') this.onopen?.(event as Event);
        if (type === 'message') this.onmessage?.(event as MessageEvent<string>);
        if (type === 'close') this.onclose?.(event as CloseEvent);
        if (type === 'error') this.onerror?.(event as Event);
        for (const listener of this.listeners[type] ?? []) {
          listener(event);
        }
      }

      send(_raw: string) {}

      close() {
        this.readyState = 3;
        this.emitEvent('close', new CloseEvent('close'));
      }
    }

    // @ts-expect-error test-time override
    window.WebSocket = BlockedStateSocket;
  });

  await page.goto('http://127.0.0.1:3000/chat');

  await expect(page.getByText('向你的研究知识库提问')).toBeVisible();
  await expect(page.getByRole('button', { name: '总结当前知识库里关于 GraphRAG 的核心方法差异' })).toBeVisible();
  await expect(page.getByText('当前推理模型不可用。请先前往')).toBeVisible();
  await expect(page.getByRole('main').getByRole('link', { name: '模型设置', exact: true })).toBeVisible();
  await expect(page.getByTestId('chat-session-aside')).toContainText('本次会话速览');
  await expect(page.getByTestId('chat-session-aside')).toContainText('开始提问后，这里会持续汇总当前会话的引用和阅读重点。');
  await expect(page.getByTestId('global-runtime-status')).toContainText('已连接');
  await page.locator('footer input').first().fill('blocked 下尝试发送');
  await expect(page.getByRole('button', { name: '发送' })).toBeDisabled();
});

test('chat page renders markdown code and math with stream response', async ({ page }) => {
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
          effective_source: { marker_tuning: {} }
        },
        status: { level: 'READY', reasons: [] }
      })
    });
  });

  await page.addInitScript(() => {
    class MockSocket {
      static OPEN = 1;
      readyState = 1;
      listeners: Record<string, Array<(ev: Event | MessageEvent<string>) => void>> = {};
      onopen: ((ev: Event) => void) | null = null;
      onmessage: ((ev: MessageEvent<string>) => void) | null = null;
      onclose: ((ev: CloseEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;

      constructor(_url: string) {
        setTimeout(() => this.emitEvent('open', new Event('open')), 0);
      }

      addEventListener(type: string, listener: (ev: Event | MessageEvent<string>) => void) {
        this.listeners[type] = this.listeners[type] ?? [];
        this.listeners[type].push(listener);
      }

      removeEventListener(type: string, listener: (ev: Event | MessageEvent<string>) => void) {
        this.listeners[type] = (this.listeners[type] ?? []).filter((item) => item !== listener);
      }

      emitEvent(type: string, event: Event | MessageEvent<string>) {
        if (type === 'open') this.onopen?.(event as Event);
        if (type === 'message') this.onmessage?.(event as MessageEvent<string>);
        if (type === 'close') this.onclose?.(event as CloseEvent);
        if (type === 'error') this.onerror?.(event as Event);
        for (const listener of this.listeners[type] ?? []) {
          listener(event);
        }
      }

      send(raw: string) {
        const parsed = JSON.parse(raw) as { type?: string; payload?: { query?: string } };
        if (parsed.type !== 'chat') {
          return;
        }
        const traceId = 'trace-chat-1';
        const parts = [
          '这是代码与公式示例。\n\n```ts\nconst answer = 42;\n```\n\n',
          '公式：$E=mc^2$'
        ];
        setTimeout(() => {
          this.emitEvent(
            'message',
            new MessageEvent('message', {
              data: JSON.stringify({ type: 'message', traceId, mode: 'local', content: parts[0] })
            })
          );
        }, 20);
        setTimeout(() => {
          this.emitEvent(
            'message',
            new MessageEvent('message', {
              data: JSON.stringify({ type: 'message', traceId, mode: 'local', content: parts[1] })
            })
          );
        }, 40);
        setTimeout(() => {
          this.emitEvent(
            'message',
            new MessageEvent('message', {
              data: JSON.stringify({ type: 'messageEnd', traceId, mode: 'local' })
            })
          );
        }, 60);
      }

      close() {
        this.readyState = 3;
        this.emitEvent('close', new CloseEvent('close'));
      }
    }

    // @ts-expect-error test-time override
    window.WebSocket = MockSocket;
  });

  await page.goto('http://127.0.0.1:3000/chat');
  await expect(page.getByTestId('global-runtime-status')).toContainText('已连接');
  await expect(page.getByText('当前推理模型不可用。请先前往')).toHaveCount(0);
  const input = page.locator('footer input').first();
  const sendBtn = page.getByRole('button', { name: '发送' });
  await expect(input).toBeVisible();
  await input.fill('给我代码与公式');
  await expect(sendBtn).toBeEnabled();
  await sendBtn.click();

  await expect(page.locator('pre code')).toContainText('const answer = 42;');
  await expect(page.locator('.katex').first()).toBeVisible();
});
