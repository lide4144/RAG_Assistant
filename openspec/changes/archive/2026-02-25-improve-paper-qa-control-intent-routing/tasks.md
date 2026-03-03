## 1. 意图路由基础

- [x] 1.1 在 `app/qa.py` 增加 `intent_type` 判定入口与路由分支（retrieval/style/format/continuation）
- [x] 1.2 在 `app/config.py` 与 `configs/default.yaml` 增加 `intent_router_enabled` 及默认值
- [x] 1.3 在 trace 中新增 `intent_type`、`topic_query_source` 字段并通过序列化校验

## 2. 控制意图主题锚定

- [x] 2.1 在 `app/session_state.py` 提供控制意图可复用的 `anchor_query` 构建逻辑
- [x] 2.2 增加 `style_control_reuse_last_topic` 与 `style_control_max_turn_distance` 配置并接入运行流程
- [x] 2.3 在控制意图场景将 `rewrite_query/query_used` 切换为锚定主题，禁止控制词直入检索

## 3. 改写与 Gate 协同

- [x] 3.1 在 `app/rewrite.py` 增加控制意图防误改写逻辑（控制词不作为独立检索 query）
- [x] 3.2 在 `run_sufficiency_gate` 调用链接入 `topic_query_source`，控制意图使用 `anchor_query` 参与 topic match
- [x] 3.3 为锚点缺失或超限场景增加澄清分支与统一 reason 文案

## 4. 可视化与可观测

- [x] 4.1 在 `app/ui.py` 调试面板展示 `intent_type`、`anchor_query`、`topic_query_source`
- [x] 4.2 为控制意图 + refuse/clarify 场景补充高亮展示，便于定位误拒答

## 5. 测试与回归

- [x] 5.1 在 `tests/test_rewrite.py` 增加“用中文回答我/简短点/继续”不作为检索 query 的用例
- [x] 5.2 在 `tests/test_m7_6_multi_turn.py` 增加控制意图主题继承与超距澄清用例
- [x] 5.3 在 `tests/test_m8_sufficiency_gate.py` 增加控制意图场景 topic_match 输入来源断言
- [x] 5.4 更新相关 README/报告中的新增字段与验收口径
