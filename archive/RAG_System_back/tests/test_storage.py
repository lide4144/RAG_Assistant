"""
RAG存储模块单元测试

测试覆盖：
1. 异常处理测试
2. 分块器测试
3. 向量化器测试
4. 向量存储测试
5. 存储服务测试
"""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# ============================================================
# 1. 异常处理测试
# ============================================================

class TestExceptions:
    """测试异常类和错误处理"""
    
    def test_storage_error_code_values(self):
        """测试错误码枚举值"""
        from src.storage.exceptions import StorageErrorCode
        
        assert StorageErrorCode.STORAGE_CONNECTION_FAILED.value == "E3001"
        assert StorageErrorCode.EMBEDDING_FAILED.value == "E3002"
        assert StorageErrorCode.CHUNKING_FAILED.value == "E3003"
        assert StorageErrorCode.DOCUMENT_EXISTS.value == "E3004"
        assert StorageErrorCode.DOCUMENT_NOT_FOUND.value == "E3005"
        assert StorageErrorCode.COLLECTION_NOT_FOUND.value == "E3006"
    
    def test_storage_error_creation(self):
        """测试存储错误创建"""
        from src.storage.exceptions import StorageError, StorageErrorCode
        
        error = StorageError(
            code=StorageErrorCode.STORAGE_CONNECTION_FAILED,
            message="数据库连接失败",
        )
        
        assert error.code == StorageErrorCode.STORAGE_CONNECTION_FAILED
        assert error.message == "数据库连接失败"
        assert "E3001" in str(error)
    
    def test_embedding_error(self):
        """测试嵌入错误"""
        from src.storage.exceptions import EmbeddingError, StorageErrorCode
        
        error = EmbeddingError(
            message="模型加载失败",
            model_name="test-model",
        )
        
        assert error.code == StorageErrorCode.EMBEDDING_FAILED
        assert error.context.model_name == "test-model"
    
    def test_chunking_error(self):
        """测试分块错误"""
        from src.storage.exceptions import ChunkingError, StorageErrorCode
        
        error = ChunkingError(message="分块失败")
        assert error.code == StorageErrorCode.CHUNKING_FAILED
    
    def test_empty_content_error(self):
        """测试空内容错误"""
        from src.storage.exceptions import EmptyContentError
        
        error = EmptyContentError()
        assert "E3003" in str(error)
    
    def test_document_exists_error(self):
        """测试文档已存在错误"""
        from src.storage.exceptions import DocumentExistsError
        
        error = DocumentExistsError(document_id="doc-123")
        assert error.context.document_id == "doc-123"
    
    def test_collection_not_found_error(self):
        """测试集合未找到错误"""
        from src.storage.exceptions import CollectionNotFoundError
        
        error = CollectionNotFoundError(collection_name="test-collection")
        assert error.context.collection_name == "test-collection"
    
    def test_validate_error_code(self):
        """测试错误码验证"""
        from src.storage.exceptions import validate_error_code
        
        assert validate_error_code("E3001") is True
        assert validate_error_code("E3002") is True
        assert validate_error_code("E3001.1") is True  # 子错误码
        assert validate_error_code("E4001") is False  # 不属于存储模块
        assert validate_error_code("invalid") is False
    
    def test_create_error_response(self):
        """测试创建错误响应"""
        from src.storage.exceptions import (
            create_error_response,
            StorageError,
            StorageErrorCode,
        )
        
        error = StorageError(
            code=StorageErrorCode.STORAGE_CONNECTION_FAILED,
            message="测试错误",
        )
        
        response = create_error_response(error)
        
        assert response["success"] is False
        assert response["error"]["code"] == "E3001"
        assert response["error"]["message"] == "测试错误"
    
    def test_wrap_exception(self):
        """测试异常包装"""
        from src.storage.exceptions import wrap_exception, StorageError
        
        original = ValueError("原始错误")
        wrapped = wrap_exception(original, operation="test_operation")
        
        assert isinstance(wrapped, StorageError)
        assert wrapped.context.operation == "test_operation"


