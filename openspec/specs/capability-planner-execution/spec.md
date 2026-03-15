# capability-planner-execution 规范

## 目的
定义统一解析与能力规划节点、LangGraph 顶层 planner runtime、受限 tool 执行契约及其观测边界，确保聊天链路能够在目录筛选、跨文档总结、研究辅助与严格事实问答之间执行受控分流，并为后续 agent-first tool 扩展提供稳定顶层运行时。

## 需求
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
- **那么** 系统必须先进入顶层 planner runtime，再由 runtime 决定调用哪些受支持能力或回退到 legacy 路径

### 需求:系统必须提供基于 LangGraph 的顶层 planner shell
系统必须在 Python kernel 聊天入口前提供一个基于 LangGraph 的顶层 planner runtime，由该 runtime 统一承接聊天请求状态、LLM 或规则 planner 决策、tool 选择、节点调度、失败回退与执行路径选择；禁止将顶层编排继续仅以 `qa.py` 内部隐式分支、单独 skill 入口或 Gateway 路由规则的方式扩张。

#### 场景:聊天请求先进入 planner runtime
- **当** Gateway 转发一条新的聊天请求到 Python kernel
- **那么** 系统必须先进入 LangGraph planner runtime，再由 runtime 决定后续调用受支持 tool、兼容路径或 legacy fallback

### 需求:系统必须优先稳定主聊天问答路径，其他路径允许兼容接入
第一阶段系统必须优先保证 `Local` 主聊天问答路径可以稳定通过 planner runtime 承接；对于 `catalog`、`summary`、`control` 等 Local 内部分支，允许先通过兼容节点、委托现有函数或 passthrough 方式接入；`Web` 与 `Hybrid` 禁止被要求在第一阶段一并迁入 planner runtime。

#### 场景:非主路径先以兼容节点接入
- **当** planner runtime 路由到 `catalog`、`summary` 或 `control` 路径
- **那么** 系统可以先通过兼容节点或 passthrough 调用现有能力实现，只要 runtime 入口、状态对象与回退语义保持统一

#### 场景:Web 与 Hybrid 在第一阶段保持原链路
- **当** 用户以 `web` 或 `hybrid` 模式发起聊天请求
- **那么** 系统必须继续走现有链路，不要求在第一阶段进入 planner runtime

### 需求:系统必须显式区分 Planner、Tool 与确定性 Pipeline 三层职责
系统必须显式区分 `LLM Planner`、`tool 层` 和 `确定性 pipeline / kernel` 的职责边界；Planner 必须负责理解、选择、排序、澄清和停止，tool 层必须负责受约束能力调用，确定性 pipeline 必须负责检索、证据门控、引用绑定、任务状态和可审计落盘；禁止任一层无边界吞并其他两层职责。

#### 场景:planner 仅决定调用关系
- **当** planner 判定一次请求需要先查论文集合再做跨文档总结
- **那么** planner 必须只输出受支持的调用顺序和参数，而不是直接绕过 tool/pipeline 自行生成最终证据化回答

### 需求:系统必须为 Planner runtime 暴露稳定的 tool 调用契约
系统必须为 Planner runtime 暴露稳定的 tool 调用契约，使后续具体能力可以作为 planner 可调用工具接入；该契约必须至少支持结构化输入、结构化结果、失败原因、可观测元数据和依赖前序产物；禁止让 planner 直接耦合某个 kernel 内部函数的私有调用细节。

#### 场景:新能力以 tool contract 接入
- **当** 后续变更把 `catalog_lookup` 或 `paper_assistant` 能力整理为 agent tool
- **那么** planner runtime 必须能够通过统一 tool contract 调用它，而不要求 Gateway 或前端理解该工具的内部实现

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

### 需求:系统必须保留确定性回退到现有 QA 主路径
当 planner runtime 运行失败、状态校验失败、planner 节点不可用、tool contract 不满足或策略判定不应继续 agent 执行时，系统必须回退到现有确定性 QA 主路径或受支持兼容路径，并保持聊天链路可继续返回回答；禁止因 runtime 故障直接让请求中断。

#### 场景:planner runtime 异常时回退 legacy QA
- **当** planner runtime 在规划、路由或 tool 调度阶段抛出异常
- **那么** 系统必须切换到 legacy QA 路径完成本轮请求，并在观测字段中记录回退类型和原因

### 需求:系统必须区分 planner fallback 与 tool/pipeline fallback
系统必须区分 `planner fallback` 与 `tool/pipeline fallback` 两类降级：前者用于规划失败、状态不完整、置信不足或策略禁止继续 agent 执行；后者用于 tool 调用失败、结果为空、证据不足或 citation 不满足；两类回退都必须是受控的，并禁止继续无限步自治重试。

#### 场景:planner 决策失败时降级到 legacy 路径
- **当** planner runtime 无法形成有效的能力选择结果
- **那么** 系统必须记录 `planner fallback` 并降级到受支持的 legacy QA 或确定性路径

#### 场景:tool 结果不满足依赖时停止后续步骤
- **当** 某个 tool 返回空结果或未满足 evidence/citation 前置条件，且后续步骤依赖该结果
- **那么** 系统必须触发 `tool/pipeline fallback`、停止后续依赖步骤，并返回受控失败、澄清或降级答案

### 需求:系统必须区分顶层委托与本地执行
当 planner 输出 `local_execute`、`delegate_web`、`delegate_research_assistant`、`clarify` 或 `legacy_fallback` 时，runtime 必须按该顶层结果执行互斥路径；禁止把联网委托、研究辅助委托和本地 tool 执行混成同一类本地 passthrough。

#### 场景:研究辅助结果走独立委托语义
- **当** planner 返回 `decision_result=delegate_research_assistant`
- **那么** runtime 必须进入研究辅助能力路径，并保持该路径与普通本地 tool 执行在 trace 和 fallback 上可区分

### 需求:系统必须支持受限的多动作计划执行
系统必须支持受限的顺序执行计划，允许的动作仅包括已注册且当前策略允许的 `tool/skill` 条目；对于本地执行路径，计划步数必须有硬上限，且每个后续步骤必须显式声明对前序产物的依赖。对于 `delegate_web`、`delegate_research_assistant`、`clarify` 与 `legacy_fallback`，系统禁止继续展开本地无限步计划。

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
系统必须在运行 trace 中输出 planner runtime、tool 调用与执行链路观测字段，至少包含 `planner_used`、`planner_source`、`decision_result`、`primary_capability`、`knowledge_route`、`research_mode`、`requires_clarification`、`selected_tools_or_skills`、`planner_confidence`、`action_plan`、`selected_path`、`execution_trace`、`short_circuit`、`truncated`、`planner_fallback` 与 `planner_fallback_reason`，并能够区分 planner 级与 tool/pipeline 级降级；当触发回退时必须记录回退原因与停止点。

#### 场景:agent-first 链路可审计
- **当** 系统经由 planner runtime 完成一次单步或多步请求
- **那么** run trace 必须包含 planner 决策、tool 选择、执行轨迹、回退状态与停止原因，且字段可序列化并可用于后续评测

#### 场景:顶层策略与执行结果可共同审计
- **当** 系统经由 planner runtime 完成一次本地执行、联网委托、研究辅助委托或兼容回退
- **那么** run trace 必须同时记录顶层决策结果、执行路径和回退原因
