## 新增需求

### 需求:系统必须将 planner LLM 不可用定义为服务阻断而非合法决策来源
系统必须将 planner LLM 被禁用、模型缺失、密钥缺失、调用链路不可用或正式模式配置不完整等情况定义为正式服务阻断条件；在这些条件下，系统禁止继续构造任何看似合法的 `planner decision`、禁止将其重写为普通 `controlled_terminate` 请求结果，也禁止把该状态解释为另一种正式 planner source。

#### 场景:planner 配置缺失不产生伪决策
- **当** 正式模式下 planner model 缺失或 API key 缺失
- **那么** 系统必须将该状态视为服务阻断，并且不得生成可继续消费的 planner decision 对象

## 修改需求

### 需求:系统必须在规划失败时输出受控结束语义
当 planner 输出非法结构、缺失必要字段、引用未注册能力、命中策略禁止规则或置信度不足以继续执行时，系统必须停止继续扩张计划，并进入 `controlled_terminate` 或等价的受控结束语义；禁止把失败重新解释为 `rule planner` 决策，也禁止通过隐式默认字段继续执行。仅当 planner LLM 基础设施已经可用并成功进入单轮决策阶段时，系统才允许使用该请求级受控结束语义；对于基础设施未就绪的情况，系统必须提升为服务阻断。

#### 场景:planner 输出非法 tool 名称
- **当** planner 选择了 registry 中不存在的 tool
- **那么** runtime 必须将该结果视为 planner 失败并进入受控结束

#### 场景:LLM planner decision 被 validation 拒绝
- **当** LLM planner 输出在结构、语义、执行或策略任一层校验失败
- **那么** 系统必须进入受控结束语义，并记录稳定 rejection reason，而不是继续执行该 decision 或切换到 `rule planner`

#### 场景:基础设施未就绪不走请求级受控结束
- **当** planner LLM 在正式模式下因缺配置或不可调用而无法开始本轮决策
- **那么** 系统必须阻断正式聊天服务，而不得把该状态当作单轮规划失败处理

