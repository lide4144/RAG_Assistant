## ADDED Requirements
<!-- 无 -->

## MODIFIED Requirements

### 需求:缺失 entities 时必须规则抽取
当输入 chunk 不含 `entities` 字段时，系统必须基于 `clean_text` 调用 LLM 进行结构化实体抽取，并强制模型输出可被 Pydantic 校验的 JSON 结果，至少包含 `entity_name` 与 `entity_type`。

#### 场景:缺失 entities 字段触发 LLM 抽取
- **当** 输入 chunk 未提供 `entities`
- **那么** 系统必须从 `clean_text` 触发 LLM 结构化抽取并将通过校验的实体用于实体共现建边

#### 场景:LLM 输出不合法时执行降级
- **当** LLM 返回非 JSON 或不满足实体 schema
- **那么** 系统必须将该 chunk 视为抽取失败并降级为可继续处理的空实体结果，且禁止中断全量构图

#### 场景:批量抽取必须受并发限制
- **当** 系统并发处理多个缺失实体的 chunk
- **那么** 系统必须通过受控并发（如信号量配合 `asyncio.gather`）调用 LLM，且禁止无上限并发请求

## REMOVED Requirements
<!-- 无 -->
