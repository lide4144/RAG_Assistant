# Rewrite + Routing Quality Eval

- total_samples: 5
- rewrite_entity_keep_rate: 1.000
- rewrite_no_concat_rate: 1.000
- route_accuracy: 1.000
- passed: True

## Alerts
- none

## Sample Details

| id | expected_intent | predicted_intent | route_correct | no_concat | lost_entities |
|---|---|---|---:|---:|---|
| r1 | continuation_control | continuation_control | True | True | [] |
| r2 | format_control | format_control | True | True | [] |
| r3 | style_control | style_control | True | True | [] |
| r4 | retrieval_query | retrieval_query | True | True | [] |
| r5 | retrieval_query | retrieval_query | True | True | [] |
