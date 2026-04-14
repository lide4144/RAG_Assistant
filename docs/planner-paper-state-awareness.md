# Planner Paper State Awareness

本文档描述 Planner 如何感知和利用论文生命周期状态进行任务规划与路由决策。

## 概述

Planner 现已集成 SQLite 论文存储，能够：

- 查询论文生命周期状态（`dedup`、`import`、`parse`、`clean`、`index`、`graph_build`、`ready`、`failed`、`rebuild_pending`）
- 基于论文状态进行智能任务路由
- 在 action plan 中声明论文级依赖
- 处理论文状态不满足时的 fallback

## 核心功能

### 1. 论文状态查询

Planner Runtime 通过 `_get_cached_papers()` 和 `_get_cached_paper()` 函数查询论文状态：

```python
from app.planner_runtime import _get_cached_papers, _get_cached_paper

# 查询所有就绪论文
ready_papers = _get_cached_papers(status="ready", limit=100)

# 查询单篇论文
paper = _get_cached_paper("paper_id_123")
```

### 2. 论文状态过滤

Planner Policy 提供基于论文状态的过滤函数：

```python
from app.planner_policy import (
    filter_papers_by_lifecycle_status,
    categorize_papers_by_status,
    build_paper_status_summary,
)

# 过滤就绪论文
ready_papers = filter_papers_by_lifecycle_status(papers, include_statuses={"ready"})

# 按状态分类
categories = categorize_papers_by_status(papers)

# 构建状态摘要
summary = build_paper_status_summary(papers)
```

### 3. Catalog Lookup 状态过滤

`execute_catalog_lookup` 函数支持 `status_filter` 参数：

```python
from app.capability_planner import execute_catalog_lookup

# 只查询就绪论文
result = execute_catalog_lookup(
    query="大模型",
    max_papers=20,
    status_filter="ready",  # 只返回状态为 ready 的论文
)
```

### 4. Action Plan 论文依赖

在 action plan 步骤中可以声明对论文状态的依赖：

```json
{
  "action": "cross_doc_summary",
  "query": "总结这些论文的方法",
  "paper_dependencies": [
    {"paper_id": "p1", "required_status": "ready"},
    {"paper_id": "p2", "required_status": "ready"}
  ]
}
```

执行器会在执行前检查依赖是否满足，如不满足会触发 fallback。

## 降级策略

当 SQLite 数据库不可用时，Planner 会自动降级到文件读取：

```python
# 在 _get_cached_papers 和 _get_cached_paper 中实现
try:
    papers = list_papers(db_path=store_path, ...)
except Exception as exc:
    # Fallback to file-based loading
    from app.library import load_papers
    papers = load_papers()
```

## 缓存机制

Planner Runtime 使用内存缓存减少重复数据库查询：

- 缓存 TTL：30 秒
- 缓存键：`papers:{status}:{limit}` 或 `paper:{paper_id}`
- 手动清除：`clear_planner_paper_cache()`

## 配置选项

暂无特殊配置选项。Planner 自动使用默认的论文存储路径。

## 注意事项

1. 论文状态感知功能默认启用，无需额外配置
2. 降级到文件读取时会发出 `RuntimeWarning`
3. 缓存机制可减少数据库查询，但可能导致 30 秒内的状态延迟
4. 论文依赖检查会增加执行时间，建议只在必要时使用

## API 变更

### 新增函数

- `_get_cached_papers()` - 带缓存的论文列表查询
- `_get_cached_paper()` - 带缓存的单篇论文查询
- `clear_planner_paper_cache()` - 清除论文缓存
- `filter_papers_by_lifecycle_status()` - 按状态过滤论文
- `categorize_papers_by_status()` - 按状态分类论文
- `build_paper_status_summary()` - 构建状态摘要

### 修改函数

- `execute_catalog_lookup()` - 新增 `status_filter` 参数
- `_validate_semantics()` - 新增 `paper_dependencies` 验证
- `_execute_tool_calls()` - 新增论文依赖检查

## 迁移指南

### 从旧版本迁移

无需特殊迁移步骤。Planner 会自动：

1. 检测并使用 SQLite 论文存储
2. 在数据库不可用时降级到文件读取
3. 缓存查询结果以提高性能

### 启用论文依赖

在 action plan 中添加 `paper_dependencies` 字段即可启用：

```json
{
  "action": "your_tool",
  "paper_dependencies": [
    {"paper_id": "p1", "required_status": "ready"}
  ]
}
```
