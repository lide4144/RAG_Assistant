# embedding-indexing-and-cache 规范

## 目的
待定 - 由归档变更 m2-4-embedding-dense-retrieval 创建。归档后请更新目的。
## 需求
### 需求:Embedding 索引构建必须基于 clean_text 并过滤无效 chunk
系统必须使用 `data/processed/chunks_clean.jsonl` 中 `suppressed=false` 的 chunk 构建 embedding 索引。系统必须使用 `clean_text` 作为 embedding 输入文本，且禁止对 `content_type=watermark` 的 chunk 生成 embedding。

#### 场景:按字段过滤并构建向量索引
- **当** 用户执行 embedding 索引构建流程
- **那么** 系统必须仅处理 `suppressed=false` 且 `content_type!=watermark` 的 chunk，并使用 `clean_text` 生成向量

### 需求:Embedding 配置必须完全来自配置文件
系统必须从配置或运行时配置读取 embedding 路由参数（provider、base_url、model、api_key_env、batch_size、normalize、cache_enabled、cache_path），并通过统一 stage 路由解析后生效。系统禁止在 embedding 路径硬编码固定 provider 或固定环境变量名。

#### 场景:加载 stage=embedding 路由配置
- **当** 系统启动 query embedding 或索引构建流程
- **那么** 系统必须按 stage 路由加载并解析 embedding 配置，且不得强依赖 `SILICONFLOW_API_KEY`

### 需求:Embedding 批量调用必须支持重试与部分失败处理
系统必须按 `batch_size` 对文本进行批量 API 调用；单条失败时必须记录错误并最多重试 2 次；超过重试上限的条目必须保留失败记录且不得导致整批结果丢失。

#### 场景:单条请求失败重试
- **当** 批量请求中的某个 chunk embedding 失败
- **那么** 系统必须对该条目最多重试 2 次并记录失败原因

### 需求:Embedding 输入预检必须拦截空文本与超限文本
系统对每个待 embedding 的 `clean_text` 必须先执行预检：`strip()` 后为空必须跳过并累计 `skipped_empty`；超过 token 上限时必须按配置策略执行 `truncate` 或 `split`，并记录 `truncated_count`、`skipped_over_limit_count` 与 `skipped_empty_chunk_ids`（可截断存储）。

#### 场景:空文本被跳过并计数
- **当** 某个 chunk 的 `clean_text.strip()` 为空
- **那么** 系统必须跳过该 chunk，不向 embedding API 发送请求，并增加 `skipped_empty` 计数

#### 场景:超限文本按策略处理
- **当** 某个 chunk 超过模型安全 token 上限
- **那么** 系统必须按配置执行 truncate 或 split，并更新相应统计字段

### 需求:Embedding 缓存必须按 provider/model/text-hash 复用并支持断点续跑
当 `cache_enabled=true` 时，系统必须在构建前加载缓存并按 `(provider, model, normalized_text_hash)` 命中；命中项禁止重复请求 API；未命中项成功后必须写入 `embedding_cache.jsonl`（或等价后端）。系统中断后再次运行时必须从剩余未命中条目继续处理。

#### 场景:二次构建从缓存恢复
- **当** 首次构建中途失败或被中断后再次运行同配置同语料
- **那么** 系统必须优先命中已缓存条目，仅对剩余 miss 条目调用 API，且 runs 日志记录 `embedding_cache_hits`、`embedding_cache_miss`

### 需求:Embedding 向量输出必须包含可复现元信息
系统必须输出 `data/indexes/vec_index_embed.json`（或分片）且包含 `docs` 元信息（chunk_id/paper_id/page/section/content_type）与向量数组。索引头必须记录 `embedding_provider`、`embedding_model`、`embedding_dim`、`build_time`，并保证同配置同语料重复运行时维度与模型信息一致。

#### 场景:索引头携带模型与维度信息
- **当** embedding 索引构建完成
- **那么** 输出索引必须包含 provider/model/dim/build_time 与逐条 docs 元信息，且所有向量维度一致

### 需求:Embedding 回退模型必须满足维度一致性守卫
系统在 embedding 主备模型切换时必须校验向量维度与目标索引维度一致。若维度不一致，系统必须禁止进入向量检索分支并触发词频检索降级。

#### 场景:主备维度不一致触发降级
- **当** embedding 备用模型输出维度与主索引维度不一致
- **那么** 系统必须跳过向量检索并降级到 TF-IDF/BM25，且记录 `dimension_mismatch` 诊断

### 需求:Embedding API 失败后必须支持词频静默降级
当 embedding API 在重试后仍失败时，系统必须优先静默降级到词频检索；仅在运行上下文明确禁止降级时才允许抛出可识别的不可恢复异常。

#### 场景:重试耗尽后降级词频检索
- **当** embedding API 发生超时或 5xx 且达到最大重试次数
- **那么** 系统必须自动切换到 TF-IDF/BM25 检索并保持请求链路可继续执行

