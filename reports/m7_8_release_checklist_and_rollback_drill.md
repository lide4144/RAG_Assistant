# M7.8 发布检查清单与回滚演练记录

日期：2026-02-27

## 发布检查清单

- [x] UI 导入反馈显示成功/失败数量
- [x] UI 导入反馈展示结构化失败原因与下一步建议
- [x] 用户视图展示论文级摘要导航（不替代 citation）
- [x] citation 交互仍可定位到 chunk 证据
- [x] 高级调试信息仅在开发者面板可见
- [x] 双层检索与语义匹配回归测试已补齐
- [x] Redis 并发隔离与状态恢复回归测试已补齐
- [x] 重写质量与语义路由准确率评测脚本已提供
- [x] citation 合规回归测试已补齐（引用需可追溯至 chunk）

## 一键回滚方案

```bash
scripts/rollback_to_legacy_gate.sh
```

执行后会：

1. 备份当前 `configs/default.yaml`
2. 将 `configs/paper_assistant_growth_legacy.yaml` 覆盖为新的 `configs/default.yaml`

## 回滚演练记录

演练时间：2026-02-27

### 演练步骤

1. 执行 `scripts/rollback_to_legacy_gate.sh`
2. 校验 `configs/default.yaml` 已切换为 legacy gate 配置
3. 启动一次 QA（使用默认配置）确认系统可运行
4. 记录备份文件路径，确保可恢复到演练前配置

### 演练结果

- 状态：已执行
- 执行记录：
  - 回滚命令输出：`[OK] rolled back to legacy gate config.`
  - 备份文件：`configs/default.yaml.bak.20260227161512`
  - 配置校验：`cmp -s configs/default.yaml configs/paper_assistant_growth_legacy.yaml` 返回 `0`（一致）
  - QA 冒烟：`python3 -m app.qa --q "请给出当前知识库的概览" --mode hybrid --top-k 3 --top-evidence 2` 返回 `0`，运行目录 `runs/20260227_161533`
  - 恢复步骤：`cp configs/default.yaml.bak.20260227161512 configs/default.yaml` 已执行
- 结论：单命令回滚与恢复链路可用，满足“可一键切回旧路径”要求。
