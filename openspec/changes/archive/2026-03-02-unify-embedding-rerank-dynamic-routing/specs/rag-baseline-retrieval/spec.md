## MODIFIED Requirements

### 需求:Dense backend 必须可配置并默认使用 embedding
系统必须支持 `dense_backend: embedding|tfidf` 配置，默认值必须为 `embedding`。当 `dense_backend=embedding` 且 embedding stage 不可用（例如密钥缺失、连通失败、维度不一致）时，系统必须自动降级到 `tfidf` 路径并保持 CLI/接口语义不变。

#### 场景:embedding 不可用时自动回退
- **当** 用户以 `--mode dense|hybrid` 运行且 embedding stage 返回不可用
- **那么** 系统必须回退到 TF-IDF 检索路径并返回可用候选

## ADDED Requirements

### 需求:检索链路必须记录 embedding 降级原因
当检索链路从 embedding 回退到词频检索时，系统必须在运行日志记录降级原因（至少区分 `missing_api_key`、`network_error`、`timeout`、`dimension_mismatch`）与是否成功回退。

#### 场景:降级原因可追踪
- **当** 一次查询发生 embedding 回退
- **那么** 运行日志必须包含降级原因分类与回退结果字段，且字段可序列化

