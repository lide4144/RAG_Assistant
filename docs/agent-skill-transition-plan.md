# Agent/Skill 混合架构转型计划

> 状态说明：这份文档对应的是较早的“保守 Planner/Skill 渐进式路线”。
> 当前主路线已切换到 agent-first 版本，请优先参考 [docs/agent-first-transition-plan.md](/home/programer/RAG_GPTV1.0/docs/agent-first-transition-plan.md)。
> 除 `introduce-langgraph-planner-shell` 外，本文中的旧变更定义不应再直接作为主线推进依据。

## 这份文档是干什么的

这不是实现方案，也不是开发任务清单，而是一份面向当前系统演进方向的规划文档。

目标是回答三个问题：

1. 为什么不建议把现有系统整体替换成纯 Agent 系统
2. 如果要演进，什么样的混合架构更适合当前项目
3. 前端、网关、内核分别要怎样变化，才能平滑过渡

## 一句话结论

建议采用“Planner/Skill 在上，确定性 Pipeline 在下”的混合架构。

不要把现有系统整体改造成“完全由大模型自由调工具完成所有流程”的系统。

更合理的方向是：

- 让大模型负责理解问题、补全上下文、选择技能、决定调用顺序
- 让现有内核继续负责导入、索引、检索、建图、证据绑定、引用输出、任务状态等确定性执行

基于当前仓库形态，更推荐：

- 以 `LangGraph` 作为顶层 Planner/Skill 编排框架
- 保留现有 `frontend + gateway + python kernel` 主干
- 前端协议先延续现有事件流，只吸收 `Vercel AI SDK` 的交互思路，不直接整体迁移

不推荐当前阶段直接以 `Dify` 或 `FastGPT` 替换现有主底座。

## 当前系统现状

当前系统本质上是一个本地研究助手工作台，主要由三层组成：

- `frontend`：聊天、Pipeline、设置、结果展示
- `gateway`：前后端协议与流式/任务编排
- `python kernel`：导入、索引、检索、问答、图构建、运行配置

它的优点是：

- 流程比较稳定
- 每一层职责相对清楚
- 任务状态和产物可追踪
- 有证据门控和引用约束

它的问题是：

- 多轮代词和省略问题理解较弱
- 对复杂研究任务的灵活编排不够
- 某些“应该先读上下文再选工具”的场景处理不自然

## 为什么不建议直接全面 Agent 化

如果直接变成“LLM + 一堆 Skill + 自由调用”，会带来几个风险：

- 行为不可预测，同一个问题可能每次走不同路径
- 证据链容易断，回答更难稳定绑定到 chunk
- 前端和网关协议会快速复杂化
- 调试难度上升，很难快速知道是哪个阶段出了问题
- 导入、建图、索引等工程任务不适合交给 Agent 自由发挥

换句话说，当前系统的问题更像“上层理解和编排不够聪明”，而不是“底层流程应该被取消”。

## 目标架构

建议目标架构如下：

```text
用户请求
  ↓
Planner
  ↓
Skill 选择 / 调度
  ↓
稳定能力接口
  ↓
现有 Kernel Pipeline
  ↓
证据门控 / 引用 / 任务状态
  ↓
前端展示
```

其中：

- `Planner` 负责理解用户真实意图
- `Skill` 负责完成相对开放的认知任务
- `Kernel Pipeline` 负责完成确定性执行

## 推荐采用的外部方案

### 最适合当前系统的技术组合

#### 1. LangGraph

适合原因：

- 适合在不推翻现有 Python 内核的前提下增加有状态编排
- 能把“多轮上下文理解、Skill 选择、工具路由”放在顶层图中
- 不强迫你改写底层 RAG、任务、图构建逻辑

建议定位：

- 只负责 Planner/Skill 层
- 不接管导入、索引、任务、引用等底层确定性逻辑

#### 2. Vercel AI SDK

适合原因：

- 它代表了目前前端多状态流式交互的较成熟范式
- 可以为未来的聊天事件、工具事件、推理状态提示提供参考

建议定位：

- 先参考交互协议和数据流设计
- 不在当前阶段强制整体替换现有 WebSocket 聊天架构

### 当前阶段不建议作为主底座的方案

#### Dify / FastGPT

不推荐原因：

