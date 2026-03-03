# RAG_GPTV1.0

基于论文知识库的本地 RAG 实验项目。当前系统覆盖了从 PDF 入库到问答输出的完整链路，并在检索、重写、图扩展、证据门控等环节持续迭代。

## 项目概览

### 已实现里程碑（Milestones）

- M1: 论文入库（PDF 解析 + Chunk 化 + 存储）
- M1.5: Chunk 清洗与质量标注（`clean_text`、`content_type`、`quality_flags`）
- M2: 基础检索（BM25 / 向量 / Hybrid）+ QA baseline
- M2.1: 多论文聚合检索（paper 分组、scope policy、内容类型策略）
- M2.2: Query Intent Calibration（歧义问题校准、summary shell 检测、单次 retry）
- M2.3: Output Consistency & Evidence Allocation（输出一致性、证据分配、引用追踪与降级告警）
- M2.4: Embedding Dense Retrieval（外部 API embedding、dense_backend 切换、缓存与失败记录）
- M3: Query Rewriting（规则优先，可选 LLM 开关与降级）
- M4: Chunk Graph Construction（adjacent/entity 图构建、阈值截断、邻居查询）
- M5: Graph Expansion Retrieval（初检 top-k 上 1-hop 图扩展召回、强过滤、候选规模控制）
- M5.1: Graph Expansion Compatibility Patch（seeds 元数据契约增强、backend 语义继承、runs 扩展预算追踪）
- M7: Evidence Policy（关键结论引用约束、citation 可追溯校验、Sufficiency Gate 门控）
- M7.6: Multi-turn Session State（`session_id` 会话状态、脱水历史、`standalone_query` 指代消解、clarify 闭环）
- M7.8: Meta-question Rewrite Guard（元问题识别、`meta_guard` 护栏、实体保真转写、可观测字段）

### 系统链路（从输入到回答）

```text
PDF files
  -> ingest
  -> clean_chunks
  -> build_indexes (bm25 + tfidf vec + optional embedding vec)
  -> (optional) graph_build
  -> qa
       |- scope policy + query rewrite + intent calibration
       |- retrieval + graph expansion + rerank
       |- evidence allocation + evidence policy gate
       `- answer + citations + run logs
```

## 目录结构

- `app/`: 核心代码（ingest / clean / index / graph / qa 等）
- `configs/`: 配置文件（默认 `default.yaml`）
- `data/papers/`: PDF 输入目录
- `data/processed/`: 处理中间产物（chunks / graph）
- `data/indexes/`: 检索索引与 embedding 缓存
- `reports/`: 评估和验收报告
- `runs/`: 每次运行的 trace 和报告
- `openspec/`: 变更与规范

## 环境准备

推荐使用 venv：

```bash
python3 -m venv venv
source venv/bin/activate
venv/bin/python -m pip install -U pip
# 按项目依赖安装
venv/bin/python -m pip install -r requirements.txt
```

如需 embedding / LLM 路径，设置 API Key：

```bash
export SILICONFLOW_API_KEY="your_key"
```

## 快速开始（最小可跑通）

### 1) 入库

```bash
venv/bin/python -m app.ingest --input data/papers --out data/processed
```

产物：
- `data/processed/chunks.jsonl`
- `data/processed/papers.json`
- `runs/<timestamp>/ingest_report.json`

### 2) 清洗

```bash
venv/bin/python -m app.clean_chunks --input data/processed/chunks.jsonl --out data/processed/chunks_clean.jsonl
```

产物：
- `data/processed/chunks_clean.jsonl`

### 3) 构建索引

```bash
venv/bin/python -m app.build_indexes \
  --input data/processed/chunks_clean.jsonl \
  --bm25-out data/indexes/bm25_index.json \
  --vec-out data/indexes/vec_index.json \
  --embed-out data/indexes/vec_index_embed.json
```

产物：
- `data/indexes/bm25_index.json`
- `data/indexes/vec_index.json`
- `data/indexes/vec_index_embed.json`（仅当 `embedding.enabled=true`）
- `data/indexes/embedding_cache.jsonl`（启用缓存时）
- `data/indexes/embedding_failures.jsonl`（有失败时）

### 4) （可选）图构建

```bash
venv/bin/python -m app.graph_build \
  --input data/processed/chunks_clean.jsonl \
  --out data/processed/graph.json \
  --threshold 1 \
  --top-m 30
