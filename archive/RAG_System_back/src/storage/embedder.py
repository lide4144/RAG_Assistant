"""
向量化器 (Embedder)

负责将文本块转换为向量表示（embeddings）。

支持的提供商：
- sentence-transformers: 本地模型，无需API
- openai: OpenAI Embedding API
- huggingface: HuggingFace Inference API

主要功能：
1. 单文本/批量文本向量化
2. 可配置的模型和参数
3. 批处理优化
4. 统一的接口
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from src.models.schemas import DocumentChunk, EmbeddedChunk
from src.storage.exceptions import (
    EmbeddingAPIError,
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingModelLoadError,
    EmbeddingModelNotFoundError,
    MissingAPIKeyError,
    StorageErrorContext,
)


logger = logging.getLogger(__name__)


# ============================================================
# 配置类
# ============================================================

@dataclass
class EmbeddingConfig:
    """
    向量化配置
    
    Attributes:
        provider: 提供商名称 (sentence-transformers, openai, huggingface)
        model_name: 模型名称
        batch_size: 批处理大小
        max_length: 最大序列长度
        device: 计算设备 (cpu, cuda, mps)
        normalize: 是否对向量进行归一化
        api_key: API密钥（用于远程服务）
        api_base: API基础URL
    """
    provider: str = "sentence-transformers"
    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"
    batch_size: int = 32
    max_length: int = 512
    device: str = "cpu"
    normalize: bool = True
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    
    def __post_init__(self):
        """后处理：从环境变量获取API密钥"""
        if self.api_key is None and self.provider == "openai":
            self.api_key = os.environ.get("OPENAI_API_KEY")
        if self.api_base is None and self.provider == "openai":
            self.api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")


# ============================================================
# 抽象基类
# ============================================================

class BaseEmbedder(ABC):
    """
    向量化器抽象基类
    
    所有向量化器实现都必须继承此类
    """
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型名称"""
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        pass
    
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        对单个文本进行向量化
        
        Args:
            text: 输入文本
        
        Returns:
            向量（浮点数列表）
        """
        pass
    
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        对多个文本进行批量向量化
        
        Args:
            texts: 文本列表
        
        Returns:
            向量列表
        """
        pass
    
    def embed_chunk(self, chunk: DocumentChunk) -> EmbeddedChunk:
        """
        对单个文档块进行向量化
        
        Args:
            chunk: 文档块
        
        Returns:
            向量化后的文档块
        """
        embedding = self.embed_text(chunk.content)
        
        return EmbeddedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            section_title=chunk.section_title,
            metadata=chunk.metadata,
            embedding=embedding,
            embedding_model=self.model_name,
            embedding_dimension=self.dimension
        )
    
    def embed_chunks(self, chunks: List[DocumentChunk]) -> List[EmbeddedChunk]:
        """
        对多个文档块进行批量向量化
        
        Args:
            chunks: 文档块列表
        
        Returns:
            向量化后的文档块列表
        """
        if not chunks:
            return []
        
        # 提取所有内容
        texts = [chunk.content for chunk in chunks]
        
        # 批量向量化
        embeddings = self.embed_texts(texts)
        
        # 构建结果
        embedded_chunks = []
        for chunk, embedding in zip(chunks, embeddings):
            embedded_chunks.append(EmbeddedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                section_title=chunk.section_title,
                metadata=chunk.metadata,
                embedding=embedding,
                embedding_model=self.model_name,
                embedding_dimension=self.dimension
            ))
        
        return embedded_chunks


# ============================================================
# Sentence-Transformers 实现
# ============================================================

