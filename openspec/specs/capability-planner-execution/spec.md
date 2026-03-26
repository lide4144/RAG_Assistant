# capability-planner-execution 规范

## 目的
定义统一解析与能力规划节点、LangGraph 顶层 planner runtime、受限 tool 执行契约及其观测边界，确保聊天链路能够在目录筛选、跨文档总结、研究辅助与严格事实问答之间执行受控分流，并为后续 agent-first tool 扩展提供稳定顶层运行时。
## 需求
### 需求:系统必须禁止规则规划器参与线上正式执行
系统必须将 `rule planner` 退出线上正式执行链；`rule planner` 可以保留为离线评测、开发诊断或历史回放资产，但禁止在用户请求的正式执行路径中生成或替换顶层 `planner decision`。

#### 场景:线上请求只接受 LLM 正式决策
- **当** 一条 `Local` 聊天请求进入顶层 planner runtime
- **那么** 系统必须只接受通过 validation 的 `LLM planner decision` 作为正式执行输入，且不得再调用 `rule planner` 生成本轮正式决策

### 需求:系统必须提供统一解析与能力规划节点
系统必须在进入主 QA 流之前调用统一的解析与能力规划节点，并一次性输出 `is_new_topic`、`standalone_query`、`primary_capability`、`decision_result`、`knowledge_route`、`research_mode`、`requires_clarification`、`selected_tools_or_skills`、`action_plan`、规划置信度与结构化 fallback；禁止将换题检测、路径选择与 tool 选择拆成多个彼此无约束的前置步骤。

#### 场景:统一节点输出结构化计划
- **当** 用户输入“列出我昨天上传的 3 篇大模型论文，并用表格对比一下它们的方法差异”
- **那么** 系统必须输出包含新话题判断、独立问题与两步 `action_plan` 的结构化规划结果

#### 场景:统一节点输出顶层策略与执行计划
- **当** 用户输入“如果本地没有这方面的论文，就帮我联网查最近的综述，否则先总结库里的相关工作”
- **那么** 系统必须输出包含本地/联网路径判断、受限 action plan、fallback 语义与规划置信度的结构化结果

### 需求:系统必须将 LangGraph shell 定义为顶层 LLM Planner runtime
系统必须将现有 LangGraph shell 定义为顶层 `LLM Planner runtime`，统一承接用户意图理解、tool 选择、执行顺序、澄清判断与降级决策；禁止继续将其仅定义为临时兼容壳层或仅用于路由现有 QA 分支的薄包装。

#### 场景:planner runtime 成为顶层唯一编排入口
- **当** `Local` 聊天请求进入 Python kernel
- **那么** 系统必须先进入顶层 planner runtime，再由 runtime 决定调用哪些受支持能力或进入受控结束路径

### 需求:系统必须提供基于 LangGraph 的顶层 planner shell
系统必须在 Python kernel 聊天入口前提供一个基于 LangGraph 的顶层 planner runtime，由该 runtime 统一承接聊天请求状态、LLM 或规则 planner 决策、tool 选择、节点调度、失败回退与执行路径选择；禁止将顶层编排继续仅以 `qa.py` 内部隐式分支、单独 skill 入口或 Gateway 路由规则的方式扩张。

#### 场景:聊天请求先进入 planner runtime
- **当** Gateway 转发一条新的聊天请求到 Python kernel
- **那么** 系统必须先进入 LangGraph planner runtime，再由 runtime 决定后续调用受支持 tool、兼容路径或受控结束路径

### 需求:系统必须支持 llm-first planner source 与受控结束
系统必须将线上正式 planner source 收敛为 `llm_primary` 单一模式，并在该模式下只允许通过 validation 的 `LLM decision` 驱动顶层执行；禁止继续提供 `rule_only` 或 `llm_primary_with_rule_fallback` 作为线上正式决策模式。系统可以保留与 `rule planner` 相关的离线对比或诊断能力，但这些能力禁止影响本轮用户主执行路径。对于正式模式下的聊天入口，planner LLM 基础设施必须先满足可服务前置条件；若基础设施未就绪，系统必须阻断服务而不是进入普通请求级受控结束。

