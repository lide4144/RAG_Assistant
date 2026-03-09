## 1. Runtime 契约与持久化

- [x] 1.1 扩展 pipeline runtime 配置模型，新增 `marker_llm` 结构并支持 `use_llm`、`llm_service` 与 provider 专属字段的保存和读取
- [x] 1.2 为不同 `llm_service` 实现字段级校验与脱敏摘要返回，覆盖 `Gemini`、`Google Vertex`、`Ollama`、`Claude`、`OpenAI`、`Azure OpenAI`
- [x] 1.3 扩展 runtime overview / ingest 报告契约，加入 Marker LLM 摘要、降级状态、降级原因与产物健康摘要

## 2. Marker 导入与产物管理后端

- [x] 2.1 在 Marker 导入链路中落地可审计的降级逻辑，确保 LLM 失败但基础解析可继续时返回结构化 fallback 元数据
- [x] 2.2 提供 `data/indexes` 与 `data/processed` 核心产物的列表/详情接口，返回类型、更新时间、健康状态与关联阶段
- [x] 2.3 为产物管理接口补充受控操作能力，至少覆盖复制路径、重建入口和删除前风险确认所需的元数据

## 3. 前端设置与工作台体验

- [x] 3.1 在设置页新增 Marker LLM service 配置表单，按 provider 动态展示字段并保留现有 marker tuning 保存行为
- [x] 3.2 在设置页与 runtime overview 中展示 Marker LLM 生效摘要、字段来源、保存状态和字段级错误反馈
- [x] 3.3 在知识处理页加入导入降级状态卡、风险摘要和 `degraded`/`failed_with_fallback` 阶段映射
- [x] 3.4 使用 Magic MCP 组件增强降级提示区、状态卡和产物管理面板的视觉表现，并整合到现有页面结构
- [x] 3.5 新增 Marker 产物管理视图或面板，展示 `Index` 与 `processed` 产物列表、健康状态、建议动作和受控操作入口

## 4. 验证与回归

- [x] 4.1 为 runtime config 与导入状态接口补充单元/集成测试，覆盖 provider 缺字段、脱敏回显与降级元数据返回
- [x] 4.2 为设置页与知识处理页补充 Playwright 用例，覆盖 Marker LLM 配置保存、降级提示展示和产物管理交互
- [x] 4.3 验证现有 Marker tuning、runtime overview 与流水线状态展示不回归，并更新必要文档或操作说明
