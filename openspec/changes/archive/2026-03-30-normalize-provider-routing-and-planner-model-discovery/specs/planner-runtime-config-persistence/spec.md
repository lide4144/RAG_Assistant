## 新增需求

无

## 修改需求

### 需求:系统必须对 Planner Runtime 提供一致的来源可观测性
系统必须在管理接口或运行态概览中说明 Planner Runtime 当前使用的是静态基线、runtime 持久化配置还是环境变量覆盖。禁止让管理员在前端保存后仍无法判断顶层规划器是否真正使用了新的模型连接。对于正式模式，来源可观测性还必须明确说明当前 Planner Runtime 是否满足正式聊天可服务前置条件。对于使用 OpenAI-compatible 上游的 Planner Runtime，系统还必须在保存、回显与执行时使用一致的 provider 规范化语义，避免展示层显示可用而执行层因 provider 解释不同而失败。

#### 场景:管理员查看 Planner Runtime 生效来源
- **当** 管理员打开运行态概览或 Planner Runtime 设置面板
- **那么** 系统必须明确展示 Planner Runtime 的当前模型、启用状态和来源语义

#### 场景:管理员查看正式模式阻断原因
- **当** Planner Runtime 因关键配置缺失或阻断规则而不可服务
- **那么** 管理接口必须明确展示正式模式阻断原因，而不得仅显示模糊的未启用状态

#### 场景:旧 provider 别名配置被读取
- **当** Planner Runtime 持久化配置中存在旧的 OpenAI-compatible provider 别名
- **那么** 系统必须在读取与执行时将其规范化为统一 provider 语义，并保持运行态概览与执行链判断一致

### 需求:系统必须将开发诊断模式与正式 planner 运行配置分离表达
系统若保留无 planner LLM 的开发、离线评测或诊断运行方式，必须通过独立模式字段或等价机制表达，而不得继续复用正式 Planner Runtime 配置字段来表示“关闭 planner LLM”。系统禁止让开发诊断模式与正式服务模式共享相同的可用性语义。

#### 场景:无 LLM 诊断模式通过独立模式表达
- **当** 系统需要进入不依赖 planner LLM 的开发或诊断运行方式
- **那么** 配置治理必须通过独立模式语义表达该状态，而不是通过 `planner.use_llm=false` 表达

#### 场景:存在运行时持久化 Planner Key
- **当** Planner Runtime 的运行时持久化配置已提供可用 API Key
- **那么** 系统必须允许执行链直接使用该最终解析值完成 planner 调用，而不得因为缺少旧环境变量注入副作用而误判 planner 不可服务

## 移除需求
