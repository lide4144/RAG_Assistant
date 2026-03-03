## 新增需求

## 修改需求

### 需求:检索模式与融合
系统必须在首次检索后对 Top-5 evidence 执行 summary shell 比例检测；当 shell 占比大于 60% 且尚未 retry 时，系统必须最多触发一次 query retry。完成最终一次检索后，系统必须在初检 `top_k` 上执行图扩展召回，并将“初检 + 扩展”候选并入后续证据组织流程。

#### 场景:触发单次 retry
- **当** Top-5 evidence 中 summary shell 占比 > 60%
- **那么** 系统必须移除 `summary/overview/abstract/reporting` 相关 cue words，强制追加已命中的语义意图 cue words 并重新检索一次

#### 场景:retry 次数上限
- **当** 系统已执行一次 retry
- **那么** 同一请求禁止再次触发 retry，且 `query_retry_used` 必须为 true

#### 场景:初检后执行图扩展
- **当** 系统完成最终一次检索并得到初检 `top_k` 候选
- **那么** 系统必须执行 1-hop 图扩展并将合并去重后的候选集合提供给后续证据组织阶段

## 移除需求
