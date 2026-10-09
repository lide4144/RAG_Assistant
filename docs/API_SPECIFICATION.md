
# 论文资源管理系统 - API接口规范文档

## 目录

1. [通用数据结构](#1-通用数据结构)
2. [文档转换模块接口规范](#2-文档转换模块接口规范)
3. [RAG存储模块接口规范](#3-rag存储模块接口规范)
4. [RAG问答模块接口规范](#4-rag问答模块接口规范)
5. [配置格式规范](#5-配置格式规范)
6. [错误处理规范](#6-错误处理规范)

---

## 1. 通用数据结构

### 1.1 文件类型枚举 (FileType)

```python
from enum import Enum

class FileType(str, Enum):
    """支持的文件类型"""
    PDF = "pdf"
    HTML = "html"
    TXT = "txt"
    MARKDOWN = "md"
```

### 1.2 处理状态枚举 (ProcessingStatus)

```python
class ProcessingStatus(str, Enum):
    """处理状态"""
    PENDING = "pending"          # 待处理
    PROCESSING = "processing"    # 处理中
    SUCCESS = "success"          # 处理成功
    FAILED = "failed"            # 处理失败
    PARTIAL = "partial"          # 部分成功
```

### 1.3 基础元数据 (BaseMetadata)

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class BaseMetadata(BaseModel):
    """
    基础元数据结构
    所有文档相关的元数据都应包含这些基础字段
    """
    title: Optional[str] = Field(
        default=None,
        description="文档标题"
    )
    authors: Optional[list[str]] = Field(
        default=None,
        description="作者列表"
    )
    abstract: Optional[str] = Field(
        default=None,
        description="摘要"
    )
    keywords: Optional[list[str]] = Field(
        default=None,
        description="关键词列表"
    )
    publication_date: Optional[datetime] = Field(
        default=None,
        description="发表日期"
    )
    source: Optional[str] = Field(
        default=None,
        description="来源（期刊名、会议名等）"
    )
    doi: Optional[str] = Field(
        default=None,
        description="DOI标识符"
    )
    language: Optional[str] = Field(
        default="zh",
        description="文档语言，ISO 639-1编码"
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description="扩展元数据，用于存储自定义字段"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "title": "基于深度学习的文本分类研究",
                "authors": ["张三", "李四"],
                "abstract": "本文提出了一种新的文本分类方法...",
                "keywords": ["深度学习", "文本分类", "NLP"],
                "publication_date": "2024-01-15T00:00:00Z",
                "source": "计算机学报",
                "doi": "10.1234/example.2024.001",
                "language": "zh",
                "extra": {"citations": 42}
            }
        }
```

### 1.4 处理结果基类 (BaseResult)

```python
class BaseResult(BaseModel):
    """
    所有处理结果的基类
    """
    success: bool = Field(
        description="处理是否成功"
    )
    status: ProcessingStatus = Field(
        description="处理状态"
    )
    message: Optional[str] = Field(
        default=None,
        description="状态消息或错误信息"
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="处理耗时（毫秒）"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="处理时间戳"
    )
```

---

## 2. 文档转换模块接口规范

### 2.1 模块职责

文档转换模块负责将各种格式的论文文件（PDF、HTML、TXT）转换为标准的Markdown格式，同时提取文档元数据。

### 2.2 输入数据结构

#### 2.2.1 DocumentInput - 单文档输入

```python
class DocumentInput(BaseModel):
    """
    文档转换模块的输入结构
    
    用途：描述需要转换的单个文档
    """
    file_path: str = Field(
        description="文件路径（绝对路径或相对于工作目录的路径）"
    )
    file_type: Optional[FileType] = Field(
        default=None,
        description="文件类型，若为None则自动检测"
    )
    metadata: Optional[BaseMetadata] = Field(
        default=None,
        description="预设的元数据（可选，会与提取的元数据合并）"
    )
    encoding: Optional[str] = Field(
        default="utf-8",
        description="文件编码（主要用于TXT文件）"
    )
    extract_images: bool = Field(
        default=True,
        description="是否提取图片"
    )
    extract_tables: bool = Field(
        default=True,
        description="是否提取表格"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "/data/papers/example.pdf",
                "file_type": "pdf",
                "metadata": {
                    "title": "预设标题（如果PDF中无法提取）"
                },
                "encoding": "utf-8",
                "extract_images": True,
                "extract_tables": True
            }
        }
```

#### 2.2.2 BatchDocumentInput - 批量文档输入

```python
class BatchDocumentInput(BaseModel):
    """
    批量文档转换输入
    
    用途：批量处理多个文档
    """
    documents: list[DocumentInput] = Field(
        description="待转换的文档列表"
    )
    parallel: bool = Field(
        default=True,
        description="是否并行处理"
    )
    max_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="最大并行工作线程数"
    )
    continue_on_error: bool = Field(
        default=True,
        description="遇到错误时是否继续处理其他文档"
    )
```

### 2.3 输出数据结构

#### 2.3.1 MarkdownDocument - 转换后的Markdown文档

```python
class SourceInfo(BaseModel):
    """
    来源信息
    """
    original_file_path: str = Field(
        description="原始文件路径"
    )
    original_file_type: FileType = Field(
        description="原始文件类型"
    )
    original_file_size_bytes: int = Field(
        description="原始文件大小（字节）"
    )
    original_file_hash: str = Field(
        description="原始文件MD5哈希值"
    )
    conversion_timestamp: datetime = Field(
        description="转换时间戳"
    )


class ImageInfo(BaseModel):
    """
    提取的图片信息
    """
    image_id: str = Field(
        description="图片唯一标识符"
    )
    original_page: Optional[int] = Field(
        default=None,
        description="图片所在页码（PDF专用）"
    )
    image_path: Optional[str] = Field(
        default=None,
        description="图片保存路径（如果保存到文件）"
    )
    image_base64: Optional[str] = Field(
        default=None,
        description="图片Base64编码（如果内嵌）"
    )
    mime_type: str = Field(
        description="图片MIME类型"
    )
    width: int = Field(
        description="图片宽度（像素）"
    )
    height: int = Field(
        description="图片高度（像素）"
    )
    caption: Optional[str] = Field(
        default=None,
        description="图片标题/说明"
    )


class TableInfo(BaseModel):
    """
    提取的表格信息
    """
    table_id: str = Field(
        description="表格唯一标识符"
    )
    original_page: Optional[int] = Field(
        default=None,
        description="表格所在页码（PDF专用）"
    )
    markdown_content: str = Field(
        description="表格的Markdown格式内容"
    )
    caption: Optional[str] = Field(
        default=None,
        description="表格标题"
    )
    rows: int = Field(
        description="行数"
    )
    columns: int = Field(
        description="列数"
    )


class MarkdownDocument(BaseModel):
    """
    转换后的Markdown文档
    
    用途：作为文档转换模块的输出，同时也是RAG存储模块的输入
    
    重要：这是模块间传递的核心数据结构
    """
    document_id: str = Field(
        description="文档唯一标识符（UUID格式）"
    )
    content: str = Field(
        description="Markdown格式的文档正文内容"
    )
    metadata: BaseMetadata = Field(
        description="文档元数据"
    )
    source_info: SourceInfo = Field(
        description="来源信息"
    )
    images: Optional[list[ImageInfo]] = Field(
        default=None,
        description="提取的图片列表"
    )
    tables: Optional[list[TableInfo]] = Field(
        default=None,
        description="提取的表格列表"
    )
    sections: Optional[list[str]] = Field(
        default=None,
        description="文档章节标题列表（用于结构化索引）"
    )
    word_count: int = Field(
        description="文档字数"
    )
    page_count: Optional[int] = Field(
        default=None,
        description="原始文档页数（PDF专用）"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "content": "# 论文标题\n\n## 摘要\n\n这是摘要内容...\n\n## 1. 引言\n\n引言内容...",
                "metadata": {
                    "title": "基于深度学习的文本分类研究",
                    "authors": ["张三", "李四"],
                    "abstract": "本文提出了一种新的文本分类方法...",
                    "keywords": ["深度学习", "文本分类"]
                },
                "source_info": {
                    "original_file_path": "/data/papers/example.pdf",
                    "original_file_type": "pdf",
                    "original_file_size_bytes": 1024000,
                    "original_file_hash": "d41d8cd98f00b204e9800998ecf8427e",
                    "conversion_timestamp": "2024-01-15T10:30:00Z"
                },
                "images": [],
                "tables": [],
                "sections": ["摘要", "1. 引言", "2. 相关工作", "3. 方法", "4. 实验", "5. 结论"],
                "word_count": 5000,
                "page_count": 12
            }
        }
```

#### 2.3.2 ConversionResult - 转换结果

```python
class ConversionResult(BaseResult):
    """
    单文档转换结果
    """
    document: Optional[MarkdownDocument] = Field(
        default=None,
        description="转换后的文档（成功时有值）"
    )
    error_details: Optional[str] = Field(
        default=None,
        description="详细错误信息（失败时有值）"
    )
    warnings: Optional[list[str]] = Field(
        default=None,
        description="转换过程中的警告信息"
    )


class BatchConversionResult(BaseResult):
    """
    批量转换结果
    """
    results: list[ConversionResult] = Field(
        description="各文档的转换结果列表"
    )
    total_count: int = Field(
        description="总文档数"
    )
    success_count: int = Field(
        description="成功转换数"
    )
    failed_count: int = Field(
        description="失败数"
    )
```

### 2.4 接口定义

```python
from abc import ABC, abstractmethod

class BaseConverter(ABC):
    """
    文档转换器基类
    
    所有格式的转换器都必须实现此接口
    """
    
    @abstractmethod
    def convert(self, input: DocumentInput) -> ConversionResult:
        """
        转换单个文档
        
        Args:
            input: 文档输入对象
            
        Returns:
            ConversionResult: 转换结果
        """
        pass
    
    @abstractmethod
    def supports(self, file_type: FileType) -> bool:
        """
        检查是否支持指定的文件类型
        
        Args:
            file_type: 文件类型
            
        Returns:
            bool: 是否支持
        """
        pass


class DocumentConverterService:
    """
    文档转换服务
    
    对外提供的统一接口
    """
    
    def convert_document(self, input: DocumentInput) -> ConversionResult:
        """
        转换单个文档
        
        Args:
            input: DocumentInput对象
            
        Returns:
            ConversionResult: 包含MarkdownDocument或错误信息
        """
        pass
    
    def convert_batch(self, input: BatchDocumentInput) -> BatchConversionResult:
        """
        批量转换文档
        
        Args:
            input: BatchDocumentInput对象
            
        Returns:
            BatchConversionResult: 批量转换结果
        """
        pass
```

---

## 3. RAG存储模块接口规范

### 3.1 模块职责

RAG存储模块负责：
1. 将Markdown文档分割成合适的文本块（Chunks）
2. 使用嵌入模型将文本块向量化
3. 将向量和元数据存储到向量数据库中

### 3.2 输入数据结构

#### 3.2.1 StorageInput - 存储输入（使用MarkdownDocument）

```python
class ChunkingConfig(BaseModel):
    """
    分块配置
    """
    chunk_size: int = Field(
        default=512,
        ge=100,
        le=4096,
        description="每个块的目标字符数"
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=500,
        description="块之间的重叠字符数"
    )
    split_by: str = Field(
        default="paragraph",
        description="分割方式：paragraph（段落）、sentence（句子）、token（词元）"
    )
    respect_sections: bool = Field(
        default=True,
        description="是否尊重章节边界，避免跨章节分割"
    )


class StorageInput(BaseModel):
    """
    RAG存储模块的输入
    
    用途：将一个或多个MarkdownDocument存储到向量数据库
    """
    documents: list[MarkdownDocument] = Field(
        description="待存储的Markdown文档列表"
    )
    collection_name: str = Field(
        default="papers",
        description="向量数据库中的集合名称"
    )
    chunking_config: ChunkingConfig = Field(
        default_factory=ChunkingConfig,
        description="分块配置"
    )
    update_existing: bool = Field(
        default=True,
        description="如果文档已存在是否更新"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "documents": ["...MarkdownDocument对象列表..."],
                "collection_name": "papers",
                "chunking_config": {
                    "chunk_size": 512,
                    "chunk_overlap": 50,
                    "split_by": "paragraph",
                    "respect_sections": True
                },
                "update_existing": True
            }
        }
```

### 3.3 输出数据结构

#### 3.3.1 DocumentChunk - 文档块

```python
class DocumentChunk(BaseModel):
    """
    文档分块结果
    
    用途：表示存储在向量数据库中的单个文本块
    """
    chunk_id: str = Field(
        description="块唯一标识符（格式：{document_id}_{chunk_index}）"
    )
    document_id: str = Field(
        description="所属文档的ID"
    )
    content: str = Field(
        description="块的文本内容"
    )
    chunk_index: int = Field(
        description="块在文档中的索引位置"
    )
    start_char: int = Field(
        description="块在原文档中的起始字符位置"
    )
    end_char: int = Field(
        description="块在原文档中的结束字符位置"
    )
    section_title: Optional[str] = Field(
        default=None,
        description="块所属的章节标题"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="块的元数据（继承自文档元数据）"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": "550e8400-e29b-41d4-a716-446655440000_0",
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "content": "这是第一个文本块的内容...",
                "chunk_index": 0,
                "start_char": 0,
                "end_char": 512,
                "section_title": "1. 引言",
                "metadata": {
                    "title": "论文标题",
                    "authors": ["张三", "李四"]
                }
            }
        }
