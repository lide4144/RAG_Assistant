## 1. Token 与扩展逻辑加固

- [x] 1.1 调整 `TOKEN_RE` 以支持中文词段与复合术语（`-`、`/`）
- [x] 1.2 实现同义词 key 统一小写与英文复数轻量归一（仅词典命中时生效）
- [x] 1.3 增加中文词典 key 子串命中逻辑，提升中文 query 扩展触发率

## 2. 关键词质量与命中语义

- [x] 2.1 增加最小中英停用词过滤，减少关键词预算噪声占用
- [x] 2.2 将 `keyword_expansion` 命中改为“实际新增扩展词”驱动

## 3. 测试与回归验证

- [x] 3.1 补充中文扩展与复合术语保留的单测场景
- [x] 3.2 运行 `tests/test_rewrite.py` 并确认通过
- [x] 3.3 运行受影响回归测试（`tests/test_m2_retrieval_qa.py`、`tests/test_runlog_and_config.py`）并确认通过
