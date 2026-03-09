## 新增需求

### 需求:系统必须持久化 Pipeline 运行态配置
系统必须提供独立的 pipeline runtime 配置持久化能力，至少覆盖 Marker tuning 参数：`recognition_batch_size`、`detector_batch_size`、`layout_batch_size`、`ocr_error_batch_size`、`table_rec_batch_size`、`model_dtype`。

#### 场景:保存并读取 pipeline runtime 配置
- **当** 管理员保存 pipeline runtime 配置
- **那么** 系统必须在后续读取中返回完整字段且字段语义一致

### 需求:系统必须提供 pipeline runtime 管理接口
系统必须提供管理接口用于读取与保存 pipeline runtime 配置，并返回字段级校验错误，禁止返回无上下文通用错误。

#### 场景:读取配置
- **当** 前端请求 pipeline runtime 配置
- **那么** 系统必须返回当前生效配置与默认回退值

#### 场景:保存非法配置
- **当** 请求中包含非法批大小或不支持的 dtype
- **那么** 系统必须返回字段级错误信息并拒绝写入

### 需求:系统必须提供运行态概览聚合输出
系统必须提供统一运行态概览输出，聚合 LLM stage 与 pipeline runtime 配置，并给出状态等级（`READY`/`DEGRADED`/`BLOCKED`/`ERROR`）与原因列表。

#### 场景:业务页面读取统一概览
- **当** 对话页或壳层请求运行态概览
- **那么** 系统必须一次返回可直接渲染的模型摘要、pipeline tuning 摘要与状态等级

## 修改需求
<!-- 无 -->

## 移除需求
<!-- 无 -->
