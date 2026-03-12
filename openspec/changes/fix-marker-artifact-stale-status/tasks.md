## 1. 阶段时间建模

- [x] 1.1 在 `app/library.py` 的导入工作流结果中补充 `import_stage.updated_at`、`clean_stage.updated_at` 与 `index_stage.updated_at`
- [x] 1.2 在 `app/kernel_api.py` 中增加阶段时间收集与解析逻辑，并将其写入最新 pipeline 状态持久化文件

## 2. 产物 stale 判定修复

- [x] 2.1 调整 Marker 产物健康检查逻辑，使其按 `related_stage` 对比对应阶段的最近完成时间，而不是单一全局更新时间
- [x] 2.2 更新 `import-latest`、`marker-artifacts` 与 pipeline stage 聚合输出，确保阶段时间与产物状态语义一致

## 3. 回归验证

- [x] 3.1 为最新导入结果补充契约测试，验证接口返回阶段级 `updated_at`
- [x] 3.2 为 Marker 产物状态补充契约测试，验证同轮导入不误报 stale 且跨轮旧产物仍会报 stale
