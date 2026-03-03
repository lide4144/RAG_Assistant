## 上下文

M2.1 已实现跨论文聚合与 scope policy，但在歧义问题上仍可能被 summary shell 证据主导，影响答案有效性。M2.2 需要在检索前后增加轻量校准与一次 retry，且必须保持 M3 rewrite 模块边界不变。

## 目标 / 非目标

**目标：**
- 在检索阶段生成 `calibrated_query`，将查询从 summary cue 导向语义目标 cue。
- 在 Top-5 shell 占比过高时触发一次可追踪 retry。
- 完整落盘校准与 retry 字段，支持复现。
- 产出 M2.2 评估报告模板与记录路径。

**非目标：**
- 不修改 `app/rewrite.py` 的策略与接口。
- 不引入重型 NLP/分类模型。
- 不改变既有 dense/bm25/hybrid 索引构建逻辑。

## 决策

### 决策 1：新增检索前置校准层（Intent Calibration）
- 在 `rewrite_query` 之后、`retrieve_candidates` 之前执行 `calibrate_query_intent`。
- 输入：`Q`、`rewritten_query`、`keywords_entities`、scope 信息。
- 输出：`calibrated_query`、`calibration_reason`。
- 原因：保持改写模块独立，同时让检索 query 能表达真实语义目标。

### 决策 2：歧义问题硬性禁用 summary cues
- 当 scope 为歧义且无 paper clue 时，从 query 中移除 summary/overview/abstract/reporting 类 cue。
- 原因：直接抑制 summary shell 吸引效应。

### 决策 3：基于规则的意图 cue 注入
- 支持 limitation/contribution/dataset/metric（可选 architecture）规则匹配。
- 命中后按预定义中英 cue words 追加到 `calibrated_query`。
- 原因：实现简单、可解释、可控。

### 决策 4：Top-5 shell 占比触发单次 retry
- 首次检索后计算 shell 比例；若 >60% 且未重试，则执行一次 retry。
- retry 逻辑：移除 shell cues，强制追加命中意图 cues，重新检索。
- 原因：低成本补救首次查询偏移，避免无限重试。

### 决策 5：日志字段与报告优先落地
- 在 runs JSON 中新增 `calibrated_query`、`calibration_reason`、`query_retry_used`、`query_retry_reason`。
- 增加 `reports/m2_2_intent_calibration.md` 记录模板。
- 原因：先保证可观测与可复现，再迭代策略质量。

## 风险 / 权衡

- [风险] 规则过于宽松导致误判意图  
  → 缓解：将命中词与追加词写入 `calibration_reason`，便于回放调参。

- [风险] retry 增加时延  
  → 缓解：限制最多一次，且仅在 shell 比例 >60% 时触发。

- [风险] 过度移除 summary 词可能影响少数“概述类”问题  
  → 缓解：仅在 scope 歧义且缺少 paper clue 时强制移除。

## 迁移计划

1. 在 QA 检索编排入口增加 intent calibration 与字段透传。
2. 增加 summary shell 检测与单次 retry 分支。
3. 更新运行日志 schema 校验与落盘逻辑。
4. 增加/更新测试：意图命中、禁用 summary cue、retry 触发与上限。
5. 生成 `reports/m2_2_intent_calibration.md` 并填充 10 条样例。

## 开放问题

- architecture 意图是否在 M2.2 强制纳入，还是先作为可选策略？
- shell 模式是否需增加正则白名单以减少误检？
