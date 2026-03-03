## 为什么

当前 `ingest` 与 `clean_chunks` 只能分两条命令执行，批处理时操作成本高，且容易漏跑清洗步骤。需要在保留解耦能力的同时提供一条可选快捷路径，让入库成功后可自动触发清洗。

## 变更内容

- 为 `python -m app.ingest` 增加可选参数（例如 `--clean` 或 `--clean-after-ingest`）。
- 当参数开启且 ingest 成功时，自动调用 `run_clean_chunks(...)`，生成 `chunks_clean.jsonl`。
- 若清洗失败，不得影响 `chunks.jsonl` / `papers.json` 的成功产出与 ingest 主流程返回语义。
- 在运行报告中记录清洗是否启用、清洗输出路径、清洗错误（如有）。
- 保持 `python -m app.clean_chunks` 独立命令可继续单独运行。

## 功能 (Capabilities)

### 新增功能

### 修改功能
- `paper-ingestion-pipeline`: 修改 ingest 命令行为，支持可选联动清洗步骤且保证主流程兼容。
- `pipeline-development-conventions`: 修改运行可复现约定，增加 ingest 联动清洗的运行日志字段与错误处理约束。

## 影响

- 代码影响：`app/ingest.py`、`app/clean_chunks.py`（接口复用）、报告写入逻辑。
- 测试影响：新增 ingest+clean 联动测试、清洗失败不影响主产物测试。
- 运行影响：默认行为不变；仅在显式参数开启时执行自动清洗。
