import { expect, test, type Page } from '@playwright/test';

type StageKey = 'answer' | 'embedding' | 'rerank' | 'rewrite' | 'graph_entity';

type StagePayload = { provider: string; api_base: string; api_key: string; model: string };

type FullPayload = Record<StageKey, StagePayload>;

const allStages: StageKey[] = ['answer', 'embedding', 'rerank', 'rewrite', 'graph_entity'];

async function mockRuntimePanels(page: Page) {
  await page.route('**/api/admin/pipeline-config', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true })
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        saved: {
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
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          }
        },
        effective_source: { marker_tuning: {} }
      })
    });
  });
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4o-mini', configured: true },
          embedding: { provider: 'siliconflow', model: 'BAAI/bge-small-zh-v1.5', configured: true },
          rerank: { provider: 'siliconflow', model: 'BAAI/bge-reranker-base', configured: true },
          rewrite: { provider: 'ollama', model: 'Qwen2.5-3B-Instruct', configured: true },
          graph_entity: { provider: 'siliconflow', model: 'Pro/deepseek-ai/DeepSeek-V3.2', configured: true }
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
}

test('llm settings page stays usable when llm-config returns non-json html', async ({ page }) => {
  await mockRuntimePanels(page);
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'text/html',
      body: '<!DOCTYPE html><html><body>not found</body></html>'
    });
  });

  const pageErrors: string[] = [];
  page.on('pageerror', (error) => {
    pageErrors.push(error.message);
  });

  await page.goto('http://127.0.0.1:3000/settings');

  await expect(page.getByRole('heading', { name: '统一配置 LLM 连接' })).toBeVisible();
  await expect(page.getByTestId('llm-ready-text')).toBeVisible();
  expect(pageErrors.join('\n')).not.toContain("Unexpected token '<'");
});

test('llm settings panel can save and reload full-stage config', async ({ page }) => {
  let savedConfig: FullPayload | null = null;
  await mockRuntimePanels(page);

  await page.route('**/api/admin/llm-config', async (route) => {
    if (route.request().method() === 'GET') {
      if (!savedConfig) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ configured: false })
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          configured: true,
          answer: {
            provider: savedConfig.answer.provider,
            api_base: savedConfig.answer.api_base,
            model: savedConfig.answer.model,
            api_key_masked: 'ans***'
          },
          embedding: {
            provider: savedConfig.embedding.provider,
            api_base: savedConfig.embedding.api_base,
            model: savedConfig.embedding.model,
            api_key_masked: 'emb***'
          },
          rerank: {
            provider: savedConfig.rerank.provider,
            api_base: savedConfig.rerank.api_base,
            model: savedConfig.rerank.model,
            api_key_masked: 'rr***'
          },
          rewrite: {
            provider: savedConfig.rewrite.provider,
            api_base: savedConfig.rewrite.api_base,
            model: savedConfig.rewrite.model,
            api_key_masked: 'rw***'
          },
          graph_entity: {
            provider: savedConfig.graph_entity.provider,
            api_base: savedConfig.graph_entity.api_base,
            model: savedConfig.graph_entity.model,
            api_key_masked: 'ge***'
          }
        })
      });
      return;
    }

    const reqPayload = route.request().postDataJSON() as FullPayload;
    for (const stage of allStages) {
      expect(reqPayload[stage].model).toBeTruthy();
    }
    savedConfig = reqPayload;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, config: savedConfig })
    });
  });

  await page.route('**/api/admin/detect-models', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        raw_count: 2,
        models: [{ id: 'gpt-4o-mini' }, { id: 'gpt-4.1-mini' }]
      })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByRole('heading', { name: '统一配置 LLM 连接' })).toBeVisible();
  await expect(page.getByText('统一配置 LLM 连接')).toBeVisible();

  await page.getByTestId('llm-answer-api-base-input').fill('https://answer.example.com/v1');
  await page.getByTestId('llm-answer-api-key-input').fill('sk-answer');
  await page.getByTestId('llm-answer-detect-btn').click();
  await expect(page.getByTestId('llm-answer-model-select')).toHaveValue('gpt-4o-mini');

  await page.getByTestId('llm-embedding-api-base-input').fill('https://embedding.example.com/v1');
  await page.getByTestId('llm-embedding-api-key-input').fill('sk-embedding');
  await page.getByTestId('llm-embedding-detect-btn').click();
  await expect(page.getByTestId('llm-embedding-model-select')).toHaveValue('BAAI/bge-small-zh-v1.5');

  await page.getByTestId('llm-rerank-api-base-input').fill('https://rerank.example.com/v1');
  await page.getByTestId('llm-rerank-api-key-input').fill('sk-rerank');
  await page.getByTestId('llm-rerank-detect-btn').click();
  await expect(page.getByTestId('llm-rerank-model-select')).toHaveValue('BAAI/bge-reranker-base');

  await page.getByTestId('llm-rewrite-detect-btn').click();
  await expect(page.getByTestId('llm-rewrite-model-select')).toHaveValue('Qwen2.5-3B-Instruct');

  await page.getByTestId('llm-graph_entity-detect-btn').click();
  await expect(page.getByTestId('llm-graph_entity-model-select')).toHaveValue('Pro/deepseek-ai/DeepSeek-V3.2');

  await page.getByTestId('llm-save-btn').click();
  await expect(page.getByTestId('llm-status-text')).toContainText('配置已保存');

  await page.reload();
  await expect(page.getByTestId('llm-answer-api-base-input')).toHaveValue('https://answer.example.com/v1');
  await expect(page.getByTestId('llm-answer-model-select')).toHaveValue('gpt-4o-mini');
  await expect(page.getByTestId('llm-embedding-api-base-input')).toHaveValue('https://embedding.example.com/v1');
  await expect(page.getByTestId('llm-rerank-api-base-input')).toHaveValue('https://rerank.example.com/v1');
  await expect(page.getByText('🔄 已继承全局配置')).toHaveCount(2);
});

