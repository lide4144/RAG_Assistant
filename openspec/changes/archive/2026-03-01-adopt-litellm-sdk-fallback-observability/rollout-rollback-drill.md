# Gray Rollout and Rollback Drill

Date: 2026-03-01

## Gray Rollout Plan
1. Keep `llm_use_legacy_client=false` and start with low-traffic environment.
2. Configure backup model per stage (`rewrite_llm_fallback_*`, `answer_llm_fallback_*`).
3. Monitor diagnostics fields:
   - `provider_used`, `model_used`, `attempts_used`, `fallback_reason`, `elapsed_ms`, `error_category`.
4. Validate warning compatibility in runlog output.

## Rollback Plan
1. Set `llm_use_legacy_client=true`.
2. Keep route config in place but disable fallback model fields if needed.
3. Confirm warnings and output schema remain unchanged.
4. Re-run rewrite/runlog focused test set before widening traffic.

## Drill Result
- Configuration-level rollback switch is available and validated through code path toggles.
- No process-level deployment changes required (in-process rollback only).
