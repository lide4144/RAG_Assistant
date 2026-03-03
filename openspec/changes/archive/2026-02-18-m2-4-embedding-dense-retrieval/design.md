## 上下文

当前检索链路已具备 BM25、"dense"（TF-IDF cosine）与 hybrid 融合、query rewrite、content_type 权重与 1-hop 图扩展，但 dense 语义能力仍受限于词袋匹配。M2.4 需要接入外部 embedding API（默认 SiliconFlow）并将 dense 升级为真实向量检索，同时必须保持 QA CLI、输出结构与后续证据组织流程兼容。

约束条件：
- 索引与检索文本必须使用 `clean_text`。
- `watermark` chunk 禁止参与 embedding。
- dense 升级后仍需保留 TF-IDF dense 作为可配置 baseline（`dense_backend`）。
- graph expansion 不允许对扩展候选二次调用 embedding API。
- 必须增加可复现日志与缓存命中统计。

## 目标 / 非目标

**目标：**
- 引入可配置 embedding provider 接口，并在索引构建阶段批量生成 chunk embedding。
- 构建本地 JSON 向量索引（`vec_index_embed.json`）与 JSONL 缓存（`embedding_cache.jsonl`）。
- dense 模式支持 `embedding|tfidf` backend 切换，默认 embedding。
- hybrid 在 dense 分值来源切换后仍按 min-max 归一化进行融合。
- 维持 M2.3 输出结构与 graph expansion 兼容。
- 运行日志完整记录 embedding 参数、缓存命中、API 调用、查询时延与分值类型。

**非目标：**
- 不训练或微调 embedding 模型。
- 不引入向量数据库服务。
- 不做多 embedding 模型集成检索。

## 决策

### 决策 1：引入统一 Dense Backend 抽象
- 方案：在检索层引入 `dense_backend` 配置分支。
  - `embedding`：query 走 embedding API，doc 使用本地 embedding 索引，余弦相似度排序。
  - `tfidf`：保留现有 TF-IDF dense 行为，不触发 embedding API。
- 原因：保证 `--mode dense` CLI 语义不变，同时满足 M2.4 默认升级与 M9 消融实验可复现。
- 备选方案：新增 CLI 参数区分 `dense-embed/dense-tfidf`。
  - 未选原因：破坏现有 CLI 语义并增加用户迁移成本。

### 决策 2：索引构建采用“缓存优先 + 批量补齐”
- 方案：读取可用 chunk 后先按 `(chunk_id, model)` 命中缓存，miss 集合按 `batch_size` 批量请求 API；单条失败最多重试 2 次；成功结果写回缓存并产出索引。
- 原因：降低外部 API 成本与构建时间，满足“第二次构建命中率 >90%”目标。
- 备选方案：全量重新计算 embedding。
  - 未选原因：成本高、不可复现性更强、无法达成缓存验收。

### 决策 3：规范化与打分策略固定为 L2 + cosine（可开关）
- 方案：`embedding.normalize=true` 时对 doc/query 向量做 L2 normalize，dense 分值统一为 cosine；记录 `dense_score_type=cosine`。
- 原因：与主流 embedding 检索一致，便于跨问题比较与混合融合归一化。
- 备选方案：dot-product 或 provider 原生相似度。
  - 未选原因：不同模型尺度不稳定，融合可解释性较差。

### 决策 4：图扩展候选分值继承，不做二次向量化
- 方案：扩展候选若无 embedding 分值，则继承 seed 分值乘衰减（邻接 0.97，实体 0.94）。
- 原因：避免扩展阶段 API 调用爆炸，同时保留图结构召回收益。
- 备选方案：扩展候选实时补 embedding。
  - 未选原因：调用量不可控，时延与成本不可接受。

### 决策 5：日志协议扩展并保持输出兼容
- 方案：新增 embedding 相关运行字段，但不删除既有 M2.3 字段；保留 `papers_ranked`、`evidence_grouped`、`answer_citations` 等结构。
- 原因：兼容现有下游评估脚本与报表。

## 风险 / 权衡

- [风险] 外部 API 波动或限流导致构建失败
  - 缓解：批量重试（最多 2 次）、记录失败项并继续处理成功样本、日志记录 `embedding_api_calls` 与失败信息。
- [风险] 模型维度或 provider 响应格式变化导致索引不一致
  - 缓解：写入 `embedding_provider/model/dim` 到索引头；构建前做维度一致性校验。
- [风险] hybrid 融合后排序波动影响既有体验
  - 缓解：保留 `dense_backend=tfidf` 回退；通过报告记录 dense/hybrid 对比样例。
- [风险] cache 文件增长与模型切换污染
  - 缓解：缓存键包含 `chunk_id + model`，读取时按当前模型过滤。

## 迁移计划

1. 配置迁移：在 `configs/default.yaml` 增加 `embedding` 段与 `dense_backend` 默认值。
2. 索引迁移：新增 embedding 索引构建命令路径，保留原 BM25/TF-IDF 索引流程。
3. 检索迁移：dense/hybrid 逻辑接入 backend 分支；graph expansion 接入分值继承逻辑。
4. 观测迁移：日志结构扩展并验证字段完整性。
5. 验收迁移：运行 M2.4 指定的 dense/hybrid/缓存/兼容测试并输出 `reports/m2_4_embedding_upgrade.md`。

回滚策略：若 embedding provider 不可用或线上效果不稳定，将 `dense_backend` 切回 `tfidf`，并暂时禁用 `embedding.enabled`。

## 开放问题

- 当前代码中索引构建与 QA 运行日志写入是否在同一模块，若分散需先统一字段注入点。
- 是否需要在构建阶段对失败 chunk 产生独立错误清单文件，便于离线补算。
