# M7.8 Meta-question 意图重写护栏评估

生成方式：`venv/bin/python scripts/eval_m7_8_meta_guard.py`

## 1. standalone_query 优化前后对比（10 例）

| # | sample_id | run_id(before) | run_id(after) | 场景输入（次轮） | 优化前（问题） | 优化后（M7.8） |
|---|---|---|---|---|---|---|
| 1 | m78-01 | `runs/m78_baseline_01` | `runs/m78_guard_01` | Why does it lack of evidences? | Transformer 有什么用处 由什么组成 Why does it lack of evidences? | Transformer 详细架构 内部组件 机制 |
| 2 | m78-02 | `runs/m78_baseline_02` | `runs/m78_guard_02` | 你没回答全，为什么？ | Transformer 有什么用处 由什么组成 你没回答全 为什么 | Transformer 详细架构 内部组件 机制 |
| 3 | m78-03 | `runs/m78_baseline_03` | `runs/m78_guard_03` | 再找找具体组成 | Transformer 有什么用处 再找找具体组成 | Transformer 详细架构 内部组件 机制 |
| 4 | m78-04 | `runs/m78_baseline_04` | `runs/m78_guard_04` | 没有证据吗 | RAG 没有证据吗 | RAG 详细架构 内部组件 机制 |
| 5 | m78-05 | `runs/m78_baseline_05` | `runs/m78_guard_05` | why no evidence | RAG what is it why no evidence | RAG detailed architecture internal components mechanism |
| 6 | m78-06 | `runs/m78_baseline_06` | `runs/m78_guard_06` | 回答不完整，补充下 | this work 回答不完整 补充下 | this work 详细架构 内部组件 机制 |
| 7 | m78-07 | `runs/m78_baseline_07` | `runs/m78_guard_07` | still no proof? | what method is proposed still no proof | method detailed architecture internal components mechanism |
| 8 | m78-08 | `runs/m78_baseline_08` | `runs/m78_guard_08` | 你是不是没找到证据 | 这篇论文 你是不是没找到证据 | 这篇论文 详细架构 内部组件 机制 |
| 9 | m78-09 | `runs/m78_baseline_09` | `runs/m78_guard_09` | please find more concrete components | Transformer please find more concrete components | Transformer detailed architecture internal components mechanism |
| 10 | m78-10 | `runs/m78_baseline_10` | `runs/m78_guard_10` | lack of evidences, retry | RAG lack of evidences retry | RAG detailed architecture internal components mechanism |

判定结果：10/10 样本未出现机械拼接 query，10/10 样本满足实体约束。

## 2. Evidence 命中质量变化

评估口径：以样本清单中的 `hit_depth_improved` 标注计算。

- 命中深度提升：8/10
- 噪声比例下降：10/10（以去除机械拼接与状态词污染为代理）

## 3. Gate 触发变化

统计口径：同一批样本在优化前后 `insufficient_evidence_for_answer` 的触发比例。

- 优化前：7/10（70%）
- 优化后：4/10（40%）
- 变化：下降 3 个样本

