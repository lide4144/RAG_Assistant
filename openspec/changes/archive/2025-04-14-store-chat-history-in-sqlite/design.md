## 上下文

当前系统的会话存储位于 `app/session_state.py`，支持两种后端：
- **File 后端**：使用 `data/session_store.json` 存储所有会话
- **Redis 后端**：使用 Redis 键值存储，支持 TTL

存在的问题：
1. 前端 localStorage 和后端存储分离，调试时难以关联
2. JSON 文件不支持 SQL 查询，无法快速筛选和分析
3. 没有统一的接口抽象，新增后端需要修改多处代码

## 目标 / 非目标

**目标：**
- 引入 SQLite 作为第三种存储后端，统一前后端数据模型
- 设计可插拔的存储后端接口，支持 file/redis/sqlite 三种实现
- 支持通过 SQL 查询快速调试会话数据
- 保持现有 File 和 Redis 后端 100% 兼容
- 数据库 schema 支持版本管理和迁移

**非目标：**
- 不替换现有 File/Redis 后端（保持向后兼容）
- 不实现分布式 SQLite（单机单文件方案）
- 不实现用户认证和多租户（仅支持单用户调试场景）
- 不修改前端 localStorage 逻辑（可选 API 接口）

## 决策

### 1. 存储后端接口设计

采用抽象基类模式定义统一接口：

```python
from abc import ABC, abstractmethod
from typing import Any

class SessionStore(ABC):
    @abstractmethod
    def read_session(self, session_id: str) -> dict[str, Any]: ...
    
    @abstractmethod
    def write_session(self, session_id: str, data: dict[str, Any]) -> None: ...
    
    @abstractmethod
    def delete_session(self, session_id: str) -> bool: ...
    
    @abstractmethod
    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]: ...
```

**理由**：
- 清晰的契约定义，便于测试和 mock
- 新增后端只需实现接口，无需修改调用方
- 支持运行时切换后端

**替代方案**：
- 函数式风格（传递 store 参数）→ 不够结构化，难以保证一致性
- 全局配置切换 → 不够灵活，难以同时操作多个后端

### 2. SQLite Schema 设计

```sql
-- 会话主表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 消息表（对应前端 messages）
CREATE TABLE session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' | 'assistant'
    content TEXT NOT NULL,
    metadata TEXT,  -- JSON: citations, mode, viewMode 等
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Turns 表（对应后端 turns，用于调试）
CREATE TABLE session_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    user_input TEXT,
    standalone_query TEXT,
    answer TEXT,
    decision TEXT,
    cited_chunk_ids TEXT,  -- JSON array
    entity_mentions TEXT,  -- JSON array
    topic_anchors TEXT,    -- JSON array
    output_warnings TEXT,  -- JSON array
    planner_summary TEXT,  -- JSON object
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    UNIQUE(session_id, turn_number)
);

-- Schema 版本表（用于迁移）
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**理由**：
- 分离 messages 和 turns，支持不同查询场景
- JSON 字段存储动态 metadata，保持 schema 简洁
- 外键约束确保数据一致性

**替代方案**：
- 单表存储所有数据 → 查询复杂，难以索引
- 每个 session 一个表 → 表数量爆炸，难以管理

### 3. 配置策略

环境变量：
- `SESSION_BACKEND`：file | redis | sqlite（默认 file）
- `SESSION_SQLITE_PATH`：数据库文件路径（默认 data/session_store.db）

**理由**：
- 与现有 `SESSION_BACKEND` 环境变量保持一致
- 新增 `SESSION_SQLITE_PATH` 提供灵活性

**替代方案**：
- 配置文件方式 → 增加复杂度，环境变量足够简单

### 4. 数据库迁移机制

采用简单版本号机制：

```python
# app/db/migrations.py
MIGRATIONS = [
    (1, """
        CREATE TABLE sessions (...);
        CREATE TABLE session_messages (...);
        CREATE TABLE session_turns (...);
        CREATE TABLE schema_migrations (...);
    """),
    # 未来新增迁移在这里添加
]

def migrate(db_path: str) -> None:
    current_version = get_current_version(db_path)
    for version, sql in MIGRATIONS:
        if version > current_version:
            execute_sql(sql)
            set_version(version)
```

**理由**：
- 简单可靠，无需外部迁移工具
- 版本号顺序执行，支持增量升级

**替代方案**：
- Alembic/SQLAlchemy Migrate → 引入额外依赖，过于复杂

### 5. 项目结构

```
app/
├── session_state.py          # 保持现有接口，内部调用 store
└── db/
    ├── __init__.py
    ├── session_store.py      # SessionStore 抽象基类
    ├── file_store.py         # FileStore 实现（从 session_state 提取）
    ├── redis_store.py        # RedisStore 实现（从 session_state 提取）
    ├── sqlite_store.py       # SQLiteStore 实现
    └── migrations.py         # 数据库迁移逻辑
```

**理由**：
- 清晰分离关注点
- 现有代码逐步迁移，降低风险
- db 模块可独立测试

## 风险 / 权衡

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| SQLite 文件损坏 | 数据丢失 | 定期备份；重要部署使用 Redis 后端 |
| 并发写入冲突 | 数据库锁定 | SQLite WAL 模式；单进程部署场景为主 |
| 性能瓶颈 | 查询变慢 | 单文件 < 1GB 性能良好；大数据量用 Redis |
| 前后端数据不一致 | 调试困难 | 可选同步机制，默认保持分离以简化 |
| Schema 变更 | 迁移失败 | 版本控制；完整测试迁移路径 |

## 迁移计划

### Phase 1: 开发阶段
1. 创建 `app/db/` 模块结构
2. 实现 `SessionStore` 抽象接口
3. 实现 `SQLiteStore`
4. 修改 `session_state.py` 使用新接口（保持向后兼容）
5. 编写单元测试

### Phase 2: 测试阶段
1. 本地测试所有三种后端
2. 验证数据迁移（如从 file 切换到 sqlite）
3. 性能基准测试

### Phase 3: 部署阶段
1. 默认保持 `SESSION_BACKEND=file`
2. 可选切换到 `SESSION_BACKEND=sqlite`
3. 监控稳定性

### 回滚策略
- 切换 `SESSION_BACKEND=file` 即可回滚
- SQLite 文件保留，数据不丢失

## 开放问题

1. **数据迁移工具**：是否需要提供从 JSON 到 SQLite 的数据迁移脚本？
   - 建议：提供可选的 `scripts/migrate_sessions_to_sqlite.py`

2. **API 接口**：调试 API 是否在本次范围内实现？
   - 建议：Phase 2 实现基础查询接口，复杂的留给后续迭代

3. **加密需求**：SQLite 文件是否需要加密？
   - 建议：初期不加密，后续如需可用 SQLCipher

4. **清理策略**：是否需要自动清理旧会话？
   - 建议：初期手动清理，后续可增加 TTL 机制
