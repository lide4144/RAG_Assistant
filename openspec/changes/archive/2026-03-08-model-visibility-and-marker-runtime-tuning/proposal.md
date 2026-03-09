## 为什么

当前“模型设置”页面主要承担编辑功能，但业务页面（对话/知识处理）缺少“当前生效模型与运行档位”的可见性。用户在排障时无法快速确认：当前到底在用哪一套模型、哪些 stage 缺失、Marker/Surya 是否处于高显存档位。

在 8GB 显存设备上，Marker/Surya 的批大小和 dtype 直接影响吞吐与稳定性。仅靠环境变量手工调参不透明、不可回显、不可追溯，难以在团队内复用。

## 变更内容

- 将“模型配置”从单页编辑能力升级为“全局可见 + 页面可感知”的运行态信息能力。
- 在应用壳层新增只读“模型运行状态条”，跨页面持续显示关键 stage 的当前模型与状态等级（READY/DEGRADED/BLOCKED/ERROR）。
- 在聊天页增加“当前会话模型摘要”，明确 Answer/Rerank/Rewrite 生效模型，不再只显示“已配置/未配置”布尔态。
- 在设置页增加“当前生效配置概览”，将“设置表单”和“生效状态”并列，避免配置后仍需跳转确认。
- 新增可持久化的 Marker 运行档位配置（batch size / dtype），支持前端配置与后端校验，并提供默认安全档位。

## 功能 (Capabilities)

### 新增功能
- `pipeline-runtime-config-persistence`: 定义与持久化 pipeline 运行态参数（含 Marker/Surya 显存相关参数），并提供管理 API。

### 修改功能
- `frontend-saas-shell-navigation`: 导航壳层新增全局模型运行状态展示。
- `frontend-chat-focused-experience`: 聊天页展示当前生效模型摘要与状态引导。
- `frontend-llm-connection-settings`: 设置页新增“生效配置可视化”与 pipeline/marker 运行档位设置区。
- `marker-pdf-structured-parsing`: 明确可配置的批处理与 dtype 运行参数及其安全边界。

## 影响

- 前端：`AppShell`、`/chat`、`/settings` 页面信息架构与状态同步机制。
- 后端：新增 pipeline runtime 配置读写接口；新增运行态概览接口（聚合 LLM 与 pipeline 运行配置）。
- 配置：新增 runtime 持久化文件（或扩展现有 runtime 文件）用于记录 marker tuning 参数。
- 运维：补充 8GB 显存建议档位、异常回退建议与排障路径。
