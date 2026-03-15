## ADDED Requirements

### 需求:系统必须提供 kernel agent tool registry
系统必须在 Python kernel 中提供面向 planner runtime 的 `tool registry`，并以注册项而非私有函数名作为本地能力真相源。每个注册项必须至少声明 `tool_name`、`capability_family`、`version`、`planner_visible`、`input_schema`、`result_schema`、`failure_types`、`streaming_mode`、`evidence_policy`、`produces` 与 `depends_on`；禁止让 planner 直接依赖未注册的内部函数、分支名或 endpoint 细节。

#### 场景:planner 读取已注册 tool 元数据
- **当** planner runtime 构建本轮可用 `capability_registry`
- **那么** registry 中的每个本地 tool 必须包含稳定名称、能力分类、输入输出契约和 evidence/streaming 元数据

#### 场景:未注册能力不可作为 tool 暴露
- **当** 某个 kernel 内部函数尚未注册到 tool registry
- **那么** planner runtime 必须禁止将其暴露为可调用 tool

### 需求:系统必须为 tool 调用提供统一 call envelope
系统必须让 planner runtime 以统一 `call envelope` 调用本地 tool，至少包含 `call_id`、`tool_name`、`arguments`、`depends_on_artifacts`、`trace_context` 与 `execution_mode`；禁止让不同 tool 使用彼此不兼容的顶层调用结构。

#### 场景:顺序计划中的后续步骤消费前序产物
- **当** `cross_doc_summary` 依赖 `catalog_lookup` 产生的 `paper_set`
- **那么** runtime 必须在 `call envelope` 中显式传递依赖产物，而不是要求 tool 自行回溯 planner 内部状态

### 需求:系统必须为 tool 执行提供统一 result envelope
系统必须让每个 tool 返回统一 `result envelope`，至少包含 `status`、`output`、`artifacts`、`sources`、`warnings` 与 `observability`；其中 `artifacts` 必须显式声明可供后续步骤复用的命名产物，`sources` 必须与来源契约兼容；禁止仅返回自由文本或隐式副作用作为唯一结果。

#### 场景:catalog tool 返回可复用 paper_set
- **当** `catalog_lookup` 成功命中论文集合
- **那么** result envelope 必须在 `artifacts` 中返回可命名复用的 `paper_set`，并在 `output` 中返回匹配计数与选中集合摘要

### 需求:系统必须为 tool 失败提供稳定 failure 语义
系统必须让每个 tool 在失败或阻塞时返回稳定 `failure envelope`，至少包含 `failure_type`、`retryable`、`user_safe_message`、`failed_dependency` 与 `stop_plan`。`failure_type` 必须从已声明集合中选择，至少覆盖 `invalid_input`、`precondition_failed`、`empty_result`、`insufficient_evidence`、`timeout` 与 `execution_error`；禁止仅以未结构化异常字符串表达失败。

#### 场景:目录查询为空触发受控失败
- **当** `catalog_lookup` 未找到符合条件的论文
- **那么** tool 必须返回 `failure_type=empty_result`、`stop_plan=true` 和可直接面向用户披露的安全说明

#### 场景:研究辅助前置条件不足触发阻塞
- **当** `paper_assistant` 缺少主题范围或必要论文集合
- **那么** tool 必须返回 `failure_type=precondition_failed` 并附带面向 planner/runtime 的阻塞原因

### 需求:系统必须显式声明每个 tool 的流式支持模式
系统必须要求每个已注册 tool 显式声明 `streaming_mode`，其值必须限制为 `none`、`final_only` 或 `text_stream`。当 tool 声明 `text_stream` 时，系统仍必须在结束时回收为完整 final result；禁止由 gateway、前端或 planner 自行猜测某个 tool 是否可流式。

#### 场景:summary tool 声明文本流式
- **当** `cross_doc_summary` 被注册为支持流式输出
- **那么** registry 必须显式标记 `streaming_mode=text_stream`，且 tool 完成后仍返回完整 result envelope

#### 场景:control tool 禁止伪流式
- **当** `control` 仅返回结构化格式或样式指令
- **那么** registry 必须将其标记为 `streaming_mode=final_only` 或 `none`，而不是伪装成文本流式 tool

### 需求:系统必须显式声明每个 tool 的 evidence gate policy
系统必须要求每个已注册 tool 显式声明 `evidence_policy`，其值必须限制为 `citation_required`、`citation_optional` 或 `citation_forbidden`。tool 的最终输出和来源结构必须服从该声明；禁止由调用方临时猜测某个 tool 是否需要 evidence gate。

#### 场景:fact qa 需要严格证据门控
- **当** `fact_qa` 注册到 tool registry
- **那么** 系统必须声明其 `evidence_policy=citation_required`

#### 场景:中文化工具禁止冒充正文证据
- **当** `title_term_localization` 作为 explanatory tool 注册
- **那么** 系统必须声明其 `evidence_policy=citation_forbidden`，且结果不得直接作为正文事实 citation 输出

### 需求:系统必须支持现有 kernel 能力的分阶段工具化
系统必须允许现有 kernel 能力以分阶段方式进入 tool registry。第一阶段至少必须支持 `catalog_lookup`、`fact_qa`、`cross_doc_summary`、`control` 与 `paper_assistant`；同时必须为 `title_term_localization` 和后续研究辅助组合能力保留稳定注册入口，禁止要求一次性重写全部底层实现后才能开始 agent tool 化。

#### 场景:首批运行时能力进入 registry
- **当** 系统启用本地 agent tool registry
- **那么** 首批已存在的 retrieval、summary、fact QA、control 与研究辅助能力必须能以注册项形式被 planner/runtime 发现

#### 场景:后续能力通过同一注册入口扩展
- **当** 后续变更引入标题中文化或更细粒度研究辅助工具
- **那么** 新能力必须通过同一 registry 与 tool contract 接入，而不是重新创建绕过 registry 的旁路入口

## MODIFIED Requirements

## REMOVED Requirements
