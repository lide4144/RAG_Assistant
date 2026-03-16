# LLM Planner Shadow Sample Set

## High-Risk Samples

1. 多轮追问后继续追问同一论文的作者、年份与实验指标。
2. `summary` 与 `strict_fact` 混合请求，例如“总结差异并给出准确率数值”。
3. `paper_assistant` 模糊范围请求，例如“给我下一步研究建议”但未提供论文集合。
4. `control` 锚点缺失或过期后的格式化请求。
5. 明确要求联网或包含最新/最近时间信号的 web delegation 请求。

## Sample Record Shape

```json
{
  "sample_id": "shadow-001",
  "query": "帮我总结这些论文并给出下一步建议",
  "history_summary": "上一轮仍在澄清论文范围",
  "risk_tags": ["paper_assistant", "clarify", "multi_turn"],
  "expected_focus": "比较澄清策略与低置信回答策略",
  "review_label": null
}
```
