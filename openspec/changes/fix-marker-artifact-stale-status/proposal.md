## 为什么

当前 Marker 产物管理面板会把“最近一次运行时间”作为单一全局锚点来判断所有产物是否过期，导致同一轮导入中较早生成的 `chunks`、`papers`、`bm25` 等文件在导入成功后仍被标记为“产物早于最近一次运行”。这会误导管理员，把正常产物误判成待更新状态，并削弱运行态概览的可信度。

## 变更内容

- 调整 Marker 产物健康判定逻辑，使产物按其所属阶段（Import、Clean、Index、Graph Build）与对应阶段的完成时间进行比较，而不是统一对比单一全局更新时间。
- 为导入结果与最新 pipeline 状态补充阶段级 `updated_at` 元数据，确保 `import-latest`、`marker-artifacts` 与 runtime overview 使用一致的阶段时间语义。
- 更新相关契约测试，覆盖“同轮导入不误报 stale”与“跨轮旧产物仍正确报 stale”两类行为。

## 功能 (Capabilities)

### 新增功能

### 修改功能
- `frontend-marker-artifact-management`: 修正“待更新”状态的判定语义，使产物仅在早于所属阶段最近完成时间时才显示为过期。
- `pipeline-runtime-config-persistence`: 扩展运行态概览与最新状态持久化输出，补充阶段级更新时间供产物管理与状态聚合复用。

## 影响

- `app/library.py` 中导入工作流返回结构，需要补充导入、清洗、索引阶段的完成时间。
- `app/kernel_api.py` 中产物健康判定、最新导入结果聚合、pipeline 状态持久化与读取逻辑。
- `tests/test_kernel_api_contract.py` 以及依赖该接口语义的前端/后端契约测试。
