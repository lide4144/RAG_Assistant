## 上下文

当前 `Sufficiency Gate（充分性门控）` 在交互裁判权上已经降级为 `guardrail（护栏）`，但实现内部仍然承担了大量高不确定性的语义判别责任。现状主要问题有三类：

- `app/sufficiency.py` 维护了静态 `question type（问题类型）` 词表、`key element（关键要素）` 槽位、`token overlap / trigram similarity（词重合 / 三元组近似语义）` 等启发式规则，并用这些规则直接形成不足结论。
- `app/qa.py` 仍保留与 `sufficiency` 高度同构的词表和判定片段，尤其是 `KEY_ELEMENT_*`、`QUESTION_TYPE_*` 一类证据充分性静态规则，使得证据检验相关规则出现双份维护风险。
- `llm-first-planner` 已把顶层交互姿态收口到 `LLM planner`，但底层 `sufficiency` 仍残留“通过规则解释复杂语义”的迁移期结构，这与后续维护目标冲突。

这次设计要解决的不是“如何给 `sufficiency` 再补一组规则”，而是明确其长期可维护边界：`sufficiency` 只做受限证据判别与硬校验，不再继续扩张为语义规则系统。

相关利益相关方包括：

- `planner / policy`：消费 `sufficiency` 结构化约束并决定最终用户姿态
- `qa` 主链：负责把问题、证据和上游上下文送入证据检验层
- `run trace / tests`：负责观测 judge/validator 输出来源与回归行为

## 目标 / 非目标

**目标：**

- 删除 `sufficiency.py` 中不该继续维护的静态问题类型词表、关键要素槽位映射和近似语义规则。
- 将证据检验收敛为 `semantic evidence judge（语义证据判别）` + `deterministic validator（确定性校验器）` 两层结构。
- 用 `missing_aspects（缺失方面）`、`coverage_summary（覆盖摘要）` 取代旧的 `missing_key_elements（缺失关键要素）` 槽位输出。
- 删除或降权 `qa.py` 中仅为 `sufficiency` 服务的重复规则常量，尤其是证据充分性相关的 `KEY_ELEMENT_*`、`QUESTION_TYPE_*` 及其派生逻辑，避免双份维护。
- 保持 planner、citation、evidence guardrails 的现有边界，不把证据检验重新做成顶层决策器。

**非目标：**

- 不将 `evidence gate（证据门）`、`citation contract（引用契约）` 或最小证据存在性检查移除。
- 不让 `semantic judge` 直接决定最终 `clarify / partial_answer / refuse` 用户姿态。
- 不在本次设计中重构全部 `qa.py`；仅处理与 `sufficiency` 强耦合、会导致规则漂移的部分。
- 不要求为 judge 新建独立基础设施；可复用现有 LLM 调用栈，但 judge 本身仍必须由独立小模型承担。

## 决策

### 决策 1：删除静态问题类型和关键要素槽位规则
正式执行链中，不再保留 `QUESTION_TYPE_*`、`KEY_ELEMENT_*` 这类静态词表和槽位映射作为证据充分性的正式主裁决依据。

选择原因：这类规则与真实用户问法分布强耦合，越补越多且仍覆盖不稳，是当前维护困难的主要来源。

备选方案：

- 保留词表但弱化权重：实现简单，但会继续诱导后来者在旧规则层追加 patch。
- 仅调整词表内容：短期可缓解个别误判，但无法解决结构性维护问题。

### 决策 2：用独立小模型语义判别替代近似语义规则
新增 `semantic evidence judge` 抽象，输入为 `question`、`query_used / anchor_query`、`evidence_grouped` 与必要上下文，输出结构化 `coverage_summary`、`missing_aspects`、`decision_hint`、`confidence` 与 `judge_source`。该 judge 必须由独立的小模型调用承担，而不是继续由本地 token overlap、substring、trigram 或同构启发式担任正式主裁决。其职责是回答“证据是否回答了问题、是否只能部分回答、还缺哪些方面”，而不是产出最终用户姿态。

选择原因：`topic mismatch（主题不匹配）`、`partial coverage（部分覆盖）`、`missing aspects（缺失方面）` 本质上是语义判别问题，不适合继续用 token overlap、trigram 或槽位硬编码来做正式主裁决。

备选方案：