test('llm settings panel handles legacy three-stage payload and can still save full-stage config', async ({ page }) => {
  await mockRuntimePanels(page);
  await page.route('**/api/admin/llm-config', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          configured: true,
          answer: { provider: 'openai', api_base: 'https://answer.legacy.example.com/v1', model: 'gpt-4o-mini' },
          embedding: { provider: 'ollama', api_base: 'http://127.0.0.1:11434/v1', model: 'BAAI/bge-small-zh-v1.5' },
          rerank: { provider: 'ollama', api_base: 'http://127.0.0.1:11434/v1', model: 'BAAI/bge-reranker-base' }
        })
      });
      return;
    }

    const reqPayload = route.request().postDataJSON() as FullPayload;
    for (const stage of allStages) {
      expect(reqPayload[stage]).toBeTruthy();
      expect(reqPayload[stage].provider).toBeTruthy();
      expect(reqPayload[stage].api_base).toBeTruthy();
      expect(reqPayload[stage].api_key).toBeTruthy();
      expect(reqPayload[stage].model).toBeTruthy();
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, config: reqPayload })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByRole('heading', { name: '统一配置 LLM 连接' })).toBeVisible();

  await expect(page.getByTestId('llm-answer-api-base-input')).toHaveValue('https://answer.legacy.example.com/v1');
  await expect(page.getByTestId('llm-embedding-api-base-input')).toHaveValue('http://127.0.0.1:11434/v1');
  await expect(page.getByTestId('llm-rerank-api-base-input')).toHaveValue('http://127.0.0.1:11434/v1');
  await expect(page.getByTestId('llm-rewrite-model-select')).toHaveValue('Qwen2.5-3B-Instruct');
  await expect(page.getByTestId('llm-graph_entity-model-select')).toHaveValue('Pro/deepseek-ai/DeepSeek-V3.2');

  await page.getByTestId('llm-answer-api-key-input').fill('sk-answer');
  await page.getByTestId('llm-embedding-api-key-input').fill('sk-embedding');
  await page.getByTestId('llm-rerank-api-key-input').fill('sk-rerank');
  await page.getByTestId('llm-save-btn').click();

  await expect(page.getByTestId('llm-status-text')).toContainText('配置已保存');
});

test('llm settings panel shows auth failed message when detect returns AUTH_FAILED', async ({ page }) => {
  await mockRuntimePanels(page);
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.route('**/api/admin/detect-models', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: {
          code: 'AUTH_FAILED',
          message: 'authentication failed against upstream models endpoint'
        }
      })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByRole('heading', { name: '统一配置 LLM 连接' })).toBeVisible();

  await page.getByTestId('llm-answer-api-base-input').fill('https://api.example.com/v1');
  await page.getByTestId('llm-answer-api-key-input').fill('sk-invalid');
  await page.getByTestId('llm-answer-detect-btn').click();

  await expect(page.getByTestId('llm-answer-error')).toContainText('认证失败：请检查 API Key 是否正确');
  await expect(page.getByTestId('llm-answer-error')).toContainText('authentication failed against upstream models endpoint');
});

