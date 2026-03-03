## 新增需求

### 需求:重写输入必须包含上轮决策与告警信号
系统必须在 rewrite 输入中提供 `last_turn_decision` 与 `last_turn_warnings`，用于状态感知转写与补证据优先级判定。

#### 场景:状态信号传递到 rewrite
- **当** 会话存在上一轮记录
- **那么** 系统必须向 rewrite 阶段传入上一轮 `decision` 与 `output_warnings` 的脱水映射

### 需求:重写输入必须包含历史实体集合
系统必须基于最近 N 轮历史提取 `entities_from_history`（论文名、方法名、指标名等）并传递给 rewrite；该集合必须用于元问题转写的实体保真约束。

#### 场景:历史实体可用于追问补全
- **当** 当前输入缺少明确实体且历史中存在实体
- **那么** rewrite 必须可读取 `entities_from_history` 并用于生成实体完整的 `standalone_query`

## 修改需求

### 需求:滑动窗口历史供重写
系统必须在 rewrite 阶段读取最近 N 轮（默认 N=3）脱水历史，并生成 `standalone_query`。若当前问题含指代，`standalone_query` 必须补齐关键实体，且禁止拼接历史回答整段文本。若上一轮 `decision=clarify`，系统必须先执行 clarify 合并逻辑，再进行元问题护栏判断。若进入上下文预算裁剪流程且 `total_tokens > max_context_tokens`，系统必须从最老历史轮次开始删除，并必须始终保留当前轮问题；在进入证据裁剪前，系统必须至少保留 1 轮历史。

#### 场景:指代追问补齐实体
- **当** 当前输入为代词追问（例如“它和微调有什么区别？”）且历史包含实体（例如 `RAG`）
- **那么** `standalone_query` 必须包含该实体并保持当前问题意图

#### 场景:clarify 优先于元问题护栏
- **当** 上一轮 `decision=clarify` 且当前轮进入 rewrite
- **那么** 系统必须先完成 clarify 合并后再执行元问题识别与转写

#### 场景:预算超限时按历史先裁剪
- **当** 组装上下文时估算 token 超过 `max_context_tokens`
- **那么** 系统必须按时间顺序先删除最老历史，直到历史仅剩 1 轮或预算恢复可用，再决定是否进入证据裁剪

## 移除需求

- 无
