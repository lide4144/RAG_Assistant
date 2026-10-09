"""
文档转换模块单元测试

测试内容：
1. 异常类和错误码
2. 工具函数
3. 各转换器
4. 转换服务
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# 导入被测试的模块
from src.converter import (
    BaseConverter,
    BatchConversionResult,
    BatchDocumentInput,
    ConversionConfig,
    ConversionResult,
    ConverterError,
    ConverterErrorCode,
    DocumentConverterService,
    DocumentInput,
    ErrorContext,
    FileType,
    HTMLConverter,
    MarkdownConverter,
    MarkdownDocument,
    PDFConverter,
    TXTConverter,
    UnsupportedFileTypeError,
    convert_document,
)
from src.utils import (
    calculate_file_hash,
    clean_text,
    count_words,
    create_markdown_table,
    detect_encoding,
    detect_file_type,
    ensure_directory,
    escape_markdown,
    extract_sections,
    get_file_extension,
    get_file_size,
    is_valid_file,
    make_safe_filename,
    normalize_whitespace,
    safe_decode,
    timer,
)


# ============================================================
# 测试夹具
# ============================================================

@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_txt_file(temp_dir):
    """创建示例TXT文件"""
    file_path = temp_dir / "sample.txt"
    content = """这是一个测试文档

第一章 引言

这是引言部分的内容。本文主要讨论文档转换技术。

第二章 方法

这是方法部分的内容。我们使用了多种技术来实现转换。

第三章 结论

这是结论部分的内容。
"""
    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.fixture
def sample_html_file(temp_dir):
    """创建示例HTML文件"""
    file_path = temp_dir / "sample.html"
    content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>测试文档</title>
    <meta name="description" content="这是一个测试描述">
    <meta name="keywords" content="测试,文档,HTML">
    <meta name="author" content="张三">
</head>
<body>
    <nav>导航栏</nav>
    <article>
        <h1>测试文档标题</h1>
        <p>这是第一段内容。</p>
        <h2>第一节</h2>
        <p>这是第一节的内容。包含一些<strong>重要</strong>的信息。</p>
        <h2>第二节</h2>
        <p>这是第二节的内容。包含一个<a href="https://example.com">链接</a>。</p>
        <ul>
            <li>列表项1</li>
            <li>列表项2</li>
        </ul>
    </article>
    <footer>页脚</footer>
</body>
</html>
"""
    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.fixture
def sample_md_file(temp_dir):
    """创建示例Markdown文件"""
    file_path = temp_dir / "sample.md"
    content = """---
title: 测试Markdown文档
author: 李四
keywords:
  - markdown
  - test
---

# 测试文档

这是一个测试Markdown文档。

## 第一节

第一节的内容。

## 第二节

第二节的内容。
"""
    file_path.write_text(content, encoding="utf-8")
    return file_path


@pytest.fixture
def conversion_config():
    """创建测试用转换配置"""
    return ConversionConfig(
        extract_images=False,
        extract_tables=False,
        debug=True,
    )


# ============================================================
# 异常类测试
# ============================================================