- 更适合从零快速搭应用，不适合接管现有深度定制系统
- 你们已经有前端、网关、内核和任务体系，直接换平台相当于换底盘

建议定位：

- 可以作为产品或流程参考
- 不建议作为当前主线重构方案

#### LlamaIndex Workflows

不作为首选原因：

- 它适合文档/RAG 驱动场景，但你当前更缺的是“上层编排”，不是“重建 RAG 生态”
- 如果后续要顺便重整索引、检索、文档解析生态，再考虑它会更合理

建议定位：

- 作为备选参考
- 当前优先级低于 LangGraph

## 推荐的第一批 Skill

建议先从“高价值、低破坏性”的 Skill 开始。

### 1. 指代消解 Skill

作用：

- 把“他们”“上面那篇”“这些论文”之类的表达，还原成具体论文、作者或对象列表

为什么先做：

- 这是多轮对话中最影响体验的问题之一
- 它主要改善理解层，不会破坏底层流程

### 2. 问题分类 Skill

作用：

- 判断当前问题是事实问答、标题翻译、论文对比、开放式分析、任务操作，还是需要澄清

为什么先做：

- 这决定后面该走哪条路径

### 3. 工具路由 Skill

作用：

- 决定当前轮应该调用本地检索、联网补充、论文列表读取、标题翻译、比较总结等哪类能力

为什么先做：

- 它能提升系统灵活性，但不替代现有核心能力

### 4. 标题/术语中文化 Skill

作用：

- 面向论文标题、方法名、术语名，输出自然、可解释的中文译名或常见中文说法

为什么先做：

- 这是用户可直接感知的增益
- 风险比“生成事实结论”更低

### 5. 研究辅助 Skill

作用：

- 生成对比摘要、创新点提炼、后续追问建议、灵感卡片草稿

为什么先做：

- 它符合当前产品的研究助手定位

## 不建议 Agent 化的能力

以下能力建议继续保持确定性执行，不要直接改造成自由 Skill：

- PDF 导入
- Chunk 清洗
- 索引构建
- 图构建
- 文件写盘
- 任务状态维护
- 证据绑定
- 引用生成
- 失败恢复和重试逻辑

原因很简单：这些更像工程流水线，不像认知任务。

## 推荐演进阶段

### 阶段 0：先加一层 Planner，不改底层主链路

目标：

- 保持现有 `frontend -> gateway -> kernel` 主干不变
- 在聊天请求进入核心 QA 之前，先做一次“理解和路由”

此阶段不追求“自主 Agent”，只追求“更聪明的入口判断”。

### 阶段 1：把第一批 Skill 接入聊天链路

目标：

- 先解决多轮指代、问题类型识别、工具选择、标题中文化这类问题
- 让模型学会在回答前做轻量判断，而不是直接检索

此阶段核心不是更多工具，而是更好的问题预处理。

### 阶段 2：引入轻量 Planner + Tool Call 记录

目标：

- 让系统能记录“这轮调用了哪些 Skill、为什么调用”
- 但仍然保持流程有限、可观察、可回放

不要一开始就做复杂多步 Agent 反思循环。

### 阶段 3：把开放式研究任务做成组合 Skill

目标：

- 比如“比较这几篇论文”“给我提炼方向”“生成灵感卡片”
- 这类任务适合多个 Skill 串联

但依旧建议保持有限编排，而不是完全开放式自治。

## 适合拆分为 OpenSpec 的多变更路线

为了避免一次性开启一个过大的“agent 化重构”变更，建议把这条路线拆成多个小而清晰的 OpenSpec 变更。

推荐原则：

- 每个变更只解决一类边界问题
- 先改“理解层”，再改“协议层”，最后改“体验层”
- 不把 LangGraph 接入、Skill 定义、前端适配、观测增强混成一个超大变更

下面给出建议的拆分方式。

### 变更 1：顶层 Planner 骨架接入

建议变更名：

- `introduce-langgraph-planner-shell`

目标：

- 在 Python 侧引入顶层 Planner 壳层
- 保持现有 Kernel 主链路不变
- 先打通“用户请求 -> Planner -> 现有能力入口”的骨架

主要边界：

- 不在这一变更里做复杂 Skill
- 不在这一变更里大改前端
- 不替换现有检索和问答主链路

建议影响的 spec：

- `capability-planner-execution`
- `node-gateway-orchestration`