# ============================================================
# 2. 分块器测试
# ============================================================

class TestChunker:
    """测试文档分块器"""
    
    @pytest.fixture
    def sample_text(self):
        """示例文本"""
        return """# 第一章 引言

这是引言的第一段。这段话包含了一些基本信息。

这是引言的第二段。我们将讨论更多内容。

## 第二章 方法

这是方法章节的内容。我们介绍了主要的技术方法。

### 2.1 实验设计

实验设计的详细说明。包括数据收集和分析方法。

# 第三章 结论

这是结论章节。总结了主要发现。
"""
    
    @pytest.fixture
    def sample_document(self, sample_text):
        """创建示例MarkdownDocument"""
        from src.models.schemas import (
            MarkdownDocument,
            BaseMetadata,
            SourceInfo,
            FileType,
        )
        
        return MarkdownDocument(
            document_id="test-doc",
            content=sample_text,
            metadata=BaseMetadata(title="测试文档"),
            source_info=SourceInfo(
                original_file_path="/test/doc.md",
                original_file_type=FileType.MARKDOWN,
                original_file_size_bytes=len(sample_text.encode("utf-8")),
                original_file_hash="test123",
            ),
            word_count=len(sample_text),
        )
    
    def test_paragraph_split_strategy(self):
        """测试段落分割策略"""
        from src.storage.chunker import ParagraphSplitStrategy
        
        strategy = ParagraphSplitStrategy()
        text = "第一段。\n\n第二段。\n\n第三段。"
        
        segments = strategy.split(text)
        
        assert len(segments) == 3
        assert "第一段" in segments[0]
        assert "第二段" in segments[1]
        assert "第三段" in segments[2]
    
    def test_sentence_split_strategy(self):
        """测试句子分割策略"""
        from src.storage.chunker import SentenceSplitStrategy
        
        strategy = SentenceSplitStrategy()
        text = "第一句。第二句！第三句？第四句。"
        
        segments = strategy.split(text)
        
        assert len(segments) >= 3
    
    def test_token_split_strategy(self):
        """测试Token分割策略"""
        from src.storage.chunker import TokenSplitStrategy
        
        strategy = TokenSplitStrategy(chars_per_token=2.5)
        text = "这是 一个 测试 文本 用于 验证 分词 功能"
        
        segments = strategy.split(text)
        
        assert len(segments) >= 1
    
    def test_section_parser(self):
        """测试章节解析器"""
        from src.storage.chunker import SectionParser
        
        parser = SectionParser()
        text = """# 标题1

内容1

## 标题2

内容2

### 标题3

内容3
"""
        sections = parser.parse(text)
        
        assert len(sections) == 3
        assert sections[0].title == "标题1"
        assert sections[1].title == "标题2"
        assert sections[2].title == "标题3"
    
    def test_chunker_basic(self, sample_document):
        """测试基本分块功能"""
        from src.storage.chunker import Chunker
        from src.models.schemas import ChunkingConfig
        
        config = ChunkingConfig(
            chunk_size=200,
            chunk_overlap=50,
        )
        chunker = Chunker(config)
        
        result = chunker.chunk_document(sample_document)
        
        assert len(result.chunks) > 0
        assert result.total_chars > 0
        
        # 验证块属性
        for chunk in result.chunks:
            assert chunk.document_id == "test-doc"
            assert chunk.chunk_id.startswith("test-doc_")
            assert len(chunk.content) > 0
    
    def test_chunker_respect_sections(self, sample_document):
        """测试尊重章节边界"""
        from src.storage.chunker import Chunker
        from src.models.schemas import ChunkingConfig
        
        config = ChunkingConfig(
            chunk_size=200,
            chunk_overlap=0,
            respect_sections=True,
        )
        chunker = Chunker(config)
        
        result = chunker.chunk_document(sample_document)
        
        # 验证章节标题已分配
        section_titles = [c.section_title for c in result.chunks if c.section_title]
        assert len(section_titles) > 0
    
    def test_chunker_with_metadata(self, sample_document):
        """测试带元数据的分块"""
        from src.storage.chunker import Chunker
        from src.models.schemas import ChunkingConfig
        
        config = ChunkingConfig(chunk_size=300)
        chunker = Chunker(config)
        
        result = chunker.chunk_document(sample_document)
        
        for chunk in result.chunks:
            assert "title" in chunk.metadata
    
    def test_chunker_empty_content(self):
        """测试空内容处理"""
        from src.storage.chunker import Chunker
        from src.storage.exceptions import EmptyContentError
        from src.models.schemas import (
            MarkdownDocument,
            BaseMetadata,
            SourceInfo,
            FileType,
        )
        
        chunker = Chunker()
        
        empty_doc = MarkdownDocument(
            document_id="empty-doc",
            content="",
            metadata=BaseMetadata(),
            source_info=SourceInfo(
                original_file_path="/test/empty.md",
                original_file_type=FileType.MARKDOWN,
                original_file_size_bytes=0,
                original_file_hash="empty",
            ),
            word_count=0,
        )
        
        with pytest.raises(EmptyContentError):
            chunker.chunk_document(empty_doc)
    
    def test_chunker_whitespace_only(self):
        """测试仅空白内容处理"""
        from src.storage.chunker import Chunker
        from src.storage.exceptions import EmptyContentError
        from src.models.schemas import (
            MarkdownDocument,
            BaseMetadata,
            SourceInfo,
            FileType,
        )
        
        chunker = Chunker()
        
        whitespace_doc = MarkdownDocument(
            document_id="whitespace-doc",
            content="   \n\n  \t  ",
            metadata=BaseMetadata(),
            source_info=SourceInfo(
                original_file_path="/test/whitespace.md",
                original_file_type=FileType.MARKDOWN,
                original_file_size_bytes=10,
                original_file_hash="whitespace",
            ),
            word_count=0,
        )
        
        with pytest.raises(EmptyContentError):
            chunker.chunk_document(whitespace_doc)
    
    def test_create_chunker_helper(self):
        """测试创建分块器辅助函数"""
        from src.storage.chunker import create_chunker
        
        chunker = create_chunker(
            chunk_size=256,
            chunk_overlap=32,
            split_by="sentence",
        )
        
        assert chunker.config.chunk_size == 256
        assert chunker.config.chunk_overlap == 32
    
    def test_chunk_document_helper(self, sample_document):
        """测试分块文档辅助函数"""
        from src.storage.chunker import chunk_document
        from src.models.schemas import ChunkingConfig
        
        # 使用较小的chunk_size以确保生成块
        config = ChunkingConfig(chunk_size=100, chunk_overlap=10)
        chunks = chunk_document(sample_document, config)
        
        assert len(chunks) > 0


