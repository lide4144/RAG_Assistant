## 上下文

当前问答流水线默认将用户输入作为检索语义入口，即使输入是“用中文回答我”“简短点”“继续”等控制语句，也会走改写、检索与 Sufficiency Gate 主题匹配。该行为在单轮可接受，但在多轮论文问答中会造成高频误拒答：控制语句缺少主题词，检索结果与主题弱相关，最终触发 `topic_mismatch`。

现有系统已经具备多轮状态（`session_id`、`standalone_query`、`entity_mentions`）、改写护栏与 Gate 可观测字段，具备实现“控制意图分流 + 主题继承”所需基础。

## 目标 / 非目标

**目标：**
- 在检索前识别控制意图，将非检索输入从检索路径分流。
- 对控制意图复用最近主题锚点，避免把控制词当检索 query。
- 在控制意图场景下让 Sufficiency Gate 使用锚定主题进行 topic match。
- 增加可观测字段与配置开关，支持灰度与回退。

**非目标：**
- 不改变核心召回、重排与答案生成模型。
- 不引入新的外部依赖或复杂模型分类器。
- 不在本变更中重构 UI 整体布局，仅扩展调试字段展示。

## 决策

### 决策 1：新增轻量 Intent Router（规则优先）
- 方案：在 `run_qa` 入口新增 `intent_type` 判定，优先识别 `style_control`、`format_control`、`continuation_control`，未命中则走 `retrieval_query`。
- 备选：
  - 全量 LLM 分类：精度潜力高，但延迟与失败面更大。
  - 不分流，仅扩展 rewrite 规则：耦合过高，后续维护困难。
- 选择理由：规则路由可控、可解释、与现有 rewrite 护栏一致，适合先落地。

### 决策 2：控制意图采用“主题锚定继承”，不直接新检索
- 方案：从会话状态提取 `last_standalone_query` + `entity_mentions` + 最近引用线索，生成 `anchor_query`；控制意图优先基于 `anchor_query` 作答。
- 备选：
  - 直接复用上一轮答案文本：可能传播上一轮错误且证据链弱。
  - 控制意图也执行新检索：会重复触发当前问题。
- 选择理由：继承主题比继承答案更稳健，并保持证据链可追踪。

### 决策 3：Gate 保持严格，但切换 topic match 输入来源
- 方案：保留现有 Gate 阈值与拒答逻辑；当 `intent_type` 为控制意图时，用 `anchor_query` 作为 `query_used` 参与 topic match。
- 备选：
  - 降低阈值：会扩大误答风险。
  - 控制意图跳过 Gate：破坏防幻觉护栏。
- 选择理由：在不降低安全性的前提下修复误拒答。

### 决策 4：配置化灰度发布
- 方案：新增 `intent_router_enabled`、`style_control_reuse_last_topic`、`style_control_max_turn_distance`。
- 备选：全量强制开启。
- 选择理由：支持逐步上线与快速回滚。

## 风险 / 权衡

- [误判为控制意图] → 增加低置信度回退到 `retrieval_query`，并记录 `intent_confidence`。
- [主题锚点过旧] → 引入 `style_control_max_turn_distance`，超限触发澄清提示。
- [混合输入（控制+检索）解析不稳] → 拆分为控制前缀 + 检索载荷，无法拆分时走检索主路径。
- [可观测字段增多导致 trace 复杂] → 只增加必要字段：`intent_type`、`anchor_query`、`topic_query_source`。

