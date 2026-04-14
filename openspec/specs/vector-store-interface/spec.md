## Purpose

Define the unified vector store interface that supports multiple backend implementations (memory and Qdrant).

## Requirements

### Requirement: 向量存储必须提供统一的 CRUD 接口
所有向量存储后端必须实现统一的接口，支持文档的增删改查操作。

#### Scenario: 添加文档到向量存储
- **When** 调用 `add_documents(docs)` 方法传入文档列表
- **Then** 系统必须将文档存储到后端并返回文档 ID 列表

#### Scenario: 从向量存储删除文档
- **When** 调用 `delete_documents(doc_ids)` 方法传入文档 ID 列表
- **Then** 系统必须从后端删除指定文档

#### Scenario: 更新向量存储中的文档
- **When** 调用 `update_document(doc_id, doc)` 方法
- **Then** 系统必须更新指定 ID 的文档内容

#### Scenario: 获取文档详情
- **When** 调用 `get_document(doc_id)` 方法
- **Then** 系统必须返回指定 ID 的文档内容

### Requirement: 向量存储必须支持相似度搜索
所有向量存储后端必须支持基于向量相似度的文档检索。

#### Scenario: 执行相似度搜索
- **When** 调用 `search(query_vector, top_k, filters)` 方法
- **Then** 系统必须返回与查询向量最相似的 top_k 个文档及其相似度分数

#### Scenario: 带过滤条件的搜索
- **When** 调用 `search(query_vector, top_k, filters)` 方法并传入过滤条件
- **Then** 系统必须仅返回满足过滤条件的相似文档

### Requirement: 向量存储必须支持元数据过滤
搜索操作必须支持基于文档元数据的过滤。

#### Scenario: 按元数据字段过滤
- **When** 传入形如 `{"paper_id": "abc123"}` 的过滤条件
- **Then** 系统必须只返回 `paper_id` 等于 "abc123" 的文档

#### Scenario: 复合过滤条件
- **When** 传入包含多个条件的过滤表达式
- **Then** 系统必须只返回满足所有条件的文档

### Requirement: 向量存储必须提供统计信息接口
向量存储必须提供获取集合统计信息的能力。

#### Scenario: 获取集合统计信息
- **When** 调用 `get_collection_stats()` 方法
- **Then** 系统必须返回文档总数、向量维度等统计信息

### Requirement: 向量存储必须支持健康检查
向量存储必须提供健康状态检查接口。

#### Scenario: 检查存储后端健康状态
- **When** 调用 `health_check()` 方法
- **Then** 系统必须返回布尔值表示后端连接是否正常

### Requirement: 向量存储工厂必须支持配置驱动的实例化
系统必须通过工厂模式根据配置创建对应的后端实例。

#### Scenario: 通过配置创建内存存储实例
- **When** 配置文件中 `vector_store.backend` 设置为 "memory"
- **Then** 工厂必须返回 `MemoryVectorStore` 实例

#### Scenario: 通过配置创建 Qdrant 存储实例
- **When** 配置文件中 `vector_store.backend` 设置为 "qdrant"
- **Then** 工厂必须返回 `QdrantVectorStore` 实例
