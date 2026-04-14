## 1. 项目结构搭建

- [x] 1.1 创建 `app/db/` 目录结构
- [x] 1.2 创建 `app/db/__init__.py`
- [x] 1.3 创建 `app/db/session_store.py`（定义 SessionStore 抽象基类）

## 2. 存储后端接口定义

- [x] 2.1 在 `session_store.py` 中定义 `SessionStore` 抽象基类
- [x] 2.2 定义 `read_session(session_id: str)` 抽象方法
- [x] 2.3 定义 `write_session(session_id: str, data: dict)` 抽象方法
- [x] 2.4 定义 `delete_session(session_id: str)` 抽象方法
- [x] 2.5 定义 `list_sessions(limit: int)` 抽象方法
- [x] 2.6 定义 `clear_all()` 抽象方法（用于测试清理）

## 3. SQLite 数据库 Schema 实现

- [x] 3.1 创建 `app/db/migrations.py`
- [x] 3.2 定义 `schema_migrations` 表结构
- [x] 3.3 定义 `sessions` 表结构
- [x] 3.4 定义 `session_messages` 表结构
- [x] 3.5 定义 `session_turns` 表结构
- [x] 3.6 实现 `migrate(db_path: str)` 迁移函数
- [x] 3.7 实现 `get_current_version()` 版本查询函数

## 4. SQLite 存储后端实现

- [x] 4.1 创建 `app/db/sqlite_store.py`
- [x] 4.2 实现 `SQLiteStore` 类继承 `SessionStore`
- [x] 4.3 实现 `__init__(db_path: str)` 构造函数
- [x] 4.4 实现 `read_session(session_id)` 方法
- [x] 4.5 实现 `write_session(session_id, data)` 方法
- [x] 4.6 实现 `delete_session(session_id)` 方法
- [x] 4.7 实现 `list_sessions(limit)` 方法
- [x] 4.8 实现 `_ensure_tables()` 内部方法
- [x] 4.9 启用 WAL 模式支持并发读取

## 5. 现有后端提取和重构

- [x] 5.1 创建 `app/db/file_store.py`
- [x] 5.2 将 `session_state.py` 中的 File 后端逻辑提取到 `FileStore` 类
- [x] 5.3 创建 `app/db/redis_store.py`
- [x] 5.4 将 `session_state.py` 中的 Redis 后端逻辑提取到 `RedisStore` 类
- [x] 5.5 确保两个后端都实现 `SessionStore` 接口

## 6. session_state.py 适配

- [x] 6.1 修改 `_resolve_store_backend()` 支持 `sqlite` 值
- [x] 6.2 实现 `_create_store(backend: str)` 工厂函数
- [x] 6.3 修改 `_read_session_record()` 使用新的 Store 接口
- [x] 6.4 修改 `_persist_session_record()` 使用新的 Store 接口
- [x] 6.5 修改 `clear_session()` 使用新的 Store 接口
- [x] 6.6 保持所有现有函数签名不变（向后兼容）

## 7. 数据模型转换

- [x] 7.1 实现 `turn_to_message(turn: dict) -> dict` 转换函数
- [x] 7.2 实现 `message_to_turn(message: dict) -> dict` 转换函数
- [x] 7.3 确保 JSON 字段的序列化/反序列化
- [x] 7.4 处理 `cited_chunk_ids`、`entity_mentions` 等数组字段

## 8. 配置和环境变量

- [x] 8.1 支持 `SESSION_BACKEND=sqlite` 环境变量
- [x] 8.2 支持 `SESSION_SQLITE_PATH` 环境变量
- [x] 8.3 设置默认路径为 `data/session_store.db`
- [x] 8.4 在 `config.py` 中添加配置验证

## 9. 单元测试

- [x] 9.1 创建 `tests/test_sqlite_store.py`
- [x] 9.2 测试 SQLiteStore 基本 CRUD 操作
- [x] 9.3 测试数据库迁移逻辑
- [x] 9.4 测试多后端切换
- [x] 9.5 测试数据一致性
- [x] 9.6 使用临时数据库文件避免测试污染

## 10. 集成测试

- [x] 10.1 测试 `append_turn_record()` 写入 SQLite
- [x] 10.2 测试 `load_history_window()` 从 SQLite 读取
- [x] 10.3 测试 `clear_session()` 清理 SQLite 数据
- [x] 10.4 验证三种后端（file/redis/sqlite）行为一致

## 11. 调试工具（可选）

- [x] 11.1 创建 `scripts/migrate_sessions_to_sqlite.py`（JSON 到 SQLite 迁移脚本）
- [x] 11.2 创建 `scripts/query_sessions.py`（SQL 查询工具）

## 12. 文档和注释

- [x] 12.1 为 `SessionStore` 接口添加文档字符串
- [x] 12.2 为 `SQLiteStore` 添加类级文档
- [x] 12.3 更新 `docs/` 中的相关文档
- [x] 12.4 在代码中添加关键逻辑注释
