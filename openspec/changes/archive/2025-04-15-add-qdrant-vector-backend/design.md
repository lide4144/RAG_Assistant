## 上下文

当前 RAG_GPT 项目的向量存储主要依赖内存中的 dict/list 结构（存储在 `data/indexes/` 目录下的 JSON 文件）。这种实现虽然简单，但随着论文库规模增长，面临以下问题：

- **内存占用**：加载 10 万+ 文档的索引时，Python 进程可能占用数 GB 内存
- **启动延迟**：每次服务启动需要加载整个索引文件
- **并发安全**：文件写入缺乏事务保护，并发操作可能导致数据损坏
- **检索性能**：暴力相似度搜索的时间复杂度为 O(n)，无法利用向量索引优化

项目已使用 `qdrant-client` 作为依赖（通过 Poetry 管理），为集成 Qdrant 后端提供了基础。

## 目标 / 非目标

**目标：**
- 设计统一的向量存储抽象层，使内存存储和 Qdrant 存储可互换使用
- 实现 QdrantVectorStore，支持完整的 CRUD 操作和相似度搜索
- 提供配置驱动的后端切换机制
- 实现批量操作以优化大数据量场景
- 提供数据迁移脚本，支持从现有文件索引迁移到 Qdrant
- 保持现有代码的向后兼容性

**非目标：**
- 支持除 Memory 和 Qdrant 之外的其他向量数据库（如 Milvus、Weaviate）
- 实现 Qdrant 的分布式集群模式（仅支持单机或云托管）
- 实时同步内存索引和 Qdrant 索引
- 支持向量量化（quantization）等高级 Qdrant 特性

## 决策

### 决策 1：使用抽象基类而非 Protocol 定义接口

**选择**：使用 `abc.ABC` 定义 `BaseVectorStore` 抽象基类。

**理由**：
- 提供显式的接口契约，子类必须实现所有抽象方法
- 支持在基类中实现通用的工具方法（如批量处理逻辑）
- 类型检查器（mypy）能更好地识别未实现的方法

**替代方案**：Python Protocol（typing.Protocol）
- 优点：更灵活，支持结构子类型
- 缺点：无法强制实现检查，不适合需要共享实现代码的场景

### 决策 2：使用工厂模式创建存储实例

**选择**：实现 `VectorStoreFactory.create(config)` 静态工厂方法。

**理由**：
- 将配置解析和实例创建逻辑集中管理
- 便于添加新的后端类型（未来扩展）
- 支持懒加载（lazy initialization）

**工厂代码结构**：
```python
class VectorStoreFactory:
    @staticmethod
    def create(config: dict) -> BaseVectorStore:
        backend = config.get("backend", "memory")
        if backend == "memory":
            return MemoryVectorStore(**config)
        elif backend == "qdrant":
            return QdrantVectorStore(**config)
        raise ValueError(f"Unknown backend: {backend}")
```

### 决策 3：统一文档数据模型

**选择**：所有存储后端使用统一的文档 Schema：
```python
{
    "doc_id": str,           # 唯一标识符
    "paper_id": str,         # 论文 ID
    "content_type": str,     # "body" | "abstract" | "title"
    "page_start": int,       # 起始页码
    "section": Optional[str], # 章节标题
    "text": str,             # 原始文本
    "clean_text": str,       # 清洗后的文本
    "embedding": List[float] # 向量（可选，搜索时传入）
}
```

**理由**：
- 确保不同后端返回的数据结构一致
- 简化上层业务逻辑（pipeline 组件无需关心后端差异）
- 便于数据迁移和备份

### 决策 4：批量操作默认批次大小为 100

**选择**：`add_documents` 和 `delete_documents` 的默认批次大小为 100。

**理由**：
- Qdrant 官方推荐单次上传不超过 100 条记录以避免超时
- 平衡网络往返次数和单次请求大小
- 可通过配置参数覆盖

### 决策 5：过滤条件使用字典 DSL

**选择**：过滤条件使用嵌套字典表示：
```python
{
    "paper_id": "abc123",           # 精确匹配
    "page_start": {"gte": 5},      # 范围查询
    "content_type": ["body", "abstract"]  # 多值匹配
}
```

