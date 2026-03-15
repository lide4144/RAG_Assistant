# Agent-First 转向计划

## 这份文档是干什么的

这份文档用于取代此前偏保守的“Planner/Skill 渐进式混合架构”路线。

当前目标已经明确调整为：

- 顶层由 LLM Planner 负责操作理解与工具选择
- 底层仍保留确定性 Pipeline 和安全边界
- LangGraph 作为顶层运行时，不再只是被动壳层

这是一份供后续开启 OpenSpec 变更时直接参考的路线图。

当前仓库中的最小实现契约见 [docs/planner-runtime-contract.md](/home/programer/RAG_GPTV1.0/docs/planner-runtime-contract.md)。

## 当前已完成工作的重新定位

### 已完成 1：`introduce-langgraph-planner-shell`

保留，不废弃。

但其角色从“保守的 planner shell 底座”升级为：

- Agent-first 架构中的顶层运行时基础
- LLM Planner 的承载容器
- 后续所有 tool/skill 编排的入口

### 已撤回 2：`add-conversation-reference-resolution-skill`

当前不作为主线继续推进。

原因：

- 它原先被定义为强前置、偏规则化的对象补全 skill
- 在 agent-first 版本里，这种能力更适合变成 Planner 可调用的工具或 fallback 机制

这意味着：

- 它不是被否定
- 而是暂时退出主线
- 后续可在 agent-first 路线里以“reference resolution tool/fallback”身份重新引入

## 旧变更处置表

下面这张表用于明确：旧路线里的变更，哪些保留复用，哪些暂停，哪些由新变更替代。

| 旧变更 | 处置方式 | 说明 |
|---|---|---|
| `introduce-langgraph-planner-shell` | 保留复用 | 继续作为 `LLM Planner runtime` 底座，不废弃 |
| `add-conversation-reference-resolution-skill` | 暂停主线 / 后续重引入 | 不再按“强前置规则 skill”推进；未来以 tool 或 fallback 形式回归 |
| `add-query-classification-and-skill-routing` | 废弃旧定义 / 由新变更替代 | 改由 `add-llm-planner-tool-selection-policy` 接管 |
| `add-paper-title-and-term-localization-skill` | 保留需求 / 并入 tool 体系 | 需求仍有效，但不建议继续以旧 skill-first 定义推进；后续作为 Planner 可调用 tool 接入 |
| `add-research-assistant-composite-skills` | 废弃旧定义 / 由新变更替代 | 改由 `add-research-assistant-agent-skills` 接管 |
| `extend-gateway-for-planner-and-skill-events` | 废弃旧定义 / 由新变更替代 | 改由 `extend-gateway-for-agent-execution-events` 接管 |
| `add-chat-planner-awareness-ui` | 废弃旧定义 / 由新变更替代 | 改由 `add-agent-planning-awareness-ui` 接管 |
| `add-planner-skill-observability-and-evals` | 废弃旧定义 / 由新变更替代 | 改由 `add-agent-observability-and-evals` 接管 |

### 处置原则

- “保留复用”表示旧变更仍可继续存在，并作为新路线基础。
- “暂停主线”表示旧变更目录可以保留，但不要继续按旧 proposal/design/spec/tasks 推进。
- “废弃旧定义 / 由新变更替代”表示不要再基于旧变更继续开工，应改为开启新变更。
- “保留需求 / 并入 tool 体系”表示用户价值仍然成立，但实现边界需要改写为 agent-first 版本。

## 新的目标架构

```text
用户输入
  ↓
LLM Planner (LangGraph runtime)
  ↓
决定调用哪些 tool / skill
  ↓
确定性 Kernel 能力执行
  ↓
evidence gate / citation / task state
  ↓
前端展示
```

关键原则：

- 顶层操作理解交给 LLM Planner
- 底层数据处理、检索、引用、安全边界继续保持确定性
- 不把系统做成无限步、自主失控的开放式 agent

## agent-first 版本的建议变更清单

### 1. `shift-to-agent-first-planner-runtime`

目标：

- 正式定义从保守 Planner/Skill 路线转向 agent-first
- 让 LangGraph shell 成为 LLM Planner runtime

作用：

- 这是后续所有 agent-first 变更的总起点

### 2. `add-llm-planner-tool-selection-policy`

目标：

- 让顶层 LLM Planner 负责判断用户意图
- 负责选择调用哪些 tool / skill
- 决定是否需要澄清、是否走本地、是否联网、是否走研究辅助能力

替代旧变更：

- `add-query-classification-and-skill-routing`

### 3. `expose-kernel-capabilities-as-agent-tools`

目标：

- 把现有 Kernel 中可复用能力整理成明确的 agent tools
- 例如：论文列表、catalog 查询、summary、fact QA、control、标题中文化、研究辅助等

作用：

- 让底层能力从“主流程内部步骤”变成“可被 Planner 调用的稳定工具”

### 4. `extend-gateway-for-agent-execution-events`

目标：

- 为 agent-first planner 增加高层事件流
- 支持 planning、tool selection、tool running、tool result、degraded/fallback 等状态

替代旧变更：

- `extend-gateway-for-planner-and-skill-events`

### 5. `add-agent-planning-awareness-ui`

目标：

- 在聊天 UI 展示少量高层 agent 规划状态
- 例如：正在理解请求、正在选择工具、正在调用某个能力

替代旧变更：

- `add-chat-planner-awareness-ui`

### 6. `add-agent-safe-fallback-and-guardrails`

目标：

- 定义 agent-first 架构下的安全边界
- 包括：evidence gate、citation contract、tool 调用失败回退、planner 降级策略

作用：

- 防止“顶层更自由”演变成“系统更容易幻觉和失控”

### 7. `add-research-assistant-agent-skills`

目标：

- 将论文对比、创新点提炼、下一步建议、灵感草稿等定义为可被 Planner 调用的组合技能

替代旧变更：

- `add-research-assistant-composite-skills`

### 8. `add-agent-observability-and-evals`

目标：

- 为 agent-first planner 增加规划决策、工具调用、失败回退与效果评测

替代旧变更：

- `add-planner-skill-observability-and-evals`

## 建议顺序

### 第一阶段：重定义总路线

1. `shift-to-agent-first-planner-runtime`

### 第二阶段：让 Planner 真正能决策

2. `add-llm-planner-tool-selection-policy`
3. `expose-kernel-capabilities-as-agent-tools`

### 第三阶段：让系统能把 agent 行为表达出来

4. `extend-gateway-for-agent-execution-events`
5. `add-agent-planning-awareness-ui`

### 第四阶段：补安全与研究能力

6. `add-agent-safe-fallback-and-guardrails`
7. `add-research-assistant-agent-skills`

### 第五阶段：补评测

8. `add-agent-observability-and-evals`

## 开新对话时应该怎么说

如果要分别开启这些变更，建议每次新对话都补充以下背景：

- 当前路线是 agent-first，不再沿用旧的保守 skill-first 定义
- `introduce-langgraph-planner-shell` 已完成，视为 LLM Planner runtime 底座
- `add-conversation-reference-resolution-skill` 已撤回，不作为主线；如需对象补全，需重新以 tool/fallback 视角设计
- 除 `introduce-langgraph-planner-shell` 外，旧路线里其余变更若未明确标注“保留复用”，都不应继续按旧定义推进
- 当前只讨论指定变更，不要扩到其他变更范围

## 一句话总结

原路线解决的是“如何逐步搭建 Planner/Skill 架构”。

新路线解决的是“如何让 LLM 真正站到顶层做规划，同时保住底层确定性与安全边界”。
