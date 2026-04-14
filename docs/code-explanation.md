# RAG_GPT app 目录代码说明文档

> 本文档用于毕业设计中期答辩时解释代码使用

## 📁 目录结构概览

```
app/
├── 核心入口与 API
│   ├── kernel_api.py          # FastAPI 主入口，所有 HTTP/WebSocket 接口
│   ├── qa.py                  # 问答主流程，RAG 链路 orchestration
│   └── generate.py            # 答案生成器
│
├── 数据入库与处理
│   ├── ingest.py              # 论文入库主流程
│   ├── parser.py              # PDF/文本解析器
│   ├── marker_parser.py       # Marker PDF 结构化解析
│   ├── chunker.py             # 文本分块器
│   ├── clean_chunks.py        # Chunk 清洗（去水印等）
│   └── web_ingest.py          # 网页内容抓取
│
├── 索引与检索
│   ├── index_vec.py           # 向量索引（TF-IDF/Embedding）
│   ├── index_bm25.py          # BM25 索引
│   ├── retrieve.py            # 检索主流程
│   ├── graph_build.py         # 图构建与扩展
│   └── rerank.py              # 重排序（精排）
│
├── 查询理解与改写
│   ├── rewrite.py             # 查询改写（指代消解、关键词扩展）
│   ├── intent_calibration.py  # 意图校准
│   └── document_structure.py  # 文档结构解析
│
├── Agent 与规划
│   ├── capability_planner.py  # 能力规划器（Agent 大脑）
│   ├── planner_runtime.py     # Planner 运行时
│   ├── planner_policy.py      # 决策策略
│   └── agent_tools.py         # Agent 工具注册
│
├── LLM 客户端与路由
│   ├── llm_client.py          # LLM 调用客户端
│   ├── llm_routing.py         # 多模型路由与降级
│   ├── embedding_api.py       # Embedding API 封装
│   └── vector_backend.py      # 向量后端抽象
│
├── 存储与数据管理
│   ├── paper_store.py         # 论文存储（数据库操作）
│   ├── library.py             # 论文库管理
│   ├── paper_summary.py       # 论文摘要管理
│   ├── session_state.py       # 会话状态管理
│   └── job_store.py           # 任务存储
│
├── 配置与治理
│   ├── config.py              # 配置加载与验证
│   ├── config_governance.py   # 配置治理
│   ├── pipeline_runtime_config.py  # Pipeline 运行时配置
│   ├── planner_runtime_config.py   # Planner 运行时配置
│   └── admin_llm_config.py    # LLM 配置管理
│
├── 可观测性与日志
│   ├── llm_observability.py   # LLM 观测性
│   ├── llm_diagnostics.py     # LLM 诊断
│   ├── llm_log_config.py      # LLM 日志配置
│   ├── runlog.py              # 运行日志
│   └── sufficiency.py         # 证据充分性判断
│
└── 工具与辅助
    ├── models.py              # 数据模型定义
│   ├── paths.py               # 路径管理
│   ├── fs_utils.py            # 文件系统工具
│   └── writer.py              # 文件写入工具
```

---

## 🔵 核心入口与 API 模块

### kernel_api.py
**作用**：FastAPI 主入口，提供所有 HTTP API 和 WebSocket 接口

**核心功能**：
- 提供 `/chat` 问答接口（流式 SSE）
- 提供 `/papers` 论文管理接口（增删改查）
- 提供 `/pipeline` Pipeline 执行接口
- 提供 `/health` 健康检查接口
- 提供 `/config` 运行时配置接口
- WebSocket 支持（通过 Gateway 转发）

**关键类/函数**：
```python
app = FastAPI(title="RAG GPT Kernel API")  # FastAPI 应用实例

# 主要端点
@app.post("/chat")           # 聊天问答
@app.get("/papers")          # 获取论文列表
@app.post("/papers")         # 上传论文
@app.delete("/papers/{id}")  # 删除论文
@app.post("/pipeline/run")   # 执行 pipeline
@app.get("/health")          # 健康检查
```

**答辩讲解要点**：
> "这是系统的核心 API 层，所有前端请求都通过这里进入。采用 FastAPI 框架，支持异步处理，提供标准的 RESTful API 和流式 SSE 输出。"

---

### qa.py
**作用**：问答主流程， orchestrates 整个 RAG 链路

**核心流程**：
```
用户问题 → Query Rewriting → 检索 → Rerank → Evidence Judgment → 答案生成
```

**关键函数**：
```python
def run_qa(query: str, session_id: str | None = None, ...) -> dict:
    """
    执行问答流程
    1. 加载会话状态
    2. 查询改写（指代消解）
    3. 多层检索（摘要层 → Chunk层 → 图扩展）
    4. 重排序
    5. 证据判断
    6. 生成答案
    7. 保存会话状态
    """

def run_sufficiency_gate(...) -> dict:
    """证据充分性判断门控"""
```