```

#### 3.3.2 EmbeddedChunk - 向量化后的块

```python
class EmbeddedChunk(DocumentChunk):
    """
    向量化后的文档块
    
    用途：存储到向量数据库的完整数据结构
    """
    embedding: list[float] = Field(
        description="向量表示（维度取决于嵌入模型）"
    )
    embedding_model: str = Field(
        description="使用的嵌入模型名称"
    )
    embedding_dimension: int = Field(
        description="向量维度"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": "550e8400-e29b-41d4-a716-446655440000_0",
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "content": "这是第一个文本块的内容...",
                "chunk_index": 0,
                "start_char": 0,
                "end_char": 512,
                "section_title": "1. 引言",
                "metadata": {"title": "论文标题"},
                "embedding": [0.1, 0.2, 0.3, "...共768维..."],
                "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "embedding_dimension": 384
            }
        }
```

#### 3.3.3 StorageResult - 存储结果

```python
class DocumentStorageInfo(BaseModel):
    """
    单个文档的存储信息
    """
    document_id: str = Field(
        description="文档ID"
    )
    chunks_count: int = Field(
        description="生成的块数量"
    )
    chunk_ids: list[str] = Field(
        description="所有块的ID列表"
    )
    success: bool = Field(
        description="是否存储成功"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="错误信息"
    )


