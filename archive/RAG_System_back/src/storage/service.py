"""
RAG存储服务 (RAG Storage Service)

提供统一的文档存储API接口，是外部调用的主入口。

功能：
1. 将MarkdownDocument存储到向量数据库
2. 文档分块、向量化的完整流程
3. 文档的增删改查操作
4. 批量处理和错误处理
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from src.models.schemas import (
    BaseResult,
    ChunkingConfig,
    DocumentChunk,
    DocumentStorageInfo,
    EmbeddedChunk,
    MarkdownDocument,
    ProcessingStatus,
    RetrievedChunk,
    StorageInput,
    StorageResult,
)
from src.storage.chunker import Chunker, ChunkResult
from src.storage.embedder import (
    BaseEmbedder,
    EmbeddingConfig,
    EmbedderFactory,
)
from src.storage.vector_store import (
    BaseVectorStore,
    ChromaVectorStore,
    SearchResult,
    VectorStoreConfig,
    VectorStoreFactory,
)
from src.storage.exceptions import (
    ChunkingError,
    DocumentExistsError,
    DocumentNotFoundError,
    EmbeddingError,
    StorageError,
    StorageErrorCode,
    StorageErrorContext,
)


logger = logging.getLogger(__name__)


# ============================================================
# 配置类
# ============================================================

@dataclass
class StorageServiceConfig:
    """
    存储服务配置
    
    整合了分块、向量化和存储的所有配置
    """
    # 分块配置
    chunk_size: int = 512
    chunk_overlap: int = 50
    split_by: str = "paragraph"
    respect_sections: bool = True
    min_chunk_size: int = 0              # 最小块大小（0表示保留所有内容，防止数据丢失）
    merge_small_chunks: bool = True      # 是否合并小块
    
    # 向量化配置
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32
    
    # 存储配置
    vector_db_type: str = "chroma"
    persist_directory: str = "./data/vectordb"
    default_collection: str = "papers"
    distance_metric: str = "cosine"
    
    # OpenAI配置（如果使用OpenAI作为向量化提供商）
    openai_api_key: Optional[str] = None
    openai_api_base: Optional[str] = None
    
    def to_chunking_config(self) -> ChunkingConfig:
        """转换为分块配置"""
        return ChunkingConfig(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            split_by=self.split_by,
            respect_sections=self.respect_sections,
            min_chunk_size=self.min_chunk_size,
            merge_small_chunks=self.merge_small_chunks
        )
    
    def to_embedding_config(self) -> EmbeddingConfig:
        """转换为向量化配置"""
        return EmbeddingConfig(
            provider=self.embedding_provider,
            model_name=self.embedding_model,
            device=self.embedding_device,
            batch_size=self.embedding_batch_size,
            api_key=self.openai_api_key,
            api_base=self.openai_api_base
        )
    
    def to_vector_store_config(self) -> VectorStoreConfig:
        """转换为存储配置"""
        return VectorStoreConfig(
            db_type=self.vector_db_type,
            persist_directory=self.persist_directory,
            collection_name=self.default_collection,
            distance_metric=self.distance_metric
        )


# ============================================================
# 主服务类
# ============================================================

class RAGStorageService:
    """
    RAG存储服务
    
    提供完整的文档存储和管理功能，整合分块、向量化和存储。
    
    使用示例:
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
    """
    
    def __init__(
        self,
        config: Optional[StorageServiceConfig] = None,
        chunker: Optional[Chunker] = None,
        embedder: Optional[BaseEmbedder] = None,
        vector_store: Optional[BaseVectorStore] = None
    ):
        """
        初始化存储服务
        
        Args:
            config: 服务配置
            chunker: 自定义分块器
            embedder: 自定义向量化器
            vector_store: 自定义向量存储
        """
        self._config = config or StorageServiceConfig()
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # 初始化组件
        self._chunker = chunker or Chunker(self._config.to_chunking_config())
        self._embedder = embedder
        self._vector_store = vector_store
        
        # 延迟初始化向量化器和存储
        self._embedder_initialized = embedder is not None
        self._store_initialized = vector_store is not None
    
    def _ensure_embedder(self) -> BaseEmbedder:
        """确保向量化器已初始化"""
        if self._embedder is None:
            self._embedder = EmbedderFactory.create(
                self._config.to_embedding_config()
            )
            self._embedder_initialized = True
        return self._embedder
    
    def _ensure_vector_store(self) -> BaseVectorStore:
        """确保向量存储已初始化"""
        if self._vector_store is None:
            self._vector_store = VectorStoreFactory.create(
                self._config.to_vector_store_config()
            )
            self._store_initialized = True
        return self._vector_store
    
    def store_documents(self, input: StorageInput) -> StorageResult:
        """
        存储文档到向量数据库
        
        完整流程：分块 -> 向量化 -> 存储
        
        Args:
            input: StorageInput对象，包含MarkdownDocument列表
        
        Returns:
            StorageResult: 存储结果
        """
        start_time = time.time()
        
        documents = input.documents
        collection_name = input.collection_name
        chunking_config = input.chunking_config
        update_existing = input.update_existing
        
        self._logger.info(
            f"开始存储 {len(documents)} 个文档到集合 {collection_name}"
        )
        
        # 使用输入中的分块配置
        if chunking_config:
            self._chunker = Chunker(chunking_config)
        
        # 确保组件已初始化
        embedder = self._ensure_embedder()
        vector_store = self._ensure_vector_store()
        
        # 确保集合存在
        if not vector_store.collection_exists(collection_name):
            vector_store.create_collection(
                name=collection_name,
                dimension=embedder.dimension,
                distance_metric=self._config.distance_metric
            )
        
        documents_info: List[DocumentStorageInfo] = []
        total_chunks = 0
        success_count = 0
        
        for doc in documents:
            doc_info = self._store_single_document(
                document=doc,
                collection_name=collection_name,
                update_existing=update_existing,
                embedder=embedder,
                vector_store=vector_store
            )
            documents_info.append(doc_info)
            
            if doc_info.success:
                success_count += 1
                total_chunks += doc_info.chunks_count
        
        # 计算处理时间
        processing_time_ms = (time.time() - start_time) * 1000
        
        # 确定整体状态
        if success_count == len(documents):
            status = ProcessingStatus.SUCCESS
            message = f"成功存储 {len(documents)} 个文档，共 {total_chunks} 个块"
        elif success_count == 0:
            status = ProcessingStatus.FAILED
            message = f"所有 {len(documents)} 个文档存储失败"
        else:
            status = ProcessingStatus.PARTIAL
            message = f"部分成功: {success_count}/{len(documents)} 个文档存储成功"
        
        self._logger.info(
            f"存储完成: {success_count}/{len(documents)} 成功, "
            f"总块数: {total_chunks}, "
            f"耗时: {processing_time_ms:.2f}ms"
        )
        
        return StorageResult(
            success=success_count > 0,
            status=status,
            message=message,
            processing_time_ms=processing_time_ms,
            collection_name=collection_name,
            documents_info=documents_info,
            total_documents=len(documents),
            total_chunks=total_chunks,
            success_documents=success_count
        )
    
    def _store_single_document(
        self,
        document: MarkdownDocument,
        collection_name: str,
        update_existing: bool,
        embedder: BaseEmbedder,
        vector_store: BaseVectorStore
    ) -> DocumentStorageInfo:
        """
        存储单个文档
        
        Args:
            document: Markdown文档
            collection_name: 集合名称
            update_existing: 是否更新已存在的文档
            embedder: 向量化器
            vector_store: 向量存储
        
        Returns:
            DocumentStorageInfo: 文档存储信息
        """
        document_id = document.document_id
        
        try:
            # 检查文档是否已存在
            if hasattr(vector_store, 'document_exists'):
                exists = vector_store.document_exists(document_id, collection_name)
                if exists and not update_existing:
                    raise DocumentExistsError(
                        document_id=document_id,
                        collection_name=collection_name
                    )
                elif exists:
                    # 删除旧块
                    vector_store.delete_document(document_id, collection_name)
                    self._logger.debug(f"已删除旧文档块: {document_id}")
            
            # 分块
            self._logger.debug(f"分块文档: {document_id}")
            chunk_result = self._chunker.chunk_document(document)
            
            if not chunk_result.chunks:
                return DocumentStorageInfo(
                    document_id=document_id,
                    chunks_count=0,
                    chunk_ids=[],
                    success=True,
                    error_message="文档分块为空"
                )
            
            # 向量化
            self._logger.debug(
                f"向量化文档: {document_id}, "
                f"{len(chunk_result.chunks)} 个块"
            )
            embedded_chunks = embedder.embed_chunks(chunk_result.chunks)
            
            # 存储
            self._logger.debug(f"存储文档: {document_id}")
            chunk_ids = vector_store.add_chunks(embedded_chunks, collection_name)
            
            return DocumentStorageInfo(
                document_id=document_id,
                chunks_count=len(chunk_ids),
                chunk_ids=chunk_ids,
                success=True
            )
        
        except DocumentExistsError as e:
            self._logger.warning(f"文档已存在: {document_id}")
            return DocumentStorageInfo(
                document_id=document_id,
                chunks_count=0,
                chunk_ids=[],
                success=False,
                error_message=str(e)
            )
        
        except (ChunkingError, EmbeddingError, StorageError) as e:
            self._logger.error(f"存储文档失败: {document_id}, 错误: {e}")
            return DocumentStorageInfo(
                document_id=document_id,
                chunks_count=0,
                chunk_ids=[],
                success=False,
                error_message=str(e)
            )
        
        except Exception as e:
            self._logger.exception(f"存储文档时发生未预期错误: {document_id}")
            return DocumentStorageInfo(
                document_id=document_id,
                chunks_count=0,
                chunk_ids=[],
                success=False,
                error_message=f"未预期的错误: {str(e)}"
            )
    
    def delete_document(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> BaseResult:
        """
        从向量数据库中删除文档
        
        Args:
            document_id: 要删除的文档ID
            collection_name: 集合名称
        
        Returns:
            BaseResult: 删除结果
        """
        start_time = time.time()
        collection = collection_name or self._config.default_collection
        
        try:
            vector_store = self._ensure_vector_store()
            
            # 检查文档是否存在
            if hasattr(vector_store, 'document_exists'):
                if not vector_store.document_exists(document_id, collection):
                    return BaseResult(
                        success=False,
                        status=ProcessingStatus.FAILED,
                        message=f"文档不存在: {document_id}",
                        processing_time_ms=(time.time() - start_time) * 1000
                    )
            
            # 删除文档
            deleted_count = vector_store.delete_document(document_id, collection)
            
            return BaseResult(
                success=True,
                status=ProcessingStatus.SUCCESS,
                message=f"成功删除文档 {document_id}，共 {deleted_count} 个块",
                processing_time_ms=(time.time() - start_time) * 1000
            )
        
        except Exception as e:
            self._logger.error(f"删除文档失败: {document_id}, 错误: {e}")
            return BaseResult(
                success=False,
                status=ProcessingStatus.FAILED,
                message=str(e),
                processing_time_ms=(time.time() - start_time) * 1000
            )
    
    def get_document_info(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> Optional[DocumentStorageInfo]:
        """
        获取文档存储信息
        
        Args:
            document_id: 文档ID
            collection_name: 集合名称
        
        Returns:
            DocumentStorageInfo: 文档存储信息，不存在则返回None
        """
        collection = collection_name or self._config.default_collection
        
        try:
            vector_store = self._ensure_vector_store()
            
            chunks = vector_store.get_document_chunks(document_id, collection)
            
            if not chunks:
                return None
            
            return DocumentStorageInfo(
                document_id=document_id,
                chunks_count=len(chunks),
                chunk_ids=[c.chunk_id for c in chunks],
                success=True
            )
        
        except Exception as e:
            self._logger.error(f"获取文档信息失败: {document_id}, 错误: {e}")
            return None
    
    def list_documents(
        self,
        collection_name: Optional[str] = None
    ) -> List[str]:
        """
        列出集合中所有文档ID
        
        Args:
            collection_name: 集合名称
        
        Returns:
            文档ID列表
        """
        collection = collection_name or self._config.default_collection
        
        try:
            vector_store = self._ensure_vector_store()
            return vector_store.list_documents(collection)
        except Exception as e:
            self._logger.error(f"列出文档失败: {e}")
            return []
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = 0.0
    ) -> List[RetrievedChunk]:
        """
        搜索相关文档块
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            collection_name: 集合名称
            filter_metadata: 元数据过滤条件
            similarity_threshold: 相似度阈值
        
        Returns:
            检索到的文档块列表
        """
        collection = collection_name or self._config.default_collection
        
        try:
            embedder = self._ensure_embedder()
            vector_store = self._ensure_vector_store()
            
            # 向量化查询
            query_embedding = embedder.embed_text(query)
            
            # 搜索
            result = vector_store.search(
                query_embedding=query_embedding,
                top_k=top_k,
                collection_name=collection,
                filter_metadata=filter_metadata,
                similarity_threshold=similarity_threshold
            )
            
            return result.chunks
        
        except Exception as e:
            self._logger.error(f"搜索失败: {e}")
            return []
    
    def search_with_embedding(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = 0.0
    ) -> SearchResult:
        """
        使用向量进行搜索（适用于已有向量的场景）
        
        Args:
            query_embedding: 查询向量
            top_k: 返回结果数量
            collection_name: 集合名称
            filter_metadata: 元数据过滤条件
            similarity_threshold: 相似度阈值
        
        Returns:
            搜索结果
        """
        collection = collection_name or self._config.default_collection
        
        vector_store = self._ensure_vector_store()
        
        return vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            collection_name=collection,
            filter_metadata=filter_metadata,
            similarity_threshold=similarity_threshold
        )
    
    def get_collection_stats(
        self,
        collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Args:
            collection_name: 集合名称
        
        Returns:
            统计信息字典
        """
        collection = collection_name or self._config.default_collection
        
        try:
            vector_store = self._ensure_vector_store()
            return vector_store.get_collection_stats(collection)
        except Exception as e:
            self._logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def create_collection(
        self,
        name: str,
        distance_metric: str = "cosine"
    ) -> bool:
        """
        创建新集合
        
        Args:
            name: 集合名称
            distance_metric: 距离度量方式
        
        Returns:
            是否成功
        """
        try:
            vector_store = self._ensure_vector_store()
            embedder = self._ensure_embedder()
            
            vector_store.create_collection(
                name=name,
                dimension=embedder.dimension,
                distance_metric=distance_metric
            )
            return True
        except Exception as e:
            self._logger.error(f"创建集合失败: {name}, 错误: {e}")
            return False
    
    def delete_collection(self, name: str) -> bool:
        """
        删除集合
        
        Args:
            name: 集合名称
        
        Returns:
            是否成功
        """
        try:
            vector_store = self._ensure_vector_store()
            vector_store.delete_collection(name)
            return True
        except Exception as e:
            self._logger.error(f"删除集合失败: {name}, 错误: {e}")
            return False
    
    def list_collections(self) -> List[str]:
        """
        列出所有集合
        
        Returns:
            集合名称列表
        """
        try:
            vector_store = self._ensure_vector_store()
            return vector_store.list_collections()
        except Exception as e:
            self._logger.error(f"列出集合失败: {e}")
            return []
    
    @property
    def embedder(self) -> BaseEmbedder:
        """获取向量化器"""
        return self._ensure_embedder()
    
    @property
    def vector_store(self) -> BaseVectorStore:
        """获取向量存储"""
        return self._ensure_vector_store()
    
    @property
    def chunker(self) -> Chunker:
        """获取分块器"""
        return self._chunker


