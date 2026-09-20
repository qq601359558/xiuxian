"""
场景 Prompt 注册表：scene_id → 构建器与调用契约
业务只经 router.invoke，不再散拼 HTTP/Prompt。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set

from ai.play_prompts import PROMPT_BUILDERS

# 校验器：返回错误信息字符串表示拒绝，None 表示通过
Validator = Callable[[Any], Optional[str]]
# 无通道时的确定性降级：返回 dict 或 None
Fallback = Callable[..., Optional[Dict[str, Any]]]


@dataclass
class SceneSpec:
    scene_id: str
    builder: Callable[..., str]
    requires_facts: bool = False
    max_tokens: int = 1200
    fallback: Optional[Fallback] = None
    validator: Optional[Validator] = None
    tags: Set[str] = field(default_factory=set)


_REGISTRY: Dict[str, SceneSpec] = {}
_BOOTSTRAPPED = False

# 需要事实包的场景（禁止无包编故事）
FACT_REQUIRED_SCENES = {
    "combat",
    "world_event",
    "npc_agenda",
    "npc_talk",
    "free_action",
    "collusion",
    "revenge",
    "hunt_announce",
    "omen_open",
    "omen_next",
    "omen_outcome",
}

# 调用方传入的 data 必须是 dict 时的场景
REQUIRE_JSON_OBJECT = FACT_REQUIRED_SCENES | {
    "tribulation",
    "heart_demon_judge",
    "heart_demon_session",
    "adventure",
    "custom_art",
    "forge",
    "omen_script",
    "world_director",
}


def _default_validator(scene_id: str) -> Validator:
    def _v(data: Any) -> Optional[str]:
        if data is None:
            return "empty_response"
        if scene_id in REQUIRE_JSON_OBJECT and not isinstance(data, dict):
            return "not_json_object"
        return None

    return _v


def bootstrap_from_play_prompts() -> None:
    """把 play_prompts.PROMPT_BUILDERS 挂进注册表（幂等）。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED and _REGISTRY:
        return
    for scene_id, builder in PROMPT_BUILDERS.items():
        if scene_id in _REGISTRY:
            continue
        _REGISTRY[scene_id] = SceneSpec(
            scene_id=scene_id,
            builder=builder,
            requires_facts=scene_id in FACT_REQUIRED_SCENES,
            validator=_default_validator(scene_id),
            tags={"builtin"},
        )
    _BOOTSTRAPPED = True


def register(spec: SceneSpec, *, replace: bool = False) -> None:
    bootstrap_from_play_prompts()
    if spec.scene_id in _REGISTRY and not replace:
        raise ValueError(f"scene already registered: {spec.scene_id}")
    if spec.validator is None:
        spec.validator = _default_validator(spec.scene_id)
    _REGISTRY[spec.scene_id] = spec


def get_scene(scene_id: str) -> Optional[SceneSpec]:
    bootstrap_from_play_prompts()
    return _REGISTRY.get(scene_id)


def list_scenes() -> list[str]:
    bootstrap_from_play_prompts()
    return sorted(_REGISTRY.keys())


def clear_registry_for_tests() -> None:
    global _BOOTSTRAPPED
    _REGISTRY.clear()
    _BOOTSTRAPPED = False


def known_scene_ids() -> set[str]:
    bootstrap_from_play_prompts()
    return set(_REGISTRY.keys())
