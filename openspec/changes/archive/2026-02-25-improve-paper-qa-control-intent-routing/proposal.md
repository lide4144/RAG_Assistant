## 为什么

当前论文问答多轮对话中，用户常用“用中文回答我”“简短点”“继续”等控制类输入来调整回答方式，而不是发起新检索。现有流程会把这类输入直接当作查询词，导致检索偏题并触发 Sufficiency Gate 的 `topic_mismatch` 拒答，影响可用性与连贯性。

## 变更内容

- 新增控制意图路由，在检索前区分 `retrieval_query` 与 `style/format/continuation` 等非检索输入。
- 为非检索输入增加会话锚定策略：优先复用上一轮主题（`standalone_query`、`entity_mentions`、最近证据上下文），而非发起无主题新检索。
- 调整 Sufficiency Gate 的主题匹配输入来源：当输入被判定为控制意图时，使用锚定主题文本参与 topic match，避免把“用中文回答我”直接作为主题词。
- 增加可观测字段与配置开关，支持灰度启用与回退。
- **BREAKING**：无（默认配置下保持现有行为，仅在开启新开关后生效）。

## 功能 (Capabilities)

### 新增功能
- `control-intent-routing`: 在问答入口识别控制意图并分流执行路径，支持 style/format/continuation 等非检索类用户输入。

### 修改功能
- `query-rewriting`: 增加控制意图场景下的改写/继承策略，避免将控制词作为独立检索 query。
- `multi-turn-session-state`: 扩展会话锚定上下文提取与复用规则，支持最近主题与证据上下文继承。
- `sufficiency-gate`: 在控制意图场景下切换 topic match 的问题文本来源，降低误触发 `topic_mismatch`。
- `visual-debug-interactive-ui`: 展示意图分类、锚定主题、路由决策与 gate 输入来源，便于调试与验收。

## 影响

- 受影响代码：
  - `app/qa.py`（入口路由、gate 调用参数、trace 输出）
  - `app/rewrite.py`（控制意图识别与改写策略）
  - `app/session_state.py`（锚定主题提取）
  - `app/config.py` 与 `configs/default.yaml`（新配置项）
  - `app/ui.py`（调试可视化字段）
- 受影响测试：
  - `tests/test_rewrite.py`
  - `tests/test_m7_6_multi_turn.py`
  - `tests/test_m8_sufficiency_gate.py`
- 受影响文档：
  - `README.md` 与相关报告文档中的多轮/护栏行为说明。