**理由**：
- 直观易懂，接近 MongoDB 查询语法
- 易于序列化为 JSON（用于配置或 API）
- 可扩展支持更复杂的逻辑（AND/OR）

**Qdrant 映射**：字典 DSL 将被转换为 Qdrant 的 `Filter` 对象，使用 `FieldCondition` 和 `MatchValue`/`Range` 等。

### 决策 6：配置结构使用扁平化设计

**选择**：配置文件中 `vector_store` 段采用扁平化结构：
```yaml
vector_store:
  backend: "qdrant"
  # Qdrant 特有配置
  host: "localhost"
  port: 6333
  collection_name: "paper_chunks"
  api_key: null  # 云托管时使用
  # Memory 特有配置（预留）
  index_dir: "data/indexes"
```

**理由**：
- 配置文件简洁，不需要嵌套多层
- 使用 `backend` 字段决定哪些配置项生效
- 避免使用复杂的条件配置块

## 风险 / 权衡

**[风险] Qdrant 服务不可用导致系统故障**
- 缓解措施：
  - 启动时执行健康检查，连接失败时优雅降级到内存模式（可选配置）
  - 捕获 `VectorStoreConnectionError`，在 API 层返回 503 状态码和友好错误信息
  - 监控 Qdrant 健康状态，集成到 `/health/deps` 端点

**[风险] 数据迁移过程中断导致数据不一致**
- 缓解措施：
  - 迁移脚本使用幂等设计（支持重复执行）
  - 先验证目标集合为空或不存在，避免意外覆盖
  - 提供 `--dry-run` 模式预览迁移结果

**[风险] 网络延迟影响检索性能**
- 缓解措施：
  - Qdrant 和 Kernel 服务部署在同一网络（或同一主机）
  - 使用连接池和 keep-alive 减少连接建立开销
  - 批量操作减少网络往返次数

**[风险] 元数据过滤 DSL 过于简化，无法满足复杂查询**
- 缓解措施：
  - 初始版本支持常见过滤场景（精确匹配、范围、多值）
  - 预留扩展接口，未来支持嵌套逻辑（AND/OR/NOT）
  - 如需复杂查询，可直接使用 Qdrant 原生客户端

**[权衡] 统一接口 vs. 后端特性暴露**
- 权衡：统一接口限制了使用 Qdrant 高级特性（如向量量化、混合搜索）
- 决策：基础接口保持简洁，QdrantVectorStore 可提供额外方法（如 `hybrid_search`）供高级用户使用

**[权衡] 批量大小与实时性**
- 权衡：大批量操作提升吞吐，但延迟单个文档的可见性
- 决策：默认批次 100，同时提供 `flush()` 方法强制同步

## 迁移计划

### 阶段 1：代码集成（向后兼容）
1. 创建 `app/vector_store/` 模块和抽象基类
2. 实现 `MemoryVectorStore`（适配现有代码）
3. 实现 `QdrantVectorStore` 基础功能
4. 更新 Pipeline 组件，使用工厂获取存储实例
5. 所有现有功能保持默认使用内存存储

### 阶段 2：本地验证
1. 使用 `docker-compose.qdrant.yml` 启动本地 Qdrant
2. 修改 `configs/default.yaml` 启用 Qdrant 后端
3. 运行完整 Pipeline 验证功能正常
4. 执行性能基准测试对比内存存储

### 阶段 3：数据迁移（可选）
1. 备份现有索引文件
2. 运行 `scripts/migrate_to_qdrant.py` 迁移数据
3. 验证迁移后的数据完整性（文档数、向量对比）
4. 切换配置启用 Qdrant 生产环境

### 阶段 4：回滚策略
- **回滚触发**：Qdrant 服务故障或性能不达标
- **回滚步骤**：
  1. 修改配置 `vector_store.backend: "memory"`
  2. 重启 Kernel 服务
  3. 重新运行索引流程生成内存索引（或从备份恢复文件索引）

## 待解决问题

1. **Qdrant 版本要求**：确定最低支持的 Qdrant 服务器版本（目标 v1.7+）
2. **向量维度配置**：集合创建时需要指定向量维度，应从配置读取还是从首条文档推断？
3. **距离度量**：使用 Cosine 还是 Euclidean？需与现有嵌入模型输出一致
4. **过期数据清理**：是否实现 TTL 或手动清理机制？
