# SQLite Session Storage

本指南介绍如何使用 SQLite 作为对话历史的存储后端，以便进行 SQL 查询和调试。

## 为什么使用 SQLite？

相比默认的 JSON 文件存储，SQLite 提供以下优势：

- **SQL 查询**：使用标准 SQL 查询会话数据
- **结构化存储**：更好的数据一致性和完整性
- **调试友好**：支持复杂的过滤和聚合查询
- **原子操作**：支持事务，避免数据损坏

## 快速开始

### 1. 切换到 SQLite 后端

设置环境变量：

```bash
export SESSION_BACKEND=sqlite
export SESSION_SQLITE_PATH=data/session_store.db
```

或者使用默认值（`data/session_store.db`）：

```bash
export SESSION_BACKEND=sqlite
```

### 2. 启动应用

```bash
python -m app.kernel_api
```

第一次启动时会自动创建数据库文件和表结构。

## 配置选项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `SESSION_BACKEND` | `file` | 存储后端类型：`file`、`redis`、`sqlite` |
| `SESSION_SQLITE_PATH` | `data/session_store.db` | SQLite 数据库文件路径 |

## 数据库 Schema

### 表结构

**sessions** - 会话主表
```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**session_turns** - 对话轮次表
```sql
CREATE TABLE session_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    user_input TEXT,
    standalone_query TEXT,
    answer TEXT,
    decision TEXT,
    cited_chunk_ids TEXT,  -- JSON 数组
    entity_mentions TEXT,  -- JSON 数组
    topic_anchors TEXT,    -- JSON 数组
    output_warnings TEXT,  -- JSON 数组
    planner_summary TEXT,  -- JSON 对象
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    UNIQUE(session_id, turn_number)
);
```

**schema_migrations** - 迁移版本表
```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 调试工具

### 1. 会话查询工具

```bash
# 列出最近的会话
python scripts/query_sessions.py list --limit 10

# 查看特定会话详情
python scripts/query_sessions.py show <session_id>

# 查看会话的所有 turns
python scripts/query_sessions.py turns <session_id>

# 搜索会话
python scripts/query_sessions.py search "GraphRAG"

# 查看数据库统计
python scripts/query_sessions.py stats

# 执行自定义 SQL 查询
python scripts/query_sessions.py query "SELECT * FROM sessions WHERE updated_at > datetime('now', '-1 day')"
```

### 2. 数据迁移工具

从 JSON 文件迁移到 SQLite：

```bash
# 预览迁移（不实际写入）
python scripts/migrate_sessions_to_sqlite.py --dry-run

# 执行迁移
python scripts/migrate_sessions_to_sqlite.py data/session_store.json data/session_store.db
```

## SQL 查询示例

### 查询最近的会话

```sql
SELECT id, title, updated_at
FROM sessions
ORDER BY updated_at DESC
LIMIT 10;
```

### 查询特定会话的所有 turns

```sql
SELECT turn_number, user_input, decision, created_at
FROM session_turns
WHERE session_id = 'your-session-id'
ORDER BY turn_number;
```

### 统计每天的会话数

```sql
SELECT DATE(created_at) as day, COUNT(*) as count
FROM sessions
GROUP BY DATE(created_at)
ORDER BY day DESC;
```

### 查找引用特定 chunk 的会话

```sql
SELECT DISTINCT s.id, s.title
FROM sessions s
JOIN session_turns st ON s.id = st.session_id
WHERE st.cited_chunk_ids LIKE '%chunk-id-you-looking-for%';
```

### 查询平均每个会话的轮数

```sql
SELECT 
    AVG(turn_count) as avg_turns,
    MAX(turn_count) as max_turns,
    MIN(turn_count) as min_turns
FROM (
    SELECT session_id, COUNT(*) as turn_count
    FROM session_turns
    GROUP BY session_id
);
```

## 编程使用

### 创建存储实例

```python
from app.db import create_store, SQLiteStore

# 通过工厂函数创建
store = create_store("sqlite", db_path="data/sessions.db")

# 或直接实例化
store = SQLiteStore("data/sessions.db")
```

### 基本操作

```python
# 写入会话
store.write_session("session-123", {
    "turns": [...],
    "state": {...}
})

# 读取会话
session = store.read_session("session-123")

# 删除会话
store.delete_session("session-123")

# 列出会话
sessions = store.list_sessions(limit=10)

# 执行 SQL 查询（仅 SQLite）
results = store.execute_query(
    "SELECT * FROM sessions WHERE updated_at > datetime('now', '-1 day')"
)
```

## 向后兼容性

SQLite 后端与现有的 File 和 Redis 后端完全兼容：

- 相同的 `SessionStore` 接口
- 相同的函数签名
- 可以通过环境变量自由切换
- 数据相互隔离，不会冲突

## 注意事项

1. **并发写入**：SQLite 支持 WAL 模式，但并发写入性能不如 Redis。适合单进程或低并发场景。

2. **数据备份**：SQLite 是单文件，可以直接复制 `.db` 文件进行备份。

3. **迁移回滚**：如需回滚到 File 后端，只需切换 `SESSION_BACKEND=file`，SQLite 数据库文件会保留。

4. **数据清理**：定期清理旧的会话数据以保持性能：
   ```sql
   DELETE FROM session_turns WHERE created_at < datetime('now', '-30 days');
   DELETE FROM sessions WHERE updated_at < datetime('now', '-30 days');
   ```

## 故障排除

### 数据库锁定

如果出现 "database is locked" 错误：
- 检查是否有其他进程正在写入
- WAL 模式已启用，通常可以并发读取
- 重启应用可以释放锁

### 数据迁移失败

使用迁移工具时：
```bash
# 先预览
python scripts/migrate_sessions_to_sqlite.py --dry-run

# 检查 JSON 文件格式
python -c "import json; json.load(open('data/session_store.json'))"
```

### 性能问题

如果查询变慢：
- 检查数据库文件大小：`ls -lh data/session_store.db`
- 考虑定期清理旧数据
- 使用索引（已自动创建）
