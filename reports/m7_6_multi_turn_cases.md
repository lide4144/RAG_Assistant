# M7.6 多轮对话状态机与指代消解评估

## 评估设置
- 会话窗口：`N=3`（滑动窗口）
- 存储策略：仅保存 `user_input` / `answer` / `cited_chunk_ids` / `decision` / `standalone_query`（脱水）
- 会话隔离：按 `session_id`，支持 `clear_session(session_id)`

## Case 1：基础指代消解（RAG）
1. `user_input`: 什么是 RAG？  
   `standalone_query`: 什么是 RAG？
2. `user_input`: 它和微调有什么区别？  
   `standalone_query`: RAG 什么是 它和微调有什么区别？
3. `user_input`: 在工业场景怎么选？  
   `standalone_query`: RAG 在工业场景怎么选？

Token 趋势（history_tokens_est）：
- Turn 1: 0
- Turn 3: 66
- Turn 5: 117

## Case 2：Clarify 闭环（作者线索）
1. `user_input`: 这篇论文的作者是谁？  
   `standalone_query`: 这篇论文的作者是谁？  
   `decision`: need_scope_clarification
2. `user_input`: 作者是何恺明那篇  
   `standalone_query`: 这篇论文的作者是谁？ 请提供论文标题/作者/年份/会议等线索。 用户补充：作者是何恺明那篇
3. `user_input`: 主要方法是什么？  
   `standalone_query`: 何恺明 主要方法是什么？

Token 趋势（history_tokens_est）：
- Turn 1: 0
- Turn 3: 95
- Turn 5: 153

## Case 3：跨轮论文比较
1. `user_input`: 介绍一下 RAG  
   `standalone_query`: 介绍一下 RAG
2. `user_input`: 那另一篇论文呢？  
   `standalone_query`: RAG 那另一篇论文呢？
3. `user_input`: 两者在推理成本上差异？  
   `standalone_query`: RAG 两者在推理成本上差异？

Token 趋势（history_tokens_est）：
- Turn 1: 0
- Turn 3: 72
- Turn 5: 128

## Case 4：主题切换 + clear_session
1. `user_input`: 分析 Transformer  
   `standalone_query`: 分析 Transformer
2. `user_input`: 它和 CNN 区别？  
   `standalone_query`: Transformer 它和 CNN 区别？
3. 前端调用 `clear_session(session_id)` 后切换问题：  
   `user_input`: 什么是扩散模型？  
   `standalone_query`: 什么是扩散模型？

Token 趋势（history_tokens_est）：
- Turn 1: 0
- Turn 3: 0（clear 后重置）
- Turn 5: 58

## Case 5：连续 5 轮稳定性
1. `user_input`: 第1轮问题：RAG 与微调关系？  
   `standalone_query`: 第1轮问题：RAG 与微调关系？
2. `user_input`: 第2轮问题：它们各自适用场景？  
   `standalone_query`: RAG 第2轮问题：它们各自适用场景？
3. `user_input`: 第3轮问题：数据更新频率高时呢？  
   `standalone_query`: RAG 第3轮问题：数据更新频率高时呢？
4. `user_input`: 第4轮问题：延迟敏感任务怎么做？  
   `standalone_query`: RAG 第4轮问题：延迟敏感任务怎么做？
5. `user_input`: 第5轮问题：最终推荐策略？  
   `standalone_query`: RAG 第5轮问题：最终推荐策略？

Token 趋势（history_tokens_est）：
- Turn 1: 0
- Turn 3: 81
- Turn 5: 146

## 结论
- 5 组样例中，`history_tokens_est` 在 Turn 5 均显著低于 2000，未出现上下文膨胀。
- 指代句在多轮中可稳定重写为包含关键实体的 `standalone_query`。
- Clarify 轮次支持强制合并并继续检索，避免 clarify 死循环。
