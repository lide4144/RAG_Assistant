from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib import error, request

from app.llm_routing import (
    classify_error_category,
    is_in_cooldown,
    is_recoverable,
    register_route_failure,
    register_route_success,
)


try:  # pragma: no cover - optional dependency in CI/dev sandboxes
    import litellm
except Exception:  # pragma: no cover
    litellm = None

_EVENT_CALLBACKS: list[Callable[[dict[str, Any]], None]] = []

_LITELLM_PROVIDER_PREFIXES = {
    "openai",
    "azure",
    "anthropic",
    "ollama",
    "openrouter",
    "vertex_ai",
    "xai",
    "huggingface",
    "novita",
    "vercel_ai_gateway",
}


def register_llm_event_callback(callback: Callable[[dict[str, Any]], None]) -> None:
    _EVENT_CALLBACKS.append(callback)


def clear_llm_event_callbacks() -> None:
    _EVENT_CALLBACKS.clear()


def _emit_event(event: dict[str, Any]) -> None:
    for callback in list(_EVENT_CALLBACKS):
        try:
            callback(event)
        except Exception:
            # Observability callback failures must not impact LLM flow.
            pass


@dataclass
class LLMCallResult:
    ok: bool
    content: str | None
    reason: str | None
    status_code: int | None = None
    attempts_used: int = 0
    max_retries: int = 0
    elapsed_ms: int = 0
    timestamp: str | None = None
    provider_used: str | None = None
    model_used: str | None = None
    fallback_reason: str | None = None
    error_category: str | None = None


@dataclass
class LLMStreamResult(LLMCallResult):
    first_token_latency_ms: int | None = None
    chunks_received: int = 0
    stream_events: list[dict[str, Any]] | None = None


def _provider_endpoint(provider: str, api_base: str | None = None) -> str | None:
    explicit = str(api_base or "").strip()
    if explicit:
        base = explicit.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"
    normalized = (provider or "").strip().lower()
    if normalized == "siliconflow":
        return "https://api.siliconflow.cn/v1/chat/completions"
    return None


def _litellm_model_name(provider: str, model: str) -> str:
    normalized_provider = str(provider or "").strip().lower()
    raw_model = str(model or "").strip()
    if not raw_model:
        return raw_model
    if normalized_provider not in _LITELLM_PROVIDER_PREFIXES:
        return raw_model
    if raw_model.startswith(f"{normalized_provider}/"):
        return raw_model
    return f"{normalized_provider}/{raw_model}"


def _iso_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _base_result(
    *,
    ok: bool,
    content: str | None,
    reason: str | None,
    t0: float,
    retries: int,
    status_code: int | None = None,
    attempts_used: int = 0,
    provider_used: str | None = None,
    model_used: str | None = None,
    fallback_reason: str | None = None,
    error_category: str | None = None,
) -> LLMCallResult:
    return LLMCallResult(
        ok=ok,
        content=content,
        reason=reason,
        status_code=status_code,
        attempts_used=max(0, int(attempts_used)),
        max_retries=max(0, int(retries)),
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        timestamp=_iso_now(),
        provider_used=provider_used,
        model_used=model_used,
        fallback_reason=fallback_reason,
        error_category=error_category,
    )


def _base_stream_result(
    *,
    ok: bool,
    content: str | None,
    reason: str | None,
    t0: float,
    retries: int,
    status_code: int | None = None,
    attempts_used: int = 0,
    provider_used: str | None = None,
    model_used: str | None = None,
    fallback_reason: str | None = None,
    error_category: str | None = None,
    first_token_latency_ms: int | None = None,
    chunks_received: int = 0,
    stream_events: list[dict[str, Any]] | None = None,
) -> LLMStreamResult:
    return LLMStreamResult(
        ok=ok,
        content=content,
        reason=reason,
        status_code=status_code,
        attempts_used=max(0, int(attempts_used)),
        max_retries=max(0, int(retries)),
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        timestamp=_iso_now(),
        provider_used=provider_used,
        model_used=model_used,
        fallback_reason=fallback_reason,
        error_category=error_category,
        first_token_latency_ms=(None if first_token_latency_ms is None else max(0, int(first_token_latency_ms))),
        chunks_received=max(0, int(chunks_received)),
        stream_events=stream_events,
    )


