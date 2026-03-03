## 上下文

当前多轮 rewrite 已具备 `standalone_query` 与术语保留能力，但在“系统状态追问”场景（如“为什么没有证据”“你没答全”）仍会被对话情绪词污染，造成查询偏离事实目标。M7.8 仅修复 rewrite 意图对齐，不改变 retrieval/graph/rerank/gate 主链路与输出结构；并与 M7.6 的 clarify 状态机、M8 的证据不足告警联动。

## 目标 / 非目标

**目标：**
- 为元问题增加状态感知识别与护栏转写，避免机械拼接历史问句。
- 让 `standalone_query` 满足“实体完整、意图纯净、可检索”。
- 在 `last_turn_warnings` 含 `insufficient_evidence_for_answer` 时，优先转写为补证据查询。
- 输出可观测字段：`rewrite_meta_detected`、`rewrite_guard_applied`、`rewrite_guard_strategy`、`rewrite_notes`。
- 提供 LLM rewrite 失败降级到规则改写的确定性路径。

**非目标：**
- 不调整检索召回、图扩展、重排与 Gate 判定算法。
- 不更改前端接口形态与最终回答模板。
- 不在本里程碑引入新的外部依赖或模型。

## 决策

1. 决策：在 rewrite 阶段新增 `meta_guard` 子流程，位于 `standalone_query` 生成之后、最终 `rewrite_query` 落定之前。  
   理由：最小侵入即可修复意图错位；不影响下游管线接口。

2. 决策：元问题判定采用“规则优先 + LLM 可选增强”的混合策略。  
   理由：规则可稳定覆盖“为什么没证据/再找找/没答全”等高频表达；LLM 仅用于语义归一，失败可回退。

3. 决策：护栏转写采用“实体保真 + 最小增补”。  
   理由：避免引入无关任务，保证检索目标集中于“架构/机制/实验/指标”等可证据化维度。

4. 决策：与 M7.6/M8 的执行顺序固定为：`clarify 合并 -> meta_guard 判定 -> insufficiency 优先补证据转写`。  
   理由：先修复指代与范围，再处理元问题，减少误判与冲突。

5. 决策：当 LLM rewrite 输出异常（空串、污染串、越界任务）时，直接走规则转写并写入 `rewrite_notes`。  
   理由：保证可检索与可观测，避免 silent failure。

备选方案对比：
- 仅靠 prompt 调整：实现快但约束不可验证，且异常难追踪。
- 将护栏下沉到检索前 gate：会改变主链路位置，不符合本里程碑边界。

## 风险 / 权衡

- [风险] 元问题模式覆盖不足导致漏判。 -> 缓解：维护中英混合触发词表并通过 10+ 样本回归。
- [风险] 过度转写导致语义漂移。 -> 缓解：强制实体保真与最小增补规则，禁止引入新任务域。
- [风险] LLM 与规则结果不一致。 -> 缓解：定义异常判定和统一回退条件，记录 `rewrite_guard_strategy`。
- [权衡] 增加 rewrite 逻辑复杂度。 -> 收益：显著减少状态词污染，提升证据命中质量。

## 迁移计划

1. 在 rewrite 模块新增 `meta_guard` 判定与转写函数，扩展 trace 字段。  
2. 接入 `last_turn_decision`、`last_turn_warnings`、`entities_from_history` 到 rewrite 输入契约。  
3. 更新 query-rewriting 与 multi-turn-session-state 增量规范。  
4. 增加回归样本与评估报告 `reports/m7_8_meta_question_guard.md`。  
5. 灰度验证：对比优化前后 query 与证据命中质量，再全量启用。

回滚策略：关闭 `meta_guard` 开关（默认回退到原 rewrite 路径），保留新增日志字段兼容读取。

## 开放问题

- 元问题词表是否需要按领域动态扩展（如医学/法律中的“证据”同义表达）？
- “证据质量显著提升”是否需要引入半自动评分脚本以减少人工偏差？
