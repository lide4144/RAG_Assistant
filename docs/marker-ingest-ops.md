# Marker 本地文档增强解析运维说明

## 1. 依赖安装

Marker 为可选增强依赖，未安装时系统会继续使用本地基础解析器；默认启动路径不再把 Marker 视为前置条件。

```bash
venv/bin/python -m pip install -r requirements.txt
```

若需要单独安装 Marker：

```bash
venv/bin/python -m pip install marker-pdf
```

## 2. 配置开关

`configs/default.yaml` 新增：

- `marker_enabled`: 是否启用 Marker PDF 增强解析（默认 `false`）
- `marker_timeout_sec`: Marker 单文档超时秒数（默认 `30`）
- `title_confidence_threshold`: 标题门禁阈值（默认 `0.6`）
- `title_blacklist_patterns`: 标题黑名单正则列表（默认包含 `Preprint. Under review.`、`All rights reserved` 等）

个人电脑或低资源环境推荐保持：

```yaml
marker_enabled: false
```

## 2.1 Marker Runtime 档位（推荐）

系统支持通过 `POST /api/admin/pipeline-config` 持久化以下参数：

- `recognition_batch_size`
- `detector_batch_size`
- `layout_batch_size`
- `ocr_error_batch_size`
- `table_rec_batch_size`
- `model_dtype`

并支持显式注册字段的环境变量覆盖（优先级：`ENV > runtime config > default`）：

- `RECOGNITION_BATCH_SIZE`
- `DETECTOR_BATCH_SIZE`
- `LAYOUT_BATCH_SIZE`
- `OCR_ERROR_BATCH_SIZE`
- `TABLE_REC_BATCH_SIZE`
- `MODEL_DTYPE`

8GB 显存推荐安全档位：

```json
{
  "recognition_batch_size": 2,
  "detector_batch_size": 2,
  "layout_batch_size": 2,
  "ocr_error_batch_size": 1,
  "table_rec_batch_size": 1,
  "model_dtype": "float16"
}
```

### 2.2 Marker LLM Service 配置

`POST /api/admin/pipeline-config` 现同时支持 `marker_llm` 配置块，用于对齐 Marker `--use_llm` 相关前端设置：

- `use_llm`
- `llm_service`
- `gemini_api_key`
- `vertex_project_id`
- `ollama_base_url`
- `ollama_model`
- `claude_api_key`
- `claude_model_name`
- `openai_api_key`
- `openai_model`
- `openai_base_url`
- `azure_endpoint`
- `azure_api_key`
- `deployment_name`

常见 service 与必填字段：

- `gemini`：`gemini_api_key`
- `marker.services.vertex.GoogleVertexService`：`vertex_project_id`
- `marker.services.ollama.OllamaService`：`ollama_base_url`、`ollama_model`
- `marker.services.claude.ClaudeService`：`claude_api_key`、`claude_model_name`
- `marker.services.openai.OpenAIService`：`openai_api_key`、`openai_model`
- `marker.services.azure_openai.AzureOpenAIService`：`azure_endpoint`、`azure_api_key`、`deployment_name`

读取配置时，接口会返回脱敏后的 `marker_llm` 摘要和 `effective_source`；保存时若 secret 字段留空，后端会保留已有密钥而不是清空。字段 owner、页面边界与统一来源语义见 `docs/config-governance.md`。

## 3. 观测字段

`papers.json`（本地文档）新增字段：

- `parser_engine` (`marker` / `legacy` / `text` / `docx` / `pptx` / `xlsx` / `rtf` / `odt` / `epub`)
- `title_source` (`marker_h1` / `marker_h2` / `marker_markdown_first_line` / `marker` / `metadata` / `fallback_*`)
- `title_confidence` (0-1)
- `ingest_metadata.title_layer`：最终采用的标题层级
- `ingest_metadata.title_decision_trace[]`：每层候选是 `accepted`、`rejected` 还是 `missing`
- `ingest_metadata.structured_title_candidates[]`：结构化标题候选快照，供历史修复脚本复用
- `ingest_metadata.markdown_consumption_status`：`partial` / `missing`
- `ingest_metadata.block_semantics_preserved`、`ingest_metadata.block_types[]`

`chunks.jsonl` / `chunks_clean.jsonl`（Marker 成功时）会额外保留：

- `content_type`：`table_block`、`formula_block` 或 `body`
- `block_type`
- `markdown_source`
- `structure_provenance`

`runs/*/ingest_report.json` 新增：