class StorageResult(BaseResult):
    """
    RAG存储模块的输出结果
    """
    collection_name: str = Field(
        description="存储的集合名称"
    )
    documents_info: list[DocumentStorageInfo] = Field(
        description="各文档的存储信息"
    )
    total_documents: int = Field(
        description="总文档数"
    )
    total_chunks: int = Field(
        description="总块数"
    )
    success_documents: int = Field(
        description="成功存储的文档数"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "status": "success",
                "message": "成功存储3个文档",
                "processing_time_ms": 1523.5,
                "timestamp": "2024-01-15T10:35:00Z",
                "collection_name": "papers",
                "documents_info": [
                    {
                        "document_id": "550e8400-e29b-41d4-a716-446655440000",
                        "chunks_count": 15,
                        "chunk_ids": ["..."],
                        "success": True
                    }
                ],
                "total_documents": 3,
                "total_chunks": 45,
                "success_documents": 3
            }
        }
```

### 3.4 接口定义

```python
class RAGStorageService:
    """
    RAG存储服务
    
    提供文档存储、删除、更新功能
    """
    
    def store_documents(self, input: StorageInput) -> StorageResult:
        """
        存储文档到向量数据库
        
        Args:
            input: StorageInput对象，包含MarkdownDocument列表
            
        Returns:
            StorageResult: 存储结果
        """
        pass
    
    def delete_document(self, document_id: str, collection_name: str = "papers") -> BaseResult:
        """
        从向量数据库中删除文档
        
        Args:
            document_id: 要删除的文档ID
            collection_name: 集合名称
            
        Returns:
            BaseResult: 删除结果
        """
        pass
    
    def get_document_info(self, document_id: str, collection_name: str = "papers") -> Optional[DocumentStorageInfo]:
        """
        获取文档存储信息
        
        Args:
            document_id: 文档ID
            collection_name: 集合名称
            
        Returns:
            DocumentStorageInfo: 文档存储信息，不存在则返回None
        """
        pass
    
    def list_documents(self, collection_name: str = "papers") -> list[str]:
        """
        列出集合中所有文档ID
        
        Args:
            collection_name: 集合名称
            
        Returns:
            list[str]: 文档ID列表
        """
        pass
