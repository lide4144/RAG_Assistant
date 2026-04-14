# 根本修复总结：契约标准化

## 问题回顾

### 根本原因
设计时 `step_contract.depends_on` 的语义**定义不明确**：
```python
# 原契约（模糊）
"step_contract": {
    "depends_on": "string[]",  # ❌ 未明确是 artifact 名还是工具名
}
```

导致模型输出不一致：
- 有时输出 artifact 名：`["paper_set"]`
- 有时输出工具名：`["catalog_lookup"]`

## 根本修复方案

### 1. 明确定义契约
```python
# 新契约（明确）
"step_contract": {
    "produces": "artifact_name|null",  # 明确：artifact 名称
    "depends_on": "artifact_name[]",   # 明确：artifact 名称数组
}
```

### 2. 添加标准化层
创建两个新函数：

#### `_build_tool_produces_map`
```python
def _build_tool_produces_map(raw_plan: list[dict]) -> dict[str, list[str]]:
    """构建工具名称到 produces 的映射表"""
    # 返回: {'catalog_lookup': ['paper_set'], 'cross_doc_summary': ['answer']}
```

#### `_normalize_step_dependencies`
```python
def _normalize_step_dependencies(
    step: dict,
    tool_produces_map: dict[str, list[str]],
    step_index: int,
) -> tuple[list[str], list[str]]:
    """
    标准化 step 的 depends_on，统一转换为 artifact 名称
    
    转换规则:
    - 如果是 artifact 名（不在工具列表中）-> 保持不变
    - 如果是工具名（在工具列表中）-> 转换为其 produces
    
    返回: (标准化后的依赖列表, 转换日志)
    """
```

### 3. 简化依赖检查
```python
# 原逻辑（复杂，需兼容两种格式）
missing_dep = []
for dep in normalized["depends_on"]:
    if dep in produced:  # 检查 artifact
        continue
    if dep in processed_tools:  # 检查工具名
        # 还要检查工具 produces
        ...

# 新逻辑（简单，只检查 artifact 名）
missing_dep = [
    dep for dep in normalized["depends_on"]
    if dep not in produced
]
```

### 4. 流程改造
```
原流程:
Planner 输出 -> 直接使用 -> 依赖检查（复杂兼容逻辑）

新流程:
Planner 输出 -> 标准化层（工具名转 artifact 名）-> 依赖检查（简单）
```

## 修复效果对比

### 转换示例
**Planner 输出**（工具名）：
```json
{
  "action": "cross_doc_summary",
  "depends_on": ["catalog_lookup"],
  "produces": "answer"
}
```

**标准化后**（artifact 名）：
```json
{
  "action": "cross_doc_summary",
  "depends_on": ["paper_set"],  // ← 已转换
  "produces": "answer"
}
```

**转换日志**：
```
"Step 2 (cross_doc_summary): converted tool dependency 'catalog_lookup' to artifacts ['paper_set']"
```

### 代码复杂度对比
| 方面 | 修复前 | 修复后 |
|------|--------|--------|
| 依赖检查行数 | 30+ 行 | 3 行 |
| 逻辑分支 | 3 个（artifact/工具/缺失） | 1 个（是否在 produced 中） |
| 命名冲突风险 | 有 | 无（已标准化） |
| 可维护性 | 低 | 高 |

## 核心改进

### 1. 契约清晰
- `depends_on` 明确定义为 artifact 名
- 不再允许工具名（但通过标准化层兼容）

### 2. 职责分离
- **标准化层**：处理输入不一致性
- **依赖检查**：只处理标准化后的数据

### 3. 可观测性
- 添加转换日志到执行追踪
- 便于调试和问题定位

### 4. 向后兼容
- 自动转换工具名到 artifact 名
- 不破坏现有 planner 输出

## 测试验证

```python
# 测试用例 1: 工具名依赖 -> 通过（自动转换）
assert _prepare_tool_calls(state_with_tool_deps) == success

# 测试用例 2: artifact 名依赖 -> 通过
assert _prepare_tool_calls(state_with_artifact_deps) == success

# 测试用例 3: 混合依赖 -> 通过
assert _prepare_tool_calls(state_with_mixed_deps) == success

# 测试用例 4: 真正缺失 -> 正确拒绝
assert _prepare_tool_calls(state_with_missing_deps) == fallback
```

## 总结

| 维度 | 修复前 | 修复后 |
|------|--------|--------|
| **设计层面** | 契约模糊 | 契约明确 |
| **实现层面** | 复杂兼容 | 简单清晰 |
| **可维护性** | 低 | 高 |
| **可观测性** | 无转换记录 | 有详细日志 |
| **扩展性** | 难扩展 | 易扩展 |

**根本修复**：通过添加标准化层，将"兼容不同输入"和"核心逻辑"分离，既保持了向后兼容，又使核心逻辑变得简单清晰。
