"""
RAG存储模块 - 异常处理

本模块定义了RAG存储过程中可能出现的所有异常类型。
所有异常都继承自 StorageError 基类，并包含标准化的错误码。

错误码规则（3xxx系列）：
- E3001: 存储连接失败
- E3002: 向量化失败
- E3003: 分块失败
- E3004: 文档已存在
- E3005: 文档未找到
- E3006: 集合未找到
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class StorageErrorCode(str, Enum):
    """
    RAG存储模块错误码枚举
    
    所有错误码都以 E3 开头，表示属于RAG存储模块
    """
    # 存储连接错误 (E3001.x)
    STORAGE_CONNECTION_FAILED = "E3001"
    DATABASE_INIT_FAILED = "E3001.1"
    DATABASE_CONNECTION_LOST = "E3001.2"
    DATABASE_TIMEOUT = "E3001.3"
    
    # 向量化错误 (E3002.x)
    EMBEDDING_FAILED = "E3002"
    EMBEDDING_MODEL_NOT_FOUND = "E3002.1"
    EMBEDDING_MODEL_LOAD_FAILED = "E3002.2"
    EMBEDDING_DIMENSION_MISMATCH = "E3002.3"
    EMBEDDING_BATCH_FAILED = "E3002.4"
    EMBEDDING_API_ERROR = "E3002.5"
    
    # 分块错误 (E3003.x)
    CHUNKING_FAILED = "E3003"
    INVALID_CHUNK_CONFIG = "E3003.1"
    CHUNK_TOO_SMALL = "E3003.2"
    CHUNK_TOO_LARGE = "E3003.3"
    EMPTY_CONTENT = "E3003.4"
    
    # 文档存在性错误 (E3004.x, E3005.x)
    DOCUMENT_EXISTS = "E3004"
    DOCUMENT_NOT_FOUND = "E3005"
    DOCUMENT_UPDATE_FAILED = "E3005.1"
    DOCUMENT_DELETE_FAILED = "E3005.2"
    
    # 集合错误 (E3006.x)
    COLLECTION_NOT_FOUND = "E3006"
    COLLECTION_CREATE_FAILED = "E3006.1"
    COLLECTION_DELETE_FAILED = "E3006.2"
    COLLECTION_ALREADY_EXISTS = "E3006.3"
    
    # 数据操作错误 (E3010.x)
    INSERT_FAILED = "E3010"
    QUERY_FAILED = "E3011"
    UPDATE_FAILED = "E3012"
    DELETE_FAILED = "E3013"
    
    # 配置错误 (E3020.x)
    INVALID_CONFIG = "E3020"
    MISSING_API_KEY = "E3020.1"
    INVALID_MODEL_NAME = "E3020.2"


# 错误码对应的默认错误消息
ERROR_MESSAGES: Dict[StorageErrorCode, str] = {
    # 存储连接错误
    StorageErrorCode.STORAGE_CONNECTION_FAILED: "存储服务连接失败",
    StorageErrorCode.DATABASE_INIT_FAILED: "数据库初始化失败",
    StorageErrorCode.DATABASE_CONNECTION_LOST: "数据库连接丢失",
    StorageErrorCode.DATABASE_TIMEOUT: "数据库操作超时",
    
    # 向量化错误
    StorageErrorCode.EMBEDDING_FAILED: "向量化失败",
    StorageErrorCode.EMBEDDING_MODEL_NOT_FOUND: "向量化模型未找到",
    StorageErrorCode.EMBEDDING_MODEL_LOAD_FAILED: "向量化模型加载失败",
    StorageErrorCode.EMBEDDING_DIMENSION_MISMATCH: "向量维度不匹配",
    StorageErrorCode.EMBEDDING_BATCH_FAILED: "批量向量化失败",
    StorageErrorCode.EMBEDDING_API_ERROR: "向量化API调用失败",
    
    # 分块错误
    StorageErrorCode.CHUNKING_FAILED: "文档分块失败",
    StorageErrorCode.INVALID_CHUNK_CONFIG: "分块配置无效",
    StorageErrorCode.CHUNK_TOO_SMALL: "分块大小过小",
    StorageErrorCode.CHUNK_TOO_LARGE: "分块大小过大",
    StorageErrorCode.EMPTY_CONTENT: "文档内容为空",
    
    # 文档存在性错误
    StorageErrorCode.DOCUMENT_EXISTS: "文档已存在",
    StorageErrorCode.DOCUMENT_NOT_FOUND: "文档未找到",
    StorageErrorCode.DOCUMENT_UPDATE_FAILED: "文档更新失败",
    StorageErrorCode.DOCUMENT_DELETE_FAILED: "文档删除失败",
    
    # 集合错误
    StorageErrorCode.COLLECTION_NOT_FOUND: "集合未找到",
    StorageErrorCode.COLLECTION_CREATE_FAILED: "集合创建失败",
    StorageErrorCode.COLLECTION_DELETE_FAILED: "集合删除失败",
    StorageErrorCode.COLLECTION_ALREADY_EXISTS: "集合已存在",
    
    # 数据操作错误
    StorageErrorCode.INSERT_FAILED: "数据插入失败",
    StorageErrorCode.QUERY_FAILED: "数据查询失败",
    StorageErrorCode.UPDATE_FAILED: "数据更新失败",
    StorageErrorCode.DELETE_FAILED: "数据删除失败",
    
    # 配置错误
    StorageErrorCode.INVALID_CONFIG: "配置无效",
    StorageErrorCode.MISSING_API_KEY: "缺少API密钥",
    StorageErrorCode.INVALID_MODEL_NAME: "无效的模型名称",
}


@dataclass
class StorageErrorContext:
    """
    错误上下文信息
    
    用于存储错误发生时的详细上下文，便于调试和日志记录
    """
    document_id: Optional[str] = None
    collection_name: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    operation: Optional[str] = None
    model_name: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {}
        if self.document_id:
            result["document_id"] = self.document_id
        if self.collection_name:
            result["collection_name"] = self.collection_name
        if self.chunk_id:
            result["chunk_id"] = self.chunk_id
        if self.chunk_index is not None:
            result["chunk_index"] = self.chunk_index
        if self.operation:
            result["operation"] = self.operation
        if self.model_name:
            result["model_name"] = self.model_name
        if self.extra:
            result.update(self.extra)
        return result


class StorageError(Exception):
    """
    RAG存储模块异常基类
    
    所有存储相关的异常都应继承此类。
    提供标准化的错误码、错误消息和上下文信息。
    
    属性:
        code: 错误码
        message: 错误消息
        context: 错误上下文
        cause: 原始异常（如果有）
        timestamp: 错误发生时间
    
    使用示例:
        raise StorageError(
            code=StorageErrorCode.EMBEDDING_FAILED,
            message="向量化文档失败",
            context=StorageErrorContext(document_id="doc_123")
        )
    """
    
    def __init__(
        self,
        code: StorageErrorCode,
        message: Optional[str] = None,
        context: Optional[StorageErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, "未知错误")
        self.context = context or StorageErrorContext()
        self.cause = cause
        self.timestamp = datetime.utcnow()
        
        # 构建完整的错误消息
        full_message = f"[{self.code.value}] {self.message}"
        if self.context.document_id:
            full_message += f" (文档: {self.context.document_id})"
        if self.context.collection_name:
            full_message += f" (集合: {self.context.collection_name})"
        
        super().__init__(full_message)
    
    def to_dict(self, include_traceback: bool = False) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Args:
            include_traceback: 是否包含堆栈信息（调试模式下使用）
        
        Returns:
            包含错误详情的字典
        """
        result = {
            "code": self.code.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context.to_dict()
        }
        
        if self.cause:
            result["cause"] = str(self.cause)
        
        if include_traceback:
            result["traceback"] = traceback.format_exc()
        
        return result
    
    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        code: StorageErrorCode = StorageErrorCode.STORAGE_CONNECTION_FAILED,
        context: Optional[StorageErrorContext] = None
    ) -> "StorageError":
        """
        从其他异常创建StorageError
        
        Args:
            exception: 原始异常
            code: 错误码
            context: 错误上下文
        
        Returns:
            StorageError实例
        """
        return cls(
            code=code,
            message=str(exception),
            context=context,
            cause=exception
        )


