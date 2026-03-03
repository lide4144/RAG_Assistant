## 为什么

当前系统主要依赖 CLI 与日志进行调试，人工验证检索链路与引用来源成本高且不直观。在进入 M9 大规模自动评估前，需要一个轻量可视化交互层，将回答结果与底层检索/图扩展/拒答信号并排展示，降低定位错误与回归风险的时间成本。

## 变更内容

- 新增一个轻量 Web UI（`app/ui.py`，基于 Streamlit 或 Gradio），用于多轮对话与可视化调试。
- 在对话区渲染 User/Assistant 多轮消息，Assistant 中的引用标记（如 `[1]`、`[2]`）可交互查看对应证据。
- 新增“开启新对话/清空上下文”入口，调用会话清理接口（M7.6 `clear_session`）。
- 新增开发者审查面板，展示每轮 Query 演变、证据来源与关键评分、降级告警（Sufficiency Gate）。
- 支持明确标识 graph expand 拉入的证据，满足人工 Trace 审查。

## 功能 (Capabilities)

### 新增功能
- `visual-debug-interactive-ui`: 提供可运行的交互式 UI，将聊天结果与可视化调试信息（trace）统一呈现。

### 修改功能
- `multi-turn-session-state`: 增加 UI 层可触发的会话重置行为与无污染新会话语义。
- `graph-expansion-retrieval`: 增加面向审查的证据来源可见性要求，明确标注 graph_expand 来源。
- `sufficiency-gate`: 增加 UI 层对拒答/澄清降级信号的高亮展示要求。
- `output-consistency-evidence-allocation`: 增加 UI 层对回答内引用标记的可交互映射要求。

## 影响

- 代码：新增 `app/ui.py` 及必要的 UI 适配代码；可能调整管线输出结构的字段透传（trace/debug payload）。
- API：不引入外部公开 API 破坏性变化，主要为现有 Python API 增加/规范调试字段消费方式。
- 依赖：新增或确认 `streamlit`（或 `gradio`）运行依赖。
- 测试与验证：新增 UI 启动与交互验收步骤；补充至少一次 graph_expand 场景的人工验证流程。