test('llm settings panel shows stage-specific save error for rewrite and keeps other stage inputs', async ({ page }) => {
  await mockRuntimePanels(page);
  await page.route('**/api/admin/llm-config', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ configured: false })
      });
      return;
    }
    await route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: {
          code: 'INVALID_PARAMS',
          stage: 'rewrite',
          message: 'rewrite.route is unavailable'
        }
      })
    });
  });

  await page.route('**/api/admin/detect-models', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        raw_count: 1,
        models: [{ id: 'gpt-4o-mini' }]
      })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByRole('heading', { name: '统一配置 LLM 连接' })).toBeVisible();

  await page.getByTestId('llm-answer-api-key-input').fill('sk-answer');
  await page.getByTestId('llm-answer-detect-btn').click();
  await page.getByTestId('llm-embedding-api-key-input').fill('sk-embedding');
  await page.getByTestId('llm-rerank-api-key-input').fill('sk-rerank');
  await page.getByTestId('llm-save-btn').click();

  await expect(page.getByTestId('llm-rewrite-error')).toContainText('参数校验失败');
  await expect(page.getByTestId('llm-rewrite-error')).toContainText('rewrite.route is unavailable');
  await expect(page.getByTestId('llm-answer-api-key-input')).toHaveValue('sk-answer');
  await expect(page.getByTestId('llm-answer-api-key-input')).toHaveValue('sk-answer');
});

test('llm settings provider preset auto-fills api base and allows manual override', async ({ page }) => {
  await mockRuntimePanels(page);
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByRole('heading', { name: '统一配置 LLM 连接' })).toBeVisible();

  await page.getByTestId('llm-answer-provider-select').selectOption({ label: 'Ollama' });
  await expect(page.getByTestId('llm-answer-provider-select')).toHaveValue('ollama');
  await expect(page.getByTestId('llm-answer-api-base-input')).toHaveValue('http://127.0.0.1:11434/v1');

  await page.getByTestId('llm-answer-api-base-input').fill('https://override.example.com/v1');
  await expect(page.getByTestId('llm-answer-api-base-input')).toHaveValue('https://override.example.com/v1');
});

test('llm settings api key visibility toggle switches type and keeps value', async ({ page }) => {
  await mockRuntimePanels(page);
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByRole('heading', { name: '统一配置 LLM 连接' })).toBeVisible();

  const apiKeyInput = page.getByTestId('llm-answer-api-key-input');
  await apiKeyInput.fill('sk-keep-value');
  await expect(apiKeyInput).toHaveAttribute('type', 'password');
  await expect(apiKeyInput).toHaveValue('sk-keep-value');

  await page.getByRole('button', { name: '显示密钥' }).first().click();
  await expect(apiKeyInput).toHaveAttribute('type', 'text');
  await expect(apiKeyInput).toHaveValue('sk-keep-value');

  await page.getByRole('button', { name: '隐藏密钥' }).first().click();
  await expect(apiKeyInput).toHaveAttribute('type', 'password');
  await expect(apiKeyInput).toHaveValue('sk-keep-value');
});

test('settings page supports marker tuning save and runtime overview panel', async ({ page }) => {
  let pipelineSaved = false;
  let savedMarkerPayload: Record<string, unknown> | null = null;
  await page.route('**/api/admin/pipeline-config', async (route) => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON() as { marker_tuning: { recognition_batch_size: number } };
      expect(payload.marker_tuning.recognition_batch_size).toBeGreaterThan(0);
      savedMarkerPayload = payload.marker_tuning as Record<string, unknown>;
      pipelineSaved = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true })
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        saved: {
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
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          }
        },
        effective_source: { marker_tuning: {} }
      })
    });
  });
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4o-mini', configured: true },
          embedding: { provider: 'siliconflow', model: 'emb', configured: true },
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
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByTestId('runtime-overview-panel')).toContainText('当前生效配置概览');
  await page.getByTestId('pipeline-recognition_batch_size-input').fill('8');
  await page.getByTestId('pipeline-model-dtype-select').selectOption('float32');
  await page.getByTestId('pipeline-8gb-preset-btn').click();
  await expect(page.getByTestId('pipeline-recognition_batch_size-input')).toHaveValue('1');
  await expect(page.getByTestId('pipeline-detector_batch_size-input')).toHaveValue('1');
  await expect(page.getByTestId('pipeline-layout_batch_size-input')).toHaveValue('1');
  await expect(page.getByTestId('pipeline-ocr_error_batch_size-input')).toHaveValue('1');
  await expect(page.getByTestId('pipeline-table_rec_batch_size-input')).toHaveValue('1');
  await expect(page.getByTestId('pipeline-model-dtype-select')).toHaveValue('float16');
  await page.getByTestId('pipeline-save-btn').click();
  await expect.poll(() => pipelineSaved).toBeTruthy();
  expect(savedMarkerPayload).toMatchObject({
    recognition_batch_size: 1,
    detector_batch_size: 1,
    layout_batch_size: 1,
    ocr_error_batch_size: 1,
    table_rec_batch_size: 1,
    model_dtype: 'float16'
  });
});

