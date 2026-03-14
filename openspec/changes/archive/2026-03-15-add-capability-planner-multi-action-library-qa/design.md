## 上下文

当前系统以 `app/qa.py` 为中心串联 rewrite、intent routing、检索、sufficiency gate、answer generation 与 evidence gate。该流程对“单轮事实问答”有效，但对以下场景表现不稳定：

- 目录/元数据请求被误送入正文检索与证据门控；
- `waiting_followup` 状态下的新问题会被机械拼接到上一轮澄清问题后；
- 复合查询无法表达“先筛选对象，再对对象做总结/对比”；
- summary 风格问题与 strict fact 问题共用同一 gate，导致过度澄清或错误拒答。

当前仓库已具备几项可复用基础：

- 论文目录元数据与 Library 能力已存在；
- 多轮状态机、`pending_clarify`、`standalone_query` 与 trace 结构已存在；
- 控制意图语义路由已存在，但仍以单一 `intent_type` 为核心输出。

约束：

- 不能引入重型 Agent/Graph 框架；
- 必须保持现有 `run_trace`、session store、已有 QA 主流程的大致外壳；
- 规划失败时必须回退到最小可用路径，不能中断现有聊天链路。

## 目标 / 非目标

**目标：**

- 以单个前置规划节点统一完成换题检测、独立问题生成、主能力判断与复合查询拆解。
- 将请求分流到 `meta_catalog`、`cross_doc_summary`、`fact_qa`、`control` 四条能力线。
- 支持受限的多动作执行计划，并明确步骤依赖、短路与观测字段。
- 为执行链路提供防御机制：低时延、级联失败熔断、结果集硬上限、strict fact 逃逸拦截。
- 收窄 `sufficiency_gate` 与 `evidence_policy_gate` 的适用范围，使其主要服务于 strict fact QA。

**非目标：**

- 不构建通用 Agent 编排器或无限步工具规划。
- 不在本次变更中重写整个 UI 交互流。
- 不替换现有检索、重排、SSE/WS 流式传输协议。
- 不在第一阶段引入新的外部 workflow framework。

## 决策

### 决策 1：统一 Planner 契约先落规则版实现，后续再切到单个 LLM 节点

第一阶段先固定一个统一的 `Resolver + Planner` JSON 契约，并以本地规则规划器实现该契约；后续如需提升表达覆盖率，再切换为单个 `Resolver + Planner` LLM 节点。当前实现仍输出同一组受约束字段：

- `is_new_topic`
- `should_clear_pending_clarify`
- `standalone_query`
- `primary_capability`
- `strictness`
- `action_plan`
- `planner_confidence`

阶段 1 原因：

- 先稳定执行链路、trace 契约与降级行为，再引入模型依赖，风险更低；
- 当前多动作集合有限，规则版足以覆盖首批 `catalog_lookup / cross_doc_summary / fact_qa / control` 路由；
- 保留统一 JSON 契约后，未来接入 LLM planner 时不必重写下游执行器与观测字段。

后续切换到单个 LLM 节点的原因：

- 避免将“换题检测”和“能力规划”拆成两次 LLM 调用，降低时延与解析开销；
- 两项任务共享同一上下文：当前输入、挂起澄清状态、最近主题锚点；
- 能更稳定覆盖表达变体与更复杂的复合查询。

实现备注：

- `planner_use_llm` / `planner_model` 等配置在第一阶段仅作为预留开关，尚未接入实际 planner 调用；
- 当 `planner_use_llm=false` 或 LLM planner 不可用时，系统继续使用规则版 planner，并保持相同 trace 字段与回退语义。

替代方案：

- 分离 `Turn Resolver` 与 `Capability Planner`：更模块化，但会增加一次模型往返与更多失败模式。
- 立即强制切到 LLM planner：表达覆盖更强，但会过早引入模型超时、JSON 解析失败与路由不稳定问题。

### 决策 2：使用受限的 Query Decomposition，而不是 Intent Promotion 或裸意图数组

