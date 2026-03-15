## ADDED Requirements

### 需求:系统必须让研究辅助入口受 planner policy 显式控制
系统必须要求研究辅助能力仅在 planner policy 输出 `decision_result=delegate_research_assistant` 时进入执行；禁止仅凭前端模式、单独 endpoint 或隐式 prompt 约定直接进入论文助理路径。

#### 场景:未命中研究辅助决策时不进入论文助理
- **当** 用户请求只需要本地严格事实问答或目录查询，且 planner 未输出研究辅助委托
- **那么** 系统必须不进入论文助理能力

## MODIFIED Requirements

### 需求:系统必须将论文助理模式纳入 planner runtime 的统一调度
系统必须将论文助理模式纳入顶层 planner runtime 的统一调度边界；planner 必须基于标准化 policy 输入决定何时进入研究辅助能力、何时先澄清、何时回退到普通事实问答、总结路径或 legacy fallback，并通过 `decision_result`、`research_mode` 与 `selected_tools_or_skills` 明确表达结果；禁止将论文助理模式实现为绕过 planner runtime 的独立旁路入口。

#### 场景:研究辅助请求先经过 planner policy
- **当** 用户提出“帮我比较这些论文并给出下一步研究建议”之类的研究辅助请求
- **那么** 系统必须先由 planner runtime 输出 `delegate_research_assistant` 或其他受控结果，而不是直接跳入某个旁路模式

### 需求:系统必须在证据不足时执行最小澄清
系统必须保持最小澄清策略（一次仅一条澄清问题），且该澄清必须由 planner runtime 统一决定并面向科研任务语义；当研究辅助能力前置条件不满足时，系统必须输出 `decision_result=clarify` 并停止进入论文助理执行路径，禁止绕过 planner 直接进入自由生成回答。

#### 场景:研究辅助前置条件不足时先澄清
- **当** planner runtime 判定用户意图属于研究辅助，但缺少主题、论文范围或实验约束
- **那么** 系统必须输出 1 条面向科研任务语义的澄清问题，并停止研究辅助执行

#### 场景:澄清问题任务语义化
- **当** 系统判定需要澄清
- **那么** `clarify_questions` 必须为 1 条，且内容必须引导用户补充主题、方法或实验约束

## REMOVED Requirements
