## 新增需求

### 需求:系统必须禁止规则规划器参与线上正式执行
系统必须将 `rule planner` 退出线上正式执行链；`rule planner` 可以保留为离线评测、开发诊断或历史回放资产，但禁止在用户请求的正式执行路径中生成或替换顶层 `planner decision`。

#### 场景:线上请求只接受 LLM 正式决策
- **当** 一条 `Local` 聊天请求进入顶层 planner runtime
- **那么** 系统必须只接受通过 validation 的 `LLM planner decision` 作为正式执行输入，且不得再调用 `rule planner` 生成本轮正式决策

## 修改需求

### 需求:系统必须支持 llm-first planner source 与受控结束
系统必须将线上正式 planner source 收敛为 `llm_primary` 单一模式，并在该模式下只允许通过 validation 的 `LLM decision` 驱动顶层执行；禁止继续提供 `rule_only` 或 `llm_primary_with_rule_fallback` 作为线上正式决策模式。系统可以保留与 `rule planner` 相关的离线对比或诊断能力，但这些能力禁止影响本轮用户主执行路径。

#### 场景:LLM decision 成为唯一正式执行来源
- **当** 系统运行在线上正式模式且 `LLM planner decision` 通过 validation gate
- **那么** planner runtime 必须将该 decision 作为唯一正式顶层决策继续执行，而不得再请求 `rule planner` 生成替代结果

#### 场景:离线对比不影响主路径
- **当** 系统为了评测或诊断额外生成 planner 诊断记录
- **那么** 这些诊断记录必须只写入观测或评测路径，不得改变 `selected_path`、`decision_result` 或用户最终可见回答

### 需求:系统必须提供无规则回退的受控失败收束
当 `LLM planner decision` 被 validation 拒绝、planner runtime 节点抛出异常、或关键状态校验失败时，系统必须进入受控失败收束路径，并输出可审计的失败类型与最终用户可见姿态；禁止通过 `rule planner`、`legacy QA` 或其他旧规则链补写一份替代性的顶层正式决策。

#### 场景:validation reject 不触发规则回退
- **当** `LLM planner decision` 在结构、语义、执行或策略任一层校验失败
- **那么** planner runtime 必须停止接受该 decision，并进入受控失败收束路径，而不得切换到 `rule planner`

#### 场景:运行时异常不切回旧问答主链
- **当** planner runtime 在规划、路由或 tool 调度阶段抛出异常
- **那么** 系统必须返回受控且可审计的失败收束结果，并记录异常原因，而不得回退到旧 `qa.py` 主链重做顶层决策

## 移除需求
