# chunk-graph-construction 规范

## 目的
待定 - 由归档变更 m4-graph-construction 创建。归档后请更新目的。

## 需求

### 需求:仅对有效 chunk 建图
图构建流程必须仅使用 `suppressed=false` 且 `content_type != "watermark"` 的 chunk；默认应当排除 `content_type="front_matter"`，除非显式配置开启。

#### 场景:默认过滤无效与水印节点
- **当** 系统读取 `data/processed/chunks_clean.jsonl` 并构建图
- **那么** 所有 `suppressed=true` 或 `content_type="watermark"` 的 chunk 必须不进入图节点集合

#### 场景:默认排除 front_matter
- **当** 未启用 front_matter 建图配置
- **那么** `content_type="front_matter"` 的 chunk 必须不进入图节点集合

### 需求:系统必须构建同论文邻接边
系统必须在同一 `paper_id` 内按 `(page_start, chunk_id)` 排序后建立无向邻接边；若 `section` 存在，必须优先在相同 `section` 内建立邻接，否则退化为页序邻接。

#### 场景:section 存在时优先 section 邻接
- **当** 同一论文的两个相邻序位 chunk 具有不同 `section`
- **那么** 系统禁止仅因序位相邻而建立跨 section 邻接边

#### 场景:section 缺失时按页序邻接
- **当** chunk 缺少可用 `section` 信息
- **那么** 系统必须按 `(page_start, chunk_id)` 序位建立相邻 chunk 的无向边

### 需求:系统必须构建实体共现边并限制规模
系统必须在同一 `paper_id` 内为共享实体数不小于阈值（默认 1）的 chunk 建立实体共现边；每个 chunk 的实体邻居数量必须限制为 `top_m`（默认 30），并按共享实体数量降序保留。

#### 场景:满足阈值时建立实体边
- **当** 两个 chunk 在同论文内共享实体数量大于等于阈值
- **那么** 系统必须在二者间建立实体共现边

#### 场景:邻居数超过 top_m 时截断
- **当** 某个 chunk 可连接的实体邻居数量超过 `top_m`
- **那么** 系统必须仅保留共享实体数最高的前 `top_m` 个邻居

### 需求:缺失 entities 时必须规则抽取
当输入 chunk 不含 `entities` 字段时，系统必须基于 `clean_text` 进行规则实体抽取，至少覆盖：全大写缩写（长度 2~10）、连字符数字词（如 `GUESS-18`）、CamelCase。

#### 场景:缺失 entities 字段触发抽取
- **当** 输入 chunk 未提供 `entities`
- **那么** 系统必须从 `clean_text` 抽取规则实体并用于实体共现建边

### 需求:图产物必须可加载并可查询邻居
系统必须输出可加载的图文件（`graph.json` 或 `graph.pkl`），并提供查询接口 `neighbors(chunk_id, type=adjacent|entity, hop=1) -> list[chunk_id]`；可选支持权重查询接口。

#### 场景:图文件加载后可查询邻接邻居
- **当** 图构建完成并加载图产物
- **那么** 调用 `neighbors` 查询必须返回与边类型匹配的 chunk_id 列表（边界节点允许为空）