**答辩讲解要点**：
> "这是 RAG 的核心流程。用户提问后，系统首先进行查询改写解决指代问题，然后执行三层检索（摘要层粗召回、章节层结构检索、Chunk层精检索），接着进行重排序和证据判断，最后生成带引用的答案。"

---

### generate.py
**作用**：答案生成器

**核心功能**：
- 构建 Prompt 模板
- 调用 LLM 生成答案
- 处理流式输出

---

## 🟢 数据入库与处理模块

### ingest.py
**作用**：论文入库主流程，处理 PDF → Chunks → 索引的完整流程

**核心流程**：
```python
def run_ingest(paper_dir: Path) -> dict:
    """
    论文入库流程：
    1. 扫描目录，发现新论文
    2. 解析 PDF（使用 Marker 或规则解析）
    3. 文本分块（Chunking）
    4. Chunk 清洗（去水印、去噪声）
    5. 构建索引（BM25 + 向量）
    6. 保存到存储
    7. 更新论文库状态
    """
```

**答辩讲解要点**：
> "这是论文入库的核心流程。系统支持 PDF 解析，使用 Marker 进行结构化解析，然后进行智能分块和清洗，最后构建 BM25 和向量双索引。"

---

### parser.py
**作用**：通用文档解析器

**核心功能**：
- PDF 文本提取
- 标题提取
- 论文 ID 生成（基于内容哈希）

---

### marker_parser.py
**作用**：Marker 结构化 PDF 解析器

**核心功能**：
- 调用 Marker 工具进行高质量 PDF 解析
- 提取结构化内容（标题、段落、表格、公式）
- 保留文档结构信息

**答辩讲解要点**：
> "Marker 是一个专门用于学术论文的 PDF 解析工具，能够识别文档结构，比传统 OCR 效果更好。"

---

### chunker.py
**作用**：文本分块器

**核心算法**：
```python
def build_chunks(pages: list[PageText], paper_id: str) -> list[ChunkRecord]:
    """
    文本分块策略：
    1. 按章节标题分割
    2. 控制每个 chunk 的 token 数（默认 512）
    3. 保留章节层级信息
    4. 区分内容类型（正文、表格、公式）
    """
```

**答辩讲解要点**：
> "分块是 RAG 的关键。我们采用章节感知分块，既保证语义完整性，又控制 chunk 大小，方便后续检索和嵌入。"

---

### clean_chunks.py
**作用**：Chunk 清洗

**核心功能**：
- 去除水印文本
- 去除页眉页脚
- 去除噪声字符
- 标记内容类型

---

## 🟡 索引与检索模块

### index_vec.py
**作用**：向量索引（支持 TF-IDF 和 Embedding 两种模式）

**核心功能**：
```python
@dataclass
class VecIndex:
    docs: list[VecDoc]              # 文档集合
    embeddings: list[list[float]]   # 向量表示
    index_type: str                 # "tfidf" 或 "embedding"
    embedding_model: str            # 使用的模型

def build_vec_index(chunks: list, use_embedding: bool = True) -> VecIndex:
    """构建向量索引"""

def search_vec(index: VecIndex, query: str, top_k: int = 10) -> list[VecDoc]:
    """向量检索"""
```

**答辩讲解要点**：
> "向量索引支持两种后端：TF-IDF（轻量、本地）和 Embedding（语义、需 API）。系统默认使用 Embedding，当 API 不可用时自动降级到 TF-IDF。"

---

### index_bm25.py
**作用**：BM25 索引（基于词频的传统检索）

**核心功能**：
```python
def build_bm25_index(chunks: list) -> BM25Index:
    """构建 BM25 索引"""

def search_bm25(index: BM25Index, query: str, top_k: int = 10) -> list[BM25Doc]:
    """BM25 检索，基于词频和逆文档频率"""
```

**答辩讲解要点**：
> "BM25 是经典的关键词检索算法，对精确匹配效果好。我们同时使用 BM25 和向量检索，然后融合结果。"

---

### retrieve.py
**作用**：检索主流程， orchestrates 多层检索

**核心流程**：
```python
def retrieve_candidates(query: str, config: PipelineConfig) -> list[RetrievalCandidate]:
    """
    多层检索流程：
    1. 摘要层检索（粗召回候选文档）
    2. 结构层检索（章节感知）
    3. Chunk 层检索（精检索）
    4. 图扩展（Graph Expansion）
    5. 候选合并与去重
    """
```

**答辩讲解要点**：
> "检索采用三层架构：先通过摘要层粗召回候选文档，然后针对结构类问题进行章节检索，最后在候选范围内进行 chunk 精检索，并执行图扩展召回相关上下文。"

