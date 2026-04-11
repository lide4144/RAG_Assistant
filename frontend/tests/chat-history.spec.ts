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

  await page.locator('button').filter({ hasText: '昨天的研究会话' }).first().click();
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

test('chat page blocks formal send when planner runtime is unavailable', async ({ page }) => {
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
          graph_entity: { provider: 'siliconflow', model: 'DeepSeek-V3.2', configured: true },
          sufficiency_judge: { provider: 'siliconflow', model: 'Qwen/Qwen2.5-7B-Instruct', configured: true }
        },
        planner: {
          service_mode: 'production',
          use_llm: true,
          provider: 'openai',
          api_base: 'https://planner.example.com/v1',
          model: 'gpt-4.1-mini',
          timeout_ms: 9000,
          configured: false,
          formal_chat_available: false,
          blocked: true,
          block_reason_code: 'planner_missing_api_key',
          block_reason_message: 'Planner Runtime 当前不可服务，请先修复规划模型配置。',
          source: 'runtime'
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

  await expect(page.getByRole('button', { name: '发送' })).toBeDisabled();
  await page.getByRole('button', { name: /总结当前知识库里关于 GraphRAG 的核心方法差异/ }).click();
  await expect(page.getByText('Planner Runtime 当前不可服务，请先修复规划模型配置。 请先前往')).toBeVisible();
});

test('chat page restores a background job after reload', async ({ page }) => {
  let jobStatusCalls = 0;

  await page.addInitScript(() => {
    class MockSocket {
      static OPEN = 1;
      readyState = 1;
      listeners: Record<string, Array<(event: Event | MessageEvent<string>) => void>> = {};
      onopen: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;

      constructor(_url: string) {
        setTimeout(() => this.emitEvent('open', new Event('open')), 0);
      }

      addEventListener(type: string, listener: (event: Event | MessageEvent<string>) => void) {
        this.listeners[type] = this.listeners[type] ?? [];
        this.listeners[type].push(listener);
      }

      removeEventListener(type: string, listener: (event: Event | MessageEvent<string>) => void) {
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
        const parsed = JSON.parse(raw) as { type?: string; payload?: { jobId?: string } };
        if (parsed.type !== 'job_subscribe' || parsed.payload?.jobId !== 'job_planner_restore_1') {
          return;
        }
        const emit = (payload: unknown, ms: number) => {
          setTimeout(() => {
            this.emitEvent('message', new MessageEvent('message', { data: JSON.stringify(payload) }));
          }, ms);
        };
        emit(
          {
            type: 'message',
            jobId: 'job_planner_restore_1',
            seq: 1,
            createdAt: '2026-04-01T00:00:01Z',
            traceId: 'trace_restore_1',
            mode: 'local',
            content: '第一段'
          },
          10
        );
        emit(
          {
            type: 'message',
            jobId: 'job_planner_restore_1',
            seq: 2,
            createdAt: '2026-04-01T00:00:02Z',
            traceId: 'trace_restore_1',
            mode: 'local',
            content: '第二段'
          },
          20
        );
        emit(
          {
            type: 'sources',
            jobId: 'job_planner_restore_1',
            seq: 3,
            createdAt: '2026-04-01T00:00:03Z',
            traceId: 'trace_restore_1',
            mode: 'local',
            runId: 'run_restore_1',
            sources: [
              {
                source_type: 'local',
                source_id: 'paper-1',
                title: '恢复测试论文',
                snippet: '这是恢复后的来源片段',
                locator: 'p.3',
                score: 0.98
              }
            ]
          },
          30
        );
        emit(
          {
            type: 'messageEnd',
            jobId: 'job_planner_restore_1',
            seq: 4,
            createdAt: '2026-04-01T00:00:03Z',
            traceId: 'trace_restore_1',
            mode: 'local',
            runId: 'run_restore_1'
          },
          40
        );
      }

      close() {
        this.readyState = 3;
        this.emitEvent('close', new CloseEvent('close'));
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
          graph_entity: { provider: 'siliconflow', model: 'DeepSeek-V3.2', configured: true },
          sufficiency_judge: { provider: 'siliconflow', model: 'Qwen/Qwen2.5-7B-Instruct', configured: true }
        },
        planner: {
          service_mode: 'production',
          provider: 'openai',
          api_base: 'https://planner.example.com/v1',
          model: 'gpt-4.1-mini',
          timeout_ms: 9000,
          configured: true,
          formal_chat_available: true,
          blocked: false,
          source: 'runtime'
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

  await page.route('**/api/jobs?state=queued,running&limit=100', async (route) => {
    const active = jobStatusCalls < 2;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        active
          ? [
              {
                job_id: 'job_planner_restore_1',
                kind: 'planner_chat',
                state: 'running',
                created_at: '2026-04-01T00:00:00Z',
                updated_at: '2026-04-01T00:00:01Z',
                accepted: true,
                session_id: 'restore-session-1',
                trace_id: 'trace_restore_1',
                progress_stage: 'running',
                latest_output_text: '第一段'
              }
            ]
          : []
      )
    });
  });

  await page.route('**/api/jobs/planner', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        job: {
          job_id: 'job_planner_restore_1',
          kind: 'planner_chat',
          state: 'queued',
          created_at: '2026-04-01T00:00:00Z',
          updated_at: '2026-04-01T00:00:00Z',
          accepted: true,
          session_id: 'restore-session-1',
          trace_id: 'trace_restore_1',
          progress_stage: 'queued',
          latest_output_text: ''
        }
      })
    });
  });

  await page.route('**/api/jobs/job_planner_restore_1', async (route) => {
    jobStatusCalls += 1;
    const done = jobStatusCalls >= 3;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job_planner_restore_1',
        kind: 'planner_chat',
        state: done ? 'succeeded' : 'running',
        created_at: '2026-04-01T00:00:00Z',
        updated_at: done ? '2026-04-01T00:00:03Z' : '2026-04-01T00:00:01Z',
        accepted: true,
        session_id: 'restore-session-1',
        trace_id: 'trace_restore_1',
        run_id: done ? 'run_restore_1' : undefined,
        progress_stage: done ? 'completed' : 'running',
        latest_output_text: done ? '第一段第二段' : '第一段'
      })
    });
  });

  await page.route('**/api/jobs/job_planner_restore_1/events**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  await page.goto('http://127.0.0.1:3000/chat');
  await page.evaluate(() => {
    localStorage.setItem(
      'rag-workbench-chat-history-v1',
      JSON.stringify({
        sessions: [
          {
            id: 'restore-session-1',
            title: '恢复中的会话',
            createdAt: '2026-04-01T00:00:00Z',
            updatedAt: '2026-04-01T00:00:00Z',
            preview: '',
            messageCount: 0,
            messages: []
          }
        ]
      })
    );
  });
  await page.reload();

  await page.getByPlaceholder('例如：比较这两篇论文的方法差异，并用中文解释各自优缺点。').fill('请继续生成恢复测试回答');
  await page.getByRole('button', { name: '发送' }).click();

  await expect(page.getByRole('article').filter({ hasText: '请继续生成恢复测试回答' }).first()).toBeVisible();
  await expect(page.getByRole('article').filter({ hasText: '第一段第二段' }).first()).toBeVisible();

  await page.reload();

  await expect(page.getByRole('article').filter({ hasText: '请继续生成恢复测试回答' }).first()).toBeVisible();
  await expect(page.getByRole('article').filter({ hasText: '第一段第二段' }).first()).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('恢复测试论文')).toBeVisible();
});

