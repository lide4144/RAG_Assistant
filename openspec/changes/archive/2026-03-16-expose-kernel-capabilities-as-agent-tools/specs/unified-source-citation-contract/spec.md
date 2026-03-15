## ADDED Requirements

### 需求:系统必须对非 citation 类 tool 输出提供显式 provenance 类型
系统必须允许来源结构显式区分 `citation`、`metadata` 与 `explanatory` provenance。对于由 `catalog_lookup`、`control`、`title_term_localization` 或研究辅助建议段生成的非正文证据结果，系统必须使用 `metadata` 或 `explanatory` 类型标记；禁止把它们伪装为 chunk/page citation。

#### 场景:目录查询结果标记为 metadata provenance
- **当** `catalog_lookup` 输出论文集合、导入时间或处理状态等目录信息
- **那么** 返回来源必须标记为 `metadata` provenance，而不是正文 citation

#### 场景:中文化结果标记为 explanatory provenance
- **当** `title_term_localization` 输出标题中文化或术语解释
- **那么** 返回来源必须标记为 `explanatory` provenance，而不是正文 citation

## MODIFIED Requirements

### 需求:系统必须统一本地与 Web 来源结构
系统必须以同构字段输出本地证据与 Web 来源，至少包含 `source_type`、`source_id`、`title`、`snippet`、`locator`、`score`；在 agent-first tool 输出场景下，来源结构还必须显式包含 provenance 类型，以区分 `citation`、`metadata` 与 `explanatory` 结果；禁止按来源类型返回完全不同的引用结构，也禁止把非 citation 类 tool 输出伪装成正文证据来源。

#### 场景:Hybrid 模式输出同构来源
- **当** 回答同时使用本地证据与 Web 来源
- **那么** 返回的来源列表必须使用同一字段集合，且每条来源可独立渲染

#### 场景:tool 输出来源保留 provenance 类型
- **当** planner/runtime 组合了 fact QA、catalog lookup 或 localization 等不同 tool 结果
- **那么** 最终来源结构必须在同一字段集合中保留 provenance 类型，供上层区分 citation 与非 citation 结果

### 需求:系统必须保证引用编号稳定映射
系统必须保证回答中的引用编号与来源列表一一对应，且在流式完成后编号不得重排；仅 `citation` 类型来源可以参与正文引用编号映射，`metadata` 与 `explanatory` provenance 禁止被编号为正文事实引用。

#### 场景:引用编号可点击追溯
- **当** 用户点击回答中的 `[n]`
- **那么** UI 必须定位到第 n 条来源并展示其定位信息（chunk/page 或 URL）

#### 场景:非 citation provenance 不参与正文编号
- **当** 回答同时包含目录元数据说明或中文化解释
- **那么** 这些 `metadata` 或 `explanatory` 来源必须不占用正文 citation 编号

## REMOVED Requirements
