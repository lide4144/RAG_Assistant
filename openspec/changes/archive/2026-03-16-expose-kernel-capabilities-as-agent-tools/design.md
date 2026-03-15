## 上下文

当前仓库已经完成 agent-first 路线的两个前置步骤：

- `capability-planner-execution` 已把 LangGraph shell 定义为顶层 planner runtime，并要求 planner、tool、deterministic kernel 三层职责分离；
- `llm-planner-tool-selection-policy` 已固定 planner decision 输入输出、有限顶层决策结果与 registry 驱动的选择语义。

但在 Python kernel 内部，当前可复用能力仍主要以执行函数、兼容分支或特例模式存在。虽然代码里已经出现了 `catalog_lookup`、`fact_qa`、`cross_doc_summary`、`control`、`paper_assistant` 等运行时名称，`docs/planner-runtime-contract.md` 也给出了最小 envelope 草案，但它们还不是一套完整的 agent tool 契约：

- 各能力的输入输出结构没有统一 schema 层定义；
- 失败语义目前主要停留在实现细节或 trace 字段，缺少稳定分类；
- 是否支持流式、何时允许流式、何时必须 final-only 尚未固定；
- 哪些结果属于 citation-bearing、哪些只属于 metadata/explanatory provenance 还未成为正式规范；
- “中文化”“研究辅助组合能力”等后续工具化入口尚未被纳入统一注册表。

本次变更要解决的是“tool contract 层缺失”，而不是重写底层 pipeline，也不是为 planner 设计新的决策策略。核心约束如下：

- 不重写 `qa.py`、检索、citation、evidence gate、任务状态等底层核心逻辑；
- 不在本次变更中定义 LLM planner 的选型、prompt 或策略细则；
- 不触碰前端和 gateway 协议；
- 必须沿用现有 planner runtime 作为唯一顶层入口；
- 必须允许当前私有能力逐步被 tool 化，而不是要求一次完成所有替换。

## 目标 / 非目标

**目标：**

- 定义一个对 planner runtime 稳定可见的 kernel tool registry 与 tool contract。
- 明确每个 tool 至少需要声明什么：输入、输出、失败语义、流式支持、evidence gate policy、产物依赖。
- 明确 planner 只负责选择与排序，tool 层只负责受约束执行，kernel 继续负责确定性安全边界。
- 为首批现有能力给出 agent-first 工具化归类，并为后续中文化、研究辅助组合能力保留可扩展入口。
- 让 citation-bearing、metadata-bearing、explanatory 三类输出在来源结构上可区分且可审计。

**非目标：**

- 不在本次变更中实现新的 LLM planner 决策策略或 prompt。
- 不要求重构底层 retrieval、summary、fact QA、control pipeline 的核心实现。
- 不在本次变更中定义前端展示 planning/tool-running 状态的协议。
- 不在本次变更中要求 Web/Hybrid 一并切入同一 tool registry。
- 不把“所有未来能力”一次性冻结为完整工具目录，只定义首批与扩展机制。

## 决策

### 决策 1：新增独立的 `kernel-agent-tools` capability，而不是把细节继续塞进 planner spec

本次变更新增独立 capability `kernel-agent-tools`，专门承载 registry、tool contract、failure contract、streaming 与 evidence policy。`capability-planner-execution` 保留顶层运行时与边界语义，但不再承担逐个 tool 的细节定义。

原因：

- planner runtime spec 负责“谁决定、谁执行、如何回退”，不适合继续膨胀为所有 tool 的字段手册；
- 单独 capability 更适合未来继续增补 `localization`、研究辅助组合工具或 reference resolution tool；
- 工具契约属于跨能力共享层，后续 gateway events、observability、evals 都会依赖它。

替代方案：

- 只修改 `capability-planner-execution`：会让运行时 spec 继续膨胀，难以维护。
- 为每个 tool 单独开一个 capability：首批会过度碎片化，尚未形成共享 schema。

### 决策 2：采用“registry entry + call envelope + result envelope + failure envelope”四层契约

每个 tool 需要四层正式契约：

1. `registry entry`
   - 声明 `tool_name`、`capability_family`、`version`、`planner_visible`、`streaming_mode`、`evidence_policy`、`input_schema`、`result_schema`、`failure_types`、`produces`、`depends_on`。
2. `call envelope`
   - 由 runtime 生成 `call_id`、`tool_name`、`arguments`、`depends_on_artifacts`、`trace_context`、`execution_mode`。
3. `result envelope`
   - 统一返回 `status`、`output`、`artifacts`、`sources`、`warnings`、`observability`。
4. `failure envelope`
   - 统一返回 `status=failed|blocked`、`failure_type`、`retryable`、`user_safe_message`、`failed_dependency`、`stop_plan`。

原因：

- 这样才能把“可规划能力”和“实现函数”分开；
- 运行时可以稳定记录 trace，而不是把失败原因散落在日志字符串；
- planner 未来更换为 LLM 或混合策略时，不会影响下游执行与观测。

替代方案：

- 只保留 call/result 两层：会把阻塞与失败语义挤进自由文本，后续难做回退治理。
- 直接复用内部 Python 函数签名：会把私有实现细节泄露给 planner。

### 决策 3：用三类 evidence policy 固定 tool 输出边界

每个 tool 必须声明 `evidence_policy`，首批限制为三类：

- `citation_required`
  - 适用于 `fact_qa` 以及研究辅助中包含强断言的结论部分；
- `citation_optional`
  - 适用于 `cross_doc_summary`、`paper_assistant` 中的综合性总结段，允许解释性组织，但若生成关键结论仍必须绑定来源；
- `citation_forbidden`
  - 适用于 `catalog_lookup`、`control`、`title_term_localization` 这类 metadata/explanatory 工具，禁止把结果渲染为正文 citation 事实。

