## MODIFIED Requirements

### 需求:存储后端接口扩展
系统必须扩展现有 `session_state.py` 的存储接口，支持可插拔的后端实现。

#### 场景:后端配置解析
- **当** 系统初始化会话存储模块
- **那么** 系统必须读取 `SESSION_BACKEND` 环境变量
- **并且** 有效值必须包括 `file`（默认）、`redis`、`sqlite`

#### 场景:后端实例化
- **当** 系统创建存储后端实例
- **那么** 系统必须根据配置实例化对应的后端实现
- **并且** 所有后端必须实现统一的 `SessionStore` 接口

### 需求:统一会话存储接口
系统必须定义统一的 `SessionStore` 接口，所有后端实现必须遵循。

#### 场景:读取会话记录
- **当** 系统调用 `store.read_session(session_id)`
- **那么** 无论使用哪种后端，都必须返回统一的会话数据结构

#### 场景:写入会话记录
- **当** 系统调用 `store.write_session(session_id, data)`
- **那么** 无论使用哪种后端，都必须持久化存储

#### 场景:删除会话记录
- **当** 系统调用 `store.delete_session(session_id)`
- **那么** 无论使用哪种后端，都必须删除对应的会话数据

#### 场景:列出所有会话
- **当** 系统调用 `store.list_sessions()`
- **那么** 无论使用哪种后端，都必须返回会话列表

### 需求:SQLite后端配置选项
系统必须支持SQLite特定的配置选项。

#### 场景:配置数据库文件路径
- **当** 管理员设置 `SESSION_SQLITE_PATH=/data/sessions.db`
- **那么** 系统必须使用指定的路径创建和访问数据库文件

#### 场景:默认数据库路径
- **当** 未设置 `SESSION_SQLITE_PATH` 配置
- **那么** 系统必须使用默认路径 `data/session_store.db`

## ADDED Requirements

### 需求:现有后端保持不变
现有File和Redis后端的实现和行为必须保持100%兼容，不受影响。

#### 场景:File后端继续使用
- **当** 配置 `SESSION_BACKEND=file`
- **那么** 系统必须继续使用 `data/session_store.json` 文件
- **并且** 所有现有代码路径必须正常工作

#### 场景:Redis后端继续使用
- **当** 配置 `SESSION_BACKEND=redis`
- **那么** 系统必须继续使用Redis存储
- **并且** 所有Redis特定功能（TTL等）必须正常工作
