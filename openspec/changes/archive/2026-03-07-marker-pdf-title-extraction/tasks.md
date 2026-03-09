## 1. 解析器接入与路由

- [x] 1.1 新增 `app/marker_parser.py`，封装 Marker 调用并输出统一中间表示（标题候选、块文本、层级、页码映射）
- [x] 1.2 在 `app/ingest.py` 增加 PDF 解析路由（Marker 首选、legacy 回退）与超时/异常处理
- [x] 1.3 增加配置项（启用开关、超时、标题门禁阈值）并接入 `configs/default.yaml` 与加载逻辑
- [x] 1.4 更新 `requirements.txt`，新增 Marker 及必要依赖，并标注可选安装/兼容说明

## 2. 标题质量门禁与元数据落盘

- [x] 2.1 在标题抽取流程实现黑名单过滤与候选评分，阻断占位标题写入
- [x] 2.2 扩展 `PaperRecord` 与写入逻辑，落盘 `parser_engine`、`title_source`、`title_confidence`（或等价字段）
- [x] 2.3 更新 `ingest_report.json` / run trace 生成逻辑，输出 `parser_fallback` 与失败原因字段

## 3. 分块策略联动与兼容

- [x] 3.1 在 chunk 构建前接入结构化边界优先分段，缺失时回退现有文本规则分段
- [x] 3.2 保持现有 `chunk_size` / `overlap` 约束与运行时校验，避免行为回归
- [x] 3.3 为 URL 与非 Marker 路径保持兼容，确保非 PDF 流程不受影响

## 4. 测试与质量回归

- [x] 4.1 新增单测：`Preprint. Under review.` 等黑名单标题必须被拒绝
- [x] 4.2 新增单测：Marker 失败时自动回退且导入任务不中断
- [x] 4.3 新增集成测试：`papers.json` 与 `ingest_report.json` 含新增观测字段且格式正确
- [x] 4.4 对样例语料做前后对比，记录标题修复率与关键检索/答案回归结果

## 5. 历史数据修复与发布

- [x] 5.1 提供按 `paper_id` 增量重建标题与元数据的修复脚本
- [x] 5.2 完成小批量灰度重跑并验证回滚开关可用
- [x] 5.3 更新 README/运维文档，说明 Marker 依赖安装、开关与故障排查