#### 场景:LLM decision 成为唯一正式执行来源
- **当** 系统运行在线上正式模式且 `LLM planner decision` 通过 validation gate
- **那么** planner runtime 必须将该 decision 作为唯一正式顶层决策继续执行，而不得再请求 `rule planner` 生成替代结果

#### 场景:离线对比不影响主路径
- **当** 系统为了评测或诊断额外生成 planner 诊断记录
- **那么** 这些诊断记录必须只写入观测或评测路径，不得改变 `selected_path`、`decision_result` 或用户最终可见回答

#### 场景:基础设施未就绪时不进入普通受控结束
- **当** 系统运行在线上正式模式但 planner LLM 基础设施未满足执行前置条件
- **那么** 聊天入口必须进入系统级阻断状态，而不得继续返回看似正常的 `controlled_terminate` 单轮结果

### 需求:系统必须优先稳定主聊天问答路径，其他路径允许兼容接入
第一阶段系统必须优先保证 `Local` 主聊天问答路径可以稳定通过 planner runtime 承接；对于 `catalog`、`summary`、`control` 等 Local 内部分支，允许先通过兼容节点、委托现有函数或 passthrough 方式接入；`Web` 与 `Hybrid` 禁止被要求在第一阶段一并迁入 planner runtime。

#### 场景:非主路径先以兼容节点接入
- **当** planner runtime 路由到 `catalog`、`summary` 或 `control` 路径
- **那么** 系统可以先通过兼容节点或 passthrough 调用现有能力实现，只要 runtime 入口、状态对象与回退语义保持统一

#### 场景:Web 与 Hybrid 在第一阶段保持原链路
- **当** 用户以 `web` 或 `hybrid` 模式发起聊天请求
- **那么** 系统必须继续走现有链路，不要求在第一阶段进入 planner runtime

### 需求:系统必须显式区分 Planner、Tool 与确定性 Pipeline 三层职责
系统必须显式区分 `LLM Planner`、`tool 层` 和 `确定性 pipeline / kernel` 的职责边界；Planner 必须负责理解、选择、排序、澄清和停止，tool 层必须负责基于注册契约执行受约束能力调用并返回结构化结果，确定性 pipeline 必须负责检索、证据门控、引用绑定、任务状态和可审计落盘；禁止任一层无边界吞并其他两层职责，也禁止 planner 直接调用未经过 tool registry 解析的 kernel 私有函数。

#### 场景:planner 仅决定调用关系
- **当** planner 判定一次请求需要先查论文集合再做跨文档总结
- **那么** planner 必须只输出受支持的调用顺序和参数，而不是直接绕过 tool/pipeline 自行生成最终证据化回答

#### 场景:tool 层承接受约束执行
- **当** planner 已选择某个已注册 tool
- **那么** runtime 必须先通过 tool 层解析和执行该调用，再由底层 pipeline 负责具体检索、citation 与 gate 约束

### 需求:系统必须为 Planner runtime 暴露稳定的 tool 调用契约
系统必须为 Planner runtime 暴露稳定的 tool 调用契约，使后续具体能力可以作为 planner 可调用工具接入；该契约必须至少支持 registry 级 tool 元数据、结构化输入、结构化结果、失败原因、流式支持声明、evidence policy、可观测元数据和依赖前序产物；禁止让 planner 直接耦合某个 kernel 内部函数的私有调用细节。

#### 场景:新能力以 tool contract 接入
- **当** 后续变更把 `catalog_lookup` 或 `paper_assistant` 能力整理为 agent tool
- **那么** planner runtime 必须能够通过统一 tool contract 调用它，而不要求 Gateway 或前端理解该工具的内部实现

#### 场景:runtime 读取 tool 元数据决定执行约束
- **当** 某个已注册 tool 声明 `streaming_mode=final_only` 且 `evidence_policy=citation_forbidden`
- **那么** runtime 必须按该元数据约束执行与结果组装，而不是由 planner 或 gateway 临时猜测

