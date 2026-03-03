# output-consistency-evidence-allocation 规范

## 目的
待定 - 由归档变更 m2-3-output-consistency-evidence-allocation 创建。归档后请更新目的。
## 需求
### 需求:输出字段一致性
系统必须输出统一 QA JSON 结构，并且必须包含 `question`、`mode`、`scope_mode`、`query_used`、`rewrite_rule_query`、`rewrite_llm_query`、`rewrite_llm_used`、`rewrite_llm_fallback`、`calibrated_query`、`papers_ranked`、`evidence_grouped`、`answer`、`answer_citations`、`final_decision`、`output_warnings`。当启用流式回答时，必须额外包含流式观测字段并保证类型可序列化。

#### 场景:输出字段齐全
- **当** QA 流程完成一次回答生成
- **那么** 最终 JSON 必须包含基础字段；若启用流式则必须包含对应流式观测字段

### 需求:paper 与 evidence 一致性修复
系统必须保证 `papers_ranked` 前 N（默认 5）中的每篇论文都在 `evidence_grouped` 中至少有 1 条证据。若 Top paper 无证据，系统必须自动补选该 paper 的最高分 supporting chunk，并在 `output_warnings` 增加 `top_paper_has_no_evidence_fixed`。

#### 场景:Top paper 无证据时自动修复
- **当** `papers_ranked[0]` 对应论文在 `evidence_grouped` 中证据为空
- **那么** 系统必须补入至少 1 条来自该论文 `supporting_chunks` 的证据并记录修复 warning

### 需求:证据分配上限与来源约束
系统必须执行 evidence 分配策略：每篇论文最多 `max_evidence_per_paper`（默认 2）条、最少 1 条（当该论文被展示时）；`evidence_grouped` 最多展示 `max_papers_display`（默认 6）篇；证据必须来自该论文 `supporting_chunks`，且 quote 必须来自原始 `text` 字段。

#### 场景:按论文限额分配证据
- **当** 候选证据覆盖超过 6 篇论文或单篇论文超过 2 条高分证据
- **那么** 系统必须按配置截断并保持每个展示论文至少 1 条证据

#### 场景:quote 来源受控
- **当** 系统生成 evidence quote
- **那么** quote 必须来自原始 `text`，长度应在 50~120 字之间；若原文不足允许短 quote 但不得为空

### 需求:回答引用可追溯
系统必须继续输出 `answer_citations` 并映射至 `evidence_grouped` 的 chunk 证据；当映射不完整时，系统必须输出低置信提示与补充说明，不得直接将摘要层内容作为最终引用。

#### 场景:引用映射不完整时给出低置信提示
- **当** 回答中存在无法完整映射的引用项
- **那么** 系统必须标记低置信状态并提示用户进一步确认来源

### 需求:证据不足降级
系统必须将证据不足降级流程改为“语义相似度主判定驱动”，并在输出中保留可解释理由与建议追问；系统可选接入 LLM 复核，但不得覆盖语义判定的可观测结果。

#### 场景:语义判定为 clarify
- **当** 语义判定显示缺失关键信息且可继续追问
- **那么** 系统必须输出面向用户语义的澄清问题与缺口说明

#### 场景:语义判定为 refuse
- **当** 语义判定显示当前证据无法支持回答
- **那么** 系统必须输出拒答说明并提示补充资料来源

### 需求:M7 验收检查必须可执行
系统必须提供可执行的 M7 验收检查流程：
1) 对 30 个问题运行自动检查，要求回答输出均包含 citations；
2) 对 10 个回答提供抽检材料，能从被引用 chunk 中找到语义一致支撑。

#### 场景:自动检查 30 题引用完整
- **当** 执行 M7 自动验收脚本并输入 30 个问题集
- **那么** 脚本结果必须显示 30/30 回答包含 citations，且失败样例必须输出问题与缺失字段详情

#### 场景:人工抽检 10 条可追溯
- **当** 执行抽检导出流程并随机抽取 10 条回答
- **那么** 系统必须输出每条回答的关键结论、citation 与对应 chunk 片段，支持人工核验语义一致性

### 需求:summary shell 仍主导时告警
当 M2.2 已执行 summary cue 抑制后，若 Top evidence 的 summary shell 占比仍超过 60%，系统必须在输出中记录 `summary_shell_still_dominant`。

#### 场景:retry 后仍被 shell 主导
- **当** query retry 后 Top evidence 的 summary shell 占比仍大于 60%
- **那么** 系统必须追加 `summary_shell_still_dominant` 到 `output_warnings`

### 需求:证据充分时必须支持 LLM 约束生成
系统必须在 Sufficiency Gate 判定证据充分且 `answer_use_llm=true` 时，支持基于本轮 `evidence_grouped` 的 LLM 生成回答；若 LLM 调用失败必须降级到模板回答，并记录失败诊断信息用于排障。

#### 场景:证据充分触发 LLM 回答
- **当** `answer_use_llm=true` 且 Sufficiency Gate 判定充分
- **那么** 系统必须尝试 `llm_answer_with_evidence`，并仅使用本轮 `evidence_grouped` 作为事实来源

#### 场景:LLM 回答失败降级模板
- **当** `llm_answer_with_evidence` 调用超时、限流、空响应、HTTP 错误、网络异常或解析失败
- **那么** 系统必须回退到模板回答路径并保持流程不中断，同时输出与失败原因一致的 answer 诊断对象

### 需求:流式回答观测字段必须可追踪
当回答阶段启用流式时，系统必须输出可追踪字段（至少包含流式是否启用、是否实际走流、首字延迟或回退原因），用于运行审计与容量分析。

#### 场景:流式启用时字段落盘
- **当** `answer_stream_enabled=true` 且本轮回答执行结束
- **那么** 运行产物必须包含流式观测字段，并与 warning/diagnostics 语义一致

### 需求:系统必须支持轻量语义相似度证据判定
系统在日常助手模式下必须使用轻量级 Embedding 模型计算问题与候选证据的余弦相似度，并将语义分数作为证据充分性主判定依据，禁止继续使用纯 Token 交集作为唯一主判定。

#### 场景:语义判定返回结构化决策
- **当** 系统完成证据组织并进入回答前判定
- **那么** 系统必须基于语义相似度产出结构化决策（`answer/refuse/clarify`、`reason`、`missing_aspects`）

### 需求:系统必须支持可配置阈值而非硬编码阈值
系统必须将语义判定阈值配置化（例如 strict/balanced/explore 配置档），禁止将单一固定阈值硬编码为所有场景默认门槛。

#### 场景:切换策略档位生效
- **当** 运维将门控策略从 `balanced` 切换为 `explore`
- **那么** 系统必须按新阈值执行判定并在观测字段中体现当前策略

