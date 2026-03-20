## 上下文

当前系统已经具备顶层 planner runtime、结构化 planner decision、tool registry 契约、validation gate 和交互姿态裁判边界，但主执行语义仍残留大量“LLM 可参与、规则可兜底”的迁移期假设。现有规范中仍明确保留 `rule_only`、`shadow_compare`、`llm_primary_with_rule_fallback` 等模式，以及 validation reject 后优先切回 rule planner 的路径；而这次变更的前提已经改变：旧规则控制无法达到最低要求，因此不能继续作为正式决策来源。

这意味着本次设计不是单纯“提高 LLM 权重”，而是要把 planner runtime、decision validation、interaction authority 和 tool execution 一起收敛到一个更严格的运行时模型：LLM planner 是唯一正式的顶层对话解释器；validation、registry 和 kernel guardrails 负责约束它；旧规则链不再参与本轮正式决策，只允许保留为离线评估、历史兼容读取或诊断参考。

受影响的主要利益相关方包括 Python kernel 聊天入口、planner runtime、tool registry、deterministic pipeline、trace/observability 与后续要编写的 capability specs。

## 目标 / 非目标

**目标：**
- 将顶层 planner runtime 收敛为 LLM-first 单一主决策架构，移除 rule planner 作为正式执行来源。
- 让多轮关系判断、能力选择、顶层路径选择和最终交互姿态统一由 LLM planner decision 驱动。
- 保留并强化 validation gate、tool registry、kernel constraints envelope、evidence/citation guardrails 作为硬约束，而不是回到旧规则兜底。
- 为失败情况定义新的受控收束语义：validation reject、tool failure、constraint violation、planner runtime exception 都必须产生可审计且有限的结束路径。
- 为后续 specs 修改提供清晰的设计锚点，避免不同 capability 各自引入新的 fallback 解释。

**非目标：**
- 不在本次设计中要求 Web 或 Hybrid 路径同时迁入新的 LLM-first planner runtime。
- 不在本次设计中完成所有 query tools 和 task tools 的产品化落地；本次只定义顶层决策与受约束执行框架。
- 不把 deterministic backend、evidence gate 或 citation contract 替换为纯 LLM 生成逻辑。
- 不保留 rule planner 作为线上常规回退执行路径。

## 决策

### 决策 1：LLM planner 成为唯一正式主决策来源
运行时仅接受经过 validation gate 的 LLM planner decision 进入正式执行链。旧 rule planner 不再作为线上决策源，不再参与“本轮是否执行、澄清、委托、拒答”的最终路径选择。

选择原因：现有规则控制已无法达到最低要求，继续保留它作为正式 fallback 只会让系统维持双真相源，并延续“LLM 决策被旧规则尾部改写”的结构性问题。

备选方案：
- `llm_primary_with_rule_fallback`：迁移风险更低，但会保留双决策真相源，与 proposal 冲突。
- `rule_only + shadow_compare`：便于保守灰度，但无法实现本次变更目标。

### 决策 2：validation gate 只负责准入，不负责把决策改写成旧规则结果
validation gate 继续执行结构、语义、执行和策略四层校验，但其职责限定为 `accept`、`accept_with_warnings`、`reject` 与稳定 reason code 记录。若 decision 被拒绝，运行时必须进入受控失败收束语义，而不是切回 rule planner 产出另一份正式 decision。

选择原因：validation 的作用是限制 LLM 的可执行边界，而不是偷偷恢复旧规划器。把 reject 直接映射到规则回退，会重新引入不可审计的双轨执行模型。

备选方案：
- validation reject 后切 rule planner：兼容性更强，但与“旧规则无法满足最低要求”的约束冲突。
- validation 失败后自动补全字段重试：实现简单，但会模糊 rejection 语义并降低可审计性。

### 决策 3：失败统一收束为受控结束路径，而不是旧规则兜底
本次设计把失败分为三类：
- `planner_reject`：LLM decision 未通过 validation，直接进入受控澄清、拒答或显式系统失败响应。
- `tool_or_constraint_failure`：已批准 decision 在执行中命中空结果、依赖缺失、证据不足、citation 不满足等约束，由 planner 根据 constraints envelope 决定澄清、部分回答或拒答。
- `runtime_exception`：planner runtime 或节点级异常，进入显式可审计的最小失败路径，不调用旧 rule planner 补救。