### 需求:系统必须让 planner runtime 消费标准化 planner decision
planner runtime 必须将顶层 `planner decision` 作为正式输入给后续路由与执行节点，并从中读取 `decision_result`、`knowledge_route`、`selected_tools_or_skills`、`action_plan` 与 `fallback`；禁止继续仅依赖散落在 state 中的临时决策字段解释下一步路径。

#### 场景:runtime 根据 decision_result 选择路径
- **当** planner 返回 `decision_result=delegate_web`
- **那么** runtime 必须将本轮请求委托到既有联网链路或受支持委托路径，而不是继续在本地执行 tool 计划

### 需求:系统必须为 planner shell 暴露统一状态对象
系统必须为 planner runtime 暴露统一状态对象，至少包含请求元信息、planner 决策字段、tool 调用字段、执行结果字段、fallback 字段与响应字段；后续节点必须通过该状态对象读写，不得依赖未声明的临时全局变量、隐式上下文或绕过 state 的私有副作用。

#### 场景:节点通过统一状态传递规划与执行结果
- **当** planner 节点完成意图理解并选择下一步 tool
- **那么** 后续路由和执行节点必须从统一状态对象读取能力选择、依赖产物、fallback 标记和响应上下文

### 需求:系统必须提供无规则回退的受控失败收束
当 `LLM planner decision` 被 validation 拒绝、planner runtime 节点抛出异常、或关键状态校验失败时，系统必须进入受控失败收束路径，并输出可审计的失败类型与最终用户可见姿态；禁止通过 `rule planner`、`legacy QA` 或其他旧规则链补写一份替代性的顶层正式决策。

#### 场景:validation reject 不触发规则回退
- **当** `LLM planner decision` 在结构、语义、执行或策略任一层校验失败
- **那么** planner runtime 必须停止接受该 decision，并进入受控失败收束路径，而不得切换到 `rule planner`

#### 场景:运行时异常不切回旧问答主链
- **当** planner runtime 在规划、路由或 tool 调度阶段抛出异常
- **那么** 系统必须返回受控且可审计的失败收束结果，并记录异常原因，而不得回退到旧 `qa.py` 主链重做顶层决策

### 需求:系统必须区分 planner fallback 与 tool/pipeline fallback
系统必须区分 `planner fallback` 与 `tool/pipeline fallback` 两类降级：前者用于规划失败、状态不完整、置信不足或策略禁止继续 agent 执行；后者用于 tool 调用失败、结果为空、证据不足或 citation 不满足；两类回退都必须是受控的，并禁止继续无限步自治重试。

#### 场景:planner 决策失败时进入受控结束
- **当** planner runtime 无法形成有效的能力选择结果
- **那么** 系统必须记录 `planner fallback` 并进入受控结束路径

#### 场景:tool 结果不满足依赖时停止后续步骤
- **当** 某个 tool 返回空结果或未满足 evidence/citation 前置条件，且后续步骤依赖该结果
- **那么** 系统必须触发 `tool/pipeline fallback`、停止后续依赖步骤，并返回受控失败、澄清或降级答案

### 需求:系统必须将 planner 决策与 QA 交互姿态解耦
系统必须将“是否澄清、是否给部分回答、是否拒答”的顶层交互姿态定义为 `planner / policy（规划器 / 策略层）` 的唯一决策结果，而 deterministic kernel（确定性内核）仅负责输出证据、依赖、引用或执行约束信号；禁止继续由 `qa.py`、`sufficiency gate（充分性门控）`、`evidence gate（证据门）` 或其他尾部规则在 planner 决策之后独立重写本轮最终交互姿态。系统必须通过统一的 `constraints envelope（约束信封）` 将底层阻塞信息回传给 planner，再由 planner 统一决定最终用户可见姿态。

#### 场景:kernel 输出约束信号但不独占最终姿态
- **当** deterministic kernel（确定性内核）判定当前请求证据不足、依赖不满足或引用不合法
- **那么** kernel 必须输出结构化约束信号供 `planner / policy（规划器 / 策略层）` 消费，而不是绕过顶层 planner 直接决定最终用户姿态

#### 场景:planner 成为用户交互姿态真相源
- **当** 本轮请求最终以 `clarify（澄清）`、`partial_answer（部分回答）` 或 `refuse（拒答）` 收束
- **那么** 运行 trace 必须能表明该姿态来自 `planner / policy（规划器 / 策略层）` 的最终决策，且不得存在 `legacy qa tail override（旧问答尾部改写）`

