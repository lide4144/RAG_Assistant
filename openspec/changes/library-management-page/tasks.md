## 1. 后端 API 实现

- [x] 1.1 在 `app/kernel_api.py` 中新增 `POST /api/library/papers/bulk-delete` 端点
- [x] 1.2 实现 `bulk_delete_papers` 函数，循环调用 `_orchestrate_paper_delete`
- [x] 1.3 定义 `BulkDeleteRequest` 和 `BulkDeleteResponse` 模型
- [ ] 1.4 测试批量删除 API（单篇成功、多篇成功、部分失败场景）

## 2. 前端类型定义

- [x] 2.1 创建 `frontend/types/library.ts`，定义 `Paper` 接口
- [x] 2.2 定义 `Filters`、`Pagination`、`BulkOperationResult` 等类型
- [x] 2.3 定义状态样式映射常量 `statusStyles`

## 3. API 封装层

- [x] 2.1 创建 `frontend/lib/library-api.ts`
- [x] 2.2 实现 `listPapers` 函数（支持搜索、筛选参数）
- [x] 2.3 实现 `deletePaper`、`rebuildPaper`、`retryPaper` 单篇操作函数
- [x] 2.4 实现 `bulkDeletePapers`、`bulkRebuildPapers` 批量操作函数
- [x] 2.5 实现 `getVectorBackendState` 获取向量后端状态函数

## 4. 轮询 Hook

- [x] 3.1 创建 `frontend/lib/use-papers-poll.ts`
- [x] 3.2 实现 10 秒间隔的轮询逻辑
- [x] 3.3 实现页面隐藏时暂停轮询功能
- [x] 3.4 实现手动刷新触发器

## 5. 组件开发 - 基础组件

- [x] 4.1 创建 `frontend/components/paper-card.tsx`
- [x] 4.2 实现论文卡片 UI（标题、状态、专题、导入时间、复选框）
- [x] 4.3 实现状态样式动态切换
- [x] 4.4 创建 `frontend/components/paper-list.tsx`
- [x] 4.5 实现卡片列表容器和分页控件

## 6. 组件开发 - 筛选和统计

- [x] 5.1 创建 `frontend/components/paper-filters.tsx`
- [x] 5.2 实现搜索框（300ms 防抖）
- [x] 5.3 实现状态下拉筛选器
- [x] 5.4 实现专题下拉筛选器
- [x] 5.5 创建 `frontend/components/library-stats.tsx`
- [x] 5.6 实现统计概览（总数、就绪、失败、处理中）
- [x] 5.7 实现专题分布展示
- [x] 5.8 实现向量后端状态显示

## 7. 组件开发 - 详情和批量操作

- [x] 6.1 创建 `frontend/components/paper-detail-modal.tsx`
- [x] 6.2 实现论文详情弹窗（基本信息 + 处理阶段状态）
- [x] 6.3 创建 `frontend/components/paper-bulk-toolbar.tsx`
- [x] 6.4 实现批量操作工具栏（已选数量、批量删除、批量重建、清空选择）

## 8. 主容器组件

- [x] 7.1 创建 `frontend/components/library-shell.tsx`
- [x] 7.2 实现状态管理（papers、selectedIds、filters、pagination）
- [x] 7.3 集成筛选逻辑（搜索、状态、专题组合过滤）
- [x] 7.4 集成客户端分页逻辑
- [x] 7.5 实现全选/取消全选逻辑
- [x] 7.6 集成轮询 Hook

## 9. 页面路由

- [x] 8.1 创建 `frontend/app/library/page.tsx`
- [x] 8.2 集成 LibraryShell 组件
- [x] 8.3 添加页面元数据（title、description）

## 10. 导航集成

- [x] 9.1 修改 `frontend/components/app-shell.tsx`
- [x] 9.2 在导航栏添加 "知识库" 入口（位于 "知识处理" 和 "模型设置" 之间）
- [x] 9.3 使用 Books/Library 图标

## 11. 交互完善

- [x] 10.1 实现删除确认对话框
- [x] 10.2 实现批量删除确认对话框（显示论文列表摘要）
- [x] 10.3 实现重建确认对话框
- [x] 10.4 集成 sonner toast 提示
- [x] 10.5 实现操作后的列表自动刷新

## 12. 测试和优化

- [ ] 11.1 测试搜索功能（关键词匹配标题和来源）
- [ ] 11.2 测试筛选组合（状态 + 专题 + 搜索）
- [ ] 11.3 测试分页功能
- [ ] 11.4 测试批量选择（单选、全选、取消）
- [ ] 11.5 测试批量操作（删除、重建）
- [ ] 11.6 测试轮询刷新（页面可见/隐藏切换）
- [ ] 11.7 响应式布局测试（移动端适配）
