## 新增需求

### 需求:Embedding 输入预检必须拦截空文本与超限文本
系统对每个待 embedding 的 `clean_text` 必须先执行预检：`strip()` 后为空必须跳过并累计 `skipped_empty`；超过 token 上限时必须按配置策略执行 `truncate` 或 `split`，并记录 `truncated_count`、`skipped_over_limit_count` 与 `skipped_empty_chunk_ids`（可截断存储）。

#### 场景:空文本被跳过并计数
- **当** 某个 chunk 的 `clean_text.strip()` 为空
- **那么** 系统必须跳过该 chunk，不向 embedding API 发送请求，并增加 `skipped_empty` 计数

#### 场景:超限文本按策略处理
- **当** 某个 chunk 超过模型安全 token 上限
- **那么** 系统必须按配置执行 truncate 或 split，并更新相应统计字段

## 修改需求

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

## 移除需求
