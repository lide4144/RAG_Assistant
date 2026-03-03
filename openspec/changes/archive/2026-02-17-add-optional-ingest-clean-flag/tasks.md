## 1. ingest 参数与调用链

- [x] 1.1 在 `app/ingest.py` 增加可选参数 `--clean`（或等效命名），默认关闭
- [x] 1.2 当 ingest 主流程成功且参数开启时，调用 `run_clean_chunks(chunks_file, out/chunks_clean.jsonl)`
- [x] 1.3 保持 `python -m app.clean_chunks` 独立命令可单独执行，不与 ingest 强耦合

## 2. 失败隔离与报告字段

- [x] 2.1 清洗步骤异常时捕获错误，不回滚已生成的 `chunks.jsonl` 与 `papers.json`
- [x] 2.2 在 ingest report 增加字段：`clean_enabled`、`clean_output`、`clean_success`、`clean_error`
- [x] 2.3 在 CLI 输出中增加清洗阶段状态提示（成功/失败）

## 3. 测试与回归

- [x] 3.1 新增联动成功测试：开启 `--clean` 后生成 `chunks_clean.jsonl`
- [x] 3.2 新增联动失败测试：模拟清洗失败时 ingest 仍保留主产物并返回主流程成功语义
- [x] 3.3 新增默认行为测试：未开启参数时不触发清洗，兼容现有 ingest 行为
- [x] 3.4 运行 ingest + clean 相关测试并更新文档命令示例
