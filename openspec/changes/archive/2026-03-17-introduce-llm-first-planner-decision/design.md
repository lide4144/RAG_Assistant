## 上下文

当前仓库已经具备 agent-first 迁移的关键底座：

- `app/planner_runtime.py` 已经提供顶层 planner runtime、tool registry、runtime fallback 和 execution trace；
- `gateway/src/adapters/pythonKernelClient.ts` 已让 `Local` 模式优先进入 `/planner/qa*`，并保留 legacy `/qa*` 兼容回退；
- 前端聊天壳层已经预留 `planning`、`toolSelection`、`toolRunning`、`toolResult` 与 `fallback` 事件类型；
- `llm-planner-tool-selection-policy`、`capability-planner-execution`、`kernel-agent-tools` 与 `paper-assistant-mode` 已固定顶层 planner、tool contract 和 deterministic kernel 的基本边界。

但当前顶层语义理解仍以规则主导：

- `app/capability_planner.py` 通过词表、启发式规则和固定模板决定 `strict_fact`、`summary`、`delegate_web`、`paper_assistant`、`clarify` 等顶层决策；
- `app/qa.py` 仍保留大量面向用户的交互策略判断，例如最小澄清、连续澄清上限后强制低置信回答、助理模式下优先澄清而非拒答、控制意图锚点缺失时强制澄清等。

这形成了双重语义中心：planner runtime 在顶部做一次决策，`qa.py` 又在后面重新决定用户最终看到的是 `answer`、`clarify` 还是 `refuse`。这种分裂会让系统在多轮追问、助理型模糊需求、总结与严格事实混合请求上显得僵硬，直接损害“像智能系统”的体验。

本次变更的设计目标不是立刻重写底层 pipeline，而是把“谁负责理解用户、谁负责决定交互姿态、谁负责判定是否可安全输出”三个问题重新划边界，并提供一条可灰度、可回滚的迁移路径。

约束：

- 必须复用现有 `frontend -> gateway -> python kernel` 主链路；
- 必须保持 `message / sources / messageEnd / error` 主协议兼容；
- 不重写 retrieval、evidence gate、citation contract、artifact 依赖与 task state；
- LLM planner 必须输出可被现有 runtime 接受的结构化 decision，而不是引入全新不兼容协议；
- 迁移必须支持 shadow mode，避免一次性切换顶层决策来源。

利益相关者：

- 终端用户：需要更自然的多轮理解、澄清和研究辅助体验；
- Python kernel 维护者：需要可验证、可回退的 planner 接入方式；
- Gateway / Frontend 维护者：需要稳定事件语义与兼容闭环；
- 评测与运维：需要能够比较 rule planner 与 LLM planner 的差异，并判定何时可灰度。

## 目标 / 非目标

**目标：**

- 定义与当前 runtime 兼容的最小 `LLM planner decision schema`，使 LLM 可替换现有 rule planner 成为顶层语义理解主入口。
- 定义 runtime 侧 `planner decision validation` 分层校验，确保 LLM 只能提出候选决策，正式决策仍由 runtime 接受。
- 定义 `shadow mode` 对比机制，使 rule planner 与 LLM planner 能在同一请求上并行决策、差异记录和人工评审。
- 调整职责边界：将“是否澄清、何时部分回答、助理模式交互姿态”等面向用户的策略逐步上移到 planner / policy 层；保留 evidence gate、citation、tool registry、artifact 依赖、task state 和 trace 在 deterministic kernel/runtime。
- 定义渐进式迁移顺序，使系统可以先灰度总结与研究辅助类请求，再考虑严格事实路径。

**非目标：**

- 不在本变更中重写底层 retrieval、rewrite、rerank、sufficiency 或 evidence gate 实现。
- 不在本变更中引入新的前端 UI 外观或新的独立聊天协议。
- 不在本变更中要求 Web / Hybrid 立即与 Local 共用同一 planner 执行器实现。
- 不在本变更中一次性删除现有 rule planner；它在 shadow、fallback 与过渡阶段仍保留。
- 不让 LLM 直接生成底层 `tool_calls`、`tool_results`、`sources`、`artifacts` 或 runtime trace。

## 决策

### 决策 1：采用“LLM 产出候选 decision，runtime 接受正式 decision”的双层模型

LLM planner 的职责是产出结构化 `planner decision`，其字段与当前 `PlannerResult` / runtime contract 兼容。runtime 在接收该结果后必须先通过 validation gate，只有通过验证的 decision 才能进入工具准备、路由和执行。

这意味着：

- LLM 负责语义理解、上下文延续判断、顶层能力选择、是否澄清和有限步 `action_plan`；
- runtime 负责决定这份 decision 是否结构合法、语义自洽、工具已注册、依赖满足且策略允许；
- deterministic kernel 继续负责 evidence gate、citation、任务状态、source provenance 和最终输出合法性。

原因：