# ============================================================
# 3. 向量化器测试
# ============================================================

class TestEmbedder:
    """测试向量化器"""
    
    def test_embedding_config_defaults(self):
        """测试嵌入配置默认值"""
        from src.storage.embedder import EmbeddingConfig
        
        config = EmbeddingConfig()
        
        assert config.provider == "sentence-transformers"
        assert config.model_name is not None
    
    def test_embedding_config_openai(self):
        """测试OpenAI嵌入配置"""
        from src.storage.embedder import EmbeddingConfig
        
        config = EmbeddingConfig(
            provider="openai",
            model_name="text-embedding-ada-002",
            api_key="test-key",
        )
        
        assert config.provider == "openai"
        assert config.api_key == "test-key"
    
    @pytest.mark.skipif(
        True,  # 跳过需要下载模型的测试
        reason="需要下载模型文件，在CI环境中跳过"
    )
    def test_sentence_transformers_embedder(self):
        """测试Sentence-Transformers嵌入器"""
        from src.storage.embedder import SentenceTransformersEmbedder, EmbeddingConfig
        
        config = EmbeddingConfig(
            provider="sentence-transformers",
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
        )
        
        embedder = SentenceTransformersEmbedder(config)
        
        # 测试单文本嵌入
        text = "这是一个测试文本"
        embedding = embedder.embed_text(text)
        
        assert len(embedding) > 0
        assert all(isinstance(v, float) for v in embedding)
    
    @pytest.mark.skipif(
        True,
        reason="需要下载模型文件"
    )
    def test_batch_embedding(self):
        """测试批量嵌入"""
        from src.storage.embedder import SentenceTransformersEmbedder, EmbeddingConfig
        
        config = EmbeddingConfig(
            provider="sentence-transformers",
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
        )
        
        embedder = SentenceTransformersEmbedder(config)
        
        texts = ["文本1", "文本2", "文本3"]
        embeddings = embedder.embed_texts(texts)
        
        assert len(embeddings) == 3
        assert all(len(e) == embedder.dimension for e in embeddings)
    
    def test_embedder_factory_invalid_provider(self):
        """测试工厂创建无效提供商"""
        from src.storage.embedder import EmbedderFactory, EmbeddingConfig
        from src.storage.exceptions import EmbeddingError
        
        config = EmbeddingConfig(provider="invalid-provider")
        
        with pytest.raises(EmbeddingError):
            EmbedderFactory.create(config)
    
    def test_openai_embedder_missing_api_key(self):
        """测试OpenAI嵌入器缺少API密钥"""
        from src.storage.embedder import OpenAIEmbedder, EmbeddingConfig
        from src.storage.exceptions import MissingAPIKeyError
        
        config = EmbeddingConfig(
            provider="openai",
            model_name="text-embedding-ada-002",
            api_key=None,
        )
        
        # 清除环境变量
        import os
        original_key = os.environ.pop("OPENAI_API_KEY", None)
        
        try:
            with pytest.raises(MissingAPIKeyError):
                OpenAIEmbedder(config)
        finally:
            if original_key:
                os.environ["OPENAI_API_KEY"] = original_key