# ============================================================
# 便捷函数
# ============================================================

# 默认服务实例
_default_service: Optional[RAGStorageService] = None


def get_storage_service(
    config: Optional[StorageServiceConfig] = None
) -> RAGStorageService:
    """
    获取存储服务实例
    
    Args:
        config: 配置对象
    
    Returns:
        RAGStorageService实例
    """
    global _default_service
    
    if _default_service is None or config is not None:
        _default_service = RAGStorageService(config)
    
    return _default_service


def store_documents(
    documents: List[MarkdownDocument],
    collection_name: str = "papers",
    chunking_config: Optional[ChunkingConfig] = None
) -> StorageResult:
    """
    存储文档的便捷函数
    
    Args:
        documents: Markdown文档列表
        collection_name: 集合名称
        chunking_config: 分块配置
    
    Returns:
        存储结果
    """
    service = get_storage_service()
    
    input = StorageInput(
        documents=documents,
        collection_name=collection_name,
        chunking_config=chunking_config or ChunkingConfig()
    )
    
    return service.store_documents(input)


def search_documents(
    query: str,
    top_k: int = 5,
    collection_name: str = "papers",
    similarity_threshold: float = 0.0
) -> List[RetrievedChunk]:
    """
    搜索文档的便捷函数
    
    Args:
        query: 查询文本
        top_k: 返回结果数量
        collection_name: 集合名称
        similarity_threshold: 相似度阈值
    
    Returns:
        检索到的文档块列表
    """
    service = get_storage_service()
    
    return service.search(
        query=query,
        top_k=top_k,
        collection_name=collection_name,
        similarity_threshold=similarity_threshold
    )