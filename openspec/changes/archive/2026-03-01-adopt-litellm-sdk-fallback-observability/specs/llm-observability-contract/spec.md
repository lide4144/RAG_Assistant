## ADDED Requirements

### 需求:系统必须记录统一的 LLM 调用观测字段
系统必须为每次 LLM 调用记录统一字段，包括 `provider_used`、`model_used`、`attempts_used`、`fallback_reason`、`elapsed_ms` 与错误类别。

#### 场景:降级调用产生完整诊断
- **当** 一次请求发生 fallback
- **那么** 诊断记录必须包含触发原因、原模型与最终模型信息

### 需求:系统必须在流式调用中记录首 token 与事件摘要
系统必须记录流式路径的首 token 延迟与事件摘要，以维持与现有性能诊断口径一致。

#### 场景:流式回答完成后写入指标
- **当** 流式回答正常完成
- **那么** 系统必须写入首 token 延迟与 chunks 数量指标

## MODIFIED Requirements
<!-- 无 -->

## REMOVED Requirements
<!-- 无 -->