```

---

## 4. RAG问答模块接口规范

### 4.1 模块职责

RAG问答模块负责：
1. 接收用户查询
2. 从向量数据库中检索相关文档块
3. 调用LLM生成回答

### 4.2 输入数据结构

#### 4.2.1 QueryInput - 查询输入

```python
class RetrievalConfig(BaseModel):
    """
    检索配置
    """
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="返回的最相关文档块数量"
    )
    similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="相似度阈值，低于此值的结果将被过滤"
    )
    rerank: bool = Field(
        default=False,
        description="是否使用重排序模型"
    )
    filter_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="元数据过滤条件"
    )


class LLMConfig(BaseModel):
    """
    LLM配置
    
    用途：配置用于生成回答的大语言模型
    """
    provider: str = Field(
        default="openai",
        description="LLM提供商：openai、anthropic、azure、local、custom"
    )
    model: str = Field(
        default="gpt-3.5-turbo",
        description="模型名称"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API密钥（如果为None则从环境变量读取）"
    )
    api_base: Optional[str] = Field(
        default=None,
        description="自定义API端点（用于自部署或代理）"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="生成温度"
    )
    max_tokens: int = Field(
        default=2048,
        ge=100,
        le=32000,
        description="最大生成token数"
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="自定义系统提示词"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "provider": "openai",
                "model": "gpt-3.5-turbo",
                "api_key": None,
                "api_base": "https://api.openai.com/v1",
                "temperature": 0.7,
                "max_tokens": 2048,
                "system_prompt": "你是一个专业的学术助手，基于提供的论文内容回答问题。"
            }
        }