# ============================================================
# 存储连接相关异常
# ============================================================

class StorageConnectionError(StorageError):
    """存储连接错误"""
    
    def __init__(
        self,
        message: str = "存储服务连接失败",
        context: Optional[StorageErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(
            code=StorageErrorCode.STORAGE_CONNECTION_FAILED,
            message=message,
            context=context,
            cause=cause
        )


class DatabaseInitError(StorageError):
    """数据库初始化错误"""
    
    def __init__(
        self,
        message: str = "数据库初始化失败",
        db_type: Optional[str] = None,
        context: Optional[StorageErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        if context is None:
            context = StorageErrorContext()
        if db_type:
            context.extra["db_type"] = db_type
        
        super().__init__(
            code=StorageErrorCode.DATABASE_INIT_FAILED,
            message=message,
            context=context,
            cause=cause
        )
        self.db_type = db_type


# ============================================================
# 向量化相关异常
# ============================================================

class EmbeddingError(StorageError):
    """向量化错误基类"""
    
    def __init__(
        self,
        message: str = "向量化失败",
        model_name: Optional[str] = None,
        context: Optional[StorageErrorContext] = None,
        cause: Optional[Exception] = None,
        error_code: Optional[StorageErrorCode] = None
    ):
        if context is None:
            context = StorageErrorContext()
        if model_name:
            context.model_name = model_name
        
        super().__init__(
            code=error_code or StorageErrorCode.EMBEDDING_FAILED,
            message=message,
            context=context,
            cause=cause
        )
        self.model_name = model_name


class EmbeddingModelNotFoundError(EmbeddingError):
    """向量化模型未找到"""
    
    def __init__(
        self,
        model_name: str,
        context: Optional[StorageErrorContext] = None
    ):
        super().__init__(
            message=f"向量化模型未找到: {model_name}",
            model_name=model_name,
            context=context,
            error_code=StorageErrorCode.EMBEDDING_MODEL_NOT_FOUND
        )


class EmbeddingModelLoadError(EmbeddingError):
    """向量化模型加载失败"""
    
    def __init__(
        self,
        model_name: str,
        context: Optional[StorageErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(
            message=f"向量化模型加载失败: {model_name}",
            model_name=model_name,
            context=context,
            cause=cause,
            error_code=StorageErrorCode.EMBEDDING_MODEL_LOAD_FAILED
        )


class EmbeddingDimensionMismatchError(EmbeddingError):
    """向量维度不匹配"""
    
    def __init__(
        self,
        expected_dim: int,
        actual_dim: int,
        context: Optional[StorageErrorContext] = None
    ):
        if context is None:
            context = StorageErrorContext()
        context.extra["expected_dimension"] = expected_dim
        context.extra["actual_dimension"] = actual_dim
        
        super().__init__(
            message=f"向量维度不匹配: 期望 {expected_dim}, 实际 {actual_dim}",
            context=context,
            error_code=StorageErrorCode.EMBEDDING_DIMENSION_MISMATCH
        )
        self.expected_dim = expected_dim
        self.actual_dim = actual_dim


class EmbeddingAPIError(EmbeddingError):
    """向量化API调用失败"""
    
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        context: Optional[StorageErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        if context is None:
            context = StorageErrorContext()
        if provider:
            context.extra["provider"] = provider
        if status_code:
            context.extra["status_code"] = status_code
        
        super().__init__(
            message=message,
            context=context,
            cause=cause,
            error_code=StorageErrorCode.EMBEDDING_API_ERROR
        )
        self.provider = provider
        self.status_code = status_code


# ============================================================
# 分块相关异常
# ============================================================

class ChunkingError(StorageError):
    """分块错误基类"""
    
    def __init__(
        self,
        message: str = "文档分块失败",
        document_id: Optional[str] = None,
        context: Optional[StorageErrorContext] = None,
        cause: Optional[Exception] = None,
        error_code: Optional[StorageErrorCode] = None
    ):
        if context is None:
            context = StorageErrorContext()
        if document_id:
            context.document_id = document_id
        
        super().__init__(
            code=error_code or StorageErrorCode.CHUNKING_FAILED,
            message=message,
            context=context,
            cause=cause
        )


class InvalidChunkConfigError(ChunkingError):
    """分块配置无效"""
    
    def __init__(
        self,
        message: str,
        config_field: Optional[str] = None,
        context: Optional[StorageErrorContext] = None
    ):
        if context is None:
            context = StorageErrorContext()
        if config_field:
            context.extra["config_field"] = config_field
        
        super().__init__(
            message=message,
            context=context,
            error_code=StorageErrorCode.INVALID_CHUNK_CONFIG
        )
        self.config_field = config_field


class EmptyContentError(ChunkingError):
    """文档内容为空"""
    
    def __init__(
        self,
        document_id: Optional[str] = None,
        context: Optional[StorageErrorContext] = None
    ):
        super().__init__(
            message="文档内容为空，无法进行分块",
            document_id=document_id,
            context=context,
            error_code=StorageErrorCode.EMPTY_CONTENT
        )


# ============================================================
# 文档相关异常
# ============================================================

class DocumentExistsError(StorageError):
    """文档已存在"""
    
    def __init__(
        self,
        document_id: str,
        collection_name: Optional[str] = None,
        context: Optional[StorageErrorContext] = None
    ):
        if context is None:
            context = StorageErrorContext()
        context.document_id = document_id
        if collection_name:
            context.collection_name = collection_name
        
        super().__init__(
            code=StorageErrorCode.DOCUMENT_EXISTS,
            message=f"文档已存在: {document_id}",
            context=context
        )
        self.document_id = document_id
        self.collection_name = collection_name


class DocumentNotFoundError(StorageError):
    """文档未找到"""
    
    def __init__(
        self,
        document_id: str,
        collection_name: Optional[str] = None,
        context: Optional[StorageErrorContext] = None
    ):
        if context is None:
            context = StorageErrorContext()
        context.document_id = document_id
        if collection_name:
            context.collection_name = collection_name
        
        super().__init__(
            code=StorageErrorCode.DOCUMENT_NOT_FOUND,
            message=f"文档未找到: {document_id}",
            context=context
        )
        self.document_id = document_id
        self.collection_name = collection_name


# ============================================================
# 集合相关异常
# ============================================================

class CollectionNotFoundError(StorageError):
    """集合未找到"""
    
    def __init__(
        self,
        collection_name: str,
        context: Optional[StorageErrorContext] = None
    ):
        if context is None:
            context = StorageErrorContext()
        context.collection_name = collection_name
        
        super().__init__(
            code=StorageErrorCode.COLLECTION_NOT_FOUND,
            message=f"集合未找到: {collection_name}",
            context=context
        )
        self.collection_name = collection_name


class CollectionExistsError(StorageError):
    """集合已存在"""
    
    def __init__(
        self,
        collection_name: str,
        context: Optional[StorageErrorContext] = None
    ):
        if context is None:
            context = StorageErrorContext()
        context.collection_name = collection_name
        
        super().__init__(
            code=StorageErrorCode.COLLECTION_ALREADY_EXISTS,
            message=f"集合已存在: {collection_name}",
            context=context
        )
        self.collection_name = collection_name


class CollectionCreateError(StorageError):
    """集合创建失败"""
    
    def __init__(
        self,
        collection_name: str,
        context: Optional[StorageErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        if context is None:
            context = StorageErrorContext()
        context.collection_name = collection_name
        
        super().__init__(
            code=StorageErrorCode.COLLECTION_CREATE_FAILED,
            message=f"集合创建失败: {collection_name}",
            context=context,
            cause=cause
        )
        self.collection_name = collection_name


# ============================================================
# 配置相关异常
# ============================================================

class ConfigError(StorageError):
    """配置错误"""
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        context: Optional[StorageErrorContext] = None,
        error_code: Optional[StorageErrorCode] = None
    ):
        if context is None:
            context = StorageErrorContext()
        if config_key:
            context.extra["config_key"] = config_key
        
        super().__init__(
            code=error_code or StorageErrorCode.INVALID_CONFIG,
            message=message,
            context=context
        )
        self.config_key = config_key


class MissingAPIKeyError(ConfigError):
    """缺少API密钥"""
    
    def __init__(
        self,
        provider: str,
        context: Optional[StorageErrorContext] = None
    ):
        if context is None:
            context = StorageErrorContext()
        context.extra["provider"] = provider
        
        super().__init__(
            message=f"缺少 {provider} 的API密钥",
            context=context,
            error_code=StorageErrorCode.MISSING_API_KEY
        )
        self.provider = provider


# ============================================================
# 错误处理工具函数
# ============================================================

def validate_error_code(code: str) -> bool:
    """
    验证错误码是否有效
    
    Args:
        code: 错误码字符串
    
    Returns:
        是否为有效的存储模块错误码
    """
    try:
        StorageErrorCode(code)
        return True
    except ValueError:
        # 尝试匹配带子错误码的格式 (如 E3001.1)
        base_code = code.split(".")[0]
        try:
            StorageErrorCode(base_code)
            return True
        except ValueError:
            return False


def get_error_message(code: StorageErrorCode) -> str:
    """
    获取错误码对应的默认消息
    
    Args:
        code: 错误码
    
    Returns:
        错误消息
    """
    return ERROR_MESSAGES.get(code, "未知错误")


def is_storage_error(code: str) -> bool:
    """
    判断错误码是否属于存储模块（E3xxx）
    
    Args:
        code: 错误码字符串
    
    Returns:
        是否为存储模块错误码
    """
    return code.startswith("E3")


def create_error_response(
    error: StorageError,
    include_traceback: bool = False
) -> Dict[str, Any]:
    """
    创建标准化的错误响应
    
    Args:
        error: StorageError实例
        include_traceback: 是否包含堆栈信息
    
    Returns:
        错误响应字典
    """
    from src.models.schemas import ProcessingStatus
    
    return {
        "success": False,
        "status": ProcessingStatus.FAILED.value,
        "error": error.to_dict(include_traceback=include_traceback),
        "timestamp": error.timestamp.isoformat()
    }


def wrap_exception(
    exception: Exception,
    operation: str,
    context: Optional[StorageErrorContext] = None
) -> StorageError:
    """
    将通用异常包装为StorageError
    
    根据异常类型自动选择合适的错误码
    
    Args:
        exception: 原始异常
        operation: 操作名称
        context: 错误上下文
    
    Returns:
        StorageError实例
    """
    if context is None:
        context = StorageErrorContext()
    context.operation = operation
    
    # 根据异常类型选择错误码
    exception_type = type(exception).__name__
    
    if "connection" in exception_type.lower() or "connect" in str(exception).lower():
        code = StorageErrorCode.STORAGE_CONNECTION_FAILED
    elif "timeout" in exception_type.lower() or "timeout" in str(exception).lower():
        code = StorageErrorCode.DATABASE_TIMEOUT
    elif "not found" in str(exception).lower():
        code = StorageErrorCode.DOCUMENT_NOT_FOUND
    elif "already exists" in str(exception).lower():
        code = StorageErrorCode.DOCUMENT_EXISTS
    else:
        code = StorageErrorCode.STORAGE_CONNECTION_FAILED
    
    return StorageError.from_exception(exception, code=code, context=context)