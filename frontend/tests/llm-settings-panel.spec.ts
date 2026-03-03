import { expect, test } from '@playwright/test';

test('llm settings panel can save and reload three-stage config', async ({ page }) => {
  let savedConfig:
    | {
        answer: { provider: string; api_base: string; api_key: string; model: string };
        embedding: { provider: string; api_base: string; api_key: string; model: string };
        rerank: { provider: string; api_base: string; api_key: string; model: string };
      }
    | null = null;

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
          }
        })
      });
      return;
    }
    const reqPayload = route.request().postDataJSON() as {
      answer: { provider: string; api_base: string; api_key: string; model: string };
      embedding: { provider: string; api_base: string; api_key: string; model: string };
      rerank: { provider: string; api_base: string; api_key: string; model: string };
    };
    expect(reqPayload.answer.model).toBeTruthy();
    expect(reqPayload.embedding.model).toBeTruthy();
    expect(reqPayload.rerank.model).toBeTruthy();
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

  await page.goto('http://127.0.0.1:3000/chat');
  await expect(page.getByText('LLM Connection Settings')).toBeVisible();

  await page.getByTestId('llm-answer-api-base-input').fill('https://answer.example.com/v1');
  await page.getByTestId('llm-answer-api-key-input').fill('sk-answer');
  await page.getByTestId('llm-answer-detect-btn').click();
  await expect(page.getByTestId('llm-answer-model-select')).toHaveValue('gpt-4o-mini');

  await page.getByTestId('llm-embedding-api-base-input').fill('https://embedding.example.com/v1');
  await page.getByTestId('llm-embedding-api-key-input').fill('sk-embedding');
  await page.getByTestId('llm-embedding-detect-btn').click();
  await expect(page.getByTestId('llm-embedding-model-select')).toHaveValue('gpt-4o-mini');

  await page.getByTestId('llm-rerank-api-base-input').fill('https://rerank.example.com/v1');
  await page.getByTestId('llm-rerank-api-key-input').fill('sk-rerank');
  await page.getByTestId('llm-rerank-detect-btn').click();
  await expect(page.getByTestId('llm-rerank-model-select')).toHaveValue('gpt-4o-mini');

  await page.getByTestId('llm-save-btn').click();
  await expect(page.getByText('三路配置已保存，刷新后将回显最新持久化结果')).toBeVisible();

  await page.reload();
  await expect(page.getByTestId('llm-answer-api-base-input')).toHaveValue('https://answer.example.com/v1');
  await expect(page.getByTestId('llm-answer-model-select')).toHaveValue('gpt-4o-mini');
  await expect(page.getByTestId('llm-embedding-api-base-input')).toHaveValue('https://embedding.example.com/v1');
  await expect(page.getByTestId('llm-embedding-model-select')).toHaveValue('gpt-4o-mini');
  await expect(page.getByTestId('llm-rerank-api-base-input')).toHaveValue('https://rerank.example.com/v1');
  await expect(page.getByTestId('llm-rerank-model-select')).toHaveValue('gpt-4o-mini');
});

test('llm settings panel shows auth failed message when detect returns AUTH_FAILED', async ({ page }) => {
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

  await page.goto('http://127.0.0.1:3000/chat');

  await page.getByTestId('llm-answer-api-base-input').fill('https://api.example.com/v1');
  await page.getByTestId('llm-answer-api-key-input').fill('sk-invalid');
  await page.getByTestId('llm-answer-detect-btn').click();

  await expect(
    page.getByText('[AUTH_FAILED] authentication failed against upstream models endpoint')
  ).toBeVisible();
});

test('llm settings panel shows stage-specific save error for embedding and keeps other stage inputs', async ({ page }) => {
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
          stage: 'embedding',
          message: 'embedding.api_key is required'
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

  await page.goto('http://127.0.0.1:3000/chat');

  await page.getByTestId('llm-answer-api-base-input').fill('https://answer.example.com/v1');
  await page.getByTestId('llm-answer-api-key-input').fill('sk-answer');
  await page.getByTestId('llm-answer-detect-btn').click();

  await page.getByTestId('llm-embedding-api-base-input').fill('https://embedding.example.com/v1');
  await page.getByTestId('llm-embedding-api-key-input').fill('sk-embedding');
  await page.getByTestId('llm-embedding-detect-btn').click();

  await page.getByTestId('llm-rerank-api-base-input').fill('https://rerank.example.com/v1');
  await page.getByTestId('llm-rerank-api-key-input').fill('sk-rerank');
  await page.getByTestId('llm-rerank-detect-btn').click();

  await page.getByTestId('llm-save-btn').click();

  await expect(page.getByText('[INVALID_PARAMS] embedding.api_key is required')).toBeVisible();
  await expect(page.getByTestId('llm-answer-api-base-input')).toHaveValue('https://answer.example.com/v1');
  await expect(page.getByTestId('llm-rerank-api-base-input')).toHaveValue('https://rerank.example.com/v1');
});