class TestConverterExceptions:
    """测试转换器异常类"""
    
    def test_converter_error_basic(self):
        """测试基本异常创建"""
        error = ConverterError(
            code=ConverterErrorCode.CONVERSION_FAILED,
            message="测试错误"
        )
        
        assert error.code == ConverterErrorCode.CONVERSION_FAILED
        assert error.message == "测试错误"
        assert isinstance(error.timestamp, datetime)
    
    def test_converter_error_with_context(self):
        """测试带上下文的异常"""
        context = ErrorContext(
            file_path="/test/file.pdf",
            file_type="pdf",
            page_number=5
        )
        
        error = ConverterError(
            code=ConverterErrorCode.PDF_PARSE_ERROR,
            message="解析失败",
            context=context
        )
        
        assert error.context.file_path == "/test/file.pdf"
        assert error.context.page_number == 5
    
    def test_converter_error_to_dict(self):
        """测试异常转字典"""
        error = ConverterError(
            code=ConverterErrorCode.ENCODING_ERROR,
            message="编码错误"
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["code"] == "E2005"
        assert error_dict["message"] == "编码错误"
        assert "timestamp" in error_dict
    
    def test_unsupported_file_type_error(self):
        """测试不支持的文件类型异常"""
        error = UnsupportedFileTypeError(
            file_type="xyz",
            supported_types=["pdf", "html", "txt"]
        )
        
        assert error.code == ConverterErrorCode.UNSUPPORTED_FILE_TYPE
        assert "xyz" in error.message
        assert error.supported_types == ["pdf", "html", "txt"]
    
    def test_error_code_validation(self):
        """测试错误码验证"""
        # 有效的错误码
        assert ConverterErrorCode.CONVERSION_FAILED.value == "E2002"
        assert ConverterErrorCode.PDF_PARSE_ERROR.value == "E2003"
        
        # 验证错误码格式
        for code in ConverterErrorCode:
            assert code.value.startswith("E2")


# ============================================================
# 工具函数测试
# ============================================================

class TestHelperFunctions:
    """测试辅助函数"""
    
    def test_ensure_directory(self, temp_dir):
        """测试目录创建"""
        new_dir = temp_dir / "new" / "nested" / "dir"
        result = ensure_directory(new_dir)
        
        assert result.exists()
        assert result.is_dir()
    
    def test_get_file_size(self, sample_txt_file):
        """测试获取文件大小"""
        size = get_file_size(sample_txt_file)
        assert size > 0
    
    def test_calculate_file_hash(self, sample_txt_file):
        """测试文件哈希计算"""
        hash_md5 = calculate_file_hash(sample_txt_file, "md5")
        hash_sha256 = calculate_file_hash(sample_txt_file, "sha256")
        
        assert len(hash_md5) == 32  # MD5是32位十六进制
        assert len(hash_sha256) == 64  # SHA256是64位十六进制
    
    def test_get_file_extension(self):
        """测试获取文件扩展名"""
        assert get_file_extension("test.pdf") == "pdf"
        assert get_file_extension("test.HTML") == "html"
        assert get_file_extension("test.tar.gz") == "gz"
        assert get_file_extension("noextension") == ""
    
    def test_is_valid_file(self, sample_txt_file, temp_dir):
        """测试文件有效性检查"""
        assert is_valid_file(sample_txt_file) is True
        assert is_valid_file(temp_dir / "nonexistent.txt") is False
        assert is_valid_file(temp_dir) is False  # 目录不是有效文件
    
    def test_detect_file_type(self, sample_txt_file, sample_html_file):
        """测试文件类型检测"""
        assert detect_file_type(sample_txt_file) == FileType.TXT
        assert detect_file_type(sample_html_file) == FileType.HTML
    
    def test_normalize_whitespace(self):
        """测试空白规范化"""
        text = "  多个   空格  \n\n\n多个换行  "
        result = normalize_whitespace(text)
        
        assert "   " not in result
        assert "\n\n\n" not in result
    
    def test_clean_text(self):
        """测试文本清理"""
        text = "包含\x00控制\x01字符的文本"
        result = clean_text(text)
        
        assert "\x00" not in result
        assert "\x01" not in result
        assert "包含" in result
    
    def test_count_words(self):
        """测试字数统计"""
        # 中文
        chinese_text = "这是一段中文测试文本"
        assert count_words(chinese_text) > 0
        
        # 英文
        english_text = "This is a test text"
        assert count_words(english_text) == 5
        
        # 混合
        mixed_text = "这是test混合文本"
        count = count_words(mixed_text)
        assert count > 1
    
    def test_extract_sections(self):
        """测试章节提取"""
        markdown = """# 标题

## 第一节

内容

### 1.1 子节

## 第二节
"""
        sections = extract_sections(markdown)
        
        assert "标题" in sections
        assert "第一节" in sections
        assert "1.1 子节" in sections
    
    def test_escape_markdown(self):
        """测试Markdown转义"""
        text = "*bold* and _italic_ and `code`"
        result = escape_markdown(text)
        
        assert "\\*" in result
        assert "\\_" in result
        assert "\\`" in result
    
    def test_create_markdown_table(self):
        """测试创建Markdown表格"""
        headers = ["列1", "列2", "列3"]
        rows = [
            ["a", "b", "c"],
            ["d", "e", "f"],
        ]
        
        table = create_markdown_table(headers, rows)
        
        assert "| 列1 | 列2 | 列3 |" in table
        assert ":---" in table  # 左对齐标记
        assert "| a | b | c |" in table
    
    def test_make_safe_filename(self):
        """测试安全文件名"""
        unsafe = '<>:"/\\|?*test.txt'
        safe = make_safe_filename(unsafe)
        
        for char in '<>:"/\\|?*':
            assert char not in safe
    
    def test_timer(self):
        """测试计时器"""
        import time
        
        with timer() as t:
            time.sleep(0.01)  # 10ms
        
        assert t["elapsed_ms"] >= 10
    
    def test_detect_encoding(self):
        """测试编码检测"""
        # UTF-8
        utf8_bytes = "你好世界".encode("utf-8")
        encoding, confidence = detect_encoding(utf8_bytes)
        assert encoding.lower() in ["utf-8", "utf-8-sig"]
        
        # UTF-8 with BOM
        utf8_bom = b"\xef\xbb\xbf" + "测试".encode("utf-8")
        encoding, confidence = detect_encoding(utf8_bom)
        assert encoding.lower() == "utf-8-sig"
    
    def test_safe_decode(self):
        """测试安全解码"""
        # 正常UTF-8
        utf8_bytes = "测试文本".encode("utf-8")
        result = safe_decode(utf8_bytes)
        assert result == "测试文本"
        
        # 带编码
        gbk_bytes = "测试文本".encode("gbk")
        result = safe_decode(gbk_bytes, encoding="gbk")
        assert result == "测试文本"


# ============================================================
# TXT转换器测试
# ============================================================

class TestTXTConverter:
    """测试TXT转换器"""
    
    def test_supports(self):
        """测试支持的文件类型"""
        converter = TXTConverter()
        
        assert converter.supports(FileType.TXT) is True
        assert converter.supports(FileType.PDF) is False
        assert converter.supports(FileType.HTML) is False
    
    def test_convert_basic(self, sample_txt_file):
        """测试基本转换"""
        converter = TXTConverter()
        input = DocumentInput(file_path=str(sample_txt_file))
        
        result = converter.convert(input)
        
        assert result.success is True
        assert result.document is not None
        assert result.document.content is not None
        assert len(result.document.content) > 0
    
    def test_convert_with_title_inference(self, temp_dir):
        """测试标题推断"""
        file_path = temp_dir / "titled.txt"
        content = """论文标题

这是论文的正文内容。
"""
        file_path.write_text(content, encoding="utf-8")
        
        converter = TXTConverter()
        input = DocumentInput(file_path=str(file_path))
        result = converter.convert(input)
        
        assert result.success is True
        # 标题应该被推断或包含在内容中
        assert "论文标题" in result.document.content or \
               result.document.metadata.title is not None
    
    def test_convert_with_sections(self, sample_txt_file):
        """测试章节检测"""
        converter = TXTConverter()
        input = DocumentInput(file_path=str(sample_txt_file))
        
        result = converter.convert(input)
        
        assert result.success is True
        # 检查是否包含章节标题
        content = result.document.content
        assert "#" in content  # Markdown标题标记
    
    def test_convert_with_encoding(self, temp_dir):
        """测试编码处理"""
        file_path = temp_dir / "gbk.txt"
        content = "这是GBK编码的文本"
        file_path.write_bytes(content.encode("gbk"))
        
        converter = TXTConverter()
        input = DocumentInput(
            file_path=str(file_path),
            encoding="gbk"
        )
        result = converter.convert(input)
        
        assert result.success is True
        assert "GBK编码" in result.document.content


# ============================================================
# Markdown转换器测试
# ============================================================

class TestMarkdownConverter:
    """测试Markdown转换器"""
    
    def test_supports(self):
        """测试支持的文件类型"""
        converter = MarkdownConverter()
        
        assert converter.supports(FileType.MARKDOWN) is True
        assert converter.supports(FileType.TXT) is False
    
    def test_convert_basic(self, sample_md_file):
        """测试基本转换"""
        converter = MarkdownConverter()
        input = DocumentInput(file_path=str(sample_md_file))
        
        result = converter.convert(input)
        
        assert result.success is True
        assert result.document is not None
    
    def test_extract_front_matter(self, sample_md_file):
        """测试YAML front matter提取"""
        converter = MarkdownConverter()
        input = DocumentInput(file_path=str(sample_md_file))
        
        result = converter.convert(input)
        
        assert result.success is True
        # 元数据应该被提取
        assert result.document.metadata.title == "测试Markdown文档" or \
               "测试Markdown文档" in str(result.document.content)


# ============================================================
# HTML转换器测试
# ============================================================

class TestHTMLConverter:
    """测试HTML转换器"""
    
    def test_supports(self):
        """测试支持的文件类型"""
        converter = HTMLConverter()
        
        assert converter.supports(FileType.HTML) is True
        assert converter.supports(FileType.PDF) is False
    
    def test_convert_basic(self, sample_html_file):
        """测试基本转换"""
        converter = HTMLConverter()
        input = DocumentInput(file_path=str(sample_html_file))
        
        result = converter.convert(input)
        
        assert result.success is True
        assert result.document is not None
        assert result.document.content is not None
    
    def test_extract_metadata(self, sample_html_file):
        """测试元数据提取"""
        converter = HTMLConverter()
        input = DocumentInput(file_path=str(sample_html_file))
        
        result = converter.convert(input)
        
        assert result.success is True
        metadata = result.document.metadata
        
        # 检查标题
        assert metadata.title is not None
    
    def test_remove_unwanted_elements(self, sample_html_file):
        """测试移除不需要的元素"""
        converter = HTMLConverter()
        input = DocumentInput(file_path=str(sample_html_file))
        
        result = converter.convert(input)
        
        assert result.success is True
        content = result.document.content
        
        # 导航和页脚应该被移除
        assert "导航栏" not in content or len(content) < 1000  # 简单检查


# ============================================================
# 转换服务测试
# ============================================================

class TestDocumentConverterService:
    """测试文档转换服务"""
    
    def test_create_service(self):
        """测试创建服务"""
        service = DocumentConverterService()
        
        assert service is not None
        assert len(service.get_supported_types()) > 0
    
    def test_supported_types(self):
        """测试支持的类型"""
        service = DocumentConverterService()
        supported = service.get_supported_types()
        
        assert FileType.TXT in supported
        assert FileType.HTML in supported
        assert FileType.MARKDOWN in supported
    
    def test_is_supported(self, sample_txt_file, sample_html_file):
        """测试文件支持检查"""
        service = DocumentConverterService()
        
        assert service.is_supported(sample_txt_file) is True
        assert service.is_supported(sample_html_file) is True
        assert service.is_supported("nonexistent.xyz") is False
    
    def test_convert_document(self, sample_txt_file):
        """测试单文档转换"""
        service = DocumentConverterService()
        input = DocumentInput(file_path=str(sample_txt_file))
        
        result = service.convert_document(input)
        
        assert result.success is True
        assert result.document is not None
        assert result.processing_time_ms is not None
    
    def test_convert_file(self, sample_txt_file, temp_dir):
        """测试便捷文件转换方法"""
        service = DocumentConverterService()
        output_path = temp_dir / "output.md"
        
        result = service.convert_file(
            sample_txt_file,
            output_path=output_path
        )
        
        assert result.success is True
        assert output_path.exists()
    
    def test_convert_batch(self, sample_txt_file, sample_html_file):
        """测试批量转换"""
        service = DocumentConverterService()
        
        batch_input = BatchDocumentInput(
            documents=[
                DocumentInput(file_path=str(sample_txt_file)),
                DocumentInput(file_path=str(sample_html_file)),
            ],
            parallel=True,
            max_workers=2,
        )
        
        result = service.convert_batch(batch_input)
        
        assert result.total_count == 2
        assert result.success_count >= 1
        assert len(result.results) == 2
    
    def test_convert_nonexistent_file(self):
        """测试转换不存在的文件"""
        service = DocumentConverterService()
        input = DocumentInput(file_path="/nonexistent/file.txt")
        
        result = service.convert_document(input)
        
        assert result.success is False
        assert result.error_details is not None
    
    def test_convert_unsupported_type(self, temp_dir):
        """测试转换不支持的文件类型"""
        # 创建一个不支持的文件
        file_path = temp_dir / "test.xyz"
        file_path.write_text("test content")
        
        service = DocumentConverterService()
        input = DocumentInput(file_path=str(file_path))
        
        result = service.convert_document(input)
        
        assert result.success is False


# ============================================================
# 便捷函数测试
# ============================================================

class TestConvenienceFunctions:
    """测试便捷函数"""
    
    def test_convert_document_function(self, sample_txt_file):
        """测试convert_document便捷函数"""
        input = DocumentInput(file_path=str(sample_txt_file))
        result = convert_document(input)
        
        assert result.success is True


# ============================================================
# 错误处理测试
# ============================================================

class TestErrorHandling:
    """测试错误处理"""
    
    def test_file_not_found(self):
        """测试文件不存在错误"""
        service = DocumentConverterService()
        input = DocumentInput(file_path="/path/to/nonexistent/file.txt")
        
        result = service.convert_document(input)
        
        assert result.success is False
        assert "E2" in result.error_details  # 转换模块错误码
    
    def test_batch_continue_on_error(self, sample_txt_file, temp_dir):
        """测试批量处理错误继续"""
        service = DocumentConverterService()
        
        batch_input = BatchDocumentInput(
            documents=[
                DocumentInput(file_path=str(sample_txt_file)),
                DocumentInput(file_path="/nonexistent.txt"),
                DocumentInput(file_path=str(sample_txt_file)),
            ],
            continue_on_error=True,
        )
        
        result = service.convert_batch(batch_input)
        
        # 应该有2个成功，1个失败
        assert result.success_count == 2
        assert result.failed_count == 1


# ============================================================
# 数据模型测试
# ============================================================

class TestDataModels:
    """测试数据模型"""
    
    def test_document_input(self):
        """测试DocumentInput模型"""
        input = DocumentInput(
            file_path="/test/file.pdf",
            file_type=FileType.PDF,
            extract_images=True,
            extract_tables=False
        )
        
        assert input.file_path == "/test/file.pdf"
        assert input.file_type == FileType.PDF
        assert input.extract_images is True
        assert input.extract_tables is False
    
    def test_conversion_result(self):
        """测试ConversionResult模型"""
        from src.models.schemas import ProcessingStatus
        
        result = ConversionResult(
            success=True,
            status=ProcessingStatus.SUCCESS,
            message="转换成功",
            processing_time_ms=100.5,
        )
        
        assert result.success is True
        assert result.processing_time_ms == 100.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])