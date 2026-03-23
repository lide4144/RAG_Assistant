# llm-runtime-config-persistence 规范

## 目的
待定 - 由归档变更 add-llm-visual-config-and-model-detection 创建。归档后请更新目的。
## 需求
### 需求:系统必须持久化 LLM 路由配置
系统必须提供持久化结构保存管理员选择的路由配置，并支持读取最新生效配置。持久化配置必须覆盖 `answer`、`embedding`、`rerank`、`rewrite` 与 `graph_entity` 五个位点，每个位点至少包含 `provider`、`api_base`、`api_key` 与 `model`。系统必须支持向后兼容旧格式配置并映射到新结构。

#### 场景:保存后读取多 stage 配置
- **当** 管理员保存全模型位点配置
- **那么** 系统必须在后续读取时返回完整位点结构且字段语义一致

### 需求:系统必须保护敏感配置输出
系统必须在日志和 API 响应中对 `api_key` 做脱敏处理，禁止明文回显。

#### 场景:保存接口返回
- **当** 保存接口返回配置摘要
- **那么** 系统必须仅返回脱敏后的 key 信息

### 需求:系统必须保证配置异常时可回退
系统在持久化配置缺失、损坏或校验失败时必须回退到静态默认配置，禁止因配置异常导致路由整体不可用。

#### 场景:持久化配置损坏
- **当** 运行时读取到无效持久化配置
- **那么** 系统必须记录告警并回退到静态配置继续服务

### 需求:系统必须兼容旧单路配置载荷
系统在接收旧格式 `api_base/api_key/model` 载荷时必须继续可用，并将其映射到三路持久化结构，以避免历史客户端立即失效。

#### 场景:旧客户端调用保存接口
- **当** 客户端仅提交 `api_base/api_key/model`
- **那么** 系统必须成功保存并生成可被三路读取接口消费的配置结构

### 需求:系统必须消除单一环境变量硬依赖
系统必须通过 stage 配置的 `api_key_env` 解析密钥，禁止把 `SILICONFLOW_API_KEY` 作为唯一默认依赖。若某 stage 未配置可用密钥，系统必须仅影响该 stage 并返回可观测告警，禁止拖垮其他 stage。

#### 场景:embedding 缺失 key 不影响 answer
- **当** embedding 未配置可用 API key 且 answer 配置完整
- **那么** 系统必须保持 answer 路由可用，并将 embedding 标记为不可用或降级

### 需求:系统必须消除 rewrite 对 answer 的隐式覆盖
系统必须将 `rewrite` 视为独立位点并单独生效，禁止在配置加载阶段强制使用 `answer` 路由覆盖 `rewrite` 路由。

#### 场景:rewrite 与 answer 使用不同模型
- **当** 管理员将 `rewrite` 与 `answer` 配置为不同模型
- **那么** 系统必须按各自位点配置生效，且不得在加载时将 rewrite 覆盖为 answer

### 需求:系统必须将 LLM runtime 配置纳入统一治理语义
系统必须将 LLM runtime 配置视为统一配置治理模型中的 `runtime` owner 字段集合，而不是孤立的特殊配置机制。系统必须明确 `answer`、`embedding`、`rerank`、`rewrite`、`graph_entity` 与 `sufficiency_judge` 六个 stage 的运行时配置仅覆盖其所属字段，并必须与静态基线配置形成可解释的回退关系。

#### 场景:读取 LLM 运行时配置的治理属性
- **当** 系统加载 `answer`、`embedding`、`rerank`、`rewrite`、`graph_entity` 或 `sufficiency_judge` 的运行时配置
- **那么** 系统必须能够将这些字段解释为 runtime owner，并在缺失或失效时回退到静态基线或安全默认值

### 需求:系统必须提供一致的字段来源可观测性
系统必须对 LLM runtime 配置相关字段提供一致的来源说明语义，使管理员能够判断当前 stage 使用的是静态基线、runtime 持久化配置还是环境强覆盖。禁止继续把字段来源信息散落为仅内部可知的实现细节。

#### 场景:管理员查看 stage 生效来源
- **当** 管理员查看某个 LLM stage 的当前生效配置
- **那么** 系统必须能够用一致语义说明其来源为 `default`、`runtime`、`env` 或回退状态

