## ADDED Requirements

### 需求:LLM 失败诊断对象必须统一建模
系统必须为 `rewrite` 与 `answer` 两个 LLM 阶段输出结构化失败诊断对象；对象必须至少包含 `stage`、`provider`、`model`、`reason`、`status_code`、`attempts_used`、`max_retries`、`elapsed_ms`、`fallback_warning`。

#### 场景:answer 阶段超时触发诊断落盘
- **当** answer LLM 调用超时并触发模板降级
- **那么** 系统必须在运行产物中写入 `stage=answer` 的诊断对象，且 `reason=timeout`、`fallback_warning=llm_answer_timeout_fallback_to_template`

#### 场景:rewrite 阶段限流触发诊断落盘
- **当** rewrite LLM 调用返回 429 并触发规则降级
- **那么** 系统必须在运行产物中写入 `stage=rewrite` 的诊断对象，且 `reason=rate_limit`、`status_code=429`

### 需求:诊断日志必须可审计且不泄露敏感信息
系统必须保证失败诊断字段可用于排障审计，同时禁止写入 API key、完整提示词、完整响应正文等敏感数据。

#### 场景:落盘字段合规
- **当** 生成任意一条 LLM 失败诊断日志
- **那么** 诊断对象必须仅包含约定字段与必要摘要信息，且不得包含密钥与完整 prompt/response 内容

### 需求:fallback warning 与诊断对象必须一致
当 `output_warnings` 出现 LLM fallback warning 时，系统必须存在一条对应阶段、对应 reason 的诊断对象。

#### 场景:warning 与诊断一致
- **当** `output_warnings` 包含 `llm_answer_timeout_fallback_to_template`
- **那么** 运行产物必须同时包含 `stage=answer`、`reason=timeout` 的诊断对象
