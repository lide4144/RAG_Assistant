## 为什么

当前跨论文检索下，指代不明问题（如“这篇论文/本文/this work”）容易被 summary 外壳句主导召回，导致证据可读但不回答真实意图。需要在不改动 M3 rewrite 模块的前提下，在检索阶段增加轻量校准与一次性 retry，稳定拉回 limitation/contribution/dataset/metric 等目标语义证据。

## 变更内容

- 在检索前新增 query intent calibration：基于问题意图对 `calibrated_query` 追加语义 cue words。
- 对 scope 歧义问题增加约束：禁止在 `query_used` 追加 `summary/overview/abstract` 类 cue words。
- 增加 Top-5 summary shell 占比检测与最多一次 retry 机制：
  - 触发后移除 summary cues，强制注入语义目标 cues，重新检索一次。
- 扩展 QA 运行输出与 runs 日志字段：
  - `calibrated_query`
  - `calibration_reason`
  - `query_retry_used`
  - `query_retry_reason`（可选）
- 增加评估记录 `reports/m2_2_intent_calibration.md`，覆盖至少 10 条问题。

## 功能 (Capabilities)

### 新增功能
- 无

### 修改功能
- `multi-paper-scope-policy`: 增加歧义问题下 summary cue 禁用与意图校准策略约束。
- `rag-baseline-retrieval`: 增加检索前校准、shell 占比检测与单次 retry 行为，以及 QA 输出新增字段。
- `pipeline-development-conventions`: 增加 M2.2 运行日志字段与评估记录要求。

## 影响

- 受影响代码：`app/qa.py`、`app/retrieve.py`（或等价检索编排入口）、可能新增 `app/intent_calibration.py`。
- 受影响输出：QA 结果结构与 runs JSON schema。
- 受影响报告：新增 `reports/m2_2_intent_calibration.md`。
- 无外部依赖强制新增；不修改 `app/rewrite.py` 的既有逻辑边界。
