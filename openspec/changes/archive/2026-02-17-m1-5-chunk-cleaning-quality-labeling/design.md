## 上下文

当前流水线已能从 PDF 产出 `chunks.jsonl`，但 chunk 文本仍含水印噪声、URL、控制符、疑似乱码与表格碎片化内容，直接进入 BM25/向量检索会降低稳定性。本次变更在不破坏现有 `chunks.jsonl` 与 CLI 行为前提下，引入一个入库后清洗与标注层，产出 `chunks_clean.jsonl` 供检索阶段使用。

约束：
- 保留原始 `text`，不对原始输入做破坏性覆盖。
- 新增字段必须可被下游读取，但不强制立即替换全部下游逻辑。
- 规则需可复现、可测试，并支持对指定样例 chunk 的确定性断言。

## 目标 / 非目标

**目标：**
- 对每个 chunk 生成 `clean_text`，并输出 `content_type`、`quality_flags`、`section`（可空）。
- 完成六类规则实现：水印行过滤、URL 归一化、控制符清理、乱码标记、content_type 分类、同页短碎片合并。
- 新增 `data/processed/chunks_clean.jsonl`，并保证对检索融合可配置降权（`table_list` 默认 *0.5）但仍可作为证据引用。
- 提供针对验收样例的自动化校验。

**非目标：**
- 不改写 `data/processed/chunks.jsonl` 的结构和生成方式。
- 不引入机器学习分类器；`content_type` 仅采用规则法。
- 不在本次变更实现完整检索算法重构，仅加入最小必要降权钩子。

## 决策

1. 采用“两阶段文本处理”：
- 阶段 A：行级处理（去水印、URL 替换、控制符清理）。
- 阶段 B：记录级处理（乱码比率、content_type、quality_flags）。
- 理由：行级规则先执行可稳定后续统计，减少分类噪声。
- 备选：一次性正则流水线；缺点是可调试性和规则可维护性较差。

2. 采用“非破坏性增强输出”：
- 输出保留原字段，并新增 `clean_text/content_type/quality_flags/section`。
- 理由：下游可渐进迁移，不阻断现有流程。
- 备选：直接替换 `text`；缺点是审计和回溯困难。

3. `content_type` 采用优先级规则匹配：
- 建议优先级：`watermark > dialogue_script > reference > front_matter > appendix > formula_block > body`。
- 理由：避免多标签冲突时结果不稳定。
- 备选：无优先级并行命中；缺点是需要复杂冲突消解。

4. 短碎片合并按页内连续窗口实现：
- 对同一 `paper_id + page_start`、按 `chunk_id` 排序扫描，连续 `len(text)<=40` 且数量 `>=6` 合并为 `table_list`。
- 合并后 `clean_text` 按换行拼接，打 `short_fragment_merged`，可选保留 `merged_from`。
- 理由：匹配表格/列表碎片的主要噪声模式，并控制误合并范围。
- 备选：全局按词频聚类；复杂度高且解释性差。

5. 检索融合降权只对 `table_list` 生效：
- 融合分数乘 0.5（配置化），但不从候选集中剔除。
- 理由：降低噪声召回影响，同时保留“列举类问题”证据价值。
- 备选：直接过滤；会损失“游戏/平台/技术栈”类问答召回。

## 风险 / 权衡

- [规则误判导致 content_type 偏差] -> 通过优先级和样例回归测试控制；后续可补充白名单/黑名单。
- [短碎片合并误伤正文短句] -> 严格限制在同页连续 >=6 条且长度阈值 40，降低误触发。
- [水印过滤过强误删有效行] -> 仅匹配给定关键词子串，不做泛化模糊删除。
- [检索降权影响特定查询召回] -> 仅降权不删除，并允许在配置中调节系数。

## 迁移计划

1. 新增清洗模块（建议 `app/clean_chunks.py`）并支持 CLI：
   `python -m app.clean_chunks --input data/processed/chunks.jsonl --out data/processed/chunks_clean.jsonl`
2. 在 ingest 完成后可选调用清洗步骤，或由独立命令执行（优先独立命令，降低耦合）。
3. 在检索融合逻辑中读取 `content_type`，对 `table_list` 应用降权因子。
4. 增加测试：
   - 规则级单元测试（6 大规则）
   - 样例断言测试（题述 5 条必须通过）
   - 合并逻辑测试（连续阈值、边界条件）

回滚策略：
- 若出现问题，可停用清洗输出并继续使用原 `chunks.jsonl`；该变更不破坏历史数据。

## 开放问题

- `weird_char_ratio` 的字符集合定义是否需要按中英文分别调整阈值。
- `section` 字段在 M1.5 是否只置空，还是先做轻量标题回填。
- `table_list` 降权系数是否固定 0.5，或暴露为配置项（推荐配置化）。
