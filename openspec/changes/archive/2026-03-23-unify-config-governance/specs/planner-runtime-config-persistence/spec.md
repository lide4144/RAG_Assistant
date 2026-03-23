## 新增需求

### 需求:系统必须将 Planner Runtime 配置纳入统一治理语义
系统必须将 `planner_use_llm`、`planner_provider`、`planner_api_base`、`planner_api_key`、`planner_model` 与 `planner_timeout_ms` 视为统一配置治理模型中的 `runtime` owner 字段集合。系统必须允许管理员在前端独立管理这些字段，而不是继续要求开发者通过 `default.yaml` 承担顶层规划模型的成本与切换责任。

#### 场景:读取 Planner Runtime 的治理属性
- **当** 系统加载 Planner Runtime 配置
- **那么** 系统必须能够将其解释为 runtime owner，并在缺失或失效时回退到静态基线或安全默认值

### 需求:系统必须对 Planner Runtime 提供一致的来源可观测性
系统必须在管理接口或运行态概览中说明 Planner Runtime 当前使用的是静态基线、runtime 持久化配置还是环境变量覆盖。禁止让管理员在前端保存后仍无法判断顶层规划器是否真正使用了新的模型连接。

#### 场景:管理员查看 Planner Runtime 生效来源
- **当** 管理员打开运行态概览或 Planner Runtime 设置面板
- **那么** 系统必须明确展示 Planner Runtime 的当前模型、启用状态和来源语义

## 修改需求

## 移除需求