---

### graph_build.py
**作用**：图构建与图扩展召回

**核心概念**：
- **节点**：Chunk
- **边类型**：
  - `adjacent`：相邻 chunk（上下文连续性）
  - `entity`：共享实体（语义关联性）

**核心功能**：
```python
def run_graph_build(chunks: list) -> ChunkGraph:
    """
    构建 Chunk 关系图：
    1. 相邻边：连续 chunk 建立邻接关系
    2. 实体边：使用 LLM 提取实体，共享实体的 chunk 建立连接
    """

def expand_candidates_with_graph(
    seed_candidates: list,
    graph: ChunkGraph,
    alpha: float = 0.3
) -> list[RetrievalCandidate]:
    """
    图扩展召回：
    1. 对 top-k seed 候选执行 1-hop 邻居查询
    2. 支持 adjacent 和 entity 两种扩展类型
    3. 过滤噪声类型（watermark、front_matter）
    4. 分数继承与衰减
    """
```

**答辩讲解要点**：
> "GraphRAG 是我们的技术创新点。通过构建 chunk 之间的关系图，可以召回语义相关但向量距离较远的上下文。比如两个 chunk 讨论同一个实验方法，但用词不同，通过实体边可以连接起来。"

---

### rerank.py
**作用**：重排序（精排）

**核心功能**：
```python
def rerank_candidates(
    query: str,
    candidates: list[RetrievalCandidate],
    config: PipelineConfig
) -> RerankOutcome:
    """
    重排序流程：
    1. 使用交叉编码器（Cross-Encoder）计算 query-chunk 相关性
    2. 融合初检分数和重排分数
    3. 返回精排后的 top-n 候选
    """
```

**答辩讲解要点**：
> "初检（BM25/向量）速度快但精度有限。重排序使用交叉编码器进行精排，虽然计算量大但相关性判断更准确。"

---

## 🟠 查询理解与改写模块

### rewrite.py
**作用**：查询改写，解决指代消解和关键词扩展

**核心功能**：
```python
def rewrite_query(
    query: str,
    history: list[dict],
    config: PipelineConfig
) -> RewriteResult:
    """
    查询改写流程：
    1. 指代消解：将"它"、"这篇文章"解析为具体实体
    2. 关键词扩展：基于同义词词典扩展
    3. 问句转检索句：去除冗余礼貌用语
    4. 元问题处理：识别"为什么没证据"等追问
    """
```

**关键技术点**：
- **指代消解**：利用会话历史中的实体信息
- **关键词扩展**：中英文同义词词典
- **元问题护栏**：识别用户对系统状态的追问

**答辩讲解要点**：
> "查询改写是 RAG 的关键预处理。比如用户问'它的参数量是多少'，系统需要从上下文中识别'它'指的是 BERT，然后改写成'BERT 模型的参数量是多少'，这样才能检索到相关结果。"

---

### intent_calibration.py
**作用**：意图校准

**核心功能**：
- 识别查询意图类型（事实查询、总结、比较等）
- 校准检索策略
- 处理澄清需求

---

### document_structure.py
**作用**：文档结构解析与结构感知检索

**核心功能**：
- 解析论文章节结构
- 支持结构类问题（如"第三章讲了什么"）
- 章节树索引

---

## 🔴 Agent 与规划模块

### capability_planner.py
**作用**：能力规划器（Agent 的大脑）

**核心功能**：
```python
class PlannerResult:
    decision_result: str          # 决策结果：answer/clarify/delegate
    selected_tools: list[str]     # 选中的工具
    research_mode: bool           # 是否进入研究辅助模式
    clarify_questions: list[str]  # 澄清问题

def parse_planner_result(llm_output: str) -> PlannerResult:
    """
    解析 Planner LLM 的决策输出
    """
```

**支持的决策类型**：
- `answer`：直接回答
- `clarify`：需要澄清
- `delegate_research_assistant`：委托给论文助理
- `delegate_web_search`：委托给网页搜索

**答辩讲解要点**：
> "这是 Agent 架构的核心。Planner 负责决策用户请求的处理方式：直接回答、先澄清、还是调用特定工具（论文助理、网页搜索）。"

---

### planner_runtime.py
**作用**：Planner 运行时

**核心功能**：
- 执行 Planner 决策
- 调用 Agent 工具
- 管理工具注册表
- 处理工具执行结果

---

### planner_policy.py
**作用**：决策策略

**核心功能**：
- 定义何时澄清、何时回答
- 连续澄清上限控制（默认 2 次）
- 证据不足时的处理策略

---

### agent_tools.py
**作用**：Agent 工具注册与管理