test('settings page keeps marker tuning inputs when backend returns field_errors', async ({ page }) => {
  let pipelineConfigLoaded = false;
  await page.route('**/api/admin/pipeline-config', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: {
            message: 'Marker tuning 参数越界',
            field_errors: {
              recognition_batch_size: 'recognition_batch_size must be between 1 and 32'
            }
          }
        })
      });
      return;
    }
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
    pipelineConfigLoaded = true;
  });
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        llm: {
          answer: { provider: 'openai', model: 'gpt-4o-mini', configured: true },
          embedding: { provider: 'siliconflow', model: 'emb', configured: true },
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
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect.poll(() => pipelineConfigLoaded).toBeTruthy();
  await page.getByTestId('pipeline-detector_batch_size-input').fill('5');
  await page.getByTestId('pipeline-layout_batch_size-input').fill('4');
  await page.getByTestId('pipeline-model-dtype-select').selectOption('float32');

  await page.getByTestId('pipeline-save-btn').click();

  await expect(page.getByText('recognition_batch_size must be between 1 and 32')).toBeVisible();
  await expect(page.getByText('Marker tuning 参数越界')).toBeVisible();
  await expect(page.getByTestId('pipeline-detector_batch_size-input')).toHaveValue('5');
  await expect(page.getByTestId('pipeline-layout_batch_size-input')).toHaveValue('4');
  await expect(page.getByTestId('pipeline-model-dtype-select')).toHaveValue('float32');
});

test('settings page shows unsaved badge and supports override toggle for inherited stages', async ({ page }) => {
  await mockRuntimePanels(page);
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByRole('heading', { name: '统一配置 LLM 连接' })).toBeVisible();

  await page.getByTestId('llm-answer-api-base-input').fill('https://override-answer.example.com/v1');
  await expect(page.getByText('⚠️ 未保存').first()).toBeVisible();

  const rewriteCard = page.locator('article').filter({ hasText: 'Rewrite 模型' }).first();
  await expect(rewriteCard.getByText('🔄 已继承全局配置')).toBeVisible();
  await rewriteCard.getByRole('checkbox', { name: '独立配置 (Override)' }).check();
  await expect(page.getByTestId('llm-rewrite-api-base-input')).toBeVisible();
  await expect(page.getByTestId('llm-rewrite-api-key-input')).toBeVisible();
});

test('settings page saves marker llm service config and shows runtime summary', async ({ page }) => {
  await page.route('**/api/admin/pipeline-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        saved: {
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          },
          marker_llm: {
            use_llm: true,
            llm_service: 'marker.services.openai.OpenAIService',
            openai_api_key: 'sk-***',
            openai_model: 'gpt-4.1-mini',
            openai_base_url: 'https://api.openai.com/v1'
          }
        },
        effective: {
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          },
          marker_llm: {
            use_llm: true,
            llm_service: 'marker.services.openai.OpenAIService',
            openai_model: 'gpt-4.1-mini',
            openai_base_url: 'https://api.openai.com/v1'
          }
        },
        effective_source: {
          marker_tuning: {},
          marker_llm: { openai_model: 'runtime', openai_base_url: 'runtime' }
        }
      })
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
            summary_fields: [
              { field: 'openai_model', value: 'gpt-4.1-mini', source: 'runtime' },
              { field: 'openai_base_url', value: 'https://api.openai.com/v1', source: 'runtime' }
            ]
          },
          last_ingest: {
            degraded: true,
            fallback_reason: 'marker parse timeout',
            fallback_path: 'marker -> legacy (parse_timeout)',
            confidence_note: '当前结果来自降级路径。'
          },
          artifacts: { counts: { healthy: 4, missing: 1, stale: 0 } }
        },
        status: { level: 'DEGRADED', reasons: ['marker parse timeout'] }
      })
    });
  });
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByTestId('marker-llm-panel')).toContainText('Marker LLM Services');
  await expect(page.getByTestId('runtime-overview-panel')).toContainText('marker parse timeout');
  await expect(page.getByText('openai_model:')).toBeVisible();
  await expect(page.getByText('最近导入: 降级完成')).toBeVisible();
});

