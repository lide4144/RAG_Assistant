# RAG存储模块演示

本演示展示如何使用RAG存储模块对Markdown文档进行分块、向量化和语义搜索。

## 目录结构

```
storage_demo/
├── inputs/          # 输入的Markdown文件目录
├── outputs/         # 搜索结果输出目录
├── run_storage_demo.py  # 演示脚本
└── README.md        # 本文件
```

## 功能特性

1. **自动文档发现**：从`inputs/`目录读取所有Markdown文件
2. **智能分块**：支持段落、句子、token三种分块策略，防止数据丢失
3. **文本向量化**：使用sentence-transformers模型生成384维向量
4. **向量存储**：使用ChromaDB存储和管理文档向量
5. **语义搜索**：基于向量相似度的语义搜索
6. **结果保存**：搜索结果自动保存到`outputs/`目录

## 使用方法

### 1. 安装依赖

```bash
pip install chromadb sentence-transformers
```

### 2. 准备输入文件

将Markdown文件放入`inputs/`目录：

```bash
# 方式1: 手动复制
cp your_document.md src/demo/storage_demo/inputs/

# 方式2: 使用转换模块的输出
cp src/demo/converter_demo/outputs/*.md src/demo/storage_demo/inputs/
```

如果`inputs/`目录为空，演示程序会自动创建一个示例文档。

### 3. 运行演示

```bash
python -m src.demo.storage_demo.run_storage_demo
```

### 4. 查看输出

搜索结果保存在`outputs/`目录：
- `search_results_1.txt` - 第一个查询的结果
- `search_results_2.txt` - 第二个查询的结果
- `search_results_3.txt` - 第三个查询的结果

## 演示流程

演示程序会自动执行以下6个步骤：

### 步骤1: 查找Markdown文档
- 扫描`inputs/`目录
- 列出所有找到的`.md`文件
- 如果没有文件，创建示例文档

### 步骤2: 读取并解析文档
- 读取每个Markdown文件
- 创建`MarkdownDocument`对象
- 提取文档标题和元数据

### 步骤3: 初始化RAG存储服务
- 配置分块参数（512字符，50字符重叠）
- 下载向量化模型（首次运行约90MB）
- 创建ChromaDB数据库

### 步骤4: 存储文档
- 文档分块（智能段落切分）
- 文本向量化（384维向量）
- 存储到向量数据库

### 步骤5: 语义搜索演示
- 执行3个示例查询
- 每个查询返回Top-3最相关的文本块
- 显示相似度分数和内容预览
- 保存搜索结果到`outputs/`

### 步骤6: 显示统计信息
- 总文档数
- 总文本块数
- 向量数据库大小

## 配置说明

可以在`run_storage_demo.py`中修改配置参数：

```python
config = StorageServiceConfig(
    # 分块配置
    chunk_size=512,              # 每块的最大字符数
    chunk_overlap=50,            # 块之间的重叠字符数
    split_by="paragraph",        # 分块方式: paragraph/sentence/token
    respect_sections=True,       # 是否尊重章节边界
    min_chunk_size=0,            # 最小块大小（0=保留所有）
    merge_small_chunks=True,     # 是否合并小块
    
    # 向量化配置
    embedding_provider="sentence-transformers",
    embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
    
    # 存储配置
    vector_db_type="chroma",
    persist_directory=persist_dir,
    default_collection="demo_papers",
)
```

## 数据丢失防止

本演示使用以下策略防止短章节（如FAQ、摘要）被丢弃：

- `min_chunk_size=0`：保留所有内容，不设最小大小限制
- `merge_small_chunks=True`：将太小的块与前一块合并

详见：[docs/DATA_LOSS_PREVENTION.md](../../../docs/DATA_LOSS_PREVENTION.md)

## 向量化模型

默认使用`paraphrase-multilingual-MiniLM-L12-v2`模型：
- **维度**：384维
- **大小**：约90MB
- **语言**：支持50+语言（包括中文、英文）
- **速度**：快速（CPU可运行）
- **质量**：适合通用语义搜索

其他可选模型：
- `all-MiniLM-L6-v2`：更快，仅英文（384维）
- `all-mpnet-base-v2`：更准确，仅英文（768维）
- `paraphrase-multilingual-mpnet-base-v2`：最准确，多语言（768维）

## 故障排除

### 问题1: 找不到Markdown文件
**症状**：`未在 inputs 中找到Markdown文件`

**解决**：
```bash
# 检查目录是否存在
ls src/demo/storage_demo/inputs/

# 复制文件
cp your_file.md src/demo/storage_demo/inputs/
```

### 问题2: 模型下载失败
**症状**：`网络问题导致模型下载失败`

**解决**：
1. 检查网络连接
2. 配置代理（如需要）
3. 手动下载模型到缓存目录

### 问题3: 内存不足
**症状**：`MemoryError` 或程序崩溃

**解决**：
- 减小`chunk_size`（如改为256）
- 减小`embedding_batch_size`（如改为16）
- 使用更小的模型

### 问题4: 依赖包未安装
**症状**：`ModuleNotFoundError: No module named 'chromadb'`

**解决**：
```bash
pip install chromadb sentence-transformers
```

## API集成示例

演示程序展示的完整流程可以用于您自己的项目：

```python
from src.storage import RAGStorageService, StorageServiceConfig
from src.models.schemas import StorageInput, MarkdownDocument

# 1. 创建服务
config = StorageServiceConfig(
    chunk_size=512,
    embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
    persist_directory="./my_vectordb"
)
service = RAGStorageService(config)

# 2. 存储文档
result = service.store_documents(
    StorageInput(documents=[your_markdown_doc])
)

# 3. 搜索
chunks = service.search("你的查询", top_k=5)
for chunk in chunks:
    print(f"相似度: {chunk.similarity_score:.3f}")
    print(chunk.content)
```

## 性能优化

- **批量处理**：一次传入多个文档比逐个处理更快
- **持久化存储**：设置固定的`persist_directory`避免重复向量化
- **GPU加速**：设置`embedding_device="cuda"`使用GPU
- **并行处理**：增大`embedding_batch_size`提高吞吐量

## 相关文档

- [存储模块文档](../../../docs/STORAGE_MODULE.md)
- [数据丢失防止指南](../../../docs/DATA_LOSS_PREVENTION.md)
- [API规范](../../../docs/API_SPECIFICATION.md)
- [架构文档](../../../docs/ARCHITECTURE.md)

## 下一步

运行演示后，您可以：

1. **实验不同配置**：修改chunk_size、split_by等参数
2. **使用真实文档**：将您的Markdown文件放入inputs/
3. **集成到项目**：参考演示代码集成到您的应用
4. **探索高级功能**：查看[存储模块文档](../../../docs/STORAGE_MODULE.md)