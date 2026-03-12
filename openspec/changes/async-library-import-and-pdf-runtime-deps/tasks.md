## 1. 后端异步导入任务化

- [x] 1.1 将 `library_import` 纳入统一任务状态机并扩展任务类型定义
- [x] 1.2 为浏览器上传新增服务端暂存目录，先落盘再启动后台导入任务
- [x] 1.3 让 `/api/library/import` 与 `/api/library/import-from-dir` 返回 `task_id/task_state/accepted`
- [x] 1.4 在后台导入线程结束后写入最新 pipeline status 并清理暂存目录
- [x] 1.5 让取消任务接口对 `library_import` 复用统一取消语义

## 2. 前端导入面板适配

- [x] 2.1 调整导入提交逻辑，改为处理“任务已提交”响应而非同步完成响应
- [x] 2.2 增加导入任务轮询并在终态后刷新导入结果、历史与产物面板
- [x] 2.3 保持页面离开保护逻辑覆盖导入任务运行中状态

## 3. 依赖与测试修复

- [x] 3.1 为导入后台执行与立即受理增加后端契约测试
- [x] 3.2 修复 `llm-settings-panel.spec.ts` 中过窄类型推断导致的 TypeScript 报错
- [x] 3.3 将 `pymupdf` 加入运行时依赖清单
- [x] 3.4 为重复提交导入任务增加“复用活动任务”回归测试
- [x] 3.5 修复 Marker 超时守卫在线程导入中的主线程兼容问题，并补充对应测试
- [x] 3.6 为前端导入任务轮询与终态刷新增加自动化测试
- [x] 3.7 在依赖说明中补充“重建镜像后执行最小 PDF 导入烟测”的部署验证要求

## 4. 验证

- [x] 4.1 `venv/bin/python -m pytest -q tests/test_kernel_api_contract.py`
- [x] 4.2 `npx playwright test tests/pipeline-workbench.spec.ts`
- [x] 4.3 `npx tsc --noEmit`
- [x] 4.4 `venv/bin/python -m pytest -q tests/test_marker_parser.py tests/test_marker_ingestion.py tests/test_kernel_api_contract.py`
