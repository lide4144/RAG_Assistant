## 上下文

当前代码已具备 M2~M7 主链路、`scope_mode` 路由、`rewrite_rule_query/rewrite_llm_query` 字段、证据分组与 M7 证据门控能力；但 `llm_rewrite` 仍是 stub，回答生成仍以模板分支为主。M7.5 需要在不破坏现有行为与回归测试的前提下，引入可配置的真实 LLM 调用层（默认 SiliconFlow + DeepSeek-V3.2），并将调用失败显式降级到规则/模板路径。

约束：
- `llm_rewrite` 仅发生在检索前，且 `scope_mode=clarify_scope` 禁止调用。
- `llm_answer` 仅发生在检索后且 Sufficiency Gate 通过时，仅可读取本轮 `evidence_grouped`。
- 任意 LLM 异常（超时、限流、空响应）不得中断主流程。

## 目标 / 非目标

**目标：**
- 提供统一 LLM 客户端抽象（provider/model/timeout/retry），支持 rewrite 与 answer 两类调用。
- 在 rewrite 阶段实现“尝试 LLM，失败回退规则”的硬约束，并补全 `strategy_hits` 与 runlog 可追踪字段。
- 在 answer 阶段实现 evidence-grounded 生成，并确保关键结论与 `answer_citations` 可追溯映射。
- 增加配置项、回归测试与评估报告流程，满足 M7.5 验收。

**非目标：**
- 不在本里程碑引入多模型路由/自动模型选择。
- 不改变已有检索、重排、图扩展算法本身。
- 不在本阶段追求回答风格优化；优先保证约束与可追溯性。

## 决策

### 决策 1：新增 `app/llm_client.py` 统一封装调用
- 方案：定义 `LLMClient` 与请求/响应结构，内含 provider/model/timeout/retries；统一标准化错误类型（timeout/rate_limit/empty_response/unknown）。
- 选择理由：避免在 `rewrite.py` 和 `qa.py` 重复写网络调用、重试和错误映射，便于后续扩展 provider。
- 备选：
  - 直接在各模块内联 HTTP 调用：实现快但重复高、难以统一降级。
  - 引入重量 SDK：耦合较强，不利于当前项目轻量结构。

### 决策 2：Rewrite 路径采用“规则先产出 + LLM 覆盖”
- 方案：先生成 `rewrite_rule_query`，再按开关尝试 LLM；成功时写入 `rewrite_llm_query` 并作为 `rewrite_query`，失败时 `rewrite_query` 回退 `rewrite_rule_query` 并置 `rewrite_llm_fallback=true`。
- 选择理由：保证任何情况下都有可用 query，不破坏 M2/M3 语义。
- 备选：纯 LLM 改写；风险是高失败率时直接影响检索质量。

### 决策 3：Answer 路径使用“先门控后生成，再做证据策略校验”
- 方案：当 Sufficiency Gate 充分且 `answer_use_llm=true` 时，将 `question+scope_mode+evidence_grouped(+warnings)`构造成严格提示词生成 answer/citations；随后仍通过 M7 evidence policy gate 做二次约束。
- 选择理由：双层防线（生成约束 + gate 校验）可最大化降低幻觉。
- 备选：跳过 gate 直接信任 LLM citations；不满足 M7.5 强约束。

### 决策 4：配置默认保守，显式开关启用
- 方案：`rewrite_use_llm=false`、`answer_use_llm=false` 保持默认；新增 provider/model/timeout/retries/fallback 配置与 `SILICONFLOW_API_KEY` 检查。
- 选择理由：默认行为与历史回归一致，启用后可控增量发布。
- 备选：默认开启 LLM；会扩大成本与回归风险。

## 风险 / 权衡

- [风险] LLM 幻觉导致无依据结论 → [缓解] 仅传 evidence、要求 citation 子集、M7 gate 不通过则弱回答。
- [风险] 超时/限流导致链路抖动 → [缓解] `llm_timeout_ms` + `llm_max_retries` + 统一 fallback。
- [风险] 引文格式不稳定 → [缓解] 结构化输出解析与标准化，不合法即降级模板。
- [风险] 成本波动 → [缓解] 开关默认关闭、采样评估后再扩大启用比例。

## Migration Plan

1. 扩展 `PipelineConfig` 与 `configs/default.yaml`，保持默认不开启。
2. 接入 `LLMClient`，先落地 rewrite，再落地 answer（均含 fallback）。
3. 补齐测试：rewrite fallback、clarify_scope 禁用、answer citation 子集、异常降级。
4. 运行 20+20 评估并产出 `reports/m7_5_llm_rewrite_eval.md` 与 `reports/m7_5_llm_answer_eval.md`。
5. 分阶段启用（先 `rewrite_use_llm`，后 `answer_use_llm`），观察 runlog 与 warning 分布。

回滚策略：关闭 `rewrite_use_llm` 和 `answer_use_llm` 即恢复纯规则/模板路径，无需数据迁移。

## Open Questions

- SiliconFlow 在当前部署环境的限流阈值与稳定超时窗口是否需要按环境分级配置？
- `llm_answer` 结构化输出采用 JSON schema 强校验还是“文本 + 后处理提取”更稳妥？
- M7.5 报告中的 20 题样本集是否固定沉淀到仓库（便于持续回归）？