- 继续使用 token overlap / trigram / 本地启发式作为“semantic”近似：实现成本低，但准确性和可维护性都不够，也会把旧规则链换壳保留。
- 让 planner 直接接管全部证据判别：会稀释 `sufficiency` 的边界，也会让 planner 越过 deterministic backend 的验证职责。

### 决策 3：保留 deterministic validator，只做硬边界
保留 `deterministic validator` 作为第二层，仅负责：

- 最小证据存在性
- 噪声证据类型拦截（如仅 `front_matter/reference`）
- 引用/证据存在性和明显越界阻断
- judge 不可用时的高严重度失败语义

validator 不再根据问题类型词表推断“应该缺什么”，只负责验证“当前输出是否踩边界”。

选择原因：这类检查天然适合确定性实现，而且需要稳定、可审计、可回放。

备选方案：

- 把所有校验也交给 judge：边界会变模糊，且会损伤可审计性。
- 在 judge 失败时回落到本地启发式：会重新引入一条隐性规则旁路，破坏“独立小模型主裁决”的设计边界。

### 决策 4：输出契约从槽位名迁移到覆盖摘要
`sufficiency` 输出将从旧的 `missing_key_elements`、`key_element_coverage` 主口径，迁移为：

- `coverage_summary`
- `missing_aspects`
- `allows_partial_answer`
- `judge_source`
- `validator_source`

必要时可以保留兼容字段做迁移期透传，但这些字段不再是主契约，也不应再驱动上游逻辑。

选择原因：旧槽位名直接绑定了被删除的规则系统。如果不改输出契约，上层代码会继续反向要求把规则补回来。

备选方案：

- 仅在内部换实现，保留旧输出字段：兼容性高，但会固化旧心智模型。
- 一次性彻底删除兼容字段：边界最清晰，但集成改造成本更高。

### 决策 5：清理 `qa.py` 中与 sufficiency 同构的重复规则
如果 `qa.py` 中的词表、问题类型或主题不足判断仅用于支撑 `sufficiency`，则在本次改造中删除或降权，重点包括 `KEY_ELEMENT_*`、`QUESTION_TYPE_*` 及其派生判断，避免新旧两套规则残留。与控制意图、planner 路由等其他职责直接相关的规则不在本次删除范围内。

选择原因：仅重写 `sufficiency.py` 而不清理 `qa.py`，会保留双份规则资产，后续仍会发生漂移。

备选方案：

- 先不动 `qa.py`：实施范围更小，但无法真正解决维护扩张问题。
- 大规模拆分 `qa.py`：长期更合理，但超出本次变更范围。

## 风险 / 权衡

- [judge 初期不稳定] → 先通过 trace 记录 `coverage_summary`、`missing_aspects` 与旧规则结果对比，验证后再完全切主。
- [删除规则后早期回归样例会失败] → 重写测试口径，从“词表命中”改为“结构化证据覆盖判断”。
- [上层仍依赖旧槽位字段] → 设计迁移期兼容字段，但禁止新增调用方继续绑定这些字段。
- [`qa.py` 残留同构规则] → 在实现期显式盘点只为 `sufficiency` 服务的常量和路径，并一并清理。
- [judge 调用失败导致系统不可用] → 允许按现有 LLM client 重试，但重试后必须直接返回高严重度系统错误；禁止回退到本地启发式或旧规则链。

## 迁移计划

1. 先盘点并标记 `sufficiency.py` 与 `qa.py` 中所有与证据语义判别相关的静态规则。
2. 引入 `semantic evidence judge` 抽象，并将 `sufficiency` 先改造成“judge + validator”双输出结构。
3. 为上层保留有限兼容字段，但将主消费字段切换到 `coverage_summary` / `missing_aspects`。
4. 删除旧的静态问题类型、关键要素槽位与近似语义裁决路径，确保 judge 不可用时进入高严重度失败语义，而不是旧规则回退。
5. 最后清理相关测试、trace 文档和注释，防止后来者继续往 `sufficiency` 里补词表规则。

## 开放问题

- 迁移期是否保留 `missing_key_elements` 兼容字段一到两个版本，还是直接只保留 `missing_aspects`？
- `judge_system_error` 的用户可见文案，是否统一为系统错误模板，还是允许 planner 根据场景包装成“稍后重试”提示？
