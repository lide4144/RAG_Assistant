## ADDED Requirements

### 需求:系统必须将 rewrite 阶段的 LLM 失败处理迁移到统一路由策略
系统必须在 rewrite 阶段通过统一路由策略处理 LLM 调用失败与降级，并将结果映射到既有 warning 语义；禁止在 rewrite 业务逻辑中直接依赖单一供应商 API key 常量。

#### 场景:缺失主模型凭据时触发统一降级
- **当** rewrite 阶段主模型缺少凭据或不可用
- **那么** 系统必须通过统一路由策略执行降级并产出兼容的 fallback warning

## MODIFIED Requirements
<!-- 无 -->

## REMOVED Requirements
<!-- 无 -->
