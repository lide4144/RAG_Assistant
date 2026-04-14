# Qdrant 向量存储部署指南

本文档详细介绍如何在 RAG GPT 项目中部署和使用 Qdrant 向量数据库。

## 目录

- [概述](#概述)
- [部署方式](#部署方式)
- [配置说明](#配置说明)
- [数据迁移](#数据迁移)
- [性能优化](#性能优化)
- [故障排除](#故障排除)

## 概述

Qdrant 是一个开源向量数据库，提供高性能的向量相似度搜索。相比默认的内存存储，Qdrant 具有以下优势：

- **扩展性**：支持大规模数据（百万级文档）
- **持久化**：数据持久存储，服务重启不丢失
- **高性能**：基于 HNSW 算法的近似最近邻搜索
- **混合搜索**：支持向量相似度 + 元数据过滤

## 部署方式

### 方式一：本地 Docker 部署（推荐开发环境）

```bash
# 启动 Qdrant
docker-compose -f docker-compose.qdrant.yml up -d

# 查看日志
docker-compose -f docker-compose.qdrant.yml logs -f

# 停止 Qdrant
docker-compose -f docker-compose.qdrant.yml down
```

默认端口：
- REST API: `6333`
- gRPC: `6334`

### 方式二：云托管（Qdrant Cloud）

1. 注册 [Qdrant Cloud](https://cloud.qdrant.io/)
2. 创建集群
3. 获取 API Key 和 URL

### 方式三：Kubernetes 部署

参考 Qdrant 官方 Helm Chart：

```bash
helm repo add qdrant https://qdrant.github.io/qdrant-helm
helm install qdrant qdrant/qdrant
```

## 配置说明

### 基础配置

在 `configs/default.yaml` 中添加：

```yaml
vector_store:
  backend: qdrant  # 可选: memory, qdrant
  
  # 通用配置
  collection_name: paper_chunks
  vector_size: 1024
  distance: COSINE  # COSINE, EUCLID, DOT
  batch_size: 100
  timeout: 60
  
  # 本地连接配置
  host: localhost
  port: 6333
  
  # 云托管配置（覆盖 host/port）
  # url: https://your-cluster.cloud.qdrant.io
  # api_key: ${QDRANT_API_KEY}
```

### 环境变量

可通过环境变量覆盖配置：

```bash
# 基本连接
export VECTOR_STORE_BACKEND=qdrant
export QDRANT_HOST=localhost
export QDRANT_PORT=6333

# 云托管
export QDRANT_URL=https://your-cluster.cloud.qdrant.io
export QDRANT_API_KEY=your-api-key

# 集合配置
export QDRANT_COLLECTION=paper_chunks
export QDRANT_VECTOR_SIZE=1024
```

### 距离度量选择

| 距离度量 | 适用场景 | 说明 |
|---------|---------|------|
| `COSINE` | 语义相似度（推荐） | 适用于归一化后的嵌入向量 |
| `EUCLID` | 原始向量空间 | 适用于未归一化的向量 |
| `DOT` | 快速近似 | 适用于已归一化的向量 |

大多数嵌入模型（如 BGE、OpenAI）输出归一化向量，建议使用 `COSINE`。

## 数据迁移

### 从内存索引迁移

```bash
# 1. 预览迁移（不实际上传）
python scripts/migrate_to_qdrant.py --dry-run

# 2. 执行迁移
python scripts/migrate_to_qdrant.py

# 3. 迁移并验证数据完整性
python scripts/migrate_to_qdrant.py --verify

# 4. 强制重新上传（覆盖已有数据）
python scripts/migrate_to_qdrant.py --no-skip-existing
```

### 命令行参数

```bash
python scripts/migrate_to_qdrant.py \
  --input data/indexes/vec_index_embed.json \
  --host localhost \
  --port 6333 \
  --collection paper_chunks \
  --dry-run
```

| 参数 | 说明 | 默认值 |
|-----|------|--------|
| `--input` | 输入索引文件 | `data/indexes/vec_index_embed.json` |
| `--host` | Qdrant 主机 | `localhost` |
| `--port` | Qdrant 端口 | `6333` |
| `--url` | Qdrant Cloud URL | - |
| `--api-key` | API Key | - |
| `--collection` | 集合名称 | `paper_chunks` |
| `--vector-size` | 向量维度 | `1024` |
| `--dry-run` | 预览模式 | - |
| `--verify` | 验证迁移 | - |
| `--no-skip-existing` | 覆盖已有数据 | - |

## 性能优化

### 批处理大小

调整 `batch_size` 参数：

```yaml
vector_store:
  batch_size: 100  # 默认，可根据网络延迟调整
```

- 本地部署：`100-500`
- 云托管：`50-100`（考虑网络延迟）

### 连接超时

```yaml
vector_store:
  timeout: 60  # 秒
```

大规模迁移时可增加超时时间。

### 向量量化（高级）

对于生产环境的大规模化，可在 Qdrant 中启用量化：

```python
# 创建集合时启用量化
client.create_collection(
    collection_name="paper_chunks",
    vectors_config=models.VectorParams(
        size=1024,
        distance=models.Distance.COSINE,
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(
                type=models.ScalarType.INT8,
                quantile=0.99,
            ),
        ),
    ),
)
```

量化可减少内存占用约 75%，对精度影响较小。

## 故障排除

### 连接失败

```
Failed to connect to Qdrant: Connection refused
```

**解决方案：**
1. 检查 Qdrant 是否运行：`docker-compose -f docker-compose.qdrant.yml ps`
2. 检查端口是否被占用：`lsof -i :6333`
3. 检查防火墙设置

### 集合创建失败

```
Failed to ensure collection: Collection already exists with different parameters
```

**解决方案：**
1. 删除现有集合并重建：
   ```bash
   curl -X DELETE http://localhost:6333/collections/paper_chunks
   ```
2. 或使用不同的集合名称

### 上传超时

```
VectorStoreTimeoutError: Failed to add documents
```

**解决方案：**
1. 减小 `batch_size`
2. 增加 `timeout`
3. 检查 Qdrant 资源（CPU/内存）

### 健康检查失败

访问 `/health/deps` 查看状态：

```json
{
  "vector_store": {
    "status": "error",
    "backend": "qdrant",
    "reason": "connection_failed"
  }
}
```

**解决方案：**
1. 检查 Qdrant 服务状态
2. 检查配置中的 host/port 是否正确
3. 检查网络连通性：`curl http://localhost:6333/healthz`

### 维度不匹配

```
Vector dimension mismatch: expected 1024, got 768
```

**解决方案：**
1. 删除集合并重建（注意：会丢失数据）
2. 修改配置中的 `vector_size` 与实际嵌入模型输出维度一致

## 监控与维护

### 查看集合统计

```bash
curl http://localhost:6333/collections/paper_chunks | jq
```

### 备份与恢复

```python
from app.vector_store import VectorStoreFactory

# 导出
store = VectorStoreFactory.create({"backend": "qdrant", ...})
store.export_to_file("backup.json")

# 导入
store.import_from_file("backup.json")
```

### 日志监控

```bash
# Qdrant 日志
docker-compose -f docker-compose.qdrant.yml logs -f

# 应用日志（启用 Qdrant 后）
tail -f logs/kernel.log | grep -i qdrant
```

## 回滚到内存存储

如需回滚：

1. 修改配置：`backend: memory`
2. 重启 Kernel 服务
3. 重新构建索引（如有需要）

```yaml
vector_store:
  backend: memory
  index_dir: data/indexes
```

## 参考

- [Qdrant 官方文档](https://qdrant.tech/documentation/)
- [Qdrant Cloud](https://cloud.qdrant.io/)
- [向量相似度度量](https://qdrant.tech/documentation/concepts/search/#metrics)