选择原因：只有把失败语义显式化，才能在没有 rule fallback 的前提下保持系统可解释、可观测、可调试。

备选方案：
- 统一降级到 legacy QA：表面连续，但会绕回旧规则/旧链路并污染交互真相源。
- 无法执行时直接 500：实现最简单，但不符合受控系统目标。

### 决策 4：保留 deterministic backend 与硬护栏，严格禁止 planner 越权
LLM planner 只负责“理解、选择、排序、澄清、停止”；tool 层负责注册解析和结构化调用；deterministic pipeline 继续负责检索、证据门控、citation、任务状态、硬上限与审计落盘。planner 不允许直接调用 kernel 私有函数，也不允许绕过 evidence gate 或 citation contract 直接生成可见结果。

选择原因：你要的是 LLM-first planner，不是开放式自治 agent。必须把“决定做什么”和“如何稳定执行”分层固定下来。

备选方案：
- 让 planner 直接生成最终答案并只做轻校验：实现快，但会破坏证据和引用边界。
- 把更多判断继续塞回 kernel/QA：能复用现有代码，但会重新稀释 planner authority。

### 决策 5：旧 rule planner 仅保留为离线对比与诊断资产
现有 rule planner 代码和历史决策逻辑不立即物理删除，但退出线上正式执行链。它只允许用于离线评测、回放分析、样本对比或开发期诊断，不得影响用户本轮正式回答。

选择原因：这样既不把它继续当成合格 fallback，又保留必要的迁移观察和历史资产利用空间。

备选方案：
- 立即彻底删除 rule planner：边界最清晰，但会削弱迁移期分析能力。
- 继续 shadow_compare 在线并列输出：可观测性高，但需要非常谨慎地保证其绝不影响主链。

## 风险 / 权衡

- [validation reject 率可能较高] → 先把 reject reason code、样本采集和 trace 做完整，再针对高频失败模式优化 prompt、schema 和 registry。
- [去掉 rule fallback 后，早期失败会更直接暴露给用户] → 明确最小失败路径文案和姿态语义，优先收敛到“可解释的澄清/拒答”，而不是无结构错误。
- [现有规范之间存在明显冲突] → 后续 specs 必须优先修改 `capability-planner-execution`、`llm-planner-tool-selection-policy`、`llm-planner-decision-validation`，消除 rule fallback 相关条款。
- [部分历史链路仍隐式依赖 legacy QA 或尾部规则] → 在实现前增加运行 trace 检查点，定位任何仍会改写 `final_user_visible_posture` 的组件。
- [LLM 作为唯一正式决策源会提高 prompt 和 schema 设计压力] → 通过更严格的 decision schema、tool registry 元数据和 validation 分层来降低自由度，而不是重新引入规则兜底。

## Migration Plan

1. 先修改相关 capability specs，把所有“rule planner 正式回退”语义替换为“validation reject / controlled termination / offline comparison only”。
2. 收敛 planner runtime 配置，移除 `rule_only` 与 `llm_primary_with_rule_fallback` 的线上正式模式，只保留 LLM-first 正式模式；如保留 shadow，对其做明确的非主链隔离。
3. 调整 validation gate 输出和 runtime 分支，使 reject 不再调用 rule planner，而是进入受控失败路径。
4. 在聊天主链增加 trace 校验，确认最终交互姿态只来自 planner/policy，且无 legacy tail override。
5. 最后再按新的 specs 拆 tasks 和实现，逐步替换旧规则链的残余依赖。

## Open Questions

- validation reject 后的最小用户可见结束路径是否统一为 `clarify/refuse/system_failure` 三类，还是还需要保留单独的 `legacy_fallback` 枚举但改写其含义？
- `shadow_compare` 是否继续保留在线记录模式，还是完全转为离线回放工具，以避免任何“影子规则链”被误接入正式执行？
- 对于 planner runtime 异常，是否允许走“受支持兼容路径”，如果允许，这条兼容路径是否仍会触发旧 QA 尾部姿态改写，需要单独再收口？
