## 为什么

当前 agent-first 路线已经明确由顶层 planner runtime 负责理解与决策，但 Python kernel 里的 retrieval、summary、fact QA、control、中文化与研究辅助能力仍大多以内部流程步骤或私有函数形式存在，planner 只能“知道有这些能力”，却没有稳定的可调用 tool 契约。这会让后续能力扩展继续耦合 kernel 实现细节，也无法一致表达输入输出、失败语义、流式行为和 evidence gate 约束。

现在需要补上这层契约，因为 `shift-to-agent-first-planner-runtime` 与 `add-llm-planner-tool-selection-policy` 已经固定了顶层运行时和 planner decision 语义；如果不尽快把底层可复用能力整理为 agent tools，planner/tool/kernel 三层边界仍会停留在概念层，后续研究辅助、中文化和控制类能力也会继续以旁路方式扩张。

## 变更内容

- 新增 kernel agent tools capability，定义 planner 可消费的 tool registry、tool call/result envelope、失败分类、流式输出约束、evidence gate policy 与依赖产物传递方式。
- 将现有本地能力按 agent-first 方式整理为分阶段可工具化的 tool family，首批覆盖 `catalog_lookup`、`fact_qa`、`cross_doc_summary`、`control`、`paper_assistant`，并为 `title_term_localization`、研究辅助组合能力等后续工具化保留稳定注册入口。
- 明确顶层 planner 与底层 tool execution 的职责边界：planner 只负责选择、排序、停止、澄清与降级；tool 只负责受约束执行；kernel pipeline 继续负责检索、引用、证据门控、任务状态与 trace。
- 补充不同 tool 类型的输出语义，区分 citation-bearing、metadata-bearing、explanatory 三类结果，避免目录查询、控制或中文化结果被错误当作事实证据或 citation。

## 功能 (Capabilities)

### 新增功能
- `kernel-agent-tools`: 定义 Python kernel 对 planner 暴露的 agent tool registry、统一调用契约、返回结构、失败语义、流式规则、evidence gate policy 和分阶段工具化范围。

### 修改功能
- `capability-planner-execution`: 要求 planner runtime 通过注册后的 tool contract 执行本地能力，并显式区分顶层 planner decision 与底层 tool execution 观测字段、停止点和回退语义。
- `paper-assistant-mode`: 要求研究辅助能力以 planner 可调用 tool/skill 形式接入，声明前置条件、结构化输入输出、失败语义与证据约束，而不是保留为旁路模式。
- `unified-source-citation-contract`: 要求不同 tool 输出在来源结构上显式区分 citation-bearing、metadata-bearing 与 explanatory provenance，禁止将中文化或控制类结果伪装成正文 citation。

## 影响

- Python kernel planner/runtime：`app/planner_runtime.py`、`app/capability_planner.py`、未来 tool registry 与执行适配层。
- 现有能力封装边界：catalog、summary、fact QA、control、paper assistant、标题/术语中文化等能力的接入方式。
- 观测与评测：tool call trace、streaming 事件分类、tool/pipeline fallback 分类、evidence gate 命中记录。
- 后续变更依赖：研究辅助组合技能、agent observability、gateway execution events 将基于本变更定义的 tool contract 继续推进。
