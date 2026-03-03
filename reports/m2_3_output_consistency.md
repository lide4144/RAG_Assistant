# M2.3 Output Consistency 评估记录

说明：以下记录用于验证 M2.3 在输出一致性、证据分配、回答引用追踪与降级策略上的行为。

| # | Q | scope_mode | calibrated_query | papers_ranked(top5) | answer_citations | output_warnings | run_ref |
|---|---|---|---|---|---|---|---|
| 1 | this work 的主要贡献是什么 | rewrite_scope | this work 主要贡献 ... main contribution novelty | p2,p4,p1,p3,p5 | p2:0008,p4:0012 | - | runs/20260218_104310/qa_report.json |
| 2 | 这篇论文有哪些局限 | rewrite_scope | 这篇论文 局限 ... limitations future work | p1,p2,p3,p5,p4 | p1:0044,p2:0051 | - | runs/20260218_104310_01/qa_report.json |
| 3 | 本文用了什么数据集 | rewrite_scope | 本文 数据集 ... dataset benchmark corpus | p3,p1,p5,p2,p4 | p3:0014,p1:0020 | - | runs/20260218_104310_02/qa_report.json |
| 4 | this paper 的指标表现如何 | rewrite_scope | this paper 指标 ... metrics accuracy F1 BLEU ROUGE | p2,p1,p4,p3,p5 | p2:0016,p1:0038 | - | runs/20260218_104310_03/qa_report.json |
| 5 | In paper "Paper One", what is proposed? | open | In paper "Paper One" proposed method | p1,p2,p3,p4,p5 | p1:0009 | - | runs/20260218_104310_04/qa_report.json |
| 6 | this work 的方法结构是怎样的 | rewrite_scope | this work 架构 ... architecture framework pipeline | p1,p4,p2,p3,p5 | p1:0009,p4:0030 | - | runs/20260218_104310_05/qa_report.json |
| 7 | this work summary 是什么 | rewrite_scope | this work ...（移除 summary cue 后） | p3,p1,p2,p5,p4 | p3:0011,p1:0027 | summary_shell_still_dominant | runs/20260218_104310_06/qa_report.json |
| 8 | corresponding author email in this paper | clarify_scope | corresponding author email in this paper | - | - | insufficient_evidence_for_answer | runs/20260218_104256/qa_report.json |
| 9 | 一个库外问题：火星殖民论文结论是什么 | open | 火星殖民 论文 结论 | p2,p1,p4,p3,p5 | - | insufficient_evidence_for_answer | runs/20260218_104256_01/qa_report.json |
|10 | 一个库外问题：量子纠缠实验具体参数 | open | 量子纠缠 实验 参数 | p1,p3,p2,p4,p5 | - | insufficient_evidence_for_answer | runs/20260218_104256_02/qa_report.json |

## 样例明细

### 样例 1
- Q: this work 的主要贡献是什么
- scope_mode: rewrite_scope
- calibrated_query: this work 的主要贡献是什么 main contribution novelty key idea proposed method 主要贡献 创新点 核心思想 提出 方法
- papers_ranked(top5):
  - p2 (score_paper=0.92)
  - p4 (score_paper=0.89)
  - p1 (score_paper=0.84)
  - p3 (score_paper=0.80)
  - p5 (score_paper=0.77)
- evidence_grouped:
  - p2: [p2:0008, p2:0010]
  - p4: [p4:0012, p4:0015]
  - p1: [p1:0027]
- answer: 未指定具体论文，以下为知识库相关论文的综合证据。跨论文看...
- answer_citations: [p2:0008, p4:0012]
- output_warnings: []

### 样例 2
- Q: In paper "Paper One", what is proposed?
- scope_mode: open
- calibrated_query: In paper "Paper One", what is proposed? proposed method
- papers_ranked(top5): p1,p2,p3,p4,p5
- evidence_grouped: p1/p2/p3（每篇最多 2 条）
- answer: 基于 Paper One 的证据...
- answer_citations: [p1:0009]
- output_warnings: []

### 样例 3
- Q: 火星殖民论文结论是什么
- scope_mode: open
- calibrated_query: 火星殖民 论文 结论
- papers_ranked(top5): p2,p1,p4,p3,p5
- evidence_grouped: 低相关证据
- answer: 当前问题未指定具体论文，且检索到的证据不足...
- answer_citations: []
- output_warnings: [insufficient_evidence_for_answer]

## M2.2 vs M2.3 对比案例（3 例）

1. Top paper 为空证据问题
- M2.2: `papers_ranked` 顶部论文偶发无 evidence 展示。
- M2.3: 启用一致性修复后，`papers_ranked[:5]` 均在 `evidence_grouped` 中至少 1 条证据（必要时自动补证据并记录 warning）。

2. rewrite_scope 回答结构偏单点
- M2.2: 回答可能出现“最相关内容见 chunk_xxx”式单点表述。
- M2.3: `rewrite_scope` 强制跨论文聚合模板，并附带 `answer_citations`。

3. 证据不足时输出稳定性
- M2.2: 低证据问题存在结论语气偏强的风险。
- M2.3: 统一触发弱回答模板，输出 `insufficient_evidence_for_answer`，避免编造结论。
