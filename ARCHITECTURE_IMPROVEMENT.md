# 架构改进：系统控制 vs 模型生成

## 问题描述

之前的架构存在**系统过度控制**的问题：

```
错误架构：
用户问题 → Planner → 系统获取数据 → [系统直接回答] → 用户
                              ↑
                              └── 跳过了大模型层
```

具体表现：
- `catalog` 路由直接由 `compose_catalog_answer()` 格式化输出
- 系统拼接字符串，跳过了大模型的自然语言生成能力
- 用户体验差（机器式回答）

## 改进方案

### 正确架构

```
正确架构：
用户问题 → Planner识别意图 → 系统获取数据 → 大模型生成回答 → 用户
                                      ↑
                                      └── 大模型基于数据生成自然语言
```

### 具体修改

#### 1. 配置选项 (`app/config.py`)

```python
# 新增配置
 catalog_use_llm_answer: bool = True  # 是否使用大模型生成 catalog 回答
```

#### 2. Catalog 回答生成 (`app/qa.py`)

**修改前：**
```python
if planner_strictness == "catalog":
    answer = compose_catalog_answer(catalog_result)  # 系统直接回答
```

**修改后：**
```python
if planner_strictness == "catalog":
    if config.catalog_use_llm_answer:
        # 大模型基于数据生成回答
        answer = _build_catalog_llm_answer(
            question=question,
            catalog_result=catalog_result,
            ...
        )
    else:
        # 回退到系统格式化（兼容旧行为）
        answer = compose_catalog_answer(catalog_result)
```

#### 3. 新增函数 `_build_catalog_llm_answer`

功能：
- 构建包含 catalog 数据的 prompt
- 调用大模型生成自然语言回答
- 支持流式输出
- 失败时回退到系统格式化

## 优势对比

| 方面 | 旧架构（系统回答） | 新架构（模型回答） |
|------|-------------------|-------------------|
| **回答质量** | 机器式、格式化 | 自然、流畅 |
| **灵活性** | 固定模板 | 根据问题调整语气 |
| **可扩展性** | 需修改代码 | 调整 prompt 即可 |
| **用户体验** | 生硬 | 友好、专业 |
| **多语言** | 需手动翻译 | 模型自动适配 |

## 示例对比

### 查询："列出最近导入的论文"

**旧架构（系统回答）：**
```
基于目录元数据，匹配到这些论文：
1. Transformer Architecture | paper_id=p1 | imported_at=2024-01-15
2. BERT Pre-training | paper_id=p2 | imported_at=2024-01-14
...
```

**新架构（大模型回答）：**
```
最近导入的论文包括以下研究成果：

1. **Transformer Architecture**（2024-01-15导入）
   这篇论文介绍了Transformer架构的核心创新...

2. **BERT Pre-training**（2024-01-14导入）
   该研究提出了预训练语言模型的新范式...

这些论文涵盖了自然语言处理领域的前沿进展，
您想了解哪一篇的更多细节？
```

## 配置说明

在 `config.yaml` 中：

```yaml
# 启用大模型生成 catalog 回答（推荐）
 catalog_use_llm_answer: true

# 回退到系统格式化（兼容旧版本）
 catalog_use_llm_answer: false
```

## 扩展性

此架构改进为后续功能奠定基础：

1. **跨文档总结**（`cross_doc_summary`）：同理，系统获取多文档数据，大模型生成综合回答
2. **对比分析**：系统获取多论文信息，大模型生成对比表格和分析
3. **智能推荐**：基于用户历史，大模型生成个性化推荐

核心原则：**系统负责数据，模型负责生成**
