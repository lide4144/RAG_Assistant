## 1. Sufficiency Gate 核心改造

- [x] 1.1 修改 `app/sufficiency.py` 中的 `_is_insufficient_evidence` 函数，将 `min_evidence` 从 2 改为 1
- [x] 1.2 修改证据不足但有 1 条证据时的决策逻辑，返回 `decision: "answer"` 和 `answer_mode: "low_confidence_with_model_knowledge"`
- [x] 1.3 在 Sufficiency Gate 返回值中新增 `answer_mode`、`allows_model_knowledge`、`confidence_level` 字段
- [x] 1.4 添加单元测试验证新的证据阈值逻辑

## 2. Session State 用户偏好存储

- [x] 2.1 在 `app/session_state.py` 中新增 `user_honesty_preferences` 数据结构定义
- [x] 2.2 实现 `load_user_honesty_preferences` 函数，支持从 session 读取用户偏好
- [x] 2.3 实现 `save_user_honesty_preference` 函数，支持保存"不再提示"选择
- [x] 2.4 添加偏好自动重置逻辑（新会话或 24 小时后）
- [x] 2.5 添加单元测试验证偏好存储和重置逻辑

## 3. 回答生成流程改造

- [x] 3.1 修改 `app/qa.py` 中的 `_build_answer` 函数，识别 `answer_mode: "low_confidence_with_model_knowledge"`
- [x] 3.2 当证据不足时，修改 LLM 系统提示，允许使用模型知识并强制要求内联标注
- [x] 3.3 实现内联标注格式 `[📄 chunk_id]` 和 `[🤖 模型推测]` 的生成逻辑（通过 LLM 系统提示实现）
- [x] 3.4 在 trace 输出中新增 `answer_confidence` 字段，包含 level、source、evidence_coverage、uncertainty_reasons
- [x] 3.5 在 trace 输出中新增 `honesty_disclosure` 字段，包含 should_show、type、severity、title、message、evidence_stats、suggested_actions
- [x] 3.6 根据用户偏好设置 `honesty_disclosure.should_show` 值
- [x] 3.7 添加集成测试验证完整的低置信度回答流程

## 4. 向后兼容与边界处理

- [x] 4.1 确保所有新增字段都是可选的，不破坏现有 API 契约
- [x] 4.2 验证当证据为 0 条时，系统仍然返回拒绝（不进入模型知识模式）
- [x] 4.3 验证现有前端可以正常忽略新字段工作
- [x] 4.4 添加回归测试确保原有功能不受影响

## 5. 测试与验证

- [x] 5.1 创建测试用例：1 条证据时触发模型知识补充
- [x] 5.2 创建测试用例：0 条证据时仍然拒绝
- [x] 5.3 创建测试用例：内联标注格式正确性验证
- [x] 5.4 创建测试用例：用户偏好"不再提示"功能
- [x] 5.5 创建测试用例：结构化置信度数据完整性验证
- [x] 5.6 运行完整回归测试套件（21 个测试全部通过）
- [x] 5.7 手动测试验证端到端流程

## 6. 文档更新

- [x] 6.1 更新 API 文档，说明新增的 `answer_confidence` 和 `honesty_disclosure` 字段（创建了 docs/soft-evidence-api.md）
- [x] 6.2 在代码中添加关键函数的 docstring 说明（已在 session_state.py 中添加）
- [x] 6.3 更新配置说明（如有新增配置项）（无需新增配置项）
