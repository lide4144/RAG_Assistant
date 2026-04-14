## 上下文

### 当前状态

系统已有完整的后端论文管理能力（SQLite 数据库），但前端缺少专门的知识库管理界面：
- **后端 API**: 已存在单篇删除、重建、重试 API，但缺少批量删除
- **前端**: Pipeline 页面专注于处理流程，不适合承载论文管理
- **数据存储**: 已完全迁移到 SQLite（paper_store），JSON 文件仅作兼容导出

### 约束条件

- **UI 框架**: Next.js + React + Tailwind CSS + Lucide Icons
- **状态管理**: React hooks（useState, useEffect），无全局状态库
- **API 调用**: fetchAdminJson 封装函数
- **轮询模式**: setInterval，已有 AppShell（15s）、TaskCenter（5s）参考实现
- **分页**: 客户端分页（后端返回全量数据，前端分页展示）

## 目标 / 非目标

**目标：**
1. 创建独立的 `/library` 页面用于知识库管理
2. 实现 Card 视图的论文列表展示
3. 支持搜索、状态筛选、专题过滤功能
4. 支持单篇论文的查看、删除、重建、重试操作
5. 支持批量选择和批量操作（删除、重建）
6. 实现 10 秒间隔的实时数据刷新
7. 新增后端批量删除 API

**非目标：**
- 后端分页（当前 API 返回全量数据）
- 论文内容预览（只展示元数据）
- 批量导入功能（保留在 Pipeline 页面）
- Table/List 视图切换（只做 Card）
- 实时 WebSocket 推送（使用轮询）

## 决策

### 1. 组件架构

选择 **集中式容器组件** 模式：

```
LibraryPage (page.tsx)
└── LibraryShell (library-shell.tsx) - 状态管理容器
    ├── LibraryStats - 统计概览
    ├── PaperFilters - 筛选控件
    ├── PaperList - 卡片列表
    │   └── PaperCard[] - 论文卡片
    ├── PaperDetailModal - 详情弹窗
    └── PaperBulkToolbar - 批量操作栏
```

**理由**：
- 所有论文状态集中在 LibraryShell 管理
- 避免 props drilling，通过 props 传递回调函数
- 与现有 PipelineShell、SettingsShell 模式保持一致

### 2. 状态管理

使用 React hooks 本地状态：

```typescript
// LibraryShell 核心状态
const [papers, setPapers] = useState<Paper[]>([]);
const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
const [filters, setFilters] = useState<Filters>({...});
const [pagination, setPagination] = useState<Pagination>({ page: 1, pageSize: 12 });
```

**考虑过的替代方案**：
- Context API：过度设计，数据不跨页面共享
- Zustand/Jotai：引入新依赖，与项目现有模式不符

### 3. API 设计

**批量删除 API**：

```typescript
POST /api/library/papers/bulk-delete
Body: { paper_ids: string[] }
Response: {
  ok: boolean;
  total: number;
  succeeded: number;
  failed: number;
  results: Array<{
    paper_id: string;
    ok: boolean;
    error?: string;
  }>;
}
```

**实现方式**：在 `kernel_api.py` 中新增端点，循环调用现有的 `_orchestrate_paper_delete`。

### 4. 轮询策略

**10 秒间隔 + 页面隐藏检测**：

```typescript
useEffect(() => {
  const timer = setInterval(loadPapers, 10000);
  const handleVisibility = () => {
    if (document.hidden) clearInterval(timer);
    else timer = setInterval(loadPapers, 10000);
  };
  document.addEventListener('visibilitychange', handleVisibility);
}, []);
```

**理由**：
- 平衡实时性和服务器负载
- 参考现有 AppShell 15s、TaskCenter 5s 的模式
- 页面隐藏时暂停，节省资源

### 5. 分页策略

**客户端分页**：

```typescript
const filteredPapers = papers.filter(...); // 先过滤
const paginatedPapers = filteredPapers.slice(
  (page - 1) * pageSize,
  page * pageSize
);
const totalPages = Math.ceil(filteredPapers.length / pageSize);
```

**理由**：
- 后端 API 返回全量数据（最多 500 条）
- 客户端分页减少 API 调用次数
- 分页控件使用简洁的数字按钮（1 2 3 ... 10）

### 6. 批量操作 UX

**选中态 + 底部工具栏**：
- 每张卡片显示复选框
- 选中后底部弹出固定工具栏
- 工具栏显示：已选数量、批量删除、批量重建、清空选择

**考虑过的替代方案**：
- 右键菜单：移动端不友好
- 顶部批量操作栏：遮挡筛选控件

## 风险 / 权衡

| 风险 | 缓解措施 |
|------|----------|
| 论文数量过大（>500）时客户端分页性能问题 | 后端 API 限制 max 500，如需更多需后端支持分页 |
| 批量删除部分失败时用户困惑 | 显示详细结果列表，区分成功/失败 |
| 频繁轮询导致服务器压力 | 10 秒间隔 + 页面隐藏暂停，必要时可配置化 |
| 删除后向量索引未立即生效 | 明确提示用户"建议重建索引" |

## 迁移计划

无数据迁移，纯功能新增：

1. **后端部署**：新增 API 端点，不影响现有数据
2. **前端部署**：新增页面路由，不影响现有功能
3. **回滚**：删除新增文件即可回滚

## 实现细节

### 文件结构

```
frontend/
├── app/library/page.tsx              # 路由页面
├── components/
│   ├── library-shell.tsx             # 主容器组件
│   ├── paper-card.tsx                # 论文卡片
│   ├── paper-list.tsx                # 卡片列表容器
│   ├── paper-detail-modal.tsx        # 详情弹窗
│   ├── paper-bulk-toolbar.tsx        # 批量操作栏
│   ├── paper-filters.tsx             # 筛选控件
│   └── library-stats.tsx             # 统计概览
├── lib/
│   ├── library-api.ts                # API 封装
│   └── use-papers-poll.ts            # 轮询 Hook
└── types/
    └── library.ts                    # 类型定义

app/
└── kernel_api.py                     # 新增批量删除端点
```

### 类型定义

```typescript
interface Paper {
  paper_id: string;
  title: string;
  source_uri: string;
  status: 'imported' | 'parsed' | 'cleaned' | 'ready' | 'failed' | 'deleted';
  topics: string[];
  imported_at: string;
  stage_statuses?: Record<string, { state: string; message?: string }>;
}

interface Filters {
  q: string;
  status: string | null;
  topic: string | null;
}
```

### 状态样式映射

```typescript
const statusStyles = {
  ready: { border: 'border-emerald-200', bg: 'bg-emerald-50', label: '就绪', icon: '✅' },
  parsed: { border: 'border-sky-200', bg: 'bg-sky-50', label: '解析中', icon: '⏳' },
  failed: { border: 'border-rose-200', bg: 'bg-rose-50', label: '失败', icon: '⚠️' },
  rebuild_pending: { border: 'border-amber-200', bg: 'bg-amber-50', label: '待重建', icon: '🔄' },
  deleted: { border: 'border-slate-200', bg: 'bg-slate-50', label: '已删除', icon: '🗑️' },
};
```

## 开放问题

1. 是否需要论文编辑功能（修改标题、专题）？
2. 是否需要导出论文列表功能？
3. 批量删除的最大数量限制（建议 50 篇/次）？
4. 是否需要支持按时间范围筛选？
