## 1. Planner 配置治理收紧

- [x] 1.1 盘点 `planner_use_llm` 在 `app/config.py`、`app/planner_runtime_config.py`、运行态概览和设置接口中的读取与暴露位置
- [x] 1.2 调整 Planner Runtime 配置模型，移除正式配置面对 `planner_use_llm` 的依赖，并为兼容历史配置保留受控读取路径
- [x] 1.3 设计并落地独立的开发/诊断模式表达方式，确保其不与正式服务模式共享可用性语义

## 2. Kernel 服务阻断门禁

- [x] 2.1 在 Kernel 聊天入口增加 planner 基础设施门禁检查，覆盖模型缺失、密钥缺失、正式模式无效配置和显式阻断态
- [x] 2.2 调整 `app/planner_runtime.py` 与 `app/kernel_api.py` 的失败语义，区分系统级阻断与请求级 `controlled_terminate`
- [x] 2.3 为系统级阻断补充稳定的 reason code、响应载荷和 trace 字段，避免复用普通 planner fallback 语义

## 3. 健康检查与运行态概览

- [x] 3.1 扩展 `/health/deps` 或等价健康接口，增加 planner LLM 可服务状态、阻断原因和正式聊天可用性字段
- [x] 3.2 调整运行态概览与管理接口，使其能明确展示 Planner Runtime 是否满足正式模式前置条件
- [x] 3.3 为历史环境和配置迁移补充清晰的阻断提示，避免“服务在线但不可聊天”的假阳性

## 4. Gateway 与前端阻断映射

- [x] 4.1 调整 Gateway agent 事件映射，确保服务级阻断与普通 planner/tool fallback 可区分
- [x] 4.2 调整聊天页状态映射和 UI 文案，在 planner LLM 阻断态下停止展示正常聊天姿态
- [x] 4.3 校准设置页或相关管理视图，使正式模式下不再暴露 `planner_use_llm` 作为合法切换项

## 5. 回归测试与验证

- [x] 5.1 为 Kernel 增加测试，覆盖 planner model 缺失、API key 缺失、正式模式非法配置时的系统级阻断
- [x] 5.2 为健康检查、Gateway 事件和前端状态映射增加测试，覆盖服务阻断与普通 fallback 的区分
- [x] 5.3 回归验证现有请求级受控结束路径，确保 validation reject、tool failure 和 runtime exception 仍保持单轮收束语义
