"""
向量存储 (Vector Store)

负责与向量数据库交互，提供数据的存储、检索、删除等功能。

支持的数据库：
- ChromaDB: 默认实现，轻量级本地向量数据库

主要功能：
1. 集合管理（创建、删除、列表）
2. 文档存储和检索
3. 相似性搜索
4. 元数据过滤
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.models.schemas import EmbeddedChunk, RetrievedChunk
from src.storage.exceptions import (
    CollectionCreateError,
    CollectionExistsError,
    CollectionNotFoundError,
    DatabaseInitError,
    DocumentExistsError,
    DocumentNotFoundError,
    StorageConnectionError,
    StorageError,
    StorageErrorCode,
    StorageErrorContext,
)


logger = logging.getLogger(__name__)


# ============================================================
# 配置类
# ============================================================

@dataclass
class VectorStoreConfig:
    """
    向量存储配置
    
    Attributes:
        db_type: 数据库类型 (chroma, milvus, etc.)
        persist_directory: 持久化目录（用于本地数据库）
        host: 数据库主机（用于远程数据库）
        port: 数据库端口
        collection_name: 默认集合名称
        distance_metric: 距离度量方式 (cosine, euclidean, ip)
    """
    db_type: str = "chroma"
    persist_directory: str = "./data/vectordb"
    host: Optional[str] = None
    port: Optional[int] = None
    collection_name: str = "papers"
    distance_metric: str = "cosine"
    
    # ChromaDB特有配置
    anonymized_telemetry: bool = False


@dataclass
class SearchResult:
    """搜索结果"""
    chunks: List[RetrievedChunk]
    total_found: int
    query_embedding: Optional[List[float]] = None


# ============================================================
# 抽象基类
# ============================================================

class BaseVectorStore(ABC):
    """
    向量存储抽象基类
    
    所有向量存储实现都必须继承此类
    """
    
    @abstractmethod
    def create_collection(
        self,
        name: str,
        dimension: Optional[int] = None,
        distance_metric: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        创建集合
        
        Args:
            name: 集合名称
            dimension: 向量维度
            distance_metric: 距离度量方式
            metadata: 集合元数据
        """
        pass
    
    @abstractmethod
    def delete_collection(self, name: str) -> None:
        """
        删除集合
        
        Args:
            name: 集合名称
        """
        pass
    
    @abstractmethod
    def list_collections(self) -> List[str]:
        """
        列出所有集合
        
        Returns:
            集合名称列表
        """
        pass
    
    @abstractmethod
    def collection_exists(self, name: str) -> bool:
        """
        检查集合是否存在
        
        Args:
            name: 集合名称
        
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    def add_chunks(
        self,
        chunks: List[EmbeddedChunk],
        collection_name: Optional[str] = None
    ) -> List[str]:
        """
        添加向量化后的文档块
        
        Args:
            chunks: 向量化后的文档块列表
            collection_name: 集合名称
        
        Returns:
            添加的块ID列表
        """
        pass
    
    @abstractmethod
    def delete_chunks(
        self,
        chunk_ids: List[str],
        collection_name: Optional[str] = None
    ) -> int:
        """
        删除文档块
        
        Args:
            chunk_ids: 块ID列表
            collection_name: 集合名称
        
        Returns:
            删除的块数量
        """
        pass
    
    @abstractmethod
    def delete_document(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> int:
        """
        删除文档的所有块
        
        Args:
            document_id: 文档ID
            collection_name: 集合名称
        
        Returns:
            删除的块数量
        """
        pass
    
    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = 0.0
    ) -> SearchResult:
        """
        相似性搜索
        
        Args:
            query_embedding: 查询向量
            top_k: 返回结果数量
            collection_name: 集合名称
            filter_metadata: 元数据过滤条件
            similarity_threshold: 相似度阈值
        
        Returns:
            搜索结果
        """
        pass
    
    @abstractmethod
    def get_chunk(
        self,
        chunk_id: str,
        collection_name: Optional[str] = None
    ) -> Optional[EmbeddedChunk]:
        """
        获取单个块
        
        Args:
            chunk_id: 块ID
            collection_name: 集合名称
        
        Returns:
            文档块，不存在则返回None
        """
        pass
    
    @abstractmethod
    def get_document_chunks(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> List[EmbeddedChunk]:
        """
        获取文档的所有块
        
        Args:
            document_id: 文档ID
            collection_name: 集合名称
        
        Returns:
            文档块列表
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass


# ============================================================
# ChromaDB 实现
# ============================================================

