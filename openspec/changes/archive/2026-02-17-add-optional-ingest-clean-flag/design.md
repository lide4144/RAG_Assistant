## 上下文

当前项目已有两条可独立执行的流程：
- `python -m app.ingest --input ... --out ...` 生成 `chunks.jsonl` / `papers.json`
- `python -m app.clean_chunks --input ... --out ...` 生成 `chunks_clean.jsonl`

用户希望保留独立清洗能力，同时给 ingest 增加可选快捷联动，避免批处理时漏跑清洗步骤。约束是：联动清洗失败不能破坏 ingest 主产物和主流程语义。

## 目标 / 非目标

**目标：**
- 为 ingest 增加可选参数（`--clean` 或 `--clean-after-ingest`）触发清洗。
- ingest 成功后执行清洗；清洗失败只记录错误，不回滚 `chunks.jsonl/papers.json`。
- 运行报告中记录清洗启用状态、输出路径、失败信息。
- 保持 `app.clean_chunks` 独立命令可单独重跑。

**非目标：**
- 不将清洗变成 ingest 默认必跑步骤。
- 不重构清洗规则本身。
- 不引入新的工作流编排器。

## 决策

1. 采用“默认解耦，显式联动”模式  
- 方案：新增 `--clean`（或同义参数）默认 `False`。  
- 原因：保持向后兼容，避免改变现有 ingest 运行时长与失败面。  
- 备选：默认开启清洗；会引入破坏性行为变化。

2. 联动调用复用现有 API  
- 方案：在 ingest 中直接调用 `run_clean_chunks(chunks_file, out/chunks_clean.jsonl)`。  
- 原因：避免重复实现、保证独立命令与联动行为一致。  
- 备选：subprocess 调用 `python -m app.clean_chunks`；调试与错误处理更复杂。

3. 失败隔离  
- 方案：清洗异常被捕获并写入 report 字段，不改变 ingest 已成功写出的主产物。  
- 原因：满足“失败不影响 chunks.jsonl 产出”的业务要求。  
- 备选：清洗失败返回非零；会放大非关键步骤故障影响。

4. 可观测性最小字段  
- 方案：在 `ingest_report.json` 增加 `clean_enabled/clean_output/clean_success/clean_error`。  
- 原因：不改动现有报告主结构即可回放排障。  
- 备选：写独立 clean report；对当前里程碑收益有限。

## 风险 / 权衡

- [联动增加 ingest 时长] -> 默认关闭，仅用户显式开启。
- [清洗失败被忽略造成误判] -> 在报告与 stderr 输出显式标识失败。
- [参数命名歧义] -> 仅保留一个主参数并在 help 写明行为。
- [双路径行为漂移] -> 强制复用 `run_clean_chunks`，避免逻辑分叉。

## 迁移计划

1. 在 `app.ingest` 增加 `--clean` 参数并写入 report 字段。
2. ingest 产出主文件后，在参数开启时调用 `run_clean_chunks`。
3. 为联动成功/失败/未开启三种路径补充测试。
4. 更新文档示例命令。

回滚策略：
- 删除 `--clean` 调用分支即可恢复原 ingest 行为；独立清洗命令不受影响。

## 开放问题

- 参数最终命名采用 `--clean` 还是 `--clean-after-ingest`（建议 `--clean` + help 说明）。
- 清洗失败是否需要额外写入 `runs/...` trace（当前仅写 ingest_report）。
