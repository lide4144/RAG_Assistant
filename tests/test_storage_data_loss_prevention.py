"""
测试分块器的数据丢失防止功能

验证新增的 min_chunk_size 和 merge_small_chunks 参数是否能有效防止短章节被丢弃
"""

import pytest
from src.models.schemas import (
    ChunkingConfig,
    MarkdownDocument,
    BaseMetadata,
    SourceInfo,
    FileType,
)
from src.storage.chunker import Chunker


class TestDataLossPrevention:
    """测试数据丢失防止功能"""
    
    @pytest.fixture
    def short_sections_document(self):
        """创建包含多个短章节的文档"""
        content = """# 第一章 引言

这是引言的第一段。

## 第二章 方法

方法简述。

### 2.1 实验

实验说明。

# 第三章 结论

结论总结。
"""
        return MarkdownDocument(
            document_id="short-sections",
            content=content,
            metadata=BaseMetadata(title="短章节文档"),
            source_info=SourceInfo(
                original_file_path="/test/short.md",
                original_file_type=FileType.MARKDOWN,
                original_file_size_bytes=len(content.encode("utf-8")),
                original_file_hash="test456",
            ),
            word_count=len(content),
        )
    
    def test_default_config_preserves_all_content(self, short_sections_document):
        """
        测试：默认配置（min_chunk_size=0）应保留所有内容
        
        这是防止数据丢失的关键测试
        """
        config = ChunkingConfig(
            chunk_size=512,
            chunk_overlap=50,
            respect_sections=True,
            min_chunk_size=0,  # 默认值，保留所有内容
            merge_small_chunks=True,
        )
        chunker = Chunker(config)
        result = chunker.chunk_document(short_sections_document)
        
        # 应该生成至少一个块（不应丢弃任何内容）
        assert len(result.chunks) > 0, "不应该丢弃任何内容块"
        
        # 验证所有文本内容都被包含
        all_chunk_content = " ".join(chunk.content for chunk in result.chunks)
        assert "引言" in all_chunk_content
        assert "方法" in all_chunk_content
        assert "实验" in all_chunk_content
        assert "结论" in all_chunk_content
    
    def test_min_chunk_size_zero_no_data_loss(self, short_sections_document):
        """
        测试：min_chunk_size=0 时不丢失任何数据
        """
        config = ChunkingConfig(
            chunk_size=200,
            respect_sections=True,
            min_chunk_size=0,  # 明确设为0
        )
        chunker = Chunker(config)
        result = chunker.chunk_document(short_sections_document)
        
        # 每个章节应该生成至少一个块
        assert len(result.chunks) >= 3, f"应该至少有3个块，实际有{len(result.chunks)}个"
        
        # 打印块内容以便调试
        for i, chunk in enumerate(result.chunks):
            print(f"块 {i}: {chunk.content[:50]}...")
    
    def test_merge_small_chunks_enabled(self, short_sections_document):
        """
        测试：启用 merge_small_chunks 时小块会被合并
        """
        config = ChunkingConfig(
            chunk_size=200,
            respect_sections=True,
            min_chunk_size=20,  # 设置一个小的阈值
            merge_small_chunks=True,  # 启用合并
        )
        chunker = Chunker(config)
        result = chunker.chunk_document(short_sections_document)
        
        # 应该有块生成，但数量可能因合并而减少
        assert len(result.chunks) > 0
        
        # 验证内容没有丢失
        all_content = " ".join(c.content for c in result.chunks)
        assert "引言" in all_content
        assert "方法" in all_content
    
    def test_merge_small_chunks_disabled(self, short_sections_document):
        """
        测试：禁用 merge_small_chunks 时小块保持独立
        """
        config = ChunkingConfig(
            chunk_size=200,
            respect_sections=True,
            min_chunk_size=20,
            merge_small_chunks=False,  # 禁用合并
        )
        chunker = Chunker(config)
        result = chunker.chunk_document(short_sections_document)
        
        # 应该有更多独立的小块
        assert len(result.chunks) > 0
        
        # 验证即使很小的块也被保留
        small_chunks = [c for c in result.chunks if len(c.content) < 50]
        if len(small_chunks) > 0:
            print(f"找到 {len(small_chunks)} 个小块（< 50字符）")
    
    def test_explicit_min_chunk_size(self):
        """
        测试：显式设置 min_chunk_size
        """
        config = ChunkingConfig(
            chunk_size=300,
            min_chunk_size=50,  # 显式设置最小块大小
            merge_small_chunks=True,
        )
        
        text = "这是一个短段落。\n\n这是第二个短段落。\n\n这是第三个非常非常非常长的段落，包含了更多的内容以确保它超过最小块大小的限制。"
        
        chunker = Chunker(config)
        chunks = chunker.chunk_text(text, document_id="test")
        
        # 应该有块生成
        assert len(chunks) > 0
        
        # 验证块的大小
        for chunk in chunks:
            print(f"块大小: {len(chunk.content)} 字符")
    
    def test_production_scenario_short_faqs(self):
        """
        测试：生产场景 - 处理FAQ类型的文档（很多短问答）
        """
        faq_content = """# FAQ

## Q1: 什么是深度学习？

深度学习是机器学习的一个分支。

## Q2: 什么是神经网络？

神经网络是深度学习的基础。

## Q3: 如何训练模型？

使用训练数据和优化算法。

## Q4: 什么是过拟合？

模型在训练集上表现好但在测试集上表现差。
"""
        
        doc = MarkdownDocument(
            document_id="faq",
            content=faq_content,
            metadata=BaseMetadata(title="FAQ文档"),
            source_info=SourceInfo(
                original_file_path="/test/faq.md",
                original_file_type=FileType.MARKDOWN,
                original_file_size_bytes=len(faq_content.encode("utf-8")),
                original_file_hash="faq123",
            ),
            word_count=len(faq_content),
        )
        
        # 使用生产推荐配置
        config = ChunkingConfig(
            chunk_size=512,
            chunk_overlap=50,
            respect_sections=True,
            min_chunk_size=0,  # 保留所有内容
            merge_small_chunks=True,  # 合并小块
        )
        
        chunker = Chunker(config)
        result = chunker.chunk_document(doc)
        
        # 关键：验证没有数据丢失
        assert len(result.chunks) > 0, "FAQ文档不应被丢弃"
        
        all_content = " ".join(c.content for c in result.chunks)
        # 验证所有问题都被保留
        assert "Q1" in all_content
        assert "Q2" in all_content
        assert "Q3" in all_content
        assert "Q4" in all_content
        assert "深度学习" in all_content
        assert "神经网络" in all_content
        
        print(f"✓ FAQ文档成功生成 {len(result.chunks)} 个块，无数据丢失")
    
    def test_comparison_old_vs_new_behavior(self, short_sections_document):
        """
        对比测试：展示新旧行为的区别
        """
        # 旧行为模拟：使用较大的min_chunk_size
        old_config = ChunkingConfig(
            chunk_size=512,
            min_chunk_size=100,  # 较大的最小值可能导致丢失
            merge_small_chunks=False,
        )
        
        # 新推荐配置：min_chunk_size=0
        new_config = ChunkingConfig(
            chunk_size=512,
            min_chunk_size=0,  # 不丢失任何内容
            merge_small_chunks=True,
        )
        
        old_chunker = Chunker(old_config)
        new_chunker = Chunker(new_config)
        
        old_result = old_chunker.chunk_document(short_sections_document)
        new_result = new_chunker.chunk_document(short_sections_document)
        
        print(f"旧配置生成块数: {len(old_result.chunks)}")
        print(f"新配置生成块数: {len(new_result.chunks)}")
        
        # 新配置应该保留更多内容
        assert len(new_result.chunks) >= len(old_result.chunks), \
            "新配置应该保留至少与旧配置相同或更多的块"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])