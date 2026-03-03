## 上下文

当前 QA 流程在 `app/qa.py` 中按单轮执行：scope 判定 -> rewrite -> retrieval -> answer -> runlog。该流程缺少会话状态层，导致多轮追问无法稳定做指代消解，clarify 决策也无法在下一轮形成闭环。M7.6 已在实现中新增 `app/session_state.py`，并在 `run_qa` 入口前置会话读取与合并逻辑。

约束：
- 历史存储必须“脱水”，禁止写入 raw chunk 文本。
- rewrite 与 answer 的职责必须分离：历史用于 rewrite（实体补全），答案事实仅来自当轮检索证据。
- 保持与既有 CLI/测试兼容（旧测试构造的 `Namespace` 无 session 参数）。

## 目标 / 非目标

**目标：**
- 引入 `session_id` 维度的状态存储与隔离。
- 在 rewrite 前基于最近 N=3 轮脱水历史生成 `standalone_query`。
- 支持 clarify 决策的下一轮强制合并，避免循环澄清。
- 新增并持久化多轮监控字段：`session_id`、`turn_number`、`history_used_turns`、`history_tokens_est`、`coreference_resolved`。
- 提供 `clear_session(session_id)` 接口。

**非目标：**
- 不在本里程碑引入复杂对话规划/长期记忆检索。
- 不将历史回答作为事实证据注入 answer 的证据区。
- 不重构现有检索、重排与 evidence gate 主体算法。

## 决策

### Decision 1: 新增独立会话模块
- 选择：新增 `app/session_state.py`，集中实现会话读写、窗口裁剪、token 估算、clarify 合并、coref 重写。
- 原因：避免在 `qa.py` 中散落状态逻辑，提高可测试性与后续扩展性。
- 备选：
  - 仅在 `qa.py` 内部维护全局 dict：实现快但不可持久化、难测试。
  - 引入 Redis：超出当前仓库依赖和部署复杂度。

### Decision 2: 脱水历史持久化结构
- 选择：每轮仅保存 `user_input`、`standalone_query`、`answer`、`cited_chunk_ids`、`decision`、`entity_mentions`。
- 原因：将历史 token 增长控制在低位，避免 chunk 文本累积。
- 备选：存完整 retrieval candidates；被拒绝，因成本与污染风险高。

### Decision 3: Clarify 闭环优先于检索
- 选择：若存在 `pending_clarify`，先 merge 为新独立问题，再继续 scope/rewrite/retrieve。
- 原因：满足澄清状态闭环要求，避免用户短答直接触发无效检索。
- 备选：让用户短答直接进检索；会造成高歧义与循环。

### Decision 4: 历史只用于重写与语气衔接
- 选择：在 answer prompt 仅注入 `history_brief_style_only`（短摘要），并显式保持 evidence-only 回答约束。
- 原因：维持对话连贯但不污染事实来源。

### Decision 5: 向后兼容参数
- 选择：`run_qa` 对 `session_id/session_store/clear_session` 使用 `getattr` 默认值。
- 原因：兼容现有单元测试和旧调用方。

## 风险 / 权衡

- [风险] 基于词表与实体回填的指代消解可能误补实体。
  - 缓解：仅在检测到指代标记时触发；仅补充历史实体，不拼接历史长回答。
- [风险] clarify merge 可能形成较长 query。
  - 缓解：只合并上一轮待澄清三元组，不跨多轮级联。
- [风险] 本地 JSON session store 并发写入冲突。
  - 缓解：当前 CLI 单进程场景可接受，后续可替换为 DB/Redis。

## 迁移计划

1. 新增 `app/session_state.py` 与单元测试。
2. 在 `app/qa.py` 接入 session 读写、standalone query、clarify merge、clear-session 参数。
3. 在 `app/runlog.py` 扩展 trace 校验字段。
4. 运行回归测试并修正兼容问题。
5. 补充 `reports/m7_6_multi_turn_cases.md` 作为验收记录。

回滚策略：
- 回退 `qa.py` 的 session 接入与 `session_state.py` 引用，恢复单轮逻辑。
- 保留既有 retrieval/answer 路径不变，回滚影响可控。

## Open Questions

- 后续是否需要把 session store 抽象为可插拔后端（文件/Redis/DB）？
- `history_tokens_est` 是否需要统一换算为模型 tokenizer（当前为近似估算）？
