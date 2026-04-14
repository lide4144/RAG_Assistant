# SQLite Paper Store 迁移与回滚说明

本文档描述从文件产物（`papers.json`）迁移到 SQLite 论文存储的过程，以及回滚策略。

## 概述

经过 `introduce-sqlite-paper-store-and-vector-backend-abstraction` 和 `refactor-backend-for-paper-store-lifecycle` 变更后，SQLite 论文存储（`data/processed/paper_store.sqlite3`）已成为权威数据源，负责：

- 论文身份和稳定来源路径
- 论文生命周期状态
- 专题归属
- Chunk 归属
- 每篇论文的产物状态
- 当前向量后端元数据

兼容文件如 `data/processed/papers.json` 和 `data/library_topics.json` 仍然存在，但它们是派生导出文件，不应被视为权威来源。

## 迁移步骤

### 1. 自动迁移（首次启动）

系统会在首次启动时自动执行迁移：

```python
from app.paper_store import ensure_store_current

store_path = ensure_store_current(
    processed_dir=DATA_DIR / "processed",
    topics_path=DATA_DIR / "library_topics.json",
)
```

`ensure_store_current` 函数会：
1. 检查 SQLite 数据库是否存在
2. 如不存在，从 `papers.json`、`library_topics.json` 等文件导入数据
3. 修复临时路径为稳定路径（通过指纹匹配）
4. 生成兼容导出文件

### 2. 验证迁移结果

```python
from app.paper_store import list_papers

papers = list_papers(db_path=store_path, limit=100)
print(f"迁移完成，共 {len(papers)} 篇论文")

# 检查阶段状态
papers_with_stages = list_papers(
    db_path=store_path,
    limit=100,
    include_stage_statuses=True
)
for paper in papers_with_stages:
    print(f"{paper['paper_id']}: {paper['status']}")
    for stage in paper.get('stage_statuses', []):
        print(f"  - {stage['stage']}: {stage['state']}")
```

### 3. 手动触发重新同步

如需从文件产物重新同步：

```python
from app.paper_store import sync_store_from_exports

sync_store_from_exports(
    processed_dir=DATA_DIR / "processed",
    topics_path=DATA_DIR / "library_topics.json",
)
```

当修复历史 PDF 记录时，迁移优先使用：

1. 调用方提供的显式稳定路径映射
2. `data/raw/imported` 下匹配的 basename
3. `data/raw/imported` 下匹配的指纹

如果以上都不可用，原始路径将被保留，该记录应被视为需要人工审核。

## 回滚策略

### 场景 1：数据库故障时的降级

如果 SQLite 数据库损坏或不可访问，系统会自动降级到文件产物读取：

1. **检测故障**：数据库连接失败
2. **自动降级**：`load_papers()` 函数会发出 `DeprecationWarning` 并从 `papers.json` 读取
3. **恢复服务**：系统继续使用文件产物，但功能受限（无生命周期状态、无单篇重建）

### 场景 2：手动回滚到文件模式

如需完全回滚到文件模式：

```python
# 1. 从数据库导出到文件
from app.paper_store import export_store_to_compat

export_store_to_compat(
    processed_dir=DATA_DIR / "processed",
    topics_path=DATA_DIR / "library_topics.json",
)

# 2. 删除数据库文件（谨慎操作）
import os
db_path = DATA_DIR / "processed" / "paper_store.sqlite3"
os.remove(db_path)

# 3. 配置系统使用文件模式（需修改配置）
```

### 场景 3：重建数据库

如数据库损坏但文件产物完整：

```python
# 1. 删除损坏的数据库
import os
db_path = DATA_DIR / "processed" / "paper_store.sqlite3"
os.remove(db_path)

# 2. 重新同步
from app.paper_store import ensure_store_current

ensure_store_current(
    processed_dir=DATA_DIR / "processed",
    topics_path=DATA_DIR / "library_topics.json",
)
```

预期恢复顺序：

