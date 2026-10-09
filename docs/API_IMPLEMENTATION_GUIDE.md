# API实施指南 - 后端开发说明

## 目录

1. [概述](#1-概述)
2. [技术栈选型](#2-技术栈选型)
3. [项目结构](#3-项目结构)
4. [实施步骤](#4-实施步骤)
5. [核心代码示例](#5-核心代码示例)
6. [部署配置](#6-部署配置)

---

## 1. 概述

### 1.1 现状分析

**当前系统架构**:
- ✅ 已有完整的Python业务逻辑模块（转换、存储、查询）
- ✅ 已有标准化的数据模型定义（Pydantic schemas）
- ❌ **缺少HTTP API服务层**
- ❌ 缺少文件上传处理
- ❌ 缺少身份认证和权限管理
- ❌ 缺少任务队列和异步处理

**需要实施的内容**:

```
┌─────────────────────────────────────────────────────┐
│                   前端应用                            │
│              (按FRONTEND_API_SPECIFICATION开发)      │
└────────────────────┬────────────────────────────────┘
                     │ HTTP/WebSocket
                     ▼
┌─────────────────────────────────────────────────────┐
│              API服务层 (需要开发)                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  FastAPI应用 + 路由 + 中间件                  │   │
│  └──────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────┘
                     │ 调用
                     ▼
┌─────────────────────────────────────────────────────┐
│            业务逻辑层 (已存在)                        │
│  ┌──────────────────────────────────────────────┐   │
│  │  src/converter/service.py                    │   │
│  │  src/storage/service.py                      │   │
│  │  src/query/* (需要新建)                       │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 2. 技术栈选型

### 2.1 推荐技术栈

| 组件 | 技术选型 | 说明 |
|-----|---------|------|
| **Web框架** | FastAPI | 高性能、自动生成OpenAPI文档、原生支持异步 |
| **任务队列** | Celery + Redis | 处理长时间任务（文档转换、向量化） |
| **文件存储** | MinIO / S3 | 存储上传的原始文件和图片 |
| **数据库** | PostgreSQL | 存储文档元数据、任务状态、用户信息 |
| **认证** | JWT | 基于Token的身份认证 |
| **WebSocket** | FastAPI WebSocket | 实时推送任务进度 |
| **API文档** | Swagger/ReDoc | FastAPI自动生成 |

### 2.2 依赖包清单

```txt
# requirements-api.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6      # 文件上传
celery==5.3.4                # 任务队列
redis==5.0.1                 # 缓存和消息队列
sqlalchemy==2.0.25           # ORM
alembic==1.13.1              # 数据库迁移
python-jose[cryptography]==3.3.0  # JWT
passlib[bcrypt]==1.7.4       # 密码加密
python-dotenv==1.0.0         # 环境变量
aiofiles==23.2.1             # 异步文件操作
websockets==12.0             # WebSocket支持
```

---

## 3. 项目结构

### 3.1 新增目录结构

```
RAG_System/
├── api/                          # 新建：API服务层
│   ├── __init__.py
│   ├── main.py                   # FastAPI应用入口
│   ├── dependencies.py           # 依赖注入
│   ├── config.py                 # API配置
│   │
│   ├── routes/                   # 路由模块
│   │   ├── __init__.py
│   │   ├── documents.py          # 文档转换接口
│   │   ├── storage.py            # 存储接口
│   │   ├── query.py              # 查询问答接口
│   │   ├── system.py             # 系统管理接口
│   │   └── websocket.py          # WebSocket接口
│   │
│   ├── models/                   # API数据模型（扩展）
│   │   ├── __init__.py
│   │   ├── requests.py           # 请求模型
│   │   ├── responses.py          # 响应模型
│   │   └── database.py           # 数据库模型
│   │
│   ├── services/                 # 业务服务封装
│   │   ├── __init__.py
│   │   ├── document_service.py   # 文档服务
│   │   ├── storage_service.py    # 存储服务
│   │   ├── query_service.py      # 查询服务
│   │   └── task_service.py       # 任务管理服务
│   │
│   ├── middleware/               # 中间件
│   │   ├── __init__.py
│   │   ├── auth.py              # 认证中间件
│   │   ├── cors.py              # CORS配置
│   │   └── logging.py           # 日志中间件
│   │
│   ├── tasks/                    # Celery任务
│   │   ├── __init__.py
│   │   ├── celery_app.py        # Celery配置
│   │   ├── convert_tasks.py     # 转换任务
│   │   └── storage_tasks.py     # 存储任务
│   │
│   └── utils/                    # API工具函数
│       ├── __init__.py
│       ├── file_handler.py      # 文件处理
│       ├── response_builder.py  # 响应构建器
│       └── validators.py        # 验证器
│
├── database/                     # 新建：数据库相关
│   ├── migrations/              # Alembic迁移脚本
│   └── init.sql                 # 初始化SQL
│
├── uploads/                      # 新建：文件上传目录
│   ├── documents/               # 原始文档
│   └── temp/                    # 临时文件
│
└── src/                         # 现有：业务逻辑层（保持不变）
    ├── converter/
    ├── storage/
    ├── query/                   # 需要新建RAG查询模块
    └── models/
```

---

## 4. 实施步骤

### 步骤1: 创建FastAPI应用入口

**文件**: `api/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import documents, storage, query, system
from api.middleware.logging import setup_logging
import logging

# 创建FastAPI应用
app = FastAPI(
    title="论文资源管理系统API",
    description="RAG System REST API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需要指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置日志
setup_logging()
logger = logging.getLogger(__name__)

# 注册路由
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
app.include_router(storage.router, prefix="/api/v1", tags=["storage"])
app.include_router(query.router, prefix="/api/v1", tags=["query"])
app.include_router(system.router, prefix="/api/v1", tags=["system"])

@app.on_event("startup")
async def startup_event():
    logger.info("API服务启动")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("API服务关闭")

@app.get("/api/health")
async def health_check():
    return {
        "success": True,
        "code": 0,
        "message": "服务正常",
        "data": {
            "status": "healthy",
            "version": "1.0.0"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 步骤2: 创建文档转换路由

**文件**: `api/routes/documents.py`

```python
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import List, Optional
import uuid
from datetime import datetime

from api.models.responses import ApiResponse
from api.services.document_service import DocumentService
from api.tasks.convert_tasks import convert_document_task

router = APIRouter()
document_service = DocumentService()

@router.post("/documents/convert")
async def convert_document(
    file: UploadFile = File(...),
    extract_images: bool = Form(True),
    extract_tables: bool = Form(True),
    background_tasks: BackgroundTasks = None
):
    """
    上传并转换文档
    
    对应前端API: POST /api/documents/convert
    """
    try:
        # 验证文件类型
        if not document_service.is_supported_file(file.filename):
            return ApiResponse(
                success=False,
                code=2001,
                message="不支持的文件类型",
                data={
                    "file_name": file.filename,
                    "supported_types": ["pdf", "html", "txt", "md"]
                }
            )
        
        # 保存上传的文件
        file_path = await document_service.save_uploaded_file(file)
        
        # 对于大文件，使用后台任务异步处理
        file_size = await document_service.get_file_size(file_path)
        
        if file_size > 5 * 1024 * 1024:  # 大于5MB
            # 创建任务
            task_id = str(uuid.uuid4())
            convert_document_task.delay(
                task_id=task_id,
                file_path=file_path,
                extract_images=extract_images,
                extract_tables=extract_tables
            )
            
            return ApiResponse(
                success=True,
                code=0,
                message="文档已提交转换，请通过task_id查询进度",
                data={
                    "task_id": task_id,
                    "status": "pending"
                }
            )
        
        # 小文件同步处理
        result = await document_service.convert_document_sync(
            file_path=file_path,
            extract_images=extract_images,
            extract_tables=extract_tables
        )
        
        return ApiResponse(
            success=True,
            code=0,
            message="文档转换成功",
            data=result
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/convert/batch")
async def convert_batch(
    files: List[UploadFile] = File(...),
    parallel: bool = Form(True),
    extract_images: bool = Form(True),
    extract_tables: bool = Form(True)
):
    """
    批量转换文档
    
    对应前端API: POST /api/documents/convert/batch
    """
    try:
        # 创建批量任务
        task_id = f"batch-{uuid.uuid4()}"
        
        # 保存所有文件
        file_paths = []
        for file in files:
            file_path = await document_service.save_uploaded_file(file)
            file_paths.append(file_path)
        
        # 提交到任务队列
        from api.tasks.convert_tasks import convert_batch_task
        convert_batch_task.delay(
            task_id=task_id,
            file_paths=file_paths,
            parallel=parallel,
            extract_images=extract_images,
            extract_tables=extract_tables
        )
        
        return ApiResponse(
            success=True,
            code=0,
            message=f"批量转换任务已创建: {len(files)}个文件",
            data={
                "task_id": task_id,
                "total_count": len(files),
                "status": "pending"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/convert/status/{task_id}")
async def get_convert_status(task_id: str):
    """
    查询转换任务状态
    
    对应前端API: GET /api/documents/convert/status/{task_id}
    """
    try:
        status = await document_service.get_task_status(task_id)
        
        if not status:
            return ApiResponse(
                success=False,
                code=1002,
                message="任务不存在"
            )
        
        return ApiResponse(
            success=True,
            code=0,
            message="获取成功",
            data=status
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 步骤3: 创建文档服务层

**文件**: `api/services/document_service.py`

```python
from pathlib import Path
from typing import Optional
import aiofiles
import uuid
from datetime import datetime

from src.converter.service import DocumentConverterService
from src.models.schemas import DocumentInput, ConversionResult

class DocumentService:
    """
    文档服务 - 封装业务逻辑层，提供给API路由使用
    """
    
    def __init__(self):
        # 复用现有的转换服务
        self.converter_service = DocumentConverterService()
        self.upload_dir = Path("uploads/documents")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    def is_supported_file(self, filename: str) -> bool:
        """检查文件类型是否支持"""
        file_path = Path(filename)
        return self.converter_service.is_supported(file_path)
    
    async def save_uploaded_file(self, file) -> str:
        """
        保存上传的文件
        
        Args:
            file: UploadFile对象
        
        Returns:
            保存的文件路径
        """
        # 生成唯一文件名
        file_ext = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = self.upload_dir / unique_filename
        
        # 异步保存文件
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        return str(file_path)
    
    async def get_file_size(self, file_path: str) -> int:
        """获取文件大小（字节）"""
        return Path(file_path).stat().st_size
    
    async def convert_document_sync(
        self,
        file_path: str,
        extract_images: bool = True,
        extract_tables: bool = True
    ) -> dict:
        """
        同步转换文档（用于小文件）
        
        调用现有的转换服务
        """
        # 创建输入对象
        doc_input = DocumentInput(
            file_path=file_path,
            extract_images=extract_images,
            
            extract_tables=extract_tables
        )
        
        # 调用现有的转换服务
        result: ConversionResult = self.converter_service.convert_document(doc_input)
        
        if not result.success:
            raise Exception(result.error_details or result.message)
        
        # 转换为API响应格式
        doc = result.document
        return {
            "document_id": doc.document_id,
            "title": doc.metadata.title,
            "authors": doc.metadata.authors,
            "word_count": doc.word_count,
            "page_count": doc.page_count,
            "status": "completed",
            "content_preview": doc.content[:500] if doc.content else "",
            "images_count": len(doc.images) if doc.images else 0,
            "tables_count": len(doc.tables) if doc.tables else 0,
            "sections": doc.sections,
            "processing_time_ms": result.processing_time_ms,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
    
    async def get_task_status(self, task_id: str) -> Optional[dict]:
        """
        获取任务状态
        
        从Redis或数据库中查询任务状态
        """
        # TODO: 实现任务状态查询
        # 这里需要配合Celery任务和Redis/数据库
        pass
```

### 步骤4: 创建Celery任务

**文件**: `api/tasks/celery_app.py`

```python
from celery import Celery

celery_app = Celery(
    "rag_system",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
    include=[
        "api.tasks.convert_tasks",
        "api.tasks.storage_tasks"
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
```

**文件**: `api/tasks/convert_tasks.py`

```python
from celery import Task
from api.tasks.celery_app import celery_app
from src.converter.service import DocumentConverterService
from src.models.schemas import DocumentInput

@celery_app.task(bind=True)
def convert_document_task(
    self: Task,
    task_id: str,
    file_path: str,
    extract_images: bool = True,
    extract_tables: bool = True
):
    """
    异步转换文档任务
    """
    try:
        # 更新任务状态
        self.update_state(
            state="PROCESSING",
            meta={"progress": 0, "status": "开始转换"}
        )
        
        # 执行转换
        converter_service = DocumentConverterService()
        doc_input = DocumentInput(
            file_path=file_path,
            extract_images=extract_images,
            extract_tables=extract_tables
        )
        
        result = converter_service.convert_document(doc_input)
        
        if result.success:
            return {
                "status": "completed",
                "document_id": result.document.document_id,
                "task_id": task_id
            }
        else:
            raise Exception(result.error_details)
            
    except Exception as e:
        self.update_state(
            state="FAILURE",
            meta={"error": str(e)}
        )
        raise
```

### 步骤5: 创建存储路由

**文件**: `api/routes/storage.py`

```python
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from api.models.responses import ApiResponse
from api.services.storage_service import StorageService

router = APIRouter()
storage_service = StorageService()

class StoreDocumentRequest(BaseModel):
    document_ids: List[str]
    collection_name: Optional[str] = "papers"
    chunking_config: Optional[dict] = None
    update_existing: Optional[bool] = True

@router.post("/storage/documents")
async def store_documents(request: StoreDocumentRequest):
    """
    存储文档到向量库
    
    对应前端API: POST /api/storage/documents
    """
    try:
        result = await storage_service.store_documents(
            document_ids=request.document_ids,
            collection_name=request.collection_name,
            chunking_config=request.chunking_config,
            update_existing=request.update_existing
        )
        
        return ApiResponse(
            success=True,
            code=0,
            message=f"成功存储 {result['total_documents']} 个文档",
            data=result
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/storage/collections")
async def get_collections():
    """
    获取集合列表
    
    对应前端API: GET /api/storage/collections
    """
    try:
        collections = await storage_service.get_collections()
        
        return ApiResponse(
            success=True,
            code=0,
            message="获取成功",
            data={"collections": collections}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 步骤6: 创建查询路由

**文件**: `api/routes/query.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from api.models.responses import ApiResponse
from api.services.query_service import QueryService

router = APIRouter()
query_service = QueryService()

class QueryRequest(BaseModel):
    query: str
    collection_name: Optional[str] = "papers"
    retrieval_config: Optional[dict] = None
    llm_config: Optional[dict] = None
    include_sources: Optional[bool] = True
    conversation_id: Optional[str] = None

@router.post("/query/ask")
async def ask_question(request: QueryRequest):
    """
    智能问答
    
    对应前端API: POST /api/query/ask
    """
    try:
        result = await query_service.query(
            query=request.query,
            collection_name=request.collection_name,
            retrieval_config=request.retrieval_config,
            llm_config=request.llm_config,
            include_sources=request.include_sources,
            conversation_id=request.conversation_id
        )
        
        return ApiResponse(
            success=True,
            code=0,
            message="查询成功",
            data=result
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 5. 核心代码示例

### 5.1 统一响应构建器

**文件**: `api/utils/response_builder.py`

```python
from typing import Any, Optional
from datetime import datetime

class ApiResponse:
    """统一API响应格式"""
    
    def __init__(
        self,
        success: bool,
        code: int,
        message: str,
        data: Optional[Any] = None,
        timestamp: Optional[str] = None
    ):
        self.success = success
        self.code = code
        self.message = message
        self.data = data
        self.timestamp = timestamp or datetime.utcnow().isoformat() + "Z"
    
    def dict(self):
        return {
            "success": self.success,
            "code": self.code,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp
        }
```

### 5.2 文件上传处理器

**文件**: `api/utils/file_handler.py`

```python
import aiofiles
from pathlib import Path
from typing import BinaryIO
import uuid

class FileHandler:
    """文件处理工具"""
    
    @staticmethod
    async def save_upload_file(
        file: BinaryIO,
        destination: Path
    ) -> Path:
        """异步保存上传文件"""
        async with aiofiles.open(destination, 'wb') as f:
            content = await file.read()
            await f.write(content)
        return destination
    
    @staticmethod
    def generate_unique_filename(original_filename: str) -> str:
        """生成唯一文件名"""
        ext = Path(original_filename).suffix
        return f"{uuid.uuid4()}{ext}"
```

---

## 6. 部署配置

### 6.1 启动脚本

**文件**: `scripts/start_api.sh`

```bash
#!/bin/bash

# 启动FastAPI应用
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 生产环境使用
# uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6.2 启动Celery Worker

**文件**: `scripts/start_celery.sh`

```bash
#!/bin/bash

# 启动Celery worker
celery -A api.tasks.celery_app worker --loglevel=info --concurrency=4

# 启动Celery beat（定时任务）
# celery -A api.tasks.celery_app beat --loglevel=info
```

### 6.3 Docker Compose配置

**文件**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  # FastAPI服务
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./uploads:/app/uploads
      - ./data:/app/data
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/ragdb
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

  # Celery Worker
  celery:
    build: .
    command: celery -A api.tasks.celery_app worker --loglevel=info
    volumes:
      - ./uploads:/app/uploads
      - ./data:/app/data
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  # PostgreSQL
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=ragdb
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

---

## 7. 总结

### 7.1 实施清单

- [ ] **步骤1**: 安装依赖包（FastAPI、Celery等）
- [ ] **步骤2**: 创建API目录结构
- [ ] **步骤3**: 实现FastAPI应用入口（`api/main.py`）
- [ ] **步骤4**: 实现文档转换路由（`api/routes/documents.py`）
- [ ] **步骤5**: 实现存储路由（`api/routes/storage.py`）
- [ ] **步骤6**: 实现查询路由（`api/routes/query.py`）
- [ ] **步骤7**: 创建服务层封装（`api/services/`）
- [ ] **步骤8**: 配置Celery任务队列
- [ ] **步骤9**: 实现WebSocket接口
- [ ] **步骤10**: 添加身份认证和权限控制
- [ ] **步骤11**: 配置数据库和迁移
- [ ] **步骤12**: 编写单元测试
- [ ] **步骤13**: 部署到生产环境

### 7.2 关键点

1. **现有代码无需改动**：所有`src/`下的业务逻辑保持不变
2. **API层是薄封装**：主要负责HTTP协议处理和数据转换
3. **异步处理**：大文件和批量任务使用Celery异步处理
4. **分层架构**：路由 → 服务 → 业务逻辑，职责清晰

### 7.3 开发顺序建议

1. 先实现核心功能接口（文档转换、存储、查询）
2. 再实现辅助功能（任务状态、文档管理）
3. 最后实现高级功能（WebSocket、多轮对话）

---

## 附录：完整示例代码仓库

完整的API实现代码将放在单独的分支中：

```bash
git checkout -b feature/api-layer
```

开发团队可以基于此指南逐步实现API服务层。