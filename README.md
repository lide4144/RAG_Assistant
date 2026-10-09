# 论文资源管理系统 (Paper Resource Management System)

一个基于 RAG (Retrieval-Augmented Generation) 的学术论文管理和智能问答系统。

## 功能特性

- **📄 多格式文档转换**：支持 PDF、HTML、TXT 等格式转换为标准 Markdown
- **🗄️ 向量化存储**：自动分块、向量化并存储到向量数据库
- **🤖 智能问答**：基于 RAG 的智能问答，支持多种 LLM

## 系统架构

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Document       │    │   RAG Storage    │    │   RAG Query      │
│   Converter      │───▶│   Module         │───▶│   Module         │
│   Module         │    │                  │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘
      PDF/HTML/TXT           ChromaDB              LLM (OpenAI等)
```

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd RAG_System

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API 密钥
# OPENAI_API_KEY=your-api-key-here
```

### 3. 基本使用

```python
from src.converter import DocumentConverterService
from src.storage import RAGStorageService
from src.query import RAGQueryService
from src.models import DocumentInput, StorageInput, QueryInput

# 1. 转换文档
converter = DocumentConverterService()
result = converter.convert_document(
    DocumentInput(file_path="./data/input/paper.pdf")
)

if result.success:
    print(f"转换成功: {result.document.metadata.title}")
    
    # 2. 存储到 RAG
    storage = RAGStorageService()
    storage_result = storage.store_documents(
        StorageInput(documents=[result.document])
    )
    print(f"存储成功: {storage_result.total_chunks} 个文本块")
    
    # 3. 问答
    query = RAGQueryService()
    response = query.query(
        QueryInput(query="这篇论文的主要贡献是什么？")
    )
    print(f"回答: {response.answer}")
```

## 项目结构

```
RAG_System/
├── docs/                          # 文档目录
│   ├── ARCHITECTURE.md            # 架构设计文档
│   └── API_SPECIFICATION.md       # API接口规范
├── src/                           # 源代码目录
│   ├── converter/                 # 文档转换模块
│   ├── storage/                   # RAG存储模块
│   ├── query/                     # RAG问答模块
│   ├── models/                    # 数据模型定义
│   ├── config/                    # 配置管理
│   └── utils/                     # 工具函数
├── config/                        # 配置文件目录
│   └── config.yaml               # 主配置文件
├── data/                          # 数据目录
│   ├── input/                    # 输入文件目录
│   ├── output/                   # 输出文件目录
│   └── vectordb/                 # 向量数据库存储
├── tests/                         # 测试目录
├── requirements.txt              # Python依赖
├── .env.example                  # 环境变量模板
└── README.md                     # 项目说明
```

## 配置说明

### 配置文件

主配置文件位于 `config/config.yaml`，包含以下主要配置项：

- **system**: 系统基础配置（日志、工作目录等）
- **converter**: 文档转换模块配置
- **storage**: RAG存储模块配置（向量数据库、分块、嵌入模型）
- **query**: RAG问答模块配置（检索、LLM）

### 支持的 LLM

| 提供商 | 模型 | 配置方式 |
|--------|------|----------|
| OpenAI | gpt-3.5-turbo, gpt-4 等 | API Key |
| Anthropic | claude-3 等 | API Key |
| 阿里云 | qwen-turbo, qwen-plus 等 | DashScope API Key |
| 智谱AI | glm-4, glm-3-turbo | API Key |
| 本地部署 | Ollama, vLLM 等 | OpenAI 兼容接口 |

### 支持的向量数据库

| 数据库 | 说明 |
|--------|------|
| ChromaDB | 默认，轻量级，无需额外部署 |
| Milvus | 高性能，适合大规模数据 |
| Pinecone | 云服务，托管方案 |
| Qdrant | 高性能，Rust实现 |

## 文档

- [架构设计文档](docs/ARCHITECTURE.md) - 系统架构和设计决策
- [API接口规范](docs/API_SPECIFICATION.md) - 详细的接口定义和数据结构

## 数据结构

### 核心数据流

```
DocumentInput          MarkdownDocument         DocumentChunk[]
    │                        │                        │
    ▼                        ▼                        ▼
┌─────────┐            ┌─────────────┐          ┌──────────────┐
│file_path│  ──转换──▶ │content (MD) │ ──分块──▶│chunk_id      │
│file_type│            │metadata     │  向量化  │content       │
│metadata │            │source_info  │          │embedding     │
└─────────┘            └─────────────┘          └──────────────┘
                                                       │
                                                       ▼
QueryInput                                      QueryResponse
    │                                                 │
    ▼                                                 ▼
┌─────────┐         ┌──────────────┐           ┌───────────┐
│query    │ ──检索──▶│RetrievedChunk│ ──LLM──▶ │answer     │
│llm_config│         │similarity    │          │sources    │
└─────────┘          └──────────────┘          │confidence │
                                               └───────────┘
```

## 开发

### 运行测试

```bash
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=src --cov-report=html
```

### 代码格式化

```bash
# 格式化代码
black src tests

# 排序导入
isort src tests

# 类型检查
mypy src
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！