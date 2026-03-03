## 上下文

当前 QA 链路在 M5 后形成“初检 + 图扩展”候选集合，但证据最终选择仍主要依赖检索分数，导致多论文、多段落问题中前几条 evidence 的相关性波动较大。项目已有 `app/rerank.py` 模块基础与统一运行日志能力（`run_trace`/`qa_report`），本次设计在保持现有 CLI 语义不变的前提下，引入可配置 rerank 层，并确保与 M2.4/M5 字段契约兼容。

约束：
- rerank 阶段禁止改写 `payload.dense_backend`。
- 必须保留 `score_retrieval`，新增 `score_rerank` 用于前后对比。
- 当 `dense_backend=embedding` 时，候选必须保留 `payload.embedding_provider` 与 `payload.embedding_model`。
- 默认输出 top_n=8，并记录 rerank 分布统计。

## 目标 / 非目标

**目标：**
- 在候选到证据组织之间增加 rerank 层，输出稳定的 top_n evidence。
- 建立候选字段校验与透传机制，避免 rerank 破坏上游检索语义。
- 支持 SiliconFlow `Qwen/Qwen3-Reranker-8B` 作为可选后端，并提供可降级策略。
- 在运行日志中增加 rerank 可观测字段，支持实验回放与验收。

**非目标：**
- 不替换 BM25/dense/hybrid 的初检逻辑。
- 不改变 graph expansion 的候选生成与预算策略。
- 不在本阶段引入学习排序训练流程或在线反馈学习。

## 决策

### 决策 1：采用“候选重排后截断”主流程
- 方案：在 `retrieve -> candidates` 后调用 reranker，产出 `score_rerank`，按该分数排序后截断 top_n，再进入 evidence 组织。
- 原因：最小侵入接入现有链路，且可直接对比 rerank 前后。
- 备选：在 evidence 分配阶段内部重排；会与 paper-level 分配逻辑耦合，难以评估纯 rerank 效果。

### 决策 2：字段保真优先
- 方案：rerank 输入输出对象透传原候选 payload，显式保留 `score_retrieval`；仅新增 `score_rerank`，禁止修改 `dense_backend`。
- 原因：满足 M6 对对比实验与后端语义一致性的硬约束。
- 备选：将 rerank 分数覆盖检索分数；会丢失实验可比性。

### 决策 3：Provider 适配层抽象
- 方案：在 `app/rerank.py` 中抽象 provider 调用接口，优先实现 SiliconFlow `Qwen/Qwen3-Reranker-8B`，并保留 mock/local fallback。
- 原因：满足当前模型选型，同时避免后续 provider 变更影响主流程。
- 备选：在 `qa.py` 直接写死 HTTP 调用；可维护性差。

### 决策 4：失败降级与日志齐全
- 方案：若 rerank 超时/调用失败，回退到 `score_retrieval` 排序并记录 warning；无论成功或降级都记录 `rerank_top_n`、`rerank_score_distribution`、`dense_backend`。
- 原因：保证流程可用性，同时满足可观测要求。
- 备选：失败即终止 QA；会降低系统稳健性。

## 风险 / 权衡

- [外部 reranker 服务延迟高] → 设置超时、批量大小与失败降级到检索分排序。
- [候选字段不完整导致 rerank/日志异常] → 在 rerank 前增加 schema 校验并记录缺失字段告警。
- [不同 dense_backend 混合场景可解释性下降] → 强制记录 `dense_backend` 与分数分布，报告中提供前后样例。
- [模型切换引入分数尺度变化] → 使用分布统计而非固定阈值，并通过 `reports/m6_rerank.md` 固化人工对比。

## 迁移计划

1. 在配置中新增 rerank 参数（启用开关、`top_n`、provider/model、超时、重试与降级策略）。
2. 在 `app/rerank.py` 实现候选字段校验、provider 适配与 `score_rerank` 生成。
3. 在 `app/qa.py` 接入 rerank 调用，并将 top_n 结果喂给证据分配流程。
4. 在 `app/runlog.py`（或等效日志路径）补充 rerank 指标字段落盘。
5. 增加单测/集成测试并生成 `reports/m6_rerank.md` 对比报告。

回滚策略：关闭 rerank 开关后回退为检索分直排；保留字段兼容不破坏既有输出。

## Open Questions

- SiliconFlow API 的并发与速率限制在当前 20 问评测规模下是否需要限流队列？
- `rerank_score_distribution` 采用分位数（p50/p90）还是直方图桶作为标准输出？
- 默认 top_n=8 是否应允许按问题类型动态调整（例如列表问答 vs 事实问答）？
