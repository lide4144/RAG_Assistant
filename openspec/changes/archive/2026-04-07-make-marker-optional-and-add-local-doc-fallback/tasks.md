## 1. 配置与依赖治理

- [x] 1.1 将 Marker 默认状态调整为关闭，并同步更新后端配置模型与默认配置文件
- [x] 1.2 调整依赖与安装说明，确保本地默认安装路径不再把 Marker 作为启动前提
- [x] 1.3 更新 runtime overview / 配置读写契约，稳定返回 Marker 总开关与当前模式摘要

## 2. 后端本地文档降级逻辑

- [x] 2.1 重构 ingest 解析决策语义，区分 `base_only` 与 `degraded_from_marker`
- [x] 2.2 参考 `example_projects/LightRAG` 的处理方式，建立“扩展名路由 -> 基础解析器 -> 可选增强解析器”的本地处理模型
- [x] 2.3 保持 Marker 启用但失败时的受控降级与可观测字段，避免整批导入中断
- [x] 2.4 为文本类文件补齐基础解析路径，至少覆盖 `txt/md/mdx/html/htm/tex/json/xml/yaml/yml/csv/log/conf/ini/properties/sql`
- [x] 2.5 为 Office 类文件补齐基础解析路径，至少覆盖 `docx/pptx/xlsx`
- [x] 2.6 为 `rtf/odt/epub` 等文档类格式定义首版策略：轻量抽取或受控跳过，并返回可理解提示
- [x] 2.7 清理代码与文档中的 `marker-first` 假设，将描述统一到“基础解析 / 增强解析”

## 3. 前端设置与导入状态

- [x] 3.1 在设置页新增 Marker 总开关，并在关闭时隐藏或降级展示 Marker tuning/LLM 增强配置
- [x] 3.2 在设置页与运行态概览中展示当前模式为 `基础解析` 或 `增强解析`
- [x] 3.3 在导入工作台中区分“基础解析完成”“增强降级完成”“按类型受控跳过”，避免把关闭 Marker 误报为异常

## 4. 规格与文档同步

- [x] 4.1 更新 `marker-pdf-structured-parsing`、`paper-ingestion-pipeline`、`frontend-llm-connection-settings` 等相关规范
- [x] 4.2 更新启动说明与 Marker 运维文档，明确 Marker 为可选增强能力
- [x] 4.3 补充“个人电脑默认使用基础解析”的操作说明与故障排查指南

## 5. 验证

- [x] 5.1 增加后端测试，覆盖多类型文档受理、Marker 默认关闭、显式开启、增强失败降级与按类型跳过路径
- [x] 5.2 增加前端测试，覆盖 Marker 开关保存、模式摘要显示和导入状态映射
- [x] 5.3 验证现有 Marker 成功路径、legacy 基础路径与导入 trace 输出不回归
