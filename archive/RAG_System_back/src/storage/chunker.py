"""
文档分块器 (Document Chunker)

负责将Markdown文档分割成合适的文本块（Chunks）。

支持的分割策略：
- paragraph: 按段落分割
- sentence: 按句子分割
- token: 按词元分割（简化实现，按字符计数）

主要功能：
1. 智能分块，尊重章节边界
2. 可配置的块大小和重叠
3. 保留块的位置信息和元数据
"""

from __future__ import annotations

import logging
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.models.schemas import (
    ChunkingConfig,
    DocumentChunk,
    MarkdownDocument,
)
from src.storage.exceptions import (
    ChunkingError,
    EmptyContentError,
    InvalidChunkConfigError,
    StorageErrorContext,
)


logger = logging.getLogger(__name__)


# ============================================================
# 分割策略接口
# ============================================================

class SplitStrategy(ABC):
    """分割策略抽象基类"""
    
    @abstractmethod
    def split(self, text: str) -> List[str]:
        """
        将文本分割成片段
        
        Args:
            text: 输入文本
        
        Returns:
            分割后的文本片段列表
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        pass


class ParagraphSplitStrategy(SplitStrategy):
    """
    段落分割策略
    
    按照空行（连续换行符）分割文本为段落
    """
    
    # 匹配段落分隔符（一个或多个空行）
    PARAGRAPH_PATTERN = re.compile(r'\n\s*\n')
    
    def split(self, text: str) -> List[str]:
        """按段落分割文本"""
        paragraphs = self.PARAGRAPH_PATTERN.split(text)
        # 过滤空段落并strip
        return [p.strip() for p in paragraphs if p.strip()]
    
    @property
    def name(self) -> str:
        return "paragraph"


class SentenceSplitStrategy(SplitStrategy):
    """
    句子分割策略
    
    支持中英文句子分割
    """
    
    # 中英文句子结束符
    SENTENCE_PATTERN = re.compile(r'(?<=[。！？.!?])\s*')
    
    def split(self, text: str) -> List[str]:
        """按句子分割文本"""
        sentences = self.SENTENCE_PATTERN.split(text)
        # 过滤空句子并strip
        return [s.strip() for s in sentences if s.strip()]
    
    @property
    def name(self) -> str:
        return "sentence"


class TokenSplitStrategy(SplitStrategy):
    """
    词元分割策略（简化实现）
    
    使用字符计数作为简化的token计数
    对于精确的token计数，应使用专用的tokenizer
    """
    
    def __init__(self, chars_per_token: float = 2.5):
        """
        初始化
        
        Args:
            chars_per_token: 每个token的平均字符数
                - 英文约 4 字符/token
                - 中文约 1.5-2 字符/token
                - 混合文本取 2.5 作为折中
        """
        self.chars_per_token = chars_per_token
    
    def split(self, text: str) -> List[str]:
        """
        按字符分割文本（作为token的近似）
        
        实际上是按单词和标点分割
        """
        # 使用更智能的分割：按空格和标点
        # 这里简化为按空白符和中文字符边界分割
        tokens = re.findall(r'\S+|\s+', text)
        return [t for t in tokens if t.strip()]
    
    @property
    def name(self) -> str:
        return "token"


# ============================================================
# 章节解析器
# ============================================================

@dataclass
class Section:
    """文档章节信息"""
    title: str
    level: int  # 标题级别 (1-6)
    start_pos: int  # 在原文档中的起始位置
    end_pos: int  # 在原文档中的结束位置
    content: str  # 章节内容（包含标题）


class SectionParser:
    """
    Markdown章节解析器
    
    解析Markdown文档的章节结构
    """
    
    # 匹配Markdown标题
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+?)$', re.MULTILINE)
    
    def parse(self, content: str) -> List[Section]:
        """
        解析文档章节
        
        Args:
            content: Markdown文档内容
        
        Returns:
            章节列表
        """
        sections: List[Section] = []
        
        # 找到所有标题
        headings = list(self.HEADING_PATTERN.finditer(content))
        
        if not headings:
            # 没有标题，整个文档作为一个章节
            return [Section(
                title="",
                level=0,
                start_pos=0,
                end_pos=len(content),
                content=content
            )]
        
        # 处理第一个标题之前的内容
        if headings[0].start() > 0:
            sections.append(Section(
                title="",
                level=0,
                start_pos=0,
                end_pos=headings[0].start(),
                content=content[:headings[0].start()].strip()
            ))
        
        # 处理每个标题对应的章节
        for i, match in enumerate(headings):
            level = len(match.group(1))
            title = match.group(2).strip()
            start_pos = match.start()
            
            # 确定章节结束位置
            if i + 1 < len(headings):
                end_pos = headings[i + 1].start()
            else:
                end_pos = len(content)
            
            section_content = content[start_pos:end_pos].strip()
            
            sections.append(Section(
                title=title,
                level=level,
                start_pos=start_pos,
                end_pos=end_pos,
                content=section_content
            ))
        
        return sections


# ============================================================
# 文档分块器
# ============================================================

@dataclass
class ChunkResult:
    """分块结果"""
    chunks: List[DocumentChunk]
    total_chars: int
    section_count: int


class Chunker:
    """
    文档分块器
    
    将MarkdownDocument分割成DocumentChunk列表
    
    特性：
    - 支持多种分割策略（段落、句子、词元）
    - 可配置的块大小和重叠
    - 尊重章节边界（可选）
    - 保留位置信息和元数据
    
    使用示例:
        chunker = Chunker(ChunkingConfig(
            chunk_size=512,
            chunk_overlap=50,
            split_by="paragraph",
            respect_sections=True
        ))
        
        result = chunker.chunk_document(markdown_doc)
        for chunk in result.chunks:
            print(f"Chunk {chunk.chunk_index}: {chunk.content[:50]}...")
    """
    
    # 分割策略注册表
    STRATEGIES: Dict[str, type] = {
        "paragraph": ParagraphSplitStrategy,
        "sentence": SentenceSplitStrategy,
        "token": TokenSplitStrategy,
    }
    
    def __init__(self, config: Optional[ChunkingConfig] = None):
        """
        初始化分块器
        
        Args:
            config: 分块配置，如果为None则使用默认配置
        """
        self.config = config or ChunkingConfig()
        self._validate_config()
        
        # 获取分割策略
        self._strategy = self._get_strategy()
        
        # 章节解析器
        self._section_parser = SectionParser()
        
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def _validate_config(self) -> None:
        """验证配置有效性"""
        if self.config.chunk_size < 100:
            raise InvalidChunkConfigError(
                message=f"chunk_size 不能小于 100，当前值: {self.config.chunk_size}",
                config_field="chunk_size"
            )
        
        if self.config.chunk_overlap >= self.config.chunk_size:
            raise InvalidChunkConfigError(
                message=f"chunk_overlap ({self.config.chunk_overlap}) 必须小于 chunk_size ({self.config.chunk_size})",
                config_field="chunk_overlap"
            )
        
        if self.config.split_by not in self.STRATEGIES:
            raise InvalidChunkConfigError(
                message=f"不支持的分割方式: {self.config.split_by}，支持: {list(self.STRATEGIES.keys())}",
                config_field="split_by"
            )
    
    def _get_strategy(self) -> SplitStrategy:
        """获取分割策略实例"""
        strategy_class = self.STRATEGIES[self.config.split_by]
        return strategy_class()
    
    def chunk_document(self, document: MarkdownDocument) -> ChunkResult:
        """
        对文档进行分块
        
        Args:
            document: Markdown文档
        
        Returns:
            ChunkResult: 包含所有块的结果
        
        Raises:
            EmptyContentError: 文档内容为空
            ChunkingError: 分块过程中的其他错误
        """
        content = document.content.strip()
        
        if not content:
            raise EmptyContentError(document_id=document.document_id)
        
        self._logger.info(
            f"开始分块文档: {document.document_id}, "
            f"内容长度: {len(content)}, "
            f"策略: {self.config.split_by}"
        )
        
        try:
            if self.config.respect_sections:
                chunks = self._chunk_with_sections(document)
            else:
                chunks = self._chunk_simple(document)
            
            self._logger.info(
                f"分块完成: {document.document_id}, "
                f"生成 {len(chunks)} 个块"
            )
            
            # 计算章节数量
            sections = self._section_parser.parse(content)
            section_count = len([s for s in sections if s.title])
            
            return ChunkResult(
                chunks=chunks,
                total_chars=len(content),
                section_count=section_count
            )
        
        except (EmptyContentError, InvalidChunkConfigError):
            raise
        except Exception as e:
            self._logger.exception(f"分块失败: {document.document_id}")
            raise ChunkingError(
                message=f"分块过程中发生错误: {str(e)}",
                document_id=document.document_id,
                cause=e
            )
    
    def _chunk_simple(self, document: MarkdownDocument) -> List[DocumentChunk]:
        """
        简单分块（不考虑章节边界）
        
        Args:
            document: 文档
        
        Returns:
            块列表
        """
        content = document.content
        
        # 使用策略分割文本
        segments = self._strategy.split(content)
        
        # 合并小片段成块
        chunks = self._merge_segments_to_chunks(
            segments=segments,
            document_id=document.document_id,
            metadata=self._build_chunk_metadata(document),
            section_title=None,
            base_offset=0
        )
        
        return chunks
    
    def _chunk_with_sections(self, document: MarkdownDocument) -> List[DocumentChunk]:
        """
        按章节分块（尊重章节边界）
        
        Args:
            document: 文档
        
        Returns:
            块列表
        """
        content = document.content
        
        # 解析章节
        sections = self._section_parser.parse(content)
        
        all_chunks: List[DocumentChunk] = []
        chunk_index = 0
        
        for section in sections:
            if not section.content.strip():
                continue
            
            # 对每个章节单独分块
            segments = self._strategy.split(section.content)
            
            section_chunks = self._merge_segments_to_chunks(
                segments=segments,
                document_id=document.document_id,
                metadata=self._build_chunk_metadata(document),
                section_title=section.title or None,
                base_offset=section.start_pos,
                start_index=chunk_index
            )
            
            all_chunks.extend(section_chunks)
            chunk_index += len(section_chunks)
        
        return all_chunks
    
    def _merge_segments_to_chunks(
        self,
        segments: List[str],
        document_id: str,
        metadata: Dict[str, Any],
        section_title: Optional[str],
        base_offset: int,
        start_index: int = 0
    ) -> List[DocumentChunk]:
        """
        将分割后的片段合并成块
        
        遵循配置的chunk_size和chunk_overlap
        
        Args:
            segments: 分割后的文本片段
            document_id: 文档ID
            metadata: 块元数据
            section_title: 所属章节标题
            base_offset: 在原文档中的基础偏移量
            start_index: 起始块索引
        
        Returns:
            块列表
        """
        if not segments:
            return []
        
        chunks: List[DocumentChunk] = []
        current_content: List[str] = []
        current_length = 0
        current_start = base_offset
        chunk_index = start_index
        
        for segment in segments:
            segment_length = len(segment)
            
            # 如果当前块加上新片段超过大小限制
            if current_length + segment_length > self.config.chunk_size and current_content:
                # 创建当前块
                chunk_text = self._join_segments(current_content)
                chunks.append(self._create_chunk(
                    document_id=document_id,
                    content=chunk_text,
                    chunk_index=chunk_index,
                    start_char=current_start,
                    end_char=current_start + len(chunk_text),
                    section_title=section_title,
                    metadata=metadata
                ))
                chunk_index += 1
                
                # 处理重叠
                overlap_content, overlap_length = self._get_overlap_content(
                    current_content, current_length
                )
                
                # 更新当前位置
                current_start = current_start + len(chunk_text) - overlap_length
                current_content = overlap_content
                current_length = overlap_length
            
            # 添加新片段
            current_content.append(segment)
            current_length += segment_length
        
        # 处理剩余内容
        if current_content:
            chunk_text = self._join_segments(current_content)
            min_size = self._get_min_chunk_size()
            
            # 防止数据丢失的策略
            if len(chunk_text) >= min_size or min_size == 0:
                # 块足够大或配置为保留所有内容，创建新块
                chunks.append(self._create_chunk(
                    document_id=document_id,
                    content=chunk_text,
                    chunk_index=chunk_index,
                    start_char=current_start,
                    end_char=current_start + len(chunk_text),
                    section_title=section_title,
                    metadata=metadata
                ))
            elif self.config.merge_small_chunks and chunks:
                # 配置为合并小块，且存在前一个块，则合并
                last_chunk = chunks[-1]
                merged_content = last_chunk.content + "\n\n" + chunk_text
                chunks[-1] = DocumentChunk(
                    chunk_id=last_chunk.chunk_id,
                    document_id=last_chunk.document_id,
                    content=merged_content,
                    chunk_index=last_chunk.chunk_index,
                    start_char=last_chunk.start_char,
                    end_char=current_start + len(chunk_text),
                    section_title=last_chunk.section_title,
                    metadata=last_chunk.metadata
                )
            else:
                # 配置为不合并或没有前一个块，保留为独立块（防止数据丢失）
                self._logger.warning(
                    f"创建小块 (长度={len(chunk_text)}): {chunk_text[:50]}... "
                    f"建议调整chunk_size或启用merge_small_chunks"
                )
                chunks.append(self._create_chunk(
                    document_id=document_id,
                    content=chunk_text,
                    chunk_index=chunk_index,
                    start_char=current_start,
                    end_char=current_start + len(chunk_text),
                    section_title=section_title,
                    metadata=metadata
                ))
        
        return chunks
    
    def _get_min_chunk_size(self) -> int:
        """
        获取最小块大小
        
        Returns:
            最小块大小（字符数）
            - 如果配置中指定了min_chunk_size，使用该值
            - 否则使用默认值（chunk_size的20%，最小50字符）
        """
        if self.config.min_chunk_size > 0:
            return self.config.min_chunk_size
        # 如果min_chunk_size为0，表示不丢弃任何内容
        # 但为了避免创建极小的块，设置一个合理的默认值
        return 0  # 0表示保留所有内容
    
    def _get_overlap_content(
        self,
        segments: List[str],
        total_length: int
    ) -> Tuple[List[str], int]:
        """
        获取重叠部分的内容
        
        从末尾开始选取片段，直到达到overlap大小
        
        Args:
            segments: 当前块的所有片段
            total_length: 当前块的总长度
        
        Returns:
            (重叠的片段列表, 重叠的字符数)
        """
        if self.config.chunk_overlap <= 0:
            return [], 0
        
        overlap_segments: List[str] = []
        overlap_length = 0
        
        for segment in reversed(segments):
            if overlap_length + len(segment) > self.config.chunk_overlap:
                break
            overlap_segments.insert(0, segment)
            overlap_length += len(segment)
        
        return overlap_segments, overlap_length
    
    def _join_segments(self, segments: List[str]) -> str:
        """
        连接片段成文本
        
        Args:
            segments: 片段列表
        
        Returns:
            连接后的文本
        """
        # 根据分割策略选择连接符
        if self.config.split_by == "paragraph":
            return "\n\n".join(segments)
        elif self.config.split_by == "sentence":
            return " ".join(segments)
        else:
            return "".join(segments)
    
    def _create_chunk(
        self,
        document_id: str,
        content: str,
        chunk_index: int,
        start_char: int,
        end_char: int,
        section_title: Optional[str],
        metadata: Dict[str, Any]
    ) -> DocumentChunk:
        """
        创建文档块对象
        
        Args:
            document_id: 文档ID
            content: 块内容
            chunk_index: 块索引
            start_char: 起始字符位置
            end_char: 结束字符位置
            section_title: 章节标题
            metadata: 元数据
        
        Returns:
            DocumentChunk对象
        """
        chunk_id = f"{document_id}_{chunk_index}"
        
        return DocumentChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            content=content,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            section_title=section_title,
            metadata=metadata.copy()
        )
    
    def _build_chunk_metadata(self, document: MarkdownDocument) -> Dict[str, Any]:
        """
        构建块的元数据
        
        从文档元数据中提取关键信息
        
        Args:
            document: 文档
        
        Returns:
            元数据字典
        """
        metadata = {}
        
        doc_meta = document.metadata
        if doc_meta:
            if doc_meta.title:
                metadata["title"] = doc_meta.title
            if doc_meta.authors:
                metadata["authors"] = doc_meta.authors
            if doc_meta.source:
                metadata["source"] = doc_meta.source
            if doc_meta.keywords:
                metadata["keywords"] = doc_meta.keywords
            if doc_meta.language:
                metadata["language"] = doc_meta.language
        
        # 添加来源信息
        if document.source_info:
            metadata["original_file"] = document.source_info.original_file_path
            metadata["file_type"] = document.source_info.original_file_type.value
        
        return metadata
    
    def chunk_text(
        self,
        text: str,
        document_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        """
        对纯文本进行分块（便捷方法）
        
        Args:
            text: 文本内容
            document_id: 文档ID（可选，自动生成）
            metadata: 元数据（可选）
        
        Returns:
            块列表
        """
        if not text.strip():
            raise EmptyContentError()
        
        doc_id = document_id or str(uuid.uuid4())
        meta = metadata or {}
        
        segments = self._strategy.split(text)
        
        return self._merge_segments_to_chunks(
            segments=segments,
            document_id=doc_id,
            metadata=meta,
            section_title=None,
            base_offset=0
        )


# ============================================================
# 便捷函数
# ============================================================

def create_chunker(
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    split_by: str = "paragraph",
    respect_sections: bool = True
) -> Chunker:
    """
    创建分块器的便捷函数
    
    Args:
        chunk_size: 块大小
        chunk_overlap: 重叠大小
        split_by: 分割方式
        respect_sections: 是否尊重章节边界
    
    Returns:
        Chunker实例
    """
    config = ChunkingConfig(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        split_by=split_by,
        respect_sections=respect_sections
    )
    return Chunker(config)


def chunk_document(
    document: MarkdownDocument,
    config: Optional[ChunkingConfig] = None
) -> List[DocumentChunk]:
    """
    分块文档的便捷函数
    
    Args:
        document: Markdown文档
        config: 分块配置
    
    Returns:
        块列表
    """
    chunker = Chunker(config)
    result = chunker.chunk_document(document)
    return result.chunks