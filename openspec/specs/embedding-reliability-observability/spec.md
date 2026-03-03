# embedding-reliability-observability 规范

## 目的
待定 - 由归档变更 m2-5-embedding-engineering-reproducibility 创建。归档后请更新目的。

## 需求
### 需求:Embedding 批量失败必须可归因并可恢复
系统在 embedding batch 请求失败时必须记录 HTTP 状态码、响应体摘要与 trace_id（若响应头包含如 `x-siliconcloud-trace-id`）。系统必须在 batch 失败后降级为 per-item 处理，并区分可恢复与不可恢复错误；对可恢复错误必须执行指数退避重试且重试次数必须可配置。

#### 场景:batch 失败后按条回退
- **当** 某个 embedding batch 返回非 200
- **那么** 系统必须先记录该 batch 的 status/body/trace_id，再对该 batch 条目执行 per-item 请求，不得直接终止整个构建

#### 场景:不可恢复错误不重试
- **当** per-item 返回空输入、超限或格式错误
- **那么** 系统必须将该条标记为 badcase 并跳过，且不得无限重试

### 需求:Embedding 请求必须支持限流与并发控制
系统必须支持 `max_requests_per_minute` 与 `max_concurrent_requests` 配置，并在请求调度中同时生效。对 429 响应系统必须执行指数退避，并记录 `rate_limited_count` 与 `backoff_total_ms`。

#### 场景:触发 429 后退避统计
- **当** provider 返回 429
- **那么** 系统必须按指数退避等待后重试，并在运行日志中累计 rate limit 次数与总退避时长

### 需求:Embedding 过程必须提供可观测进度与运行指标
系统在构建索引时必须输出 `Embedding progress: done/total` 与当前 batch 进度。系统必须在 runs 日志中记录 `embedding_build_time_ms`、`embedding_query_time_ms`、`embedding_failed_count`、`embedding_failed_chunk_ids`、`embedding_provider`、`embedding_model`、`embedding_dim`、`embedding_batch_size`、`embedding_api_calls`。

#### 场景:构建期间输出进度并落盘指标
- **当** 用户运行 embedding 索引构建
- **那么** 控制台必须持续显示 done/total 与 batch idx/total，且构建完成后 runs 日志包含上述 embedding 指标字段

### 需求:必须输出 M2.5 工程化评估报告
系统在完成 M2.5 验收运行后必须输出 `reports/m2_5_embedding_engineering.md`，并包含总耗时、每 1000 chunks 平均耗时、cache hit/miss 统计、top-3 失败原因分布与断点续跑两次运行对比。

#### 场景:生成评估报告
- **当** 完成至少一次 embedding 构建与一次中断重跑演示
- **那么** 系统必须生成并保存包含规定统计项的 M2.5 报告文件
