# LLM Runtime Config 运维说明

本文档说明前端可视化 LLM 配置的生效路径、回滚步骤和安全注意事项。

## 生效路径

1. 管理员在前端 `LLM Connection Settings` 分别填写 `answer`、`embedding`、`rerank`、`rewrite`、`graph_entity` 的 `provider`、`API Base`、`API Key` 并探测模型。
2. 前端调用 `POST /api/admin/llm-config` 保存五路配置。
3. 后端将配置持久化到 `configs/llm_runtime_config.json`。
   - 新结构：`answer` / `embedding` / `rerank` / `rewrite` / `graph_entity`
   - 兼容旧结构：`api_base` + `api_key` + `model`（自动映射到五路）
4. `load_and_validate_config` 加载配置时，若该文件合法，则覆盖：
   - `answer`：`answer_llm_*`
   - `embedding`：`embedding_*`
   - `rerank`：`rerank_*`
   - `rewrite`：`rewrite_llm_*`（独立于 answer，不再隐式跟随）
   - `graph_entity`：`graph_entity_llm_*`
   - API key 分路注入环境变量：
     - `RAG_RUNTIME_LLM_API_KEY_ANSWER`
     - `RAG_RUNTIME_LLM_API_KEY_EMBEDDING`
     - `RAG_RUNTIME_LLM_API_KEY_RERANK`
     - `RAG_RUNTIME_LLM_API_KEY_REWRITE`
     - `RAG_RUNTIME_LLM_API_KEY_GRAPH_ENTITY`
5. LiteLLM Router 在后续请求中优先使用该运行时配置。

## 管理接口契约

### `POST /api/admin/llm-config`（推荐：五路结构）

```json
{
  "answer": {
    "provider": "openai",
    "api_base": "https://api.example.com/v1",
    "api_key": "sk-answer",
    "model": "gpt-4.1-mini"
  },
  "embedding": {
    "provider": "ollama",
    "api_base": "http://127.0.0.1:11434/v1",
    "api_key": "local-placeholder",
    "model": "BAAI/bge-small-zh-v1.5"
  },
  "rerank": {
    "provider": "ollama",
    "api_base": "http://127.0.0.1:11434/v1",
    "api_key": "local-placeholder",
    "model": "BAAI/bge-reranker-base"
  },
  "rewrite": {
    "provider": "ollama",
    "api_base": "http://127.0.0.1:11434/v1",
    "api_key": "local-placeholder",
    "model": "Qwen2.5-3B-Instruct"
  },
  "graph_entity": {
    "provider": "siliconflow",
    "api_base": "https://api.siliconflow.cn/v1",
    "api_key": "sk-graph",
    "model": "Pro/deepseek-ai/DeepSeek-V3.2"
  }
}
```

### `POST /api/admin/llm-config`（兼容：旧单路结构）

```json
{
  "api_base": "https://api.example.com/v1",
  "api_key": "sk-legacy",
  "model": "gpt-4o-mini"
}
```

### `GET /api/admin/llm-config`

返回五路摘要（`api_key_masked` 为脱敏值）。

## Stage 路由优先级（answer / embedding / rerank / rewrite / graph_entity）

系统按以下优先级解析：

1. 运行时配置（若存在并合法）
2. stage 前缀字段（如 `embedding_provider`、`rerank_api_key_env`）
3. 旧嵌套字段（如 `embedding.provider`、`rerank.base_url`）
4. 默认值（`configs/default.yaml` / 代码默认）

说明：
- `rewrite` 与 `answer` 完全独立，可使用不同 provider/model。
- 当某一路缺失 API Key 时，仅该 stage 进入降级，不影响其他 stage。

## 依赖健康检查

`GET /health/deps` 当前输出 `answer` / `embedding` / `rerank` 三路运行态诊断（不含 rewrite 与 graph_entity）。

## 回滚步骤

1. 执行一键回滚脚本（见 `scripts/rollback_to_external_api.sh`）。
2. 或手动删除/重命名 `configs/llm_runtime_config.json`。
3. 重启 Python Kernel 服务。
4. 验证 `load_and_validate_config` 输出中的 LLM 字段已回退到静态配置。

## 故障排查

- `AUTH_FAILED`：上游密钥无效或无模型访问权限。
- `UPSTREAM_TIMEOUT`：上游模型列表接口超时。
- `UPSTREAM_NETWORK_ERROR`：DNS/网络不可达。
- `UPSTREAM_INVALID_RESPONSE`：上游返回非 OpenAI-compatible `data` 列表结构。

## 安全注意事项

- `api_key` 在持久化文件中为敏感信息，必须限制文件权限并禁止提交。
- API 响应和日志仅返回脱敏值，禁止回显明文 key。
- 仅允许受信任前端源通过 CORS 访问管理接口（`KERNEL_CORS_ALLOW_ORIGINS`）。
