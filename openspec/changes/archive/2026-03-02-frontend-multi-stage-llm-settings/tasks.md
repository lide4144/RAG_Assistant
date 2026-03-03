## 1. 运行时配置与接口契约升级

- [x] 1.1 扩展 `app/admin_llm_config.py` 运行时配置模型为 `answer/embedding/rerank` 三路结构并保留旧单路载荷兼容解析
- [x] 1.2 更新 `app/kernel_api.py` 的 `/api/admin/llm-config` GET/POST 契约以支持三路请求与三路响应摘要
- [x] 1.3 更新 `app/config.py` 运行时配置覆盖逻辑，使 `answer/rewrite`、`embedding`、`rerank` 均可从持久化配置生效
- [x] 1.4 为运行时配置与接口契约补充/更新单元测试（保存、读取、兼容旧结构、异常回退）

## 2. 前端三路配置面板实现

- [x] 2.1 重构 `frontend/components/chat-shell.tsx` 的 LLM 设置状态模型，支持 answer/embedding/rerank 三组字段
- [x] 2.2 将设置 UI 从单路表单升级为三路分组表单，并保留模型探测与保存入口
- [x] 2.3 调整前端提交与回填逻辑，使用三路配置请求/响应结构并处理单 stage 错误提示
- [x] 2.4 确保保存后刷新页面可正确回显三路最新配置

## 3. 测试与文档收敛

- [x] 3.1 更新前端 e2e 测试 `frontend/tests/llm-settings-panel.spec.ts` 覆盖三路配置保存与回显流程
- [x] 3.2 为后端补充 `auth_failed`、三路契约和兼容分支的回归测试
- [x] 3.3 更新运维/使用文档，说明三路配置字段、兼容策略与后续弃用计划
