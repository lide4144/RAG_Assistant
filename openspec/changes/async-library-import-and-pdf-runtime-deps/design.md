## 概览

本次变更追认两类已经实现的调整：

1. 将浏览器上传导入重构为后台任务，解决批量上传时单请求过长的问题。
2. 将 PDF 解析所需的 `PyMuPDF` 明确纳入运行时依赖，避免部署环境差异导致的导入失败。

## 后端设计

### 文件接收与暂存

- `/api/library/import` 在解析 multipart 表单后，不再直接调用 `run_import_workflow`。
- 服务端先将上传文件按安全文件名写入 `data/raw/_api_upload_staging/<task_id>/`。
- 文件暂存成功后立即创建 `library_import` 任务并返回 `task_id`。

### 后台任务执行

- 复用现有 `_TASKS`、`_TASK_CANCEL_EVENTS` 与 `/api/tasks/{task_id}` 查询机制。
- 新增 `task_kind=library_import`，状态机沿用 `queued/running/succeeded/failed/cancelled`。
- 后台线程调用 `run_import_workflow(uploaded_files=..., topic=..., progress_callback=...)`。
- 任务结束后写入最新 pipeline status，并清理临时暂存目录。

### 失败语义

- 如果同类导入任务已在运行，则新请求复用现有活动任务并返回 `accepted=false`。
- 如果文件暂存失败，则接口直接返回结构化错误，不进入后台任务。
- 如果导入流程本身失败，则由任务终态和 `error/recovery` 字段反馈给前端，而不是让浏览器只看到网络错误。

## 前端设计

### 导入提交

- 提交文件或目录后，前端读取接口返回的 `task_id/task_state`，立即显示“任务已提交”。
- 不再假设导入请求返回时导入已经完成。

### 状态轮询

- 当存在活动 `importTaskId` 时，前端轮询 `/api/tasks/{task_id}`。
- 轮询期间用任务 `progress.message` 或 `error.message` 更新导入提示。
- 任务进入终态后，自动刷新：
  - `/api/library/import-latest`
  - `/api/library/import-history`
  - `/api/library/marker-artifacts`

## 依赖与测试设计

### 运行时依赖

- `requirements.txt` 必须显式包含 `pymupdf`，确保 `app/parser.py` 中的 `fitz` 导入在部署镜像中可用。
- 依赖清单更新后，部署侧必须在重建镜像后执行一次最小 PDF 导入烟测，验证全新镜像可以完成至少一篇 PDF 的入库而不因缺少 `PyMuPDF` 失败。

### Marker 线程兼容

- 浏览器上传改为后台线程执行后，Marker 解析中的超时守卫不能继续无条件使用 `signal.SIGALRM`。
- `signal` 超时只允许在主线程启用；后台线程必须跳过信号注册，避免触发 `signal only works in main thread of the main interpreter` 并导致错误降级。
- 线程兼容修复属于异步导入设计的直接配套项，因为后台导入任务会复用 Marker 解析链路。

### 测试

- 后端契约测试覆盖：
  - 导入任务后台执行
  - 已有活动导入任务时复用现有 `task_id`
  - 上传接口立即返回已受理任务
- Marker 解析测试覆盖：
  - 非主线程下超时守卫不会注册 `signal`
- 前端测试修复：
  - 为设置页测试状态对象补充显式类型，避免 TypeScript 过窄推断导致 `tsc` 失败。
- 前端工作台测试覆盖：
  - 导入提交返回 `task_id`
  - `/api/tasks/{task_id}` 轮询
  - 任务终态后自动刷新导入结果、历史与产物面板