class QueryInput(BaseModel):
    """
    RAG查询输入
    
    用途：发送查询请求到RAG问答模块
    """
    query: str = Field(
        description="用户的查询问题"
    )
    collection_name: str = Field(
        default="papers",
        description="要检索的集合名称"
    )
    retrieval_config: RetrievalConfig = Field(
        default_factory=RetrievalConfig,
        description="检索配置"
    )
    llm_config: Optional[LLMConfig] = Field(
        default=None,
        description="LLM配置（如果为None则使用默认配置）"
    )
    include_sources: bool = Field(
        default=True,
        description="是否在回答中包含来源引用"
    )
    conversation_history: Optional[list[Dict[str, str]]] = Field(
        default=None,
        description="对话历史，用于多轮对话"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "深度学习在文本分类中有哪些常用方法？",
                "collection_name": "papers",
                "retrieval_config": {
                    "top_k": 5,
                    "similarity_threshold": 0.7,
                    "rerank": False
                },
                "llm_config": {
                    "provider": "openai",
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.7
                },
                "include_sources": True,
                "conversation_history": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好！我是论文助手，请问有什么可以帮您？"}
                ]
            }
        }
```

### 4.3 输出数据结构

#### 4.3.1 RetrievedChunk - 检索到的文档块

```python
class RetrievedChunk(BaseModel):
    """
    检索到的文档块
    
    用途：表示从向量数据库中检索到的相关内容
    """
    chunk_id: str = Field(
        description="块ID"
    )
    document_id: str = Field(
        description="所属文档ID"
    )
    content: str = Field(
        description="块内容"
    )
    similarity_score: float = Field(
        description="与查询的相似度分数"
    )
    metadata: Dict[str, Any] = Field(
        description="块元数据"
    )
    section_title: Optional[str] = Field(
        default=None,
        description="所属章节标题"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": "550e8400-e29b-41d4-a716-446655440000_3",
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "content": "深度学习方法在文本分类中表现出色...",
                "similarity_score": 0.89,
                "metadata": {
                    "title": "基于深度学习的文本分类研究",
                    "authors": ["张三", "李四"]
                },
                "section_title": "2. 相关工作"
            }
        }
```

#### 4.3.2 SourceReference - 来源引用

```python
class SourceReference(BaseModel):
    """
    来源引用
    
    用途：在回答中标注信息来源
    """
    document_id: str = Field(
        description="文档ID"
    )
    document_title: str = Field(
        description="文档标题"
    )
    authors: Optional[list[str]] = Field(
        default=None,
        description="作者列表"
    )
    chunk_ids: list[str] = Field(
        description="引用的块ID列表"
    )
    relevance_score: float = Field(
        description="相关性分数（取最高相似度）"
    )
    snippet: str = Field(
        description="引用片段（用于显示）"
    )
```

#### 4.3.3 QueryResponse - 查询响应

```python
class UsageStats(BaseModel):
    """
    使用统计
    """
    prompt_tokens: int = Field(
        description="输入token数"
    )
    completion_tokens: int = Field(
        description="输出token数"
    )
    total_tokens: int = Field(
        description="总token数"
    )
    retrieval_time_ms: float = Field(
        description="检索耗时（毫秒）"
    )
    llm_time_ms: float = Field(
        description="LLM生成耗时（毫秒）"
    )


class QueryResponse(BaseResult):
    """
    RAG查询响应
    
    用途：RAG问答模块的最终输出
    """
    answer: str = Field(
        description="生成的回答"
    )
    sources: Optional[list[SourceReference]] = Field(
        default=None,
        description="引用的来源列表"
    )
    retrieved_chunks: list[RetrievedChunk] = Field(
        description="检索到的所有相关块"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="回答置信度（基于检索相似度和LLM判断）"
    )
    usage: Optional[UsageStats] = Field(
        default=None,
        description="使用统计"
    )
    model_used: str = Field(
        description="实际使用的模型名称"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "status": "success",
                "message": None,
                "processing_time_ms": 2156.8,
                "timestamp": "2024-01-15T10:40:00Z",
                "answer": "根据检索到的论文内容，深度学习在文本分类中常用的方法包括：\n\n1. **CNN（卷积神经网络）**：通过卷积层提取文本的局部特征...\n\n2. **RNN/LSTM**：通过循环结构捕获文本的序列信息...\n\n3. **Transformer**：使用自注意力机制处理长距离依赖...",
                "sources": [
                    {
                        "document_id": "550e8400-e29b-41d4-a716-446655440000",
                        "document_title": "基于深度学习的文本分类研究",
                        "authors": ["张三", "李四"],
                        "chunk_ids": ["550e8400..._3", "550e8400..._5"],
                        "relevance_score": 0.89,
                        "snippet": "深度学习方法在文本分类中表现出色..."
                    }
                ],
                "retrieved_chunks": ["..."],
                "confidence": 0.85,
                "usage": {
                    "prompt_tokens": 1500,
                    "completion_tokens": 350,
                    "total_tokens": 1850,
                    "retrieval_time_ms": 156.3,
                    "llm_time_ms": 2000.5
                },
                "model_used": "gpt-3.5-turbo"
            }
        }
