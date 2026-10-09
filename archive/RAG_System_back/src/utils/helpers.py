"""
工具函数模块

提供文档转换系统所需的各种辅助函数，包括：
- 文件操作工具
- 文件类型检测
- 文件哈希计算
- 编码检测
- 文本处理工具
- Markdown格式化工具
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.models.schemas import FileType


# ============================================================
# 文件操作工具
# ============================================================

def ensure_directory(path: Union[str, Path]) -> Path:
    """
    确保目录存在，如果不存在则创建
    
    Args:
        path: 目录路径
    
    Returns:
        Path对象
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_file_size(file_path: Union[str, Path]) -> int:
    """
    获取文件大小（字节）
    
    Args:
        file_path: 文件路径
    
    Returns:
        文件大小（字节）
    
    Raises:
        FileNotFoundError: 文件不存在
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    return path.stat().st_size


def calculate_file_hash(
    file_path: Union[str, Path],
    algorithm: str = "md5",
    chunk_size: int = 8192
) -> str:
    """
    计算文件的哈希值
    
    Args:
        file_path: 文件路径
        algorithm: 哈希算法（md5, sha1, sha256）
        chunk_size: 读取块大小
    
    Returns:
        哈希值的十六进制字符串
    
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不支持的算法
    """
    algorithms = {
        "md5": hashlib.md5,
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
    }
    
    if algorithm not in algorithms:
        raise ValueError(f"不支持的哈希算法: {algorithm}，支持: {list(algorithms.keys())}")
    
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    hasher = algorithms[algorithm]()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    
    return hasher.hexdigest()


def get_file_extension(file_path: Union[str, Path]) -> str:
    """
    获取文件扩展名（小写，不含点）
    
    Args:
        file_path: 文件路径
    
    Returns:
        小写的扩展名
    """
    return Path(file_path).suffix.lower().lstrip(".")


def is_valid_file(file_path: Union[str, Path]) -> bool:
    """
    检查文件是否有效（存在且可读）
    
    Args:
        file_path: 文件路径
    
    Returns:
        是否有效
    """
    path = Path(file_path)
    return path.exists() and path.is_file() and os.access(path, os.R_OK)


# ============================================================
# 文件类型检测
# ============================================================

# 扩展名到FileType的映射
EXTENSION_TO_FILE_TYPE: Dict[str, FileType] = {
    "pdf": FileType.PDF,
    "html": FileType.HTML,
    "htm": FileType.HTML,
    "xhtml": FileType.HTML,
    "txt": FileType.TXT,
    "text": FileType.TXT,
    "md": FileType.MARKDOWN,
    "markdown": FileType.MARKDOWN,
}

# MIME类型到FileType的映射
MIME_TO_FILE_TYPE: Dict[str, FileType] = {
    "application/pdf": FileType.PDF,
    "text/html": FileType.HTML,
    "application/xhtml+xml": FileType.HTML,
    "text/plain": FileType.TXT,
    "text/markdown": FileType.MARKDOWN,
    "text/x-markdown": FileType.MARKDOWN,
}

# 文件魔数（magic bytes）
FILE_SIGNATURES: Dict[bytes, FileType] = {
    b"%PDF": FileType.PDF,
    b"<!DOCTYPE html": FileType.HTML,
    b"<!doctype html": FileType.HTML,
    b"<html": FileType.HTML,
    b"<HTML": FileType.HTML,
}


def detect_file_type(
    file_path: Union[str, Path],
    content: Optional[bytes] = None
) -> Optional[FileType]:
    """
    检测文件类型
    
    检测优先级：
    1. 文件魔数（内容检测）
    2. MIME类型
    3. 扩展名
    
    Args:
        file_path: 文件路径
        content: 文件内容（可选，如果提供则跳过读取文件）
    
    Returns:
        检测到的文件类型，如果无法检测则返回None
    """
    path = Path(file_path)
    
    # 1. 尝试通过内容检测（魔数）
    if content is None and path.exists():
        try:
            with open(path, "rb") as f:
                content = f.read(1024)  # 只读取前1KB
        except (IOError, OSError):
            content = None
    
    if content:
        for signature, file_type in FILE_SIGNATURES.items():
            if content.startswith(signature):
                return file_type
    
    # 2. 尝试通过MIME类型检测
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type and mime_type in MIME_TO_FILE_TYPE:
        return MIME_TO_FILE_TYPE[mime_type]
    
    # 3. 通过扩展名检测
    ext = get_file_extension(path)
    if ext in EXTENSION_TO_FILE_TYPE:
        return EXTENSION_TO_FILE_TYPE[ext]
    
    return None


def is_supported_file_type(file_type: Union[str, FileType]) -> bool:
    """
    检查文件类型是否受支持
    
    Args:
        file_type: 文件类型或扩展名
    
    Returns:
        是否支持
    """
    if isinstance(file_type, FileType):
        return True
    
    file_type_lower = file_type.lower()
    return file_type_lower in EXTENSION_TO_FILE_TYPE or file_type_lower in [t.value for t in FileType]


def get_supported_extensions() -> List[str]:
    """
    获取支持的文件扩展名列表
    
    Returns:
        扩展名列表
    """
    return list(EXTENSION_TO_FILE_TYPE.keys())


# ============================================================
# 编码检测
# ============================================================

# 常见编码列表
COMMON_ENCODINGS = [
    "utf-8",
    "utf-8-sig",  # 带BOM的UTF-8
    "gbk",
    "gb2312",
    "gb18030",
    "big5",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "ascii",
    "iso-8859-1",
    "cp1252",
]


def detect_encoding(content: bytes) -> Tuple[str, float]:
    """
    检测文本编码
    
    Args:
        content: 字节内容
    
    Returns:
        (编码名称, 置信度) 元组
    """
    # 尝试使用chardet（如果可用）
    try:
        import chardet
        result = chardet.detect(content)
        if result and result.get("encoding"):
            return result["encoding"], result.get("confidence", 0.0)
    except ImportError:
        pass
    
    # 回退到手动检测
    # 检查BOM
    if content.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", 1.0
    if content.startswith(b"\xff\xfe"):
        return "utf-16-le", 1.0
    if content.startswith(b"\xfe\xff"):
        return "utf-16-be", 1.0
    
    # 尝试常见编码
    for encoding in COMMON_ENCODINGS:
        try:
            content.decode(encoding)
            return encoding, 0.8
        except (UnicodeDecodeError, LookupError):
            continue
    
    # 默认返回UTF-8
    return "utf-8", 0.5


def safe_decode(
    content: bytes,
    encoding: Optional[str] = None,
    errors: str = "replace"
) -> str:
    """
    安全地解码字节内容
    
    Args:
        content: 字节内容
        encoding: 指定的编码（可选）
        errors: 错误处理方式（strict, ignore, replace）
    
    Returns:
        解码后的字符串
    """
    if encoding:
        try:
            return content.decode(encoding, errors=errors)
        except (UnicodeDecodeError, LookupError):
            pass
    
    # 自动检测编码
    detected_encoding, _ = detect_encoding(content)
    try:
        return content.decode(detected_encoding, errors=errors)
    except (UnicodeDecodeError, LookupError):
        # 最后尝试UTF-8
        return content.decode("utf-8", errors="replace")


# ============================================================
# 文本处理工具
# ============================================================

def normalize_whitespace(text: str) -> str:
    """
    规范化空白字符
    
    - 将多个连续空格替换为单个空格
    - 将多个连续换行替换为两个换行
    - 去除行首行尾空白
    
    Args:
        text: 输入文本
    
    Returns:
        规范化后的文本
    """
    # 将特殊空白字符替换为普通空格
    text = re.sub(r"[\t\f\r ]+", " ", text)
    
    # 处理换行
    lines = text.split("\n")
    lines = [line.strip() for line in lines]
    
    # 合并连续空行
    result_lines = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                result_lines.append("")
            prev_empty = True
        else:
            result_lines.append(line)
            prev_empty = False
    
    return "\n".join(result_lines).strip()


def clean_text(text: str) -> str:
    """
    清理文本
    
    - 移除控制字符
    - 规范化Unicode
    - 规范化空白
    
    Args:
        text: 输入文本
    
    Returns:
        清理后的文本
    """
    # 规范化Unicode
    text = unicodedata.normalize("NFKC", text)
    
    # 移除控制字符（保留换行和制表符）
    text = "".join(
        char for char in text
        if not unicodedata.category(char).startswith("C") or char in "\n\t"
    )
    
    return normalize_whitespace(text)


def count_words(text: str) -> int:
    """
    统计字数
    
    对于中文，按字符计数；对于英文，按单词计数
    
    Args:
        text: 输入文本
    
    Returns:
        字数
    """
    # 中文字符计数
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    
    # 非中文部分按单词计数
    non_chinese = re.sub(r"[\u4e00-\u9fff]", " ", text)
    words = len(non_chinese.split())
    
    return chinese_chars + words


def extract_sections(markdown_content: str) -> List[str]:
    """
    从Markdown内容中提取章节标题
    
    Args:
        markdown_content: Markdown格式的文本
    
    Returns:
        章节标题列表
    """
    sections = []
    
    # 匹配Markdown标题（# 开头）
    pattern = r"^(#{1,6})\s+(.+?)$"
    
    for match in re.finditer(pattern, markdown_content, re.MULTILINE):
        title = match.group(2).strip()
        sections.append(title)
    
    return sections


def truncate_text(
    text: str,
    max_length: int,
    suffix: str = "..."
) -> str:
    """
    截断文本到指定长度
    
    Args:
        text: 输入文本
        max_length: 最大长度
        suffix: 截断后缀
    
    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