class SentenceTransformersEmbedder(BaseEmbedder):
    """
    Sentence-Transformers 向量化器
    
    使用本地的sentence-transformers模型进行向量化
    优点：无需API调用，离线可用
    
    推荐模型：
    - paraphrase-multilingual-MiniLM-L12-v2: 多语言支持，384维
    - all-MiniLM-L6-v2: 英文模型，384维，速度快
    - all-mpnet-base-v2: 英文模型，768维，质量更高
    """
    
    def __init__(self, config: EmbeddingConfig):
        """
        初始化
        
        Args:
            config: 配置对象
        """
        self._config = config
        self._model = None
        self._dimension: Optional[int] = None
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # 延迟加载模型
        self._load_model()
    
    def _load_model(self) -> None:
        """加载模型"""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise EmbeddingModelLoadError(
                model_name=self._config.model_name,
                cause=ImportError(
                    "sentence-transformers 未安装。"
                    "请运行: pip install sentence-transformers"
                )
            )
        
        try:
            self._logger.info(f"加载模型: {self._config.model_name}")
            
            self._model = SentenceTransformer(
                self._config.model_name,
                device=self._config.device
            )
            
            # 获取向量维度
            self._dimension = self._model.get_sentence_embedding_dimension()
            
            self._logger.info(
                f"模型加载完成: {self._config.model_name}, "
                f"维度: {self._dimension}, "
                f"设备: {self._config.device}"
            )
        
        except Exception as e:
            raise EmbeddingModelLoadError(
                model_name=self._config.model_name,
                cause=e
            )
    
    @property
    def model_name(self) -> str:
        return self._config.model_name
    
    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise EmbeddingError(
                message="模型未加载，无法获取向量维度",
                model_name=self._config.model_name
            )
        return self._dimension
    
    def embed_text(self, text: str) -> List[float]:
        """对单个文本进行向量化"""
        if self._model is None:
            raise EmbeddingError(
                message="模型未加载",
                model_name=self._config.model_name
            )
        
        try:
            embedding = self._model.encode(
                text,
                normalize_embeddings=self._config.normalize,
                show_progress_bar=False
            )
            return embedding.tolist()
        
        except Exception as e:
            raise EmbeddingError(
                message=f"向量化失败: {str(e)}",
                model_name=self._config.model_name,
                cause=e
            )
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        if self._model is None:
            raise EmbeddingError(
                message="模型未加载",
                model_name=self._config.model_name
            )
        
        if not texts:
            return []
        
        try:
            self._logger.debug(f"批量向量化 {len(texts)} 个文本")
            
            embeddings = self._model.encode(
                texts,
                batch_size=self._config.batch_size,
                normalize_embeddings=self._config.normalize,
                show_progress_bar=len(texts) > 100  # 大量文本时显示进度
            )
            
            return embeddings.tolist()
        
        except Exception as e:
            raise EmbeddingError(
                message=f"批量向量化失败: {str(e)}",
                model_name=self._config.model_name,
                cause=e
            )


# ============================================================
# OpenAI Embedding 实现
# ============================================================