- 当前系统已经有稳定的 runtime 骨架，最小成本方案是替换 planner source，而不是重建执行器；
- 如果让 LLM 直接产出正式 runtime envelope，会重新模糊 planner / runtime / kernel 边界；
- “候选 decision” 模型天然支持 shadow、fallback 和灰度。

替代方案：

- 让 LLM 直接输出最终 route / tool envelope：实现快，但边界不稳，且难以审计。
- 继续让 rule planner 作为主决策、LLM 只做补充：无法真正解决顶层僵硬体验。

### 决策 2：LLM planner 采用最小兼容 schema，而不是引入新协议

LLM planner 的最小输出将复用现有顶层 decision 字段，包括：

- `decision_version`
- `planner_source`
- `planner_used`
- `planner_confidence`
- `user_goal`
- `standalone_query`
- `is_new_topic`
- `should_clear_pending_clarify`
- `relation_to_previous`
- `primary_capability`
- `strictness`
- `decision_result`
- `knowledge_route`
- `research_mode`
- `requires_clarification`
- `clarify_question`
- `selected_tools_or_skills`
- `action_plan`
- `fallback`

其中 `action_plan` 继续只表达 planner 级步骤，如 `action / query / produces / depends_on / params`，由 runtime 负责正规化为 tool call envelope。

原因：

- 当前 runtime、gateway trace 与前端事件已经依赖这组字段的语义；
- 使用兼容 schema 可以让 LLM planner 先在 shadow 模式接入，而不必同时改 gateway 和 frontend；
- 这能把风险集中在“决策替换”，而不是“协议替换”。

替代方案：

- 为 LLM planner 单独设计一套 richer schema：表达力更强，但会扩大迁移面。

### 决策 3：planner decision validation 分为四层，并以 reject/fallback 为主，不做隐式脑补修正

runtime 将对 LLM planner 输出做四层校验：

1. 结构合法
   - JSON 可解析、字段存在、类型正确、枚举合法、置信度范围合法；
2. 语义合法
   - `decision_result` 与 `action_plan` 一致；
   - `requires_clarification` 与 `clarify_question` 一致；
   - `primary_capability`、`strictness`、`selected_tools_or_skills` 不出现明显自相矛盾；
3. 执行合法
   - `action_plan` 中的 action 必须存在于 registry；
   - 步数必须在 runtime 上限内；
   - `depends_on` 必须可由前序产物满足；
   - 参数必须通过能力 schema / policy 校验；
4. 策略合法
   - `delegate_web`、`delegate_research_assistant` 等结果必须受当前 policy flags 控制；
   - 不允许 planner 通过 decision 绕过 clarify 前置条件或证据策略边界。

校验结果只允许三态：

- `accept`
- `accept_with_warnings`
- `reject`

`reject` 时优先回退到 rule planner，再回退到 legacy fallback。runtime 不应在 LLM decision 缺字段或自相矛盾时偷偷补默认值，因为那会掩盖 planner 真实失稳原因。

原因：

- 迁移期最重要的是可观测失败，而不是“尽量修到能跑”；
- 结构修补看似友好，实际会让 shadow 评估失真；
- reject + fallback 模型更适合后续统计问题类型并调优 planner。

替代方案：

- 大量默认填充与自动修正：短期成功率更高，但长期难以判断 LLM 质量。

### 决策 4：先引入 shadow mode，再做灰度切换；切换顺序按体验收益优先而不是风险最低优先

系统将支持三阶段 planner source 模式：

1. `rule_only`
   - 仅使用现有 rule planner；
2. `shadow_compare`
   - rule planner 仍执行，LLM planner 并行输出 decision 并记录差异；
3. `llm_primary_with_rule_fallback`
   - 优先使用通过 validation 的 LLM decision，失败时回退到 rule planner。

shadow trace 至少记录：

- 原始请求与会话信息；
- rule decision；
- LLM decision；
- validation 结果；
- 字段级 diff；
- 实际执行的 planner source；
- 人工评审标签位。

灰度切换顺序：

- 先灰度 `summary / paper_assistant` 类请求；
- 再灰度 `catalog + summary` 复合请求；
- 最后再考虑 `strict_fact` 路径。

原因：

- 用户最强烈感知的问题集中在模糊、多轮、总结、助理型场景；
- 严格事实路径对证据与错误容忍度最低，适合最后切换；
- shadow mode 是决定“LLM 是否更好且不更危险”的必要前置。

替代方案：

- 全量切换：回滚成本高，且无法区分问题来自 planner 还是执行层。
- 只做离线样本对比：无法暴露真实会话上下文与多轮影响。

### 决策 5：将 `qa.py` 中的“交互姿态决定”上移为 planner / policy 输出，而不是直接保留在 QA 尾部

迁移期需要把 `qa.py` 中面向用户体验的策略逻辑改造成“约束信号输出”，而不是继续在底层直接定夺用户最终看到什么。

上移目标包括：

- 是否需要澄清；
- 澄清问题的内容；
- 助理模式下“先澄清 / 先给低置信摘要 / 拒答”的优先级；
- 连续澄清达到上限后的回应姿态；
- 控制意图锚点缺失时的用户表达。

