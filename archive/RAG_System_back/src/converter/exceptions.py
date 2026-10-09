"""
文档转换模块 - 异常处理

本模块定义了文档转换过程中可能出现的所有异常类型。
所有异常都继承自 ConverterError 基类，并包含标准化的错误码。

错误码规则（2xxx系列）：
- E2001: 不支持的文件类型
- E2002: 转换失败（通用）
- E2003: PDF解析错误
- E2004: HTML解析错误
- E2005: 编码错误
- E2006: 图片提取失败
- E2007: 表格提取失败
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class ConverterErrorCode(str, Enum):
    """
    文档转换模块错误码枚举
    
    所有错误码都以 E2 开头，表示属于文档转换模块
    """
    # 通用转换错误
    UNSUPPORTED_FILE_TYPE = "E2001"
    CONVERSION_FAILED = "E2002"
    
    # PDF相关错误
    PDF_PARSE_ERROR = "E2003"
    PDF_ENCRYPTED = "E2003.1"
    PDF_CORRUPTED = "E2003.2"
    PDF_PAGE_ERROR = "E2003.3"
    
    # HTML相关错误
    HTML_PARSE_ERROR = "E2004"
    HTML_INVALID_STRUCTURE = "E2004.1"
    HTML_ENCODING_DETECT_FAILED = "E2004.2"
    HTML_FETCH_ERROR = "E2004.3"
    
    # 编码相关错误
    ENCODING_ERROR = "E2005"
    ENCODING_DETECT_FAILED = "E2005.1"
    ENCODING_DECODE_FAILED = "E2005.2"
    
    # 图片提取错误
    IMAGE_EXTRACTION_FAILED = "E2006"
    IMAGE_SAVE_FAILED = "E2006.1"
    IMAGE_INVALID_FORMAT = "E2006.2"
    
    # 表格提取错误
    TABLE_EXTRACTION_FAILED = "E2007"
    TABLE_PARSE_ERROR = "E2007.1"
    
    # 文件操作错误
    FILE_NOT_FOUND = "E2010"
    FILE_READ_ERROR = "E2011"
    FILE_WRITE_ERROR = "E2012"
    PERMISSION_DENIED = "E2013"
    
    # 元数据提取错误
    METADATA_EXTRACTION_FAILED = "E2020"


# 错误码对应的默认错误消息
ERROR_MESSAGES: Dict[ConverterErrorCode, str] = {
    ConverterErrorCode.UNSUPPORTED_FILE_TYPE: "不支持的文件类型",
    ConverterErrorCode.CONVERSION_FAILED: "文档转换失败",
    ConverterErrorCode.PDF_PARSE_ERROR: "PDF解析错误",
    ConverterErrorCode.PDF_ENCRYPTED: "PDF文件已加密，无法解析",
    ConverterErrorCode.PDF_CORRUPTED: "PDF文件已损坏",
    ConverterErrorCode.PDF_PAGE_ERROR: "PDF页面处理错误",
    ConverterErrorCode.HTML_PARSE_ERROR: "HTML解析错误",
    ConverterErrorCode.HTML_INVALID_STRUCTURE: "HTML结构无效",
    ConverterErrorCode.HTML_ENCODING_DETECT_FAILED: "HTML编码检测失败",
    ConverterErrorCode.HTML_FETCH_ERROR: "获取HTML内容失败",
    ConverterErrorCode.ENCODING_ERROR: "编码错误",
    ConverterErrorCode.ENCODING_DETECT_FAILED: "编码检测失败",
    ConverterErrorCode.ENCODING_DECODE_FAILED: "解码失败",
    ConverterErrorCode.IMAGE_EXTRACTION_FAILED: "图片提取失败",
    ConverterErrorCode.IMAGE_SAVE_FAILED: "图片保存失败",
    ConverterErrorCode.IMAGE_INVALID_FORMAT: "图片格式无效",
    ConverterErrorCode.TABLE_EXTRACTION_FAILED: "表格提取失败",
    ConverterErrorCode.TABLE_PARSE_ERROR: "表格解析错误",
    ConverterErrorCode.FILE_NOT_FOUND: "文件未找到",
    ConverterErrorCode.FILE_READ_ERROR: "文件读取错误",
    ConverterErrorCode.FILE_WRITE_ERROR: "文件写入错误",
    ConverterErrorCode.PERMISSION_DENIED: "权限不足",
    ConverterErrorCode.METADATA_EXTRACTION_FAILED: "元数据提取失败",
}


@dataclass
class ErrorContext:
    """
    错误上下文信息
    
    用于存储错误发生时的详细上下文，便于调试和日志记录
    """
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    page_number: Optional[int] = None
    operation: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {}
        if self.file_path:
            result["file_path"] = self.file_path
        if self.file_type:
            result["file_type"] = self.file_type
        if self.page_number is not None:
            result["page_number"] = self.page_number
        if self.operation:
            result["operation"] = self.operation
        if self.extra:
            result.update(self.extra)
        return result


class ConverterError(Exception):
    """
    文档转换模块异常基类
    
    所有转换相关的异常都应继承此类。
    提供标准化的错误码、错误消息和上下文信息。
    
    属性:
        code: 错误码
        message: 错误消息
        context: 错误上下文
        cause: 原始异常（如果有）
        timestamp: 错误发生时间
    
    使用示例:
        raise ConverterError(
            code=ConverterErrorCode.PDF_PARSE_ERROR,
            message="无法解析PDF第5页",
            context=ErrorContext(file_path="test.pdf", page_number=5)
        )
    """
    
    def __init__(
        self,
        code: ConverterErrorCode,
        message: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, "未知错误")
        self.context = context or ErrorContext()
        self.cause = cause
        self.timestamp = datetime.utcnow()
        
        # 构建完整的错误消息
        full_message = f"[{self.code.value}] {self.message}"
        if self.context.file_path:
            full_message += f" (文件: {self.context.file_path})"
        
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
        code: ConverterErrorCode = ConverterErrorCode.CONVERSION_FAILED,
        context: Optional[ErrorContext] = None
    ) -> "ConverterError":
        """
        从其他异常创建ConverterError
        
        Args:
            exception: 原始异常
            code: 错误码
            context: 错误上下文
        
        Returns:
            ConverterError实例
        """
        return cls(
            code=code,
            message=str(exception),
            context=context,
            cause=exception
        )


class UnsupportedFileTypeError(ConverterError):
    """不支持的文件类型异常"""
    
    def __init__(
        self,
        file_type: str,
        supported_types: Optional[list] = None,
        context: Optional[ErrorContext] = None
    ):
        message = f"不支持的文件类型: {file_type}"
        if supported_types:
            message += f"，支持的类型: {', '.join(supported_types)}"
        
        if context is None:
            context = ErrorContext()
        context.file_type = file_type
        
        super().__init__(
            code=ConverterErrorCode.UNSUPPORTED_FILE_TYPE,
            message=message,
            context=context
        )
        self.file_type = file_type
        self.supported_types = supported_types or []


class FileNotFoundError(ConverterError):
    """文件未找到异常"""
    
    def __init__(
        self,
        file_path: str,
        context: Optional[ErrorContext] = None
    ):
        if context is None:
            context = ErrorContext()
        context.file_path = file_path
        
        super().__init__(
            code=ConverterErrorCode.FILE_NOT_FOUND,
            message=f"文件未找到: {file_path}",
            context=context
        )
        self.file_path = file_path


class FileReadError(ConverterError):
    """文件读取错误"""
    
    def __init__(
        self,
        file_path: str,
        cause: Optional[Exception] = None,
        context: Optional[ErrorContext] = None
    ):
        if context is None:
            context = ErrorContext()
        context.file_path = file_path
        context.operation = "read"
        
        super().__init__(
            code=ConverterErrorCode.FILE_READ_ERROR,
            message=f"读取文件失败: {file_path}",
            context=context,
            cause=cause
        )


class EncodingError(ConverterError):
    """编码错误"""
    
    def __init__(
        self,
        message: str,
        encoding: Optional[str] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        if context is None:
            context = ErrorContext()
        if encoding:
            context.extra["encoding"] = encoding
        
        super().__init__(
            code=ConverterErrorCode.ENCODING_ERROR,
            message=message,
            context=context,
            cause=cause
        )
        self.encoding = encoding


class PDFParseError(ConverterError):
    """PDF解析错误"""
    
    def __init__(
        self,
        message: str,
        page_number: Optional[int] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
        error_subtype: Optional[ConverterErrorCode] = None
    ):
        if context is None:
            context = ErrorContext()
        if page_number is not None:
            context.page_number = page_number
        
        code = error_subtype or ConverterErrorCode.PDF_PARSE_ERROR
        
        super().__init__(
            code=code,
            message=message,
            context=context,
            cause=cause
        )
        self.page_number = page_number


class PDFEncryptedError(PDFParseError):
    """PDF加密错误"""
    
    def __init__(
        self,
        file_path: str,
        context: Optional[ErrorContext] = None
    ):
        if context is None:
            context = ErrorContext()
        context.file_path = file_path
        
        super().__init__(
            message=f"PDF文件已加密，无法处理: {file_path}",
            context=context,
            error_subtype=ConverterErrorCode.PDF_ENCRYPTED
        )


class PDFCorruptedError(PDFParseError):
    """PDF损坏错误"""
    
    def __init__(
        self,
        file_path: str,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        if context is None:
            context = ErrorContext()
        context.file_path = file_path
        
        super().__init__(
            message=f"PDF文件已损坏: {file_path}",
            context=context,
            cause=cause,
            error_subtype=ConverterErrorCode.PDF_CORRUPTED
        )


class HTMLParseError(ConverterError):
    """HTML解析错误"""
    
    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
        error_subtype: Optional[ConverterErrorCode] = None
    ):
        code = error_subtype or ConverterErrorCode.HTML_PARSE_ERROR
        
        super().__init__(
            code=code,
            message=message,
            context=context,
            cause=cause
        )


class HTMLFetchError(HTMLParseError):
    """HTML获取错误（用于在线HTML）"""
    
    def __init__(
        self,
        url: str,
        status_code: Optional[int] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        if context is None:
            context = ErrorContext()
        context.extra["url"] = url
        if status_code:
            context.extra["status_code"] = status_code
        
        message = f"获取HTML内容失败: {url}"
        if status_code:
            message += f" (状态码: {status_code})"
        
        super().__init__(
            message=message,
            context=context,
            cause=cause,
            error_subtype=ConverterErrorCode.HTML_FETCH_ERROR
        )
        self.url = url
        self.status_code = status_code


class ImageExtractionError(ConverterError):
    """图片提取错误"""
    
    def __init__(
        self,
        message: str,
        image_index: Optional[int] = None,
        page_number: Optional[int] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        if context is None:
            context = ErrorContext()
        if page_number is not None:
            context.page_number = page_number
        if image_index is not None:
            context.extra["image_index"] = image_index
        
        super().__init__(
            code=ConverterErrorCode.IMAGE_EXTRACTION_FAILED,
            message=message,
            context=context,
            cause=cause
        )
        self.image_index = image_index
        self.page_number = page_number


class TableExtractionError(ConverterError):
    """表格提取错误"""
    
    def __init__(
        self,
        message: str,
        table_index: Optional[int] = None,
        page_number: Optional[int] = None,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        if context is None:
            context = ErrorContext()
        if page_number is not None:
            context.page_number = page_number
        if table_index is not None:
            context.extra["table_index"] = table_index
        
        super().__init__(
            code=ConverterErrorCode.TABLE_EXTRACTION_FAILED,
            message=message,
            context=context,
            cause=cause
        )
        self.table_index = table_index
        self.page_number = page_number


class MetadataExtractionError(ConverterError):
    """元数据提取错误"""
    
    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(
            code=ConverterErrorCode.METADATA_EXTRACTION_FAILED,
            message=message,
            context=context,
            cause=cause
        )


# ============================================================
# 错误处理工具函数
# ============================================================

def validate_error_code(code: str) -> bool:
    """
    验证错误码是否有效
    
    Args:
        code: 错误码字符串
    
    Returns:
        是否为有效的转换模块错误码
    """
    try:
        ConverterErrorCode(code)
        return True
    except ValueError:
        return False


def get_error_message(code: ConverterErrorCode) -> str:
    """
    获取错误码对应的默认消息
    
    Args:
        code: 错误码
    
    Returns:
        错误消息
    """
    return ERROR_MESSAGES.get(code, "未知错误")


def is_converter_error(code: str) -> bool:
    """
    判断错误码是否属于转换模块（E2xxx）
    
    Args:
        code: 错误码字符串
    
    Returns:
        是否为转换模块错误码
    """
    return code.startswith("E2")


def create_error_response(
    error: ConverterError,
    include_traceback: bool = False
) -> Dict[str, Any]:
    """
    创建标准化的错误响应
    
    Args:
        error: ConverterError实例
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