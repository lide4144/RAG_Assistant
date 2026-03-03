## 为什么

M5 引入图扩展后，候选证据集合覆盖更广但噪声也上升，直接使用检索分数会让最终证据的相关性不稳定。M6 需要在候选阶段增加可观测、可对比的 rerank 层，把 top_n 证据稳定压到更相关的内容上。

## 变更内容

- 新增 rerank 阶段：输入 `candidates + query`，输出带 `score_rerank` 的 top_n evidence（默认 `n=8`）。
- 明确候选字段契约：`score_retrieval` 与 `payload.source / payload.dense_backend` 必须保留；当 `dense_backend=embedding` 时必须包含 `payload.embedding_provider` 与 `payload.embedding_model`。
- 明确 rerank 约束：rerank 阶段不得修改 `payload.dense_backend`，且必须保留 `score_retrieval` 以支持前后对比实验。
- 新增运行日志字段：`rerank_top_n`、`rerank_score_distribution`、`dense_backend`。
- 支持基于 SiliconFlow 的 `Qwen/Qwen3-Reranker-8B` 作为可选 reranker 后端，并保留可替换接口。
- 新增验收与报告要求：在 `reports/m6_rerank.md` 记录至少 20 个问题的 rerank 前后对比样例。

## 功能 (Capabilities)

### 新增功能
- `rerank-evidence-selection`: 对候选证据执行重排序并输出 top_n，保证 rerank 打分、字段保真与实验可观测性。

### 修改功能
- `rag-baseline-retrieval`: 检索链路从“候选后直接进入证据组织”调整为“候选 -> rerank -> 证据组织”，并新增 rerank 运行日志与字段约束。

## 影响

- 代码：`app/retrieve.py`、`app/qa.py`，可能新增 `app/rerank.py`（或同等模块）与 reranker provider 适配层。
- 配置：新增 rerank 配置（`enabled`、`top_n`、模型与服务地址/鉴权、超时/降级策略）。
- 输出与日志：候选与 evidence 结构新增 `score_rerank`，run trace 新增 rerank 统计字段，保留 `score_retrieval`。
- 测试与报告：新增 rerank 单测/集成测试及 `reports/m6_rerank.md` 人工评估记录。
