# unified-source-citation-contract 规范

## 目的
待定 - 由归档变更 perplexica-like-tech-stack-migration 创建。归档后请更新目的。
## 需求
### 需求:系统必须统一本地与 Web 来源结构
系统必须以同构字段输出本地证据与 Web 来源，至少包含 `source_type`、`source_id`、`title`、`snippet`、`locator`、`score`；禁止按来源类型返回完全不同的引用结构。

#### 场景:Hybrid 模式输出同构来源
- **当** 回答同时使用本地证据与 Web 来源
- **那么** 返回的来源列表必须使用同一字段集合，且每条来源可独立渲染

### 需求:系统必须保证引用编号稳定映射
系统必须保证回答中的引用编号与来源列表一一对应，且在流式完成后编号不得重排。

#### 场景:引用编号可点击追溯
- **当** 用户点击回答中的 `[n]`
- **那么** UI 必须定位到第 n 条来源并展示其定位信息（chunk/page 或 URL）