- 从导出文件重建 SQLite
- 验证论文列表和专题映射
- 验证向量后端元数据
- 通过 SQLite 支持的 API 恢复正常读取

## 双写过渡期注意事项

在迁移过渡期，系统遵循以下原则：

1. **写入顺序**：先写入 SQLite，再生成文件产物
2. **读取优先级**：优先从 SQLite 读取，文件产物仅作为兼容导出
3. **禁止并行修改**：禁止直接修改 `papers.json`，所有修改必须通过数据库访问层

## 故障诊断

### 检查数据库状态

```bash
# 查看数据库文件
ls -lh data/processed/paper_store.sqlite3

# 使用 sqlite3 CLI 查看表结构
sqlite3 data/processed/paper_store.sqlite3 ".schema"

# 查看论文数量
sqlite3 data/processed/paper_store.sqlite3 "SELECT COUNT(*) FROM papers;"

# 查看待重建论文
sqlite3 data/processed/paper_store.sqlite3 "SELECT paper_id, title, status FROM papers WHERE status='rebuild_pending';"
```

### 检查迁移日志

迁移过程中的问题会记录在应用程序日志中。常见问题：

- **临时路径无法修复**：原始文件已移动或删除
- **指纹不匹配**：文件内容已变更
- **来源 URI 冲突**：多篇论文指向同一来源

### 修复数据问题

```python
from app.paper_store import update_paper

# 手动修复论文状态
update_paper(
    paper_id="problem_paper_id",
    status="ready",
    error_message="",
    db_path=DATA_DIR / "processed" / "paper_store.sqlite3",
)
```

## API 变更

### 新增 API 端点

- `GET /api/library/papers/pending-rebuild` - 获取待重建论文列表
- `POST /api/library/papers/execute-rebuild` - 执行重建任务
- `POST /api/library/papers/{paper_id}/rebuild` - 标记单篇论文待重建
- `POST /api/library/papers/{paper_id}/retry` - 重试失败的论文

### 响应变更

论文详情现在包含生命周期状态：

```json
{
  "paper_id": "p1",
  "title": "论文标题",
  "status": "ready",
  "stage_statuses": [
    {"stage": "dedup", "state": "succeeded", "updated_at": "2026-04-11T10:00:00Z"},
    {"stage": "import", "state": "succeeded", "updated_at": "2026-04-11T10:01:00Z"},
    {"stage": "parse", "state": "succeeded", "updated_at": "2026-04-11T10:02:00Z"},
    {"stage": "clean", "state": "succeeded", "updated_at": "2026-04-11T10:03:00Z"},
    {"stage": "index", "state": "succeeded", "updated_at": "2026-04-11T10:04:00Z"},
    {"stage": "graph_build", "state": "succeeded", "updated_at": "2026-04-11T10:05:00Z"}
  ]
}
```

## 性能考虑

### 数据库索引

SQLite 数据库已为以下字段创建索引：
- `fingerprint` - 用于去重查询
- `source_uri` - 用于来源查询
- `status` - 用于状态筛选
- `imported_at` - 用于时间排序

### 分页查询

始终使用分页查询避免内存问题：

```python
papers = list_papers(db_path=store_path, limit=100, offset=0)
```

### 批量操作

对于大规模导入，使用批量插入：

```python
# 当前实现使用逐条插入
# 如需优化，可考虑使用事务批量提交
```

## Qdrant 升级路径

当前向量后端有意通过稳定的抽象暴露。未来的 `add-qdrant-vector-backend` 工作应该：

- 在相同的向量后端契约后添加新的后端实现
- 保持 `paper_id` 范围的删除和过滤语义不变
- 继续将后端元数据写入 SQLite 论文存储
- 避免仅因向量后端改变而更改 planner 或前端契约

## 联系支持

如遇到迁移问题，请检查：
1. 应用程序日志中的错误信息
2. 数据库文件权限
3. 文件产物完整性
4. 磁盘空间