```

### 4.4 接口定义

```python
class RAGQueryService:
    """
    RAG问答服务
    
    提供智能问答功能
    """
    
    def query(self, input: QueryInput) -> QueryResponse:
        """
        执行RAG查询
        
        Args:
            input: QueryInput对象
            
        Returns:
            QueryResponse: 包含回答和来源的响应
        """
        pass
    
    def retrieve_only(self, query: str, collection_name: str = "papers",
                      config: RetrievalConfig = None) -> list[RetrievedChunk]:
        """
        仅执行检索，不生成回答
        
        Args:
            query: 查询文本
            collection_name: 集合名称
            config: 检索配置
            
        Returns:
            list[RetrievedChunk]: 检索到的文档块列表
        """
        pass
    
    def get_supported_models(self) -> Dict[str, list[str]]:
        """
        获取支持的LLM模型列表
        
        Returns:
            Dict: 按提供商分组的模型列表
        """
        pass
```

---

## 5. 配置格式规范

### 5.1 主配置文件 (config.yaml)

```yaml
# config/config.yaml
# 论文资源管理系统主配置文件

# ============================================================
# 系统基础配置
# ============================================================
system:
  # 日志级别: DEBUG, INFO, WARNING, ERROR
  log_level: INFO
  # 工作目录
  work_dir: ./data
  # 临时文件目录
  temp_dir: ./data/temp
  # 是否启用调试模式
  debug: false

# ============================================================
# 文档转换模块配置
# ============================================================
converter:
  # 输入目录
  input_dir: ./data/input
  # 输出目录（保存转换后的Markdown文件）
  output_dir: ./data/output
  # 图片保存目录
  images_dir: ./data/output/images
  
  # PDF转换配置
  pdf:
    # 是否提取图片
    extract_images: true
    # 图片最小尺寸（像素），小于此尺寸的图片会被忽略
    min_image_size: 100
    # 是否提取表格
    extract_tables: true
    # OCR配置（用于扫描版PDF）
    ocr:
      enabled: false
      language: chi_sim+eng
  
  # HTML转换配置
  html:
    # 是否保留原始链接
    preserve_links: true
    # 是否提取内联样式
    extract_styles: false
    # 内容选择器（CSS选择器）
    content_selector: article, .content, main, body
    # 要移除的元素选择器
    remove_selectors:
      - script
      - style
      - nav
      - header
      - footer
      - .sidebar
      - .advertisement
  
  # TXT转换配置
  txt:
    # 默认编码
    default_encoding: utf-8
    # 编码检测
    detect_encoding: true

# ============================================================
# RAG存储模块配置
# ============================================================
storage:
  # 向量数据库配置
  vector_db:
    # 类型: chroma, milvus, pinecone, qdrant
    type: chroma
    # ChromaDB持久化目录
    persist_directory: ./data/vectordb
    # 默认集合名称
    default_collection: papers
  
  # 分块配置
  chunking:
    # 每个块的目标字符数
    chunk_size: 512
    # 块之间的重叠字符数
    chunk_overlap: 50
    # 分割方式: paragraph, sentence, token
    split_by: paragraph
    # 是否尊重章节边界
    respect_sections: true
  
  # 嵌入模型配置
  embedding:
    # 模型提供商: sentence-transformers, openai, custom
    provider: sentence-transformers
    # 模型名称
    model: paraphrase-multilingual-MiniLM-L12-v2
    # 批处理大小
    batch_size: 32
    # 最大序列长度
    max_length: 512
    # 设备: cpu, cuda, mps
    device: cpu
    # OpenAI嵌入配置（如果使用OpenAI）
    openai:
      model: text-embedding-ada-002
      api_key: ${OPENAI_API_KEY}

