## 为什么

当前 RAG SaaS 研究助理工作台虽然已经具备聊天、知识处理和模型配置能力，但界面仍然偏向开发者视角：术语生硬、流程反馈不足、会话缺少历史入口，普通中文用户难以快速理解系统状态并建立使用信心。现在补齐这轮前端重构，可以把已有能力包装成更完整、更可用的产品体验。

## 变更内容

- 升级全局 SaaS 视觉语言，统一留白、圆角、阴影、状态条和中文信息层，减少“简陋工具页”观感。
- 全面中文化前端术语，将 `Artifact`、`Rerank`、`Import path healthy` 等机器化表达替换为面向用户的中文文案；保留必要专业词时提供 Tooltip 释义。
- 重构知识处理页，在“处理状态”区域加入可视化进度反馈，明确展示导入、清洗、索引、图构建四阶段进度。
- 重构聊天页布局，新增历史会话侧栏，支持“新建对话”、删除旧会话与按时间分组浏览历史记录。
- 重构模型设置页，将核心模型切换升级为直接可操作的 Select 控件，并将底层 Marker Runtime Tuning 参数收纳到默认折叠的“高级模型调优”面板。
- 本次变更不引入破坏性 API（无 **BREAKING** 项）。

## 功能 (Capabilities)

### 新增功能

<!-- 无新增独立 capability；本次主要修改既有前端规范。 -->

### 修改功能

- `frontend-saas-shell-navigation`: 升级全局壳层视觉层级、状态展示和中文信息架构。
- `frontend-chat-focused-experience`: 为聊天体验增加历史会话侧栏、中文引导和更清晰的对话布局。
- `frontend-pipeline-ops-dashboard`: 为知识处理页增加阶段进度反馈、更加直观的导入和状态呈现。
- `frontend-llm-connection-settings`: 将核心模型展示改为可直接选择的配置控件，并优化中文说明。
- `frontend-stage-llm-settings`: 将晦涩底层参数折叠到高级面板，并增加 Tooltip 解释。
- `frontend-marker-artifact-management`: 将生成文件管理区的文案和状态表达改为中文友好版本。

## 影响

- 前端代码：`frontend/components/app-shell.tsx`、`frontend/components/chat-shell.tsx`、`frontend/components/PipelineWorkbenchPanel.tsx`、`frontend/components/settings-shell.tsx`、`frontend/components/marker-artifact-panel.tsx`、`frontend/app/globals.css`
- 前端规范：需要为上述 6 个既有 capability 编写增量规范
- 测试与验收：需要覆盖聊天历史侧栏、知识处理阶段进度、模型设置折叠高级参数和中文化文案