保留在 kernel/runtime 的包括：

- evidence gate 是否触发；
- citation 是否可映射；
- artifact dependency 是否满足；
- task state 与 trace；
- source provenance 合法性。

实现上的职责变化是：

- kernel 返回 `insufficient_evidence`、`missing_prerequisites`、`citation_incomplete` 等约束信号；
- planner / policy 决定在这些约束下是 `clarify`、`partial answer` 还是 `refuse`；
- runtime 记录该决策来自 planner、tool fallback 还是 deterministic safety gate。

原因：

- 当前最强烈的割裂感来自 planner 和 `qa.py` 都在做“面向用户的理解与姿态”；
- 如果只替换顶层 planner，不收缩 `qa.py` 语义中心，用户仍会感知系统人格分裂。

替代方案：

- 保留 `qa.py` 交互策略不动，只替换 planner：工程量更小，但体验收益有限。

### 决策 6：Gateway 与 Frontend 继续保持协议兼容，但要为 shadow/迁移阶段提供最小可观测性

Gateway 不承接 planner 语义，只负责：

- 转发 LLM planner 相关高层事件；
- 保留现有 `message / sources / messageEnd / error` 闭环；
- 在 shadow 模式下不向终端用户暴露内部对比细节，但允许在 trace / debug 视图中读取。

Frontend 需要保持：

- 当前标准聊天行为不被阻断；
- 规划、tool、fallback 高层事件仍可显示；
- 后续若增加 shadow/debug 视图，也只消费稳定高层字段，不依赖私有内部 trace。

原因：

- 当前前后端协议已经具备足够的增强槽位，不需要在本变更中再造一套 agent UI；
- 保持“旧协议可工作，新事件可渐进增强”是最稳的迁移方式。

替代方案：

- 先改前端协议再接 LLM planner：会显著扩大变更面。

## 风险 / 权衡

- [LLM planner 在早期会输出结构错误或语义冲突] → 用 validation gate 分类 reject reason，并保留 rule planner fallback。
- [只替换 planner 但不收缩 `qa.py` 语义逻辑，用户仍感觉系统不统一] → 将交互姿态逻辑显式列入变更范围，并在 specs 中要求 planner / policy 成为唯一真相源。
- [shadow 模式记录大量 diff，但缺少人工评审标准] → 设计中要求至少记录字段级差异，并为高风险样本预留 `rule_better / llm_better / tie / both_bad` 的人工评审标签。
- [LLM planner 在 summary 类请求上更像人，但在 strict fact 类请求上更容易放飞] → 规定灰度顺序先 summary / assistant，后 strict fact。
- [validation 如果过度“自动修正”，会掩盖 planner 真实质量] → 采用 reject/fallback 优先，不做隐式脑补。
- [runtime 增加一层 validation 与 shadow 记录，会提升复杂度] → 复用现有 runtime contract 和 trace 字段，避免重复造执行器。

## 迁移计划

1. 在 OpenSpec 层更新 planner/runtime、policy、paper assistant、gateway/front-end 相关 specs，先固定职责边界与最小 schema。
2. 在实现阶段引入 LLM planner 输出 schema 与 validation gate，但默认仍运行 `rule_only`。
3. 增加 `shadow_compare` 模式：同一请求同时产出 rule decision 与 LLM decision，记录 validation 结果和字段级 diff，不影响用户主回答。
4. 按高价值场景组织人工评审样本，优先审多轮追问、summary vs strict fact、paper assistant、control anchor 等分歧样本。
5. 当 LLM planner 在结构稳定性、体验优势和安全门槛上达标后，切到 `llm_primary_with_rule_fallback`。
6. 先灰度总结与研究辅助路径，再灰度 catalog+summary 复合路径，最后再评估 strict fact 路径。
7. 在后续实现中将 `qa.py` 中的交互姿态逻辑逐步改为约束信号输出，并将最终用户姿态统一收回到 planner / policy 层。

回滚策略：

- 若 LLM planner 在任意阶段产生高 reject 率、高 runtime fallback 率或体验明显退化，可立即切回 `rule_only`；
- 因为底层 deterministic kernel、gateway 主协议和 legacy fallback 均保留，回滚不需要恢复底层数据或协议迁移；
- shadow mode 可以继续保留，用于问题追踪而不影响用户主链路。

## 开放问题

- LLM planner 的最小 schema 是否需要单独版本化文件或共享 schema 定义，以便 Python runtime、测试和评测共同引用？
- `paper_assistant` 的连续澄清上限后强制低置信回答，最终应由 planner/policy 独立决定，还是保留部分 kernel 默认行为作为兜底？
- shadow mode 的人工评审产物应记录在 run trace、单独评测文件，还是两者同时保留？
- Local 之外的 Web / Hybrid 路径是否在后续阶段也接入同一份 LLM planner decision，还是长期保持 gateway 原生编排？