class OpenAIEmbedder(BaseEmbedder):
    """
    OpenAI Embedding 向量化器
    
    使用OpenAI的Embedding API进行向量化
    
    支持的模型：
    - text-embedding-ada-002: 1536维
    - text-embedding-3-small: 1536维
    - text-embedding-3-large: 3072维
    """
    
    # 模型维度映射
    MODEL_DIMENSIONS = {
        "text-embedding-ada-002": 1536,
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }
    
    def __init__(self, config: EmbeddingConfig):
        """
        初始化
        
        Args:
            config: 配置对象
        """
        self._config = config
        self._client = None
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # 验证API密钥
        if not self._config.api_key:
            raise MissingAPIKeyError(provider="OpenAI")
        
        # 初始化客户端
        self._init_client()
    
    def _init_client(self) -> None:
        """初始化OpenAI客户端"""
        try:
            from openai import OpenAI
        except ImportError:
            raise EmbeddingModelLoadError(
                model_name=self._config.model_name,
                cause=ImportError(
                    "openai 未安装。"
                    "请运行: pip install openai"
                )
            )
        
        try:
            self._client = OpenAI(
                api_key=self._config.api_key,
                base_url=self._config.api_base
            )
            self._logger.info(f"OpenAI客户端初始化完成，模型: {self._config.model_name}")
        
        except Exception as e:
            raise EmbeddingModelLoadError(
                model_name=self._config.model_name,
                cause=e
            )
    
    @property
    def model_name(self) -> str:
        return self._config.model_name
    
    @property
    def dimension(self) -> int:
        # 从模型名称推断维度
        for model_prefix, dim in self.MODEL_DIMENSIONS.items():
            if model_prefix in self._config.model_name:
                return dim
        # 默认返回ada-002的维度
        return 1536
    
    def embed_text(self, text: str) -> List[float]:
        """对单个文本进行向量化"""
        embeddings = self.embed_texts([text])
        return embeddings[0] if embeddings else []
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        if self._client is None:
            raise EmbeddingError(
                message="OpenAI客户端未初始化",
                model_name=self._config.model_name
            )
        
        if not texts:
            return []
        
        try:
            self._logger.debug(f"调用OpenAI API向量化 {len(texts)} 个文本")
            
            # 分批处理（OpenAI有批量限制）
            all_embeddings = []
            batch_size = min(self._config.batch_size, 100)  # OpenAI最大批量100
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                response = self._client.embeddings.create(
                    model=self._config.model_name,
                    input=batch
                )
                
                # 按索引排序结果
                batch_embeddings = [None] * len(batch)
                for item in response.data:
                    batch_embeddings[item.index] = item.embedding
                
                all_embeddings.extend(batch_embeddings)
            
            return all_embeddings
        
        except Exception as e:
            error_msg = str(e)
            status_code = None
            
            # 尝试提取状态码
            if hasattr(e, 'status_code'):
                status_code = e.status_code
            
            raise EmbeddingAPIError(
                message=f"OpenAI API调用失败: {error_msg}",
                provider="openai",
                status_code=status_code,
                cause=e
            )


# ============================================================
# HuggingFace 实现（简化版）
# ============================================================

class HuggingFaceEmbedder(BaseEmbedder):
    """
    HuggingFace 向量化器
    
    使用HuggingFace的transformers库进行本地向量化
    
    注意：这是一个简化实现，使用AutoModel加载模型
    对于生产环境，建议使用sentence-transformers
    """
    
    def __init__(self, config: EmbeddingConfig):
        """
        初始化
        
        Args:
            config: 配置对象
        """
        self._config = config
        self._model = None
        self._tokenizer = None
        self._dimension: Optional[int] = None
        self._logger = logging.getLogger(self.__class__.__name__)
        
        self._load_model()
    
    def _load_model(self) -> None:
        """加载模型"""
        try:
            from transformers import AutoModel, AutoTokenizer
            import torch
        except ImportError:
            raise EmbeddingModelLoadError(
                model_name=self._config.model_name,
                cause=ImportError(
                    "transformers 或 torch 未安装。"
                    "请运行: pip install transformers torch"
                )
            )
        
        try:
            self._logger.info(f"加载HuggingFace模型: {self._config.model_name}")
            
            self._tokenizer = AutoTokenizer.from_pretrained(self._config.model_name)
            self._model = AutoModel.from_pretrained(self._config.model_name)
            
            # 移动到指定设备
            if self._config.device != "cpu":
                self._model = self._model.to(self._config.device)
            
            self._model.eval()
            
            # 获取向量维度
            self._dimension = self._model.config.hidden_size
            
            self._logger.info(
                f"模型加载完成: {self._config.model_name}, "
                f"维度: {self._dimension}"
            )
        
        except Exception as e:
            raise EmbeddingModelLoadError(
                model_name=self._config.model_name,
                cause=e
            )
    
    @property
    def model_name(self) -> str:
        return self._config.model_name
    
    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise EmbeddingError(
                message="模型未加载，无法获取向量维度",
                model_name=self._config.model_name
            )
        return self._dimension
    
    def _mean_pooling(self, model_output, attention_mask):
        """对模型输出进行平均池化"""
        import torch
        
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    
    def embed_text(self, text: str) -> List[float]:
        """对单个文本进行向量化"""
        embeddings = self.embed_texts([text])
        return embeddings[0] if embeddings else []
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        import torch
        
        if self._model is None or self._tokenizer is None:
            raise EmbeddingError(
                message="模型未加载",
                model_name=self._config.model_name
            )
        
        if not texts:
            return []
        
        try:
            all_embeddings = []
            
            for i in range(0, len(texts), self._config.batch_size):
                batch = texts[i:i + self._config.batch_size]
                
                # Tokenize
                encoded = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self._config.max_length,
                    return_tensors='pt'
                )
                
                # 移动到设备
                if self._config.device != "cpu":
                    encoded = {k: v.to(self._config.device) for k, v in encoded.items()}
                
                # 推理
                with torch.no_grad():
                    outputs = self._model(**encoded)
                
                # 池化
                embeddings = self._mean_pooling(outputs, encoded['attention_mask'])
                
                # 归一化
                if self._config.normalize:
                    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                
                all_embeddings.extend(embeddings.cpu().numpy().tolist())
            
            return all_embeddings
        
        except Exception as e:
            raise EmbeddingError(
                message=f"向量化失败: {str(e)}",
                model_name=self._config.model_name,
                cause=e
            )


