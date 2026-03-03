## 上下文

现有 M2/M2.1 流程直接以用户原问题作为检索输入，面对同义改写、缩写表达、冗余问句时召回波动较大。M3 引入“规则优先”的 query rewrite 层，目标是在进入检索前统一问题表达，并保留可追踪的改写证据（Q、Q'、keywords/entities、命中策略）。

当前代码中 `app/qa.py` 已承担 query 入口与运行日志落盘，`app/retrieve.py` 负责检索排序，因此 rewrite 层应插入在 QA 调用 retrieve 前，避免侵入索引构建模块。

## 目标 / 非目标

**目标：**
- 产出 `Q'` 与 `keywords/entities`，并接入检索查询。
- 实现三类规则策略：术语保留、关键词扩展、问句去冗余。
- 通过开关控制规则 rewrite 与可选 LLM rewrite（默认关闭 LLM）。
- 在 runs 中可复现记录 rewrite 输入输出与策略命中。
- 形成 `reports/m3_rewrite_eval.md` 对比评估记录。

**非目标：**
- 不替换现有 BM25/向量索引结构。
- 不在 M3 实现复杂语义解析器或训练新模型。
- 不把 LLM rewrite 作为默认路径。

## 决策

### Decision 1: 新增独立模块 `app/rewrite.py`
- 方案：封装 `rewrite_query(question, config) -> RewriteResult`，避免 rewrite 逻辑散落在 `qa.py`。
- 原因：便于单测与后续替换（规则->LLM/混合）。
- 替代：直接在 `qa.py` 内联实现。
  - 放弃原因：可维护性差、测试边界不清。

### Decision 2: 规则优先，LLM 为可选后处理
- 方案：默认执行规则策略并输出 Q'；仅当配置显式启用时再执行 LLM rewrite。
- 原因：满足“先规则后可选 LLM”的里程碑要求，且离线环境稳定。
- 替代：LLM 主导 rewrite。
  - 放弃原因：成本高、可复现性弱、依赖外部服务。

### Decision 3: rewrite 结果作为 `query_used`，原问题保持 `question/input_question`
- 方案：检索调用使用 `query_used=Q'`，日志中保留 `question` 与 `rewrite_query`。
- 原因：与现有 trace 字段兼容，且能直接用于对比分析。

### Decision 4: 关键词扩展用轻量词典配置
- 方案：在配置中维护小型同义词映射（含中英关键词），产出 `keywords/entities` 供后续检索 boost。
- 原因：先实现可控版本，后续再替换为外部词典服务。

## 风险 / 权衡

- [风险] 规则过度扩展导致噪声召回上升
  → 缓解：限制扩展词数量并记录命中策略，便于调参。

- [风险] 去冗余策略误删关键信息
  → 缓解：术语保留策略优先执行，确保缩写/数字指标不丢失。

- [风险] LLM rewrite 与规则输出冲突
  → 缓解：LLM 默认关闭；开启时记录两版输出并允许回退规则结果。

## 迁移计划

1. 新增 `app/rewrite.py` 与数据结构 `RewriteResult`。
2. 在 `app/qa.py` 接入 rewrite 调用并写入 trace/report。
3. 扩展 `configs/default.yaml`（rewrite 开关、词典/策略参数）。
4. 补充单测：三类策略命中、query_used 替换、30 问题对比统计逻辑。
5. 生成 `reports/m3_rewrite_eval.md`。

回滚：若改写导致显著下降，可将 rewrite 开关关闭，恢复原问题直检索。

## 开放问题

- 关键词扩展是否需要按领域（CV/NLP/Game AI）拆词典。
- Recall@k“主观不下降”的半自动判定规则如何标准化。
- LLM rewrite 开关是否需要置信度阈值与超时回退策略。
