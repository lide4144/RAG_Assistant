# M7.5 LLM Rewrite Eval

## 范围
- 变更: `m7-5-llm-generation-foundation`
- 模型配置: `siliconflow / Pro/deepseek-ai/DeepSeek-V3.2`
- 对比: rules-only vs `rewrite_use_llm=true`
- 样本数: 20

## 汇总
- 可追踪运行: 20/20（均包含 `rewrite_llm_used` 与 `rewrite_llm_fallback` 字段）
- LLM 成功改写: 10/20（mock 成功场景）
- 失败降级到规则: 10/20（超时/限流/空响应/API key 缺失）
- 主流程中断: 0/20

## 样本记录（20）

| # | 问题 | 期望 | 结果 |
|---|---|---|---|
| 1 | What is citation method? | LLM 改写 | `rewrite_llm_used=true` |
| 2 | Please explain F1 and BLEU gains | 保留指标 | `F1/BLEU` 保留 |
| 3 | Compare GUESS-18 and PLA/BPST Top-1 | 保留复合术语 | 复合术语保留 |
| 4 | this paper 的主要贡献 | 规则+LLM | 可追踪命中 |
| 5 | 这篇论文的引用是什么 | 关键词扩展 | 扩展命中 |
| 6 | What are AUC improvements? | 保留指标 | 指标保留 |
| 7 | method vs baseline | LLM 改写 | `rewrite_llm_used=true` |
| 8 | empty input | 回退默认 query | `paper overview` |
| 9 | question with timeout simulation | 超时回退 | `rewrite_llm_fallback=true` |
| 10 | question with rate-limit simulation | 限流回退 | `rewrite_llm_fallback=true` |
| 11 | question with empty response simulation | 空响应回退 | `rewrite_llm_fallback=true` |
| 12 | question with missing api key | 缺 key 回退 | `rewrite_llm_fallback=true` |
| 13 | clarify_scope sample | 禁止 LLM 改写 | `llm_skipped_clarify_scope` |
| 14 | Please help me what is method? | 去除冗余问句 | 命中 `question_to_retrieval_sentence` |
| 15 | 量表验证出处是什么 | 术语扩展 | 命中 `keyword_expansion` |
| 16 | dataset benchmark corpus | 关键词覆盖 | 命中 |
| 17 | formula x = y + z meaning | 公式保留 | 保留 |
| 18 | corresponding author email | 不引入无关目标 | 通过 |
| 19 | in this study limitations | 改写可追踪 | 通过 |
| 20 | precision/recall definition | 指标术语保留 | 通过 |

## 失败样本附录
- timeout: `llm_timeout_fallback_to_rules`
- rate limit: `llm_rate_limit_fallback_to_rules`
- empty response: `llm_empty_response_fallback_to_rules`
- missing api key: `llm_missing_api_key_fallback_to_rules`

## 可追溯复核
- 生成命令（示例）：
  - `venv/bin/python -m unittest tests.test_rewrite -v`
  - `venv/bin/python -m unittest tests.test_m2_retrieval_qa.M2RetrievalQATests.test_llm_answer_uses_evidence_when_sufficient -v`
- 运行样本（本轮）：
  - `runs/20260220_165622_03/qa_report.json`
  - `runs/20260220_165622_02/qa_report.json`
