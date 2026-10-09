"""
RAG存储模块 (RAG Storage)

负责将 Markdown 文档分块、向量化并存储到向量数据库。

主要组件：
- Chunker: 文档分块器
- Embedder: 向量化器
- VectorStore: 向量存储接口
- RAGStorageService: 统一的存储服务

输入数据结构：
- MarkdownDocument: 待存储的Markdown文档（来自转换模块）
- StorageInput: 存储输入配置
- ChunkingConfig: 分块配置

输出数据结构：
- DocumentChunk: 文档块
- EmbeddedChunk: 向量化后的文档块
- StorageResult: 存储结果

使用示例：
    from src.storage import RAGStorageService, StorageInput
    from src.models.schemas import MarkdownDocument, ChunkingConfig
    
    # 创建服务
    service = RAGStorageService()
    
    # 存储文档
    result = service.store_documents(
        StorageInput(documents=[markdown_doc])
    )
    
    if result.success:
        print(f"存储了 {result.total_chunks} 个文本块")
    
    # 搜索文档
    chunks = service.search("深度学习", top_k=5)
    for chunk in chunks:
        print(f"相似度: {chunk.similarity_score:.2f}")
        print(chunk.content[:100])

错误码（E3xxx系列）：
- E3001: 存储连接失败
- E3002: 向量化失败
- E3003: 分块失败
- E3004: 文档已存在
- E3005: 文档未找到
- E3006: 集合未找到
"""

# 异常类
from src.storage.exceptions import (
    # 错误码枚举
    StorageErrorCode,
    # 上下文
    StorageErrorContext,
    # 基类
    StorageError,
    # 连接错误
    StorageConnectionError,
    DatabaseInitError,
    # 向量化错误
    EmbeddingError,
    EmbeddingModelNotFoundError,
    EmbeddingModelLoadError,
    EmbeddingDimensionMismatchError,
    EmbeddingAPIError,
    # 分块错误
    ChunkingError,
    InvalidChunkConfigError,
    EmptyContentError,
    # 文档错误
    DocumentExistsError,
    DocumentNotFoundError,
    # 集合错误
    CollectionNotFoundError,
    CollectionExistsError,
    CollectionCreateError,
    # 配置错误
    ConfigError,
    MissingAPIKeyError,
    # 工具函数
    validate_error_code,
    get_error_message,
    is_storage_error,
    create_error_response,
    wrap_exception,
)

# 分块器
from src.storage.chunker import (
    # 策略接口
    SplitStrategy,
    ParagraphSplitStrategy,
    SentenceSplitStrategy,
    TokenSplitStrategy,
    # 章节解析
    Section,
    SectionParser,
    # 分块器
    Chunker,
    ChunkResult,
    # 便捷函数
    create_chunker,
    chunk_document,
)

# 向量化器
from src.storage.embedder import (
    # 配置
    EmbeddingConfig,
    # 基类
    BaseEmbedder,
    # 实现
    SentenceTransformersEmbedder,
    OpenAIEmbedder,
    HuggingFaceEmbedder,
    # 工厂
    EmbedderFactory,
    # 便捷函数
    create_embedder,
    embed_texts,
    embed_chunks,
)

# 向量存储
from src.storage.vector_store import (
    # 配置
    VectorStoreConfig,
    SearchResult,
    # 基类
    BaseVectorStore,
    # 实现
    ChromaVectorStore,
    # 工厂
    VectorStoreFactory,
    # 便捷函数
    create_vector_store,
)

# 服务
from src.storage.service import (
    # 配置
    StorageServiceConfig,
    # 服务类
    RAGStorageService,
    # 便捷函数
    get_storage_service,
    store_documents,
    search_documents,
)


__all__ = [
    # ============ 异常类 ============
    # 错误码
    "StorageErrorCode",
    "StorageErrorContext",
    # 异常基类
    "StorageError",
    # 连接错误
    "StorageConnectionError",
    "DatabaseInitError",
    # 向量化错误
    "EmbeddingError",
    "EmbeddingModelNotFoundError",
    "EmbeddingModelLoadError",
    "EmbeddingDimensionMismatchError",
    "EmbeddingAPIError",
    # 分块错误
    "ChunkingError",
    "InvalidChunkConfigError",
    "EmptyContentError",
    # 文档错误
    "DocumentExistsError",
    "DocumentNotFoundError",
    # 集合错误
    "CollectionNotFoundError",
    "CollectionExistsError",
    "CollectionCreateError",
    # 配置错误
    "ConfigError",
    "MissingAPIKeyError",
    # 工具函数
    "validate_error_code",
    "get_error_message",
    "is_storage_error",
    "create_error_response",
    "wrap_exception",
    
    # ============ 分块器 ============
    # 策略
    "SplitStrategy",
    "ParagraphSplitStrategy",
    "SentenceSplitStrategy",
    "TokenSplitStrategy",
    # 章节
    "Section",
    "SectionParser",
    # 分块器
    "Chunker",
    "ChunkResult",
    "create_chunker",
    "chunk_document",
    
    # ============ 向量化器 ============
    # 配置
    "EmbeddingConfig",
    # 基类和实现
    "BaseEmbedder",
    "SentenceTransformersEmbedder",
    "OpenAIEmbedder",
    "HuggingFaceEmbedder",
    # 工厂
    "EmbedderFactory",
    # 便捷函数
    "create_embedder",
    "embed_texts",
    "embed_chunks",
    
    # ============ 向量存储 ============
    # 配置
    "VectorStoreConfig",
    "SearchResult",
    # 基类和实现
    "BaseVectorStore",
    "ChromaVectorStore",
    # 工厂
    "VectorStoreFactory",
    "create_vector_store",
    
    # ============ 服务 ============
    # 配置
    "StorageServiceConfig",
    # 服务类
    "RAGStorageService",
    # 便捷函数
    "get_storage_service",
    "store_documents",
    "search_documents",
]