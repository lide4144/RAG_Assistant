## ADDED Requirements

### 需求:系统必须将论文助理能力注册为 planner 可调用 tool
系统必须将论文助理能力作为已注册的 `paper_assistant` tool 或兼容的研究辅助 tool family 暴露给 planner runtime，并声明其输入、前置条件、输出结构、失败类型、流式支持与 evidence policy；禁止继续把论文助理仅作为隐式模式开关或旁路 prompt 约定存在。

#### 场景:planner 通过注册 tool 调用论文助理
- **当** planner runtime 判定当前请求适合进入研究辅助能力
- **那么** 执行层必须以已注册 `paper_assistant` tool 的契约发起调用，而不是跳过 tool 层直接进入旁路模式

### 需求:系统必须将论文助理建议类输出标记为 explanatory provenance
系统必须将论文助理中的下一步建议、研究方向提示、追问建议等建议型内容标记为 `explanatory provenance`，并与事实性结论来源区分；禁止将纯建议段落伪装为 chunk 级 citation 事实。

#### 场景:建议段落不冒充正文引用
- **当** 论文助理输出“下一步可以比较实验设置差异”之类的建议内容
- **那么** 该段内容必须作为 explanatory provenance 处理，而不是被渲染为正文事实 citation

## MODIFIED Requirements

### 需求:系统必须将论文助理模式纳入 planner runtime 的统一调度
系统必须将论文助理模式纳入顶层 planner runtime 的统一调度边界；planner 必须基于标准化 policy 输入决定何时进入研究辅助能力、何时先澄清、何时回退到普通事实问答、总结路径或 legacy fallback，并通过 `decision_result`、`research_mode` 与 `selected_tools_or_skills` 明确表达结果；当进入执行阶段时，系统必须通过已注册的 research assistant tool contract 发起调用，禁止将论文助理模式实现为绕过 planner runtime 和 tool registry 的独立旁路入口。

#### 场景:研究辅助请求先经过 planner 决策
- **当** 用户提出“帮我比较这些论文并给出下一步研究建议”之类的研究辅助请求
- **那么** 系统必须先由 planner runtime 判断是否进入论文助理能力，而不是直接跳入某个旁路模式

#### 场景:研究辅助请求先经过 planner policy
- **当** 用户提出“帮我比较这些论文并给出下一步研究建议”之类的研究辅助请求
- **那么** 系统必须先由 planner runtime 输出 `delegate_research_assistant` 或其他受控结果，而不是直接跳入某个旁路模式

#### 场景:论文助理通过 tool contract 执行
- **当** planner 已选择研究辅助路径
- **那么** runtime 必须通过已注册 `paper_assistant` tool 的输入输出契约执行，而不是直接调用未声明 contract 的私有实现

### 需求:系统必须保证论文助理输出仍受 kernel 安全边界约束
即使 planner 选择了论文助理能力，系统仍必须通过 kernel 的 evidence gate、citation contract 与任务状态约束生成最终输出；论文助理 tool 必须显式声明其 evidence policy，并将事实性结论与建议性内容区分为不同 provenance 类型；禁止将研究辅助模式视为可以放宽证据约束或跳过可追溯性的特例。

#### 场景:论文助理回答仍需可追溯证据
- **当** planner runtime 选择论文助理能力生成主题总结、差异比较或后续建议
- **那么** 最终回答必须仍然带有可追溯证据与引用，而不是仅输出无法审计的自由生成结论

#### 场景:建议内容与事实结论分开约束
- **当** 论文助理同时输出事实总结和下一步建议
- **那么** 系统必须对事实总结保留 citation 约束，并将建议内容标记为 explanatory provenance

## REMOVED Requirements
