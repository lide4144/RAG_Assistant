"""
TXT文档转换器

将纯文本文件转换为Markdown格式。

功能：
1. 自动检测文件编码
2. 智能段落识别
3. 标题推断
4. 文本清理和规范化
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from src.models.schemas import BaseMetadata, FileType
from src.converter.base import BaseConverter, ConversionConfig, ConversionContext
from src.converter.exceptions import (
    ConverterError,
    ConverterErrorCode,
    EncodingError,
    ErrorContext,
    FileReadError,
)
from src.utils.helpers import (
    clean_text,
    detect_encoding,
    normalize_whitespace,
    safe_decode,
)


logger = logging.getLogger(__name__)


class TXTConverter(BaseConverter):
    """
    TXT文档转换器
    
    将纯文本文件转换为Markdown格式。支持自动编码检测和智能段落识别。
    
    特性：
    - 自动检测文件编码（UTF-8, GBK, GB2312等）
    - 智能段落分割
    - 标题推断（基于文档开头内容）
    - 文本清理和规范化
    
    使用示例:
        converter = TXTConverter()
        result = converter.convert(DocumentInput(file_path="document.txt"))
        if result.success:
            print(result.document.content)
    """
    
    # 可能表示标题的模式
    TITLE_PATTERNS = [
        # 中文标题模式
        r"^[\u4e00-\u9fff]{2,50}$",  # 纯中文标题
        r"^《.*》$",  # 书名号包裹的标题
        r"^【.*】$",  # 方括号包裹的标题
        # 英文标题模式
        r"^[A-Z][A-Za-z\s:]+$",  # 首字母大写的标题
        r"^Title:\s*(.+)$",  # Title: 开头的标题
    ]
    
    # 章节标题模式
    SECTION_PATTERNS = [
        # 中文章节
        r"^第[一二三四五六七八九十百千]+[章节篇部]\s*",
        r"^[一二三四五六七八九十]+[、.．]\s*",
        # 数字章节
        r"^(\d+)[\.、．]\s+",
        r"^(\d+\.\d+)[\.、．\s]+",
        r"^Chapter\s+\d+",
        r"^Section\s+\d+",
    ]
    
    def __init__(self, config: Optional[ConversionConfig] = None):
        """
        初始化TXT转换器
        
        Args:
            config: 转换配置
        """
        super().__init__(config)
        self._compiled_title_patterns = [
            re.compile(p, re.MULTILINE) for p in self.TITLE_PATTERNS
        ]
        self._compiled_section_patterns = [
            re.compile(p, re.MULTILINE) for p in self.SECTION_PATTERNS
        ]
    
    def supports(self, file_type: FileType) -> bool:
        """
        检查是否支持指定的文件类型
        
        Args:
            file_type: 文件类型
        
        Returns:
            是否支持
        """
        return file_type == FileType.TXT
    
    def _read_file_content(self, context: ConversionContext) -> str:
        """
        读取文件内容，处理编码问题
        
        Args:
            context: 转换上下文
        
        Returns:
            解码后的文本内容
        
        Raises:
            FileReadError: 读取失败
            EncodingError: 编码问题
        """
        file_path = context.file_path
        config = context.config
        
        try:
            # 读取原始字节
            with open(file_path, "rb") as f:
                raw_content = f.read()
        except IOError as e:
            raise FileReadError(
                file_path=str(file_path),
                cause=e,
                context=ErrorContext(
                    file_path=str(file_path),
                    operation="read"
                )
            )
        
        # 尝试使用指定的编码
        specified_encoding = context.input.encoding or config.default_encoding
        
        if config.detect_encoding:
            # 自动检测编码
            detected_encoding, confidence = detect_encoding(raw_content)
            
            if confidence >= 0.8:
                encoding = detected_encoding
                logger.debug(
                    f"检测到编码: {encoding}, 置信度: {confidence:.2f}"
                )
            else:
                # 置信度低时尝试指定的编码
                encoding = specified_encoding
                context.add_warning(
                    f"编码检测置信度较低 ({confidence:.2f})，使用指定编码: {encoding}"
                )
        else:
            encoding = specified_encoding
        
        # 解码内容
        try:
            content = safe_decode(raw_content, encoding=encoding)
        except Exception as e:
            raise EncodingError(
                message=f"解码文件失败: {e}",
                encoding=encoding,
                context=ErrorContext(
                    file_path=str(file_path),
                    operation="decode"
                ),
                cause=e
            )
        
        return content
    
    def _infer_title(self, content: str) -> Optional[str]:
        """
        从文本内容推断标题
        
        策略：
        1. 检查第一行是否匹配标题模式
        2. 使用第一行非空内容作为标题（如果足够短）
        
        Args:
            content: 文本内容
        
        Returns:
            推断的标题，如果无法推断则返回None
        """
        lines = content.strip().split("\n")
        
        # 找到第一个非空行
        first_line = None
        for line in lines[:5]:  # 只检查前5行
            line = line.strip()
            if line:
                first_line = line
                break
        
        if not first_line:
            return None
        
        # 检查是否匹配标题模式
        for pattern in self._compiled_title_patterns:
            match = pattern.match(first_line)
            if match:
                if match.groups():
                    return match.group(1).strip()
                return first_line
        
        # 如果第一行足够短，可能是标题
        if len(first_line) <= 100 and not first_line.endswith(("。", ".", "！", "!", "？", "?")):
            return first_line
        
        return None
    
    def _detect_section(self, line: str) -> Tuple[bool, int, str]:
        """
        检测行是否为章节标题
        
        Args:
            line: 文本行
        
        Returns:
            (是否为章节, 章节级别, 处理后的标题文本)
        """
        line = line.strip()
        
        for i, pattern in enumerate(self._compiled_section_patterns):
            if pattern.match(line):
                # 简单的级别判断：基于模式的位置
                level = 2 if i < len(self._compiled_section_patterns) // 2 else 3
                return True, level, line
        
        return False, 0, line
    
    def _format_as_markdown(self, content: str, title: Optional[str] = None) -> str:
        """
        将纯文本格式化为Markdown
        
        Args:
            content: 原始文本
            title: 文档标题（可选）
        
        Returns:
            Markdown格式的内容
        """
        lines = content.split("\n")
        result_lines: List[str] = []
        
        # 添加标题
        if title:
            result_lines.append(f"# {title}")
            result_lines.append("")
        
        # 处理内容
        in_paragraph = False
        paragraph_lines: List[str] = []
        
        for line in lines:
            line = line.rstrip()
            
            # 跳过标题行（如果已经作为标题使用）
            if title and line.strip() == title and not result_lines[2:]:
                continue
            
            # 检测空行
            if not line.strip():
                if paragraph_lines:
                    # 结束当前段落
                    result_lines.append(" ".join(paragraph_lines))
                    result_lines.append("")
                    paragraph_lines = []
                    in_paragraph = False
                continue
            
            # 检测章节标题
            is_section, level, section_title = self._detect_section(line)
            if is_section:
                # 先结束当前段落
                if paragraph_lines:
                    result_lines.append(" ".join(paragraph_lines))
                    result_lines.append("")
                    paragraph_lines = []
                
                # 添加章节标题
                prefix = "#" * level
                result_lines.append(f"{prefix} {section_title}")
                result_lines.append("")
                in_paragraph = False
                continue
            
            # 普通行，加入当前段落
            paragraph_lines.append(line.strip())
            in_paragraph = True
        
        # 处理最后一个段落
        if paragraph_lines:
            result_lines.append(" ".join(paragraph_lines))
        
        return "\n".join(result_lines)
    
    def _convert_content(self, context: ConversionContext) -> str:
        """
        执行TXT到Markdown的转换
        
        Args:
            context: 转换上下文
        
        Returns:
            Markdown格式的内容
        """
        # 读取文件内容
        raw_content = self._read_file_content(context)
        
        # 清理文本
        content = clean_text(raw_content)
        
        # 推断标题
        title = self._infer_title(content)
        if title:
            logger.debug(f"推断的标题: {title}")
        
        # 格式化为Markdown
        markdown_content = self._format_as_markdown(content, title)
        
        return markdown_content
    
    def _extract_metadata(self, context: ConversionContext) -> BaseMetadata:
        """
        提取文档元数据
        
        TXT文件的元数据提取相对有限，主要依赖于文件名和内容推断。
        
        Args:
            context: 转换上下文
        
        Returns:
            元数据对象
        """
        # 使用预设的元数据作为基础
        if context.input.metadata:
            metadata = context.input.metadata.model_copy()
        else:
            metadata = BaseMetadata()
        
        # 如果没有标题，尝试从文件名推断
        if not metadata.title:
            # 读取内容并推断标题
            try:
                raw_content = self._read_file_content(context)
                content = clean_text(raw_content)
                title = self._infer_title(content)
                if title:
                    metadata.title = title
            except Exception:
                pass
            
            # 如果还没有标题，使用文件名
            if not metadata.title:
                metadata.title = context.file_path.stem
        
        return metadata


class MarkdownConverter(BaseConverter):
    """
    Markdown文档转换器
    
    处理已经是Markdown格式的文件，主要进行规范化和元数据提取。
    
    特性：
    - 保持Markdown格式
    - 提取YAML front matter元数据
    - 规范化Markdown语法
    """
    
    # YAML front matter模式
    FRONT_MATTER_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n",
        re.DOTALL
    )
    
    def supports(self, file_type: FileType) -> bool:
        """检查是否支持指定的文件类型"""
        return file_type == FileType.MARKDOWN
    
    def _read_file_content(self, context: ConversionContext) -> str:
        """读取文件内容"""
        file_path = context.file_path
        config = context.config
        
        try:
            with open(file_path, "rb") as f:
                raw_content = f.read()
        except IOError as e:
            raise FileReadError(
                file_path=str(file_path),
                cause=e
            )
        
        encoding = context.input.encoding or config.default_encoding
        if config.detect_encoding:
            detected_encoding, _ = detect_encoding(raw_content)
            encoding = detected_encoding
        
        return safe_decode(raw_content, encoding=encoding)
    
    def _extract_front_matter(self, content: str) -> Tuple[Optional[dict], str]:
        """
        提取YAML front matter
        
        Args:
            content: Markdown内容
        
        Returns:
            (元数据字典, 剩余内容)
        """
        match = self.FRONT_MATTER_PATTERN.match(content)
        if not match:
            return None, content
        
        yaml_content = match.group(1)
        remaining_content = content[match.end():]
        
        try:
            import yaml
            metadata = yaml.safe_load(yaml_content)
            return metadata, remaining_content
        except Exception as e:
            logger.warning(f"解析YAML front matter失败: {e}")
            return None, content
    
    def _convert_content(self, context: ConversionContext) -> str:
        """执行转换"""
        content = self._read_file_content(context)
        
        # 提取并移除front matter
        front_matter, content = self._extract_front_matter(content)
        
        # 如果有front matter，存储到上下文
        if front_matter:
            context.metadata = BaseMetadata(**{
                k: v for k, v in front_matter.items()
                if hasattr(BaseMetadata, k)
            })
        
        # 规范化内容
        content = normalize_whitespace(content)
        
        return content
    
    def _extract_metadata(self, context: ConversionContext) -> BaseMetadata:
        """提取元数据"""
        if context.metadata:
            return context.metadata
        
        if context.input.metadata:
            return context.input.metadata
        
        # 从内容中提取标题
        content = self._read_file_content(context)
        _, content = self._extract_front_matter(content)
        
        # 查找第一个标题
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            return BaseMetadata(title=title_match.group(1).strip())
        
        return BaseMetadata(title=context.file_path.stem)