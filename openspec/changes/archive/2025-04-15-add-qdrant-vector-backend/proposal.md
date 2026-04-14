## 为什么

当前项目仅支持内存或文件存储的向量索引（通过 Python 的 dict/list 结构），这在生产环境面临以下挑战：
- **扩展性问题**：随着论文库增长，内存索引占用大量 RAM，无法水平扩展
- **持久化缺失**：文件存储的索引需要手动管理，缺乏事务保证和自动备份
- **检索性能**：大规模索引（>10万文档）时，暴力相似度搜索性能下降明显

Qdrant 是一个开源向量数据库，提供高性能的向量检索、混合搜索（向量+元数据过滤）以及分布式部署能力。添加 Qdrant 后端将显著提升系统的生产可用性和可扩展性。

## 变更内容

1. **新增 Qdrant 向量存储后端**
   - 创建 `QdrantVectorStore` 类，实现统一的向量存储接口
   - 支持文档的增删改查（CRUD）操作
   - 支持基于 metadata 的过滤搜索

2. **向量存储抽象层**
   - 定义统一的 `VectorStore` 接口/基类
   - 将现有内存索引实现适配为新接口
   - 通过配置切换不同后端（memory / qdrant）

3. **配置与部署支持**
   - 在 `default.yaml` 中添加 Qdrant 连接配置（host, port, collection_name, api_key）
   - 提供 Docker Compose 配置便于本地开发
   - 支持云托管 Qdrant（Qdrant Cloud）的 API key 认证

4. **数据迁移工具**
   - 提供脚本将现有文件索引迁移到 Qdrant
   - 支持从 Qdrant 导出备份

## 功能 (Capabilities)

### 新增功能
- `qdrant-vector-store`: Qdrant 向量存储后端实现，包含连接管理、集合管理、文档 CRUD、向量搜索、元数据过滤
- `vector-store-interface`: 统一的向量存储抽象接口，使不同的存储后端可插拔

### 修改功能
- 无（现有内存索引将独立存在，保持向后兼容）

## 影响

### 代码变更
- **新增文件**: 
  - `app/vector_store/base.py` - 抽象基类
  - `app/vector_store/qdrant_store.py` - Qdrant 实现
  - `app/vector_store/memory_store.py` - 内存实现（迁移现有代码）
  - `app/vector_store/__init__.py` - 工厂函数
  - `scripts/migrate_to_qdrant.py` - 数据迁移脚本

- **修改文件**:
  - `configs/default.yaml` - 添加 vector_store 配置段
  - `app/pipeline/*.py` - 使用新的向量存储工厂获取实例

### 依赖变更
- **新增依赖**: `qdrant-client>=1.7.0`

### API 变更
- **无破坏性变更**：现有 API 保持兼容，仅内部实现变化
- 配置文件中新增 `vector_store` 配置段（可选，默认保持内存模式）

### 部署影响
- 默认保持现有行为（内存存储），不强制引入 Qdrant 依赖
- 启用 Qdrant 需要额外部署 Qdrant 服务（提供 Docker Compose 示例）

### 性能影响
- **正向**：大规模索引下查询延迟从 O(n) 降至 O(log n)
- **存储**：减少 Python 进程内存占用
- **网络**：引入 Qdrant 服务调用开销（通常 <10ms）
