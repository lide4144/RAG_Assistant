## 为什么

当前系统存在多处**代替大模型（LLM）生成回答**的硬编码逻辑。当用户请求开放式总结（如"关键贡献对比表"）时，系统直接拼接证据片段并返回机械化的格式化回复，而非调用 LLM 生成自然语言回答。这导致用户体验差，回复缺乏智能感，仿佛在与机器人而非智能助手对话。

## 变更内容

### 核心变更

1. **移除代替 LLM 的硬编码回答函数** (BREAKING)
   - 删除 `_build_assistant_summary_answer` - 不再直接拼接证据生成机械化回复
   - 删除 `compose_catalog_answer` 的硬编码输出路径 - 目录查询结果必须通过 LLM 生成自然语言回答
   - 删除 `_build_claim_plan` - 证据不足时不再返回硬编码计划

2. **强制所有回答经过 LLM**
   - 所有用户查询的回答必须由 LLM 生成
   - 证据片段作为上下文提供给 LLM，而非直接输出
   - 证据不足时，LLM 基于已有证据生成回答并附加风险提示

3. **统一错误和建议消息处理**
   - 错误消息保持硬编码（系统级错误）
   - 用户可见的建议和解释由 LLM 生成或从模板库动态渲染

### 具体文件修改

- `app/qa.py`: 移除 `_build_assistant_summary_answer`, `_build_claim_plan`, `_build_structure_coverage_notice` 等函数
- `app/capability_planner.py`: 修改 `compose_catalog_answer` 移除硬编码输出
- `app/generate.py`: 重构 `build_answer` 函数
- `app/planner_runtime.py`: 保留错误消息硬编码，但统一风格

## 功能 (Capabilities)

### 新增功能
- `llm-response-generation`: 基于证据上下文的 LLM 回答生成规范，定义如何将检索到的证据作为上下文传递给 LLM

### 修改功能
- `cross-doc-summary`: 修改需求，要求所有跨文档总结必须通过 LLM 生成，禁止直接证据拼接输出
- `catalog-lookup`: 修改需求，目录查询结果必须通过 LLM 生成自然语言回答

## 影响

### 受影响的代码文件
- `app/qa.py` - 主要修改文件，删除多个硬编码回答函数
- `app/capability_planner.py` - 修改目录查询回答生成逻辑
- `app/generate.py` - 重构回答生成入口
- `app/sufficiency.py` - 调整建议消息的生成方式

### API 变化
- 无外部 API 变化，仅内部实现调整

### 依赖变化
- 增加对 LLM 服务的依赖（所有回答路径都必须能调用 LLM）
- 需要确保 LLM 降级路径优雅处理（当 LLM 不可用时返回友好的错误提示而非崩溃）

### 用户体验影响
- **正面**: 所有回答将更加自然、智能，符合用户期望
- **潜在负面**: LLM 调用增加，响应时间可能略有增加；需要确保降级机制完善

### 测试需求
- 需要验证所有回答路径都经过 LLM
- 需要验证证据作为上下文正确传递给 LLM
- 需要验证 LLM 不可用时的降级行为
