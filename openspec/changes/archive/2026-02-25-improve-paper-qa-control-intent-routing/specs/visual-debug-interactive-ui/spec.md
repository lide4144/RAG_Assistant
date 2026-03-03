## ADDED Requirements

### 需求:系统必须展示控制意图路由与主题锚定审查信息
调试 UI 必须展示本轮 `intent_type`、`anchor_query`（若有）、`topic_query_source`（例如 `user_query` 或 `anchor_query`）以及路由开关状态，便于定位控制意图误路由问题。

#### 场景:控制意图字段可见
- **当** 用户输入“用中文回答我”并触发控制意图路由
- **那么** 审查面板必须可见 `intent_type=style_control` 与对应 `anchor_query`

## MODIFIED Requirements

### 需求:系统必须高亮 graph_expand 与降级告警
审查面板中的 `evidence_grouped` 必须高亮展示 `score_retrieval`、`score_rerank`、`source`；当 `source=graph_expand` 时必须有明确视觉标识。若 `decision` 为 `refuse` 或 `clarify`，系统必须使用醒目颜色展示 `reason` 与 `output_warnings`。当本轮命中控制意图路由时，审查面板还必须展示 `topic_match` 的查询来源，明确区分“用户原句”与“锚定主题”。

#### 场景:图扩展证据可区分
- **当** 某条 evidence 的 `source=graph_expand`
- **那么** 审查面板必须显示可识别的 graph_expand 标签，并可与 BM25/Dense 来源区分

#### 场景:降级告警高亮
- **当** Sufficiency Gate 输出 `decision=refuse` 或 `decision=clarify`
- **那么** 审查面板必须以醒目颜色展示 `reason` 与 `output_warnings`

#### 场景:主题匹配来源可审查
- **当** 本轮 `intent_type` 为控制意图且 Gate 执行了 topic match
- **那么** 审查面板必须显示 `topic_query_source`，用于确认 Gate 是否基于锚定主题计算

