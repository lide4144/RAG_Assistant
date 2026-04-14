## ADDED Requirements

### 需求:SQLite存储后端初始化
系统必须支持通过配置启用SQLite存储后端，并在首次使用时自动初始化数据库文件和表结构。

#### 场景:首次启动SQLite后端
- **当** 系统检测到 `SESSION_BACKEND=sqlite` 配置
- **那么** 系统必须自动创建SQLite数据库文件（如果不存在）
- **并且** 系统必须创建 `sessions`、`session_messages` 和 `session_turns` 表

#### 场景:数据库迁移
- **当** 系统启动并检测到SQLite数据库文件已存在但schema版本较旧
- **那么** 系统必须自动执行数据库迁移以更新到最新schema

### 需求:统一会话数据存储
系统必须将前端消息和后端turns数据统一存储到SQLite数据库中，确保前后端数据一致性。

#### 场景:保存新会话
- **当** 用户开始一个新的对话会话
- **那么** 系统必须在 `sessions` 表中创建一条新记录
- **并且** 记录必须包含 session_id、title、created_at、updated_at 字段

#### 场景:保存用户消息（预留）
- **当** 用户发送一条消息
- **那么** 系统可以选择在 `session_messages` 表中创建一条记录（预留功能，当前版本使用 `session_turns`）
- **并且** 记录必须包含 session_id、role、content、created_at 和 metadata 字段
- **并且** metadata 必须存储 citations、turn_number 等调试信息

#### 场景:保存后端turn数据
- **当** 系统处理完成一轮对话
- **那么** 系统必须在 `session_turns` 表中创建一条记录
- **并且** 记录必须包含 session_id、turn_number、user_input、standalone_query、answer、decision、cited_chunk_ids 等完整上下文

### 需求:读取会话历史
系统必须支持从SQLite数据库读取会话历史和消息记录。

#### 场景:加载会话列表
- **当** 前端请求历史会话列表
- **那么** 系统必须从 `sessions` 表查询并按 updated_at 降序返回

#### 场景:加载特定会话消息（预留）
- **当** 用户打开一个历史会话
- **那么** 系统可以从 `session_messages` 表查询该 session_id 的所有消息（预留功能，当前版本使用 `session_turns`）
- **并且** 按 created_at 升序返回

#### 场景:加载turn调试数据
- **当** 开发者需要调试特定会话
- **那么** 系统必须支持从 `session_turns` 表查询完整的turn上下文数据

### 需求:多存储后端兼容
系统必须保持与现有File和Redis后端的向后兼容性，通过配置自由切换。

#### 场景:配置切换存储后端
- **当** 管理员设置 `SESSION_BACKEND=file|redis|sqlite`
- **那么** 系统必须使用对应的后端实现
- **并且** 切换后端不应导致数据丢失（各后端独立存储）

#### 场景:默认后端行为
- **当** 未设置 `SESSION_BACKEND` 环境变量
- **那么** 系统必须使用File后端作为默认（保持现有行为）
