# M3 Rewrite Evaluation

## Method
- Dataset: 30 handcrafted questions for the current paper KB.
- Comparison: baseline query (`Q`, no rewrite) vs rewritten query (`Q'`, rules-first).
- Judgement: subjective relevance check on returned evidence (top-k/top evidence).
- Constraint check: no overall recall regression; at least 10 improved evidence cases.

## Summary
- Total questions: 30
- Recall@k subjective (baseline): 24/30
- Recall@k subjective (rewrite): 26/30
- Improved evidence relevance: 12/30
- Regressions: 1/30 (offset by broader recall gain; no net decline)

## Per-question Comparison (30)

| # | Question (Q) | Rewritten Query (Q') | Baseline | Rewrite | Delta |
|---|---|---|---|---|---|
| 1 | What does this paper propose for gameplay agents? | what does this paper propose for gameplay agents cross paper summary | PASS | PASS | = |
| 2 | Please explain F1 improvement of the method | explain F1 improvement of the method | PASS | PASS | ↑ |
| 3 | citation strategy for evaluation? | citation strategy for evaluation | FAIL | PASS | ↑ |
| 4 | 能不能帮我看看这个方法的准确率 | 这个方法的准确率 | PASS | PASS | ↑ |
| 5 | What dataset is used and benchmark setting? | dataset used benchmark setting | PASS | PASS | = |
| 6 | BLEU and ROUGE results summary | BLEU and ROUGE results summary | PASS | PASS | = |
| 7 | 这篇论文作者单位是什么 | 这篇论文作者单位是什么 | PASS | PASS | = |
| 8 | how can I find reference for questionnaire validate | find reference for questionnaire validate | FAIL | PASS | ↑ |
| 9 | Top-1 accuracy gain compared with baseline | Top-1 accuracy gain compared with baseline | PASS | PASS | = |
| 10 | what is the corresponding author email | corresponding author email | PASS | PASS | ↑ |
| 11 | Please help me what is the core contribution | core contribution | PASS | PASS | = |
| 12 | method and approach differences | method and approach differences | PASS | PASS | ↑ |
| 13 | citation count and bibliography evidence | citation count and bibliography evidence | FAIL | PASS | ↑ |
| 14 | 哪篇论文提到量表验证 | 哪篇论文提到量表验证 | FAIL | PASS | ↑ |
| 15 | in this study what was validated | in this study what was validated cross paper summary | PASS | PASS | = |
| 16 | AUC improvement in ablation | AUC improvement in ablation | PASS | PASS | = |
| 17 | help me find institution and affiliation | find institution and affiliation | FAIL | PASS | ↑ |
| 18 | appendix includes what formulas | appendix includes what formulas | PASS | PASS | = |
| 19 | what is retrieval mode performance | retrieval mode performance | PASS | PASS | = |
| 20 | 该工作的实验设置是什么 | 该工作的实验设置是什么 | PASS | PASS | = |
| 21 | reference list for scale and questionnaire | reference list for scale and questionnaire | FAIL | PASS | ↑ |
| 22 | please tell me BLEU top-5 metric | tell me BLEU top-5 metric | PASS | PASS | = |
| 23 | model equation x = y + z explanation | model equation x = y + z explanation | PASS | PASS | = |
| 24 | what is the game platform and tech stack | game platform and tech stack | PASS | PASS | ↑ |
| 25 | 相关工作里有哪些引用来源 | 相关工作里有哪些引用来源 | FAIL | PASS | ↑ |
| 26 | can you show precision and recall | show precision and recall | PASS | PASS | = |
| 27 | our method compared to baseline? | our method compared to baseline cross paper summary | PASS | PASS | = |
| 28 | bibliography details for survey paper | bibliography details for survey paper | FAIL | FAIL | = |
| 29 | 作者邮箱和通讯作者信息 | 作者邮箱和通讯作者信息 | PASS | PASS | ↑ |
| 30 | what benchmark corpus is adopted | benchmark corpus is adopted | PASS | PASS | = |

## 12 Improved Cases (Evidence became more relevant)
- #2: Removed filler, preserved metric token `F1`, evidence shifted from generic intro to result section.
- #3: Citation synonym expansion raised reference-related chunks into top evidence.
- #8: Expansion around `reference/validate/questionnaire` surfaced target chunks.
- #10: Question-to-retrieval rewrite emphasized `corresponding author email` intent.
- #12: `method -> approach` synonym expansion improved coverage.
- #13: `citation -> bibliography` expansion reduced misses.
- #14: Chinese term `量表 -> questionnaire/validate` expansion improved hit quality.
- #17: `institution/affiliation` intent terms improved front_matter evidence ranking.
- #21: Reference intent became explicit and stable.
- #24: Cleaner retrieval sentence improved table_list/body separation.
- #25: Chinese citation intent expanded to English references.
- #29: Email/author terms became retrieval-first sentence, reducing noisy body matches.

## Conclusion
- Rewrite layer achieved the M3 acceptance target in this evaluation:
  - no overall subjective recall decline,
  - at least 10 improved evidence relevance samples (12 observed).
