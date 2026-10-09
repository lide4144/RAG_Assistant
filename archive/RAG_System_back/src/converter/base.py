"""
文档转换模块 - 基础转换器接口

定义了所有文档转换器必须实现的抽象接口和通用逻辑。
每个具体的转换器（PDF、HTML、TXT）都应继承 BaseConverter 类。

设计原则：
1. 统一的接口：所有转换器提供相同的方法签名
2. 可扩展性：易于添加新的文件格式支持
3. 错误处理：统一的异常处理机制
4. 元数据提取：自动提取文档元数据
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from src.models.schemas import (
    BaseMetadata,
    ConversionResult,
    DocumentInput,
    FileType,
    ImageInfo,
    MarkdownDocument,
    ProcessingStatus,
    SourceInfo,
    TableInfo,
)
from src.converter.exceptions import (
    ConverterError,
    ConverterErrorCode,
    ErrorContext,
    FileNotFoundError,
    FileReadError,
    UnsupportedFileTypeError,
)
from src.utils.helpers import (
    calculate_file_hash,
    count_words,
    detect_file_type,
    extract_sections,
    get_file_size,
    is_valid_file,
    timer,
)


# 获取模块日志记录器
logger = logging.getLogger(__name__)


@dataclass
class ConversionConfig:
    """
    转换配置
    
    定义文档转换过程中的各种选项和参数。
    可以在创建转换器时传入，也可以在每次转换时覆盖。
    
    Attributes:
        extract_images: 是否提取图片
        extract_tables: 是否提取表格
        min_image_size: 最小图片尺寸（像素），小于此尺寸的图片会被忽略
        image_format: 图片输出格式
        image_quality: 图片质量（1-100，仅jpg格式有效）
        images_dir: 图片保存目录
        output_dir: 输出目录
        preserve_links: 是否保留链接
        ocr_enabled: 是否启用OCR
        ocr_language: OCR语言
        default_encoding: 默认文本编码
        detect_encoding: 是否自动检测编码
    """
    # 通用配置
    extract_images: bool = True
    extract_tables: bool = True
    
    # 图片配置
    min_image_size: int = 100
    image_format: str = "png"
    image_quality: int = 85
    images_dir: Optional[str] = None
    
    # 输出配置
    output_dir: Optional[str] = None
    
    # HTML配置
    preserve_links: bool = True
    content_selectors: List[str] = field(default_factory=lambda: [
        "article", ".content", ".article-content", "main", "#content", "body"
    ])
    remove_selectors: List[str] = field(default_factory=lambda: [
        "script", "style", "nav", "header", "footer", ".sidebar", ".advertisement"
    ])
    
    # PDF配置
    ocr_enabled: bool = False
    ocr_language: str = "chi_sim+eng"
    ocr_dpi: int = 300
    table_extraction_method: str = "lattice"
    
    # 文本配置
    default_encoding: str = "utf-8"
    detect_encoding: bool = True
    
    # 调试配置
    debug: bool = False


@dataclass
class ConversionContext:
    """
    转换上下文
    
    在转换过程中传递的上下文信息，包含文件信息和中间结果。
    
    Attributes:
        input: 原始输入
        config: 转换配置
        file_path: 文件路径
        file_type: 文件类型
        file_size: 文件大小
        file_hash: 文件哈希
        document_id: 文档ID
        warnings: 警告信息列表
        images: 提取的图片列表
        tables: 提取的表格列表
        metadata: 提取的元数据
    """
    input: DocumentInput
    config: ConversionConfig
    file_path: Path
    file_type: FileType
    file_size: int = 0
    file_hash: str = ""
    document_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    warnings: List[str] = field(default_factory=list)
    images: List[ImageInfo] = field(default_factory=list)
    tables: List[TableInfo] = field(default_factory=list)
    metadata: Optional[BaseMetadata] = None
    
    def add_warning(self, message: str) -> None:
        """添加警告信息"""
        self.warnings.append(message)
        logger.warning(f"[{self.document_id}] {message}")


class BaseConverter(ABC):
    """
    文档转换器抽象基类
    
    所有格式的转换器都必须继承此类并实现抽象方法。
    
    实现要求：
    1. 实现 supports() 方法，返回支持的文件类型
    2. 实现 _convert_content() 方法，执行实际的转换逻辑
    3. 可选实现 _extract_metadata() 方法，提取文档元数据
    
    使用示例:
        class MyConverter(BaseConverter):
            def supports(self, file_type: FileType) -> bool:
                return file_type == FileType.PDF
            
            def _convert_content(self, context: ConversionContext) -> str:
                # 实现转换逻辑
                return markdown_content
    """
    
    def __init__(self, config: Optional[ConversionConfig] = None):
        """
        初始化转换器
        
        Args:
            config: 转换配置，如果为None则使用默认配置
        """
        self.config = config or ConversionConfig()
        self._logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def supports(self, file_type: FileType) -> bool:
        """
        检查是否支持指定的文件类型
        
        Args:
            file_type: 文件类型枚举
        
        Returns:
            是否支持该文件类型
        """
        pass
    
    @abstractmethod
    def _convert_content(self, context: ConversionContext) -> str:
        """
        执行实际的内容转换
        
        子类必须实现此方法来处理具体的文件格式。
        
        Args:
            context: 转换上下文，包含文件信息和配置
        
        Returns:
            转换后的Markdown内容
        
        Raises:
            ConverterError: 转换过程中的任何错误
        """
        pass
    
    def _extract_metadata(self, context: ConversionContext) -> BaseMetadata:
        """
        提取文档元数据
        
        子类可以覆盖此方法来实现特定格式的元数据提取。
        默认实现返回空元数据或预设的元数据。
        
        Args:
            context: 转换上下文
        
        Returns:
            提取的元数据
        """
        # 使用预设的元数据或创建新的
        if context.input.metadata:
            return context.input.metadata
        return BaseMetadata()
    
    def _pre_convert(self, context: ConversionContext) -> None:
        """
        转换前的预处理钩子
        
        子类可以覆盖此方法来执行转换前的准备工作。
        
        Args:
            context: 转换上下文
        """
        pass
    
    def _post_convert(
        self,
        context: ConversionContext,
        content: str
    ) -> str:
        """
        转换后的后处理钩子
        
        子类可以覆盖此方法来执行转换后的处理。
        
        Args:
            context: 转换上下文
            content: 转换后的内容
        
        Returns:
            处理后的内容
        """
        return content
    
    def _validate_input(self, input: DocumentInput) -> None:
        """
        验证输入参数
        
        Args:
            input: 文档输入
        
        Raises:
            FileNotFoundError: 文件不存在
            UnsupportedFileTypeError: 不支持的文件类型
        """
        file_path = Path(input.file_path)
        
        # 检查文件是否存在
        if not is_valid_file(file_path):
            raise FileNotFoundError(
                file_path=str(file_path),
                context=ErrorContext(file_path=str(file_path))
            )
        
        # 检测或验证文件类型
        if input.file_type:
            file_type = input.file_type
        else:
            file_type = detect_file_type(file_path)
            if file_type is None:
                raise UnsupportedFileTypeError(
                    file_type=file_path.suffix,
                    supported_types=[t.value for t in FileType],
                    context=ErrorContext(file_path=str(file_path))
                )
        
        # 检查是否支持此类型
        if not self.supports(file_type):
            raise UnsupportedFileTypeError(
                file_type=file_type.value,
                supported_types=[t.value for t in FileType if self.supports(t)],
                context=ErrorContext(
                    file_path=str(file_path),
                    file_type=file_type.value
                )
            )
    
    def _create_context(
        self,
        input: DocumentInput,
        config: Optional[ConversionConfig] = None
    ) -> ConversionContext:
        """
        创建转换上下文
        
        Args:
            input: 文档输入
            config: 转换配置（可选，覆盖默认配置）
        
        Returns:
            初始化的转换上下文
        """
        file_path = Path(input.file_path)
        
        # 检测文件类型
        file_type = input.file_type
        if file_type is None:
            file_type = detect_file_type(file_path)
        
        # 获取文件信息
        file_size = get_file_size(file_path)
        file_hash = calculate_file_hash(file_path)
        
        # 合并配置
        effective_config = config or self.config
        
        return ConversionContext(
            input=input,
            config=effective_config,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            file_hash=file_hash,
        )
    
    def _create_source_info(self, context: ConversionContext) -> SourceInfo:
        """
        创建来源信息
        
        Args:
            context: 转换上下文
        
        Returns:
            来源信息对象
        """
        return SourceInfo(
            original_file_path=str(context.file_path.absolute()),
            original_file_type=context.file_type,
            original_file_size_bytes=context.file_size,
            original_file_hash=context.file_hash,
            conversion_timestamp=datetime.utcnow(),
        )
    
    def _create_document(
        self,
        context: ConversionContext,
        content: str,
        page_count: Optional[int] = None
    ) -> MarkdownDocument:
        """
        创建Markdown文档对象
        
        Args:
            context: 转换上下文
            content: Markdown内容
            page_count: 页数（可选）
        
        Returns:
            MarkdownDocument对象
        """
        # 提取章节
        sections = extract_sections(content)
        
        # 计算字数
        word_count = count_words(content)
        
        return MarkdownDocument(
            document_id=context.document_id,
            content=content,
            metadata=context.metadata or BaseMetadata(),
            source_info=self._create_source_info(context),
            images=context.images if context.images else None,
            tables=context.tables if context.tables else None,
            sections=sections if sections else None,
            word_count=word_count,
            page_count=page_count,
        )
    
    def _create_success_result(
        self,
        document: MarkdownDocument,
        processing_time_ms: float,
        warnings: Optional[List[str]] = None
    ) -> ConversionResult:
        """
        创建成功的转换结果
        
        Args:
            document: 转换后的文档
            processing_time_ms: 处理耗时
            warnings: 警告信息
        
        Returns:
            ConversionResult对象
        """
        return ConversionResult(
            success=True,
            status=ProcessingStatus.SUCCESS,
            message="转换成功",
            processing_time_ms=processing_time_ms,
            document=document,
            warnings=warnings,
        )
    
    def _create_error_result(
        self,
        error: ConverterError,
        processing_time_ms: float
    ) -> ConversionResult:
        """
        创建失败的转换结果
        
        Args:
            error: 错误对象
            processing_time_ms: 处理耗时
        
        Returns:
            ConversionResult对象
        """
        return ConversionResult(
            success=False,
            status=ProcessingStatus.FAILED,
            message=error.message,
            processing_time_ms=processing_time_ms,
            error_details=str(error),
        )
    
    def convert(
        self,
        input: DocumentInput,
        config: Optional[ConversionConfig] = None
    ) -> ConversionResult:
        """
        转换文档
        
        这是转换器的主要入口方法。它执行以下步骤：
        1. 验证输入
        2. 创建转换上下文
        3. 预处理
        4. 执行转换
        5. 提取元数据
        6. 后处理
        7. 创建结果
        
        Args:
            input: DocumentInput对象
            config: 可选的配置覆盖
        
        Returns:
            ConversionResult: 包含MarkdownDocument或错误信息
        """
        with timer() as t:
            try:
                # 1. 验证输入
                self._validate_input(input)
                
                # 2. 创建上下文
                context = self._create_context(input, config)
                self._logger.info(
                    f"开始转换文档: {context.file_path}, "
                    f"类型: {context.file_type.value}, "
                    f"大小: {context.file_size} bytes"
                )
                
                # 3. 预处理
                self._pre_convert(context)
                
                # 4. 执行转换
                content = self._convert_content(context)
                
                # 5. 提取元数据
                context.metadata = self._extract_metadata(context)
                
                # 6. 后处理
                content = self._post_convert(context, content)
                
                # 7. 创建文档
                document = self._create_document(context, content)
                
                self._logger.info(
                    f"转换完成: {context.document_id}, "
                    f"字数: {document.word_count}, "
                    f"耗时: {t['elapsed_ms']:.2f}ms"
                )
                
                return self._create_success_result(
                    document=document,
                    processing_time_ms=t["elapsed_ms"],
                    warnings=context.warnings if context.warnings else None,
                )
            
            except ConverterError as e:
                self._logger.error(f"转换失败: {e}")
                return self._create_error_result(
                    error=e,
                    processing_time_ms=t["elapsed_ms"],
                )
            
            except Exception as e:
                self._logger.exception(f"转换时发生未预期的错误: {e}")
                error = ConverterError.from_exception(
                    exception=e,
                    code=ConverterErrorCode.CONVERSION_FAILED,
                    context=ErrorContext(file_path=input.file_path),
                )
                return self._create_error_result(
                    error=error,
                    processing_time_ms=t["elapsed_ms"],
                )


class ConverterRegistry:
    """
    转换器注册表
    
    管理所有可用的转换器，根据文件类型选择合适的转换器。
    
    使用示例:
        registry = ConverterRegistry()
        registry.register(PDFConverter())
        registry.register(HTMLConverter())
        
        converter = registry.get_converter(FileType.PDF)
        result = converter.convert(input)
    """
    
    def __init__(self):
        self._converters: Dict[FileType, BaseConverter] = {}
        self._default_config: Optional[ConversionConfig] = None
    
    def register(
        self,
        converter: BaseConverter,
        file_types: Optional[List[FileType]] = None
    ) -> None:
        """
        注册转换器
        
        Args:
            converter: 转换器实例
            file_types: 要注册的文件类型列表（可选，如果不指定则自动检测）
        """
        if file_types:
            for ft in file_types:
                self._converters[ft] = converter
        else:
            # 自动检测支持的类型
            for ft in FileType:
                if converter.supports(ft):
                    self._converters[ft] = converter
    
    def get_converter(self, file_type: FileType) -> Optional[BaseConverter]:
        """
        获取指定类型的转换器
        
        Args:
            file_type: 文件类型
        
        Returns:
            转换器实例，如果没有找到则返回None
        """
        return self._converters.get(file_type)
    
    def has_converter(self, file_type: FileType) -> bool:
        """
        检查是否有指定类型的转换器
        
        Args:
            file_type: 文件类型
        
        Returns:
            是否存在转换器
        """
        return file_type in self._converters
    
    def get_supported_types(self) -> List[FileType]:
        """
        获取所有支持的文件类型
        
        Returns:
            文件类型列表
        """
        return list(self._converters.keys())
    
    def set_default_config(self, config: ConversionConfig) -> None:
        """
        设置默认配置
        
        Args:
            config: 转换配置
        """
        self._default_config = config
        for converter in set(self._converters.values()):
            converter.config = config