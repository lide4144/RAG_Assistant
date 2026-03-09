## RAG SaaS 工作台 UI/UX 现代化重构验收清单

### Feature 1: 全局布局与语义化状态指示
- [x] 顶部告警条重构为可折叠 Alert，默认仅显示降级文案。
- [x] “查看详情”展开后以结构化列表展示 fallback 参数。
- [x] 文案修复为“前往模型设置”，并右侧对齐。
- [x] 连接状态重构为无边框状态指示（发光圆点 + 文案）。
- [x] 引入全局 `StatusMapper`，页面不再直接输出原始 JSON。

### Feature 2: 知识处理页重构
- [x] 顶部 4 张统计卡使用 `tabular-nums` 与强化数字层级。
- [x] 四阶段状态改为横向步骤条并接入状态映射。
- [x] `not_started/processing/unknown` 映射为语义状态展示。
- [x] Graph Build 日志区终端风格化（深色、等宽、平滑滚动条）。
- [x] Run ID 截断展示、支持 Tooltip 与一键复制图标。

### Feature 3: 模型设置页重构
- [x] Rewrite/Graph Entity 默认继承全局配置并隐藏凭据输入。
- [x] 提供 `独立配置 (Override)` 开关并按需展开输入。
- [x] 移除底部“已保存值/生效值”JSON 回显。
- [x] 字段修改未保存时显示柔和“⚠️ 未保存”徽章。

### Feature 4: 对话问答页重构
- [x] 无历史消息时显示 3-4 个快捷指令卡并可点击发送。
- [x] 顶部模型摘要重构为结构化语义标签。

### 回归验证
- [x] Playwright E2E 通过：15/15。
- [x] 包含移动端关键路径回归：`responsive-layout.spec.ts`。