原因：

- 用户要求明确哪些 tool 受 evidence gate 约束；
- 当前最容易出错的是目录查询和中文化结果被误当成事实证据；
- 明确 policy 后，source contract 和 gate contract 才能协同工作。

替代方案：

- 所有 tool 统一走 evidence gate：会错误打击 catalog/control/localization。
- 所有 tool 都放宽约束：会让 fact QA 与研究辅助丢失安全边界。

### 决策 4：流式能力按 tool 声明，而不是由 gateway 或 UI 反推

每个 tool 必须显式声明 `streaming_mode`，首批限制为：

- `none`
- `final_only`
- `text_stream`

其中：

- `catalog_lookup`、`control`、`title_term_localization` 默认 `final_only`；
- `fact_qa`、`cross_doc_summary`、`paper_assistant` 可以声明 `text_stream`，但最终必须仍回收为统一 final result；
- planner 不得因为 tool 支持流式就跳过 final result 或安全校验。

原因：

- 流式是执行层能力，不属于 planner 决策本身；
- 由 tool 自身声明最符合“能力真相源在 kernel”；
- 这也避免 gateway/UI 协议过早绑定内部实现。

替代方案：

- 一律不流式：限制现有问答体验，且与当前系统能力不一致。
- 流式能力交给 gateway 决定：会让 Node 侧复制 Python 语义。

### 决策 5：工具化采用“适配器包裹现有 pipeline”路线，而不是重写 pipeline

首批工具化实现采用 adapter/bridge 方式包裹现有 pipeline：

- `catalog_lookup` 复用现有目录查询与 paper set 选择逻辑；
- `fact_qa` 继续使用当前 strict fact QA 主链；
- `cross_doc_summary` 继续复用总结路径；
- `control` 继续复用控制意图与锚点逻辑；
- `paper_assistant` 继续复用研究辅助逻辑与前置条件判定；
- `title_term_localization` 先定义 contract 和来源类型，后续再接入实现。

原因：

- 用户明确要求不重写底层 pipeline 核心逻辑；
- 现有系统的稳定性主要来自 deterministic pipeline，tool layer 只应做外层封装；
- 这使增量落地和回滚都更容易。

替代方案：

- 先重写成全新 tool-native pipeline：风险高，且与本次边界冲突。

### 决策 6：研究辅助与中文化能力按“组合 tool / explanatory tool”分类接入

首批能力分层如下：

- `retrieval/meta`：`catalog_lookup`
- `qa`：`fact_qa`
- `summary`：`cross_doc_summary`
- `control`：`control`
- `research_assistant`：`paper_assistant`
- `localization`：`title_term_localization`（保留注册入口）

其中：

- `paper_assistant` 视为组合型 tool，可在内部委托 summary/fact 类 pipeline，但对 planner 仍表现为一个受控工具；
- `title_term_localization` 视为 explanatory tool，输出中文化表达与解释性 provenance，不得伪装为 citation。

原因：

- 这符合当前 agent-first 路线中“先稳定 planner/runtime，再逐步工具化”的节奏；
- 也能把旧 skill-first 路线里的中文化需求平滑迁入 tool 体系。

替代方案：

- 把研究辅助拆成多个新 tool 一次性上线：时机过早，增加实现面。
- 继续把中文化保留为隐式 prompt 行为：不可审计，也无法声明证据边界。

## 风险 / 权衡

- [tool contract 过早抽象，后续实现可能想改字段] → 先固定最小字段集，只对必须稳定的 envelope 立规，给 `output` 与 `observability` 留扩展位。
- [paper assistant 同时带总结与建议，evidence policy 容易模糊] → 要求强断言部分仍受 citation 约束，建议类段落必须标记为 explanatory provenance。
- [部分现有能力天然是内部流程，不一定适合直接 tool 化] → 允许通过 adapter 暴露外层契约，不要求内部实现形态一致。
- [流式约束与现有调用链可能不完全一致] → 先把 streaming_mode 定义为声明式元数据，具体事件协议放到后续 gateway/UI 变更再落。
- [中文化 tool 目前未实现，可能被误解为必须立刻上线] → 在 spec 和 tasks 中明确它属于“预注册 + 后续逐步接入”，本次重点是 contract，不是完整实现。

## 迁移计划

1. 在 OpenSpec 层新增 `kernel-agent-tools`，并同步修改 planner/runtime、paper assistant 与 source contract 增量规范。
2. 在实现阶段先引入 registry schema 与 tool adapter 接口，不改动现有 planner decision 对象。
3. 先把已存在的 `catalog_lookup`、`fact_qa`、`cross_doc_summary`、`control`、`paper_assistant` 接到 registry，保持其内部仍调用现有 pipeline。
4. 为 tool 调用新增观测字段、failure type 和 evidence policy 标记，但保持最终用户响应与 gateway 现有协议兼容。
5. 在后续独立变更中逐步接入 `title_term_localization`、更细粒度研究辅助组合 tool 与 execution events。

回滚策略：

- 若 registry/tool adapter 层证明不成熟，可继续保留现有 planner runtime 对 legacy 执行路径的直接委托；
- 本次变更只固定 contract，不要求立即删除旧执行函数，因此回滚主要是停用 registry 接入并保留现有路径。

## 开放问题

- `paper_assistant` 后续是否要进一步拆分为 `paper_compare`、`idea_generation`、`next_question_suggestion` 等更细 tool，还是长期保持组合 tool 形态？
- `title_term_localization` 的输出是否需要单独版本化字典/缓存契约，还是仅作为轻量 explanatory tool？
- tool 的 `failure_type` 是否应在后续实现时沉淀为共享 Python Enum/schema，而不是仅规范化命名？