规划器输出一个有限动作集合上的顺序 `action_plan`，动作仅允许：

- `catalog_lookup`
- `cross_doc_summary`
- `fact_qa`
- `control`

计划最多 3 步，且后续步骤只能消费前序显式产物，例如 `paper_set`。

原因：

- 复合查询需要表达参数与依赖，不是简单的多标签分类；
- 相比 `Intent Promotion`，显式 action plan 更容易审计、短路与做结果集裁剪；
- 相比完整 agent，更符合当前代码结构与风险承受能力。

替代方案：

- `Intent Promotion`：会把目录筛选逻辑隐式塞回 summary/fact 流，重新造成“大一统 QA 入口”。
- 只返回意图数组：不能表达参数、依赖与熔断条件。

### 决策 3：把目录元数据查询升级为 Chat 可复用上游能力

`catalog_lookup` 返回的是 metadata provenance，而不是 chunk citations。其结果可直接回答“库里有哪些论文”，也可作为 `cross_doc_summary`/`fact_qa` 的上游范围输入。

原因：

- 元数据问题的证据源本就不是正文 chunk；
- 目录查询天然支持时间范围、状态、导入顺序等过滤维度；
- 复用已有 Library 目录语义，避免 Chat 侧自己再发明一套“列论文”逻辑。

替代方案：

- 继续从 chunk 检索结果反推论文列表：容易命中 references/front matter，且无法准确反映导入状态与时间。

### 决策 4：为 summary 与 strict fact 使用不同严格度与 gate

规划结果必须包含 `strictness`，值限定为：

- `catalog`
- `summary`
- `strict_fact`

执行规则：

- `catalog`：绕过 `sufficiency_gate` 与 `evidence_policy_gate`
- `summary`：走 `summary_gate`
- `strict_fact`：走现有 `sufficiency_gate + evidence_policy_gate`

原因：

- “对比/总结”与“精确数值/作者/实验设置”有不同正确性标准；
- 现有故障正是因为 summary 与 fact 共用同一严格 gate。

替代方案：

- 保持统一 gate：已被当前问题验证为不可行。

### 决策 5：执行引擎必须具备硬短路与结果集裁剪

顺序执行器在每一步后都验证产物：

- `catalog_lookup` 空结果：立即短路，禁止继续 summary/fact 步骤；
- `catalog_lookup` 超上限结果：按硬上限裁剪，只把 `selected_paper_set` 传入后续步骤；
- `summary` 或 `fact` 步骤若收到空范围输入：必须返回受控失败，不得自由生成。

原因：

- 防止空数组或大数组继续流入下游造成幻觉或上下文爆炸；
- 执行器级防御比仅依赖 planner 更稳健。

替代方案：

- 仅在 planner 里约束：单点失败风险太高，一旦 planner 误判，下游无防线。

### 决策 6：strict fact 逃逸拦截采用“双层判定”

第一层：planner 输出 `strictness`。  
第二层：executor 在执行前基于显式 strict fact 信号做再校验，例如：

- 数值类：准确率、召回率、F1、提升多少、具体数值；
- 元数据类：作者、年份、会议；
- 实验设置类：数据集、benchmark、实验条件。

若命中 strict fact 信号，则禁止流入宽松 `summary_gate`，必须升级为 `fact_qa` 或返回澄清。

原因：

- 避免“对比这 3 篇论文的准确率具体数值”伪装成 summary；
- 让 planner 错误不会直接放大为错误回答。

替代方案：

- 仅在 prompt 中依赖模型自觉区分：风险过高，不满足生产要求。

## 防御机制（Defense in Depth）

### 1. 时延防御

风险：多次前置 LLM 调用会显著拉高首 token 前延迟。

防御：

- 合并 `Turn Resolver` 与 `Capability Planner` 为单节点；
- 使用结构化 JSON schema 与低温度；
- 为 planner 设置独立小模型/短超时；
- 规划器失败时回退到单步本地保守路由，而不是再次调用更多模型。

降级：