test('settings page posts marker llm config and refreshes runtime summary after save', async ({ page }) => {
  let savedMarkerLlm: Record<string, unknown> | null = null;
  let detectPayload: Record<string, unknown> | null = null;
  let pipelineConfigState = {
    configured: true,
    saved: {
      marker_tuning: {
        recognition_batch_size: 2,
        detector_batch_size: 2,
        layout_batch_size: 2,
        ocr_error_batch_size: 1,
        table_rec_batch_size: 1,
        model_dtype: 'float16'
      },
      marker_llm: {
        use_llm: false,
        llm_service: 'gemini'
      }
    },
    effective: {
      marker_tuning: {
        recognition_batch_size: 2,
        detector_batch_size: 2,
        layout_batch_size: 2,
        ocr_error_batch_size: 1,
        table_rec_batch_size: 1,
        model_dtype: 'float16'
      },
      marker_llm: {
        use_llm: false,
        llm_service: 'gemini'
      }
    },
    effective_source: {
      marker_tuning: {},
      marker_llm: {}
    }
  };
  let runtimeOverviewState = {
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
        use_llm: false,
        llm_service: '',
        configured: false,
        status: 'disabled',
        summary_fields: []
      },
      last_ingest: {
        degraded: false,
        fallback_reason: null,
        fallback_path: null,
        confidence_note: '最近一次导入未检测到 Marker 降级路径。'
      },
      artifacts: { counts: { healthy: 4, missing: 0, stale: 0 } }
    },
    status: { level: 'READY', reasons: [] as string[] }
  };

  await page.route('**/api/admin/pipeline-config', async (route) => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON() as { marker_llm?: Record<string, unknown> };
      savedMarkerLlm = payload.marker_llm ?? null;
      expect(savedMarkerLlm).toMatchObject({
        use_llm: true,
        llm_service: 'marker.services.openai.OpenAIService',
        openai_api_key: 'sk-openai-test',
        openai_model: 'gpt-4.1-mini',
        openai_base_url: 'https://api.openai.com/v1'
      });
      pipelineConfigState = {
        ...pipelineConfigState,
        saved: {
          ...pipelineConfigState.saved,
          marker_llm: {
            use_llm: true,
            llm_service: 'marker.services.openai.OpenAIService',
            openai_api_key: 'sk-o***st',
            openai_model: 'gpt-4.1-mini',
            openai_base_url: 'https://api.openai.com/v1'
          }
        },
        effective: {
          ...pipelineConfigState.effective,
          marker_llm: {
            use_llm: true,
            llm_service: 'marker.services.openai.OpenAIService',
            openai_model: 'gpt-4.1-mini',
            openai_base_url: 'https://api.openai.com/v1'
          }
        },
        effective_source: {
          ...pipelineConfigState.effective_source,
          marker_llm: { openai_model: 'runtime', openai_base_url: 'runtime' }
        }
      };
      runtimeOverviewState = {
        ...runtimeOverviewState,
        pipeline: {
          ...runtimeOverviewState.pipeline,
          marker_llm: {
            use_llm: true,
            llm_service: 'marker.services.openai.OpenAIService',
            configured: true,
            status: 'ready',
            summary_fields: [
              { field: 'openai_model', value: 'gpt-4.1-mini', source: 'runtime' },
              { field: 'openai_base_url', value: 'https://api.openai.com/v1', source: 'runtime' }
            ]
          }
        }
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          config: {
            marker_tuning: pipelineConfigState.saved.marker_tuning,
            marker_llm: pipelineConfigState.saved.marker_llm
          }
        })
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(pipelineConfigState)
    });
  });
  await page.route('**/api/admin/runtime-overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(runtimeOverviewState)
    });
  });
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });
  await page.route('**/api/admin/detect-models', async (route) => {
    detectPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        raw_count: 2,
        models: [{ id: 'gpt-4.1-mini' }, { id: 'gpt-4.1' }]
      })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByTestId('llm-ready-text')).toBeVisible();
  await page.getByTestId('marker-llm-use-toggle').check();
  await page.getByTestId('marker-llm-service-select').selectOption('marker.services.openai.OpenAIService');
  await expect(page.getByLabel('OpenAI API Key')).toBeVisible();
  await page.getByLabel('OpenAI API Key').fill('sk-openai-test');
  await page.getByLabel('OpenAI Base URL').fill('https://api.openai.com/v1');
  await page.getByTestId('marker-llm-openai-detect-btn').click();
  await expect.poll(() => detectPayload).not.toBeNull();
  expect(detectPayload).toMatchObject({
    api_base: 'https://api.openai.com/v1',
    api_key: 'sk-openai-test'
  });
  await expect(page.getByTestId('marker-llm-openai-model-select')).toHaveValue('gpt-4.1-mini');
  await page.getByTestId('pipeline-save-btn').click();

  await expect.poll(() => savedMarkerLlm).not.toBeNull();
  await expect(page.getByText('Marker Runtime 与 LLM service 配置已保存并生效。')).toBeVisible();
  await expect(page.getByText('状态: ready · 配置完整: yes')).toBeVisible();
  await expect(page.getByText('openai_model:')).toBeVisible();
  await expect(page.getByTestId('marker-llm-panel')).toContainText('gpt-4.1-mini');
});