# ============================================================
# Markdown格式化工具
# ============================================================

def escape_markdown(text: str) -> str:
    """
    转义Markdown特殊字符
    
    Args:
        text: 输入文本
    
    Returns:
        转义后的文本
    """
    special_chars = r"\`*_{}[]()#+-.!|"
    for char in special_chars:
        text = text.replace(char, "\\" + char)
    return text


def create_markdown_table(
    headers: List[str],
    rows: List[List[str]],
    alignment: Optional[List[str]] = None
) -> str:
    """
    创建Markdown表格
    
    Args:
        headers: 表头列表
        rows: 数据行列表
        alignment: 对齐方式列表（left, center, right）
    
    Returns:
        Markdown表格字符串
    """
    if not headers:
        return ""
    
    # 处理对齐方式
    if alignment is None:
        alignment = ["left"] * len(headers)
    
    align_map = {
        "left": ":---",
        "center": ":---:",
        "right": "---:",
    }
    
    # 构建表格
    lines = []
    
    # 表头
    header_line = "| " + " | ".join(headers) + " |"
    lines.append(header_line)
    
    # 分隔行
    separator_cells = [align_map.get(a, "---") for a in alignment]
    separator_line = "| " + " | ".join(separator_cells) + " |"
    lines.append(separator_line)
    
    # 数据行
    for row in rows:
        # 确保行有足够的列
        padded_row = row + [""] * (len(headers) - len(row))
        row_line = "| " + " | ".join(padded_row[:len(headers)]) + " |"
        lines.append(row_line)
    
    return "\n".join(lines)


