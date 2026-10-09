"""
HTML文档转换器

将HTML文件转换为Markdown格式。

功能：
1. 支持本地HTML文件和URL
2. 智能内容提取（使用CSS选择器）
3. 自动清理无关元素
4. 提取元数据（标题、描述、关键词等）
5. 保留或移除链接
6. 图片处理
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from src.models.schemas import BaseMetadata, FileType, ImageInfo
from src.converter.base import BaseConverter, ConversionConfig, ConversionContext
from src.converter.exceptions import (
    ConverterErrorCode,
    EncodingError,
    ErrorContext,
    FileReadError,
    HTMLFetchError,
    HTMLParseError,
)
from src.utils.helpers import (
    clean_text,
    detect_encoding,
    safe_decode,
)


logger = logging.getLogger(__name__)


# 尝试导入可选依赖
try:
    from bs4 import BeautifulSoup, Tag, NavigableString
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    BeautifulSoup = None
    Tag = None

try:
    import markdownify
    HAS_MARKDOWNIFY = True
except ImportError:
    HAS_MARKDOWNIFY = False
    markdownify = None

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = None


class HTMLConverter(BaseConverter):
    """
    HTML文档转换器
    
    将HTML文件转换为Markdown格式，支持本地文件和URL。
    
    依赖：
    - beautifulsoup4: HTML解析
    - markdownify: HTML到Markdown转换
    - requests: URL获取（可选）
    
    特性：
    - 智能内容区域检测
    - 自动清理脚本、样式等无关元素
    - 元数据提取（title, meta标签）
    - 链接和图片处理
    
    使用示例:
        converter = HTMLConverter()
        result = converter.convert(DocumentInput(file_path="page.html"))
        if result.success:
            print(result.document.content)
    """
    
    # 默认要移除的元素选择器
    DEFAULT_REMOVE_SELECTORS = [
        "script",
        "style",
        "noscript",
        "iframe",
        "nav",
        "header",
        "footer",
        "aside",
        ".sidebar",
        ".navigation",
        ".nav",
        ".menu",
        ".advertisement",
        ".ads",
        ".ad",
        ".comments",
        ".comment",
        "#comments",
        ".social-share",
        ".share-buttons",
        ".related-posts",
        ".footer",
        ".header",
    ]
    
    # 默认内容选择器（按优先级排序）
    DEFAULT_CONTENT_SELECTORS = [
        "article",
        "main",
        ".article",
        ".content",
        ".post",
        ".entry",
        ".article-content",
        ".post-content",
        ".entry-content",
        "#content",
        "#main",
        "#article",
        "body",
    ]
    
    def __init__(self, config: Optional[ConversionConfig] = None):
        """
        初始化HTML转换器
        
        Args:
            config: 转换配置
        """
        super().__init__(config)
        
        # 检查依赖
        if not HAS_BS4:
            logger.warning(
                "beautifulsoup4未安装，HTML转换功能将受限。"
                "请运行: pip install beautifulsoup4"
            )
        
        if not HAS_MARKDOWNIFY:
            logger.warning(
                "markdownify未安装，将使用简单的HTML到Markdown转换。"
                "请运行: pip install markdownify"
            )
    
    def supports(self, file_type: FileType) -> bool:
        """检查是否支持指定的文件类型"""
        return file_type == FileType.HTML
    
    def _is_url(self, path: str) -> bool:
        """检查路径是否为URL"""
        parsed = urlparse(path)
        return parsed.scheme in ("http", "https")
    
    def _fetch_url(self, url: str, config: ConversionConfig) -> Tuple[str, str]:
        """
        获取URL内容
        
        Args:
            url: URL地址
            config: 转换配置
        
        Returns:
            (HTML内容, 最终URL)
        
        Raises:
            HTMLFetchError: 获取失败
        """
        if not HAS_REQUESTS:
            raise HTMLFetchError(
                url=url,
                context=ErrorContext(
                    file_path=url,
                    operation="fetch",
                    extra={"error": "requests库未安装"}
                )
            )
        
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                )
            }
            
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # 获取最终URL（处理重定向）
            final_url = response.url
            
            # 获取内容编码
            encoding = response.encoding
            if encoding and encoding.lower() == "iso-8859-1":
                # requests默认使用ISO-8859-1，尝试检测真实编码
                detected, _ = detect_encoding(response.content)
                encoding = detected
            
            content = response.content.decode(encoding or "utf-8", errors="replace")
            
            return content, final_url
        
        except requests.RequestException as e:
            status_code = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
            raise HTMLFetchError(
                url=url,
                status_code=status_code,
                cause=e,
                context=ErrorContext(
                    file_path=url,
                    operation="fetch"
                )
            )
    
    def _read_file_content(self, context: ConversionContext) -> Tuple[str, Optional[str]]:
        """
        读取HTML内容
        
        Args:
            context: 转换上下文
        
        Returns:
            (HTML内容, 基础URL)
        
        Raises:
            FileReadError: 读取失败
            HTMLFetchError: URL获取失败
        """
        file_path = str(context.file_path)
        config = context.config
        
        # 检查是否为URL
        if self._is_url(file_path):
            content, base_url = self._fetch_url(file_path, config)
            return content, base_url
        
        # 本地文件
        try:
            with open(context.file_path, "rb") as f:
                raw_content = f.read()
        except IOError as e:
            raise FileReadError(
                file_path=file_path,
                cause=e
            )
        
        # 检测编码
        if config.detect_encoding:
            encoding, _ = detect_encoding(raw_content)
        else:
            encoding = context.input.encoding or config.default_encoding
        
        content = safe_decode(raw_content, encoding=encoding)
        
        # 本地文件使用file:// URL作为基础URL
        base_url = context.file_path.absolute().as_uri()
        
        return content, base_url
    
    def _parse_html(self, content: str) -> "BeautifulSoup":
        """
        解析HTML内容
        
        Args:
            content: HTML字符串
        
        Returns:
            BeautifulSoup对象
        
        Raises:
            HTMLParseError: 解析失败
        """
        if not HAS_BS4:
            raise HTMLParseError(
                message="beautifulsoup4库未安装，无法解析HTML",
                context=ErrorContext(operation="parse")
            )
        
        try:
            # 使用html.parser作为默认解析器
            soup = BeautifulSoup(content, "html.parser")
            return soup
        except Exception as e:
            raise HTMLParseError(
                message=f"HTML解析失败: {e}",
                cause=e
            )
    
    def _remove_unwanted_elements(
        self,
        soup: "BeautifulSoup",
        selectors: List[str]
    ) -> None:
        """
        移除不需要的元素
        
        Args:
            soup: BeautifulSoup对象
            selectors: 要移除的CSS选择器列表
        """
        for selector in selectors:
            try:
                for element in soup.select(selector):
                    element.decompose()
            except Exception as e:
                logger.debug(f"移除选择器 {selector} 失败: {e}")
    
    def _find_content_element(
        self,
        soup: "BeautifulSoup",
        selectors: List[str]
    ) -> Optional["Tag"]:
        """
        查找主要内容元素
        
        Args:
            soup: BeautifulSoup对象
            selectors: 内容选择器列表（按优先级）
        
        Returns:
            找到的内容元素，如果没找到则返回None
        """
        for selector in selectors:
            try:
                element = soup.select_one(selector)
                if element and self._has_meaningful_content(element):
                    return element
            except Exception as e:
                logger.debug(f"选择器 {selector} 查询失败: {e}")
        
        return None
    
    def _has_meaningful_content(self, element: "Tag") -> bool:
        """
        检查元素是否有有意义的内容
        
        Args:
            element: HTML元素
        
        Returns:
            是否有有意义的内容
        """
        text = element.get_text(strip=True)
        # 至少有100个字符才算有意义
        return len(text) >= 100
    
    def _convert_to_markdown(
        self,
        element: "Tag",
        base_url: Optional[str] = None,
        preserve_links: bool = True
    ) -> str:
        """
        将HTML元素转换为Markdown
        
        Args:
            element: HTML元素
            base_url: 基础URL（用于解析相对链接）
            preserve_links: 是否保留链接
        
        Returns:
            Markdown内容
        """
        if HAS_MARKDOWNIFY:
            # 使用markdownify进行转换
            try:
                md_content = markdownify.markdownify(
                    str(element),
                    heading_style="ATX",
                    bullets="-",
                    strip=["script", "style"]
                )
                return md_content
            except Exception as e:
                logger.warning(f"markdownify转换失败: {e}，使用简单转换")
        
        # 简单的HTML到Markdown转换
        return self._simple_html_to_markdown(element, base_url, preserve_links)
    
    def _simple_html_to_markdown(
        self,
        element: "Tag",
        base_url: Optional[str] = None,
        preserve_links: bool = True
    ) -> str:
        """
        简单的HTML到Markdown转换（回退方案）
        
        Args:
            element: HTML元素
            base_url: 基础URL
            preserve_links: 是否保留链接
        
        Returns:
            Markdown内容
        """
        result = []
        
        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    result.append(text)
            elif isinstance(child, Tag):
                tag_name = child.name.lower()
                
                # 标题
                if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    level = int(tag_name[1])
                    prefix = "#" * level
                    text = child.get_text(strip=True)
                    result.append(f"\n{prefix} {text}\n")
                
                # 段落
                elif tag_name == "p":
                    text = child.get_text(strip=True)
                    if text:
                        result.append(f"\n{text}\n")
                
                # 链接
                elif tag_name == "a" and preserve_links:
                    href = child.get("href", "")
                    text = child.get_text(strip=True)
                    if base_url and href and not urlparse(href).scheme:
                        href = urljoin(base_url, href)
                    if text and href:
                        result.append(f"[{text}]({href})")
                    elif text:
                        result.append(text)
                
                # 图片
                elif tag_name == "img":
                    src = child.get("src", "")
                    alt = child.get("alt", "")
                    if base_url and src and not urlparse(src).scheme:
                        src = urljoin(base_url, src)
                    if src:
                        result.append(f"![{alt}]({src})")
                
                # 列表
                elif tag_name in ("ul", "ol"):
                    for i, li in enumerate(child.find_all("li", recursive=False)):
                        prefix = "-" if tag_name == "ul" else f"{i+1}."
                        text = li.get_text(strip=True)
                        result.append(f"{prefix} {text}")
                    result.append("")
                
                # 代码块
                elif tag_name == "pre":
                    code = child.find("code")
                    if code:
                        lang = ""
                        classes = code.get("class", [])
                        for cls in classes:
                            if cls.startswith("language-"):
                                lang = cls[9:]
                                break
                        text = code.get_text()
                        result.append(f"\n```{lang}\n{text}\n```\n")
                    else:
                        result.append(f"\n```\n{child.get_text()}\n```\n")
                
                # 内联代码
                elif tag_name == "code":
                    text = child.get_text()
                    result.append(f"`{text}`")
                
                # 强调
                elif tag_name in ("strong", "b"):
                    text = child.get_text(strip=True)
                    result.append(f"**{text}**")
                
                elif tag_name in ("em", "i"):
                    text = child.get_text(strip=True)
                    result.append(f"*{text}*")
                
                # 引用
                elif tag_name == "blockquote":
                    text = child.get_text(strip=True)
                    lines = text.split("\n")
                    quoted = "\n".join(f"> {line}" for line in lines)
                    result.append(f"\n{quoted}\n")
                
                # 分隔线
                elif tag_name == "hr":
                    result.append("\n---\n")
                
                # 表格
                elif tag_name == "table":
                    result.append(self._convert_table_to_markdown(child))
                
                # 其他块级元素
                elif tag_name in ("div", "section", "article"):
                    inner = self._simple_html_to_markdown(child, base_url, preserve_links)
                    result.append(inner)
                
                # 其他行内元素
                else:
                    text = child.get_text(strip=True)
                    if text:
                        result.append(text)
        
        return " ".join(result)
    
    def _convert_table_to_markdown(self, table: "Tag") -> str:
        """
        将HTML表格转换为Markdown表格
        
        Args:
            table: 表格元素
        
        Returns:
            Markdown表格
        """
        rows = []
        
        # 处理表头
        thead = table.find("thead")
        if thead:
            header_row = thead.find("tr")
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
                if headers:
                    rows.append("| " + " | ".join(headers) + " |")
                    rows.append("| " + " | ".join(["---"] * len(headers)) + " |")
        
        # 处理表体
        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr", recursive=False):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                # 如果还没有表头，使用第一行作为表头
                if not rows:
                    rows.append("| " + " | ".join(cells) + " |")
                    rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
                else:
                    rows.append("| " + " | ".join(cells) + " |")
        
        return "\n" + "\n".join(rows) + "\n" if rows else ""
    
    def _extract_images(
        self,
        soup: "BeautifulSoup",
        base_url: Optional[str],
        context: ConversionContext
    ) -> List[ImageInfo]:
        """
        提取图片信息
        
        Args:
            soup: BeautifulSoup对象
            base_url: 基础URL
            context: 转换上下文
        
        Returns:
            图片信息列表
        """
        images = []
        
        for i, img in enumerate(soup.find_all("img")):
            src = img.get("src", "")
            if not src:
                continue
            
            # 解析相对URL
            if base_url and not urlparse(src).scheme:
                src = urljoin(base_url, src)
            
            # 获取图片信息
            alt = img.get("alt", "")
            width = img.get("width", 0)
            height = img.get("height", 0)
            
            try:
                width = int(width) if width else 0
                height = int(height) if height else 0
            except ValueError:
                width = height = 0
            
            # 推断MIME类型
            mime_type = "image/jpeg"  # 默认
            if src.lower().endswith(".png"):
                mime_type = "image/png"
            elif src.lower().endswith(".gif"):
                mime_type = "image/gif"
            elif src.lower().endswith(".webp"):
                mime_type = "image/webp"
            elif src.lower().endswith(".svg"):
                mime_type = "image/svg+xml"
            
            image_info = ImageInfo(
                image_id=f"{context.document_id}_img_{i}",
                image_path=src,
                mime_type=mime_type,
                width=width or 0,
                height=height or 0,
                caption=alt or None
            )
            images.append(image_info)
        
        return images
    
    def _extract_html_metadata(
        self,
        soup: "BeautifulSoup"
    ) -> Dict[str, Any]:
        """
        从HTML中提取元数据
        
        Args:
            soup: BeautifulSoup对象
        
        Returns:
            元数据字典
        """
        metadata: Dict[str, Any] = {}
        
        # 提取标题
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)
        
        # 提取meta标签
        meta_mappings = {
            "description": ["description", "og:description"],
            "keywords": ["keywords"],
            "author": ["author", "og:author"],
            "language": ["language", "og:locale"],
        }
        
        for field, names in meta_mappings.items():
            for name in names:
                meta = soup.find("meta", attrs={"name": name}) or \
                       soup.find("meta", attrs={"property": name})
                if meta and meta.get("content"):
                    value = meta["content"]
                    if field == "keywords":
                        # 将关键词字符串转换为列表
                        metadata[field] = [k.strip() for k in value.split(",")]
                    else:
                        metadata[field] = value
                    break
        
        # 提取作者（可能是多个）
        author_meta = soup.find_all("meta", attrs={"name": "author"})
        if author_meta:
            authors = [m.get("content") for m in author_meta if m.get("content")]
            if authors:
                metadata["authors"] = authors
        
        # 提取发布日期
        date_names = ["article:published_time", "og:published_time", "date", "pubdate"]
        for name in date_names:
            meta = soup.find("meta", attrs={"property": name}) or \
                   soup.find("meta", attrs={"name": name})
            if meta and meta.get("content"):
                try:
                    from datetime import datetime
                    date_str = meta["content"]
                    # 尝试解析ISO格式
                    if "T" in date_str:
                        metadata["publication_date"] = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                    break
                except Exception:
                    pass
        
        return metadata
    
    def _convert_content(self, context: ConversionContext) -> str:
        """
        执行HTML到Markdown的转换
        
        Args:
            context: 转换上下文
        
        Returns:
            Markdown内容
        """
        config = context.config
        
        # 读取HTML内容
        html_content, base_url = self._read_file_content(context)
        
        # 解析HTML
        soup = self._parse_html(html_content)
        
        # 移除不需要的元素
        remove_selectors = config.remove_selectors or self.DEFAULT_REMOVE_SELECTORS
        self._remove_unwanted_elements(soup, remove_selectors)
        
        # 查找内容区域
        content_selectors = config.content_selectors or self.DEFAULT_CONTENT_SELECTORS
        content_element = self._find_content_element(soup, content_selectors)
        
        if content_element is None:
            context.add_warning("未找到主要内容区域，使用整个body")
            content_element = soup.find("body") or soup
        
        # 提取图片
        if config.extract_images:
            context.images = self._extract_images(soup, base_url, context)
        
        # 转换为Markdown
        markdown_content = self._convert_to_markdown(
            content_element,
            base_url=base_url,
            preserve_links=config.preserve_links
        )
        
        # 清理内容
        markdown_content = clean_text(markdown_content)
        
        return markdown_content
    
    def _extract_metadata(self, context: ConversionContext) -> BaseMetadata:
        """
        提取文档元数据
        
        Args:
            context: 转换上下文
        
        Returns:
            元数据对象
        """
        # 使用预设的元数据作为基础
        if context.input.metadata:
            base_metadata = context.input.metadata.model_copy()
        else:
            base_metadata = BaseMetadata()
        
        try:
            # 重新解析HTML以提取元数据
            html_content, _ = self._read_file_content(context)
            soup = self._parse_html(html_content)
            
            html_metadata = self._extract_html_metadata(soup)
            
            # 合并元数据（预设的优先）
            if not base_metadata.title and html_metadata.get("title"):
                base_metadata.title = html_metadata["title"]
            
            if not base_metadata.abstract and html_metadata.get("description"):
                base_metadata.abstract = html_metadata["description"]
            
            if not base_metadata.keywords and html_metadata.get("keywords"):
                base_metadata.keywords = html_metadata["keywords"]
            
            if not base_metadata.authors and html_metadata.get("authors"):
                base_metadata.authors = html_metadata["authors"]
            
            if not base_metadata.publication_date and html_metadata.get("publication_date"):
                base_metadata.publication_date = html_metadata["publication_date"]
            
            if not base_metadata.language and html_metadata.get("language"):
                base_metadata.language = html_metadata["language"]
        
        except Exception as e:
            logger.warning(f"提取HTML元数据失败: {e}")
        
        # 如果还没有标题，使用文件名
        if not base_metadata.title:
            base_metadata.title = context.file_path.stem
        
        return base_metadata