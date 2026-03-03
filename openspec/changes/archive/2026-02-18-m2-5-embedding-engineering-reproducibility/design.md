## 上下文

当前系统已具备 embedding 构建、缓存和检索基础能力，但在大批量构建场景下仍存在稳定性与可追踪性缺口：输入异常处理不统一、batch 失败后归因不足、429/5xx 的恢复策略不完整、断点续跑对缓存键鲁棒性不足、运行指标覆盖不够。M2.5 目标是在不改变上层调用语义的前提下，将 embedding 管线升级为可恢复、可观测、可复现的工程化流程。

关键约束：
- 构建输入固定为 `data/processed/chunks_clean.jsonl`，仅处理 `suppressed=false` 且 `content_type!=watermark`。
- 输出索引与缓存路径保持既有约定：`data/indexes/vec_index_embed.json`、`data/indexes/embedding_cache.jsonl`。
- 外部 provider（如 SiliconFlow）存在速率与可用性波动，必须通过限流、退避与失败隔离控制风险。

## 目标 / 非目标

**目标：**
- 建立 embedding 输入预检与策略化处理（空文本跳过、超限截断或拆分）。
- 建立 batch/per-item 分层失败处理，记录可定位的失败上下文（status/body/trace_id）。
- 将缓存命中规则升级为 `provider + model + normalized_text_hash`，实现可靠断点续跑。
- 支持 `max_requests_per_minute` 与 `max_concurrent_requests` 双限流，并对 429/5xx 使用指数退避。
- 扩展构建与查询日志，沉淀耗时、失败和成本相关统计；输出 M2.5 评估报告。

**非目标：**
- 不引入新的向量数据库或在线 ANN 服务。
- 不变更查询接口协议与现有 QA 输出结构。
- 不在本阶段引入多模型路由或自动模型选择。

## 决策

### 决策 1：输入预检采用“先规范化再分流”
- 方案：对 `clean_text` 先做 `strip()` 和规范化；空字符串直接跳过；超限按配置执行 `truncate` 或 `split`。
- 原因：将不可恢复错误前置，减少 provider 侧 4xx；同时保证行为可配置且可审计。
- 备选方案：把全部异常交给 provider 返回。
  - 未选原因：错误归因晚、成本高、重试无意义。

### 决策 2：失败恢复采用“batch 失败降级到 per-item”
- 方案：batch 非 200 时解析 HTTP 状态与响应体，并提取 trace_id；随后对该 batch 条目执行 per-item 请求。对可恢复错误（429/5xx/网络）指数退避重试；对不可恢复错误（空输入、超限、格式错误）直接标记 badcase。
- 原因：兼顾吞吐与成功率，并确保失败原因可追踪。
- 备选方案：batch 失败直接整体失败。
  - 未选原因：单点失败会放大损失，不满足“不中断整体流程”。

### 决策 3：缓存键升级为文本哈希语义键
- 方案：缓存 key 固定为 `provider + model + normalized_text_hash`，并保存维度、时间戳与来源信息。重跑时先读缓存，再计算 miss 集。
- 原因：规避仅按 chunk_id 命中导致的内容漂移风险，提升断点续跑正确性。
- 备选方案：沿用 `(chunk_id, model)`。
  - 未选原因：chunk 内容变化时可能命中脏缓存。

### 决策 4：限流采用“令牌速率 + 并发上限”双控制
- 方案：请求前经过 RPM 速率控制器和并发 semaphore；429 触发指数退避并累计 `backoff_total_ms`。
- 原因：比单一 sleep 更稳定，能同时约束峰值与稳态请求量。
- 备选方案：仅串行请求。
  - 未选原因：吞吐过低，无法支撑 20-30 篇论文构建时长目标。

### 决策 5：观测模型采用“运行日志 + 报告文件”双层产物
- 方案：在 `runs/*` 增加 embedding 字段（cache 命中、API 调用、失败列表、耗时）；构建后生成 `reports/m2_5_embedding_engineering.md` 汇总统计与断点续跑对比。
- 原因：既支持单次排障，也支持阶段验收与横向比较。
- 备选方案：只保留控制台输出。
  - 未选原因：不可追溯，不满足可复现审计。

## 风险 / 权衡

- [风险] `split` 策略会引入子段聚合复杂度和向量语义偏移
  - 缓解：默认使用 `truncate`，`split` 仅通过配置显式启用，并记录分段映射。
- [风险] 高并发下缓存写入可能出现竞争或部分损坏
  - 缓解：采用原子追加/临时文件落盘与周期 flush，失败时回退只读缓存模式。
- [风险] provider 返回格式变化导致 trace_id 解析失败
  - 缓解：trace_id 解析采用多 header 兼容策略并在缺失时落默认值。
- [风险] 失败样本记录过长影响日志体积
  - 缓解：对 chunk_id 列表做可配置截断，并保留 `embedding_failed_count` 全量计数。

## 迁移计划

1. 配置迁移：在 embedding 配置中新增预检策略、重试参数、限流参数。
2. 构建迁移：改造 embedding builder 执行链为 `precheck -> cache lookup -> batch call -> fallback -> persist`。
3. 日志迁移：统一 runs 字段协议，补齐构建与查询耗时、失败分类、缓存统计。
4. 报告迁移：新增 `reports/m2_5_embedding_engineering.md` 生成逻辑，包含两次运行对比。
5. 验收迁移：执行中断重跑演示并抽样失败 case 验证可归因。

回滚策略：将新限流与预检策略关闭，退回 M2.4 的基础 embedding 流程，同时保留新增日志字段（允许为空）。

## 开放问题

- 是否需要将 cache 后端从 JSONL 升级为 sqlite 以支持更高并发写入。
- split 策略下多子段向量聚合方式（mean/max/first）是否需要在本阶段固化。
- 失败原因分类枚举是否应与后续评估脚本共享常量定义。