### 变更 2：多轮指代与对象补全 Skill

建议变更名：

- `add-conversation-reference-resolution-skill`

目标：

- 解决“他们”“这些论文”“上面那篇”之类的多轮指代问题
- 在 Planner 前置阶段把问题补成可检索形式

主要边界：

- 只解决上下文对象解析
- 不处理复杂研究分析任务
- 不引入开放式 Agent 自治

建议影响的 spec：

- `multi-turn-session-state`
- `control-intent-routing`
- `paper-assistant-mode`

### 变更 3：问题分类与工具路由 Skill

建议变更名：

- `add-query-classification-and-skill-routing`

目标：

- 区分事实问答、标题翻译、论文对比、研究辅助、任务操作等问题类型
- 根据问题类型选择本地检索、联网补充或其他 Skill

主要边界：

- 只做分类和路由
- 不在这一阶段做长链路 Agent 推理

建议影响的 spec：

- `control-intent-routing`
- `ai-stage-routing-center`
- `llm-fallback-routing-policy`

### 变更 4：标题/术语中文化 Skill

建议变更名：

- `add-paper-title-and-term-localization-skill`

目标：

- 对论文标题、术语、方法名提供中文化表达
- 明确其输出是“解释性结果”，不是事实 chunk 引用

主要边界：

- 不把中文化结果冒充 citation 证据
- 不处理通用翻译平台能力

建议影响的 spec：

- `paper-assistant-mode`
- `unified-source-citation-contract`
- `evidence-policy-gate`

### 变更 5：研究辅助组合 Skill

建议变更名：

- `add-research-assistant-composite-skills`

目标：

- 提供论文对比、创新点提炼、下一步追问建议、灵感草稿生成等能力

主要边界：

- 只做研究辅助表达和组合
- 不重构底层 Pipeline

建议影响的 spec：

- `research-assistant-workbench`
- `idea-cards-lifecycle`
- `paper-assistant-mode`

### 变更 6：网关事件协议增强

建议变更名：

- `extend-gateway-for-planner-and-skill-events`

目标：

- 为 Planner/Skill 增加轻量事件
- 区分聊天事件、任务事件、技能事件

主要边界：

- 不把网关做成重状态 Agent Runtime
- 只增加必要的高层事件，不输出细碎内部 trace

建议影响的 spec：

- `node-gateway-orchestration`
- `llm-answer-streaming-delivery`
- `llm-observability-contract`

### 变更 7：前端轻量 Agent 交互适配

建议变更名：

- `add-chat-planner-awareness-ui`

目标：

- 在聊天 UI 展示少量“系统理解/正在执行”的高层提示
- 增加“我理解的是”区域和简化后的 Skill 调用概览

主要边界：

- 不把聊天页做成调试控制台
- 不默认展示完整 agent trace

建议影响的 spec：

- `frontend-chat-focused-experience`
- `research-assistant-workbench`
- `frontend-status-mapping-and-display-governance`

### 变更 8：Planner/Skill 观测与评测

建议变更名：

- `add-planner-skill-observability-and-evals`

目标：

- 记录 Planner 决策、Skill 路由、失败回退和触发效果
- 评估多轮代词问题、标题中文化和研究辅助能力的改善幅度

主要边界：

- 重点是可观测性和评估
- 不在这一阶段继续扩能力面

建议影响的 spec：

- `llm-observability-contract`
- `paper-assistant-growth-evaluation`
- `llm-failure-diagnostics-observability`

## 推荐的变更顺序

如果你要逐个开启 OpenSpec 变更，建议优先级如下：

1. `introduce-langgraph-planner-shell`
2. `add-conversation-reference-resolution-skill`
3. `add-query-classification-and-skill-routing`
4. `extend-gateway-for-planner-and-skill-events`
5. `add-chat-planner-awareness-ui`
6. `add-paper-title-and-term-localization-skill`
7. `add-research-assistant-composite-skills`
8. `add-planner-skill-observability-and-evals`

这个顺序的好处是：

- 先打骨架
- 再解决最痛的多轮理解问题
- 再补协议和 UI
- 最后扩展复杂 Skill 和评测

## 建议的变更分组

如果你不想一次开 8 个变更，可以先分成 3 组：

### A 组：骨架与入口理解

