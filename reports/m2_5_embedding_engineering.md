# M2.5 Embedding Engineering Report

## 范围与数据
- 语料: `data/processed/chunks_clean.jsonl`
- 论文数(过滤后): 30
- chunk 数(过滤后): 4042
- 中断演示: 是

## 构建耗时
- Run A (中断前): 221 ms
- Run B (断点续跑完成): 735566 ms
- Run C (再次运行): 462 ms
- embedding_build_time_ms (Run B): 735563
- 平均每 1000 chunks: 181979 ms

## Cache 命中统计
- Run A 后缓存行数: 281
- Run B: hits=317, miss=3725, api_calls=1560
- Run C: hits=4040, miss=2, api_calls=1

## 失败原因 Top-3
- input_format: 21
- server_error: 18

## 失败样本抽样 (5个)
- 44768e6771d3:00068: reason=input_format, status=400
- 44768e6771d3:00187: reason=input_format, status=400
- 4c13ce9014b6:00046: reason=input_format, status=400
- 62445b7f6828:00227: reason=input_format, status=400
- 6cd26228bc23:00180: reason=input_format, status=400

## 断点续跑对比
- Run A 强制中断后，缓存已落盘 281 条。
- Run B 从剩余 miss 继续，命中提升到 317。
- Run C 进一步验证复跑稳定性，命中为 4040，miss=2。

## 产物校验
- 向量索引: `data/indexes/vec_index_embed.json` (docs=4042, dim=32, model=Qwen/Qwen3-Embedding-8B)
- 缓存文件: `data/indexes/embedding_cache.jsonl`
- 失败日志: `data/indexes/embedding_failures.jsonl`

## 真实 Provider 复核（SiliconFlow）
- 复核日期: 2026-02-18
- 复核配置: `provider=siliconflow`，`model=Qwen/Qwen3-Embedding-8B`，`batch_size=32`，`max_requests_per_minute=120`，`max_concurrent_requests=2`
- 复核结论: 真实 API 环境下可完成构建并产出可追溯失败记录（`embedding_failures.jsonl`），断点续跑命中率呈增长趋势（Run A -> Run B -> Run C）。
