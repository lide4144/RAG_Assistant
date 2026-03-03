# LLM Runtime Config 运维说明

本文档说明前端可视化 LLM 配置的生效路径、回滚步骤和安全注意事项。

## 生效路径

1. 管理员在前端 `LLM Connection Settings` 分别填写 `answer`、`embedding`、`rerank` 的 `provider`、`API Base`、`API Key` 并探测模型。
2. 前端调用 `POST /api/admin/llm-config` 保存三路配置。
3. 后端将配置持久化到 `configs/llm_runtime_config.json`。
   - 新结构：`answer` / `embedding` / `rerank` 三路对象
   - 兼容旧结构：`api_base` + `api_key` + `model`（自动映射到三路）
4. `load_and_validate_config` 加载配置时，若该文件合法，则覆盖：
   - `answer`：`answer_llm_*`（rewrite 仍复用 answer 以保持兼容）
   - `embedding`：`embedding_*`
   - `rerank`：`rerank_*`
   - 三路密钥分别注入：
     - `RAG_RUNTIME_LLM_API_KEY_ANSWER`
     - `RAG_RUNTIME_LLM_API_KEY_EMBEDDING`
     - `RAG_RUNTIME_LLM_API_KEY_RERANK`
5. LiteLLM Router 在后续请求中优先使用该运行时配置。

## 管理接口契约

### `POST /api/admin/llm-config`（推荐：三路结构）

```json
{
  "answer": {
    "provider": "openai",
    "api_base": "https://api.example.com/v1",
    "api_key": "sk-answer",
    "model": "gpt-4.1-mini"
  },
  "embedding": {
    "provider": "siliconflow",
    "api_base": "https://api.example.com/v1",
    "api_key": "sk-embedding",
    "model": "BAAI/bge-m3"
  },
  "rerank": {
    "provider": "siliconflow",
    "api_base": "https://api.example.com/v1",
    "api_key": "sk-rerank",
    "model": "Qwen/Qwen3-Reranker-8B"
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

返回 `answer` / `embedding` / `rerank` 三路摘要（`api_key_masked` 为脱敏值）。

## Stage 路由优先级（answer / embedding / rerank）

当前系统对三路 AI 依赖采用统一优先级解析：

1. 运行时配置（若存在并合法）
2. 新的 stage 前缀字段（如 `embedding_provider`、`rerank_api_key_env`）
3. 旧的嵌套字段（如 `embedding.provider`、`rerank.base_url`）
4. 默认值（`configs/default.yaml` / 代码默认）

说明：
- `answer` 继续使用 `answer_llm_*` 路由族。
- `embedding` 与 `rerank` 推荐使用 stage 前缀字段；旧嵌套键仍兼容。
- 当某一路缺失 API Key 时，仅该 stage 进入降级，不影响其他 stage。

## 依赖健康检查

新增 `GET /health/deps` 输出三路依赖状态：
- `answer`
- `embedding`
- `rerank`

每一路都包含：
- `status`
- `provider`
- `model`
- `checked_at`
- `reason`（失败/降级时）

额外诊断：
- `embedding` 可返回 `dimension_mismatch`
- `rerank` 会返回 `passthrough_mode` 与最近失败原因

## 回滚步骤

1. 删除或重命名 `configs/llm_runtime_config.json`。
2. 重启 Python Kernel 服务（确保进程重新加载配置）。
3. 验证 `load_and_validate_config` 输出中的 LLM 字段已回退至 `configs/default.yaml`。
4. 如需临时降级，可在前端停止使用保存接口，仅保留静态配置。

## 故障排查

- `AUTH_FAILED`：上游密钥无效或无模型访问权限，检查 key 与账号权限。
- `UPSTREAM_TIMEOUT`：上游模型列表接口超时，检查网络与上游健康状态。
- `UPSTREAM_NETWORK_ERROR`：DNS/网络不可达，检查出口网络与域名解析。
- `UPSTREAM_INVALID_RESPONSE`：上游返回非 OpenAI-compatible `data` 列表结构。

## 安全注意事项

- `api_key` 在持久化文件中为敏感信息，必须限制文件权限并禁止仓库提交该文件。
- API 响应和日志仅返回脱敏值，禁止回显明文 key。
- 仅允许受信任前端源通过 CORS 访问管理接口（`KERNEL_CORS_ALLOW_ORIGINS`）。

## 兼容与弃用计划

- 当前版本继续支持旧单路保存载荷，防止历史客户端立即中断。
- 新客户端应统一使用三路结构提交。
- 建议在后续版本窗口移除旧单路写入入口，仅保留读取兼容一段时间后彻底移除。
