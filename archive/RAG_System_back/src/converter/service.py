"""
文档转换服务

提供统一的文档转换API接口，是外部调用的主入口。

功能：
1. 自动识别文件类型并选择转换器
2. 单文档转换
3. 批量并行转换
4. 统一的配置管理
5. 完整的错误处理
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from src.models.schemas import (
    BatchConversionResult,
    BatchDocumentInput,
    ConversionResult,
    DocumentInput,
    FileType,
    MarkdownDocument,
    ProcessingStatus,
)
from src.converter.base import (
    BaseConverter,
    ConversionConfig,
    ConverterRegistry,
)
from src.converter.exceptions import (
    ConverterError,
    ConverterErrorCode,
    ErrorContext,
    UnsupportedFileTypeError,
)
from src.converter.pdf_converter import PDFConverter
from src.converter.html_converter import HTMLConverter
from src.converter.txt_converter import TXTConverter, MarkdownConverter
from src.utils.helpers import (
    detect_file_type,
    is_valid_file,
    timer,
)


logger = logging.getLogger(__name__)


class DocumentConverterService:
    """
    文档转换服务
    
    对外提供的统一转换接口，负责：
    - 管理所有格式的转换器
    - 自动检测文件类型
    - 提供单文档和批量转换功能
    - 统一的错误处理
    
    使用示例:
        # 创建服务
        service = DocumentConverterService()
        
        # 单文档转换
        result = service.convert_document(
            DocumentInput(file_path="paper.pdf")
        )
        
        if result.success:
            markdown_doc = result.document
            print(f"标题: {markdown_doc.metadata.title}")
            print(f"内容: {markdown_doc.content[:100]}...")
        else:
            print(f"转换失败: {result.error_details}")
        
        # 批量转换
        batch_input = BatchDocumentInput(
            documents=[
                DocumentInput(file_path="paper1.pdf"),
                DocumentInput(file_path="paper2.html"),
            ],
            parallel=True
        )
        batch_result = service.convert_batch(batch_input)
        print(f"成功: {batch_result.success_count}/{batch_result.total_count}")
    """
    
    def __init__(
        self,
        config: Optional[ConversionConfig] = None,
        auto_register: bool = True
    ):
        """
        初始化文档转换服务
        
        Args:
            config: 全局转换配置（可选）
            auto_register: 是否自动注册所有内置转换器
        """
        self._config = config or ConversionConfig()
        self._registry = ConverterRegistry()
        self._logger = logging.getLogger(self.__class__.__name__)
        
        if auto_register:
            self._register_default_converters()
    
    def _register_default_converters(self) -> None:
        """注册默认的转换器"""
        # PDF转换器
        pdf_converter = PDFConverter(self._config)
        self._registry.register(pdf_converter, [FileType.PDF])
        
        # HTML转换器
        html_converter = HTMLConverter(self._config)
        self._registry.register(html_converter, [FileType.HTML])
        
        # TXT转换器
        txt_converter = TXTConverter(self._config)
        self._registry.register(txt_converter, [FileType.TXT])
        
        # Markdown转换器（处理已有的Markdown文件）
        md_converter = MarkdownConverter(self._config)
        self._registry.register(md_converter, [FileType.MARKDOWN])
        
        self._logger.info(
            f"已注册转换器: {[t.value for t in self._registry.get_supported_types()]}"
        )
    
    def register_converter(
        self,
        converter: BaseConverter,
        file_types: Optional[List[FileType]] = None
    ) -> None:
        """
        注册自定义转换器
        
        Args:
            converter: 转换器实例
            file_types: 要处理的文件类型列表
        """
        self._registry.register(converter, file_types)
    
    def get_supported_types(self) -> List[FileType]:
        """
        获取支持的文件类型列表
        
        Returns:
            FileType列表
        """
        return self._registry.get_supported_types()
    
    def is_supported(self, file_path: Union[str, Path]) -> bool:
        """
        检查文件是否支持转换
        
        Args:
            file_path: 文件路径
        
        Returns:
            是否支持
        """
        file_type = detect_file_type(file_path)
        if file_type is None:
            return False
        return self._registry.has_converter(file_type)
    
    def _detect_and_validate(
        self,
        input: DocumentInput
    ) -> tuple[FileType, BaseConverter]:
        """
        检测文件类型并获取对应的转换器
        
        Args:
            input: 文档输入
        
        Returns:
            (文件类型, 转换器)
        
        Raises:
            UnsupportedFileTypeError: 不支持的文件类型
        """
        # 确定文件类型
        if input.file_type:
            file_type = input.file_type
        else:
            file_type = detect_file_type(input.file_path)
            if file_type is None:
                raise UnsupportedFileTypeError(
                    file_type=Path(input.file_path).suffix,
                    supported_types=[t.value for t in self.get_supported_types()],
                    context=ErrorContext(file_path=input.file_path)
                )
        
        # 获取转换器
        converter = self._registry.get_converter(file_type)
        if converter is None:
            raise UnsupportedFileTypeError(
                file_type=file_type.value,
                supported_types=[t.value for t in self.get_supported_types()],
                context=ErrorContext(
                    file_path=input.file_path,
                    file_type=file_type.value
                )
            )
        
        return file_type, converter
    
    def convert_document(
        self,
        input: DocumentInput,
        config: Optional[ConversionConfig] = None
    ) -> ConversionResult:
        """
        转换单个文档
        
        这是单文档转换的主要入口点。
        
        Args:
            input: DocumentInput对象，包含文件路径和选项
            config: 可选的配置覆盖
        
        Returns:
            ConversionResult: 包含MarkdownDocument或错误信息
        
        使用示例:
            result = service.convert_document(
                DocumentInput(
                    file_path="paper.pdf",
                    extract_images=True,
                    extract_tables=True
                )
            )
        """
        with timer() as t:
            try:
                self._logger.info(f"开始转换: {input.file_path}")
                
                # 检测文件类型并获取转换器
                file_type, converter = self._detect_and_validate(input)
                
                # 合并配置
                effective_config = config or self._config
                
                # 使用转换器的配置覆盖全局配置
                # （如果输入中指定了extract_images/extract_tables，优先使用）
                if effective_config:
                    effective_config = ConversionConfig(
                        **{
                            **effective_config.__dict__,
                            "extract_images": input.extract_images,
                            "extract_tables": input.extract_tables,
                        }
                    )
                
                # 执行转换
                result = converter.convert(input, effective_config)
                
                self._logger.info(
                    f"转换完成: {input.file_path}, "
                    f"成功: {result.success}, "
                    f"耗时: {t['elapsed_ms']:.2f}ms"
                )
                
                return result
            
            except ConverterError as e:
                self._logger.error(f"转换失败: {input.file_path}, 错误: {e}")
                return ConversionResult(
                    success=False,
                    status=ProcessingStatus.FAILED,
                    message=e.message,
                    processing_time_ms=t["elapsed_ms"],
                    error_details=str(e),
                )
            
            except Exception as e:
                self._logger.exception(f"转换时发生未预期错误: {input.file_path}")
                return ConversionResult(
                    success=False,
                    status=ProcessingStatus.FAILED,
                    message=str(e),
                    processing_time_ms=t["elapsed_ms"],
                    error_details=f"未预期的错误: {e}",
                )
    
    def convert_batch(
        self,
        input: BatchDocumentInput,
        config: Optional[ConversionConfig] = None
    ) -> BatchConversionResult:
        """
        批量转换文档
        
        支持并行处理多个文档，可配置最大并行数。
        
        Args:
            input: BatchDocumentInput对象，包含文档列表和处理选项
            config: 可选的配置覆盖
        
        Returns:
            BatchConversionResult: 批量转换结果
        
        使用示例:
            batch_input = BatchDocumentInput(
                documents=[
                    DocumentInput(file_path="paper1.pdf"),
                    DocumentInput(file_path="paper2.html"),
                    DocumentInput(file_path="paper3.txt"),
                ],
                parallel=True,
                max_workers=4,
                continue_on_error=True
            )
            result = service.convert_batch(batch_input)
        """
        with timer() as t:
            total_count = len(input.documents)
            self._logger.info(
                f"开始批量转换: {total_count} 个文档, "
                f"并行: {input.parallel}, "
                f"最大线程: {input.max_workers}"
            )
            
            results: List[ConversionResult] = []
            
            if input.parallel and total_count > 1:
                # 并行处理
                results = self._convert_parallel(
                    input.documents,
                    input.max_workers,
                    input.continue_on_error,
                    config
                )
            else:
                # 串行处理
                results = self._convert_sequential(
                    input.documents,
                    input.continue_on_error,
                    config
                )
            
            # 统计结果
            success_count = sum(1 for r in results if r.success)
            failed_count = total_count - success_count
            
            # 确定整体状态
            if success_count == total_count:
                status = ProcessingStatus.SUCCESS
                message = f"成功转换 {total_count} 个文档"
            elif success_count == 0:
                status = ProcessingStatus.FAILED
                message = f"所有 {total_count} 个文档转换失败"
            else:
                status = ProcessingStatus.PARTIAL
                message = f"部分成功: {success_count}/{total_count} 个文档转换成功"
            
            self._logger.info(
                f"批量转换完成: {success_count}/{total_count} 成功, "
                f"耗时: {t['elapsed_ms']:.2f}ms"
            )
            
            return BatchConversionResult(
                success=success_count > 0,
                status=status,
                message=message,
                processing_time_ms=t["elapsed_ms"],
                results=results,
                total_count=total_count,
                success_count=success_count,
                failed_count=failed_count,
            )
    
    def _convert_sequential(
        self,
        documents: List[DocumentInput],
        continue_on_error: bool,
        config: Optional[ConversionConfig]
    ) -> List[ConversionResult]:
        """
        串行转换文档
        
        Args:
            documents: 文档列表
            continue_on_error: 遇到错误是否继续
            config: 配置
        
        Returns:
            转换结果列表
        """
        results: List[ConversionResult] = []
        
        for i, doc_input in enumerate(documents):
            self._logger.debug(f"处理文档 {i + 1}/{len(documents)}: {doc_input.file_path}")
            
            result = self.convert_document(doc_input, config)
            results.append(result)
            
            if not result.success and not continue_on_error:
                self._logger.warning(f"文档转换失败且设置为不继续: {doc_input.file_path}")
                # 为剩余文档创建失败结果
                for remaining_doc in documents[i + 1:]:
                    results.append(ConversionResult(
                        success=False,
                        status=ProcessingStatus.FAILED,
                        message="由于前序文档失败而跳过",
                        processing_time_ms=0,
                        error_details="批量处理中止",
                    ))
                break
        
        return results
    
    def _convert_parallel(
        self,
        documents: List[DocumentInput],
        max_workers: int,
        continue_on_error: bool,
        config: Optional[ConversionConfig]
    ) -> List[ConversionResult]:
        """
        并行转换文档
        
        Args:
            documents: 文档列表
            max_workers: 最大并行数
            continue_on_error: 遇到错误是否继续
            config: 配置
        
        Returns:
            转换结果列表（保持原始顺序）
        """
        results: List[Optional[ConversionResult]] = [None] * len(documents)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_index = {
                executor.submit(self.convert_document, doc, config): i
                for i, doc in enumerate(documents)
            }
            
            # 收集结果
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                
                try:
                    result = future.result()
                    results[index] = result
                    
                    if not result.success and not continue_on_error:
                        # 取消剩余任务
                        self._logger.warning("文档转换失败，取消剩余任务")
                        for f in future_to_index:
                            f.cancel()
                        break
                
                except Exception as e:
                    self._logger.exception(f"并行任务异常: {e}")
                    results[index] = ConversionResult(
                        success=False,
                        status=ProcessingStatus.FAILED,
                        message=str(e),
                        processing_time_ms=0,
                        error_details=f"并行执行异常: {e}",
                    )
        
        # 填充未完成的任务
        for i, result in enumerate(results):
            if result is None:
                results[i] = ConversionResult(
                    success=False,
                    status=ProcessingStatus.FAILED,
                    message="任务被取消",
                    processing_time_ms=0,
                    error_details="批量处理中止",
                )
        
        return results
    
    def convert_file(
        self,
        file_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        **kwargs
    ) -> ConversionResult:
        """
        便捷方法：转换单个文件
        
        Args:
            file_path: 输入文件路径
            output_path: 输出文件路径（可选，如果指定则保存Markdown到文件）
            **kwargs: 传递给DocumentInput的其他参数
        
        Returns:
            ConversionResult
        
        使用示例:
            # 简单转换
            result = service.convert_file("paper.pdf")
            
            # 转换并保存
            result = service.convert_file(
                "paper.pdf",
                output_path="paper.md",
                extract_images=True
            )
        """
        input = DocumentInput(file_path=str(file_path), **kwargs)
        result = self.convert_document(input)
        
        # 如果成功且指定了输出路径，保存文件
        if result.success and output_path and result.document:
            try:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(result.document.content)
                
                self._logger.info(f"已保存到: {output_path}")
            except Exception as e:
                self._logger.error(f"保存文件失败: {e}")
                # 不影响返回结果，只记录警告
                if result.warnings is None:
                    result.warnings = []
                result.warnings.append(f"保存文件失败: {e}")
        
        return result
    
    def convert_directory(
        self,
        input_dir: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        pattern: str = "*",
        recursive: bool = False,
        **kwargs
    ) -> BatchConversionResult:
        """
        便捷方法：转换目录中的所有文档
        
        Args:
            input_dir: 输入目录
            output_dir: 输出目录（可选）
            pattern: 文件匹配模式（如 "*.pdf"）
            recursive: 是否递归处理子目录
            **kwargs: 传递给BatchDocumentInput的其他参数
        
        Returns:
            BatchConversionResult
        
        使用示例:
            # 转换目录中所有PDF
            result = service.convert_directory(
                "papers/",
                output_dir="output/",
                pattern="*.pdf",
                recursive=True
            )
        """
        input_dir = Path(input_dir)
        
        if not input_dir.exists():
            return BatchConversionResult(
                success=False,
                status=ProcessingStatus.FAILED,
                message=f"目录不存在: {input_dir}",
                processing_time_ms=0,
                results=[],
                total_count=0,
                success_count=0,
                failed_count=0,
            )
        
        # 收集文件
        if recursive:
            files = list(input_dir.rglob(pattern))
        else:
            files = list(input_dir.glob(pattern))
        
        # 过滤只保留支持的文件类型
        supported_files = [f for f in files if f.is_file() and self.is_supported(f)]
        
        if not supported_files:
            return BatchConversionResult(
                success=True,
                status=ProcessingStatus.SUCCESS,
                message="没有找到支持的文件",
                processing_time_ms=0,
                results=[],
                total_count=0,
                success_count=0,
                failed_count=0,
            )
        
        self._logger.info(f"找到 {len(supported_files)} 个支持的文件")
        
        # 创建文档输入列表
        documents = [
            DocumentInput(file_path=str(f))
            for f in supported_files
        ]
        
        # 默认参数
        batch_kwargs = {
            "parallel": True,
            "max_workers": 4,
            "continue_on_error": True,
        }
        batch_kwargs.update(kwargs)
        
        batch_input = BatchDocumentInput(documents=documents, **batch_kwargs)
        result = self.convert_batch(batch_input)
        
        # 如果指定了输出目录，保存所有成功的文件
        if output_dir and result.success_count > 0:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for i, conv_result in enumerate(result.results):
                if conv_result.success and conv_result.document:
                    # 计算相对路径并保持目录结构
                    original_file = Path(documents[i].file_path)
                    try:
                        rel_path = original_file.relative_to(input_dir)
                    except ValueError:
                        rel_path = original_file.name
                    
                    output_file = output_dir / rel_path.with_suffix(".md")
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(conv_result.document.content)
                    except Exception as e:
                        self._logger.error(f"保存文件失败: {output_file}, {e}")
        
        return result


# 创建默认服务实例（便于快速使用）
_default_service: Optional[DocumentConverterService] = None


def get_converter_service() -> DocumentConverterService:
    """
    获取默认的转换服务实例
    
    Returns:
        DocumentConverterService实例
    """
    global _default_service
    if _default_service is None:
        _default_service = DocumentConverterService()
    return _default_service


def convert_document(
    input: DocumentInput,
    config: Optional[ConversionConfig] = None
) -> ConversionResult:
    """
    便捷函数：转换单个文档
    
    使用默认的转换服务实例。
    
    Args:
        input: 文档输入
        config: 配置
    
    Returns:
        转换结果
    """
    return get_converter_service().convert_document(input, config)


def convert_batch(
    input: BatchDocumentInput,
    config: Optional[ConversionConfig] = None
) -> BatchConversionResult:
    """
    便捷函数：批量转换文档
    
    使用默认的转换服务实例。
    
    Args:
        input: 批量文档输入
        config: 配置
    
    Returns:
        批量转换结果
    """
    return get_converter_service().convert_batch(input, config)