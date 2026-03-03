## 1. 数据模型与构建入口

- [x] 1.1 定义图产物结构（节点元信息、adjacent/entity 邻接表、可选权重）并实现图保存/加载函数（json 为主，pkl 可选）
- [x] 1.2 在 `app/graph_build.py` 增加 CLI 入口参数（输入路径、输出路径、threshold、top_m、front_matter 开关）

## 2. 节点过滤与实体抽取

- [x] 2.1 实现建图节点过滤：仅保留 `suppressed=false` 且非 `watermark`，默认排除 `front_matter`
- [x] 2.2 实现 entities 缺失兜底抽取（大写缩写、连字符数字、CamelCase，来源 `clean_text`）

## 3. 图边构建

- [x] 3.1 实现 adjacent 边：同论文内按 `(page_start, chunk_id)` 排序，section 优先、缺失时页序回退
- [x] 3.2 实现 entity 边：同论文共享实体数阈值建边，并按共享数排序后截断到 `top_m`

## 4. 查询 API 与质量约束

- [x] 4.1 实现 `neighbors(chunk_id, type=adjacent|entity, hop=1)` 与可选 `neighbors_with_weight` 查询接口
- [x] 4.2 增加图规模与稀疏性统计输出（如实体邻居为空原因、截断计数）以支持验收排查

## 5. 测试与验收记录

- [x] 5.1 增加单元测试：过滤规则、邻接正确性、实体边上限、图文件加载查询
- [x] 5.2 生成 M4 验收记录，覆盖随机抽样邻接/实体查询与图规模上限检查
