## 新增需求

### 需求:基础检索索引构建
系统必须基于 `data/processed/chunks_clean.jsonl` 构建 BM25 与向量索引。系统必须使用 `clean_text` 作为索引文本字段，且禁止将 `content_type=watermark` 的 chunk 纳入任一索引。

#### 场景:构建 BM25 与向量索引
- **当** 用户执行索引构建流程并提供 `chunks_clean.jsonl`
- **那么** 系统必须同时产出 BM25 与向量索引，并记录索引条目数

#### 场景:过滤 watermark chunk
- **当** 输入 chunk 的 `content_type` 为 `watermark`
- **那么** 系统必须在 BM25 与向量索引构建阶段都排除该 chunk

### 需求:检索模式与融合
系统必须支持 `dense`、`bm25`、`hybrid` 三种检索模式。`hybrid` 模式必须融合 BM25 与向量候选，且对 `content_type=table_list` 的候选应用降权（默认乘以 `0.5`），但禁止直接剔除该候选。

#### 场景:dense 模式返回候选
- **当** 用户以 `--mode dense` 发起检索
- **那么** 系统必须返回向量检索 top-k 候选

#### 场景:bm25 模式返回候选
- **当** 用户以 `--mode bm25` 发起检索
- **那么** 系统必须返回 BM25 检索 top-k 候选

#### 场景:hybrid 模式融合并降权
- **当** 用户以 `--mode hybrid` 发起检索且候选中包含 `table_list`
- **那么** 系统必须返回融合后的排序结果，并对 `table_list` 候选执行降权后仍保留在候选集中

### 需求:最小 QA CLI 输出
系统必须提供命令 `python -m app.qa --q "<question>" --mode dense|bm25|hybrid`。命令输出必须包含简短 Answer 与 Top-5 evidence 列表，且每条 evidence 至少包含 `chunk_id`、`section/page`、`quote`。

#### 场景:CLI 问答输出格式
- **当** 用户执行 QA CLI 并获得候选证据
- **那么** 系统必须输出 Answer 与 Top-5 evidence，且字段结构满足 `chunk_id + section/page + quote`

### 需求:证据引用来源约束
系统检索与重排阶段必须基于 `clean_text` 工作，但 evidence 的 `quote` 必须来自原始 `text` 字段。

#### 场景:生成 evidence quote
- **当** 系统为答案生成证据引用片段
- **那么** 每条 `quote` 必须截取自对应 chunk 的原始 `text`，而不是 `clean_text`

### 需求:M2 最小验收
系统必须满足 M2 基线验收：dense 与 bm25 都能返回 top-k，hybrid 能返回融合结果；并对至少 30 个自制问题可在 evidence 中找到相关段落（主观评审）。

#### 场景:检索模式验收
- **当** 对同一问题分别执行 `dense`、`bm25`、`hybrid`
- **那么** 系统必须在三种模式下都返回非空候选，且 `hybrid` 返回融合排序结果

#### 场景:30 问题主观相关性检查
- **当** 用户完成 30 个自制问题的基线测试
- **那么** 至少应能在每个问题的 evidence 中找到相关段落或记录无法命中的具体原因

## 修改需求

## 移除需求
