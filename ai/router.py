"""
AI 中台统一入口：router.invoke(scene_id, ...)
契约：
  未注册 scene → 拒绝
  requires_facts 且无 FactPack → 拒绝
  配额超限 → 拒绝（可展示 reason）
  无通道：允许 local 降级则 fallback，否则明确不可用
  成功/失败均记 calllog + audit
  返回 {ok, scene_id, data|error, ref_ids}
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ai.audit import write_audit
from ai.calllog import log_ai_call
from ai.quota import quota
from ai.registry import SceneSpec, get_scene


def _extract_ref_ids(data: Any) -> List[str]:
    if not isinstance(data, dict):
        return []
    refs = data.get("ref_ids") or data.get("refs") or []
    if isinstance(refs, list):
        return [str(x) for x in refs]
    return []


def _result(
    *,
    ok: bool,
    scene_id: str,
    data: Any = None,
    error: str = "",
    ref_ids: Optional[List[str]] = None,
    latency_ms: int = 0,
    used_fallback: bool = False,
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "scene_id": scene_id,
        "data": data,
        "error": error,
        "ref_ids": ref_ids or _extract_ref_ids(data),
        "latency_ms": latency_ms,
        "used_fallback": used_fallback,
    }


def _audit(scene_id: str, actor_id: str, ok: bool, error: str, extra: Optional[dict] = None) -> None:
    rec = {
        "source": "ai.router",
        "scene_id": scene_id,
        "actor_id": actor_id,
        "ok": ok,
        "error": error,
    }
    if extra:
        rec.update(extra)
    write_audit(rec)


def _call_gateway(prompt: str, timeout: float) -> Optional[Dict[str, Any]]:
    from ai.gateway import _chat_json

    return _chat_json(prompt, timeout=timeout)


def invoke(
    scene_id: str,
    *,
    facts: Any = None,
    payload: Optional[Dict[str, Any]] = None,
    actor_id: str = "system",
    timeout: float = 20.0,
    gateway: Any = None,
) -> Dict[str, Any]:
    """中台唯一 AI 调用入口。gateway 可注入（测试）。"""
    payload = dict(payload or {})
    spec = get_scene(scene_id)
    if spec is None:
        err = f"unknown_scene:{scene_id}"
        _audit(scene_id, actor_id, False, err)
        return _result(ok=False, scene_id=scene_id, error=err)

    if spec.requires_facts and facts is None:
        err = "facts_required"
        _audit(scene_id, actor_id, False, err)
        return _result(ok=False, scene_id=scene_id, error=err)

    allowed, reason = quota.allow(scene_id)
    if not allowed:
        _audit(scene_id, actor_id, False, reason)
        return _result(ok=False, scene_id=scene_id, error=reason or "quota_exceeded")

    try:
        if "facts" in _builder_accepts_facts(spec) and facts is not None:
            prompt = spec.builder(facts=facts, **payload)
        elif facts is not None and "facts" not in payload:
            # builder 不收 facts 关键字时，不注入，避免 TypeError
            prompt = spec.builder(**payload)
        else:
            prompt = spec.builder(**payload)
    except TypeError:
        try:
            prompt = spec.builder(**payload)
        except Exception as e:
            err = f"prompt_build_failed:{e}"
            _audit(scene_id, actor_id, False, err)
            return _result(ok=False, scene_id=scene_id, error=err)
    except Exception as e:
        err = f"prompt_build_failed:{e}"
        _audit(scene_id, actor_id, False, err)
        return _result(ok=False, scene_id=scene_id, error=err)

    call = gateway if gateway is not None else _call_gateway
    t0 = time.time()
    data = None
    error = ""
    used_fallback = False

    try:
        data = call(prompt, timeout)
    except Exception as e:
        error = f"gateway_error:{e}"

    latency_ms = int((time.time() - t0) * 1000)

    if data is None and not error:
        # 通道不可用或返回空
        from config import ai_available, local_ai_allowed, ai_unavailable_message
        from ai.gateway import ai_ready

        if spec.fallback is not None and (ai_ready() or local_ai_allowed()):
            try:
                if facts is not None:
                    data = spec.fallback(facts=facts, **payload)
                else:
                    data = spec.fallback(**payload)
                used_fallback = data is not None
            except TypeError:
                try:
                    data = spec.fallback(**payload)
                    used_fallback = data is not None
                except Exception as e:
                    error = f"fallback_failed:{e}"
            except Exception as e:
                error = f"fallback_failed:{e}"
            if data is None and not error:
                error = (
                    ai_unavailable_message()
                    if not (ai_available() or local_ai_allowed())
                    else "ai_empty_response"
                )
        else:
            error = (
                ai_unavailable_message()
                if not (ai_available() or local_ai_allowed())
                else "ai_empty_response"
            )

    if data is not None and spec.validator is not None:
        verr = spec.validator(data)
        if verr:
            log_ai_call(
                kind=f"router:{scene_id}",
                channel="midplatform",
                status="schema_fail",
                prompt=prompt[:2000],
                response=data,
                error=verr,
                duration_ms=latency_ms,
                extra={"actor_id": actor_id},
            )
            _audit(scene_id, actor_id, False, verr, {"used_fallback": used_fallback})
            return _result(
                ok=False,
                scene_id=scene_id,
                error=verr,
                latency_ms=latency_ms,
                used_fallback=used_fallback,
            )

    ok = data is not None
    log_ai_call(
        kind=f"router:{scene_id}",
        channel="midplatform",
        status="ok" if ok else "fail",
        prompt=prompt[:2000] if isinstance(prompt, str) else str(prompt)[:2000],
        response=data,
        error=error,
        duration_ms=latency_ms,
        extra={"actor_id": actor_id, "used_fallback": used_fallback},
    )
    _audit(
        scene_id,
        actor_id,
        ok,
        "" if ok else error,
        {"latency_ms": latency_ms, "used_fallback": used_fallback},
    )
    return _result(
        ok=ok,
        scene_id=scene_id,
        data=data if ok else None,
        error="" if ok else error,
        latency_ms=latency_ms,
        used_fallback=used_fallback,
    )


def _builder_accepts_facts(spec: SceneSpec) -> set:
    import inspect

    try:
        sig = inspect.signature(spec.builder)
        return set(sig.parameters.keys())
    except Exception:
        return set()