class ChromaVectorStore(BaseVectorStore):
    """
    ChromaDB 向量存储实现
    
    ChromaDB是一个轻量级的本地向量数据库，支持持久化存储。
    
    特性：
    - 本地运行，无需额外服务
    - 支持元数据过滤
    - 自动持久化
    """
    
    # 距离度量映射
    DISTANCE_METRICS = {
        "cosine": "cosine",
        "euclidean": "l2",
        "ip": "ip",  # 内积
    }
    
    def __init__(self, config: Optional[VectorStoreConfig] = None):
        """
        初始化ChromaDB存储
        
        Args:
            config: 配置对象
        """
        self._config = config or VectorStoreConfig()
        self._client = None
        self._collections: Dict[str, Any] = {}  # 缓存已打开的集合
        self._logger = logging.getLogger(self.__class__.__name__)
        
        self._init_client()
    
    def _init_client(self) -> None:
        """初始化ChromaDB客户端"""
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise DatabaseInitError(
                message="chromadb 未安装。请运行: pip install chromadb",
                db_type="chroma"
            )
        
        try:
            # 确保持久化目录存在
            persist_dir = Path(self._config.persist_directory)
            persist_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建客户端
            settings = Settings(
                anonymized_telemetry=self._config.anonymized_telemetry,
                persist_directory=str(persist_dir),
                is_persistent=True
            )
            
            self._client = chromadb.Client(settings)
            
            self._logger.info(
                f"ChromaDB初始化完成，持久化目录: {persist_dir}"
            )
        
        except Exception as e:
            raise DatabaseInitError(
                message=f"ChromaDB初始化失败: {str(e)}",
                db_type="chroma",
                cause=e
            )
    
    def _get_collection(self, name: Optional[str] = None):
        """获取或创建集合"""
        collection_name = name or self._config.collection_name
        
        if collection_name in self._collections:
            return self._collections[collection_name]
        
        try:
            # 尝试获取已存在的集合
            collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": self.DISTANCE_METRICS.get(
                    self._config.distance_metric, "cosine"
                )}
            )
            self._collections[collection_name] = collection
            return collection
        
        except Exception as e:
            raise CollectionNotFoundError(
                collection_name=collection_name,
                context=StorageErrorContext(
                    collection_name=collection_name,
                    operation="get_collection"
                )
            )
    
    def create_collection(
        self,
        name: str,
        dimension: Optional[int] = None,
        distance_metric: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """创建集合"""
        try:
            # 检查是否已存在
            existing = self._client.list_collections()
            if any(c.name == name for c in existing):
                raise CollectionExistsError(collection_name=name)
            
            # 构建元数据
            collection_metadata = {
                "hnsw:space": self.DISTANCE_METRICS.get(distance_metric, "cosine")
            }
            if dimension:
                collection_metadata["dimension"] = dimension
            if metadata:
                collection_metadata.update(metadata)
            
            # 创建集合
            collection = self._client.create_collection(
                name=name,
                metadata=collection_metadata
            )
            self._collections[name] = collection
            
            self._logger.info(f"创建集合: {name}")
        
        except CollectionExistsError:
            raise
        except Exception as e:
            raise CollectionCreateError(
                collection_name=name,
                cause=e
            )
    
    def delete_collection(self, name: str) -> None:
        """删除集合"""
        try:
            self._client.delete_collection(name=name)
            
            # 从缓存中移除
            if name in self._collections:
                del self._collections[name]
            
            self._logger.info(f"删除集合: {name}")
        
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise CollectionNotFoundError(collection_name=name)
            raise StorageError(
                code=StorageErrorCode.COLLECTION_DELETE_FAILED,
                message=f"删除集合失败: {name}",
                cause=e
            )
    
    def list_collections(self) -> List[str]:
        """列出所有集合"""
        try:
            collections = self._client.list_collections()
            return [c.name for c in collections]
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.QUERY_FAILED,
                message="列出集合失败",
                cause=e
            )
    
    def collection_exists(self, name: str) -> bool:
        """检查集合是否存在"""
        return name in self.list_collections()
    
    def add_chunks(
        self,
        chunks: List[EmbeddedChunk],
        collection_name: Optional[str] = None
    ) -> List[str]:
        """添加向量化后的文档块"""
        if not chunks:
            return []
        
        collection = self._get_collection(collection_name)
        
        try:
            # 准备数据
            ids = [chunk.chunk_id for chunk in chunks]
            embeddings = [chunk.embedding for chunk in chunks]
            documents = [chunk.content for chunk in chunks]
            
            # 构建元数据
            metadatas = []
            for chunk in chunks:
                meta = {
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                    "embedding_model": chunk.embedding_model,
                }
                if chunk.section_title:
                    meta["section_title"] = chunk.section_title
                
                # 添加用户元数据（转换为字符串以兼容ChromaDB）
                for key, value in chunk.metadata.items():
                    if isinstance(value, (str, int, float, bool)):
                        meta[key] = value
                    elif isinstance(value, list):
                        meta[key] = ", ".join(str(v) for v in value)
                    else:
                        meta[key] = str(value)
                
                metadatas.append(meta)
            
            # 添加到集合
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            
            self._logger.debug(f"添加 {len(chunks)} 个块到集合 {collection.name}")
            
            return ids
        
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.INSERT_FAILED,
                message=f"添加文档块失败: {str(e)}",
                context=StorageErrorContext(
                    collection_name=collection_name or self._config.collection_name,
                    operation="add_chunks"
                ),
                cause=e
            )
    
    def delete_chunks(
        self,
        chunk_ids: List[str],
        collection_name: Optional[str] = None
    ) -> int:
        """删除文档块"""
        if not chunk_ids:
            return 0
        
        collection = self._get_collection(collection_name)
        
        try:
            collection.delete(ids=chunk_ids)
            self._logger.debug(f"删除 {len(chunk_ids)} 个块")
            return len(chunk_ids)
        
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.DELETE_FAILED,
                message=f"删除块失败: {str(e)}",
                cause=e
            )
    
    def delete_document(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> int:
        """删除文档的所有块"""
        collection = self._get_collection(collection_name)
        
        try:
            # 查找所有属于该文档的块
            results = collection.get(
                where={"document_id": document_id}
            )
            
            if not results["ids"]:
                return 0
            
            # 删除这些块
            collection.delete(ids=results["ids"])
            
            count = len(results["ids"])
            self._logger.info(f"删除文档 {document_id} 的 {count} 个块")
            
            return count
        
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.DOCUMENT_DELETE_FAILED,
                message=f"删除文档失败: {document_id}",
                context=StorageErrorContext(document_id=document_id),
                cause=e
            )
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        collection_name: Optional[str] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = 0.0
    ) -> SearchResult:
        """相似性搜索"""
        collection = self._get_collection(collection_name)
        
        try:
            # 构建查询参数
            query_params = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
                "include": ["documents", "metadatas", "distances"]
            }
            
            # 添加过滤条件
            if filter_metadata:
                query_params["where"] = filter_metadata
            
            # 执行查询
            results = collection.query(**query_params)
            
            # 转换结果
            chunks = []
            
            if results["ids"] and results["ids"][0]:
                for i, chunk_id in enumerate(results["ids"][0]):
                    # ChromaDB返回的是距离，需要转换为相似度
                    distance = results["distances"][0][i]
                    
                    # 根据距离度量转换为相似度
                    if self._config.distance_metric == "cosine":
                        # 余弦距离 = 1 - 余弦相似度
                        similarity = 1 - distance
                    elif self._config.distance_metric == "euclidean":
                        # 欧氏距离转相似度：使用 1 / (1 + distance)
                        similarity = 1 / (1 + distance)
                    else:  # ip
                        # 内积作为相似度
                        similarity = distance
                    
                    # 应用阈值过滤
                    if similarity < similarity_threshold:
                        continue
                    
                    metadata = results["metadatas"][0][i]
                    
                    chunk = RetrievedChunk(
                        chunk_id=chunk_id,
                        document_id=metadata.get("document_id", ""),
                        content=results["documents"][0][i],
                        similarity_score=similarity,
                        metadata={
                            k: v for k, v in metadata.items()
                            if k not in ["document_id", "chunk_index", "start_char", 
                                        "end_char", "section_title", "embedding_model"]
                        },
                        section_title=metadata.get("section_title")
                    )
                    chunks.append(chunk)
            
            return SearchResult(
                chunks=chunks,
                total_found=len(chunks),
                query_embedding=query_embedding
            )
        
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.QUERY_FAILED,
                message=f"搜索失败: {str(e)}",
                cause=e
            )
    
    def get_chunk(
        self,
        chunk_id: str,
        collection_name: Optional[str] = None
    ) -> Optional[EmbeddedChunk]:
        """获取单个块"""
        collection = self._get_collection(collection_name)
        
        try:
            results = collection.get(
                ids=[chunk_id],
                include=["documents", "metadatas", "embeddings"]
            )
            
            if not results["ids"]:
                return None
            
            metadata = results["metadatas"][0]
            
            return EmbeddedChunk(
                chunk_id=chunk_id,
                document_id=metadata.get("document_id", ""),
                content=results["documents"][0],
                chunk_index=metadata.get("chunk_index", 0),
                start_char=metadata.get("start_char", 0),
                end_char=metadata.get("end_char", 0),
                section_title=metadata.get("section_title"),
                metadata={
                    k: v for k, v in metadata.items()
                    if k not in ["document_id", "chunk_index", "start_char",
                                "end_char", "section_title", "embedding_model"]
                },
                embedding=results["embeddings"][0] if results["embeddings"] else [],
                embedding_model=metadata.get("embedding_model", "unknown"),
                embedding_dimension=len(results["embeddings"][0]) if results["embeddings"] else 0
            )
        
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.QUERY_FAILED,
                message=f"获取块失败: {chunk_id}",
                cause=e
            )
    
    def get_document_chunks(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> List[EmbeddedChunk]:
        """获取文档的所有块"""
        collection = self._get_collection(collection_name)
        
        try:
            results = collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas", "embeddings"]
            )
            
            chunks = []
            
            for i, chunk_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i]
                
                chunk = EmbeddedChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    content=results["documents"][i],
                    chunk_index=metadata.get("chunk_index", i),
                    start_char=metadata.get("start_char", 0),
                    end_char=metadata.get("end_char", 0),
                    section_title=metadata.get("section_title"),
                    metadata={
                        k: v for k, v in metadata.items()
                        if k not in ["document_id", "chunk_index", "start_char",
                                    "end_char", "section_title", "embedding_model"]
                    },
                    embedding=results["embeddings"][i] if results["embeddings"] else [],
                    embedding_model=metadata.get("embedding_model", "unknown"),
                    embedding_dimension=len(results["embeddings"][i]) if results["embeddings"] else 0
                )
                chunks.append(chunk)
            
            # 按chunk_index排序
            chunks.sort(key=lambda c: c.chunk_index)
            
            return chunks
        
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.QUERY_FAILED,
                message=f"获取文档块失败: {document_id}",
                cause=e
            )
    
    def list_documents(
        self,
        collection_name: Optional[str] = None
    ) -> List[str]:
        """列出集合中所有文档ID"""
        collection = self._get_collection(collection_name)
        
        try:
            # 获取所有块的元数据
            results = collection.get(include=["metadatas"])
            
            # 提取唯一的document_id
            document_ids = set()
            for metadata in results["metadatas"]:
                if "document_id" in metadata:
                    document_ids.add(metadata["document_id"])
            
            return list(document_ids)
        
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.QUERY_FAILED,
                message="列出文档失败",
                cause=e
            )
    
    def get_collection_stats(
        self,
        collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取集合统计信息"""
        collection = self._get_collection(collection_name)
        
        try:
            count = collection.count()
            documents = self.list_documents(collection_name)
            
            return {
                "collection_name": collection.name,
                "total_chunks": count,
                "total_documents": len(documents),
                "document_ids": documents
            }
        
        except Exception as e:
            raise StorageError(
                code=StorageErrorCode.QUERY_FAILED,
                message="获取统计信息失败",
                cause=e
            )
    
    def document_exists(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> bool:
        """检查文档是否存在"""
        collection = self._get_collection(collection_name)
        
        try:
            results = collection.get(
                where={"document_id": document_id},
                limit=1
            )
            return len(results["ids"]) > 0
        
        except Exception:
            return False
    
    def update_chunks(
        self,
        chunks: List[EmbeddedChunk],
        collection_name: Optional[str] = None
    ) -> List[str]:
        """更新文档块（先删除再添加）"""
        if not chunks:
            return []
        
        # 删除已存在的块
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        try:
            self.delete_chunks(chunk_ids, collection_name)
        except Exception:
            pass  # 忽略删除错误
        
        # 添加新块
        return self.add_chunks(chunks, collection_name)


# ============================================================
# 工厂和便捷函数
# ============================================================

class VectorStoreFactory:
    """
    向量存储工厂
    
    根据配置创建对应的向量存储实例
    """
    
    STORES = {
        "chroma": ChromaVectorStore,
    }
    
    @classmethod
    def create(cls, config: Optional[VectorStoreConfig] = None) -> BaseVectorStore:
        """
        创建向量存储
        
        Args:
            config: 配置对象
        
        Returns:
            向量存储实例
        """
        if config is None:
            config = VectorStoreConfig()
        
        db_type = config.db_type.lower()
        
        if db_type not in cls.STORES:
            raise DatabaseInitError(
                message=f"不支持的数据库类型: {db_type}，支持: {list(cls.STORES.keys())}",
                db_type=db_type
            )
        
        store_class = cls.STORES[db_type]
        return store_class(config)
    
    @classmethod
    def register_store(cls, name: str, store_class: type) -> None:
        """注册自定义存储"""
        cls.STORES[name.lower()] = store_class


def create_vector_store(
    db_type: str = "chroma",
    persist_directory: str = "./data/vectordb",
    **kwargs
) -> BaseVectorStore:
    """
    创建向量存储的便捷函数
    
    Args:
        db_type: 数据库类型
        persist_directory: 持久化目录
        **kwargs: 其他配置参数
    
    Returns:
        向量存储实例
    """
    config = VectorStoreConfig(
        db_type=db_type,
        persist_directory=persist_directory,
        **kwargs
    )
    return VectorStoreFactory.create(config)