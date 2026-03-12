## 新增需求

## 修改需求

### 需求:系统必须提供运行态概览聚合输出
系统必须提供统一运行态概览输出，聚合 LLM stage 与 pipeline runtime 配置，并给出状态等级（`READY`/`DEGRADED`/`BLOCKED`/`ERROR`）与原因列表。对于 Marker pipeline，概览输出还必须包含 `use_llm`、`llm_service`、最近一次降级状态、产物健康摘要与可直接渲染的 UI 文案。系统还必须输出按阶段归档的最近完成时间，供 `import-latest`、`marker-artifacts` 与 runtime overview 以一致语义判断各类产物是否过期。

#### 场景:业务页面读取统一概览
- **当** 对话页或壳层请求运行态概览
- **那么** 系统必须一次返回可直接渲染的模型摘要、pipeline tuning 摘要与状态等级

#### 场景:业务页面读取包含降级摘要的统一概览
- **当** 对话页、知识处理页或设置页请求运行态概览
- **那么** 系统必须一次返回模型摘要、pipeline tuning 摘要、Marker LLM 摘要、最近一次降级状态与产物健康信息

#### 场景:按阶段时间判断产物 stale
- **当** 后端聚合 `import-latest` 或 `marker-artifacts` 数据
- **那么** 系统必须返回 Import、Clean、Index、Graph Build 的阶段级 `updated_at`，并使用与产物 `related_stage` 对应的时间判断 stale，而不是统一对比单一全局更新时间

## 移除需求