test('chat session stays on the same conversation after visiting settings during a running job', async ({ page }) => {
  let jobStatusCalls = 0;

  await page.addInitScript(() => {
    class MockSocket {
      static OPEN = 1;
      readyState = 1;
      listeners: Record<string, Array<(event: Event | MessageEvent<string>) => void>> = {};
      onopen: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;

      constructor(_url: string) {
        setTimeout(() => this.emitEvent('open', new Event('open')), 0);
      }

      addEventListener(type: string, listener: (event: Event | MessageEvent<string>) => void) {
        this.listeners[type] = this.listeners[type] ?? [];
        this.listeners[type].push(listener);
      }

      removeEventListener(type: string, listener: (event: Event | MessageEvent<string>) => void) {
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
        const parsed = JSON.parse(raw) as { type?: string; payload?: { jobId?: string } };
        if (parsed.type !== 'job_subscribe' || parsed.payload?.jobId !== 'job_planner_nav_1') {
          return;
        }
        const emit = (payload: unknown, ms: number) => {
          setTimeout(() => {
            this.emitEvent('message', new MessageEvent('message', { data: JSON.stringify(payload) }));
          }, ms);
        };
        emit(
          {
            type: 'message',
            jobId: 'job_planner_nav_1',
            seq: 1,
            createdAt: '2026-04-01T00:00:01Z',
            traceId: 'trace_nav_1',
            mode: 'local',
            content: '第一段'
          },
          10
        );
        emit(
          {
            type: 'message',
            jobId: 'job_planner_nav_1',
            seq: 2,
            createdAt: '2026-04-01T00:00:02Z',
            traceId: 'trace_nav_1',
            mode: 'local',
            content: '第二段'
          },
          120
        );
        emit(
          {
            type: 'messageEnd',
            jobId: 'job_planner_nav_1',
            seq: 3,
            createdAt: '2026-04-01T00:00:03Z',
            traceId: 'trace_nav_1',
            mode: 'local',
            runId: 'run_nav_1'
          },
          150
        );
      }

      close() {
        this.readyState = 3;
        this.emitEvent('close', new CloseEvent('close'));
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
          graph_entity: { provider: 'siliconflow', model: 'DeepSeek-V3.2', configured: true },
          sufficiency_judge: { provider: 'siliconflow', model: 'Qwen/Qwen2.5-7B-Instruct', configured: true }
        },
        planner: {
          service_mode: 'production',
          provider: 'openai',
          api_base: 'https://planner.example.com/v1',
          model: 'gpt-4.1-mini',
          timeout_ms: 9000,
          configured: true,
          formal_chat_available: true,
          blocked: false,
          source: 'runtime'
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
        jobs: {
          active: [],
          settings_locked: false
        },
        status: { level: 'READY', reasons: [] }
      })
    });
  });

  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        answer: { provider: 'openai', api_base: 'https://api.openai.com/v1', model: 'gpt-4.1-mini' },
        embedding: { provider: 'ollama', api_base: 'http://127.0.0.1:11434/v1', model: 'nomic-embed-text' },
        rerank: { provider: 'siliconflow', api_base: 'https://api.siliconflow.cn/v1', model: 'Qwen/Qwen3-Reranker-8B' },
        rewrite: { provider: 'ollama', api_base: 'http://127.0.0.1:11434/v1', model: 'qwen2.5:3b' },
        graph_entity: { provider: 'openai', api_base: 'https://api.siliconflow.cn/v1', model: 'DeepSeek-V3.2' },
        sufficiency_judge: { provider: 'openai', api_base: 'https://api.siliconflow.cn/v1', model: 'Qwen/Qwen2.5-7B-Instruct' }
      })
    });
  });

  await page.route('**/api/admin/pipeline-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        saved: {
          marker_enabled: false,
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          }
        },
        effective: {
          marker_enabled: false,
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          }
        },
        effective_source: {
          marker_tuning: {}
        }
      })
    });
  });

  await page.route('**/api/admin/planner-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        service_mode: 'production',
        provider: 'openai',
        api_base: 'https://planner.example.com/v1',
        model: 'gpt-4.1-mini',
        timeout_ms: 9000
      })
    });
  });

  await page.route('**/api/jobs?state=queued,running&limit=100', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          job_id: 'job_planner_nav_1',
          kind: 'planner_chat',
          state: 'running',
          created_at: '2026-04-01T00:00:00Z',
          updated_at: '2026-04-01T00:00:01Z',
          accepted: true,
          session_id: 'fresh-session-1',
          trace_id: 'trace_nav_1',
          progress_stage: 'running',
          latest_output_text: '第一段'
        }
      ])
    });
  });

  await page.route('**/api/jobs/planner', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        job: {
          job_id: 'job_planner_nav_1',
          kind: 'planner_chat',
          state: 'queued',
          created_at: '2026-04-01T00:00:00Z',
          updated_at: '2026-04-01T00:00:00Z',
          accepted: true,
          session_id: 'fresh-session-1',
          trace_id: 'trace_nav_1',
          progress_stage: 'queued',
          latest_output_text: ''
        }
      })
    });
  });

  await page.route('**/api/jobs/job_planner_nav_1', async (route) => {
    jobStatusCalls += 1;
    const done = jobStatusCalls >= 2;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job_planner_nav_1',
        kind: 'planner_chat',
        state: done ? 'succeeded' : 'running',
        created_at: '2026-04-01T00:00:00Z',
        updated_at: done ? '2026-04-01T00:00:03Z' : '2026-04-01T00:00:01Z',
        accepted: true,
        session_id: 'fresh-session-1',
        trace_id: 'trace_nav_1',
        run_id: done ? 'run_nav_1' : undefined,
        progress_stage: done ? 'completed' : 'running',
        latest_output_text: done ? '第一段第二段' : '第一段'
      })
    });
  });

  await page.route('**/api/jobs/job_planner_nav_1/events**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([])
    });
  });

  await page.goto('http://127.0.0.1:3000/chat');
  await page.evaluate(() => {
    localStorage.removeItem('rag-workbench-chat-history-v1');
    localStorage.removeItem('rag-workbench-chat-active-session-v1');
  });
  await page.reload();

  await page.getByPlaceholder('例如：比较这两篇论文的方法差异，并用中文解释各自优缺点。').fill('切页后继续同一个会话');
  await page.getByRole('button', { name: '发送' }).click();

  await expect(page.getByTestId('chat-streaming-stage-card')).toBeVisible();
  await expect(page.getByRole('article').filter({ hasText: '切页后继续同一个会话' }).first()).toBeVisible();
  await expect(page.getByRole('article').filter({ hasText: '第一段' }).first()).toBeVisible();

  await page.locator('[data-testid="nav-settings-link"]:visible').first().click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByTestId('settings-shell-title')).toBeVisible();

  await page.locator('[data-testid="nav-chat-link"]:visible').first().click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole('article').filter({ hasText: '切页后继续同一个会话' }).first()).toBeVisible();
  await expect(page.getByRole('article').filter({ hasText: '第一段第二段' }).first()).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('切页后继续同一个会话')).not.toHaveCount(0);
  await expect(page.getByText('新对话')).toHaveCount(0);
});
