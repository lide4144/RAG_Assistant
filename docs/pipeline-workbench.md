# Pipeline Workbench 与任务进度

## 概览

本项目新增了 `Pipeline Workbench`，用于承载图构建等长耗时任务的可见性与控制。

- 入口：`/chat` 页面顶部 `Pipeline` 选项
- 当前覆盖任务：`graph_build`
- 任务状态：`idle / queued / running / succeeded / failed / cancelled`

## Phase 1 验收（图构建可见性）

验收项：
- Kernel 提供图构建任务启动接口：`POST /api/tasks/graph-build/start`
- Kernel 提供任务状态查询接口：`GET /api/tasks/{task_id}`
- 图构建阶段进度可见，实体抽取阶段提供 `processed/total`
- 失败时返回结构化错误（失败阶段、错误信息、恢复建议）

本地验证记录：
- `PYTHONPATH=. venv/bin/pytest -q tests/test_kernel_api_contract.py` 通过
- `npm --prefix gateway test` 通过
- `npm --prefix gateway run build` 通过

发布步骤（Phase 1）：
1. 启动 Kernel 与 Gateway。
2. 打开 `/chat`，切到 `Pipeline`。
3. 点击“启动图构建”，确认状态从 `queued` 到 `running`，并可见阶段和进度。
4. 完成后确认状态 `succeeded`，失败时确认错误摘要与恢复提示可见。

回滚步骤（Phase 1）：
1. 回滚 Kernel 中 `/api/tasks/*` 接口改动。
2. 回滚 Gateway 任务事件转发逻辑（保留 chat 四事件）。
3. 前端隐藏 `Pipeline` 区域或降级为只读提示。

## Phase 2 验收（Workbench 入口与流程引导）

验收项：
- 工作台存在 `Chat / Pipeline` 一级入口
- Pipeline 中存在任务中心（状态、阶段、进度条、耗时、更新时间）
- 存在“进入 Chat 验证”流转按钮
- 展示“最近导入结果”结构化面板（新增、跳过、失败、失败原因）
- 失败任务可“重试”，运行中任务可“取消”
- Pipeline UI 与逻辑已从 `chat-shell.tsx` 拆分

本地验证记录：
- `npm --prefix frontend run build` 通过
- 前端新增交互测试文件：`frontend/tests/pipeline-workbench.spec.ts`

使用说明：
1. 在 `/chat` 切换到 `Pipeline`。
2. 点击“启动图构建”观察任务状态变化。
3. 构建完成后点击“进入 Chat 验证”进行问答验证。

## 验收整改补充（2026-03-06）

### 新增/调整能力

- 导入结果接口：`GET /api/library/import-latest`
  - 返回字段：`added`、`skipped`、`failed`、`failure_reasons`
- 任务取消接口：`POST /api/tasks/{task_id}/cancel`
  - 仅对 `queued/running` 任务生效，终态任务返回 `cancelled=false`
- 前端任务按钮策略：
  - `failed` 状态显示“重试 ⟳”
  - `running` 状态显示“取消”
  - 默认显示“启动图构建”
- 组件重构：
  - 新增 `frontend/components/PipelineWorkbenchPanel.tsx`
  - 新增 `frontend/components/usePipelineWorkbench.ts`
  - `chat-shell.tsx` 保留聊天主流程与页面编排

### 回归验证日志

- `cd frontend && npx tsc --noEmit` 通过
- `cd gateway && npm run build` 通过
- `venv/bin/python -m pytest -q tests/test_kernel_api_contract.py` 通过（`7 passed, 3 subtests passed`）
- `cd frontend && npx playwright test tests/pipeline-workbench.spec.ts` 通过（`1 passed`）
