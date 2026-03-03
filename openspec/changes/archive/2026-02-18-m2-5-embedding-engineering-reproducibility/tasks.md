## 1. 配置与输入预检

- [x] 1.1 在 embedding 配置中新增并校验 `max_requests_per_minute`、`max_concurrent_requests`、重试次数与超限处理策略（truncate/split）
- [x] 1.2 在 embedding 构建入口实现输入预检：`strip()` 空文本跳过、token 超限检测与策略化处理
- [x] 1.3 落盘预检统计字段：`skipped_empty`、`truncated_count`、`skipped_over_limit_count`、`skipped_empty_chunk_ids`

## 2. 失败恢复与限流控制

- [x] 2.1 实现 batch 请求失败解析（HTTP status、response body、trace_id）并写入运行日志
- [x] 2.2 实现 batch 失败后的 per-item fallback，区分可恢复/不可恢复错误并阻断无限重试
- [x] 2.3 实现 429/5xx/网络错误指数退避，记录 `rate_limited_count` 与 `backoff_total_ms`
- [x] 2.4 实现双限流调度（RPM + 并发 semaphore）并覆盖构建流程

## 3. 缓存键升级与断点续跑

- [x] 3.1 将缓存命中键升级为 `(provider, model, normalized_text_hash)`，并保持向后兼容读取
- [x] 3.2 重构构建流程为“缓存优先 + miss 补齐”，确保中断重跑仅处理剩余 miss
- [x] 3.3 在 runs 日志落盘 `embedding_cache_hits`、`embedding_cache_miss`、`embedding_api_calls`

## 4. 索引产物与可观测性增强

- [x] 4.1 扩展 `vec_index_embed.json` 头信息与 docs 元信息字段（provider/model/dim/build_time/chunk metadata）
- [x] 4.2 确保向量维度一致性校验与异常记录，不因局部失败中断整体输出
- [x] 4.3 增加构建进度输出 `Embedding progress: done/total` 与 `batch idx/total`
- [x] 4.4 增强 runs 字段：`embedding_build_time_ms`、`embedding_query_time_ms`、`embedding_failed_count`、`embedding_failed_chunk_ids`

## 5. 验收与报告

- [x] 5.1 在至少 20 篇论文数据上完成一次全量 embedding 构建并记录失败样本
- [x] 5.2 执行一次中断重跑演示并对比两次运行 cache 命中变化
- [x] 5.3 抽样 5 个失败 chunk，验证日志中失败原因可归类（空输入/超限/429/5xx 等）
- [x] 5.4 生成 `reports/m2_5_embedding_engineering.md`，包含耗时、cache hit/miss、top-3 失败原因与重跑对比