- `introduce-langgraph-planner-shell`
- `add-conversation-reference-resolution-skill`
- `add-query-classification-and-skill-routing`

### B 组：协议与前端适配

- `extend-gateway-for-planner-and-skill-events`
- `add-chat-planner-awareness-ui`

### C 组：面向研究助手的 Skill 扩展

- `add-paper-title-and-term-localization-skill`
- `add-research-assistant-composite-skills`
- `add-planner-skill-observability-and-evals`

## 前端需要如何变化

前端不需要立刻重写，但需要逐步适配“系统会先理解、再执行”的新交互方式。

### 前端原则

- 保持聊天仍然是主入口
- 不把内部 Agent 细节全部暴露给用户
- 只展示对用户有帮助的“高层过程”

### 推荐增加的前端元素

#### 1. 轻量“当前理解”提示

例如：

- 正在识别你提到的论文
- 正在读取上一轮论文列表
- 正在判断是否需要联网补充

这类提示能让用户知道系统不是卡住，而是在理解问题。

#### 2. 调用概览卡片

当某轮调用了 Skill 时，可在回答上方或回答后显示一条很短的过程摘要：

- 已使用：论文列表读取、标题中文化
- 已使用：本地检索、论文对比总结

不要展示过细的调试 trace。

#### 3. “我理解的是”澄清区

当系统需要处理代词或省略时，可以给出一句轻提示：

- 我理解你说的“他们”是上一轮提到的 3 篇论文

如果理解错了，用户可以立刻纠正。

#### 4. 回答来源层次化

未来可以把来源分成两层：

- 事实证据来源
- 辅助技能来源

例如，标题中文化这类 Skill 产生的是“解释性结果”，不应冒充 chunk 事实证据。

#### 4.1 面向 OpenSpec 的前端边界

前端相关变更建议只关注下面几件事：

- 聊天区如何展示 Planner 的高层理解
- 聊天区如何展示 Skill 的简短调用摘要
- 证据来源与 Skill 结果如何分层呈现

前端变更不建议承担：

- 复杂 Agent 编排逻辑
- Planner 决策本体
- 过细的调试可视化

#### 5. 更自然的拒答与澄清

当证据不足时，前端应该更多展示：

- 需要你补充哪个对象
- 当前无法确定的原因

而不是只显示一条笼统拒答。

## 网关需要如何变化

网关建议作为“轻编排层”演进，不要直接变成复杂 Agent Runtime。

推荐变化：

- 增加 Planner/Skill 相关的轻量事件类型
- 保持聊天事件、任务事件、技能事件分域
- 允许记录“本轮做了哪些高层动作”

不推荐的变化：

- 在网关里塞入复杂多轮反思式 Agent 执行逻辑
- 把网关变成重状态的自治控制中心

## Kernel 需要如何变化

Kernel 不应被整体推翻，而应逐步暴露更清晰的稳定能力接口。

推荐方向：

- 把“可复用能力”与“内部阶段”区分开
- 为 Skill 提供更稳定的调用入口
- 保留证据门控、引用绑定、任务状态等硬边界

Kernel 更像“能力底座”，不是第一个被替换的对象。

## 证据门控在新架构中的位置

证据门控不建议删除。

更合理的做法是：

- Planner 和 Skill 尽量减少错误进入检索和作答阶段的机会
- Evidence Gate 继续作为最终安全边界存在

也就是说，未来应当让“更聪明的前置理解”减少 Gate 触发频率，而不是拿掉 Gate。

## 判断这条路线是否成功的信号

可以用下面这些信号来判断转型是否有效：

- 多轮代词问题触发拒答的比例明显下降
- 标题翻译、对象补全、论文列表跟进等问题命中率提升
- 前端没有明显变成调试控制台
- Gateway 协议复杂度仍可控
- Evidence Gate 触发率下降，但事实错误率没有上升

## 推荐的近期规划

如果要开始，可以先做一轮纯设计阶段的规划，不急着动代码。

建议下一步先产出：

1. `proposal`：为什么要引入 Planner/Skill 混合架构
2. `design`：Planner 放在哪里、Skill 如何分类、协议如何扩展
3. `spec`：第一批 Skill 的能力定义与边界

## 最后一句话

最适合当前系统的，不是“推倒重来做 Agent”，而是：

在现有稳定工作台上，加一个更聪明的理解与编排层。
