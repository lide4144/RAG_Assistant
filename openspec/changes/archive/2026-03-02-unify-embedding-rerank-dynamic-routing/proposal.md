## 为什么

当前项目已支持在运行时配置 answer LLM，但 embedding 与 rerank 仍默认绑定 `SILICONFLOW_API_KEY` 和固定 provider，导致启动与运行路径存在“部分可动态、部分硬依赖”的割裂。随着多供应商接入和线上稳定性要求提高，需要把三条 AI 路径统一到同一套路由与降级语义下，降低单点依赖和运维复杂度。

## 变更内容

- 统一配置面：为 embedding 与 rerank 增加与 answer 对齐的动态配置族（provider/model/api_base/api_key_env），并移除对单一环境变量命名的硬编码假设。
- 统一路由面：将现有 `app/llm_routing.py` 从“LLM 回答路由”扩展为“多阶段 AI 路由中心”，明确支持 `stage=answer|embedding|rerank`。
- 统一容错面：
  - Embedding 失败时，定义可观测且可控的降级路径（优先静默降级到词频检索；不可降级场景抛出可识别异常交由上层决策）。
  - Reranker 失败时，定义“静默穿透”策略：跳过重排，直接沿用上游检索序。
- 统一可观测面：新增 `/health/deps`，一次返回 answer、embedding、rerank 三路连通性与关键状态，便于发布前巡检与运行期排障。

## 功能 (Capabilities)

### 新增功能

- `ai-stage-routing-center`: 提供统一的多阶段 AI 路由抽象，覆盖 answer/embedding/rerank 的配置解析、API key 解析、失败分类与阶段级回退信号。
- `dependency-health-status-endpoint`: 提供 `/health/deps` 依赖健康检查能力，输出 answer/embedding/rerank 三路状态与失败原因摘要。

### 修改功能

- `llm-runtime-config-persistence`: 从仅覆盖 answer/rewrite 的运行时配置，扩展为可服务多阶段路由的配置读取与生效机制。
- `embedding-indexing-and-cache`: 将 embedding 调用从固定 provider/key 假设改为阶段化路由，并补充失败后降级/异常语义。
- `rerank-evidence-selection`: 将 rerank 调用改为阶段化路由，明确 API 异常时的“静默穿透”行为与可观测信号。
- `rag-baseline-retrieval`: 对 dense=embedding 的检索路径补充降级策略，确保在 embedding 依赖不可用时可回落到词频检索路径。

## 影响

- 受影响代码：
  - 配置加载与校验：`app/config.py`、`configs/*.yaml`
  - 路由策略：`app/llm_routing.py`
  - 检索与重排：`app/retrieve.py`、`app/rerank.py`、`app/qa.py`
  - 服务接口：`app/kernel_api.py`（新增 `/health/deps`）
- 受影响运维：
  - 环境变量与运行时配置项将从“单路 LLM”扩展为“三阶段 AI 路由”。
  - 监控与健康探针需要纳入 `/health/deps` 新输出。
- 兼容性：
  - 预期保持向后兼容（旧配置可通过默认映射继续工作），但依赖默认 `SILICONFLOW_API_KEY` 的隐式行为将被弱化并显式化。
