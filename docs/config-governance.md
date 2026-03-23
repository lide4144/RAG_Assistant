# 配置治理总览

本文档给出当前配置系统的 owner 初版清单，用于解释 `default.yaml`、runtime JSON 与环境变量的职责边界。

## 1. Owner 分类

- `static`：静态基线配置，主要来自 `configs/default.yaml`
- `runtime`：运行时可调整配置，主要来自前端管理页与 runtime 持久化文件
- `env_only`：仅允许通过宿主机环境变量控制的部署级配置

## 2. 关键字段清单

### 2.1 LLM stage 字段

| 字段组 | Owner | 默认来源 | Runtime 持久化 | 显式 env 覆盖 |
| --- | --- | --- | --- | --- |
| `answer.provider/api_base/model/api_key` | `runtime` | `default.yaml` | `configs/llm_runtime_config.json` | `RAG_LLM_ANSWER_*` |
| `embedding.provider/api_base/model/api_key` | `runtime` | `default.yaml` | `configs/llm_runtime_config.json` | `RAG_LLM_EMBEDDING_*` |
| `rerank.provider/api_base/model/api_key` | `runtime` | `default.yaml` | `configs/llm_runtime_config.json` | `RAG_LLM_RERANK_*` |
| `rewrite.provider/api_base/model/api_key` | `runtime` | `default.yaml` | `configs/llm_runtime_config.json` | `RAG_LLM_REWRITE_*` |
| `graph_entity.provider/api_base/model/api_key` | `runtime` | `default.yaml` | `configs/llm_runtime_config.json` | `RAG_LLM_GRAPH_ENTITY_*` |
| `sufficiency_judge.provider/api_base/model/api_key` | `runtime` | `default.yaml` | `configs/llm_runtime_config.json` | `RAG_LLM_SUFFICIENCY_JUDGE_*` |

说明：

- `api_key` 在运行时配置落盘后会被注入 `RAG_RUNTIME_LLM_API_KEY_<STAGE>` 供后端路由读取。
- 若显式设置 `RAG_LLM_<STAGE>_*`，则该 stage 对应字段以环境变量为准，并在概览接口中标记为 `env`。

### 2.2 Pipeline runtime 字段

| 字段组 | Owner | 默认来源 | Runtime 持久化 | 显式 env 覆盖 |
| --- | --- | --- | --- | --- |
| `marker_tuning.*` | `runtime` | 代码默认值 | `configs/pipeline_runtime_config.json` | 现有 `RECOGNITION_BATCH_SIZE` 等字段 |
| `marker_llm.*` | `runtime` | 代码默认值 | `configs/pipeline_runtime_config.json` | 现有 `MARKER_USE_LLM`、`OPENAI_MODEL` 等字段 |

说明：

- Pipeline runtime 允许 env 强覆盖，但覆盖边界仅限注册过的字段。
- 未注册字段不得通过隐式 `os.getenv` 参与来源竞争。

### 2.3 Planner runtime 字段

| 字段组 | Owner | 默认来源 | Runtime 持久化 | 显式 env 覆盖 |
| --- | --- | --- | --- | --- |
| `planner.use_llm/provider/api_base/model/api_key/timeout_ms` | `runtime` | `default.yaml` | `configs/planner_runtime_config.json` | `PLANNER_*` |

说明：

- `planner` 属于顶层规划器配置，虽然进入前端可管理范围，但必须以独立高风险面板暴露，不能混入普通 stage 卡片。
- `planner.api_key` 落盘后会被注入 `PLANNER_RUNTIME_API_KEY` 供 Python planner runtime 读取。

### 2.4 静态基线字段示例

以下字段继续由 `configs/default.yaml` 管理，不进入前端设置页：

- `chunk_size`
- `overlap`
- `top_k_retrieval`
- `top_n_evidence`
- `rewrite_meta_patterns`
- `planner_enabled`
- `session_store_backend`
- `graph_expand_alpha`

### 2.5 Env-only 字段示例

以下字段属于部署级或敏感配置，不通过前端 runtime 页编辑：

- `KERNEL_CORS_ALLOW_ORIGINS`
- `KERNEL_ADMIN_UPSTREAM_TIMEOUT_SEC`
- `SESSION_REDIS_URL`
- `OPENAI_API_KEY`
- `SILICONFLOW_API_KEY`

## 3. 来源优先级

- `static`：`default.yaml` -> 代码默认值
- `runtime`：`env`（仅注册且允许覆盖时）-> runtime 持久化 -> `default.yaml` 或代码默认值
- `env_only`：部署环境变量 -> 安全默认值 / 不可用状态

## 4. 页面边界

“模型设置”页只负责 runtime owner 字段：

- 六个 LLM stage（含证据判定模型 `sufficiency_judge`）
- Planner Runtime 独立高风险面板
- Marker tuning
- Marker LLM service

以下内容不在本页覆盖范围：

- 检索、规划、会话等系统级策略
- 宿主机路径与服务连接
- 未被治理模型标记为 `runtime` 的字段
