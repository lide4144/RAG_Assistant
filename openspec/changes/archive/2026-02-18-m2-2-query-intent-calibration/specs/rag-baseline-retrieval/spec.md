## 修改需求

### 需求:最小 QA CLI 输出
系统必须提供命令 `python -m app.qa --q "<question>" --mode dense|bm25|hybrid`。除既有字段外，系统还必须在运行输出中记录：`calibrated_query`、`calibration_reason`、`query_retry_used`、`query_retry_reason`（若触发）。

#### 场景:校准字段完整落盘
- **当** 用户执行 QA CLI 并完成检索
- **那么** 输出与运行记录必须包含上述校准字段，且字段可序列化

### 需求:检索模式与融合
系统必须在首次检索后对 Top-5 evidence 执行 summary shell 比例检测；当 shell 占比大于 60% 且尚未 retry 时，系统必须最多触发一次 query retry。

#### 场景:触发单次 retry
- **当** Top-5 evidence 中 summary shell 占比 > 60%
- **那么** 系统必须移除 `summary/overview/abstract/reporting` 相关 cue words，强制追加已命中的语义意图 cue words 并重新检索一次

#### 场景:retry 次数上限
- **当** 系统已执行一次 retry
- **那么** 同一请求禁止再次触发 retry，且 `query_retry_used` 必须为 true

## 新增需求

### 需求:summary shell 识别规则
系统必须支持 summary shell 识别规则，至少覆盖 `In summary`、`SUMMARY OF`、`Reporting summary`、`This paper: • introduces`、`In this survey paper` 等模式，用于计算 Top-5 shell 占比。

#### 场景:计算 shell 占比
- **当** 首次检索得到 Top-5 evidence
- **那么** 系统必须计算并记录 shell 占比，以支持是否触发 retry 的判定
