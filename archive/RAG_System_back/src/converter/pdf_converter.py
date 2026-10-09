"""
PDF文档转换器

将PDF文件转换为Markdown格式。

功能：
1. 提取文本内容（保持结构）
2. 提取图片
3. 提取表格
4. 提取元数据
5. 支持OCR（可选）
6. 处理加密PDF

依赖：
- PyMuPDF (fitz): PDF解析
- Pillow: 图片处理
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.models.schemas import BaseMetadata, FileType, ImageInfo, TableInfo
from src.converter.base import BaseConverter, ConversionConfig, ConversionContext
from src.converter.exceptions import (
    ConverterError,
    ConverterErrorCode,
    ErrorContext,
    FileReadError,
    ImageExtractionError,
    PDFCorruptedError,
    PDFEncryptedError,
    PDFParseError,
    TableExtractionError,
)
from src.utils.helpers import (
    clean_text,
    ensure_directory,
    generate_unique_filename,
    make_safe_filename,
)


logger = logging.getLogger(__name__)


# 尝试导入可选依赖
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    fitz = None

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None


class PDFConverter(BaseConverter):
    """
    PDF文档转换器
    
    将PDF文件转换为Markdown格式，支持文本、图片和表格提取。
    
    依赖：
    - PyMuPDF (fitz): PDF解析和文本/图片提取
    - Pillow: 图片处理和保存
    
    特性：
    - 高质量文本提取（保持结构）
    - 图片提取和保存
    - 表格检测和转换
    - 元数据提取（标题、作者、日期等）
    - 支持OCR（需要额外配置）
    - 处理加密和损坏的PDF
    
    使用示例:
        converter = PDFConverter()
        result = converter.convert(DocumentInput(file_path="document.pdf"))
        if result.success:
            print(result.document.content)
    """
    
    # 章节标题模式
    SECTION_PATTERNS = [
        # 中文章节
        (r"^第[一二三四五六七八九十百千]+[章节篇部][\s\.．:：]*.+$", 2),
        (r"^[一二三四五六七八九十]+[、.．]\s*.+$", 2),
        (r"^[\(（][一二三四五六七八九十]+[\)）]\s*.+$", 3),
        # 数字章节
        (r"^(\d+)[\.、．]\s+.+$", 2),
        (r"^(\d+\.\d+)[\.、．\s]+.+$", 3),
        (r"^(\d+\.\d+\.\d+)[\.、．\s]+.+$", 4),
        # 英文章节
        (r"^Chapter\s+\d+[\s:：].+$", 2),
        (r"^Section\s+\d+[\s:：].+$", 3),
        (r"^Part\s+[IVXLCDM]+[\s:：].+$", 2),
        # 通用标题（全大写或首字母大写的短行）
        (r"^[A-Z][A-Z\s]{5,50}$", 2),
        # 摘要、引言等
        (r"^(摘\s*要|Abstract|ABSTRACT|引言|Introduction|INTRODUCTION|结论|Conclusion|CONCLUSION|参考文献|References|REFERENCES)\s*$", 2),
    ]
    
    def __init__(self, config: Optional[ConversionConfig] = None):
        """
        初始化PDF转换器
        
        Args:
            config: 转换配置
        """
        super().__init__(config)
        
        # 编译章节模式
        self._section_patterns = [
            (re.compile(pattern, re.MULTILINE), level)
            for pattern, level in self.SECTION_PATTERNS
        ]
        
        # 检查依赖
        if not HAS_PYMUPDF:
            logger.warning(
                "PyMuPDF未安装，PDF转换功能将不可用。"
                "请运行: pip install PyMuPDF"
            )
    
    def supports(self, file_type: FileType) -> bool:
        """检查是否支持指定的文件类型"""
        return file_type == FileType.PDF
    
    def _open_pdf(self, context: ConversionContext) -> "fitz.Document":
        """
        打开PDF文件
        
        Args:
            context: 转换上下文
        
        Returns:
            PyMuPDF文档对象
        
        Raises:
            PDFParseError: PDF无法打开
            PDFEncryptedError: PDF已加密
            PDFCorruptedError: PDF已损坏
        """
        if not HAS_PYMUPDF:
            raise PDFParseError(
                message="PyMuPDF库未安装，无法处理PDF文件",
                context=ErrorContext(
                    file_path=str(context.file_path),
                    operation="open"
                )
            )
        
        try:
            doc = fitz.open(str(context.file_path))
            
            # 检查是否加密
            if doc.is_encrypted:
                # 尝试用空密码解密
                if not doc.authenticate(""):
                    doc.close()
                    raise PDFEncryptedError(
                        file_path=str(context.file_path),
                        context=ErrorContext(file_path=str(context.file_path))
                    )
            
            return doc
        
        except PDFEncryptedError:
            raise
        
        except fitz.FileDataError as e:
            raise PDFCorruptedError(
                file_path=str(context.file_path),
                cause=e,
                context=ErrorContext(file_path=str(context.file_path))
            )
        
        except Exception as e:
            raise PDFParseError(
                message=f"无法打开PDF文件: {e}",
                cause=e,
                context=ErrorContext(
                    file_path=str(context.file_path),
                    operation="open"
                )
            )
    
    def _extract_page_text(
        self,
        page: "fitz.Page",
        page_num: int,
        context: ConversionContext
    ) -> str:
        """
        提取单页文本
        
        Args:
            page: PDF页面对象
            page_num: 页码（从0开始）
            context: 转换上下文
        
        Returns:
            提取的文本
        """
        try:
            # 使用blocks模式提取，保持更好的结构
            text_blocks = page.get_text("blocks")
            
            lines = []
            for block in text_blocks:
                if block[6] == 0:  # 文本块（非图片）
                    text = block[4].strip()
                    if text:
                        lines.append(text)
            
            return "\n\n".join(lines)
        
        except Exception as e:
            context.add_warning(f"提取第{page_num + 1}页文本时出错: {e}")
            
            # 回退到简单提取
            try:
                return page.get_text("text")
            except Exception:
                return ""
    
    def _detect_section_title(self, line: str) -> Tuple[bool, int]:
        """
        检测行是否为章节标题
        
        Args:
            line: 文本行
        
        Returns:
            (是否为章节标题, 标题级别)
        """
        line = line.strip()
        
        for pattern, level in self._section_patterns:
            if pattern.match(line):
                return True, level
        
        return False, 0
    
    def _format_text_as_markdown(
        self,
        text: str,
        title: Optional[str] = None
    ) -> str:
        """
        将提取的文本格式化为Markdown
        
        Args:
            text: 原始文本
            title: 文档标题
        
        Returns:
            Markdown格式的文本
        """
        lines = text.split("\n")
        result_lines: List[str] = []
        
        # 添加标题
        if title:
            result_lines.append(f"# {title}")
            result_lines.append("")
        
        current_paragraph: List[str] = []
        
        for line in lines:
            line = line.strip()
            
            if not line:
                # 空行，结束当前段落
                if current_paragraph:
                    result_lines.append(" ".join(current_paragraph))
                    result_lines.append("")
                    current_paragraph = []
                continue
            
            # 检测章节标题
            is_section, level = self._detect_section_title(line)
            if is_section:
                # 先结束当前段落
                if current_paragraph:
                    result_lines.append(" ".join(current_paragraph))
                    result_lines.append("")
                    current_paragraph = []
                
                # 添加章节标题
                prefix = "#" * level
                result_lines.append(f"{prefix} {line}")
                result_lines.append("")
                continue
            
            # 普通行
            current_paragraph.append(line)
        
        # 处理最后一个段落
        if current_paragraph:
            result_lines.append(" ".join(current_paragraph))
        
        return "\n".join(result_lines)
    
    def _extract_images(
        self,
        doc: "fitz.Document",
        context: ConversionContext
    ) -> List[ImageInfo]:
        """
        从PDF中提取图片
        
        Args:
            doc: PDF文档对象
            context: 转换上下文
        
        Returns:
            图片信息列表
        """
        if not HAS_PIL:
            context.add_warning("Pillow未安装，跳过图片提取")
            return []
        
        config = context.config
        images: List[ImageInfo] = []
        
        # 确定图片保存目录
        if config.images_dir:
            images_dir = Path(config.images_dir)
        elif config.output_dir:
            images_dir = Path(config.output_dir) / "images"
        else:
            images_dir = context.file_path.parent / "images"
        
        ensure_directory(images_dir)
        
        image_count = 0
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            try:
                image_list = page.get_images(full=True)
            except Exception as e:
                context.add_warning(f"获取第{page_num + 1}页图片列表失败: {e}")
                continue
            
            for img_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    
                    # 提取图片数据
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue
                    
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)
                    
                    # 检查尺寸
                    if width < config.min_image_size or height < config.min_image_size:
                        continue
                    
                    # 生成图片ID和文件名
                    image_id = f"{context.document_id}_img_{image_count}"
                    image_filename = generate_unique_filename(
                        images_dir,
                        f"{context.file_path.stem}_img_{image_count}",
                        config.image_format or image_ext
                    )
                    image_path = images_dir / image_filename
                    
                    # 保存图片
                    try:
                        # 如果需要转换格式
                        if config.image_format and config.image_format != image_ext:
                            img_obj = Image.open(io.BytesIO(image_bytes))
                            if config.image_format.lower() in ("jpg", "jpeg"):
                                # JPEG不支持透明度
                                if img_obj.mode in ("RGBA", "LA", "P"):
                                    img_obj = img_obj.convert("RGB")
                                img_obj.save(
                                    image_path,
                                    format="JPEG",
                                    quality=config.image_quality
                                )
                            else:
                                img_obj.save(image_path, format=config.image_format.upper())
                        else:
                            with open(image_path, "wb") as f:
                                f.write(image_bytes)
                    except Exception as e:
                        context.add_warning(f"保存图片失败: {e}")
                        continue
                    
                    # 确定MIME类型
                    mime_type = f"image/{config.image_format or image_ext}"
                    if mime_type == "image/jpg":
                        mime_type = "image/jpeg"
                    
                    # 创建图片信息
                    image_info = ImageInfo(
                        image_id=image_id,
                        original_page=page_num + 1,
                        image_path=str(image_path),
                        mime_type=mime_type,
                        width=width,
                        height=height,
                        caption=None
                    )
                    images.append(image_info)
                    image_count += 1
                
                except Exception as e:
                    context.add_warning(
                        f"提取第{page_num + 1}页第{img_index + 1}张图片失败: {e}"
                    )
        
        logger.info(f"共提取 {len(images)} 张图片")
        return images
    
    def _extract_tables(
        self,
        doc: "fitz.Document",
        context: ConversionContext
    ) -> List[TableInfo]:
        """
        从PDF中提取表格
        
        使用PyMuPDF的表格检测功能。
        
        Args:
            doc: PDF文档对象
            context: 转换上下文
        
        Returns:
            表格信息列表
        """
        tables: List[TableInfo] = []
        table_count = 0
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            try:
                # PyMuPDF 1.23.0+ 支持表格提取
                if hasattr(page, "find_tables"):
                    page_tables = page.find_tables()
                    
                    for table in page_tables:
                        try:
                            # 提取表格数据
                            table_data = table.extract()
                            
                            if not table_data or len(table_data) < 2:
                                continue
                            
                            # 转换为Markdown表格
                            markdown_table = self._table_to_markdown(table_data)
                            
                            table_info = TableInfo(
                                table_id=f"{context.document_id}_table_{table_count}",
                                original_page=page_num + 1,
                                markdown_content=markdown_table,
                                caption=None,
                                rows=len(table_data),
                                columns=len(table_data[0]) if table_data else 0
                            )
                            tables.append(table_info)
                            table_count += 1
                        
                        except Exception as e:
                            context.add_warning(f"处理表格失败: {e}")
                
            except Exception as e:
                context.add_warning(f"提取第{page_num + 1}页表格失败: {e}")
        
        logger.info(f"共提取 {len(tables)} 个表格")
        return tables
    
    def _table_to_markdown(self, table_data: List[List[str]]) -> str:
        """
        将表格数据转换为Markdown格式
        
        Args:
            table_data: 表格数据（二维列表）
        
        Returns:
            Markdown表格字符串
        """
        if not table_data:
            return ""
        
        # 清理单元格内容
        cleaned_data = []
        for row in table_data:
            cleaned_row = []
            for cell in row:
                # 处理None和换行
                cell_text = str(cell) if cell else ""
                cell_text = cell_text.replace("\n", " ").strip()
                cell_text = cell_text.replace("|", "\\|")
                cleaned_row.append(cell_text)
            cleaned_data.append(cleaned_row)
        
        lines = []
        
        # 表头（第一行）
        headers = cleaned_data[0]
        lines.append("| " + " | ".join(headers) + " |")
        
        # 分隔行
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        
        # 数据行
        for row in cleaned_data[1:]:
            # 确保列数匹配
            padded_row = row + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(padded_row[:len(headers)]) + " |")
        
        return "\n".join(lines)
    
    def _extract_pdf_metadata(
        self,
        doc: "fitz.Document"
    ) -> Dict[str, Any]:
        """
        提取PDF元数据
        
        Args:
            doc: PDF文档对象
        
        Returns:
            元数据字典
        """
        metadata: Dict[str, Any] = {}
        
        try:
            pdf_metadata = doc.metadata
            
            if pdf_metadata:
                # 标题
                if pdf_metadata.get("title"):
                    metadata["title"] = pdf_metadata["title"]
                
                # 作者
                if pdf_metadata.get("author"):
                    # 可能有多个作者，用逗号或分号分隔
                    author_str = pdf_metadata["author"]
                    authors = re.split(r"[,;，；]", author_str)
                    metadata["authors"] = [a.strip() for a in authors if a.strip()]
                
                # 主题/摘要
                if pdf_metadata.get("subject"):
                    metadata["abstract"] = pdf_metadata["subject"]
                
                # 关键词
                if pdf_metadata.get("keywords"):
                    keywords_str = pdf_metadata["keywords"]
                    keywords = re.split(r"[,;，；]", keywords_str)
                    metadata["keywords"] = [k.strip() for k in keywords if k.strip()]
                
                # 创建日期
                if pdf_metadata.get("creationDate"):
                    try:
                        from datetime import datetime
                        date_str = pdf_metadata["creationDate"]
                        # PDF日期格式: D:YYYYMMDDHHmmSS
                        if date_str.startswith("D:"):
                            date_str = date_str[2:]
                        if len(date_str) >= 8:
                            year = int(date_str[:4])
                            month = int(date_str[4:6])
                            day = int(date_str[6:8])
                            metadata["publication_date"] = datetime(year, month, day)
                    except Exception:
                        pass
                
                # 创建者/来源
                if pdf_metadata.get("creator"):
                    metadata["source"] = pdf_metadata["creator"]
        
        except Exception as e:
            logger.warning(f"提取PDF元数据失败: {e}")
        
        return metadata
    
    def _infer_title_from_content(
        self,
        doc: "fitz.Document"
    ) -> Optional[str]:
        """
        从PDF内容中推断标题
        
        策略：
        1. 第一页的第一个大字体文本
        2. 第一页的第一行文本
        
        Args:
            doc: PDF文档对象
        
        Returns:
            推断的标题
        """
        if len(doc) == 0:
            return None
        
        try:
            first_page = doc[0]
            
            # 获取文本块及其属性
            blocks = first_page.get_text("dict")["blocks"]
            
            # 找到最大字体的文本行
            max_font_size = 0
            title_text = None
            
            for block in blocks:
                if block.get("type") != 0:  # 非文本块
                    continue
                
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        font_size = span.get("size", 0)
                        
                        if text and font_size > max_font_size:
                            # 标题通常不会太长
                            if len(text) <= 200:
                                max_font_size = font_size
                                title_text = text
            
            return title_text
        
        except Exception as e:
            logger.debug(f"从内容推断标题失败: {e}")
            return None
    
    def _convert_content(self, context: ConversionContext) -> str:
        """
        执行PDF到Markdown的转换
        
        Args:
            context: 转换上下文
        
        Returns:
            Markdown内容
        """
        config = context.config
        
        # 打开PDF
        doc = self._open_pdf(context)
        
        try:
            # 记录页数
            page_count = len(doc)
            logger.info(f"PDF共 {page_count} 页")
            
            # 提取所有页面的文本
            all_text = []
            for page_num in range(page_count):
                page = doc[page_num]
                page_text = self._extract_page_text(page, page_num, context)
                if page_text.strip():
                    all_text.append(page_text)
            
            full_text = "\n\n".join(all_text)
            
            # 提取元数据以获取标题
            pdf_metadata = self._extract_pdf_metadata(doc)
            title = pdf_metadata.get("title")
            
            # 如果没有标题，尝试从内容推断
            if not title:
                title = self._infer_title_from_content(doc)
            
            # 提取图片
            if config.extract_images:
                context.images = self._extract_images(doc, context)
            
            # 提取表格
            if config.extract_tables:
                context.tables = self._extract_tables(doc, context)
            
            # 存储PDF元数据和页数到上下文
            context.metadata = BaseMetadata(**{
                k: v for k, v in pdf_metadata.items()
                if hasattr(BaseMetadata, k) or k in ["title", "authors", "abstract", "keywords", "publication_date", "source"]
            })
            
            # 存储页数供后续使用
            context.extra = {"page_count": page_count}
            
            # 格式化为Markdown
            markdown_content = self._format_text_as_markdown(full_text, title)
            
            # 清理内容
            markdown_content = clean_text(markdown_content)
            
            return markdown_content
        
        finally:
            doc.close()
    
    def _extract_metadata(self, context: ConversionContext) -> BaseMetadata:
        """
        提取文档元数据
        
        Args:
            context: 转换上下文
        
        Returns:
            元数据对象
        """
        # 如果已经在转换过程中提取了元数据，直接使用
        if context.metadata:
            metadata = context.metadata
        elif context.input.metadata:
            metadata = context.input.metadata.model_copy()
        else:
            metadata = BaseMetadata()
        
        # 如果没有标题，使用文件名
        if not metadata.title:
            metadata.title = context.file_path.stem
        
        return metadata
    
    def _create_document(
        self,
        context: ConversionContext,
        content: str,
        page_count: Optional[int] = None
    ) -> "MarkdownDocument":
        """
        创建Markdown文档对象（重写以包含页数）
        
        Args:
            context: 转换上下文
            content: Markdown内容
            page_count: 页数
        
        Returns:
            MarkdownDocument对象
        """
        # 从上下文获取页数
        if page_count is None and hasattr(context, "extra") and context.extra:
            page_count = context.extra.get("page_count")
        
        return super()._create_document(context, content, page_count)