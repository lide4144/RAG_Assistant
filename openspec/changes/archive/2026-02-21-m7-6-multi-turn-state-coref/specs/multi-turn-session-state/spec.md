## 新增需求

### 需求:会话状态脱水存储
系统必须按 `session_id` 维护会话状态。每轮结束后，系统必须仅存储脱水记录：`user_input`、`standalone_query`、`answer`、`cited_chunk_ids`、`decision`（可含最小派生字段如 `entity_mentions`），禁止存储原始 chunk 文本或完整检索 payload。

#### 场景:写入回合记录
- **当** 一轮问答完成并产出最终答案
- **那么** 系统必须向对应 `session_id` 追加一条脱水 turn 记录，且记录中不得出现 raw chunk 文本

### 需求:滑动窗口历史供重写
系统必须在 rewrite 阶段读取最近 N 轮（默认 N=3）脱水历史，并生成 `standalone_query`。若当前问题含指代，`standalone_query` 必须补齐关键实体，且禁止拼接历史回答整段文本。

#### 场景:指代追问补齐实体
- **当** 当前输入为代词追问（例如“它和微调有什么区别？”）且历史包含实体（例如 `RAG`）
- **那么** `standalone_query` 必须包含该实体并保持当前问题意图

### 需求:会话清空与隔离
系统必须提供 `clear_session(session_id)` 接口。调用后，指定会话历史必须被删除；不同 `session_id` 的历史必须隔离，禁止跨会话污染。

#### 场景:清空后重新提问
- **当** 前端调用 `clear_session(session_id)` 后用户发起新问题
- **那么** 系统必须按新会话起点处理，`history_used_turns` 必须为 0 或等效空历史状态

### 需求:多轮监控日志字段
系统必须在运行日志中新增并输出：`session_id`、`turn_number`、`history_used_turns`、`history_tokens_est`、`coreference_resolved`、`standalone_query`。

#### 场景:trace 字段完整
- **当** 系统完成任意一轮多轮问答
- **那么** `run_trace` 中必须包含全部新增字段，且类型可序列化并通过 schema 校验
