import { expect, test } from '@playwright/test';

test('pipeline workbench renders task center and reacts to task events', async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/admin/llm-config')) {
        return new Response(JSON.stringify({ configured: false }), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        });
      }
      if (url.includes('/api/library/import-latest')) {
        return new Response(
          JSON.stringify({
            added: 3,
            skipped: 1,
            failed: 1,
            failure_reasons: ['bad pdf'],
            pipeline_stages: [
              { stage: 'import', state: 'succeeded', updated_at: '2026-03-06T00:00:01Z' },
              { stage: 'clean', state: 'succeeded', updated_at: '2026-03-06T00:00:01Z' },
              { stage: 'index', state: 'running', updated_at: '2026-03-06T00:00:02Z' },
              { stage: 'graph_build', state: 'not_started', updated_at: null, message: '尚未启动图构建任务' }
            ]
          }),
          {
            status: 200,
            headers: { 'content-type': 'application/json' }
          }
        );
      }
      if (url.includes('/api/tasks/') && url.includes('/cancel')) {
        return new Response(
          JSON.stringify({
            task_id: 'task-1',
            task_kind: 'graph_build',
            state: 'cancelled',
            cancelled: true,
            updated_at: '2026-03-06T00:00:05Z',
            message: '任务取消请求已接收'
          }),
          {
            status: 200,
            headers: { 'content-type': 'application/json' }
          }
        );
      }
      return originalFetch(input, init);
    };

    class MockSocket {
      static OPEN = 1;
      readyState = 1;
      startCount = 0;
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
        const parsed = JSON.parse(raw) as { type?: string };
        if (parsed.type !== 'task_start_graph_build') {
          return;
        }
        this.startCount += 1;
        const emit = (payload: unknown, ms: number) => {
          setTimeout(() => {
            this.emitEvent(
              'message',
              new MessageEvent('message', {
                data: JSON.stringify(payload)
              })
            );
          }, ms);
        };

        emit(
          {
            type: 'taskState',
            taskId: 'task-1',
            taskKind: 'graph_build',
            state: 'running',
            accepted: this.startCount === 2 ? false : true,
            updatedAt: '2026-03-06T00:00:01Z'
          },
          20
        );
        if (this.startCount === 1) {
          emit(
            {
              type: 'taskResult',
              taskId: 'task-1',
              taskKind: 'graph_build',
              state: 'failed',
              error: { stage: 'extract_entities', message: 'boom', recovery: 'retry' },
              updatedAt: '2026-03-06T00:00:03Z'
            },
            40
          );
          return;
        }
        emit(
          {
            type: 'taskProgress',
            taskId: 'task-1',
            taskKind: 'graph_build',
            state: 'running',
            stage: 'extract_entities',
            processed: 5,
            total: 10,
            elapsedMs: 1200,
            message: '5/10',
            updatedAt: '2026-03-06T00:00:02Z'
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

  await page.goto('http://127.0.0.1:3000/chat');
  await expect(page.locator('[data-testid="nav-pipeline-link"]:visible').first()).toBeVisible();
  await page.locator('[data-testid="nav-pipeline-link"]:visible').first().click();

  await expect(page.getByRole('heading', { name: '知识库构建流水线' })).toBeVisible();
  await expect(page.getByTestId('pipeline-start-graph-build-btn')).toBeEnabled();
  await page.getByTestId('pipeline-start-graph-build-btn').click();
  await expect(page.getByTestId('pipeline-retry-graph-build-btn')).toBeVisible();
  await page.getByTestId('pipeline-retry-graph-build-btn').click();

  await expect(page.getByTestId('pipeline-idempotent-hint')).toContainText('复用任务 task-1');
  await expect(page.getByTestId('pipeline-stage-text')).toContainText('extract_entities');
  await expect(page.getByTestId('pipeline-progress-text')).toContainText('5/10');
  await expect(page.getByTestId('pipeline-elapsed-text')).toContainText('1200ms');
  await expect(page.getByTestId('pipeline-cancel-graph-build-btn')).toBeVisible();
  await page.getByTestId('pipeline-cancel-graph-build-btn').click();
  await expect(page.getByTestId('pipeline-stage-text')).toContainText('cancelled');

  await expect(page.getByTestId('pipeline-import-added')).toContainText('3');
  await expect(page.getByTestId('pipeline-import-skipped')).toContainText('1');
  await expect(page.getByTestId('pipeline-import-failed')).toContainText('1');
  await expect(page.getByTestId('pipeline-import-failure-reasons')).toContainText('bad pdf');
  await expect(page.getByTestId('pipeline-stage-cards')).toContainText('导入');
  await expect(page.getByTestId('pipeline-stage-cards')).toContainText('索引');

  await page.getByTestId('pipeline-go-chat-btn').click();
  await expect(page.getByText('知识问答与证据追踪')).toBeVisible();
});

test('pipeline workbench covers marker artifact actions and delete confirmation', async ({ page }) => {
  const deleteRequests: Array<{ key?: string }> = [];
  let clipboardText = '';
  let artifactItems = [
    {
      key: 'indexes:vec_index',
      group: 'indexes',
      path: '/repo/data/indexes/vec_index.json',
      file_name: 'vec_index.json',
      artifact_type: 'vector-index',
      related_stage: 'index',
      exists: true,
      status: 'healthy',
      size_bytes: 1024,
      updated_at: '2026-03-09T02:00:00Z',
      health_message: '产物可用',
      actions: [
        { kind: 'copy_path', label: '复制路径' },
        { kind: 'rebuild', label: '重建入口' },
        {
          kind: 'delete',
          label: '删除产物',
          confirm_title: '删除 vec_index.json',
          confirm_message: '删除后会影响 index 阶段，可能需要重新导入或重建。确认继续吗？'
        }
      ]
    },
    {
      key: 'processed:chunks_clean',
      group: 'processed',
      path: '/repo/data/processed/chunks_clean.jsonl',
      file_name: 'chunks_clean.jsonl',
      artifact_type: 'clean-chunks',
      related_stage: 'clean',
      exists: true,
      status: 'stale',
      size_bytes: 2048,
      updated_at: '2026-03-08T23:00:00Z',
      health_message: '产物早于最近一次运行，建议检查是否需要重建',
      actions: [
        { kind: 'copy_path', label: '复制路径' },
        { kind: 'rebuild', label: '重建入口' },
        {
          kind: 'delete',
          label: '删除产物',
          confirm_title: '删除 chunks_clean.jsonl',
          confirm_message: '删除后会影响 clean 阶段，可能需要重新导入或重建。确认继续吗？'
        }
      ]
    }
  ];

  await page.addInitScript(() => {
    let copiedText = '';
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          copiedText = value;
          (window as typeof window & { __copiedArtifactPath?: string }).__copiedArtifactPath = value;
        }
      }
    });
  });

  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4o-mini', configured: true },
          embedding: { provider: 'siliconflow', model: 'bge', configured: true },
          rerank: { provider: 'siliconflow', model: 'rerank', configured: true },
          rewrite: { provider: 'ollama', model: 'rewrite', configured: true },
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
          effective_source: { marker_tuning: {} },
          marker_llm: {
            use_llm: true,
            llm_service: 'marker.services.openai.OpenAIService',
            configured: true,
            status: 'ready',
            summary_fields: [{ field: 'openai_model', value: 'gpt-4.1-mini', source: 'runtime' }]
          },
          last_ingest: {
            degraded: true,
            fallback_reason: 'marker parse timeout',
            fallback_path: 'marker -> legacy (parse_timeout)',
            confidence_note: '当前结果来自降级路径。'
          },
          artifacts: { counts: { healthy: 1, missing: 0, stale: 1 } }
        },
        status: { level: 'DEGRADED', reasons: ['marker parse timeout'] }
      })
    });
  });
  await page.route('**/api/library/import-latest', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        added: 2,
        skipped: 0,
        failed: 0,
        total_papers: 2,
        degraded: true,
        fallback_reason: 'marker parse timeout',
        fallback_path: 'marker -> legacy (parse_timeout)',
        confidence_note: '当前结果来自降级路径。',
        failure_reasons: [],
        parser_diagnostics: [
          {
            paper_id: 'pdf_a639448e61be',
            source_uri: 'pdf://sha1/a639448e61be3ab2',
            parser_engine: 'legacy',
            parser_fallback: true,
            parser_fallback_stage: 'parse_timeout',
            parser_fallback_reason: 'marker parse timeout after 120.0s',
            marker_attempt_duration_sec: 120.114,
            marker_stage_timings: {}
          }
        ],
        artifact_summary: {
          counts: { healthy: 1, missing: 0, stale: 1 }
        },
        pipeline_stages: [
          { stage: 'import', state: 'failed_with_fallback', updated_at: '2026-03-09T02:00:00Z', detail: 'marker parse timeout' },
          { stage: 'clean', state: 'failed_with_fallback', updated_at: '2026-03-09T02:00:00Z', detail: 'marker parse timeout' },
          { stage: 'index', state: 'succeeded', updated_at: '2026-03-09T02:00:00Z' },
          { stage: 'graph_build', state: 'not_started', updated_at: null, message: '尚未启动图构建任务' }
        ]
      })
    });
  });
  await page.route('**/api/library/import-history**', async (route) => {
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
      body: JSON.stringify({
        items: artifactItems,
        summary: {
          counts: { healthy: 1, missing: 0, stale: 1 }
        },
        updated_at: '2026-03-09T02:00:00Z'
      })
    });
  });
  await page.route('**/api/library/marker-artifacts/delete', async (route) => {
    const payload = route.request().postDataJSON() as { key?: string };
    deleteRequests.push(payload);
    artifactItems = artifactItems.filter((item) => item.key !== payload.key);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        deleted: payload.key,
        path: '/repo/data/processed/chunks_clean.jsonl',
        message: '已删除 chunks_clean.jsonl'
      })
    });
  });

  await page.goto('http://127.0.0.1:3000/chat');
  await page.locator('[data-testid="nav-pipeline-link"]:visible').first().click();

  await expect(page.getByRole('heading', { name: '知识库构建流水线' })).toBeVisible();
  await expect(page.getByText('Index / processed 产物总览')).toBeVisible();
  await expect(page.getByText('Marker 解析诊断')).toBeVisible();
  await expect(page.getByTestId('pipeline-parser-diagnostics')).toContainText('marker parse timeout after 120.0s');
  await expect(page.getByTestId('pipeline-stage-cards')).toContainText('降级完成');
  await expect(page.getByTestId('artifact-card-indexes-vec-index')).toContainText('vec_index.json');
  await expect(page.getByTestId('artifact-card-processed-chunks-clean')).toContainText('chunks_clean.jsonl');

  await page.getByTestId('artifact-copy-indexes-vec-index').click();
  clipboardText = await page.evaluate(() => (window as typeof window & { __copiedArtifactPath?: string }).__copiedArtifactPath ?? '');
  expect(clipboardText).toBe('/repo/data/indexes/vec_index.json');
  await expect(page.getByText('已复制路径：/repo/data/indexes/vec_index.json')).toBeVisible();

  await page.getByTestId('artifact-rebuild-indexes-vec-index').click();
  await expect(page.getByText('请使用导入入口或索引流程重建 vec_index.json')).toBeVisible();

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('删除后会影响 clean 阶段');
    await dialog.accept();
  });
  await page.getByTestId('artifact-delete-processed-chunks-clean').click();

  await expect.poll(() => deleteRequests.length).toBe(1);
  expect(deleteRequests[0]).toEqual({ key: 'processed:chunks_clean' });
  await expect(page.getByText('已删除 chunks_clean.jsonl')).toBeVisible();
  await expect(page.getByTestId('artifact-card-processed-chunks-clean')).toHaveCount(0);
});
