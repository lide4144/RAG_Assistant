## 新增需求

### 需求:系统必须在正式聊天入口前阻断不可用的 planner LLM 基础设施
系统在正式聊天模式下必须将 planner LLM 视为执行前置基础设施，并必须在请求进入主 planner runtime 之前完成门禁检查；当 planner 模型缺失、密钥缺失、运行态配置无效或健康状态已确认 planner 基础设施不可用时，系统必须阻断正式聊天执行，禁止继续进入普通 planner fallback、tool fallback 或 `controlled_terminate` 请求链路。

#### 场景:正式聊天请求在 planner 基础设施缺失时被入口阻断
- **当** 一条正式 `Local` 聊天请求到达 Kernel 且 planner model 或 planner API key 不可用
- **那么** 系统必须直接返回系统级阻断结果，并且不得继续进入 planner decision validation 或 tool 执行阶段

### 需求:系统必须区分系统级阻断与请求级失败收束
系统必须将 `planner LLM` 不可用、未就绪或被正式模式判定为无效配置的情况定义为系统级阻断；系统必须仅将单轮规划失败、validation reject、tool 失败或运行时异常定义为请求级失败收束。系统禁止继续使用单一 `controlled_terminate` 语义同时表达这两类状态。

#### 场景:单轮规划失败不等同于系统阻断
- **当** planner 基础设施已就绪但某一轮请求的 LLM decision 被 validation 拒绝
- **那么** 系统必须将该结果记录为请求级失败收束，而不得把整个聊天服务标记为系统级阻断

## 修改需求

### 需求:系统必须支持 llm-first planner source 与受控结束
系统必须将线上正式 planner source 收敛为 `llm_primary` 单一模式，并在该模式下只允许通过 validation 的 `LLM decision` 驱动顶层执行；禁止继续提供 `rule_only` 或 `llm_primary_with_rule_fallback` 作为线上正式决策模式。系统可以保留与 `rule planner` 相关的离线对比或诊断能力，但这些能力禁止影响本轮用户主执行路径。对于正式模式下的聊天入口，planner LLM 基础设施必须先满足可服务前置条件；若基础设施未就绪，系统必须阻断服务而不是进入普通请求级受控结束。

#### 场景:LLM decision 成为唯一正式执行来源
- **当** 系统运行在线上正式模式且 `LLM planner decision` 通过 validation gate
- **那么** planner runtime 必须将该 decision 作为唯一正式顶层决策继续执行，而不得再请求 `rule planner` 生成替代结果

#### 场景:离线对比不影响主路径
- **当** 系统为了评测或诊断额外生成 planner 诊断记录
- **那么** 这些诊断记录必须只写入观测或评测路径，不得改变 `selected_path`、`decision_result` 或用户最终可见回答

#### 场景:基础设施未就绪时不进入普通受控结束
- **当** 系统运行在线上正式模式但 planner LLM 基础设施未满足执行前置条件
- **那么** 聊天入口必须进入系统级阻断状态，而不得继续返回看似正常的 `controlled_terminate` 单轮结果