**核心工具**：
- `paper_assistant`：论文助理（研究辅助）
- `web_search`：网页搜索
- `catalog_lookup`：目录查询

---

## 🟣 LLM 客户端与路由模块

### llm_client.py
**作用**：LLM 调用统一客户端

**核心功能**：
```python
def call_chat_completion(
    messages: list[dict],
    model: str,
    api_base: str,
    api_key: str,
    **kwargs
) -> dict:
    """调用 LLM 聊天接口"""

def call_chat_completion_stream(...) -> Iterator[str]:
    """流式调用 LLM"""
```

**支持的 Provider**：
- OpenAI
- Azure OpenAI
- Anthropic (Claude)
- Ollama（本地模型）
- OpenRouter 等

---

### llm_routing.py
**作用**：LLM 多模型路由与降级策略

**核心功能**：
```python
def build_stage_policy(config: PipelineConfig, stage: str) -> StagePolicy:
    """
    构建阶段策略：
    - 主模型（primary）
    - 降级模型（fallback）
    - 失败冷却机制
    """

def register_route_failure(stage: str, provider: str, error: Exception):
    """记录路由失败，触发冷却"""

def register_route_success(stage: str, provider: str):
    """记录路由成功，重置冷却"""
```

**答辩讲解要点**：
> "系统支持多模型路由和自动降级。比如 GPT-4 不可用时自动降级到 GPT-3.5，或者切换到本地 Ollama 模型。"

---

### embedding_api.py
**作用**：Embedding API 封装

**核心功能**：
- 调用 Embedding 服务
- 批量编码优化
- 缓存机制

---

## ⚪ 存储与数据管理模块

### paper_store.py
**作用**：论文存储（SQLite 数据库操作）

**核心功能**：
- 论文元数据 CRUD
- Chunk 存储
- 索引状态管理
- 论文生命周期管理

---

### library.py
**作用**：论文库管理

**核心功能**：
- 论文导入工作流
- 批量操作
- 论文状态追踪

---

### session_state.py
**作用**：会话状态管理

**核心功能**：
- 多轮对话状态保存
- 历史记录管理
- 主题追踪
- 澄清状态管理

---

### job_store.py
**作用**：任务存储

**核心功能**：
- Pipeline 任务记录
- 任务事件追踪
- 配置快照保存

---

## ⚫ 配置与治理模块

### config.py
**作用**：配置加载与验证

**核心功能**：
- YAML 配置加载
- 配置验证（Pydantic）
- 默认配置管理

---

### config_governance.py
**作用**：配置治理

**核心功能**：
- 运行时配置解析
- 配置优先级管理
- 敏感信息脱敏

---

## 🔘 可观测性与日志模块

### llm_observability.py
**作用**：LLM 观测性

**核心功能**：
- LLM 调用事件记录
- Token 使用量统计
- 延迟指标收集

---

### runlog.py
**作用**：运行日志

**核心功能**：
- 运行目录创建
- JSON 日志保存
- Trace 验证

---

### sufficiency.py
**作用**：证据充分性判断

**核心功能**：
- 判断检索证据是否足够回答问题
- 识别证据缺口
- 触发补充检索

---

## 🛠️ 工具与辅助模块

### models.py
**作用**：数据模型定义

**核心类**：
```python
@dataclass
class PaperRecord:
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    ...

@dataclass
class ChunkRecord:
    chunk_id: str
    paper_id: str
    text: str
    page_start: int
    section: str
    content_type: str
    ...
```

---

## 📌 答辩代码讲解建议

### 讲解顺序建议：

1. **整体架构**（kernel_api.py）
   - "这是系统入口，FastAPI 提供 RESTful 接口"

2. **核心流程**（qa.py）
   - "这是 RAG 主流程，从用户问题到答案生成"

3. **数据处理**（ingest.py + chunker.py）
   - "这是论文入库流程，从 PDF 到结构化 Chunks"

4. **检索技术**（retrieve.py + graph_build.py）
   - "这是三层检索 + GraphRAG 扩展"

5. **智能改写**（rewrite.py）
   - "这是查询改写，解决指代消解"

6. **Agent 架构**（capability_planner.py）
   - "这是 Agent 决策，规划如何处理用户请求"

7. **鲁棒性设计**（llm_routing.py）
   - "这是多模型路由和自动降级"

### 重点强调的技术亮点：

1. **GraphRAG**：图扩展召回相关上下文
2. **多层检索**：摘要层 → 章节层 → Chunk层
3. **Agent-First 架构**：Planner 统一决策
4. **Query Rewriting**：指代消解和关键词扩展
5. **多模型路由**：自动降级保证可用性
6. **OpenSpec 规范**：70+ 功能规范驱动开发

---

*文档生成时间：2025年*
*适用于：毕业设计中期答辩*