- planner 超时或输出无效 JSON 时，回退到：
  - 新话题判定失败则保持当前状态但禁止多步执行；
  - 仅输出单步 `catalog_lookup` 或 `fact_qa` 最小路径。

### 2. 级联失败与熔断

风险：Step 1 失败后 Step 2 继续执行，会把空输入交给 summary/fact 流，诱发幻觉。

防御：

- 执行器为每一步记录 `state`, `produces`, `empty`, `short_circuit_reason`；
- 下游步骤声明依赖，若依赖产物为空则立即短路；
- Response Composer 输出显式短路说明，禁止静默吞掉失败。

降级：

- `catalog_lookup_empty`：返回“未找到符合条件的论文，因此未继续执行后续步骤”；
- `catalog_lookup_not_ready`：若命中论文均未完成处理，则返回“候选论文存在但尚未 ready”，并停止后续 summary。

### 3. 结果集防爆

风险：目录查询命中数百篇论文，导致后续上下文窗口爆炸。

防御：

- 执行器设置硬上限 `max_plan_papers`；
- `catalog_lookup` 输出 `matched_count` 与 `selected_count`；
- 选择规则优先保留：用户显式 limit、最近导入、状态 ready、相关度最高的论文；
- 被裁剪时写入 `truncated=true` 与披露说明。

降级：

- 若命中 500 篇，仅选择 Top-N（例如 20 篇）进入 summary；
- 若用户未给 limit 且 summary 覆盖仍过宽，可先返回“范围过大，请按时间/主题缩小范围”。

### 4. strict fact 逃逸防线

风险：伪装成 summary 的精确问题绕过严格 gate。

防御：

- planner 输出 `strictness`；
- executor 做二次 strict fact 特征检测；
- `strict_fact > summary`，命中后强制改走 `fact_qa`；
- 若 query 同时包含“对比/表格”与精确数值要求，则生成 `catalog_lookup -> fact_qa`，而不是 summary。

降级：

- 当模型无法确定是 summary 还是 strict fact 时，宁可升级为 `strict_fact` 或要求用户明确需要“概括趋势”还是“精确数值”。

## 风险 / 权衡

- [规划节点输出错误 JSON] → 通过 schema 校验、低温度、失败回退到单步保守路由缓解。
- [新 planner 增加模型依赖] → 使用独立小模型、短超时与本地保守回退路径缓解。
- [目录结果裁剪导致遗漏用户真正关心的论文] → 输出 `matched_count/selected_count/truncated` 并优先遵守用户显式 limit。
- [strict fact 规则过强导致本可概括的问题被升级为澄清] → 先采用少量高置信 strict fact 信号，保守上线并通过 trace 迭代。
- [多步执行增加 trace 复杂度] → 复用现有 trace 外壳，仅新增 planner/execution 字段，不重写整套日志协议。

## 迁移计划

1. 在现有 QA 主流程前插入统一 planner 契约，但第一阶段先使用规则版 planner，并保留单步回退逻辑。
2. 先支持 `catalog_lookup` 单步路径与 `catalog_lookup -> cross_doc_summary` 双步路径。
3. 为执行器增加短路、截断与 strictness 二次校验，再接入现有 gate。
4. 待 trace 证明规则版 planner 稳定后，再评估把 `planner_use_llm` 接到真实结构化 LLM planner。
5. 若 planner 线上表现异常，可关闭 planner 开关，退回现有单路 QA。

回滚策略：

- 配置级关闭统一 planner；
- 继续使用现有 `intent_router + rewrite + qa` 主流程；
- 保留新 trace 字段为空或默认值，避免破坏消费者。

## 开放问题

- planner 独立模型优先使用哪条现有 LLM 路由，是否需要专用配置组？
- `summary_gate` 的最小覆盖阈值应按论文数、主题数还是有效证据条数定义？
- `catalog_lookup` 是否需要在第一阶段支持作者/专题/导入时间以外的更多筛选维度？
- 前端是否需要直接展示 action plan 细节，还是仅展示“已按最近 3 篇论文执行对比”等摘要？
