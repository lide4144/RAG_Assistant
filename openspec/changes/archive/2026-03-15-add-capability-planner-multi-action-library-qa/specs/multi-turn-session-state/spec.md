## 新增需求

### 需求:系统必须在挂起澄清状态下先执行换题检测
当会话处于 `need_clarify` 或 `waiting_followup` 状态时，系统必须先判断当前输入是在回答挂起澄清，还是开启了新话题；禁止默认将当前输入机械拼接到上一轮问题后形成 `standalone_query`。

#### 场景:新话题清除挂起澄清
- **当** 上一轮处于 `waiting_followup` 且当前输入为“库中有哪些论文”
- **那么** 系统必须将其识别为新话题、清除挂起澄清状态，并以“库中有哪些论文”作为新的 `standalone_query`

## 修改需求

### 需求:会话清空与隔离
系统必须支持会话显式重置，并在 Redis 与记忆层同步清除（或逻辑隔离）该会话上下文，防止历史污染新会话。对于统一 planner 模式，系统还必须在检测到 `is_new_topic=true` 且 `should_clear_pending_clarify=true` 时清除挂起澄清状态，不得让旧澄清约束污染新问题。

#### 场景:清空后不污染新检索
- **当** 用户执行“新对话/清空上下文”后立即提问无关问题
- **那么** 系统必须按空上下文处理且不复用旧会话记忆

#### 场景:换题后不继承旧澄清状态
- **当** 统一 planner 判定当前输入为新话题
- **那么** 系统必须清除挂起澄清状态与临时澄清约束，并阻止上一轮问题被拼接进新的 `standalone_query`

### 需求:多轮监控日志字段
系统必须在运行日志中新增并输出：`session_id`、`turn_number`、`history_used_turns`、`history_tokens_est`、`coreference_resolved`、`standalone_query`。对于统一 planner 模式，系统还必须输出 `is_new_topic`、`should_clear_pending_clarify` 与 `relation_to_previous`。

#### 场景:trace 字段完整
- **当** 系统完成任意一轮多轮问答
- **那么** `run_trace` 中必须包含全部新增字段，且类型可序列化并通过 schema 校验

#### 场景:换题判断可审查
- **当** 当前轮发生换题检测
- **那么** run trace 必须包含 `is_new_topic`、`should_clear_pending_clarify` 与其对应判定结果

### 需求:系统必须维护主题级澄清计数状态
系统必须在显式状态机中维护澄清状态（例如 `normal/need_clarify/waiting_followup`）与主题级计数，避免通过分散 if-else 隐式维护状态。系统还必须支持在识别为新话题时重置主题级澄清计数，不得让旧主题的澄清计数延续到新主题。

#### 场景:澄清状态可恢复
- **当** 上一轮进入 `waiting_followup` 且用户补充信息
- **那么** 系统必须从挂起状态恢复并继续执行后续链路

#### 场景:换题后澄清计数重置
- **当** 当前轮被识别为新话题
- **那么** 系统必须重置上一主题的澄清计数，并按新主题重新开始状态跟踪

## 移除需求
