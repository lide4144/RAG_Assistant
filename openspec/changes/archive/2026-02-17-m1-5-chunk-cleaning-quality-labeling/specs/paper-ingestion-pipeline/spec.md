## 新增需求

### 需求:Chunk 清洗与质量标注输出
系统必须基于 `data/processed/chunks.jsonl` 生成 `data/processed/chunks_clean.jsonl`，并为每条记录新增 `clean_text`、`content_type`、`quality_flags`、`section`（可空）字段，且必须保留原始 `text` 字段不变。

#### 场景:生成清洗后文件
- **当** 用户执行 chunk 清洗流程并输入 `data/processed/chunks.jsonl`
- **那么** 系统必须产出 `data/processed/chunks_clean.jsonl`，并为每条记录写入新增字段

### 需求:水印行过滤
系统必须在生成 `clean_text` 时删除包含以下子串的整行，匹配必须不区分大小写：`Authorized licensed use limited to`、`Downloaded on`、`IEEE Xplore`、`Restrictions apply`。

#### 场景:命中水印关键词的行被删除
- **当** 某 chunk 文本中某一行包含任一水印关键词
- **那么** 系统必须从 `clean_text` 中删除该整行

### 需求:URL 归一化与标记
系统必须将 `http://` 或 `https://` 链接归一化为 `<URL>`，并在 `quality_flags` 中追加 `has_url`。

#### 场景:chunk 含 URL
- **当** chunk 文本包含至少一个 HTTP/HTTPS 链接
- **那么** `clean_text` 中该链接必须替换为 `<URL>`，且 `quality_flags` 必须包含 `has_url`

### 需求:控制符清除与空白折叠
系统必须将不可见控制字符替换为空格，并折叠连续空白为单个空格或单个换行边界，以保证 `clean_text` 可读性。

#### 场景:文本含控制字符与多重空白
- **当** chunk 文本包含控制字符或连续空白
- **那么** 系统必须在 `clean_text` 中完成控制符清除与空白折叠

### 需求:乱码检测标记
系统必须计算 `weird_char_ratio`，当其大于 `0.35` 时，必须在 `quality_flags` 中追加 `garbled`，且禁止删除原始文本字段。

#### 场景:乱码比例超阈值
- **当** 某 chunk 的 `weird_char_ratio > 0.35`
- **那么** `quality_flags` 必须包含 `garbled`，并保留该 chunk 原始 `text`

### 需求:内容类型分类
系统必须基于规则对每个 chunk 赋值 `content_type`，并至少支持：`appendix`、`dialogue_script`、`reference`、`front_matter`、`watermark`、`formula_block`、`body`。

#### 场景:附录识别
- **当** 文本命中 `APPENDIX`
- **那么** `content_type` 必须为 `appendix`

#### 场景:对话脚本识别
- **当** 文本命中 `Player Choices`、`If the player chooses` 或 `Character:`
- **那么** `content_type` 必须为 `dialogue_script`

#### 场景:参考文献识别
- **当** 文本命中期刊与年份卷期页码模式
- **那么** `content_type` 必须为 `reference`

#### 场景:前置信息识别
- **当** 文本命中邮箱 `@` 或学校/单位信息模式
- **那么** `content_type` 必须为 `front_matter`

#### 场景:水印类型识别
- **当** 文本命中水印关键词
- **那么** `content_type` 必须为 `watermark`

#### 场景:公式块识别
- **当** 文本命中 `Eq.`、`(1)(2)(3)` 或高密度符号模式
- **那么** `content_type` 必须为 `formula_block`

#### 场景:默认正文类型
- **当** 文本不命中任何专门类型规则
- **那么** `content_type` 必须为 `body`

### 需求:同页短碎片合并
系统必须按 `paper_id + page_start` 分组并按 `chunk_id` 顺序扫描；当出现连续条目满足 `len(text)<=40` 且连续数量 `>=6` 时，必须合并为一个 `table_list` block chunk。合并结果必须将条目以换行拼接到 `clean_text`，并在 `quality_flags` 追加 `short_fragment_merged`；系统可选输出 `merged_from` 保存来源 `chunk_id` 列表。

#### 场景:连续短碎片达到阈值
- **当** 同页连续短碎片数量达到或超过 6
- **那么** 系统必须输出一个 `content_type=table_list` 的合并 block，并追加 `short_fragment_merged`

## 修改需求

### 需求:chunk 数据结构
系统必须将解析结果写入 `chunks.jsonl`，且每个 chunk 记录必须包含 `chunk_id`、`paper_id`、`page_start`、`text` 字段。系统还必须支持输出 `chunks_clean.jsonl` 作为增强数据集，增强记录必须包含 `clean_text`、`content_type`、`quality_flags`、`section`（可空）字段。

#### 场景:任意 chunk 记录结构校验
- **当** 读取 `chunks.jsonl` 的任意一行并解析为对象
- **那么** 该对象必须包含 `chunk_id`、`paper_id`、`page_start`、`text`，且 `text` 不得为空字符串

#### 场景:清洗后 chunk 记录结构校验
- **当** 读取 `chunks_clean.jsonl` 的任意一行并解析为对象
- **那么** 该对象必须包含 `chunk_id`、`paper_id`、`page_start`、`text`、`clean_text`、`content_type`、`quality_flags`，且允许 `section` 为空

### 需求:最小稳定性验收
系统必须支持对至少 20 篇论文完成处理且流程无崩溃，以满足 M1 的最小可用验收要求。系统还必须通过 M1.5 指定样例断言，以证明清洗与标注规则有效。

#### 场景:20 篇论文批处理
- **当** 输入目录中存在至少 20 篇可处理论文
- **那么** 系统必须完成运行并输出结果文件，且进程不得异常退出

#### 场景:M1.5 样例断言通过
- **当** 执行 M1.5 验收检查
- **那么** 系统必须满足以下结果：`eff6f9d4b754:00109` 不含水印字符串；`eff6f9d4b754:00094` URL 归一化且含 `has_url`；`eff6f9d4b754:00093` 为 `reference`；`eff6f9d4b754:00095` 为 `dialogue_script`；`67978670bdb6:00004` 为 `front_matter`

## 移除需求