test('settings page keeps marker llm inputs when backend returns field errors', async ({ page }) => {
  let postedPayload: Record<string, unknown> | null = null;
  await page.route('**/api/admin/pipeline-config', async (route) => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON() as { marker_llm?: Record<string, unknown> };
      postedPayload = payload.marker_llm ?? null;
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: {
            message: 'pipeline runtime validation failed',
            field_errors: {
              vertex_project_id: 'is required for the selected llm_service'
            }
          }
        })
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        configured: true,
        saved: {
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          },
          marker_llm: {
            use_llm: false,
            llm_service: 'gemini'
          }
        },
        effective: {
          marker_tuning: {
            recognition_batch_size: 2,
            detector_batch_size: 2,
            layout_batch_size: 2,
            ocr_error_batch_size: 1,
            table_rec_batch_size: 1,
            model_dtype: 'float16'
          },
          marker_llm: {
            use_llm: false,
            llm_service: 'gemini'
          }
        },
        effective_source: {
          marker_tuning: {},
          marker_llm: {}
        }
      })
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
            use_llm: false,
            llm_service: '',
            configured: false,
            status: 'disabled',
            summary_fields: []
          },
          last_ingest: {
            degraded: false,
            fallback_reason: null,
            fallback_path: null,
            confidence_note: '最近一次导入未检测到 Marker 降级路径。'
          },
          artifacts: { counts: { healthy: 4, missing: 0, stale: 0 } }
        },
        status: { level: 'READY', reasons: [] }
      })
    });
  });
  await page.route('**/api/admin/llm-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ configured: false })
    });
  });

  await page.goto('http://127.0.0.1:3000/settings');
  await expect(page.getByTestId('llm-ready-text')).toBeVisible();
  await expect(page.getByTestId('pipeline-detector_batch_size-input')).toHaveValue('2');
  await page.getByTestId('pipeline-detector_batch_size-input').fill('5');
  await expect(page.getByTestId('pipeline-detector_batch_size-input')).toHaveValue('5');
  await page.getByTestId('marker-llm-use-toggle').check();
  await page.getByTestId('marker-llm-service-select').selectOption('marker.services.vertex.GoogleVertexService');
  await page.getByTestId('pipeline-save-btn').click();

  await expect.poll(() => postedPayload).not.toBeNull();
  await expect(page.getByText('pipeline runtime validation failed')).toBeVisible();
  await expect(page.getByText('is required for the selected llm_service')).toBeVisible();
  await expect(page.getByTestId('pipeline-detector_batch_size-input')).toHaveValue('5');
  await expect(page.getByTestId('marker-llm-use-toggle')).toBeChecked();
  await expect(page.getByTestId('marker-llm-service-select')).toHaveValue('marker.services.vertex.GoogleVertexService');
});
