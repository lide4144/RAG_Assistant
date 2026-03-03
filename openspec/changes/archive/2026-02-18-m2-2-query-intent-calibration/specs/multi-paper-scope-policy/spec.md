## 修改需求

### 需求:Scope Policy 指代不明处理
当问题命中指代词（如 this work/this paper/the authors/本文/这篇论文/作者）且缺少论文线索时，系统禁止默认假设某一篇论文。系统在执行跨论文模式时必须禁止向检索查询追加 `summary/in summary/overview/abstract overview/paper overview` 等 summary cue words，并必须进入意图校准流程生成 `calibrated_query`。

#### 场景:歧义问题禁用 summary cue
- **当** 问题命中指代词且未提供论文标识
- **那么** 系统必须从最终检索查询中排除 summary/overview/abstract 类 cue words

#### 场景:歧义问题生成校准查询
- **当** 问题命中指代词且采用跨论文检索模式
- **那么** 系统必须输出 `calibrated_query` 与可序列化 `calibration_reason`

## 新增需求

### 需求:意图驱动 cue words 校准
系统必须基于问题意图向 `calibrated_query` 追加语义目标 cue words。至少支持 limitation、contribution、dataset、metric 四类意图，并为每类提供中英文 cue words 追加策略。

#### 场景:limitation 意图追加
- **当** 问题命中“局限/不足/缺点/限制/future work/limitation”等词
- **那么** 系统必须向 `calibrated_query` 追加 limitation 相关中英文 cue words

#### 场景:dataset 或 metric 意图追加
- **当** 问题命中“数据集/benchmark/metric/准确率/F1”等词
- **那么** 系统必须向 `calibrated_query` 追加对应 dataset 或 metric 的中英文 cue words
