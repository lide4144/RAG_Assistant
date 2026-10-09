"""
工具函数模块

提供系统中使用的各种辅助函数和工具。

主要功能：
- 文件操作工具
- 文件类型检测
- 编码检测和处理
- 文本处理
- Markdown格式化
- 时间测量
"""

from src.utils.helpers import (
    # 文件操作
    calculate_file_hash,
    ensure_directory,
    generate_unique_filename,
    get_file_extension,
    get_file_size,
    is_valid_file,
    make_safe_filename,
    
    # 文件类型检测
    detect_file_type,
    get_supported_extensions,
    is_supported_file_type,
    EXTENSION_TO_FILE_TYPE,
    MIME_TO_FILE_TYPE,
    
    # 编码处理
    detect_encoding,
    safe_decode,
    COMMON_ENCODINGS,
    
    # 文本处理
    clean_text,
    count_words,
    extract_sections,
    normalize_whitespace,
    truncate_text,
    
    # Markdown工具
    create_markdown_table,
    escape_markdown,
    format_metadata_as_yaml,
    
    # 时间工具
    get_current_timestamp,
    timer,
)


__all__ = [
    # 文件操作
    "ensure_directory",
    "get_file_size",
    "calculate_file_hash",
    "get_file_extension",
    "is_valid_file",
    "make_safe_filename",
    "generate_unique_filename",
    
    # 文件类型检测
    "detect_file_type",
    "is_supported_file_type",
    "get_supported_extensions",
    "EXTENSION_TO_FILE_TYPE",
    "MIME_TO_FILE_TYPE",
    
    # 编码处理
    "detect_encoding",
    "safe_decode",
    "COMMON_ENCODINGS",
    
    # 文本处理
    "normalize_whitespace",
    "clean_text",
    "count_words",
    "extract_sections",
    "truncate_text",
    
    # Markdown工具
    "escape_markdown",
    "create_markdown_table",
    "format_metadata_as_yaml",
    
    # 时间工具
    "timer",
    "get_current_timestamp",
]