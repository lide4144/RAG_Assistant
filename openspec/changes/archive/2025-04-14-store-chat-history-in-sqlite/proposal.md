## 为什么

当前系统使用 JSON 文件存储对话历史，导致前后端数据分离，难以调试。当用户报告问题时，开发者无法通过 SQL 查询快速定位特定会话，也无法看到用户在前端实际看到的消息格式。引入 SQLite 单文件存储可以统一数据模型，显著提升调试效率。

## 变更内容

- 新增 SQLite 存储后端作为 `session_state.py` 的第三种存储选项
- 新增 `session_messages` 和 `session_turns` 数据库表
- 保持现有 File 和 Redis 后端兼容，通过配置切换
- 新增数据库迁移机制，支持 schema 演进

## 功能 (Capabilities)

### 新增功能
- `session-storage-sqlite`: SQLite 后端实现统一对话历史存储
- `session-debug-api`: 调试接口支持 SQL 查询导出会话数据

### 修改功能
- `session-state`: 扩展存储后端接口支持 SQLite

## 影响

- 受影响文件：`app/session_state.py`（主要）
- 新增文件：`app/db/session_store.py`（数据库操作）
- 新增依赖：`sqlite3`（Python 标准库，无需额外安装）
- 配置变更：新增 `SESSION_BACKEND=sqlite` 环境变量选项
- 向后兼容：完全兼容，现有 File/Redis 后端不受影响
