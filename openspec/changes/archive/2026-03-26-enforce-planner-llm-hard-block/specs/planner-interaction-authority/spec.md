## 新增需求

### 需求:系统必须将服务级阻断置于单轮交互姿态裁决之上
系统必须将 planner LLM 基础设施未就绪导致的正式服务阻断定义为高于单轮 `execute`、`clarify`、`partial_answer`、`refuse` 与 `delegate` 的服务可用性约束。对于系统级阻断，系统禁止继续声称本轮请求仍由普通 `planner / policy` 交互姿态裁决完成。

#### 场景:服务阻断不伪装成拒答姿态
- **当** 正式聊天入口因 planner LLM 基础设施未就绪而被阻断
- **那么** 运行 trace 与用户可见结果必须明确表达服务级阻断，而不得仅显示为普通 `refuse` 或 `controlled_terminate`

