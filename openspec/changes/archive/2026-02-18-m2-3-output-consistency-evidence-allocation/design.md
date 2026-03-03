## 上下文

当前 QA 链路已经具备 M2 检索、M2.1 论文聚合与 M2.2 意图校准能力，但输出端缺少统一“后处理治理层”。表现为：`papers_ranked` 与 `evidence_grouped` 可出现不一致、`answer` 与引用 chunk 对齐不足、`scope_mode` 下回答风格不稳定。该问题跨越 `qa` 输出组装、证据分配与日志落盘，属于跨模块行为一致性问题。

约束：
- 不改动 M2 检索索引与召回主体算法。
- 不改动 M3 rewrite 模块逻辑。
- 必须保持现有 CLI 接口可用，仅扩展输出字段与策略。

## 目标 / 非目标

**目标：**
- 建立统一输出治理流程，保证 `papers_ranked`、`evidence_grouped`、`answer`、`answer_citations` 四者一致。
- 在 `rewrite_scope/open` 两种模式下提供确定的回答模板与引用约束。
- 提供证据不足降级与 warning 机制，确保“宁可少答，不可乱答”。
- 将新增治理字段完整写入 runs，以支持复现与验收。

**非目标：**
- 不优化 BM25/dense/hybrid 的打分公式与召回器实现。
- 不引入新的 LLM 回答器，仅使用规则模板完成回答组装。
- 不在本里程碑引入新的索引存储或外部服务依赖。

## 决策

### 决策 1：增加输出治理层（post-retrieval assembly）
- 决策：在检索完成后、回答生成前新增统一的输出治理步骤，负责 evidence 分配、一致性修复、citation 构建与 warning 归集。
- 原因：将输出一致性规则集中管理，避免分散在 `qa.py` 多处条件分支。
- 备选方案：
  - 方案 A：在现有 `qa.py` 直接堆叠条件分支。
  - 方案 B：抽离 `app/output_policy.py`（或同等函数模块）承载规则。
- 选择：优先 B（结构化更清晰）；若改动成本过高，可先在 `qa.py` 内部按函数拆分并保证接口稳定。

### 决策 2：paper-first 证据分配策略
- 决策：先按 paper 分组，再做每篇 top-m 截断（默认 2），最后做展示论文数截断（默认 6）。
- 原因：直接按全局 chunk 排序容易出现“单篇论文挤占全部证据”与“top paper 无展示证据”。
- 备选方案：
  - 方案 A：全局 top-k 后再回填 paper。
  - 方案 B：先 paper 聚合再分配。
- 选择：B，可天然满足“每个展示 paper 至少 1 条 evidence”的约束。

### 决策 3：scope-aware 回答模板
- 决策：`rewrite_scope` 强制跨论文聚合回答；`open` 在有明确论文线索时允许单论文回答。
- 原因：回答结构必须与 scope policy 对齐，否则会出现跨论文检索却单 chunk 指向的误导输出。
- 备选方案：统一单模板回答。
- 选择：按 scope 分流模板。

### 决策 4：显式降级与 warning 驱动可解释性
- 决策：证据不足、top paper 补证据、summary shell 仍主导等场景统一写入 `output_warnings`。
- 原因：让“系统做了何种修复/降级”可回放、可审计。
- 备选方案：仅在控制台打印提示。
- 选择：结构化写入输出与 runs。

## 风险 / 权衡

- [风险] 输出规则变严后，部分问题会触发弱回答，主观上“更保守”。  
  → 缓解：在回答中给出补充线索建议（标题/作者/年份/会议），并保留 evidence 便于用户继续追问。

- [风险] 新增规则可能与旧测试基线冲突，导致大量快照更新。  
  → 缓解：优先补行为断言测试（字段、约束、warning），减少对文案细节的脆弱依赖。

- [风险] 若 `answer_citations` 与 evidence 构建链路耦合不当，可能出现循环修补逻辑。  
  → 缓解：定义单向流水线：候选 -> 分配 -> 分组 -> citation -> answer，不允许 answer 反向改写 citation。

## 迁移计划

1. 在 QA 流程中接入输出治理函数，保持原检索入口不变。
2. 增加输出字段（`answer_citations`、`output_warnings`）并更新 runs 落盘结构。
3. 补充/更新测试：
   - papers/evidence 一致性
   - rewrite_scope/open 回答结构
   - 证据不足降级
   - citation 与 evidence 对齐
   - summary shell 仍主导 warning
4. 生成 `reports/m2_3_output_consistency.md`，按验收样例记录至少 10 条。
5. 若发现回归，按开关方式回退到旧回答模板（仅短期保底）。

## 开放问题

- `max_evidence_per_paper`、`max_papers_display` 是否进入 `configs/default.yaml` 暴露为可调参数，还是先内置默认值。
- “高噪声 evidence” 的判定是否仅基于 `content_type`（front_matter/reference），还是叠加长度/得分阈值。
