"""
论文资源管理系统

本系统提供以下核心功能：
1. 文档转换模块（Document Converter）：将PDF、HTML、TXT等格式转换为Markdown
2. RAG存储模块（RAG Storage）：将Markdown文档向量化并存储
3. RAG问答模块（RAG Query）：通过LLM进行智能问答

快速开始:
    from src.converter import DocumentConverterService, DocumentInput
    
    # 创建转换服务
    service = DocumentConverterService()
    
    # 转换文档
    result = service.convert_document(
        DocumentInput(file_path="paper.pdf")
    )
    
    if result.success:
        print(f"标题: {result.document.metadata.title}")
        print(f"内容: {result.document.content[:200]}...")

模块:
    - converter: 文档转换模块
    - storage: RAG存储模块 (待实现)
    - query: RAG问答模块 (待实现)
    - models: 数据模型定义
    - utils: 工具函数
    - config: 配置管理
"""

__version__ = "1.0.0"
__author__ = "Paper Management System Team"

# 导出主要模块
from src import converter
from src import models
from src import utils

__all__ = [
    "converter",
    "models", 
    "utils",
    "__version__",
]