### 需求:系统必须区分顶层委托与本地执行
当 planner 输出 `local_execute`、`delegate_web`、`delegate_research_assistant`、`clarify` 或 `controlled_terminate` 时，runtime 必须按该顶层结果执行互斥路径；禁止把联网委托、研究辅助委托和本地 tool 执行混成同一类本地 passthrough。

#### 场景:研究辅助结果走独立委托语义
- **当** planner 返回 `decision_result=delegate_research_assistant`
- **那么** runtime 必须进入研究辅助能力路径，并保持该路径与普通本地 tool 执行在 trace 和 fallback 上可区分

### 需求:系统必须支持受限的多动作计划执行
系统必须支持受限的顺序执行计划，允许的动作仅包括已注册且当前策略允许的 `tool/skill` 条目；对于本地执行路径，计划步数必须有硬上限，且每个后续步骤必须显式声明对前序产物的依赖。对于 `delegate_web`、`delegate_research_assistant`、`clarify` 与 `controlled_terminate`，系统禁止继续展开本地无限步计划。

#### 场景:复合查询拆解为两步执行
- **当** 规划结果包含 `catalog_lookup -> cross_doc_summary`
- **那么** 系统必须先生成 `paper_set`，再以该集合为输入执行总结步骤

#### 场景:本地执行路径保持有限步
- **当** 规划结果为 `decision_result=local_execute` 且 `action_plan` 包含 `catalog_lookup -> cross_doc_summary`
- **那么** 系统必须按声明依赖顺序执行有限步计划，并在达到步数上限或依赖失败时停止

#### 场景:联网委托不展开本地多步计划
- **当** 规划结果为 `decision_result=delegate_web`
- **那么** 系统必须停止本地 action plan 扩张，并将请求委托到既有联网路径

### 需求:系统必须在上游结果为空时短路后续步骤
当某一步产物为空且被后续步骤依赖时，执行器必须短路并返回受控失败结果；禁止将空集合继续传入 summary、paper assistant 或 fact QA 流程。

#### 场景:目录查询为空时终止后续对比
- **当** `catalog_lookup` 未找到符合条件的论文且后续存在 `cross_doc_summary`
- **那么** 系统必须停止执行后续步骤，并明确返回“未找到符合条件的论文，因此未继续执行后续步骤”

### 需求:系统必须对计划输入集合施加硬上限与截断披露
系统必须对由 `catalog_lookup` 产生并传入后续步骤的论文集合施加硬上限，输出至少 `matched_count`、`selected_count` 与 `truncated` 等字段；禁止将未经裁剪的大结果集直接送入后续总结或问答步骤。

#### 场景:大结果集被裁剪并披露
- **当** `catalog_lookup` 命中 500 篇论文而执行器上限为 20
- **那么** 系统必须仅将 20 篇论文传入后续步骤，并在结果中披露总命中数、选中数与截断事实

### 需求:系统必须拦截伪装成 summary 的严格事实问题
当问题包含精确数值、作者、年份、会议、实验设置等 strict fact 信号时，系统必须将其升级为 `strict_fact` 严格度并走 `fact_qa` 路径；禁止仅因问题出现“对比”“表格”“总结”等表述而直接流入宽松 summary 流程。

#### 场景:准确率数值对比被升级为严格事实问答
- **当** 用户输入“对比这 3 篇论文的准确率具体数值”
- **那么** 系统必须将该问题识别为 `strict_fact`，并走严格证据门控路径而不是 summary 路径

### 需求:系统必须禁止 planner 绕过 kernel 安全边界
系统必须禁止 planner 绕过 kernel 的 evidence gate、citation contract、任务状态管理、审计 trace 和硬上限约束；即使 planner 选择了工具或组合能力，最终回答仍必须经过确定性安全边界校验后才能对外输出。

#### 场景:planner 不能直接跳过证据约束
- **当** planner 选择某个总结或研究辅助能力生成回答
- **那么** 系统必须仍然通过 kernel 的 evidence 与 citation 约束校验输出，而不是直接把 planner 中间结果暴露给用户

