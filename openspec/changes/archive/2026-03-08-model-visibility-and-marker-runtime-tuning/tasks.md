## 1. 后端运行态配置与聚合接口

- [x] 1.1 新增 pipeline runtime 配置结构与持久化读写（含默认值与范围校验）
- [x] 1.2 新增 `/api/admin/pipeline-config` 读写接口并返回脱敏/规范化字段
- [x] 1.3 新增 `/api/admin/runtime-overview` 聚合接口，输出状态等级与原因
- [x] 1.4 明确环境变量与 runtime 配置的优先级，并在概览中输出 `effective_source`

## 2. 前端可视化

- [x] 2.1 在 `AppShell` 增加全局模型运行状态条（摘要 + 跳转入口）
- [x] 2.2 在聊天页增加“当前会话模型摘要”卡片并替代单一布尔提示
- [x] 2.3 在设置页增加“当前生效配置概览”区，区分“已保存值”与“生效值”
- [x] 2.4 在设置页增加 Marker tuning 表单（batch size / dtype）

## 3. 测试与文档

- [x] 3.1 补充 API 合约测试：pipeline-config 与 runtime-overview
- [x] 3.2 补充前端 E2E：全局状态条、聊天摘要、设置页回显与保存
- [x] 3.3 更新运维文档：8GB 显存推荐档位、异常症状与回退流程
