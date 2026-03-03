## 为什么

当前 embedding 流程已能完成基础向量构建，但在大规模数据（20-30 篇论文）下仍缺少工程化保障：失败定位不充分、重跑恢复能力弱、限流与退避策略不完整、可复现元信息与成本观测不足。现在补齐这些规范，可直接降低构建中断风险并为后续评估优化提供稳定基线。

## 变更内容

- 强化 embedding 构建输入预检规范：空文本跳过、超上限文本按策略截断或拆分，并记录完整统计字段。
- 强化批量调用失败处理：要求记录 HTTP 状态/响应体/trace_id，支持 batch 失败后 per-item fallback，并区分可恢复与不可恢复错误。
- 强化缓存与断点续跑：缓存 key 升级为 `provider + model + normalized_text_hash`，并要求重跑优先命中缓存。
- 强化限流与并发控制：增加可配置 `max_requests_per_minute` 与 `max_concurrent_requests`，429 必须指数退避并统计 backoff 指标。
- 强化可观测与可复现产物：索引输出包含完整 embedding 元信息，运行日志补充 embedding 构建/查询耗时、失败样本和 cache/API 统计，并新增 M2.5 评估报告输出。
- 不引入 BREAKING API 变更；主要是在现有 embedding 管线上新增和收紧行为约束。

## 功能 (Capabilities)

### 新增功能
- `embedding-reliability-observability`: 规范 embedding 构建的失败归因、限流退避、可观测指标与可复现输出要求。

### 修改功能
- `embedding-indexing-and-cache`: 将缓存键、失败处理、断点续跑和索引元信息要求提升到工程可用级别，与 M2.5 验收标准对齐。

## 影响

- 受影响代码：embedding 索引构建流程、embedding API 客户端封装、缓存读写模块、runs 日志写入、评估报告生成。
- 受影响产物：`data/indexes/vec_index_embed.json`、`data/indexes/embedding_cache.jsonl`、`runs/*`、`reports/m2_5_embedding_engineering.md`。
- 运行影响：请求调度逻辑、失败重试路径和统计埋点增加，构建稳定性与可追踪性提高。