# ============================================================
# 4. 向量存储测试
# ============================================================

class TestVectorStore:
    """测试向量存储"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def sample_chunks(self):
        """示例文档块"""
        from src.models.schemas import EmbeddedChunk
        
        return [
            EmbeddedChunk(
                chunk_id="doc1_0",
                document_id="doc1",
                content="深度学习是人工智能的核心技术",
                chunk_index=0,
                start_char=0,
                end_char=50,
                section_title="引言",
                metadata={"title": "深度学习"},
                embedding=[0.1] * 384,
                embedding_model="test-model",
                embedding_dimension=384,
            ),
            EmbeddedChunk(
                chunk_id="doc1_1",
                document_id="doc1",
                content="神经网络可以学习复杂的数据表示",
                chunk_index=1,
                start_char=51,
                end_char=100,
                section_title="方法",
                metadata={"title": "深度学习"},
                embedding=[0.2] * 384,
                embedding_model="test-model",
                embedding_dimension=384,
            ),
            EmbeddedChunk(
                chunk_id="doc2_0",
                document_id="doc2",
                content="知识图谱用于存储实体关系",
                chunk_index=0,
                start_char=0,
                end_char=50,
                metadata={"title": "知识图谱"},
                embedding=[0.3] * 384,
                embedding_model="test-model",
                embedding_dimension=384,
            ),
        ]
    
    def test_vector_store_config(self):
        """测试向量存储配置"""
        from src.storage.vector_store import VectorStoreConfig
        
        config = VectorStoreConfig(
            db_type="chroma",
            persist_directory="/tmp/test",
            collection_name="test_collection",
        )
        
        assert config.db_type == "chroma"
        assert config.collection_name == "test_collection"
    
    def test_search_result_dataclass(self):
        """测试搜索结果数据类"""
        from src.storage.vector_store import SearchResult
        from src.models.schemas import RetrievedChunk
        
        chunk = RetrievedChunk(
            chunk_id="test_0",
            document_id="test",
            content="测试内容",
            similarity_score=0.95,
            metadata={"title": "测试"},
        )
        
        result = SearchResult(
            chunks=[chunk],
            total_found=1,
        )
        
        assert len(result.chunks) == 1
        assert result.chunks[0].similarity_score == 0.95
    
    @pytest.mark.skipif(
        True,
        reason="需要ChromaDB依赖"
    )
    def test_chroma_vector_store_creation(self, temp_dir):
        """测试ChromaDB向量存储创建"""
        from src.storage.vector_store import ChromaVectorStore, VectorStoreConfig
        
        config = VectorStoreConfig(
            db_type="chroma",
            persist_directory=temp_dir,
            collection_name="test_collection",
        )
        
        store = ChromaVectorStore(config)
        
        assert store._config.collection_name == "test_collection"
    
    @pytest.mark.skipif(
        True,
        reason="需要ChromaDB依赖"
    )
    def test_add_and_search(self, temp_dir, sample_chunks):
        """测试添加和搜索"""
        from src.storage.vector_store import ChromaVectorStore, VectorStoreConfig
        import numpy as np
        
        config = VectorStoreConfig(
            db_type="chroma",
            persist_directory=temp_dir,
        )
        
        store = ChromaVectorStore(config)
        
        # 添加块
        store.add_chunks(sample_chunks)
        
        # 搜索
        query_embedding = [0.15] * 384
        results = store.search(query_embedding, top_k=2)
        
        assert len(results.chunks) == 2
        assert all(hasattr(r, 'similarity_score') for r in results.chunks)
    
    def test_vector_store_factory_invalid_backend(self):
        """测试工厂创建无效后端"""
        from src.storage.vector_store import VectorStoreFactory, VectorStoreConfig
        from src.storage.exceptions import DatabaseInitError
        
        config = VectorStoreConfig(db_type="invalid-backend")
        
        with pytest.raises(DatabaseInitError):
            VectorStoreFactory.create(config)


# ============================================================
# 5. 存储服务测试
# ============================================================

class TestStorageService:
    """测试存储服务"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def sample_document(self):
        """示例Markdown文档"""
        from src.models.schemas import (
            MarkdownDocument,
            BaseMetadata,
            SourceInfo,
            FileType,
        )
        
        return MarkdownDocument(
            document_id="test-doc-001",
            content="""# 测试文档

## 摘要

这是一个测试文档，用于验证存储服务的功能。

## 第一章

第一章的内容。这里有一些详细的说明。

## 第二章

第二章的内容。包含更多技术细节。
""",
            metadata=BaseMetadata(
                title="测试文档",
                authors=["测试作者"],
                abstract="这是一个测试文档",
                keywords=["测试", "演示"],
            ),
            source_info=SourceInfo(
                original_file_path="/test/document.pdf",
                original_file_type=FileType.PDF,
                original_file_size_bytes=1024,
                original_file_hash="test123",
            ),
            word_count=100,
        )
    
    def test_storage_service_config(self):
        """测试存储服务配置"""
        from src.storage.service import StorageServiceConfig
        
        config = StorageServiceConfig(
            chunk_size=300,
            chunk_overlap=50,
            embedding_provider="sentence-transformers",
            vector_db_type="chroma",
        )
        
        assert config.chunk_size == 300
        assert config.embedding_provider == "sentence-transformers"
    
    def test_storage_service_config_defaults(self):
        """测试存储服务配置默认值"""
        from src.storage.service import StorageServiceConfig
        
        config = StorageServiceConfig()
        
        assert config.chunk_size == 512
        assert config.chunk_overlap == 50
        assert config.split_by == "paragraph"
        assert config.respect_sections is True
    
    @pytest.mark.skipif(
        True,
        reason="需要sentence-transformers和chromadb依赖"
    )
    def test_storage_service_store_document(self, temp_dir, sample_document):
        """测试存储文档"""
        from src.storage.service import RAGStorageService, StorageServiceConfig
        from src.models.schemas import StorageInput
        
        config = StorageServiceConfig(
            chunk_size=200,
            persist_directory=temp_dir,
        )
        
        service = RAGStorageService(config)
        
        input = StorageInput(documents=[sample_document])
        result = service.store_documents(input)
        
        assert result.success is True
        assert result.total_documents == 1
        assert result.total_chunks > 0
    
    @pytest.mark.skipif(
        True,
        reason="需要依赖"
    )
    def test_storage_service_search(self, temp_dir, sample_document):
        """测试搜索功能"""
        from src.storage.service import RAGStorageService, StorageServiceConfig
        from src.models.schemas import StorageInput
        
        config = StorageServiceConfig(persist_directory=temp_dir)
        service = RAGStorageService(config)
        
        # 先存储
        input = StorageInput(documents=[sample_document])
        service.store_documents(input)
        
        # 搜索
        results = service.search("测试文档", top_k=3)
        
        assert len(results) > 0
    
    def test_store_documents_helper(self):
        """测试便捷函数"""
        from src.storage.service import store_documents, get_storage_service
        
        # 验证函数存在
        assert callable(store_documents)
        assert callable(get_storage_service)


