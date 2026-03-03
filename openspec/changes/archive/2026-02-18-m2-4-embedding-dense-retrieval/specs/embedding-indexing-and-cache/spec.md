## ADDED Requirements

### 需求:Embedding 索引构建必须基于 clean_text 并过滤无效 chunk
系统必须使用 `data/processed/chunks_clean.jsonl` 中 `suppressed=false` 的 chunk 构建 embedding 索引。系统必须使用 `clean_text` 作为 embedding 输入文本，且禁止对 `content_type=watermark` 的 chunk 生成 embedding。

#### 场景:按字段过滤并构建向量索引
- **当** 用户执行 embedding 索引构建流程
- **那么** 系统必须仅处理 `suppressed=false` 且 `content_type!=watermark` 的 chunk，并使用 `clean_text` 生成向量

### 需求:Embedding 配置必须完全来自配置文件
系统必须从配置文件读取 provider、base_url、model、api_key_env、batch_size、normalize、cache_enabled、cache_path 等参数，禁止硬编码 provider 或模型参数。

#### 场景:加载 embedding 配置
- **当** 系统启动索引构建或 query embedding 流程
- **那么** 系统必须从配置加载 embedding 参数并按 `api_key_env` 读取环境变量

### 需求:Embedding 批量调用必须支持重试与部分失败处理
系统必须按 `batch_size` 对文本进行批量 API 调用；单条失败时必须记录错误并最多重试 2 次；超过重试上限的条目必须保留失败记录且不得导致整批结果丢失。

#### 场景:单条请求失败重试
- **当** 批量请求中的某个 chunk embedding 失败
- **那么** 系统必须对该条目最多重试 2 次并记录失败原因

### 需求:Embedding 缓存必须按 chunk_id 与 model 复用
当 `cache_enabled=true` 时，系统必须在构建前读取缓存并按 `(chunk_id, model)` 命中；命中项禁止重复调用 API；未命中项成功后必须写入缓存文件 `embedding_cache.jsonl`。

#### 场景:二次构建命中缓存
- **当** 用户第二次执行同模型 embedding 索引构建
- **那么** 系统必须优先复用缓存并显著减少 API 调用次数

### 需求:Embedding 向量必须支持归一化并写出标准索引结构
当 `normalize=true` 时，系统必须对向量执行 L2 normalize。系统必须输出 `data/indexes/vec_index_embed.json`，且包含 `embedding_provider`、`embedding_model`、`embedding_dim` 与逐条 `docs` 向量记录。

#### 场景:输出标准向量索引
- **当** embedding 索引构建完成
- **那么** 输出文件必须包含索引头信息及每个 chunk 的向量数组，并满足统一维度
