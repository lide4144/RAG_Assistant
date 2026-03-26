## 为什么

当前系统已经把 `LLM-first planner` 定义为线上正式顶层决策来源，但默认配置仍允许 `planner_use_llm=false`，并且在 `planner LLM` 被禁用、未配置或不可用时进入受控结束而不是显式系统阻断。这会制造一种危险错觉：系统看起来仍然“可运行”，但其核心基础设施实际上不可用。

既然本项目已经将 `planner LLM` 定义为整个 agent-first 编排、tool 选择与最终交互姿态的基础设施，那么当该基础设施缺失、失效或不满足上线前置条件时，系统必须进入明确阻断或受限不可服务状态，而不是继续暴露为一个貌似正常的聊天系统。

## 变更内容

- 将 `planner LLM` 从“可选运行时能力”升级为线上正式聊天链路的基础设施前置条件。
- **BREAKING**: 当 `planner_use_llm` 被关闭、planner 模型缺失、API key 缺失、planner runtime 无法成功调用 LLM、或运行态健康检查确认 planner LLM 不可用时，系统必须阻断正式聊天执行，而不是继续以 fallback planner / controlled terminate 伪装为可服务状态。
- 明确区分两类失败：
  - `请求级受控结束`：单轮请求在执行期被 validation 或 tool 失败收束。
  - `系统级阻断`：planner LLM 基础设施不可用，导致正式聊天入口整体不可服务。
- 调整运行态健康、可观测字段与前端/网关暴露语义，使其能够明确表达“planner LLM 基础设施未就绪”这一系统状态，而不是仅输出普通 fallback reason。
- 收紧配置治理语义：线上正式模式下，`planner.use_llm=false` 不再是可接受的正常运行配置，而应被视为阻断态或仅限显式开发/诊断模式。

## 功能 (Capabilities)

### 新增功能
<!-- 无新增 capability；本变更主要收紧现有规范边界。 -->

### 修改功能
- `capability-planner-execution`: 将 planner LLM 可用性定义为线上正式执行前置条件，并补充“系统级阻断”与“请求级失败收束”的边界。
- `llm-planner-tool-selection-policy`: 收紧 planner 正式来源要求，明确 `planner_use_llm=false`、模型缺失、密钥缺失、调用失败等情形不得继续被视为线上可服务状态。
- `planner-interaction-authority`: 明确系统级阻断不属于普通交互姿态裁决，而是高于单轮请求的服务可用性约束。
- `dependency-health-status-endpoint`: 调整健康检查与依赖状态语义，使 planner LLM 基础设施不可用时能够稳定暴露阻断信号。
- `frontend-chat-focused-experience`: 调整聊天页行为，使其在 planner LLM 阻断态下优先呈现明确不可服务状态，而不是继续允许用户进入看似可执行的会话流程。
- `gateway-agent-execution-events`: 调整网关事件语义，使 planner 基础设施阻断与普通 planner/tool fallback 可区分。
- `planner-runtime-config-persistence`: 收紧 planner runtime 配置治理，明确哪些配置组合在正式模式下构成无效或阻断状态。

## 影响

- 受影响代码主要包括 `app/planner_runtime.py`、`app/config.py`、`app/planner_runtime_config.py`、`app/kernel_api.py`、Gateway 健康检查与前端聊天入口状态映射。
- 受影响运行时行为包括聊天入口可用性判断、健康检查语义、fallback reason 分类、前端阻断提示与管理页对 planner runtime 配置的解释。
- 该变更会改变当前“planner 不可用时仍返回 controlled terminate”的容错预期，属于面向正式模式的行为收紧。
