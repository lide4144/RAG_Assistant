# 论文资源管理系统 - 架构设计文档

## 1. 系统概述

本系统是一个论文资源管理系统，提供以下核心功能：
1. **文档转换模块（Document Converter）**：将PDF、HTML、TXT等格式的论文转换为标准Markdown格式
2. **RAG存储模块（RAG Storage）**：将Markdown格式论文进行向量化并存储到向量数据库
3. **RAG问答模块（RAG Query）**：通过可配置的LLM API进行智能问答

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          论文资源管理系统                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │   Document       │    │   RAG Storage    │    │   RAG Query      │      │
│  │   Converter      │───▶│   Module         │───▶│   Module         │      │
│  │   Module         │    │                  │    │                  │      │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘      │
│         ▲                        ▲                        ▲                │
│         │                        │                        │                │
│  ┌──────┴──────┐          ┌──────┴──────┐          ┌──────┴──────┐        │
│  │ PDF/HTML/   │          │ Vector DB   │          │ LLM API     │        │
│  │ TXT Files   │          │ (ChromaDB)  │          │ Config      │        │
│  └─────────────┘          └─────────────┘          └─────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 3. 模块间数据流

```
输入文件 (PDF/HTML/TXT)
        │
        ▼
┌───────────────────────┐
│  DocumentInput        │
│  - file_path: str     │
│  - file_type: enum    │
│  - metadata: dict     │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  Document Converter   │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  MarkdownDocument     │
│  - content: str       │
│  - metadata: dict     │
│  - source_info: dict  │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  RAG Storage Module   │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  DocumentChunk[]      │
│  - chunk_id: str      │
│  - content: str       │
│  - embedding: vector  │
│  - metadata: dict     │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  RAG Query Module     │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  QueryResponse        │
│  - answer: str        │
│  - sources: list      │
│  - confidence: float  │
└───────────────────────┘
```

## 4. 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| 编程语言 | Python 3.10+ | 主要开发语言 |
| PDF解析 | PyMuPDF (fitz) | 高性能PDF解析库 |
| HTML解析 | BeautifulSoup4 | HTML内容提取 |
| Markdown处理 | markdownify | HTML转Markdown |
| 向量数据库 | ChromaDB | 轻量级向量存储 |
| 向量化模型 | sentence-transformers | 文本向量化 |
| LLM接口 | OpenAI API兼容 | 支持多种LLM |
| 配置管理 | Pydantic | 类型安全的配置 |

## 5. 目录结构

```
RAG_System/
├── docs/                          # 文档目录
│   ├── ARCHITECTURE.md            # 架构设计文档
│   └── API_SPECIFICATION.md       # API接口规范
├── src/                           # 源代码目录
│   ├── __init__.py
│   ├── converter/                 # 文档转换模块
│   │   ├── __init__.py
│   │   ├── base.py               # 基础转换器接口
│   │   ├── pdf_converter.py      # PDF转换器
│   │   ├── html_converter.py     # HTML转换器
│   │   └── txt_converter.py      # TXT转换器
│   ├── storage/                   # RAG存储模块
│   │   ├── __init__.py
│   │   ├── chunker.py            # 文档分块器
│   │   ├── embedder.py           # 向量化器
│   │   └── vector_store.py       # 向量存储
│   ├── query/                     # RAG问答模块
│   │   ├── __init__.py
│   │   ├── retriever.py          # 检索器
│   │   ├── llm_client.py         # LLM客户端
│   │   └── qa_engine.py          # 问答引擎
│   ├── models/                    # 数据模型定义
│   │   ├── __init__.py
│   │   └── schemas.py            # Pydantic模型
│   ├── config/                    # 配置管理
│   │   ├── __init__.py
│   │   └── settings.py           # 配置类
│   └── utils/                     # 工具函数
│       ├── __init__.py
│       └── helpers.py            # 辅助函数
├── config/                        # 配置文件目录
│   └── config.yaml               # 主配置文件
├── tests/                         # 测试目录
│   ├── __init__.py
│   ├── test_converter.py
│   ├── test_storage.py
│   └── test_query.py
├── data/                          # 数据目录
│   ├── input/                    # 输入文件目录
│   ├── output/                   # 输出文件目录
│   └── vectordb/                 # 向量数据库存储
├── requirements.txt              # Python依赖
├── setup.py                      # 安装脚本
└── README.md                     # 项目说明
```

## 6. 下一步

详细的接口规范请参阅 [API_SPECIFICATION.md](./API_SPECIFICATION.md)