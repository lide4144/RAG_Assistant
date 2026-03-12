## 上下文

当前 Marker 产物健康状态由 `app/kernel_api.py` 统一读取文件 `mtime`，再与一次导入结果的单一 `updated_at` 比较。这个 `updated_at` 实际来自 `ingest_report.json` 或 `pipeline_status_latest.json` 的最后写入时间，天然晚于同轮导入中较早生成的 import / clean / index 产物。因此，即使本轮导入已经成功并生成了最新文件，产物管理面板仍会把这些文件标记为 stale。

这次变更横跨 `app/library.py` 的导入工作流返回结构、`app/kernel_api.py` 的状态聚合与持久化逻辑，以及相关契约测试。目标是在不改动前端展示协议主体的前提下，修正后台对“待更新”状态的判定口径。

## 目标 / 非目标

**目标：**
- 为 Import、Clean、Index 阶段生成可复用的阶段级 `updated_at` 元数据。
- 让 Marker 产物按 `related_stage` 与对应阶段时间比较，仅在确实早于该阶段最近完成时间时标记为 stale。
- 保持 `import-latest`、`marker-artifacts` 与 runtime overview 的阶段时间语义一致。
- 用契约测试覆盖“本轮不误报 stale、跨轮旧产物仍报 stale”。

**非目标：**
- 不重做前端卡片文案、视觉样式或交互结构。
- 不引入新的产物分组、操作类型或新的后台接口。
- 不为每个单独文件增加独立数据库记录或额外持久化层。

## 决策

### 决策 1：以阶段级时间替代单一全局时间作为 stale 锚点
- 方案：在导入工作流结果中补充 `import_stage.updated_at`、`clean_stage.updated_at`、`index_stage.updated_at`，并在 `kernel_api` 中生成 `stage_updated_at` 映射。产物健康检查时，按 `related_stage` 读取对应锚点。
- 原因：当前误报的根因不是文件时间错误，而是比较基准过粗。按阶段对齐可以直接消除同轮误报，同时不牺牲“旧 index/graph 文件”告警能力。
- 备选：
  - 保留全局时间并增加几秒容差：实现简单，但仍然依赖猜测窗口，无法保证慢机、锁等待或异步写入场景下的正确性。
  - 完全取消 stale 判定：会丢失真实的跨轮旧产物告警能力，回退过度。

### 决策 2：沿用现有 JSON 状态持久化文件，扩展阶段时间字段
- 方案：在 `pipeline_status_latest.json` 中新增 `stage_updated_at`，并在 `_load_latest_import_result` 中优先合并该字段，必要时再回退到旧的 `updated_at`。
- 原因：现有状态文件已经是运行态概览和 import-latest 的公共来源，扩展它可以保持兼容并减少额外 IO 设计。
- 备选：
  - 创建新的阶段时间状态文件：结构更纯，但增加读取路径和一致性负担。
  - 仅依赖 `ingest_report.json`：无法覆盖后续状态聚合或兼容历史运行态写入。

### 决策 3：通过接口级契约测试验证时间语义
- 方案：在 `tests/test_kernel_api_contract.py` 中补充两类测试：一类验证 `import-latest` 返回阶段时间；一类验证 `_build_marker_artifacts` 按阶段时间判断 stale。
- 原因：问题出在接口聚合层而不是底层 ingest 算法，契约测试最能稳定覆盖回归面。
- 备选：
  - 只依赖前端 Playwright：覆盖面偏 UI，排查成本更高，且对时间语义的断言不够集中。

## 风险 / 权衡

- [历史状态文件不含 `stage_updated_at`] → 在 `_collect_stage_updated_at` 中保留回退逻辑，用旧 `updated_at` 填充 import/clean/index，避免读取旧数据时报错。
- [导入失败路径未返回完整阶段时间] → 仅在成功完成对应阶段时写入该阶段时间；缺失时维持 non-stale 或旧逻辑回退，不引入新的错误状态。
- [阶段时间与文件 `mtime` 同秒写入导致边界判断敏感] → 继续使用严格“小于”比较，等于同秒视为健康，避免再次出现同轮误报。