# ============================================================
# 工厂和便捷函数
# ============================================================

class EmbedderFactory:
    """
    向量化器工厂
    
    根据配置创建对应的向量化器实例
    """
    
    # 提供商映射
    PROVIDERS = {
        "sentence-transformers": SentenceTransformersEmbedder,
        "openai": OpenAIEmbedder,
        "huggingface": HuggingFaceEmbedder,
    }
    
    @classmethod
    def create(cls, config: Optional[EmbeddingConfig] = None) -> BaseEmbedder:
        """
        创建向量化器
        
        Args:
            config: 配置对象，如果为None则使用默认配置
        
        Returns:
            向量化器实例
        
        Raises:
            EmbeddingError: 不支持的提供商
        """
        if config is None:
            config = EmbeddingConfig()
        
        provider = config.provider.lower()
        
        if provider not in cls.PROVIDERS:
            raise EmbeddingError(
                message=f"不支持的向量化提供商: {provider}，"
                        f"支持: {list(cls.PROVIDERS.keys())}"
            )
        
        embedder_class = cls.PROVIDERS[provider]
        return embedder_class(config)
    
    @classmethod
    def register_provider(
        cls,
        name: str,
        embedder_class: type
    ) -> None:
        """
        注册自定义提供商
        
        Args:
            name: 提供商名称
            embedder_class: 向量化器类
        """
        cls.PROVIDERS[name.lower()] = embedder_class


def create_embedder(
    provider: str = "sentence-transformers",
    model_name: Optional[str] = None,
    **kwargs
) -> BaseEmbedder:
    """
    创建向量化器的便捷函数
    
    Args:
        provider: 提供商名称
        model_name: 模型名称
        **kwargs: 其他配置参数
    
    Returns:
        向量化器实例
    """
    config_kwargs = {"provider": provider}
    
    if model_name:
        config_kwargs["model_name"] = model_name
    
    config_kwargs.update(kwargs)
    config = EmbeddingConfig(**config_kwargs)
    
    return EmbedderFactory.create(config)


def embed_texts(
    texts: List[str],
    provider: str = "sentence-transformers",
    model_name: Optional[str] = None
) -> List[List[float]]:
    """
    批量向量化文本的便捷函数
    
    Args:
        texts: 文本列表
        provider: 提供商
        model_name: 模型名称
    
    Returns:
        向量列表
    """
    embedder = create_embedder(provider=provider, model_name=model_name)
    return embedder.embed_texts(texts)


def embed_chunks(
    chunks: List[DocumentChunk],
    provider: str = "sentence-transformers",
    model_name: Optional[str] = None
) -> List[EmbeddedChunk]:
    """
    批量向量化文档块的便捷函数
    
    Args:
        chunks: 文档块列表
        provider: 提供商
        model_name: 模型名称
    
    Returns:
        向量化后的文档块列表
    """
    embedder = create_embedder(provider=provider, model_name=model_name)
    return embedder.embed_chunks(chunks)