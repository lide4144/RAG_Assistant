## MODIFIED Requirements

### 需求:Embedding 配置必须完全来自配置文件
系统必须从配置或运行时配置读取 embedding 路由参数（provider、base_url、model、api_key_env、batch_size、normalize、cache_enabled、cache_path），并通过统一 stage 路由解析后生效。系统禁止在 embedding 路径硬编码固定 provider 或固定环境变量名。

#### 场景:加载 stage=embedding 路由配置
- **当** 系统启动 query embedding 或索引构建流程
- **那么** 系统必须按 stage 路由加载并解析 embedding 配置，且不得强依赖 `SILICONFLOW_API_KEY`

## ADDED Requirements

### 需求:Embedding 回退模型必须满足维度一致性守卫
系统在 embedding 主备模型切换时必须校验向量维度与目标索引维度一致。若维度不一致，系统必须禁止进入向量检索分支并触发词频检索降级。

#### 场景:主备维度不一致触发降级
- **当** embedding 备用模型输出维度与主索引维度不一致
- **那么** 系统必须跳过向量检索并降级到 TF-IDF/BM25，且记录 `dimension_mismatch` 诊断

### 需求:Embedding API 失败后必须支持词频静默降级
当 embedding API 在重试后仍失败时，系统必须优先静默降级到词频检索；仅在运行上下文明确禁止降级时才允许抛出可识别的不可恢复异常。

#### 场景:重试耗尽后降级词频检索
- **当** embedding API 发生超时或 5xx 且达到最大重试次数
- **那么** 系统必须自动切换到 TF-IDF/BM25 检索并保持请求链路可继续执行