# ============================================================
# 6. 集成测试
# ============================================================

class TestIntegration:
    """集成测试"""
    
    def test_module_imports(self):
        """测试模块导入"""
        from src.storage import (
            # 异常
            StorageError,
            StorageErrorCode,
            EmbeddingError,
            ChunkingError,
            # 分块器
            Chunker,
            ParagraphSplitStrategy,
            SentenceSplitStrategy,
            # 向量化器
            EmbeddingConfig,
            BaseEmbedder,
            EmbedderFactory,
            # 向量存储
            VectorStoreConfig,
            BaseVectorStore,
            VectorStoreFactory,
            # 服务
            RAGStorageService,
            StorageServiceConfig,
        )
        
        # 验证导入成功
        assert StorageErrorCode is not None
        assert Chunker is not None
        assert EmbeddingConfig is not None
        assert VectorStoreConfig is not None
        assert RAGStorageService is not None
    
    def test_error_code_consistency(self):
        """测试错误码一致性"""
        from src.storage.exceptions import StorageErrorCode
        from src.models.schemas import ErrorCode
        
        # 验证存储模块错误码与全局错误码一致
        storage_codes = [e.value for e in StorageErrorCode]
        
        # 所有E3xxx错误码应该以E3开头
        for code in storage_codes:
            assert code.startswith("E3")
            # 主错误码部分应该在3001-3999范围内
            main_code = code.split(".")[0]
            num = int(main_code[1:])
            assert 3001 <= num <= 3999
    
    def test_schema_compatibility(self):
        """测试数据结构兼容性"""
        from src.models.schemas import (
            ChunkingConfig,
            DocumentChunk,
            EmbeddedChunk,
            StorageInput,
            StorageResult,
        )
        
        # 验证数据结构可以正常创建
        config = ChunkingConfig(
            chunk_size=256,
            chunk_overlap=32,
            split_by="paragraph",
        )
        
        assert config.chunk_size == 256
        
        chunk = DocumentChunk(
            chunk_id="test_0",
            document_id="test",
            content="测试内容",
            chunk_index=0,
            start_char=0,
            end_char=10,
        )
        
        assert chunk.chunk_id == "test_0"


# ============================================================
# 运行测试
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])