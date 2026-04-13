## 为什么

当前系统已经把论文视为核心业务对象，但论文身份、处理状态、专题归属、chunk 与图谱归属、索引构建结果仍分散在多个文件产物中，通过 `paper_id` 软关联维持一致性。这种方式在早期可以运行，但已经难以稳定回答“这篇论文是否已存在”“处理到哪一步”“删除或重建时应清理哪些派生产物”等核心问题。

现在引入 SQLite 作为论文域的权威存储，可以先解决论文主记录、生命周期状态与派生产物归属失真问题；同时将向量检索层抽象为可替换后端，可以先保留文件向量索引以控制复杂度，并为后续演进到 SQLite + Qdrant 保持接口与语义稳定。

## 变更内容

- 引入以 SQLite 为中心的论文存储模型，使 `paper`、阶段状态、专题归属、chunk 归属与派生产物归属具备稳定主记录与可查询关系。
- 将当前以 `papers.json`、`library_topics.json`、批处理报告等文件为主的论文目录与状态视图，迁移为由 SQLite 驱动的权威视图，并允许保留兼容性导出文件作为派生产物。
- 定义单篇论文生命周期语义，至少覆盖去重、导入、解析、清洗、索引、图构建、失败、删除与重建等状态。
- 引入向量后端抽象层，统一描述 chunk embedding 写入、检索、删除、重建与后端元信息读取等能力。
- 首个向量后端继续使用文件向量索引，以最小改动接入新的抽象层；后续新增 Qdrant 后端时，不改变上层导入、检索与论文管理语义。
- **BREAKING**: 论文域的权威事实来源将从当前多文件松耦合状态切换为 SQLite；现有文件产物不再被视为论文状态与归属关系的最终真相源。

## 功能 (Capabilities)

### 新增功能
- `paper-store-lifecycle`: 定义基于 SQLite 的论文主记录、阶段状态、专题归属、派生产物归属，以及单篇论文删除与重建语义。
- `vector-backend-abstraction`: 定义可替换的向量后端契约，要求首个文件后端与后续 Qdrant 后端共享统一的写入、查询、删除和重建接口语义。

### 修改功能
- `paper-ingestion-pipeline`: 入库流程必须将论文主记录、稳定来源信息、去重结果与阶段状态写入 SQLite，并以此驱动后续清洗、索引与图构建。
- `paper-catalog-management`: 目录查询、筛选与详情展示必须基于 SQLite 权威论文记录与生命周期状态，而不是依赖松散文件拼接。
- `library-quick-ingestion`: 批量导入任务必须能够向用户展示单篇论文级的稳定状态，并与论文生命周期存储保持一致。
- `embedding-indexing-and-cache`: embedding 索引构建与检索必须通过统一向量后端接口执行，并记录当前后端类型与可重建元信息。

## 影响

- 受影响代码包括论文导入与目录管理链路，如 `app/library.py`、`app/ingest.py`、`app/kernel_api.py`、`app/retrieve.py`、`app/qa.py` 及相关前端 Library/Pipeline 展示逻辑。
- 受影响数据包括 `data/processed/papers.json`、`data/library_topics.json`、`data/processed/paper_summary.json`、`data/processed/structure_index.json`、文件向量索引与运行报告；其中部分文件将降级为兼容性导出或可重建派生产物。
- 受影响系统边界包括本地导入、单篇论文状态查询、删除/重建流程、向量检索后端选择与未来 Qdrant 接入方式。
- 新增内部依赖为论文域 SQLite 模式与向量后端抽象层；本次不要求立即引入 Qdrant 运行时依赖，但设计必须为其接入预留稳定边界。
