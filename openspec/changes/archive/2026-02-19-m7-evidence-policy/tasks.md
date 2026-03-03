## 1. 规则与数据契约落地

- [x] 1.1 在回答后处理流程中新增关键结论识别步骤（数字句、实验结果句、定义句、结论句）
- [x] 1.2 扩展 citation 校验器，强制关键结论至少绑定 1 条含 `chunk_id` 与 `section_page` 的 citation
- [x] 1.3 增加 citation 可定位校验，要求每条关键结论引用能在 `evidence_grouped` 定位到同 `chunk_id`
- [x] 1.4 统一失败码与 warning 映射，未通过项落盘为 `insufficient_evidence_for_answer`

## 2. 门控与回答降级实现

- [x] 2.1 在 answer assembly 后接入 claim-citation coverage check，并阻断未覆盖关键结论
- [x] 2.2 接入 M8 Sufficiency Gate 触发逻辑（缺 citation、不可定位、语义不一致）
- [x] 2.3 实现门控后的弱回答输出路径，确保禁止强断言并保留补充线索提示
- [x] 2.4 增加开关 `evidence_policy_enforced`，支持紧急降级为仅告警模式

## 3. 验收与回归

- [x] 3.1 新增自动验收脚本，校验 30 个问题回答的 citations 完整率为 100%
- [x] 3.2 新增抽检导出工具，输出 10 条回答的关键结论、citation、chunk 片段用于人工核验
- [x] 3.3 编写单元/集成测试覆盖关键场景：覆盖通过、citation 不可定位、语义不一致、触发 M8
- [x] 3.4 在 CI 中接入 M7 回归任务并输出失败样例明细
