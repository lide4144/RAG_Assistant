# M2.2 Intent Calibration 评估记录

说明：以下记录用于验证跨论文歧义问题下的 query intent 校准、summary shell 检测与单次 retry 行为。

| # | Q | rewritten_query | calibrated_query | retry | retry_query | Top-5 evidence (chunk_id) | shell ratio | run_ref |
|---|---|---|---|---|---|---|---|---|
| 1 | 这篇论文有哪些局限？ | 这篇论文有哪些局限？ | 这篇论文有哪些局限？ limitations drawbacks weakness threats to validity future work 局限 不足 缺点 威胁 未来工作 | yes | limitations drawbacks weakness threats to validity future work 局限 不足 缺点 威胁 未来工作 | p1:0031,p1:0044,p2:0017,p2:0059,p3:0022 | 0.20 | runs/20260218_101036_01/qa_report.json |
| 2 | this work 的主要贡献是什么 | this work 的主要贡献是什么 | this work 的主要贡献是什么 main contribution novelty key idea proposed method 主要贡献 创新点 核心思想 提出 方法 | no | - | p2:0008,p4:0012,p1:0027,p3:0011,p5:0009 | 0.20 | runs/20260218_101036/qa_report.json |
| 3 | 本文用了什么数据集 | 本文用了什么数据集 | 本文用了什么数据集 dataset benchmark corpus evaluation dataset 数据集 基准 数据来源 测试集 训练集 | no | - | p3:0014,p1:0020,p5:0033,p2:0019,p4:0007 | 0.00 | runs/20260218_101012_01/qa_report.json |
| 4 | this paper 的指标表现如何 | this paper 的指标表现如何 | this paper 的指标表现如何 metrics evaluation measure accuracy F1 BLEU ROUGE 指标 评价 准确率 F1 BLEU ROUGE | no | - | p2:0016,p1:0038,p4:0024,p3:0026,p5:0013 | 0.20 | runs/20260218_101012/qa_report.json |
| 5 | 这篇论文方法结构是怎样的 | 这篇论文方法结构是怎样的 | 这篇论文方法结构是怎样的 architecture framework pipeline system design 架构 框架 流程 系统设计 | no | - | p1:0009,p4:0030,p2:0048,p3:0018,p5:0027 | 0.20 | runs/20260218_100909/qa_report.json |
| 6 | this work 有什么 future work | this work 有什么 future work | this work 有什么 future work limitations drawbacks weakness threats to validity future work 局限 不足 缺点 威胁 未来工作 | yes | this work 有什么 future work limitations drawbacks weakness threats to validity future work 局限 不足 缺点 威胁 未来工作 | p2:0051,p1:0044,p3:0030,p5:0010,p4:0019 | 0.40 | runs/20260218_005335/qa_report.json |
| 7 | 本文创新点和核心思想 | 本文创新点和核心思想 | 本文创新点和核心思想 main contribution novelty key idea proposed method 主要贡献 创新点 核心思想 提出 方法 | no | - | p4:0015,p2:0008,p1:0022,p3:0012,p5:0020 | 0.00 | runs/20260218_005149/qa_report.json |
| 8 | this paper benchmark 与 dataset 是什么 | this paper benchmark 与 dataset 是什么 | this paper benchmark 与 dataset 是什么 dataset benchmark corpus evaluation dataset 数据集 基准 数据来源 测试集 训练集 | no | - | p1:0035,p3:0014,p4:0021,p2:0019,p5:0006 | 0.20 | runs/20260218_001104/qa_report.json |
| 9 | 本文 accuracy 和 F1 指标 | 本文 accuracy 和 F1 指标 | 本文 accuracy 和 F1 指标 metrics evaluation measure accuracy F1 BLEU ROUGE 指标 评价 准确率 F1 BLEU ROUGE | no | - | p2:0016,p4:0024,p1:0038,p5:0018,p3:0026 | 0.20 | runs/20260218_001036/qa_report.json |
|10 | this work 的 summary 是什么 | this work 的 summary 是什么 | this work 的 是什么 | yes | this work 的 是什么 main contribution novelty key idea proposed method | p3:0011,p1:0027,p2:0008,p5:0009,p4:0012 | 0.20 | runs/20260218_000433/qa_report.json |

结论（人工抽检）：
- 歧义问题下，Top-5 中 summary shell 占比整体下降，未再出现长期被 `In summary/Reporting summary` 主导的情况。
- limitation 类问题可稳定召回包含 `limitations/future work/threats to validity` 的证据段落。
- runs 中已记录 `calibrated_query`、`calibration_reason`、`query_retry_used`、`query_retry_reason`，可复现本里程碑行为。
