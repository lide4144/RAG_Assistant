# 前端API接口规范

## 目录

1. [接口概述](#1-接口概述)
2. [通用规范](#2-通用规范)
3. [文档转换接口](#3-文档转换接口)
4. [文档存储接口](#4-文档存储接口)
5. [文档检索与问答接口](#5-文档检索与问答接口)
6. [文档管理接口](#6-文档管理接口)
7. [系统管理接口](#7-系统管理接口)
8. [WebSocket接口](#8-websocket接口)
9. [错误码说明](#9-错误码说明)

---

## 1. 接口概述

### 1.1 基础信息

- **API版本**: v1
- **基础URL**: `https://api.example.com/v1`
- **协议**: HTTPS
- **数据格式**: JSON
- **字符编码**: UTF-8

### 1.2 认证方式

```http
Authorization: Bearer <token>
```

### 1.3 响应格式

所有接口统一返回格式：

```typescript
interface ApiResponse<T> {
  success: boolean;           // 请求是否成功
  code: number;              // 业务状态码
  message: string;           // 响应消息
  data?: T;                  // 响应数据
  timestamp: string;         // 响应时间戳 (ISO 8601)
}
```

---

## 2. 通用规范

### 2.1 HTTP状态码

| 状态码 | 说明 |
|-------|------|
| 200 | 请求成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 422 | 请求参数验证失败 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

### 2.2 业务状态码

| 代码 | 说明 |
|-----|------|
| 0 | 成功 |
| 1001 | 参数错误 |
| 1002 | 文件不存在 |
| 2001 | 文档转换失败 |
| 3001 | 文档存储失败 |
| 4001 | 检索失败 |
| 5001 | 系统错误 |

### 2.3 分页参数

```typescript
interface PaginationParams {
  page: number;      // 页码，从1开始
  page_size: number; // 每页数量，默认20，最大100
}

interface PaginationResponse<T> {
  items: T[];           // 数据列表
  total: number;        // 总数量
  page: number;         // 当前页码
  page_size: number;    // 每页数量
  total_pages: number;  // 总页数
}
```

### 2.4 通用请求头

```http
Content-Type: application/json
Accept: application/json
Authorization: Bearer <token>
X-Request-ID: <uuid>  # 可选，用于追踪请求
```

---

## 3. 文档转换接口

### 3.1 上传并转换文档

**接口**: `POST /api/documents/convert`

**说明**: 上传文档文件并转换为Markdown格式

**请求方式**: `multipart/form-data`

**请求参数**:

```typescript
interface ConvertDocumentRequest {
  file: File;                    // 文档文件 (必需)
  extract_images?: boolean;      // 是否提取图片，默认true
  extract_tables?: boolean;      // 是否提取表格，默认true
  metadata?: {                   // 预设元数据（可选）
    title?: string;
    authors?: string[];
    keywords?: string[];
    [key: string]: any;
  };
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "文档转换成功",
  "data": {
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "基于深度学习的文本分类研究",
    "authors": ["张三", "李四"],
    "word_count": 5000,
    "page_count": 12,
    "status": "completed",
    "content_preview": "# 论文标题\n\n## 摘要\n\n这是摘要内容...",
    "images_count": 5,
    "tables_count": 3,
    "sections": [
      "摘要",
      "1. 引言",
      "2. 相关工作",
      "3. 方法",
      "4. 实验",
      "5. 结论"
    ],
    "processing_time_ms": 1523.5,
    "created_at": "2024-01-15T10:30:00Z"
  },
  "timestamp": "2024-01-15T10:30:01Z"
}
```

### 3.2 批量转换文档

**接口**: `POST /api/documents/convert/batch`

**说明**: 批量上传并转换多个文档

**请求方式**: `multipart/form-data`

**请求参数**:

```typescript
interface BatchConvertRequest {
  files: File[];              // 多个文档文件
  parallel?: boolean;         // 是否并行处理，默认true
  extract_images?: boolean;
  extract_tables?: boolean;
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "批量转换完成: 3/3 成功",
  "data": {
    "task_id": "batch-550e8400-e29b-41d4-a716-446655440000",
    "total_count": 3,
    "success_count": 3,
    "failed_count": 0,
    "status": "completed",
    "documents": [
      {
        "document_id": "doc-1",
        "filename": "paper1.pdf",
        "status": "success",
        "title": "论文1"
      },
      {
        "document_id": "doc-2",
        "filename": "paper2.pdf",
        "status": "success",
        "title": "论文2"
      }
    ],
    "processing_time_ms": 4523.5,
    "created_at": "2024-01-15T10:30:00Z"
  },
  "timestamp": "2024-01-15T10:30:05Z"
}
```

### 3.3 获取转换任务状态

**接口**: `GET /api/documents/convert/status/{task_id}`

**说明**: 查询批量转换任务的进度

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "获取成功",
  "data": {
    "task_id": "batch-550e8400",
    "status": "processing",  // pending, processing, completed, failed
    "progress": 66,          // 进度百分比
    "total_count": 3,
    "completed_count": 2,
    "failed_count": 0,
    "estimated_time_remaining_seconds": 30,
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:15Z"
  },
  "timestamp": "2024-01-15T10:30:15Z"
}
```

---

## 4. 文档存储接口

### 4.1 存储文档到向量库

**接口**: `POST /api/storage/documents`

**说明**: 将转换后的文档存储到向量数据库

**请求参数**:

```typescript
interface StoreDocumentRequest {
  document_ids: string[];         // 要存储的文档ID列表
  collection_name?: string;       // 集合名称，默认"papers"
  chunking_config?: {             // 分块配置（可选）
    chunk_size?: number;          // 块大小，默认512
    chunk_overlap?: number;       // 重叠大小，默认50
    split_by?: string;            // 分割方式，默认"paragraph"
  };
  update_existing?: boolean;      // 是否更新已存在的文档，默认true
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "成功存储 2 个文档，共 45 个块",
  "data": {
    "task_id": "storage-task-123",
    "collection_name": "papers",
    "total_documents": 2,
    "success_documents": 2,
    "total_chunks": 45,
    "documents_info": [
      {
        "document_id": "doc-1",
        "chunks_count": 20,
        "success": true
      },
      {
        "document_id": "doc-2",
        "chunks_count": 25,
        "success": true
      }
    ],
    "processing_time_ms": 2500.0
  },
  "timestamp": "2024-01-15T10:35:00Z"
}
```

### 4.2 获取集合列表

**接口**: `GET /api/storage/collections`

**说明**: 获取所有向量数据库集合

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "获取成功",
  "data": {
    "collections": [
      {
        "name": "papers",
        "document_count": 150,
        "chunk_count": 3500,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-15T10:35:00Z"
      },
      {
        "name": "books",
        "document_count": 50,
        "chunk_count": 1200,
        "created_at": "2024-01-10T00:00:00Z",
        "updated_at": "2024-01-14T15:20:00Z"
      }
    ]
  },
  "timestamp": "2024-01-15T10:40:00Z"
}
```

### 4.3 创建集合

**接口**: `POST /api/storage/collections`

**说明**: 创建新的向量数据库集合

**请求参数**:

```typescript
interface CreateCollectionRequest {
  name: string;                   // 集合名称
  description?: string;           // 集合描述
  distance_metric?: string;       // 距离度量，默认"cosine"
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "集合创建成功",
  "data": {
    "name": "research_papers",
    "description": "科研论文集合",
    "distance_metric": "cosine",
    "created_at": "2024-01-15T10:45:00Z"
  },
  "timestamp": "2024-01-15T10:45:00Z"
}
```

### 4.4 删除集合

**接口**: `DELETE /api/storage/collections/{collection_name}`

**说明**: 删除指定集合及其所有文档

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "集合已删除",
  "data": {
    "collection_name": "old_papers",
    "deleted_document_count": 50,
    "deleted_chunk_count": 1200
  },
  "timestamp": "2024-01-15T10:50:00Z"
}
```

---

## 5. 文档检索与问答接口

### 5.1 智能问答

**接口**: `POST /api/query/ask`

**说明**: 基于向量数据库的RAG问答

**请求参数**:

```typescript
interface QueryRequest {
  query: string;                       // 问题文本
  collection_name?: string;            // 集合名称，默认"papers"
  retrieval_config?: {                 // 检索配置（可选）
    top_k?: number;                    // 返回块数量，默认5
    similarity_threshold?: number;     // 相似度阈值，默认0.7
    rerank?: boolean;                  // 是否重排序，默认false
  };
  llm_config?: {                       // LLM配置（可选）
    model?: string;                    // 模型名称
    temperature?: number;              // 温度，默认0.7
    max_tokens?: number;               // 最大token数
  };
  include_sources?: boolean;           // 是否包含来源，默认true
  conversation_id?: string;            // 对话ID，用于多轮对话
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "查询成功",
  "data": {
    "query_id": "query-550e8400",
    "answer": "根据检索到的论文内容，深度学习在文本分类中常用的方法包括：\n\n1. **CNN（卷积神经网络）**：通过卷积层提取文本的局部特征...\n\n2. **RNN/LSTM**：通过循环结构捕获文本的序列信息...\n\n3. **Transformer**：使用自注意力机制处理长距离依赖...",
    "sources": [
      {
        "document_id": "doc-1",
        "document_title": "基于深度学习的文本分类研究",
        "authors": ["张三", "李四"],
        "relevance_score": 0.89,
        "snippet": "深度学习方法在文本分类中表现出色...",
        "chunk_ids": ["doc-1_3", "doc-1_5"]
      }
    ],
    "confidence": 0.85,
    "retrieved_chunks_count": 5,
    "conversation_id": "conv-123",
    "processing_time_ms": 2156.8,
    "usage": {
      "prompt_tokens": 1500,
      "completion_tokens": 350,
      "total_tokens": 1850
    }
  },
  "timestamp": "2024-01-15T10:55:00Z"
}
```

### 5.2 文档检索

**接口**: `POST /api/query/search`

**说明**: 仅检索相关文档块，不生成回答

**请求参数**:

```typescript
interface SearchRequest {
  query: string;                    // 查询文本
  collection_name?: string;         // 集合名称
  top_k?: number;                   // 返回数量，默认10
  similarity_threshold?: number;    // 相似度阈值
  filter_metadata?: {               // 元数据过滤
    [key: string]: any;
  };
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "检索成功",
  "data": {
    "query": "深度学习文本分类",
    "chunks": [
      {
        "chunk_id": "doc-1_3",
        "document_id": "doc-1",
        "content": "深度学习方法在文本分类中表现出色...",
        "similarity_score": 0.89,
        "section_title": "2. 相关工作",
        "metadata": {
          "title": "基于深度学习的文本分类研究",
          "authors": ["张三", "李四"],
          "year": 2024
        }
      },
      {
        "chunk_id": "doc-2_5",
        "document_id": "doc-2",
        "content": "Transformer架构在NLP任务中...",
        "similarity_score": 0.85,
        "section_title": "3. 方法",
        "metadata": {
          "title": "Transformer模型研究",
          "authors": ["王五"]
        }
      }
    ],
    "total_results": 10,
    "processing_time_ms": 150.5
  },
  "timestamp": "2024-01-15T11:00:00Z"
}
```

### 5.3 多轮对话

**接口**: `POST /api/query/conversation`

**说明**: 创建或继续多轮对话

**请求参数**:

```typescript
interface ConversationRequest {
  message: string;                  // 当前消息
  conversation_id?: string;         // 对话ID，新建时不传
  collection_name?: string;
  retrieval_config?: {...};
  llm_config?: {...};
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "回复成功",
  "data": {
    "conversation_id": "conv-123",
    "message_id": "msg-456",
    "answer":   "关于您提到的Transformer模型...",
    "sources": [...],
    "history": [
      {
        "role": "user",
        "content": "什么是Transformer？",
        "timestamp": "2024-01-15T11:00:00Z"
      },
      {
        "role": "assistant",
        "content": "Transformer是一种神经网络架构...",
        "timestamp": "2024-01-15T11:00:05Z"
      }
    ],
    "created_at": "2024-01-15T11:00:00Z"
  },
  "timestamp": "2024-01-15T11:00:10Z"
}
```

### 5.4 获取对话历史

**接口**: `GET /api/query/conversation/{conversation_id}`

**说明**: 获取指定对话的历史记录

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "获取成功",
  "data": {
    "conversation_id": "conv-123",
    "messages": [
      {
        "message_id": "msg-1",
        "role": "user",
        "content": "什么是深度学习？",
        "timestamp": "2024-01-15T10:55:00Z"
      },
      {
        "message_id": "msg-2",
        "role": "assistant",
        "content": "深度学习是...",
        "sources": [...],
        "timestamp": "2024-01-15T10:55:05Z"
      }
    ],
    "total_messages": 4,
    "created_at": "2024-01-15T10:55:00Z",
    "updated_at": "2024-01-15T11:00:10Z"
  },
  "timestamp": "2024-01-15T11:05:00Z"
}
```

---

## 6. 文档管理接口

### 6.1 获取文档列表

**接口**: `GET /api/documents`

**说明**: 获取文档列表（支持分页和筛选）

**查询参数**:

```typescript
interface DocumentListQuery {
  page?: number;               // 页码
  page_size?: number;          // 每页数量
  collection_name?: string;    // 集合筛选
  status?: string;             // 状态筛选: all, converted, stored
  search?: string;             // 搜索关键词
  sort_by?: string;            // 排序字段: created_at, title, word_count
  order?: string;              // 排序方向: asc, desc
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "获取成功",
  "data": {
    "items": [
      {
        "document_id": "doc-1",
        "title": "基于深度学习的文本分类研究",
        "authors": ["张三", "李四"],
        "word_count": 5000,
        "page_count": 12,
        "status": "stored",
        "collections": ["papers"],
        "chunks_count": 20,
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:35:00Z"
      }
    ],
    "total": 150,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  },
  "timestamp": "2024-01-15T11:10:00Z"
}
```

### 6.2 获取文档详情

**接口**: `GET /api/documents/{document_id}`

**说明**: 获取单个文档的详细信息

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "获取成功",
  "data": {
    "document_id": "doc-1",
    "title": "基于深度学习的文本分类研究",
    "authors": ["张三", "李四"],
    "abstract": "本文提出了一种新的文本分类方法...",
    "keywords": ["深度学习", "文本分类", "NLP"],
    "word_count": 5000,
    "page_count": 12,
    "status": "stored",
    "content": "# 论文标题\n\n## 摘要\n\n这是摘要内容...",
    "sections": ["摘要", "1. 引言", "2. 相关工作"],
    "images": [
      {
        "image_id": "img-1",
        "caption": "模型架构图",
        "url": "https://cdn.example.com/images/img-1.png"
      }
    ],
    "tables": [
      {
        "table_id": "table-1",
        "caption": "实验结果对比",
        "rows": 5,
        "columns": 4
      }
    ],
    "source_info": {
      "original_filename": "paper.pdf",
      "file_type": "pdf",
      "file_size_bytes": 1024000,
      "upload_time": "2024-01-15T10:29:00Z"
    },
    "storage_info": {
      "collections": ["papers"],
      "chunks_count": 20,
      "stored_at": "2024-01-15T10:35:00Z"
    },
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:35:00Z"
  },
  "timestamp": "2024-01-15T11:15:00Z"
}
```

### 6.3 更新文档元数据

**接口**: `PATCH /api/documents/{document_id}`

**说明**: 更新文档的元数据信息

**请求参数**:

```typescript
interface UpdateDocumentRequest {
  title?: string;
  authors?: string[];
  abstract?: string;
  keywords?: string[];
  metadata?: {
    [key: string]: any;
  };
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "更新成功",
  "data": {
    "document_id": "doc-1",
    "updated_fields": ["title", "keywords"],
    "updated_at": "2024-01-15T11:20:00Z"
  },
  "timestamp": "2024-01-15T11:20:00Z"
}
```

### 6.4 删除文档

**接口**: `DELETE /api/documents/{document_id}`

**说明**: 删除指定文档（包括向量库中的数据）

**查询参数**:

```typescript
interface DeleteDocumentQuery {
  collections?: string[];  // 指定要删除的集合，不传则删除所有
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "文档已删除",
  "data": {
    "document_id": "doc-1",
    "deleted_collections": ["papers"],
    "deleted_chunks_count": 20
  },
  "timestamp": "2024-01-15T11:25:00Z"
}
```

### 6.5 批量删除文档

**接口**: `POST /api/documents/batch-delete`

**说明**: 批量删除多个文档

**请求参数**:

```typescript
interface BatchDeleteRequest {
  document_ids: string[];
  collections?: string[];
}
```

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "批量删除完成",
  "data": {
    "total_count": 5,
    "success_count": 5,
    "failed_count": 0,
    "deleted_chunks_count": 100
  },
  "timestamp": "2024-01-15T11:30:00Z"
}
```

---

## 7. 系统管理接口

### 7.1 获取系统统计信息

**接口**: `GET /api/system/stats`

**说明**: 获取系统整体统计数据

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "获取成功",
  "data": {
    "total_documents": 150,
    "total_collections": 3,
    "total_chunks": 3500,
    "storage_size_bytes": 524288000,
    "supported_file_types": ["pdf", "html", "txt", "md"],
    "available_models": {
      "embedding": [
        "paraphrase-multilingual-MiniLM-L12-v2"
      ],
      "llm": [
        "gpt-3.5-turbo",
        "gpt-4",
        "claude-3-sonnet"
      ]
    },
    "system_status": {
      "vector_db": "healthy",
      "embedding_service": "healthy",
      "llm_service": "healthy"
    },
    "uptime_seconds": 86400
  },
  "timestamp": "2024-01-15T11:35:00Z"
}
```

### 7.2 获取系统配置

**接口**: `GET /api/system/config`

**说明**: 获取当前系统配置信息

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "获取成功",
  "data": {
    "chunking": {
      "chunk_size": 512,
      "chunk_overlap": 50,
      "split_by": "paragraph"
    },
    "embedding": {
      "provider": "sentence-transformers",
      "model": "paraphrase-multilingual-MiniLM-L12-v2",
      "dimension": 384
    },
    "llm": {
      "default_provider": "openai",
      "default_model": "gpt-3.5-turbo",
      "temperature": 0.7,
      "max_tokens": 2048
    },
    "limits": {
      "max_file_size_mb": 50,
      "max_batch_size": 10,
      "rate_limit_per_minute": 60
    }
  },
  "timestamp": "2024-01-15T11:40:00Z"
}
```

### 7.3 健康检查

**接口**: `GET /api/health`

**说明**: 检查服务健康状态

**响应示例**:

```json
{
  "success": true,
  "code": 0,
  "message": "服务正常",
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "components": {
      "api": "healthy",
      "database": "healthy",
      "vector_db": "healthy",
      "embedding_service": "healthy",
      "llm_service": "healthy"
    },
    "timestamp": "2024-01-15T11:45:00Z"
  },
  "timestamp": "2024-01-15T11:45:00Z"
}
```

---

## 8. WebSocket接口

### 8.1 实时任务进度推送

**WebSocket URL**: `wss://api.example.com/v1/ws/tasks`

**说明**: 订阅任务进度更新

**连接参数**:

```typescript
interface WebSocketConnectionParams {
  token: string;      // 认证token
  task_ids?: string[]; // 订阅的任务ID列表
}
```

**消息格式**:

```typescript
// 服务端推送消息
interface TaskProgressMessage {
  type: "task_progress";
  data: {
    task_id: string;
    task_type: "convert" | "storage" | "query";
    status: "pending" | "processing" | "completed" | "failed";
    progress: number;        // 0-100
    current_step: string;
    message: string;
    timestamp: string;
  };
}

// 客户端订阅消息
interface SubscribeMessage {
  action: "subscribe";
  task_ids: string[];
}

// 客户端取消订阅
interface UnsubscribeMessage {
  action: "unsubscribe";
  task_ids: string[];
}
```

**示例**:

```javascript
// 连接WebSocket
const ws = new WebSocket('wss://api.example.com/v1/ws/tasks?token=xxx');

ws.onopen = () => {
  // 订阅任务
  ws.send(JSON.stringify({
    action: 'subscribe',
    task_ids: ['task-123', 'task-456']
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('任务进度:', message.data.progress + '%');
};
```

### 8.2 实时问答流式输出

**WebSocket URL**: `wss://api.example.com/v1/ws/query/stream`

**说明**: 流式输出问答结果（逐字返回）

**消息格式**:

```typescript
// 客户端发送查询
interface StreamQueryRequest {
  action: "query";
  data: {
    query: string;
    collection_name?: string;
    conversation_id?: string;
  };
}

// 服务端流式响应
interface StreamQueryResponse {
  type: "chunk" | "sources" | "done" | "error";
  data: {
    content?: string;         // type=chunk时的文本片段
    sources?: SourceReference[]; // type=sources时的来源信息
    error?: string;           // type=error时的错误信息
    query_id?: string;        // type=done时的查询ID
  };
}
```

**示例**:

```javascript
const ws = new WebSocket('wss://api.example.com/v1/ws/query/stream?token=xxx');

ws.onopen = () => {
  ws.send(JSON.stringify({
    action: 'query',
    data: {
      query: '深度学习在NLP中的应用？',
      collection_name: 'papers'
    }
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.type === 'chunk') {
    // 逐字显示回答
    displayAnswer(message.data.content);
  } else if (message.type === 'sources') {
    // 显示来源
    displaySources(message.data.sources);
  } else if (message.type === 'done') {
    // 查询完成
    console.log('查询完成:', message.data.query_id);
  }
};
```

---

## 9. 错误码说明

### 9.1 通用错误码

| 错误码 | 说明 | HTTP状态码 |
|-------|------|-----------|
| 0 | 成功 | 200 |
| 1000 | 未知错误 | 500 |
| 1001 | 参数错误 | 400 |
| 1002 | 文件不存在 | 404 |
| 1003 | 权限不足 | 403 |
| 1004 | 请求超时 | 408 |
| 1005 | 请求过于频繁 | 429 |

### 9.2 文档转换错误码

| 错误码 | 说明 |
|-------|------|
| 2001 | 不支持的文件类型 |
| 2002 | 文档转换失败 |
| 2003 | PDF解析错误 |
| 2004 | HTML解析错误 |
| 2005 | 编码错误 |
| 2006 | 图片提取失败 |
| 2007 | 表格提取失败 |
| 2008 | 文件过大 |
| 2009 | 文件损坏 |

### 9.3 存储错误码

| 错误码 | 说明 |
|-------|------|
| 3001 | 存储连接失败 |
| 3002 | 向量化失败 |
| 3003 | 分块失败 |
| 3004 | 文档已存在 |
| 3005 | 文档不存在 |
| 3006 | 集合不存在 |
| 3007 | 集合已存在 |
| 3008 | 存储空间不足 |

### 9.4 查询错误码

| 错误码 | 说明 |
|-------|------|
| 4001 | 检索失败 |
| 4002 | LLM API错误 |
| 4003 | LLM限流 |
| 4004 | Token超限 |
| 4005 | 无效的模型 |
| 4006 | 生成失败 |
| 4007 | 对话不存在 |
| 4008 | 查询为空 |

### 9.5 错误响应示例

```json
{
  "success": false,
  "code": 2001,
  "message": "不支持的文件类型",
  "data": {
    "error_code": "E2001",
    "error_detail": "文件类型 .docx 不支持，支持的类型: pdf, html, txt, md",
    "file_name": "document.docx",
    "supported_types": ["pdf", "html", "txt", "md"]
  },
  "timestamp": "2024-01-15T12:00:00Z"
}
```

---

## 10. 使用示例

### 10.1 完整工作流示例

```typescript
// 1. 上传并转换文档
const convertResponse = await fetch('/api/documents/convert', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer token'
  },
  body: formData
});

const { data: { document_id } } = await convertResponse.json();

// 2. 存储到向量库
await fetch('/api/storage/documents', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer token'
  },
  body: JSON.stringify({
    document_ids: [document_id],
    collection_name: 'papers'
  })
});

// 3. 智能问答
const queryResponse = await fetch('/api/query/ask', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer token'
  },
  body: JSON.stringify({
    query: '这篇论文的主要贡献是什么？',
    collection_name: 'papers',
    include_sources: true
  })
});

const { data: { answer, sources } } = await queryResponse.json();

console.log('回答:', answer);
console.log('来源:', sources);
```

### 10.2 React Hook示例

```typescript
// useDocumentQuery.ts
import { useState } from 'react';

interface QueryOptions {
  collection_name?: string;
  include_sources?: boolean;
}

export function useDocumentQuery() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const query = async (question: string, options?: QueryOptions) => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/query/ask', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify({
          query: question,
          collection_name: options?.collection_name || 'papers',
          include_sources: options?.include_sources ?? true
        })
      });
      
      const result = await response.json();
      
      if (!result.success) {
        throw new Error(result.message);
      }
      
      return result.data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  };
  
  return { query, loading, error };
}
```

---

## 11. 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| 1.0.0 | 2024-01-15 | 初始版本 |

---

## 12. 联系方式

- **技术支持**: support@example.com
- **API文档**: https://docs.example.com
- **GitHub**: https://github.com/example/rag-system