## 为什么

当前聊天问答链路将目录查询、跨文档总结、细粒度事实问答与多轮澄清状态混在同一条 QA 流中，导致“库中有哪些论文”被错误送入证据门控、“关键贡献对比表”被过度澄清、复合查询无法稳定表达“先筛选再对比”。随着 Library、Chat、Pipeline 三类工作台能力已经落地，这种单一路由已成为用户体验与后续扩展的主要瓶颈。

## 变更内容

- 引入统一的 `Resolver + Planner` 前置规划节点，一次性完成换题检测、独立问题生成、主能力识别与受限动作计划输出。
- 新增受限的多动作执行能力，支持 `catalog_lookup -> cross_doc_summary`、`catalog_lookup -> fact_qa` 等顺序计划，并为查无结果、超大结果集、严格事实问题逃逸提供熔断与降级机制。
- 调整多轮会话状态行为：当用户在 `waiting_followup` 状态下开启新话题时，系统必须清除挂起澄清状态，不得再机械拼接上一轮问题。
- 调整目录管理能力：Library 元数据查询结果可作为聊天侧计划执行的上游输入，并以 metadata provenance 回答，不再误入正文证据门控。
- 调整控制/路由能力：意图层从单一 `retrieval_query` 扩展为可输出受限 `action_plan` 的能力规划结果，并区分 `summary` 与 `strict_fact` 严格度。

## 功能 (Capabilities)

### 新增功能
- `capability-planner-execution`: 定义统一解析与能力规划节点、受限动作计划输出、顺序执行器、级联失败熔断、结果集截断与 strict-fact 逃逸拦截。

### 修改功能
- `control-intent-routing`: 将单一控制/检索路由扩展为统一能力规划输出，要求提供 `primary_capability`、`strictness`、`action_plan`、规划置信度与回退观测字段。
- `multi-turn-session-state`: 要求多轮状态机在挂起澄清时先执行换题检测，并在识别为新话题时清除 `pending_clarify`、禁止拼接旧问题。
- `paper-catalog-management`: 要求目录元数据检索能力可供 Chat 侧计划执行复用，并对超大结果集提供硬上限与截断披露。

## 影响

- 后端问答主流程：`app/qa.py`、`app/sufficiency.py`、会话状态与 trace 写入逻辑。
- 目录元数据查询与论文集合装配逻辑：`papers.json`/目录 API 复用。
- 路由与可观测性：planner JSON 解析、action plan 执行 trace、短路/截断/strictness 字段。
- 测试面将覆盖：换题检测、复合查询拆解、空结果熔断、超限截断、strict fact 逃逸拦截。