# ============================================================
# RAG问答模块配置
# ============================================================
query:
  # 默认检索配置
  retrieval:
    # 返回的最相关文档块数量
    top_k: 5
    # 相似度阈值
    similarity_threshold: 0.7
    # 是否启用重排序
    rerank: false
    # 重排序模型（如果启用）
    rerank_model: cross-encoder/ms-marco-MiniLM-L-6-v2
  
  # 默认LLM配置
  llm:
    # 提供商: openai, anthropic, azure, local, custom
    provider: openai
    # 模型名称
    model: gpt-3.5-turbo
    # API配置
    api_key: ${OPENAI_API_KEY}
    api_base: https://api.openai.com/v1
    # 生成参数
    temperature: 0.7
    max_tokens: 2048
    # 超时设置（秒）
    timeout: 60
    # 重试次数
    max_retries: 3
  
  # 系统提示词
  system_prompt: |
    你是一个专业的学术助手，专门帮助用户理解和分析学术论文。
    请基于提供的论文内容回答用户的问题。
    如果提供的内容不足以回答问题，请明确说明。
    回答时请引用相关的论文来源。
  
  # 提示词模板
  prompt_template: |
    根据以下论文内容回答问题：
    
    {context}
    
    问题：{question}
    
    请给出详细的回答，并标注信息来源。

# ============================================================
# 自定义LLM提供商配置（可选）
# ============================================================
custom_llm_providers:
  # 本地部署的LLM
  local_llama:
    type: openai_compatible
    api_base: http://localhost:8080/v1
    api_key: not-needed
    default_model: llama-2-7b-chat
  
  # 阿里云通义千问
  qwen:
    type: openai_compatible
    api_base: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${DASHSCOPE_API_KEY}
    default_model: qwen-turbo
  
  # 其他自定义API
  custom_api:
    type: custom
    api_base: https://your-api-endpoint.com
    api_key: ${CUSTOM_API_KEY}
    default_model: your-model-name
```

### 5.2 环境变量配置 (.env)

```bash
# .env.example
# 复制此文件为 .env 并填入实际值

# OpenAI API配置
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1

# 阿里云通义千问配置
DASHSCOPE_API_KEY=your-dashscope-api-key-here

# Anthropic API配置
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# 自定义API配置
CUSTOM_API_KEY=your-custom-api-key-here

# 系统配置
LOG_LEVEL=INFO
DEBUG=false
```

---

## 6. 错误处理规范

### 6.1 错误码定义

```python
class ErrorCode(str, Enum):
    """
    系统错误码
    """
    # 通用错误 (1xxx)
    UNKNOWN_ERROR = "E1000"
    INVALID_INPUT = "E1001"
    FILE_NOT_FOUND = "E1002"
    PERMISSION_DENIED = "E1003"
    TIMEOUT = "E1004"
    
    # 文档转换错误 (2xxx)
    UNSUPPORTED_FILE_TYPE = "E2001"
    CONVERSION_FAILED = "E2002"
    PDF_PARSE_ERROR = "E2003"
    HTML_PARSE_ERROR = "E2004"
    ENCODING_ERROR = "E2005"
    IMAGE_EXTRACTION_FAILED = "E2006"
    TABLE_EXTRACTION_FAILED = "E2007"
    
    # RAG存储错误 (3xxx)
    STORAGE_CONNECTION_FAILED = "E3001"
    EMBEDDING_FAILED = "E3002"
    CHUNKING_FAILED = "E3003"
    DOCUMENT_EXISTS = "E3004"
    DOCUMENT_NOT_FOUND = "E3005"
    COLLECTION_NOT_FOUND = "E3006"
    
    # RAG查询错误 (4xxx)
    RETRIEVAL_FAILED = "E4001"
    LLM_API_ERROR = "E4002"
    LLM_RATE_LIMIT = "E4003"
    LLM_TOKEN_LIMIT = "E4004"
    INVALID_MODEL = "E4005"
    GENERATION_FAILED = "E4006"
```

### 6.2 错误响应结构

```python
class ErrorDetail(BaseModel):
    """
    错误详情
    """
    code: ErrorCode = Field(
        description="错误码"
    )
    message: str = Field(
        description="错误消息"
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="详细错误信息"
    )
    traceback: Optional[str] = Field(
        default=None,
        description="错误堆栈（仅调试模式）"
    )


class ErrorResponse(BaseModel):
    """
    错误响应
    """
    success: bool = Field(
        default=False,
        description="始终为False"
    )
    status: ProcessingStatus = Field(
        default=ProcessingStatus.FAILED,
        description="处理状态"
    )
    error: ErrorDetail = Field(
        description="错误详情"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="错误发生时间"
    )
```

---

## 7. 模块间调用示例

### 7.1 完整流程示例

```python
from src.converter import DocumentConverterService
from src.storage import RAGStorageService
from src.query import RAGQueryService
from src.models.schemas import (
    DocumentInput, StorageInput, QueryInput,
    ChunkingConfig, RetrievalConfig, LLMConfig
)

