## 为什么

当前 `Sufficiency Gate（充分性门控）` 虽然已经在交互权责上降级为 `guardrail（护栏）`，但其内部仍保留大量高维护成本的语义规则：`question type（问题类型）` 词表、`key element（关键要素）` 槽位映射、`token overlap / trigram similarity（词重合 / 三元组相似度）` 近似语义判断，以及基于这些规则直接形成的不足结论。

这些规则在实践中已经暴露出三个问题：

- 真实用户问法变化快，静态词表和槽位映射无法稳定覆盖，且不断堆叠后难以维护。
- `topic mismatch（主题不匹配）`、`missing key elements（关键要素缺失）` 等高不确定性语义判断，本质上不适合继续由硬规则主导。
- `qa.py` 中还存在与 `sufficiency` 同构的常量和判定片段，尤其是 `KEY_ELEMENT_*`、`QUESTION_TYPE_*` 一类证据充分性词表，后续维护极易发生双份规则漂移。

在 `llm-first-planner` 已经把顶层决策收口到 `LLM planner` 之后，证据检验层也需要继续收缩职责边界：删除不该继续维护的语义规则，把 `sufficiency` 变成“`semantic evidence judge（语义证据判别器）` + `deterministic validator（确定性校验器）`”的受限组合，而不是继续扩张规则系统。

## 变更内容

- 删除 `sufficiency.py` 中不应继续维护的语义规则层，包括静态问题类型词表、关键要素槽位映射、基于 token/trigram 的主题近似判定，以及依赖这些规则直接形成不足结论的路径。
- 将 `Sufficiency Gate` 重构为两层：
  - `semantic evidence judge（语义证据判别）`：负责判断证据是否回答问题、是否只能部分回答、还缺什么方面。
  - `hard validator（硬校验）`：负责最小证据存在性、引用/证据类型合法性、明显越界回答拦截。
- 让 `sufficiency` 输出的缺失方面从静态槽位名，收敛为语义判别生成的结构化 `missing_aspects（缺失方面）` 与 `coverage_summary（覆盖摘要）`。
- 删除或降权 `qa.py` 中仅为 `sufficiency` 服务的重复规则常量，尤其是与证据充分性判断同构的 `KEY_ELEMENT_*`、`QUESTION_TYPE_*` 及其派生判定，防止后续出现双份维护；不波及控制意图、planner 路由等不属于本次范围的规则。
- 保留 `evidence/citation guardrails（证据/引用护栏）` 与 planner 交互契约，不把证据检验重新做成开放式自治链。

## 功能 (Capabilities)

### 新增功能

- `sufficiency-gate`: 支持将语义判别与确定性校验分层输出，并以结构化证据覆盖摘要替代旧槽位规则结论。

### 修改功能

- `planner-interaction-authority`: 明确 planner 消费的是 `semantic judge + validator` 组合后的约束摘要，而不是旧规则词表派生结果。

## 影响

- 受影响代码：`app/sufficiency.py`、可能新增的 `app/evidence_judge.py` 或等价模块、`app/qa.py` 中与 `sufficiency` 耦合的重复常量/判定，以及相关测试。
- 受影响测试：`test_m8_sufficiency_gate.py`、`test_sufficiency_semantic_policy.py` 以及 planner/QA 集成回归需要从“词表命中”改为“结构化判别结果”口径。
- 受影响维护方式：后续不再以“补一个规则项”作为默认修复路径，而是优先修正 judge schema、validator 边界或 planner 消费逻辑。
