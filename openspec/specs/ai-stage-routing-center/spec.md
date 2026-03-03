# ai-stage-routing-center 规范

## 目的
待定 - 由归档变更 unify-embedding-rerank-dynamic-routing 创建。归档后请更新目的。
## 需求
### 需求:系统必须提供统一的阶段化 AI 路由中心
系统必须提供统一路由中心处理 `stage=answer|embedding|rerank`，并为每个 stage 输出一致的路由决策结构（至少包含 provider、model、api_base、api_key_env、fallback_policy）。系统禁止在调用方硬编码单一供应商环境变量。

#### 场景:按 stage 解析路由
- **当** 调用方请求 `stage=embedding`
- **那么** 系统必须返回 embedding 路由决策，且字段结构与 answer/rerank 一致

### 需求:系统必须提供阶段级失败分类与降级信号
系统必须对网络错误、超时、5xx、认证失败、配置缺失进行统一分类，并向上层返回可判定的降级信号；当 stage 为 embedding 时降级信号必须可触发词频检索回退，当 stage 为 rerank 时降级信号必须可触发静默穿透。

#### 场景:rerank 失败分类可驱动穿透
- **当** `stage=rerank` 调用发生超时或 5xx
- **那么** 系统必须返回可识别的失败分类与“允许静默穿透”信号

