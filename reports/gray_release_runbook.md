# Gray Release and Rollback Runbook

## Target
Validate gradual rollout from legacy rewrite strategy to arbitration strategy, with one-command rollback.

## Pre-check
1. Verify FastAPI kernel health: `curl http://127.0.0.1:8000/health`
2. Verify gateway health: `curl http://127.0.0.1:8080/health`
3. Confirm config flags in `configs/default.yaml`:
   - `rewrite_parallel_candidates_enabled: true`
   - `rewrite_arbitration_enabled: true`
   - `rewrite_legacy_strategy_enabled: false`

## Gray phases
1. **Phase A (10%)**
   - Keep arbitration enabled.
   - Sample a subset of sessions by routing key in gateway.
   - Monitor: citation coverage, clarify rate, first-token latency.
2. **Phase B (50%)**
   - Expand traffic if phase A has no regression.
3. **Phase C (100%)**
   - Set as default entry strategy.

## Rollback drill
1. Toggle `rewrite_legacy_strategy_enabled: true`.
2. Reload services.
3. Re-run smoke QA and compare metrics.
4. If stable, keep legacy mode until issue analysis completes.

## Acceptance criteria
- No citation-mapping invalid errors in smoke sample.
- Citation coverage not lower than baseline by >5%.
- Clarify rate increase <= 3%.
- First token latency increase <= 15%.