- `parser_observability[]`
  - `parser_engine`
  - `parser_mode` (`base_only` / `enhanced` / `degraded_from_marker` / `controlled_skip`)
  - `base_parser`
  - `enhanced_parser`
  - `parser_fallback`
  - `parser_fallback_reason`
  - `controlled_skip`
  - `controlled_skip_reason`
  - `structured_segments_missing`
  - `structured_segments_missing_reason`
  - `title_source`
  - `title_layer`
  - `title_confidence`
  - `title_decision_trace`
  - `structured_title_candidate_counts`
  - `markdown_consumption_status`
  - `block_semantics_preserved`
  - `block_types`
- `structured_segments_missing[]`：结构化块缺失文档列表（用于快速排查静默回退）
- `marker_tuning`
  - 当前生效参数值
  - `effective_source`（`env` / `runtime` / `default`）
  - `warnings`
- `marker_llm`
  - `use_llm`
  - `llm_service`
  - `configured`
  - `summary_fields`
  - `warnings`
- `fallback_reason` / `fallback_path` / `confidence_note`
  - 供前端直接展示最近一次导入是否走了增强降级，或是否包含按类型受控跳过

## 4. 常见故障

1. `marker unavailable`：Marker 依赖未安装，执行 `pip install marker-pdf`。
2. `marker parse timeout`：增大 `marker_timeout_sec`，或在设置页关闭 Marker 总开关后重试基础解析。
3. 标题被降级为 `Untitled Paper`：说明候选命中黑名单或低于门禁阈值，优先检查 `title_layer`、`title_decision_trace` 与 `structured_title_candidates`。
4. Marker 明明识别了表格/公式但检索里没有体现：检查 `chunks*.jsonl` 的 `content_type/block_type/structure_provenance`，以及 ingest report 中的 `block_semantics_preserved`。
5. markdown 只有标题首行被使用：这是当前预期，`markdown_consumption_status=partial` 用于明确区分“存在但未完全消费”和“本身不存在”。
6. OOM 或吞吐骤降：优先将 `recognition/detector/layout` 调回 `2`，`ocr_error/table_rec` 调回 `1`，`model_dtype=float16`。
7. `effective_source` 长期为 `default`：说明 runtime 配置未保存，或对应环境变量为空/非法，检查 `/api/admin/runtime-overview` 的 `status.reasons`。
8. 保存 Marker LLM service 时提示 provider 字段缺失：检查 `/api/admin/pipeline-config` 返回的 `field_errors`，例如 Vertex 需要 `vertex_project_id`，OpenAI 需要 `openai_api_key` + `openai_model`。

## 4.2 前端排查接口

- `GET /api/admin/runtime-overview`
  - 返回 `marker_tuning`、`marker_llm`、最近一次导入降级摘要和 artifacts 健康计数。
- `GET /api/library/marker-artifacts`
  - 返回 `data/indexes` / `data/processed` 关键产物列表、状态和受控操作元数据。
- `POST /api/library/marker-artifacts/delete`
  - 删除指定产物文件，供前端在确认后执行受控清理。

## 4.1 回退流程

1. 在设置页将 Marker tuning 恢复到 8GB 安全档位并保存。
2. 若仍不稳定，在设置页关闭 Marker 总开关，临时回退到基础解析模式。
3. 执行小批量验证（见第 5 节脚本），确认恢复后再逐步恢复 Marker。

## 5. 灰度与回归脚本

- 灰度开关校验：

```bash
venv/bin/python scripts/validate_marker_gray_release.py --config configs/default.yaml
```

- 小批量灰度重跑（含结果校验）：  
  `scripts/run_marker_gray_batch.sh configs/default.yaml data/samples/gray_batch data/processed/gray_batch runs/marker_gray_batch`

- 增量修复历史标题（按 `paper_id`）：

```bash
venv/bin/python scripts/rebuild_paper_metadata.py \
  --papers data/processed/papers.json \
  --chunks data/processed/chunks.jsonl \
  --paper-id pdf_xxx --paper-id pdf_yyy \
  --rerun-marker-if-missing
```

说明：

- 脚本会优先复用 `papers.json.ingest_metadata.structured_title_candidates`
- 如果缺失且传入 `--rerun-marker-if-missing`，会尝试对原 PDF 安全重跑 Marker
- 如果结构化候选仍不可用，会显式写入 `repair_status=skipped_missing_structured_candidates`

- 前后质量对比（标题修复率 + 检索/回答回归摘要）：

```bash
venv/bin/python scripts/eval_marker_title_regression.py \
  --before-papers reports/before/papers.json \
  --after-papers reports/after/papers.json \
  --before-qa-report reports/before/qa_eval.json \
  --after-qa-report reports/after/qa_eval.json \
  --out reports/marker_title_regression.json
```
