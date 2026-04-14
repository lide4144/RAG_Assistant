## 为什么

SQLite 论文主记录与生命周期状态已就绪，但后端模块（导入、目录、检索、删除/重建）尚未切换到以数据库为中心的模型。当前代码仍依赖 `papers.json`、任务报告与文件产物作为主要状态来源，这导致论文生命周期状态无法被稳定读写，单篇论文级的删除、重建与状态查询也无法正确执行。必须在后端各模块中完成从文件产物到 SQLite 权威存储的切换。

## 变更内容

- 重构 `app/ingest.py` 的导入流程，使其优先将论文主记录写入 SQLite，并按阶段更新生命周期状态（dedup→import→parse→clean→index→ready）。
- 重构 `app/library.py` 的目录与查询接口，使其从 SQLite 读取论文列表、状态与专题归属，而非从 `papers.json` 与 `library_topics.json` 拼接。
- 重构 `app/kernel_api.py` 的批任务与论文状态聚合逻辑，使其关联到单篇论文级 SQLite 状态，而非仅返回临时 `recent_items`。
- 重构删除、重建与失败恢复流程，使其基于论文生命周期状态执行编排，并更新相关派生产物归属记录。
- **BREAKING**: 后端模块不再以文件产物（`papers.json`、`library_topics.json`）作为论文存在性与状态的权威来源；这些文件将被视为兼容导出，写入由数据库状态驱动。

## 功能 (Capabilities)

### 新增功能
- `backend-paper-lifecycle-integration`: 定义后端模块与 SQLite 论文存储的集成契约，包括导入、目录查询、状态聚合与删除/重建编排。

### 修改功能
- `paper-ingestion-pipeline`: 入库流程必须将论文主记录、稳定来源信息、去重结果与阶段状态写入 SQLite，并以此驱动后续清洗、索引与图构建。
- `paper-catalog-management`: 目录查询、筛选与详情展示必须基于 SQLite 权威论文记录与生命周期状态。

## 影响

- 受影响代码包括 `app/ingest.py`、`app/library.py`、`app/kernel_api.py` 及相关导入/目录/任务链路。
- 受影响数据包括 `data/processed/papers.json`、`data/library_topics.json` 等文件产物的角色变化；它们将降级为兼容导出。
- 受影响系统边界包括本地导入、单篇论文状态查询、删除/重建流程。
- 新增内部依赖为论文域 SQLite 模式与生命周期状态模型；后端模块必须依赖数据库访问层而非直接读取文件产物。