# 初始化服务
converter_service = DocumentConverterService()
storage_service = RAGStorageService()
query_service = RAGQueryService()

# ============================================================
# 步骤1：文档转换
# ============================================================
# 输入
doc_input = DocumentInput(
    file_path="./data/input/paper.pdf",
    file_type="pdf",
    extract_images=True,
    extract_tables=True
)

# 转换
conversion_result = converter_service.convert_document(doc_input)

if conversion_result.success:
    markdown_doc = conversion_result.document
    print(f"转换成功: {markdown_doc.document_id}")
    print(f"字数: {markdown_doc.word_count}")
else:
    print(f"转换失败: {conversion_result.error_details}")
    exit(1)

# ============================================================
# 步骤2：RAG存储
# ============================================================
# 输入（使用上一步的输出）
storage_input = StorageInput(
    documents=[markdown_doc],  # MarkdownDocument列表
    collection_name="papers",
    chunking_config=ChunkingConfig(
        chunk_size=512,
        chunk_overlap=50,
        split_by="paragraph"
    )
)

# 存储
storage_result = storage_service.store_documents(storage_input)

if storage_result.success:
    print(f"存储成功: {storage_result.total_chunks}个文本块")
else:
    print(f"存储失败: {storage_result.message}")
    exit(1)

# ============================================================
# 步骤3：RAG问答
# ============================================================
# 输入
query_input = QueryInput(
    query="这篇论文的主要贡献是什么？",
    collection_name="papers",
    retrieval_config=RetrievalConfig(
        top_k=5,
        similarity_threshold=0.7
    ),
    llm_config=LLMConfig(
        provider="openai",
        model="gpt-3.5-turbo",
        temperature=0.7
    ),
    include_sources=True
)

# 查询
response = query_service.query(query_input)

if response.success:
    print(f"回答:\n{response.answer}")
    print(f"\n来源:")
    for source in response.sources:
        print(f"  - {source.document_title} (相关度: {source.relevance_score:.2f})")
else:
    print(f"查询失败: {response.message}")
```

### 7.2 数据流转图示

```
┌─────────────────────────────────────────────────────────────────────┐
│                          数据流转详细图示                             │
└─────────────────────────────────────────────────────────────────────┘

     DocumentInput                    MarkdownDocument
    ┌─────────────┐                  ┌─────────────────┐
    │ file_path   │                  │ document_id     │
    │ file_type   │ ───转换───────▶  │ content (MD)    │
    │ metadata    │                  │ metadata        │
    │ encoding    │                  │ source_info     │
    │ ...         │                  │ images[]        │
    └─────────────┘                  │ tables[]        │
                                     │ sections[]      │
                                     └────────┬────────┘
                                              │
                                              ▼
                                     StorageInput
                                     ┌─────────────────┐
                                     │ documents[]     │◀── MarkdownDocument[]
                                     │ collection_name │
                                     │ chunking_config │
                                     └────────┬────────┘
                                              │
                                              ▼ 分块 + 向量化
                                     ┌─────────────────┐
                                     │ EmbeddedChunk[] │
                                     │ - chunk_id      │
                                     │ - content       │
                                     │ - embedding     │
                                     │ - metadata      │
                                     └────────┬────────┘
                                              │
                                              ▼ 存入向量数据库
                                     ┌─────────────────┐
                                     │   Vector DB     │
                                     │   (ChromaDB)    │
                                     └────────┬────────┘
                                              │
                                              ▼
     QueryInput                      检索相关块
    ┌─────────────────┐             ┌─────────────────┐
    │ query           │ ──检索───▶  │ RetrievedChunk[]│
    │ collection_name │             │ - content       │
    │ retrieval_config│             │ - similarity    │
    │ llm_config      │             └────────┬────────┘
    └─────────────────┘                      │
                                             ▼ 组装Prompt
                                     ┌─────────────────┐
                                     │   LLM API       │
                                     │ (OpenAI/本地)   │
                                     └────────┬────────┘
                                              │
                                              ▼
                                     QueryResponse
                                     ┌─────────────────┐
                                     │ answer          │
                                     │ sources[]       │
                                     │ retrieved_chunks│
                                     │ confidence      │
                                     │ usage           │
                                     └─────────────────┘
```

---

## 8. 版本信息

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| 1.0.0 | 2024-01-15 | 初始版本，定义核心数据结构和接口 |

---

## 9. 附录

### 9.1 Pydantic模型完整代码

完整的Pydantic模型定义请参见：[src/models/schemas.py](../src/models/schemas.py)

### 9.2 相关文档

- [架构设计文档](./ARCHITECTURE.md)
- [开发指南](./DEVELOPMENT.md)
- [部署文档](./DEPLOYMENT.md)