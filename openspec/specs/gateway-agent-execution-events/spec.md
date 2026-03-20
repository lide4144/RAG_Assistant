# gateway-agent-execution-events 规范

## 目的
定义 Gateway 面向 agent-first planner runtime 输出的高层执行事件类型、最小字段、事件顺序与降级语义，确保前端能在统一入口下感知规划、tool 执行和受控回退，而不暴露内部 trace。

## 需求
### 需求:系统必须为 agent-first 运行时提供有限的高层执行事件集合
系统必须为 Gateway 定义有限且稳定的 agent 执行事件集合，至少包含 `planning`、`toolSelection`、`toolRunning`、`toolResult` 与 `fallback` 五类事件；这些事件必须表达 planner runtime 的高层执行阶段，禁止扩展为透传内部 trace、LangGraph 节点名、prompt 片段、私有函数路径或任意未稳定的调试事件。

#### 场景:规划阶段输出高层事件
- **当** `Local` 聊天请求进入 Python kernel 的 planner runtime 并开始形成顶层执行方向
- **那么** Gateway 必须能够向前端输出 `planning` 事件，而不是等待最终回答后完全丢失规划阶段语义

#### 场景:内部节点细节不得直接透出
- **当** planner runtime 内部经过多个 LangGraph 节点、私有路由步骤或底层工具包装层
- **那么** Gateway 必须只输出受支持的高层 agent 事件，而禁止把这些内部节点或详细 trace 直接透传给前端

### 需求:系统必须为 agent 执行事件提供最小稳定字段
每个 agent 执行事件必须包含可用于统一消费的最小稳定字段，至少包括 `type`、`traceId`、`timestamp` 与阶段相关摘要字段；当事件涉及工具时，还必须包含稳定的高层 `tool_name` 与 `status` 或结果摘要；当事件涉及降级时，还必须包含 `fallback_scope`、`reason_code` 与是否继续走标准聊天输出的语义。系统禁止要求前端依赖未声明的私有字段来理解事件。

#### 场景:工具执行事件携带最小识别字段
- **当** runtime 开始执行一个已注册能力
- **那么** `toolRunning` 事件必须至少提供 `traceId`、稳定 `tool_name`、开始执行状态和必要摘要，以便前端能够在不理解底层实现的前提下识别该步骤

#### 场景:降级事件携带受控原因
- **当** runtime 触发 planner fallback、tool fallback 或受控结束
- **那么** Gateway 必须输出包含 `fallback_scope` 和 `reason_code` 的 `fallback` 事件，而不是仅输出模糊文本或直接静默切换路径

### 需求:系统必须保证 agent 执行事件与标准聊天事件兼容并存
agent 执行事件必须作为现有聊天协议的增强层存在，并必须与 `message`、`sources`、`messageEnd`、`error` 共存；系统禁止以 agent 事件替代现有标准聊天闭合语义，也禁止要求所有路径都必须先发出 agent 事件才能正常回答。

#### 场景:agent 路径同时输出执行状态和最终回答
- **当** 一次 `Local` 聊天请求经过规划、工具执行并最终产出回答
- **那么** Gateway 必须允许同一条流中先后输出 agent 执行事件以及现有 `message`、`sources`、`messageEnd` 事件

#### 场景:非 agent 或兼容路径保持旧协议可用
- **当** 某条请求未进入 agent-first 执行路径，或后端当前未提供高层 agent 事件
- **那么** Gateway 必须仍可仅依靠 `message`、`sources`、`messageEnd`、`error` 完成本轮响应，而不要求补造伪 agent 事件

### 需求:系统必须对 agent 执行事件施加最小顺序约束
系统必须保证 agent 执行事件满足最小因果顺序：`planning` 必须先于由其触发的 `toolSelection`、`toolRunning`、`toolResult` 或 `fallback`；`toolSelection` 必须先于对应 `toolRunning`；`toolRunning` 必须先于对应 `toolResult` 或该步触发的 `fallback`；最终必须由 `messageEnd` 或 `error` 关闭本轮请求。系统禁止输出违反这些最小顺序的事件流。

#### 场景:正常工具执行顺序可追踪
- **当** planner 先选中某个工具并成功执行完成
- **那么** 事件流必须按 `planning -> toolSelection -> toolRunning -> toolResult` 的因果顺序出现，并在回答完成后由标准结束事件闭合

#### 场景:规划后直接降级
- **当** planner 在规划后判定本轮请求需要走兼容回退而不进入工具执行
- **那么** Gateway 必须允许在 `planning` 后直接输出 `fallback`，而不是伪造不存在的 `toolRunning` 或 `toolResult`

### 需求:系统必须区分受控降级事件与失败终态
系统必须将 `fallback` 定义为受控降级或兼容回退事件，而将 `error` 保留为请求失败或无法继续处理的终态事件；禁止把所有 agent 降级都等同为错误。若降级后仍能继续产生标准聊天回答，系统必须继续输出后续 `message`、`sources` 与 `messageEnd`。

#### 场景:受控结束仍返回标准闭合
- **当** planner runtime 因 validation reject、tool failure 或 runtime exception 进入受控结束
- **那么** Gateway 必须先输出 `fallback` 事件，再继续输出标准聊天结束事件，而不是直接输出 `error`

#### 场景:真正失败输出错误终态
- **当** 请求在降级后仍无法得到受支持结果，或协议流已无法继续
- **那么** Gateway 必须输出 `error` 作为失败终态，而不能仅靠 `fallback` 假装本轮仍然成功

### 需求:系统必须在 planner source 迁移期保留受控的高层事件语义
Gateway 在 `llm_primary` 与 `shadow_compare` 两种 planner source 模式下，必须继续只转发稳定的高层执行事件，并在发生 LLM decision reject、tool failure 或 runtime exception 时通过 `fallback` 事件表达受控降级；禁止将 shadow 对比细节、LLM 原始输出或私有 validation trace 直接透传给前端。

#### 场景:LLM decision 被拒绝时输出受控 fallback 事件
- **当** LLM planner decision 被 runtime validation 拒绝并进入受控结束路径
- **那么** Gateway 必须输出高层 `fallback` 事件并继续保持标准聊天事件闭环，而不是透出内部 validation 细节

#### 场景:shadow 模式不透出双份规划细节
- **当** 系统运行在 shadow mode 并产出额外的诊断记录
- **那么** Gateway 必须仅向前端暴露稳定的主执行高层事件，而不是把诊断记录或内部 planner 细节作为用户事件流输出
