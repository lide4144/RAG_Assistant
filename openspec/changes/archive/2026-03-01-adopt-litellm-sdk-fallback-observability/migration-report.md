# LiteLLM Migration Comparison Report

Date: 2026-03-01

## Scope
- Rewrite + Answer LLM path migrated to route-driven configuration.
- Non-stream and stream calls emit unified diagnostics fields.
- Fallback path uses primary->backup with retry/cooldown policy.

## Observed Metrics (Test Environment)
- Fallback trigger rate: verified by unit tests for primary timeout -> backup success and cooldown activation.
- Average latency: not measured in CI; only `elapsed_ms` is emitted per call for downstream aggregation.
- Error distribution categories now normalized to: `timeout`, `rate_limit`, `http_5xx`, `network`, `other`.

## Verification Inputs
- `tests/test_llm_client_routing.py`
- `tests/test_rewrite.py`
- `tests/test_runlog_and_config.py`

## Notes
- `tests/test_m2_retrieval_qa.py` currently has existing behavior drift with Evidence Policy Gate in this repository state.
- Migration observability fields are emitted in diagnostics payload, but full production distribution requires runtime runlog aggregation.
