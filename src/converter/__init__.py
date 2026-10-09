"""
文档转换模块

将各种格式的论文文件（PDF、HTML、TXT）转换为标准的Markdown格式。

主要组件：
- DocumentConverterService: 统一的转换服务入口
- BaseConverter: 转换器基类
- PDFConverter: PDF转换器
- HTMLConverter: HTML转换器
- TXTConverter: TXT转换器
- MarkdownConverter: Markdown转换器

使用示例:
    from src.converter import DocumentConverterService, DocumentInput
    
    # 创建服务
    service = DocumentConverterService()
    
    # 转换单个文档
    result = service.convert_document(
        DocumentInput(file_path="paper.pdf")
    )
    
    if result.success:
        print(result.document.content)
    
    # 使用便捷函数
    from src.converter import convert_document
    result = convert_document(DocumentInput(file_path="paper.pdf"))

错误处理:
    所有转换错误都使用 ConverterError 及其子类。
    错误码遵循 E2xxx 模式：
    - E2001: 不支持的文件类型
    - E2002: 转换失败
    - E2003: PDF解析错误
    - E2004: HTML解析错误
    - E2005: 编码错误
    - E2006: 图片提取失败
    - E2007: 表格提取失败
"""

from src.converter.base import (
    BaseConverter,
    ConversionConfig,
    ConversionContext,
    ConverterRegistry,
)
from src.converter.exceptions import (
    ConverterError,
    ConverterErrorCode,
    EncodingError,
    ErrorContext,
    FileNotFoundError,
    FileReadError,
    HTMLFetchError,
    HTMLParseError,
    ImageExtractionError,
    MetadataExtractionError,
    PDFCorruptedError,
    PDFEncryptedError,
    PDFParseError,
    TableExtractionError,
    UnsupportedFileTypeError,
)
from src.converter.html_converter import HTMLConverter
from src.converter.pdf_converter import PDFConverter
from src.converter.txt_converter import MarkdownConverter, TXTConverter
from src.converter.service import (
    DocumentConverterService,
    convert_batch,
    convert_document,
    get_converter_service,
)

# 从schemas导入常用类型
from src.models.schemas import (
    BatchConversionResult,
    BatchDocumentInput,
    ConversionResult,
    DocumentInput,
    FileType,
    MarkdownDocument,
)


__all__ = [
    # 服务类
    "DocumentConverterService",
    "get_converter_service",
    
    # 便捷函数
    "convert_document",
    "convert_batch",
    
    # 转换器基类和注册表
    "BaseConverter",
    "ConversionConfig",
    "ConversionContext",
    "ConverterRegistry",
    
    # 具体转换器
    "PDFConverter",
    "HTMLConverter",
    "TXTConverter",
    "MarkdownConverter",
    
    # 数据模型
    "DocumentInput",
    "BatchDocumentInput",
    "ConversionResult",
    "BatchConversionResult",
    "MarkdownDocument",
    "FileType",
    
    # 异常类
    "ConverterError",
    "ConverterErrorCode",
    "ErrorContext",
    "UnsupportedFileTypeError",
    "FileNotFoundError",
    "FileReadError",
    "EncodingError",
    "PDFParseError",
    "PDFEncryptedError",
    "PDFCorruptedError",
    "HTMLParseError",
    "HTMLFetchError",
    "ImageExtractionError",
    "TableExtractionError",
    "MetadataExtractionError",
]

# 版本信息
__version__ = "1.0.0"