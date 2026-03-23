## 新增需求

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

## 修改需求

## 移除需求
