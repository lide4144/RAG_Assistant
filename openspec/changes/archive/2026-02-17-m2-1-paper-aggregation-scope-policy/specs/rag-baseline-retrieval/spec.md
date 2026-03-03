## 新增需求

## 修改需求

### 需求:检索模式与融合
系统必须支持 `dense`、`bm25`、`hybrid` 三种检索模式。`hybrid` 模式必须融合 BM25 与向量候选；系统必须继续对 `content_type=table_list` 的候选降权（默认乘以 `0.5`）且禁止直接剔除。系统还必须默认对 `content_type=front_matter` 与 `content_type=reference` 降权（建议乘以 `0.3`），并在 query 命中作者机构意图或引用出处意图时执行条件放行（取消降权或提高权重）。

#### 场景:dense 模式返回候选
- **当** 用户以 `--mode dense` 发起检索
- **那么** 系统必须返回向量检索 top-k 候选

#### 场景:bm25 模式返回候选
- **当** 用户以 `--mode bm25` 发起检索
- **那么** 系统必须返回 BM25 检索 top-k 候选

#### 场景:hybrid 模式融合并降权
- **当** 用户以 `--mode hybrid` 发起检索且候选中包含 `table_list`
- **那么** 系统必须返回融合后的排序结果，并对 `table_list` 候选执行降权后仍保留在候选集中

#### 场景:front_matter/reference 默认降权
- **当** 候选中出现 `front_matter` 或 `reference`
- **那么** 系统必须默认降低其融合分数，避免其主导 Top evidence

#### 场景:作者机构意图触发条件放行
- **当** query 命中 `author/affiliation/university/institute/email/corresponding/作者/单位/机构/通讯作者/邮箱`
- **那么** 系统必须对 `front_matter` 相关候选取消降权或提高权重

#### 场景:引用出处意图触发条件放行
- **当** query 命中 `reference/citation/appendix/scale/questionnaire/validate/引用/参考文献/量表/验证`
- **那么** 系统必须对 `reference` 相关候选取消降权或提高权重

### 需求:最小 QA CLI 输出
系统必须提供命令 `python -m app.qa --q "<question>" --mode dense|bm25|hybrid`。命令输出必须包含 Answer 与 evidence，且运行记录必须包含字段：`question`、`mode`、`scope_mode`、`query_used`、`papers_ranked`、`evidence_grouped`。其中 evidence 展示必须按论文分组。

#### 场景:CLI 问答输出字段完整
- **当** 用户执行 QA CLI 并获得候选证据
- **那么** 系统必须输出上述必需字段，并保证 `evidence_grouped` 按论文分组

## 移除需求
