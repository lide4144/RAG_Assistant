## 为什么

当前前端界面仍偏向工程调试形态，信息架构分散、视觉一致性不足、关键交互反馈不完整，难以支撑“可持续演进的 SaaS 产品体验”。
随着功能扩展（对话、知识处理、模型配置），需要统一导航、页面职责与设计令牌，降低用户学习成本并提升可用性与产品质感。

## 变更内容

- 新增全局 SaaS 布局框架：左侧沉浸式侧边导航 + 右侧主内容区，并通过路由实现无刷新切页。
- 重构模型设置页：集中管理 Answer/Embedding/Rerank 配置，支持 Provider 下拉联动默认 API Base，API Key 掩码显示与显隐切换，提供“测试并保存”反馈与 Toast 提示。
- 重构知识库构建流水线页：新增顶部统计区（Bento 布局 + 数字动效），强化 Import/Clean/Index/Graph Build 的实时状态指示，并提供 Graph Build 终端风格日志区。
- 重构对话问答页：移除配置噪音，聚焦聊天体验，支持 Markdown（代码高亮/公式），毛玻璃气泡，品牌化空白态，模型未配置时显示可跳转告警。
- 建立统一设计规范：全站汉化术语、Tailwind `slate-50` 背景 + `white` 卡面、Shadcn 简约基础 + Magic 轻动态、全操作统一 Loading 状态。

## 功能 (Capabilities)

### 新增功能
- `frontend-saas-shell-navigation`: 提供全局侧边导航与页面级路由切换能力，统一进入“对话问答/知识处理/模型设置”三大工作区。
- `frontend-chat-focused-experience`: 定义以对话为中心的聊天界面规范，包括空白态、毛玻璃消息气泡、Markdown 渲染与未配置模型告警。
- `frontend-pipeline-ops-dashboard`: 定义知识库构建流水线的统计、阶段状态与任务日志可视化规范。

### 修改功能
- `frontend-llm-connection-settings`: 将现有前端模型连接配置重构为设置中心形态，补充 Provider 联动、密钥显隐与保存反馈等规范。

## 影响

- 受影响代码：`frontend/` 中布局、路由、聊天页、流水线页、设置页与共享 UI 组件。
- 受影响状态管理：前端配置读取/保存流程、流水线状态轮询与任务日志展示。
- 受影响契约：前端对“模型已配置状态”“流水线阶段状态”“任务日志流”的接口消费方式。
- 依赖与样式影响：新增/调整 Magic MCP 相关组件与 Markdown 渲染依赖，统一 Tailwind 设计令牌。
