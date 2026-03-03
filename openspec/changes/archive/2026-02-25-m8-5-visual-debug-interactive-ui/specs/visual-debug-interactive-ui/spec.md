## ADDED Requirements

### 需求:系统必须提供可运行的双区调试 UI
系统必须提供 `app/ui.py` 入口，并且必须在一次运行中同时提供对话交互区与开发者审查面板。对话交互区必须展示多轮 User/Assistant 消息；审查面板必须展示当前轮可展开的结构化 trace 数据。

#### 场景:UI 启动成功
- **当** 开发者执行 `streamlit run app/ui.py`
- **那么** 浏览器必须成功打开 UI，且界面中可见对话区与审查面板两个区域

### 需求:系统必须支持回答引用的可交互审查
当 Assistant 回答包含 `[n]` 引用标记时，系统必须将每个标记映射到可交互证据条目，并展示至少 `chunk_id`、`paper_id`、`source` 与证据文本。系统禁止将无映射的引用标记渲染为可点击成功状态。

#### 场景:点击引用定位证据
- **当** 回答中出现 `[1]` 且用户点击该标记
- **那么** 系统必须在审查面板中定位并展示对应 citation/evidence 详情

### 需求:系统必须支持新对话与上下文清空
UI 必须提供“开启新对话”或“清空上下文”操作，并且必须调用 `clear_session(session_id)`。调用成功后，新问题处理必须基于空历史上下文，禁止复用被清空会话的历史。

#### 场景:清空后不污染新检索
- **当** 用户点击“开启新对话”后立即发起无关问题
- **那么** 系统必须按新会话处理，且回答与检索上下文不得依赖清空前历史

### 需求:系统必须高亮 graph_expand 与降级告警
审查面板中的 `evidence_grouped` 必须高亮展示 `score_retrieval`、`score_rerank`、`source`；当 `source=graph_expand` 时必须有明确视觉标识。若 `decision` 为 `refuse` 或 `clarify`，系统必须使用醒目颜色展示 `reason` 与 `output_warnings`。

#### 场景:图扩展证据可区分
- **当** 某条 evidence 的 `source=graph_expand`
- **那么** 审查面板必须显示可识别的 graph_expand 标签，并可与 BM25/Dense 来源区分

#### 场景:降级告警高亮
- **当** Sufficiency Gate 输出 `decision=refuse` 或 `decision=clarify`
- **那么** 审查面板必须以醒目颜色展示 `reason` 与 `output_warnings`