def _legacy_call_chat_completion(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_ms: int,
    temperature: float,
    t0: float,
    retries: int,
    provider: str,
) -> LLMCallResult:
    payload = {
        "model": model,
        "temperature": float(temperature),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    timeout_s = max(0.1, float(timeout_ms) / 1000.0)
    req = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            status_code = int(resp.status)
            raw = resp.read().decode("utf-8", errors="replace")
        if status_code >= 400:
            return _base_result(
                ok=False,
                content=None,
                reason="rate_limit" if status_code == 429 else "http_error",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                error_category=classify_error_category("http_error", status_code),
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return _base_result(
                ok=False,
                content=None,
                reason="invalid_json_response",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                error_category="other",
            )
        choices = parsed.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return _base_result(
                ok=False,
                content=None,
                reason="empty_response",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                error_category="other",
            )
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message", {}) if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        text = str(content or "").strip()
        if not text:
            return _base_result(
                ok=False,
                content=None,
                reason="empty_response",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                error_category="other",
            )
        return _base_result(
            ok=True,
            content=text,
            reason=None,
            status_code=status_code,
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
        )
    except error.HTTPError as exc:
        code = int(exc.code or 0)
        reason = "rate_limit" if code == 429 else "http_error"
        return _base_result(
            ok=False,
            content=None,
            reason=reason,
            status_code=code,
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            error_category=classify_error_category(reason, code),
        )
    except (TimeoutError, socket.timeout):
        return _base_result(
            ok=False,
            content=None,
            reason="timeout",
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            error_category="timeout",
        )
    except error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            return _base_result(
                ok=False,
                content=None,
                reason="timeout",
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                error_category="timeout",
            )
        return _base_result(
            ok=False,
            content=None,
            reason="network_error",
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            error_category="network",
        )
    except Exception:
        return _base_result(
            ok=False,
            content=None,
            reason="unknown_error",
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            error_category="other",
        )


def _litellm_call_chat_completion(
    *,
    api_key: str,
    model: str,
    api_base: str | None,
    system_prompt: str,
    user_prompt: str,
    timeout_ms: int,
    temperature: float,
    t0: float,
    retries: int,
    provider: str,
) -> LLMCallResult:
    if litellm is None:
        return _base_result(
            ok=False,
            content=None,
            reason="litellm_unavailable",
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            error_category="other",
        )
    litellm_model = _litellm_model_name(provider, model)
    try:
        resp = litellm.completion(
            model=litellm_model,
            api_key=api_key,
            api_base=api_base,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=float(temperature),
            timeout=max(0.1, float(timeout_ms) / 1000.0),
        )
        status_code = getattr(resp, "status_code", None)
        choices = getattr(resp, "choices", None)
        if not isinstance(choices, list) or not choices:
            return _base_result(
                ok=False,
                content=None,
                reason="empty_response",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=litellm_model,
                error_category="other",
            )
        first = choices[0]
        message = getattr(first, "message", None)
        content = getattr(message, "content", None)
        text = str(content or "").strip()
        if not text:
            return _base_result(
                ok=False,
                content=None,
                reason="empty_response",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=litellm_model,
                error_category="other",
            )
        return _base_result(
            ok=True,
            content=text,
            reason=None,
            status_code=status_code,
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=litellm_model,
        )
    except Exception as exc:  # pragma: no cover - covered via patched exceptions in tests
        err_name = exc.__class__.__name__.lower()
        status_code = int(getattr(exc, "status_code", 0) or 0) or None
        msg = str(exc).lower()
        if "rate" in err_name or "429" in msg or status_code == 429:
            reason = "rate_limit"
        elif "timeout" in err_name or "timed out" in msg:
            reason = "timeout"
        elif "apierror" in err_name and status_code and 500 <= status_code < 600:
            reason = "http_error"
        elif "connection" in err_name or "network" in err_name:
            reason = "network_error"
        else:
            reason = "unknown_error"
        return _base_result(
            ok=False,
            content=None,
            reason=reason,
            status_code=status_code,
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=litellm_model,
            error_category=classify_error_category(reason, status_code),
        )


def _call_completion_once(
    *,
    provider: str,
    model: str,
    api_key: str,
    api_base: str | None,
    system_prompt: str,
    user_prompt: str,
    timeout_ms: int,
    retries: int,
    temperature: float,
    t0: float,
    use_litellm_sdk: bool,
    use_legacy_client: bool,
) -> LLMCallResult:
    if use_litellm_sdk and not use_legacy_client:
        res = _litellm_call_chat_completion(
            api_key=api_key,
            model=model,
            api_base=api_base,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_ms=timeout_ms,
            temperature=temperature,
            t0=t0,
            retries=retries,
            provider=provider,
        )
        if res.ok or res.reason != "litellm_unavailable":
            return res
    endpoint = _provider_endpoint(provider, api_base)
    if not endpoint:
        return _base_result(
            ok=False,
            content=None,
            reason="unsupported_provider",
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            error_category="other",
        )
    return _legacy_call_chat_completion(
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_ms=timeout_ms,
        temperature=temperature,
        t0=t0,
        retries=retries,
        provider=provider,
    )


def call_chat_completion(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    system_prompt: str,
    user_prompt: str,
    timeout_ms: int,
    max_retries: int,
    temperature: float = 0.0,
    api_base: str | None = None,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
    fallback_api_key: str | None = None,
    fallback_api_base: str | None = None,
    router_retry: int | None = None,
    router_cooldown_sec: int = 0,
    router_failure_threshold: int = 1,
    use_litellm_sdk: bool = True,
    use_legacy_client: bool = False,
) -> LLMCallResult:
    t0 = time.perf_counter()
    retries = max(0, int(router_retry if router_retry is not None else max_retries))
    attempts_used = 0

    routes: list[dict[str, str | None]] = [
        {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "api_base": api_base,
        }
    ]
    if str(fallback_model or "").strip():
        routes.append(
            {
                "provider": fallback_provider or provider,
                "model": fallback_model,
                "api_key": fallback_api_key,
                "api_base": fallback_api_base or api_base,
            }
        )

    prior_failure: str | None = None
    last_failure: LLMCallResult | None = None

    for route_idx, route in enumerate(routes):
        route_provider = str(route.get("provider") or provider)
        route_model = str(route.get("model") or model)
        route_api_key = route.get("api_key")
        route_api_base = route.get("api_base")
        route_id = f"{route_provider}:{route_model}@{route_api_base or '-'}"

        if is_in_cooldown(route_id):
            _emit_event(
                {
                    "event": "route_skip_cooldown",
                    "stage": "completion",
                    "route_id": route_id,
                    "provider": route_provider,
                    "model": route_model,
                }
            )
            last_failure = _base_result(
                ok=False,
                content=None,
                reason="cooldown_active",
                attempts_used=max(1, attempts_used),
                t0=t0,
                retries=retries,
                provider_used=route_provider,
                model_used=route_model,
                fallback_reason=prior_failure,
                error_category="other",
            )
            prior_failure = "cooldown_active"
            continue

        if not str(route_api_key or "").strip():
            _emit_event(
                {
                    "event": "route_skip_missing_key",
                    "stage": "completion",
                    "route_id": route_id,
                    "provider": route_provider,
                    "model": route_model,
                }
            )
            last_failure = _base_result(
                ok=False,
                content=None,
                reason="missing_api_key",
                attempts_used=max(1, attempts_used),
                t0=t0,
                retries=retries,
                provider_used=route_provider,
                model_used=route_model,
                fallback_reason=prior_failure,
                error_category="other",
            )
            prior_failure = "missing_api_key"
            continue

        for attempt in range(retries + 1):
            attempts_used += 1
            if route_idx > 0:
                _emit_event(
                    {
                        "event": "fallback_attempt",
                        "stage": "completion",
                        "route_id": route_id,
                        "provider": route_provider,
                        "model": route_model,
                        "attempt_index": attempts_used,
                        "fallback_reason": prior_failure,
                    }
                )
            result = _call_completion_once(
                provider=route_provider,
                model=route_model,
                api_key=str(route_api_key),
                api_base=str(route_api_base or "").strip() or None,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_ms=timeout_ms,
                retries=retries,
                temperature=temperature,
                t0=t0,
                use_litellm_sdk=use_litellm_sdk,
                use_legacy_client=use_legacy_client,
            )
            result.attempts_used = attempts_used
            result.fallback_reason = prior_failure
            if result.ok:
                register_route_success(route_id)
                _emit_event(
                    {
                        "event": "request_success",
                        "stage": "completion",
                        "route_id": route_id,
                        "provider": result.provider_used,
                        "model": result.model_used,
                        "attempts_used": result.attempts_used,
                        "elapsed_ms": result.elapsed_ms,
                        "fallback_reason": result.fallback_reason,
                    }
                )
                return result
            last_failure = result
            _emit_event(
                {
                    "event": "request_failure",
                    "stage": "completion",
                    "route_id": route_id,
                    "provider": result.provider_used,
                    "model": result.model_used,
                    "attempts_used": result.attempts_used,
                    "reason": result.reason,
                    "status_code": result.status_code,
                    "error_category": result.error_category,
                    "fallback_reason": result.fallback_reason,
                }
            )
            if is_recoverable(result.reason, result.status_code) and attempt < retries:
                time.sleep(min(2.0, 0.25 * (2**attempt)))
                continue
            register_route_failure(
                route_id,
                failure_threshold=max(1, int(router_failure_threshold)),
                cooldown_seconds=max(0, int(router_cooldown_sec)),
            )
            prior_failure = str(result.reason or "error")
            break

        if last_failure is not None and route_idx == len(routes) - 1:
            return last_failure

    if last_failure is not None:
        return last_failure
    return _base_result(
        ok=False,
        content=None,
        reason="unknown_error",
        attempts_used=max(1, attempts_used),
        t0=t0,
        retries=retries,
        provider_used=provider,
        model_used=model,
        error_category="other",
    )


def _legacy_stream_once(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_ms: int,
    temperature: float,
    t0: float,
    retries: int,
    provider: str,
    on_delta: Callable[[str], None] | None,
) -> LLMStreamResult:
    payload = {
        "model": model,
        "temperature": float(temperature),
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    timeout_s = max(0.1, float(timeout_ms) / 1000.0)
    req = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    chunks: list[str] = []
    stream_events: list[dict[str, Any]] = []
    cumulative_chars = 0
    first_token_latency_ms: int | None = None
    done = False
    decode_error = False
    status_code: int | None = None
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            status_code = int(resp.status)
            if status_code >= 400:
                return _base_stream_result(
                    ok=False,
                    content=None,
                    reason="rate_limit" if status_code == 429 else "http_error",
                    status_code=status_code,
                    attempts_used=1,
                    t0=t0,
                    retries=retries,
                    provider_used=provider,
                    model_used=model,
                    error_category=classify_error_category("http_error", status_code),
                )
            while True:
                raw_line = resp.readline()
                if raw_line == b"":
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    done = True
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    decode_error = True
                    break
                if not isinstance(event, dict):
                    decode_error = True
                    break
                choices = event.get("choices", [])
                if not isinstance(choices, list) or not choices:
                    continue
                first = choices[0] if isinstance(choices[0], dict) else {}
                delta = first.get("delta", {}) if isinstance(first, dict) else {}
                piece = delta.get("content") if isinstance(delta, dict) else None
                text_piece = str(piece or "")
                if not text_piece:
                    continue
                if first_token_latency_ms is None:
                    first_token_latency_ms = int((time.perf_counter() - t0) * 1000)
                chunks.append(text_piece)
                if on_delta is not None:
                    try:
                        on_delta(text_piece)
                    except Exception:
                        pass
                cumulative_chars += len(text_piece)
                stream_events.append(
                    {
                        "event_index": len(stream_events),
                        "t_ms": int((time.perf_counter() - t0) * 1000),
                        "delta_chars": len(text_piece),
                        "cumulative_chars": cumulative_chars,
                    }
                )
        if decode_error:
            return _base_stream_result(
                ok=False,
                content=None,
                reason="stream_invalid_payload",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                first_token_latency_ms=first_token_latency_ms,
                chunks_received=len(chunks),
                stream_events=stream_events,
                error_category="other",
            )
        if not chunks:
            return _base_stream_result(
                ok=False,
                content=None,
                reason="stream_empty",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                error_category="other",
            )
        if not done:
            return _base_stream_result(
                ok=False,
                content=None,
                reason="stream_interrupted",
                status_code=status_code,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                first_token_latency_ms=first_token_latency_ms,
                chunks_received=len(chunks),
                stream_events=stream_events,
                error_category="network",
            )
        return _base_stream_result(
            ok=True,
            content="".join(chunks),
            reason=None,
            status_code=status_code,
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            first_token_latency_ms=first_token_latency_ms,
            chunks_received=len(chunks),
            stream_events=stream_events,
        )
    except error.HTTPError as exc:
        code = int(exc.code or 0)
        reason = "rate_limit" if code == 429 else "http_error"
        return _base_stream_result(
            ok=False,
            content=None,
            reason=reason,
            status_code=code,
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            error_category=classify_error_category(reason, code),
        )
    except (TimeoutError, socket.timeout):
        timeout_reason = "stream_first_token_timeout" if first_token_latency_ms is None else "stream_interrupted"
        return _base_stream_result(
            ok=False,
            content=None,
            reason=timeout_reason,
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            first_token_latency_ms=first_token_latency_ms,
            chunks_received=len(chunks),
            stream_events=stream_events,
            error_category=classify_error_category(timeout_reason),
        )
    except error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            timeout_reason = "stream_first_token_timeout" if first_token_latency_ms is None else "stream_interrupted"
            return _base_stream_result(
                ok=False,
                content=None,
                reason=timeout_reason,
                attempts_used=1,
                t0=t0,
                retries=retries,
                provider_used=provider,
                model_used=model,
                first_token_latency_ms=first_token_latency_ms,
                chunks_received=len(chunks),
                stream_events=stream_events,
                error_category=classify_error_category(timeout_reason),
            )
        return _base_stream_result(
            ok=False,
            content=None,
            reason="network_error",
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            error_category="network",
        )
    except Exception:
        reason = "stream_interrupted" if first_token_latency_ms is not None else "unknown_error"
        return _base_stream_result(
            ok=False,
            content=None,
            reason=reason,
            attempts_used=1,
            t0=t0,
            retries=retries,
            provider_used=provider,
            model_used=model,
            first_token_latency_ms=first_token_latency_ms,
            chunks_received=len(chunks),
            stream_events=stream_events,
            error_category=classify_error_category(reason),
        )


def call_chat_completion_stream(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    system_prompt: str,
    user_prompt: str,
    timeout_ms: int,
    max_retries: int,
    temperature: float = 0.0,
    on_delta: Callable[[str], None] | None = None,
    api_base: str | None = None,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
    fallback_api_key: str | None = None,
    fallback_api_base: str | None = None,
    router_retry: int | None = None,
    router_cooldown_sec: int = 0,
    router_failure_threshold: int = 1,
    use_litellm_sdk: bool = True,
    use_legacy_client: bool = False,
) -> LLMStreamResult:
    # Keep streaming on openai-compatible SSE path to preserve event fields and callback behavior.
    _ = (use_litellm_sdk, use_legacy_client)
    t0 = time.perf_counter()
    retries = max(0, int(router_retry if router_retry is not None else max_retries))
    attempts_used = 0

    routes: list[dict[str, str | None]] = [
        {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "api_base": api_base,
        }
    ]
    if str(fallback_model or "").strip():
        routes.append(
            {
                "provider": fallback_provider or provider,
                "model": fallback_model,
                "api_key": fallback_api_key,
                "api_base": fallback_api_base or api_base,
            }
        )

    prior_failure: str | None = None
    last_failure: LLMStreamResult | None = None

    for route_idx, route in enumerate(routes):
        route_provider = str(route.get("provider") or provider)
        route_model = str(route.get("model") or model)
        route_api_key = route.get("api_key")
        route_api_base = route.get("api_base")
        route_id = f"{route_provider}:{route_model}@{route_api_base or '-'}"

        if is_in_cooldown(route_id):
            _emit_event(
                {
                    "event": "route_skip_cooldown",
                    "stage": "stream",
                    "route_id": route_id,
                    "provider": route_provider,
                    "model": route_model,
                }
            )
            last_failure = _base_stream_result(
                ok=False,
                content=None,
                reason="cooldown_active",
                attempts_used=max(1, attempts_used),
                t0=t0,
                retries=retries,
                provider_used=route_provider,
                model_used=route_model,
                fallback_reason=prior_failure,
                error_category="other",
            )
            prior_failure = "cooldown_active"
            continue

        if not str(route_api_key or "").strip():
            _emit_event(
                {
                    "event": "route_skip_missing_key",
                    "stage": "stream",
                    "route_id": route_id,
                    "provider": route_provider,
                    "model": route_model,
                }
            )
            last_failure = _base_stream_result(
                ok=False,
                content=None,
                reason="missing_api_key",
                attempts_used=max(1, attempts_used),
                t0=t0,
                retries=retries,
                provider_used=route_provider,
                model_used=route_model,
                fallback_reason=prior_failure,
                error_category="other",
            )
            prior_failure = "missing_api_key"
            continue

        endpoint = _provider_endpoint(route_provider, str(route_api_base or "").strip() or None)
        if not endpoint:
            last_failure = _base_stream_result(
                ok=False,
                content=None,
                reason="unsupported_provider",
                attempts_used=max(1, attempts_used),
                t0=t0,
                retries=retries,
                provider_used=route_provider,
                model_used=route_model,
                fallback_reason=prior_failure,
                error_category="other",
            )
            prior_failure = "unsupported_provider"
            continue

        for attempt in range(retries + 1):
            attempts_used += 1
            if route_idx > 0:
                _emit_event(
                    {
                        "event": "fallback_attempt",
                        "stage": "stream",
                        "route_id": route_id,
                        "provider": route_provider,
                        "model": route_model,
                        "attempt_index": attempts_used,
                        "fallback_reason": prior_failure,
                    }
                )
            result = _legacy_stream_once(
                endpoint=endpoint,
                api_key=str(route_api_key),
                model=route_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_ms=timeout_ms,
                temperature=temperature,
                t0=t0,
                retries=retries,
                provider=route_provider,
                on_delta=on_delta,
            )
            result.attempts_used = attempts_used
            result.fallback_reason = prior_failure
            if result.ok:
                register_route_success(route_id)
                _emit_event(
                    {
                        "event": "request_success",
                        "stage": "stream",
                        "route_id": route_id,
                        "provider": result.provider_used,
                        "model": result.model_used,
                        "attempts_used": result.attempts_used,
                        "elapsed_ms": result.elapsed_ms,
                        "first_token_latency_ms": result.first_token_latency_ms,
                        "chunks_received": result.chunks_received,
                        "fallback_reason": result.fallback_reason,
                    }
                )
                return result
            last_failure = result
            _emit_event(
                {
                    "event": "request_failure",
                    "stage": "stream",
                    "route_id": route_id,
                    "provider": result.provider_used,
                    "model": result.model_used,
                    "attempts_used": result.attempts_used,
                    "reason": result.reason,
                    "status_code": result.status_code,
                    "error_category": result.error_category,
                    "fallback_reason": result.fallback_reason,
                    "first_token_latency_ms": result.first_token_latency_ms,
                    "chunks_received": result.chunks_received,
                }
            )
            if is_recoverable(result.reason, result.status_code) and attempt < retries:
                time.sleep(min(2.0, 0.25 * (2**attempt)))
                continue
            register_route_failure(
                route_id,
                failure_threshold=max(1, int(router_failure_threshold)),
                cooldown_seconds=max(0, int(router_cooldown_sec)),
            )
            prior_failure = str(result.reason or "error")
            break

        if last_failure is not None and route_idx == len(routes) - 1:
            return last_failure

    if last_failure is not None:
        return last_failure
    return _base_stream_result(
        ok=False,
        content=None,
        reason="unknown_error",
        attempts_used=max(1, attempts_used),
        t0=t0,
        retries=retries,
        provider_used=provider,
        model_used=model,
        error_category="other",
    )
