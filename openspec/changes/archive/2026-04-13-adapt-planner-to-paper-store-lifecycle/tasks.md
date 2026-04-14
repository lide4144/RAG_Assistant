## 1. Planner Runtime 论文状态集成

- [x] 1.1 在 `app/planner_runtime.py` 中导入 `paper_store` 模块
- [x] 1.2 修改论文可用性检查逻辑，从 SQLite 查询而非文件读取
- [x] 1.3 添加论文状态缓存机制，减少重复数据库查询
- [x] 1.4 实现数据库不可用时回退到文件读取的降级逻辑

## 2. Planner Policy 论文状态决策

- [x] 2.1 在 `app/planner_policy.py` 中添加基于论文状态的过滤规则
- [x] 2.2 实现 `ready` 论文筛选逻辑
- [x] 2.3 实现 `failed` 论文识别与处理逻辑
- [x] 2.4 实现 `rebuild_pending` 论文识别逻辑

## 3. Catalog Lookup 工具更新

- [x] 3.1 修改 catalog_lookup 工具实现，使其从 SQLite 查询
- [x] 3.2 添加论文状态过滤参数支持
- [x] 3.3 更新工具返回结果，包含论文生命周期状态

## 4. Action Plan 论文依赖支持

- [x] 4.1 在 action plan 格式中增加 `paper_dependencies` 字段
- [x] 4.2 修改执行器逻辑，支持论文状态依赖检查
- [x] 4.3 实现依赖不满足时的 fallback 处理

## 5. API 与契约更新

- [x] 5.1 更新 Planner API 文档，说明论文状态感知能力
- [x] 5.2 确保现有 API 契约保持不变
- [x] 5.3 添加论文状态相关的观测字段

## 6. 测试与验证

- [x] 6.1 为 Planner 论文状态查询编写单元测试
- [x] 6.2 验证 catalog_lookup 工具的状态过滤功能
- [x] 6.3 验证论文依赖声明的执行流程
- [x] 6.4 测试数据库故障时的降级路径

## 7. 文档与迁移

- [x] 7.1 更新 Planner 开发文档，说明论文状态集成
- [x] 7.2 编写迁移指南，说明如何启用论文状态感知
- [x] 7.3 更新配置文档，说明相关配置选项