def format_metadata_as_yaml(metadata: Dict[str, Any]) -> str:
    """
    将元数据格式化为YAML格式（用于Markdown front matter）
    
    Args:
        metadata: 元数据字典
    
    Returns:
        YAML格式的字符串
    """
    lines = ["---"]
    
    for key, value in metadata.items():
        if value is None:
            continue
        
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for k, v in value.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, str):
            # 处理多行字符串
            if "\n" in value:
                lines.append(f"{key}: |")
                for line in value.split("\n"):
                    lines.append(f"  {line}")
            else:
                # 转义引号
                escaped_value = value.replace('"', '\\"')
                lines.append(f'{key}: "{escaped_value}"')
        else:
            lines.append(f"{key}: {value}")
    
    lines.append("---")
    return "\n".join(lines)


# ============================================================
# 时间测量工具
# ============================================================

import time
from contextlib import contextmanager
from typing import Generator


@contextmanager
def timer() -> Generator[Dict[str, float], None, None]:
    """
    计时器上下文管理器
    
    使用示例:
        with timer() as t:
            # 执行操作
            pass
        print(f"耗时: {t['elapsed_ms']:.2f}ms")
    
    Yields:
        包含 elapsed_ms 的字典
    """
    result: Dict[str, float] = {"elapsed_ms": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        end = time.perf_counter()
        result["elapsed_ms"] = (end - start) * 1000


def get_current_timestamp() -> str:
    """
    获取当前时间戳（ISO格式）
    
    Returns:
        ISO格式的时间戳字符串
    """
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"


# ============================================================
# 路径处理工具
# ============================================================

def make_safe_filename(filename: str, max_length: int = 255) -> str:
    """
    创建安全的文件名
    
    - 移除非法字符
    - 限制长度
    - 处理特殊名称
    
    Args:
        filename: 原始文件名
        max_length: 最大长度
    
    Returns:
        安全的文件名
    """
    # 移除非法字符
    illegal_chars = r'<>:"/\|?*'
    for char in illegal_chars:
        filename = filename.replace(char, "_")
    
    # 移除控制字符
    filename = "".join(
        char for char in filename
        if not unicodedata.category(char).startswith("C")
    )
    
    # 去除首尾空白和点
    filename = filename.strip(" .")
    
    # Windows保留名称
    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    
    name_without_ext = Path(filename).stem.upper()
    if name_without_ext in reserved_names:
        filename = "_" + filename
    
    # 限制长度
    if len(filename) > max_length:
        ext = Path(filename).suffix
        name = Path(filename).stem[:max_length - len(ext) - 1]
        filename = name + ext
    
    # 如果为空，使用默认名称
    if not filename:
        filename = "unnamed"
    
    return filename


def generate_unique_filename(
    directory: Union[str, Path],
    base_name: str,
    extension: str
) -> str:
    """
    生成唯一文件名
    
    如果文件已存在，添加数字后缀
    
    Args:
        directory: 目录路径
        base_name: 基础文件名
        extension: 扩展名（不含点）
    
    Returns:
        唯一的文件名
    """
    directory = Path(directory)
    extension = extension.lstrip(".")
    
    filename = f"{base_name}.{extension}"
    filepath = directory / filename
    
    if not filepath.exists():
        return filename
    
    counter = 1
    while True:
        filename = f"{base_name}_{counter}.{extension}"
        filepath = directory / filename
        if not filepath.exists():
            return filename
        counter += 1