```

### 5) QA

```bash
venv/bin/python -m app.qa --q "这篇论文的主要贡献是什么？" --mode hybrid
```

输出：
- 终端 Answer + grouped evidence
- `runs/<timestamp>/run_trace.json`
- `runs/<timestamp>/qa_report.json`

### 6) M8.5 可视化调试 UI（Streamlit）

详细使用说明见：[UI_USAGE.md](UI_USAGE.md)

```bash
streamlit run app/ui.py
```

UI 功能：
- 对话区：多轮聊天、Assistant 回答渲染、引用编号 `[1] [2]` 点击审查
- 开发者审查面板：Query 演变、`intent_type` / `anchor_query` / `topic_query_source`、`evidence_grouped`（含 `score_retrieval` / `score_rerank` / `source`）、Sufficiency Gate 降级告警
- 会话控制：`开启新对话 / 清空上下文`（调用 `clear_session`）

M8.5 手工验收建议：
- 启动 UI 并完成至少一次问答
- 提交一个触发图扩展的问题，确认 Inspector 可区分 `source=graph_expand`
- 点击清空后提无关问题，确认新轮次不受旧上下文污染

## 模块级使用手册

本节按模块说明：用途、输入、输出、命令、典型场景。

### `app.ingest`

用途：解析 `data/papers/*.pdf`，切分 chunk，生成结构化入库产物；可选串联清洗。

输入：
- PDF 目录（`--input`）
- 配置文件（`--config`，默认 `configs/default.yaml`）

输出：
- `chunks.jsonl`、`papers.json`
- run 日志和 ingest 报告
- 可选 `chunks_clean.jsonl`（当 `--clean`）

命令：

```bash
venv/bin/python -m app.ingest \
  --input data/papers \
  --out data/processed \
  --config configs/default.yaml \
  --question "What is the main contribution?" \
  --clean
```

典型场景：
- 新增论文后重建基础语料
- 首次搭建项目数据基线

### `app.clean_chunks`

用途：对 `chunks.jsonl` 做文本清洗、类型标注、短碎片合并（table_list）。

输入：
- `--input` 指向 `chunks.jsonl`

输出：
- `chunks_clean.jsonl`
- 每条记录包含 `clean_text`、`content_type`、`quality_flags`

命令：

```bash
venv/bin/python -m app.clean_chunks \
  --input data/processed/chunks.jsonl \
  --out data/processed/chunks_clean.jsonl
```

典型场景：
- 入库后做检索前标准化
- 需要重新应用清洗规则（如 URL 标准化）

### `app.build_indexes`

用途：一次性构建 BM25、TF-IDF 向量索引，并在启用时构建 embedding 索引。

输入：
- `chunks_clean.jsonl`
- 配置文件（embedding/rerank/dense_backend 等）

输出：
- `bm25_index.json`
- `vec_index.json`（TF-IDF）
- `vec_index_embed.json`（embedding）

命令：

```bash
venv/bin/python -m app.build_indexes \
  --input data/processed/chunks_clean.jsonl \
  --bm25-out data/indexes/bm25_index.json \
  --vec-out data/indexes/vec_index.json \
  --embed-out data/indexes/vec_index_embed.json \
  --config configs/default.yaml
```

典型场景：
- 全量更新索引
- 切换 embedding 模型后重建 embedding 索引

### `app.index_bm25`

用途：仅构建 BM25 索引。

命令：

```bash
venv/bin/python -m app.index_bm25 \
  --input data/processed/chunks_clean.jsonl \
  --out data/indexes/bm25_index.json
```

### `app.index_vec`

用途：仅构建 TF-IDF 向量索引（非 embedding 索引）。

命令：

```bash
venv/bin/python -m app.index_vec \
  --input data/processed/chunks_clean.jsonl \
  --out data/indexes/vec_index.json
```

### `app.graph_build`

用途：从清洗后的 chunk 构建邻接/实体图，为 M5 图扩展检索提供结构先验。

输入：
- `chunks_clean.jsonl`

输出：
- `graph.json`（默认）

命令：

```bash
venv/bin/python -m app.graph_build \
  --input data/processed/chunks_clean.jsonl \
  --out data/processed/graph.json \
  --threshold 1 \
  --top-m 30 \
  --include-front-matter
```

典型场景：
- 希望提升跨段落关联召回
- 问题涉及作者/引用信息时需要可控图扩展

### `app.qa`

用途：主问答入口，包含 scope policy、query rewriting、intent calibration、检索融合、图扩展、重排和证据门控。

输入：
- 问题文本（`--q`）
- mode（`dense|bm25|hybrid`）
- 索引路径与配置
- 会话参数（`--session-id`、`--session-store`、`--clear-session`）

输出：
- 控制台答案和分组证据
- `run_trace.json`、`qa_report.json`
- 多轮日志字段：`session_id`、`turn_number`、`history_used_turns`、`history_tokens_est`、`coreference_resolved`、`standalone_query`

命令：

```bash
venv/bin/python -m app.qa \
  --q "What evidence describes limitations?" \
  --mode hybrid \
  --session-id demo-session \
  --chunks data/processed/chunks_clean.jsonl \
  --bm25-index data/indexes/bm25_index.json \
  --vec-index data/indexes/vec_index.json \
  --embed-index data/indexes/vec_index_embed.json \
  --config configs/default.yaml
```

典型场景：
- 论文问答主流程
- 检索策略对比（`bm25` vs `dense` vs `hybrid`）

### QA 内部关键模块（非独立 CLI）

- `app.rewrite`: 查询重写（规则优先，可选 LLM）
- `app.intent_calibration`: 意图校准与语义 cue 注入
- `app.retrieve`: 检索融合、content_type 权重、图扩展入口
- `app.rerank`: 候选重排
- `app.generate`: 答案生成（规则模板 / 可选 LLM）
- `app.judge`: 预留阶段模块

## CLI 参数说明

以下为当前代码可直接传参的 CLI 参数。

### `app.ingest`

| 参数 | 默认值 | 含义 | 调整影响 | 建议 |
|---|---|---|---|---|
| `--input` | 必填 | PDF 目录 | 决定入库源 | 统一放在 `data/papers` |
| `--out` | 必填 | 输出目录 | 决定 chunks/papers 产物位置 | 推荐 `data/processed` |
| `--config` | `configs/default.yaml` | 配置路径 | 影响 chunk、检索等默认参数写入报告 | 使用版本化配置文件 |
| `--question` | `None` | 写入 run trace 的输入问题 | 不影响入库逻辑，仅用于追踪 | 可留空 |
| `--clean` | `false` | 入库后立即清洗 | 增加耗时，但减少手工步骤 | 推荐首跑开启 |

### `app.clean_chunks`

| 参数 | 默认值 | 含义 | 调整影响 | 建议 |
|---|---|---|---|---|
| `--input` | 必填 | 原始 `chunks.jsonl` 路径 | 影响清洗输入 | 指向 ingest 产物 |
| `--out` | 必填 | 清洗后输出路径 | 影响后续索引输入 | 推荐 `data/processed/chunks_clean.jsonl` |

### `app.build_indexes`

| 参数 | 默认值 | 含义 | 调整影响 | 建议 |
|---|---|---|---|---|
| `--input` | `data/processed/chunks_clean.jsonl` | 清洗后 chunk 输入 | 输入质量直接影响召回质量 | 使用最新清洗产物 |
| `--bm25-out` | `data/indexes/bm25_index.json` | BM25 索引输出 | QA bm25/hybrid 依赖 | 保持默认 |
| `--vec-out` | `data/indexes/vec_index.json` | TF-IDF 向量索引输出 | QA dense(tfidf) / hybrid 依赖 | 保持默认 |
| `--embed-out` | `data/indexes/vec_index_embed.json` | embedding 索引输出 | `dense_backend=embedding` 时必需 | 统一版本管理 |
| `--config` | `configs/default.yaml` | 配置路径 | 控制 embedding 开关、模型与限流参数 | 与 QA 使用同一配置 |

### `app.index_bm25`

| 参数 | 默认值 | 含义 |
|---|---|---|
| `--input` | `data/processed/chunks_clean.jsonl` | 输入数据 |
| `--out` | `data/indexes/bm25_index.json` | 输出索引 |

### `app.index_vec`

| 参数 | 默认值 | 含义 |
|---|---|---|
| `--input` | `data/processed/chunks_clean.jsonl` | 输入数据 |
| `--out` | `data/indexes/vec_index.json` | 输出 TF-IDF 向量索引 |

### `app.graph_build`

| 参数 | 默认值 | 含义 | 调整影响 | 建议 |
|---|---|---|---|---|
| `--input` | `data/processed/chunks_clean.jsonl` | 图构建输入 | 决定可建图节点 | 使用清洗产物 |
| `--out` | `data/processed/graph.json` | 图文件输出 | QA 图扩展读取路径 | 与 `graph_path` 保持一致 |
| `--threshold` | `1` | 实体共现边最小共享实体数 | 越大边越稀疏 | 1~2 常用 |
| `--top-m` | `30` | 每个 chunk 保留的实体邻居上限 | 越大图更密集、扩展成本更高 | 20~50 |
| `--include-front-matter` | `false` | 是否纳入 front_matter 节点 | 影响作者/机构类问题召回 | 默认关闭，按需开启 |

### `app.qa`

| 参数 | 默认值 | 含义 | 调整影响 | 建议 |
|---|---|---|---|---|
| `--q` | 必填 | 用户问题 | 决定检索目标 | 提问尽量具体 |
| `--mode` | `hybrid` | 检索模式：`dense|bm25|hybrid` | 影响召回来源与融合方式 | 通用推荐 `hybrid` |
| `--chunks` | `data/processed/chunks_clean.jsonl` | chunks 数据路径 | 用于 paper title 映射与证据展示 | 与索引同版本 |
| `--bm25-index` | `data/indexes/bm25_index.json` | BM25 索引路径 | bm25/hybrid 依赖 | 保持默认 |
| `--vec-index` | `data/indexes/vec_index.json` | TF-IDF 向量索引路径 | dense(tfidf)/hybrid 依赖 | 保持默认 |
| `--embed-index` | `data/indexes/vec_index_embed.json` | embedding 索引路径 | dense_backend=embedding 时依赖 | 与模型一致 |
| `--config` | `configs/default.yaml` | 配置路径 | 决定重写、重排、图扩展、证据门控行为 | 与 build_indexes 同配置 |
| `--top-k` | `None` | 覆盖检索 top-k（否则用配置） | 候选数量与延迟直接相关 | 调参时显式指定 |
| `--top-evidence` | `5` | 计划中的证据输出数 | 当前版本未在主流程中生效（保留参数） | 以 `top_n_evidence` 与分组逻辑为准 |
| `--session-id` | `default` | 会话 ID（多轮上下文隔离） | 同一 session 才会复用脱水历史 | 前端会话维度传入稳定值 |
| `--session-store` | `data/session_store.json` | 会话存储文件 | 影响历史读写位置 | 本地开发保持默认即可 |
| `--clear-session` | `false` | 本轮执行前清空指定会话 | 清空后 `history_used_turns` 归零 | 切换主题时建议开启一次 |

## `configs/default.yaml` 参数参考

以下是默认配置文件中的关键参数，以及行为影响。

### 检索与融合

| 参数 | 默认值 | 含义 | 影响与建议 |
|---|---|---|---|
| `top_k_retrieval` | `20` | 检索候选规模 | 越大召回更高但噪声与耗时增加；常用 10~40 |
| `top_n_evidence` | `8` | 证据上限参考值 | 与分组展示和重排策略共同作用 |
| `fusion_weight` | `0.6` | hybrid 中 dense 权重 | 趋近 1 更偏 dense，趋近 0 更偏 bm25 |
| `RRF_k` | `60` | RRF 融合常数 | 越大对头部差异更平滑 |
| `dense_backend` | `embedding` | dense 路径后端（`embedding|tfidf`） | 无 API 时用 `tfidf` 保底 |
| `table_list_downweight` | `0.5` | 表格/列表类 chunk 降权 | 降低碎片化证据主导风险 |
| `front_matter_downweight` | `0.3` | front_matter 默认降权 | 作者/机构问题会条件放行 |
| `reference_downweight` | `0.3` | reference 默认降权 | 引用/量表/验证问题会条件放行 |

### 图扩展

| 参数 | 默认值 | 含义 | 影响与建议 |
|---|---|---|---|
| `graph_path` | `data/processed/graph.json` | 图文件路径 | 文件不存在会导致图扩展退化为无扩展 |
| `graph_expand_alpha` | `2.0` | 图扩展分值系数 | 越高越偏向图邻居召回 |
| `graph_expand_max_candidates` | `200` | 图扩展候选上限 | 控制扩展预算与延迟 |
| `graph_expand_author_keywords` | 关键词列表 | 作者意图词 | 命中时更倾向 author/front-matter 路径 |
| `graph_expand_reference_keywords` | 关键词列表 | 引用意图词 | 命中时更倾向 reference/appendix 路径 |

### Query Rewriting 与 LLM

| 参数 | 默认值 | 含义 | 影响与建议 |
|---|---|---|---|
| `rewrite_enabled` | `true` | 是否启用规则改写 | 关闭后直接使用原 query |
| `rewrite_meta_guard_enabled` | `true` | 是否启用元问题护栏 | 关闭后跳过 `meta_guard`，保留默认 trace 字段 |
| `rewrite_use_llm` | `true` | 是否启用 LLM 改写 | 开启需 API Key，失败会按策略回退 |
| `rewrite_max_keywords` | `12` | 改写关键词上限 | 过大会引入噪声 |
| `rewrite_synonyms` | 多语同义词映射 | 规则扩展词典 | 可按领域补充，提高召回一致性 |
| `rewrite_meta_patterns` | 中英元问题规则列表 | 元问题触发模式 | 可按领域补充触发词，降低漏判 |
| `rewrite_meta_noise_terms` | 状态词清洗列表 | 护栏转写时过滤噪声词 | 按业务语料迭代，避免状态词污染检索 |
| `intent_router_enabled` | `false` | 是否启用控制意图路由（M8.6） | 开启后识别 style/format/continuation 控制输入并分流 |
| `intent_control_min_confidence` | `0.75` | 控制意图最小置信度阈值 | 低于阈值会回退 `retrieval_query`，避免误分流 |
| `style_control_reuse_last_topic` | `true` | 控制意图是否复用最近主题锚点 | 关闭时保持旧行为，不做锚点继承 |
| `style_control_max_turn_distance` | `3` | 控制意图锚点最大可复用轮距 | 超限时触发澄清，避免沿用陈旧主题 |
| `answer_use_llm` | `true` | 是否使用 LLM 生成答案 | 开启后更自然，但需关注可控性 |
| `llm_timeout_ms` | `30000` | rewrite LLM 超时 | 超时后按 fallback 逻辑降级 |
| `answer_llm_timeout_ms` | `60000` | answer LLM 超时 | 生成阶段超时控制 |
| `llm_max_retries` | `1` | LLM 重试次数 | 增大可提升鲁棒性但增加时延 |
| `llm_fallback_enabled` | `true` | 是否允许失败回退 | 推荐保持开启 |

### Embedding

| 参数 | 默认值 | 含义 | 影响与建议 |
|---|---|---|---|
| `embedding.enabled` | `true` | 是否构建/使用 embedding | 关闭时仅用 tfidf dense |
| `embedding.provider` | `siliconflow` | API 提供方 | 与 `base_url`、`model` 保持一致 |
| `embedding.base_url` | `https://api.siliconflow.cn/v1` | 接口地址 | 私有网关时替换 |
| `embedding.model` | `Qwen/Qwen3-Embedding-8B` | embedding 模型 | 改模型需重建 embedding 索引 |
| `embedding.api_key_env` | `SILICONFLOW_API_KEY` | API Key 环境变量名 | key 缺失会触发失败/回退 |
| `embedding.batch_size` | `32` | 批量请求大小 | 越大吞吐高但失败重试成本大 |
| `embedding.normalize` | `true` | 向量归一化 | 建议开启，利于稳定余弦相似度 |
| `embedding.cache_enabled` | `true` | 启用缓存 | 推荐开启以降低重复成本 |
| `embedding.cache_path` | `data/indexes/embedding_cache.jsonl` | 缓存文件路径 | 需要纳入数据管理 |
| `embedding.failure_log_path` | `data/indexes/embedding_failures.jsonl` | 失败日志路径 | 用于失败追踪和补偿 |
| `embedding.max_requests_per_minute` | `120` | 每分钟请求上限 | 防止触发限流 |
| `embedding.max_concurrent_requests` | `2` | 并发请求数 | 按供应商限流策略调整 |
| `embedding.max_retries` | `2` | API 重试次数 | 网络抖动场景可适度增大 |
| `embedding.backoff_base_ms` | `500` | 退避起始 | 与 `backoff_max_ms` 共同控制重试节奏 |
| `embedding.backoff_max_ms` | `8000` | 退避上限 | 防止重试等待过长 |
| `embedding.max_tokens_per_chunk` | `512` | 单 chunk token 上限 | 超限按策略截断或拆分 |
| `embedding.over_limit_strategy` | `truncate` | 超限处理策略（`truncate|split`） | 质量与吞吐的折中 |
| `embedding.max_failed_chunk_ids` | `200` | 失败 chunk 记录上限 | 控制日志体积 |
| `embedding.max_skipped_chunk_ids` | `200` | 跳过 chunk 记录上限 | 控制日志体积 |

### Rerank 与证据策略

| 参数 | 默认值 | 含义 | 影响与建议 |
|---|---|---|---|
| `rerank.enabled` | `true` | 是否启用重排 | 关闭后直接用检索分排序 |
| `rerank.model` | `Qwen/Qwen3-Reranker-8B` | 重排模型 | 改模型需观察排序漂移 |
| `rerank.top_n` | `8` | 重排候选规模 | 越大成本越高 |
| `rerank.timeout_ms` | `8000` | 重排超时 | 超时依赖 fallback |
| `rerank.max_retries` | `1` | 重排重试次数 | 可按稳定性调整 |
| `rerank.fallback_to_retrieval` | `true` | 重排失败时回退检索排序 | 推荐开启 |
| `evidence_policy_enforced` | `true` | 强制证据门控 | 开启时关键结论必须可追溯 citation |
| `sufficiency_threshold` | `0.7` | 证据充分性阈值 | 越高越保守，拒答概率增加 |
| `sufficiency_gate_enabled` | `true` | 是否启用 M8 Sufficiency Gate | 关闭后不做 answer/refuse/clarify 前置判定 |
| `sufficiency_topic_match_threshold` | `0.15` | 主题匹配最低阈值（0~1） | 越高越严格，主题不匹配更易拒答 |
| `sufficiency_key_element_min_coverage` | `1.0` | 关键要素最小覆盖率（0~1） | 1.0 表示关键要素必须全部覆盖，否则触发 clarify/refuse |

## 常见使用组合

### 仅用 TF-IDF dense（无 embedding API）

1. 把 `configs/default.yaml` 的 `dense_backend` 设为 `tfidf`
2. 构建索引并 QA：

```bash
venv/bin/python -m app.build_indexes --config configs/default.yaml
venv/bin/python -m app.qa --q "方法如何验证？" --mode dense --config configs/default.yaml
```

### 强调覆盖率（先召回后筛选）

可尝试：
- 提高 `top_k_retrieval`（如 30~40）
- 保持 `rerank.enabled=true`
- 观察 `output_warnings` 和最终证据质量

### 强调稳定与成本

可尝试：
- 降低 `top_k_retrieval`
- 降低 `embedding.batch_size` 或关闭 `embedding.enabled`
- 保持缓存开启

## 排障与验证

### 场景 1：QA 报索引文件不存在

症状：`bm25 index not found` 或 `vec index not found`

可能原因：
- 尚未执行 `app.build_indexes`
- 路径与默认值不一致

检查步骤：

```bash
ls -lh data/indexes/
```

修复建议：
- 重新构建索引
- 通过 `--bm25-index` / `--vec-index` / `--embed-index` 显式传入正确路径

### 场景 2：dense=embedding 时报错或结果为空

症状：embedding 请求失败、构建中断、查询回退效果差

可能原因：
- `SILICONFLOW_API_KEY` 未设置
- 模型名或 `base_url` 错误
- 限流触发

检查步骤：

```bash
echo $SILICONFLOW_API_KEY
cat configs/default.yaml
```

修复建议：
- 设置正确 API Key
- 核对 `embedding.provider/base_url/model`
- 降低并发、提高退避参数
- 临时切换 `dense_backend=tfidf`

### 场景 3：图扩展没有生效

症状：`graph_expansion_stats.graph_loaded=false` 或扩展增量为 0

可能原因：
- `graph_path` 不存在或路径不一致
- `graph_expand_max_candidates` 太小

检查步骤：

```bash
ls -lh data/processed/graph.json
```

修复建议：
- 先运行 `app.graph_build`
- 校对 `graph_path`
- 调整扩展参数并观察 `run_trace.json`

### 场景 4：答案经常“证据不足”

症状：`output_warnings` 包含 `insufficient_evidence_for_answer`

可能原因：
- 证据门控开启且检索证据不足
- query 过于模糊

检查步骤：
- 查看 `runs/<timestamp>/qa_report.json` 中 `output_warnings`、`answer_citations`
- 查看 `run_trace.json` 中 `retrieval_top_k`、`papers_ranked`

修复建议：
- 提高 `top_k_retrieval`
- 优化 query（更具体）
- 必要时临时关闭 `evidence_policy_enforced` 做对比验证
- 使用 `sufficiency_topic_match_threshold` 与 `sufficiency_key_element_min_coverage` 调整拒答/澄清灵敏度

## 关键产物与日志

- 入库：`runs/<timestamp>/ingest_report.json`
- QA：`runs/<timestamp>/qa_report.json`
- 追踪：`runs/<timestamp>/run_trace.json`
- 会话：`data/session_store.json`（仅脱水历史，不包含 raw chunk 文本）
- `run_trace.json` 多轮字段：
  - `session_id`
  - `turn_number`
  - `history_used_turns`
  - `history_tokens_est`
  - `coreference_resolved`
  - `standalone_query`
  - `intent_type`
  - `intent_confidence`
  - `intent_fallback_reason`
  - `anchor_query`
  - `topic_query_source`
- `qa_report.json` / `run_trace.json` 的 M8 字段：
  - `decision`（`answer|refuse|clarify`）
  - `decision_reason`
  - `clarify_questions`（仅 `clarify` 时非空，1~2 条）
  - `sufficiency_gate`（判定特征、触发规则与最终决策）
- 常见评估报告：
  - `reports/m2_baseline.md`
  - `reports/m2_1_policy.md`
  - `reports/m2_2_intent_calibration.md`
  - `reports/m2_3_output_consistency.md`
  - `reports/m2_4_embedding_upgrade.md`
  - `reports/m4_graph_build.md`
  - `reports/m5_graph_expansion_eval.md`
  - `reports/m7_6_multi_turn_cases.md`
  - `reports/m7_8_meta_question_guard.md`

## M7 验收脚本

```bash
venv/bin/python scripts/validate_m7_evidence_policy.py \
  --questions reports/m7_questions_30.txt \
  --config configs/m7_regression.yaml
```

```bash
venv/bin/python scripts/export_m7_audit_sample.py \
  --sample-size 10 \
  --out reports/m7_audit_sample.json
```

```bash
venv/bin/python scripts/eval_m7_8_meta_guard.py \
  --samples reports/m7_8_meta_guard_samples.json \
  --output reports/m7_8_meta_question_guard.md
```

## 开发说明

如果你在做需求变更，建议使用 OpenSpec 工作流：
- 创建变更：`/opsx:new <change-name>` 或 `/opsx:ff <change-name>`
- 实现变更：`/opsx:apply <change-name>`
- 归档变更：`/opsx:archive <change-name>`
