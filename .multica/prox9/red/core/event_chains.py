"""
通用奇遇事件链：2–3 步，规则效果 + AI 可选润色
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config import (
    EVENT_CHAIN_MAX_ACTIVE_GLOBAL,
    EVENT_CHAIN_TIMEOUT_MIN,
    EVENT_CHAIN_TRIGGER_TRAVEL,
    EVENT_CHAIN_TRIGGER_ADVENTURE,
    EVENT_EFFECT_CAPS,
)
from core.models import Character, CharacterStatus
from storage.db import WorldStateRepository, CharacterRepository

_KEY = "event_chains"


class ChainStep(BaseModel):
    prompt: str
    choices: List[Dict[str, Any]] = Field(default_factory=list)
    # choice: {id, label, effects{}}


class EventChain(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    kind: str = "opportunity"
    title: str = ""
    actor_id: str = ""
    actor_name: str = ""
    step: int = 1
    max_steps: int = 2
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    location: str = ""
    created_at: float = 0.0
    status: str = "active"  # active | done | abandoned | expired
    season: int = 0
    log: List[str] = Field(default_factory=list)


def _load() -> Dict[str, Any]:
    try:
        data = WorldStateRepository.get(_KEY) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(chains: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, chains)
    except Exception:
        pass


# 预置模板：2 步，choices.effects 落账
from core.content_pack import EVENT_CHAIN_TEMPLATES as TEMPLATES  # noqa: E402


def _clamp_effects(effects: Dict[str, Any]) -> Dict[str, Any]:
    caps = EVENT_EFFECT_CAPS or {}
    out = dict(effects or {})
    if "exp" in out:
        out["exp"] = int(max(0, min(int(out["exp"]), int(caps.get("exp", 200)))))
    if "stones" in out:
        out["stones"] = int(
            max(
                -int(caps.get("stones_lose", 200)),
                min(int(out["stones"]), int(caps.get("stones_gain", 200))),
            )
        )
    if "lifespan_years" in out:
        out["lifespan_years"] = float(
            max(-5.0, min(float(out["lifespan_years"]), float(caps.get("lifespan_gain", 5))))
        )
    if "sin" in out:
        out["sin"] = int(max(0, min(int(out["sin"]), int(caps.get("sin", 40)))))
    if "merit" in out:
        out["merit"] = int(max(0, min(int(out["merit"]), int(caps.get("merit", 40)))))
    if "dao_heart" in out:
        out["dao_heart"] = int(max(-10, min(int(out["dao_heart"]), 10)))
    return out


def _apply_effects(c: Character, effects: Dict[str, Any]) -> str:
    notes = []
    e = _clamp_effects(effects)
    if e.get("exp"):
        c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + int(e["exp"]))
        notes.append(f"修为+{int(e['exp'])}")
    if e.get("stones"):
        c.spirit_stones = max(0, c.spirit_stones + int(e["stones"]))
        notes.append(f"灵石{int(e['stones']):+d}")
    if e.get("lifespan_years"):
        ly = float(e["lifespan_years"])
        if ly > 0:
            c.lifespan.add_lifespan(ly)
        else:
            c.lifespan.burn_lifespan(abs(ly))
        notes.append(f"寿元{ly:+.1f}")
    if e.get("sin"):
        c.karma.add_sin(int(e["sin"]))
        notes.append(f"业力+{int(e['sin'])}")
    if e.get("merit"):
        c.karma.add_merit(int(e["merit"]))
        notes.append(f"功德+{int(e['merit'])}")
    if e.get("dao_heart"):
        c.karma.dao_heart = max(0, c.karma.dao_heart + int(e["dao_heart"]))
        notes.append(f"道心{int(e['dao_heart']):+d}")
    return "，".join(notes) if notes else "无事"


class EventChainEngine:
    @staticmethod
    def active_for(char_id: str) -> Optional[EventChain]:
        data = _load()
        raw = data.get(char_id)
        if not raw:
            return None
        try:
            ch = EventChain.model_validate(raw)
        except Exception:
            return None
        if ch.status != "active":
            return None
        if time.time() - ch.created_at > EVENT_CHAIN_TIMEOUT_MIN * 60:
            ch.status = "expired"
            data[char_id] = ch.model_dump()
            _save(data)
            return None
        return ch

    @staticmethod
    def global_active_count() -> int:
        data = _load()
        now = time.time()
        n = 0
        timeout = EVENT_CHAIN_TIMEOUT_MIN * 60
        for cid, raw in list(data.items()):
            try:
                if raw.get("status") != "active":
                    continue
                if now - float(raw.get("created_at") or 0) > timeout:
                    raw["status"] = "expired"
                    data[cid] = raw
                    continue
                n += 1
            except Exception:
                continue
        _save(data)
        return n

    @staticmethod
    def maybe_start(
        c: Character,
        trigger: str = "travel",
        now: Optional[float] = None,
        force: bool = False,
    ) -> Optional[EventChain]:
        t = now if now is not None else time.time()
        if c.status == CharacterStatus.DEAD or c.lifespan.is_dead():
            return None
        if EventChainEngine.active_for(c.id):
            return None
        if not force:
            p = (
                EVENT_CHAIN_TRIGGER_TRAVEL
                if trigger == "travel"
                else EVENT_CHAIN_TRIGGER_ADVENTURE
            )
            if random.random() > p:
                return None
            if EventChainEngine.global_active_count() >= EVENT_CHAIN_MAX_ACTIVE_GLOBAL:
                return None
        tpl = random.choice(TEMPLATES)
        steps = []
        for st in tpl["steps"]:
            steps.append(
                {
                    "prompt": st["prompt"],
                    "choices": [
                        {
                            "id": ch["id"],
                            "label": ch["label"],
                            "effects": _clamp_effects(ch.get("effects") or {}),
                        }
                        for ch in st["choices"]
                    ],
                }
            )
        ch = EventChain(
            kind=tpl["kind"],
            title=tpl["title"],
            actor_id=c.id,
            actor_name=c.name,
            step=1,
            max_steps=len(steps),
            steps=steps,
            location=c.location,
            created_at=t,
            status="active",
        )
        # 可选 AI 润色第一步
        try:
            from core import ai_flavor

            polished = ai_flavor.polish_omen_open(
                tpl["title"], steps[0]["prompt"], loc=c.location, who=c.name
            )
            if polished and polished != steps[0]["prompt"]:
                steps[0]["prompt"] = polished
                ch.steps = steps
        except Exception:
            pass

        data = _load()
        data[c.id] = ch.model_dump()
        _save(data)
        return ch

    @staticmethod
    def view_text(c: Character) -> Dict[str, Any]:
        ch = EventChainEngine.active_for(c.id)
        if not ch:
            return {"success": False, "message": "当前无进行中的奇遇。可 /机缘 或四处走走。"}
        st = ch.steps[ch.step - 1]
        opts = " | ".join(f"{x['id']}.{x['label']}" for x in st["choices"])
        return {
            "success": True,
            "chain": ch,
            "message": (
                f"【奇遇 · {ch.title}】第 {ch.step}/{ch.max_steps} 步\n"
                f"{st['prompt']}\n选项：{opts}\n"
                f"输入 /奇遇 <编号> 选择，或 /奇遇 弃。"
            ),
        }

    @staticmethod
    def choose(c: Character, choice_id: str) -> Dict[str, Any]:
        ch = EventChainEngine.active_for(c.id)
        if not ch:
            return {"success": False, "message": "当前无进行中的奇遇。"}
        st = ch.steps[ch.step - 1]
        pick = next((x for x in st["choices"] if str(x.get("id")) == str(choice_id)), None)
        if not pick:
            return {"success": False, "message": "无效选项。"}
        summary = _apply_effects(c, pick.get("effects") or {})
        ch.log.append(f"步{ch.step}:{pick['label']} → {summary}")
        try:
            from core import ai_flavor

            flavor = ai_flavor.polish_omen_outcome(
                ch.title, pick.get("label") or "", summary, who=c.name
            )
            lines = [f"【奇遇】{flavor}"]
        except Exception:
            lines = [f"【奇遇】{pick['label']}。落账：{summary}"]

        is_last = ch.step >= ch.max_steps
        if is_last:
            ch.status = "done"
            data = _load()
            data[c.id] = ch.model_dump()
            _save(data)
            try:
                from core.world_channel import WorldChannel

                WorldChannel.post(
                    "chain",
                    f"【奇遇】{c.name} 于{c.location or '途中'}走通「{ch.title}」。",
                    level="major",
                    actor=c.name,
                    location=c.location,
                )
            except Exception:
                pass
            return {
                "success": True,
                "done": True,
                "message": "\n".join(lines) + f"\n奇遇「{ch.title}」已了结。",
            }

        ch.step += 1
        data = _load()
        data[c.id] = ch.model_dump()
        _save(data)
        nxt = ch.steps[ch.step - 1]
        # AI 润色下一步开场
        try:
            from core import ai_flavor

            nxt_prompt = ai_flavor.polish_omen_next(
                ch.title, nxt["prompt"], prev_choice=pick.get("label") or ""
            )
            if nxt_prompt:
                nxt["prompt"] = nxt_prompt
                ch.steps[ch.step - 1] = nxt
                data[c.id] = ch.model_dump()
                _save(data)
        except Exception:
            pass
        opts = " | ".join(f"{x['id']}.{x['label']}" for x in nxt["choices"])
        return {
            "success": True,
            "done": False,
            "chain": ch,
            "message": "\n".join(lines) + f"\n\n【下一步】{nxt['prompt']}\n选项：{opts}",
        }

    @staticmethod
    def abandon(c: Character) -> Dict[str, Any]:
        ch = EventChainEngine.active_for(c.id)
        if not ch:
            return {"success": False, "message": "本无奇遇。"}
        ch.status = "abandoned"
        data = _load()
        data[c.id] = ch.model_dump()
        _save(data)
        return {"success": True, "message": f"【抽身】放弃奇遇「{ch.title}」，天道不罪。"}