### 需求:系统必须提供 planner 与执行器观测字段
系统必须在运行 trace 中输出 planner runtime（规划运行时）、tool execution（工具执行）与最终交互姿态的观测字段，至少包含 `planner_used（是否使用规划器）`、`planner_source（规划器来源）`、`decision_result（决策结果）`、`primary_capability（主能力）`、`selected_path（选中路径）`、`execution_trace（执行轨迹）`、`planner_fallback（规划器回退）`、`tool_fallback（工具回退）`、`final_interaction_authority（最终交互裁判）`、`interaction_decision_source（交互决策来源）`、`final_user_visible_posture（最终用户可见姿态）` 与 `kernel_constraint_summary（内核约束摘要）`。禁止仅记录 planner 选择而无法还原最终交互姿态由谁决定。

#### 场景:顶层决策与最终姿态共同可审计
- **当** 系统经由 planner runtime（规划运行时）完成一次本地执行、委托、澄清或回退
- **那么** trace 中必须同时记录顶层 planner 决策、底层执行结果与最终用户可见姿态来源

#### 场景:被禁止的尾部改写可识别
- **当** 某个下游组件试图在 planner 决策之后重新写入最终姿态
- **那么** 系统必须将其标记为违反本规范的错误状态，并在 trace 中可识别

### 需求:系统必须在执行前解析 registry 级 tool 定义
系统必须在本地执行任一 planner action 之前先从已注册的 tool registry 解析对应 tool 定义，并据此校验 `tool_name`、输入参数、依赖产物、`streaming_mode` 与 `evidence_policy`；禁止直接把 planner 生成的 action 名称当作未经校验的内部函数调用。

#### 场景:本地执行前先做注册校验
- **当** planner decision 选择 `catalog_lookup -> cross_doc_summary`
- **那么** runtime 必须先解析这两个 action 对应的 registry 定义，再进入具体执行步骤

### 需求:系统必须记录 planner 与 tool execution 的独立观测字段
系统必须在统一状态对象和运行 trace 中同时保留顶层 planner 字段与底层 tool execution 字段。tool execution 字段至少必须包含 `call_id`、`tool_name`、`tool_status`、`failure_type`、`streaming_mode`、`evidence_policy` 与 `produced_artifacts`；禁止仅通过 planner decision 推断实际执行结果。

#### 场景:顶层决策与底层执行可区分
- **当** planner 选择 `cross_doc_summary`，但执行阶段因依赖缺失而停止
- **那么** trace 中必须既能看到 planner 原始决策，也能看到该 tool 的实际失败状态与停止原因

### 需求:系统必须在正式聊天入口前阻断不可用的 planner LLM 基础设施
系统在正式聊天模式下必须将 planner LLM 视为执行前置基础设施，并必须在请求进入主 planner runtime 之前完成门禁检查；当 planner 模型缺失、密钥缺失、运行态配置无效或健康状态已确认 planner 基础设施不可用时，系统必须阻断正式聊天执行，禁止继续进入普通 planner fallback、tool fallback 或 `controlled_terminate` 请求链路。

#### 场景:正式聊天请求在 planner 基础设施缺失时被入口阻断
- **当** 一条正式 `Local` 聊天请求到达 Kernel 且 planner model 或 planner API key 不可用
- **那么** 系统必须直接返回系统级阻断结果，并且不得继续进入 planner decision validation 或 tool 执行阶段

### 需求:系统必须区分系统级阻断与请求级失败收束
系统必须将 `planner LLM` 不可用、未就绪或被正式模式判定为无效配置的情况定义为系统级阻断；系统必须仅将单轮规划失败、validation reject、tool 失败或运行时异常定义为请求级失败收束。系统禁止继续使用单一 `controlled_terminate` 语义同时表达这两类状态。

#### 场景:单轮规划失败不等同于系统阻断
- **当** planner 基础设施已就绪但某一轮请求的 LLM decision 被 validation 拒绝
- **那么** 系统必须将该结果记录为请求级失败收束，而不得把整个聊天服务标记为系统级阻断

