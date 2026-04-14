## 新增需求

### 需求:Planner 必须能够查询论文生命周期状态
Planner 必须能够通过数据库访问层查询论文的生命周期状态（`dedup`、`import`、`parse`、`clean`、`index`、`graph_build`、`ready`、`failed`、`rebuild_pending`），以便在规划时准确判断论文可用性。

#### 场景:Planner 筛选 ready 状态的论文
- **当** Planner 需要确定哪些论文可用于检索或问答
- **那么** Planner 必须查询 SQLite 并仅选择状态为 `ready` 的论文

#### 场景:Planner 识别 failed 论文
- **当** Planner 发现某篇论文状态为 `failed`
- **那么** Planner 必须在计划中标记该论文不可用，并可建议用户重试

### 需求:Planner 必须支持基于论文状态的智能路由
Planner 必须能够根据论文生命周期状态进行智能任务路由，如优先处理待重建论文、跳过未就绪论文等。

#### 场景:Planner 优先处理 rebuild_pending 论文
- **当** 用户请求涉及待重建论文
- **那么** Planner 可以建议在执行主任务前先重建这些论文

#### 场景:Planner 识别索引未完成的论文
- **当** 某篇论文状态为 `imported` 或 `parsed` 但尚未 `ready`
- **那么** Planner 必须等待或提示用户该论文暂不可用

### 需求:Planner 必须能够在计划中表达论文级依赖
Planner 必须能够在生成的 action plan 中表达论文级别的依赖关系，如等待某论文索引完成后再执行总结。

#### 场景:Planner 生成带论文依赖的多步计划
- **当** 用户请求需要先确认论文可用再执行总结
- **那么** Planner 必须生成包含论文状态检查依赖的 action plan

### 需求:Planner 必须能够查询论文重建/失败状态
Planner 必须能够查询论文的重建状态（`rebuild_pending`）和失败原因，以支持动态计划调整。

#### 场景:Planner 查询论文失败原因
- **当** 某篇论文状态为 `failed`
- **那么** Planner 必须能够获取失败原因并在计划中体现

#### 场景:Planner 获取待重建论文列表
- **当** 用户请求批量处理待重建论文
- **那么** Planner 必须能够查询所有 `rebuild_pending` 状态的论文

## 修改需求

### 需求:系统必须为 Planner runtime 暴露稳定的 tool 调用契约
系统必须为 Planner runtime 暴露稳定的 tool 调用契约，使后续具体能力可以作为 planner 可调用工具接入；该契约必须至少支持 registry 级 tool 元数据、结构化输入、结构化结果、失败原因、流式支持声明、evidence policy、可观测元数据和依赖前序产物；禁止让 planner 直接耦合某个 kernel 内部函数的私有调用细节。

#### 场景:新能力以 tool contract 接入
- **当** 后续变更把 `catalog_lookup` 或 `paper_assistant` 能力整理为 agent tool
- **那么** planner runtime 必须能够通过统一 tool contract 调用它，而不要求 Gateway 或前端理解该工具的内部实现

#### 场景:runtime 读取 tool 元数据决定执行约束
- **当** 某个已注册 tool 声明 `streaming_mode=final_only` 且 `evidence_policy=citation_forbidden`
- **那么** runtime 必须按该元数据约束执行与结果组装，而不是由 planner 或 gateway 临时猜测

### 需求:系统必须支持受限的多动作计划执行
系统必须支持受限的顺序执行计划，允许的动作仅包括已注册且当前策略允许的 `tool/skill` 条目；对于本地执行路径，计划步数必须有硬上限，且每个后续步骤必须显式声明对前序产物的依赖。对于 `delegate_web`、`delegate_research_assistant`、`clarify` 与 `controlled_terminate`，系统禁止继续展开本地无限步计划。

#### 场景:复合查询拆解为两步执行
- **当** 规划结果包含 `catalog_lookup -> cross_doc_summary`
- **那么** 系统必须先生成 `paper_set`，再以该集合为输入执行总结步骤

#### 场景:本地执行路径保持有限步
- **当** 规划结果为 `decision_result=local_execute` 且 `action_plan` 包含 `catalog_lookup -> cross_doc_summary`
- **那么** 系统必须按声明依赖顺序执行有限步计划，并在达到步数上限或依赖失败时停止

### 需求:系统必须在上游结果为空时短路后续步骤
当某一步产物为空且被后续步骤依赖时，执行器必须短路并返回受控失败结果；禁止将空集合继续传入 summary、paper assistant 或 fact QA 流程。

#### 场景:目录查询为空时终止后续对比
- **当** `catalog_lookup` 未找到符合条件的论文且后续存在 `cross_doc_summary`
- **那么** 系统必须停止执行后续步骤，并明确返回"未找到符合条件的论文，因此未继续执行后续步骤"

### 需求:系统必须对计划输入集合施加硬上限与截断披露
系统必须对由 `catalog_lookup` 产生并传入后续步骤的论文集合施加硬上限，输出至少 `matched_count`、`selected_count` 与 `truncated` 等字段；禁止将未经裁剪的大结果集直接送入后续总结或问答步骤。

#### 场景:大结果集被裁剪并披露
- **当** `catalog_lookup` 命中 500 篇论文而执行器上限为 20
- **那么** 系统必须仅将 20 篇论文传入后续步骤，并在结果中披露总命中数、选中数与截断事实
