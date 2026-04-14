## 1. 项目设置与依赖

- [x] 1.1 添加 `qdrant-client>=1.7.0` 到依赖
- [x] 1.2 运行 `poetry install` 安装新依赖
- [x] 1.3 创建 `app/vector_store/` 目录结构
- [x] 1.4 创建 `app/vector_store/__init__.py` 导出公共接口

## 2. 抽象基类与异常定义

- [x] 2.1 创建 `app/vector_store/base.py` 定义 `BaseVectorStore` 抽象基类
- [x] 2.2 实现抽象方法声明：`add_documents`, `delete_documents`, `update_document`, `get_document`
- [x] 2.3 实现抽象方法声明：`search`, `get_collection_stats`, `health_check`
- [x] 2.4 创建 `app/vector_store/exceptions.py` 定义 `VectorStoreConnectionError` 和 `VectorStoreTimeoutError`
- [x] 2.5 定义统一的文档数据模型 `Document` dataclass

## 3. 内存存储实现（MemoryVectorStore）

- [x] 3.1 创建 `app/vector_store/memory_store.py`
- [x] 3.2 实现 `MemoryVectorStore` 类继承 `BaseVectorStore`
- [x] 3.3 实现 `add_documents` 方法（支持批量添加）
- [x] 3.4 实现 `delete_documents` 和 `update_document` 方法
- [x] 3.5 实现 `get_document` 方法
- [x] 3.6 实现 `search` 方法（暴力相似度计算）
- [x] 3.7 实现元数据过滤逻辑（精确匹配、范围、多值）
- [x] 3.8 实现 `get_collection_stats` 方法
- [x] 3.9 实现 `health_check` 方法（始终返回 True）
- [x] 3.10 实现 `save_to_file` 和 `load_from_file` 方法（兼容现有索引格式）

## 4. Qdrant 存储实现（QdrantVectorStore）

- [x] 4.1 创建 `app/vector_store/qdrant_store.py`
- [x] 4.2 实现 `QdrantVectorStore` 类继承 `BaseVectorStore`
- [x] 4.3 实现 `__init__` 方法解析配置（host/port/url/api_key/collection_name）
- [x] 4.4 实现 `_create_client` 方法支持本地和云托管连接
- [x] 4.5 实现 `_ensure_collection` 方法自动创建集合
- [x] 4.6 实现 `add_documents` 方法（批量分批处理，默认批次100）
- [x] 4.7 实现 `delete_documents` 方法（批量分批处理）
- [x] 4.8 实现 `update_document` 和 `get_document` 方法
- [x] 4.9 实现 `search` 方法支持向量相似度搜索
- [x] 4.10 实现过滤 DSL 到 Qdrant Filter 的转换（精确匹配、范围、多值）
- [x] 4.11 实现 `get_collection_stats` 方法调用 Qdrant API
- [x] 4.12 实现 `health_check` 方法验证连接状态
- [x] 4.13 实现异常处理（连接失败、超时转换为自定义异常）
- [x] 4.14 实现 `export_to_file` 和 `import_from_file` 方法

## 5. 工厂模式与配置

- [x] 5.1 创建 `app/vector_store/factory.py` 实现 `VectorStoreFactory`
- [x] 5.2 实现工厂 `create` 方法根据配置返回对应后端实例
- [x] 5.3 在 `configs/default.yaml` 添加 `vector_store` 配置段
- [x] 5.4 配置包含：backend, host, port, collection_name, api_key, index_dir
- [x] 5.5 创建 `docker-compose.qdrant.yml` 用于本地开发

## 6. 与现有 Pipeline 集成

- [x] 6.1 识别现有代码中使用索引的位置（`app/pipeline/*.py`）
- [x] 6.2 修改索引加载逻辑，使用 `VectorStoreFactory.create()` 获取实例
- [x] 6.3 确保向后兼容：默认配置使用内存存储
- [x] 6.4 更新检索逻辑调用统一的 `search` 方法
- [x] 6.5 测试 Pipeline 正常运行（索引构建、检索、问答）

## 7. 数据迁移脚本

- [x] 7.1 创建 `scripts/migrate_to_qdrant.py` 迁移脚本
- [x] 7.2 实现从现有 JSON 索引文件读取文档和向量
- [x] 7.3 实现批量上传到 Qdrant
- [x] 7.4 添加 `--dry-run` 参数预览迁移结果
- [x] 7.5 添加 `--verify` 参数验证迁移后数据完整性
- [x] 7.6 添加幂等性检查（跳过已存在的文档）
- [x] 7.7 编写迁移脚本使用说明文档

## 8. 健康检查集成

- [x] 8.1 修改 `app/kernel_api.py` 健康检查端点
- [x] 8.2 添加 Qdrant 健康状态到 `/health/deps` 响应
- [x] 8.3 实现连接失败时的友好错误信息

## 9. 测试

- [x] 9.1 创建 `tests/test_vector_store_base.py` 测试抽象接口
- [x] 9.2 创建 `tests/test_memory_store.py` 测试内存存储实现
- [x] 9.3 创建 `tests/test_qdrant_store.py` 测试 Qdrant 存储实现（需要 mock）
- [x] 9.4 创建 `tests/test_vector_store_factory.py` 测试工厂模式
- [x] 9.5 创建 `tests/test_filter_dsl.py` 测试过滤 DSL 转换
- [x] 9.6 运行全部测试确保通过

## 10. 文档与部署

- [x] 10.1 更新 `docs/startup-guide.md` 添加 Qdrant 部署说明
- [x] 10.2 编写 `docs/qdrant-deployment.md` 部署指南
- [x] 10.3 更新 README.md 添加向量存储后端说明
- [x] 10.4 创建配置示例文件 `configs/default.qdrant.yaml`
- [x] 10.5 验证 Docker Compose 配置可以正常启动 Qdrant

## 11. 验证修复与增强

- [x] 11.1 创建 `tests/test_qdrant_store.py` 完整的 Qdrant mock 测试
- [x] 11.2 更新 `app/build_indexes.py` 支持 Qdrant 后端配置
- [x] 11.3 创建 `tests/test_qdrant_marker_integration.py` Marker + Qdrant 集成测试
- [x] 11.4 更新 `docs/marker-ingest-ops.md` 添加 Marker + Qdrant 集成说明
