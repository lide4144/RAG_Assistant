# paper-summary-artifacts 规范

## 目的
待定 - 由归档变更 auto-ingest-pdf-wechat-knowledge-base 创建。归档后请更新目的。
## 需求
### 需求:系统必须为每篇文档持久化论文级摘要产物
系统必须在文档入库成功后为每篇文档生成并持久化一条 `paper_summary` 记录，记录至少包含 `paper_id/doc_id`、`title`、`one_paragraph_summary`、`key_points`、`keywords`、`source_uri`、`summary_version`。

#### 场景:入库成功后生成摘要产物
- **当** 一篇 PDF 或 URL 文档完成入库并具备可用正文
- **那么** 系统必须写入对应 `paper_summary` 记录，且字段完整可读取

### 需求:系统必须维护摘要新鲜度与可重建标识
系统必须为每条 `paper_summary` 记录保存与正文快照关联的标识（例如 `chunk_snapshot_hash` 或等价字段），用于判断摘要是否过期并支持重建。

#### 场景:正文变更后标记摘要过期
- **当** 同一文档的正文快照标识发生变化
- **那么** 系统必须将旧摘要标记为过期或触发重建流程

### 需求:系统必须支持论文级摘要检索读取
系统必须提供面向检索层的 `paper_summary` 读取能力，以支持按主题或关键词召回候选文档。

#### 场景:按关键词召回候选文档
- **当** 用户问题命中某些摘要关键词
- **那么** 系统必须返回包含对应文档标识的候选列表供下游 chunk 检索使用

