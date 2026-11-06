"""
异步造化网关：对接大模型生成心魔、世界事件提案与渡劫天命判定
规则引擎仍是数值权威；AI 负责叙事与在概率框内的天命拍板
"""
import json
import random
import time
from typing import Any, Dict, Optional

import httpx

from ai.calllog import log_ai_call

from config import (
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_MODEL,
    TRIBULATION_AI_JITTER,
    ai_available,
    local_ai_allowed,
    ai_unavailable_message,
    ccswitch_runtime,
    USE_CCSWITCH,
)
from ai.validator import DSLValidator
from ai.event_validator import EventValidator
from ai.facts import FactPack, build_fact_pack
from ai.gate import gate


def ai_ready() -> bool:
    """有 Key，或测试环境显式允许本地降级"""
    return ai_available() or local_ai_allowed()


def ai_block_reason() -> str:
    if ai_available() or local_ai_allowed():
        # 有通道但最近探测失败时给出可操作提示
        try:
            health = ai_health_status()
            if health.get("last_error"):
                return (
                    f"AI 通道已配置，但最近一次探测失败：{health['last_error']}。"
                    f"可 /ai 自检；交谈/事件将降级本地模板。"
                )
        except Exception:
            pass
        return ""
    return ai_unavailable_message()


def ai_health_status() -> Dict[str, Any]:
    """读缓存的通道健康信息（不发起网络请求）"""
    try:
        from storage.db import WorldStateRepository

        return WorldStateRepository.get("ai_health") or {}
    except Exception:
        return {}


def probe_ai_channel(force: bool = False) -> Dict[str, Any]:
    """轻量探测 AI 通道；结果写入 world_state。force=True 时忽略 60s 缓存。"""
    from storage.db import WorldStateRepository

    cached = {}
    try:
        cached = WorldStateRepository.get("ai_health") or {}
    except Exception:
        cached = {}
    now = time.time()
    if (
        not force
        and cached.get("checked_at")
        and now - float(cached.get("checked_at") or 0) < 60.0
        and cached.get("ok") is not None
    ):
        return cached

    result: Dict[str, Any] = {
        "checked_at": now,
        "mode": "CCSWITCH" if USE_CCSWITCH else "OPENAI",
        "base": LLM_API_BASE,
        "model": LLM_MODEL,
    }
    if not ai_available():
        result.update({"ok": False, "error": ai_unavailable_message()})
    else:
        try:
            data = _chat_json("只输出 JSON：{\"line\":\"通了\"}", timeout=12.0)
            ok = bool(data and data.get("line"))
            result["ok"] = ok
            if not ok:
                result["error"] = "对话测试未返回有效内容（见 data/server.log）"
            else:
                result["error"] = ""
                result["sample"] = str(data)[:80]
        except Exception as e:
            result["ok"] = False
            result["error"] = f"{type(e).__name__}: {e}"[:200]
    try:
        WorldStateRepository.set("ai_health", result)
    except Exception:
        pass
    return result


def _router_data(
    scene_id: str,
    payload: Dict[str, Any],
    *,
    facts: Any = None,
    actor_id: str = "system",
    timeout: float = 20.0,
) -> Optional[Dict[str, Any]]:
    """经中台 router 取 JSON；失败/非 dict 返回 None。业务不应再直呼 _chat_json。"""
    try:
        from ai.router import invoke as _invoke

        result = _invoke(
            scene_id,
            facts=facts,
            payload=payload,
            actor_id=actor_id,
            timeout=timeout,
        )
        data = result.get("data")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _character_brief(character) -> str:
    """把修士关键数据压成给 AI 的简报（兼容旧接口；优先用事实包）"""
    rem = character.lifespan.get_remaining_years()
    return (
        f"道号={character.name}; 境界={character.realm.name}; "
        f"修为={character.realm.current_exp}/{character.realm.max_exp}; "
        f"剩余寿元={rem:.1f}岁; 业力={character.karma.sin_value}; "
        f"功德={character.karma.merit_value}; 道心={character.karma.dao_heart}; "
        f"血煞={'是' if character.karma.is_blood_marked() else '否'}; "
        f"灵根={character.spiritual_root.display_name()}; "
        f"宗门={character.sect or '散修'}; 位置={character.location}; "
        f"随身灵石={character.spirit_stones}; 金库={character.vault_stones}; "
        f"法门={'、'.join(character.skills[:6])}"
    )


def _facts_or_brief(character, facts: Optional[FactPack] = None) -> str:
    if facts is not None:
        return facts.to_prompt_block()
    return _character_brief(character)


def _chat_endpoint() -> str:
    """拼接 OpenAI 兼容对话地址；base 缺 /v1 时自动补全"""
    base = (LLM_API_BASE or "").rstrip("/")
    if not base:
        return ""
    # 已带版本前缀则直接用
    if base.endswith("/v1") or "/v1/" in base + "/":
        return f"{base}/chat/completions"
    # 常见中转站需要 /v1
    return f"{base}/v1/chat/completions"


def _anthropic_chat_json(prompt: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    """走本机 CC Switch（Anthropic Messages 协议）"""
    rt = ccswitch_runtime()
    if not rt.get("base"):
        return None
    url = rt["base"] + "/v1/messages"
    headers = {
        "x-api-key": rt["token"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    # 部分代理用 Bearer
    full_prompt = "你是修仙世界「天道」叙事与裁决模块。只输出严格 JSON，不要 markdown。\n" + prompt
    body = {
        "model": rt["model"],
        "max_tokens": 512,
        "messages": [{"role": "user", "content": full_prompt}],
    }
    t0 = time.time()
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=timeout)
        http_s = resp.status_code
        if resp.status_code != 200:
            headers2 = {
                "Authorization": "Bearer " + rt["token"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            resp = httpx.post(url, headers=headers2, json=body, timeout=timeout)
            http_s = resp.status_code
        if resp.status_code != 200:
            log_ai_call(
                kind="chat_json",
                channel="ccswitch",
                url=url,
                model=rt["model"],
                status="http_error",
                http_status=http_s,
                prompt=full_prompt,
                raw_text=resp.text[:2000],
                error=f"HTTP {http_s}",
                duration_ms=int((time.time() - t0) * 1000),
            )
            return None
        data = resp.json()
        parts = data.get("content") or []
        text = ""
        for p in parts:
            if isinstance(p, dict) and p.get("type") == "text":
                text += str(p.get("text") or "")
        if not text:
            text = str(data.get("completion") or "")
        parsed = _parse_json_loose(text)
        log_ai_call(
            kind="chat_json",
            channel="ccswitch",
            url=url,
            model=rt["model"],
            status="ok" if parsed else "parse_fail",
            http_status=http_s,
            prompt=full_prompt,
            response=parsed,
            raw_text=text,
            duration_ms=int((time.time() - t0) * 1000),
        )
        return parsed
    except Exception as e:
        log_ai_call(
            kind="chat_json",
            channel="ccswitch",
            url=url,
            model=rt.get("model", ""),
            status="exception",
            prompt=full_prompt,
            error=str(e)[:400],
            duration_ms=int((time.time() - t0) * 1000),
        )
        return None


def _chat_json(prompt: str, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """优先 CC Switch，其次 OpenAI 兼容接口；失败返回 None"""
    if USE_CCSWITCH:
        data = _anthropic_chat_json(prompt, timeout=max(timeout, 30.0))
        if data is not None:
            return data
        # 再试 OpenAI 兼容兜底
    if not LLM_API_KEY:
        return None
    url = _chat_endpoint()
    if not url:
        return None
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    body = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是修仙世界「天道」叙事与裁决模块。只输出严格 JSON，不要 markdown。",
            },
            {"role": "user", "content": prompt},
        ],
    }
    # 先带 json_object，部分代理不支持则降级再试
    t0 = time.time()
    last_http = None
    last_body = ""
    for with_fmt in (True, False):
        payload = dict(body)
        if with_fmt:
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            last_http = resp.status_code
            if resp.status_code != 200:
                last_body = resp.text[:2000]
                try:
                    from server.log import log_event
                    log_event(
                        "GATE",
                        "llm_http_error",
                        status=resp.status_code,
                        url=url,
                        body=resp.text[:180],
                        model=LLM_MODEL,
                        with_fmt=with_fmt,
                    )
                except Exception:
                    pass
                continue
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = _parse_json_loose(content)
            log_ai_call(
                kind="chat_json",
                channel="openai",
                url=url,
                model=LLM_MODEL,
                status="ok" if parsed else "parse_fail",
                http_status=resp.status_code,
                prompt=prompt,
                response=parsed,
                raw_text=content,
                duration_ms=int((time.time() - t0) * 1000),
                extra={"with_fmt": with_fmt},
            )
            return parsed
        except Exception as e:
            last_body = str(e)[:400]
            try:
                from server.log import log_event
                log_event("GATE", "llm_exception", err=str(e)[:180], url=url, with_fmt=with_fmt)
            except Exception:
                pass
            continue
    log_ai_call(
        kind="chat_json",
        channel="openai",
        url=url,
        model=LLM_MODEL,
        status="fail",
        http_status=last_http,
        prompt=prompt,
        raw_text=last_body,
        error="all attempts failed",
        duration_ms=int((time.time() - t0) * 1000),
    )
    return None


def _parse_json_loose(content: str) -> Optional[Dict[str, Any]]:
    """从模型输出提取 JSON（容忍 ```json 包裹与前后杂讯）"""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # 截取第一个 {...}
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(text[a : b + 1])
        except Exception:
            return None
    return None


def _chat_text(prompt: str, timeout: float = 8.0) -> Optional[str]:
    if not LLM_API_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
        resp = httpx.post(
            f"{LLM_API_BASE}/chat/completions",
            headers=headers,
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


class AIGateway:
    """造化中台网关"""

    # ---------------- 心魔（按角色全量数据） ----------------
    @staticmethod
    def generate_heart_demon_text(character_name: str, sin_value: int, character=None) -> str:
        """生成渡劫时的专属心魔问心幻境；有角色对象时走 AI 全量简报"""
        if character is not None:
            brief = _character_brief(character)
            text = _chat_text(
                "你是修仙世界的心魔。根据修士数据，写一段 80-160 字的问心幻境"
                "（第二人称，紧贴其业力/寿元/宗门/执念，有压迫感，不要解释规则）。\n"
                f"修士数据：{brief}"
            )
            if text:
                return text

        # 无 API / 失败：本地因果模板
        if sin_value == 0:
            illusions = [
                f"识海之中清气升腾，忽见年少时凡间父母苍老容颜：‘儿啊，长生虚妄，何不归家尽孝？’ 道友道心微动……",
                f"虚空之中浮现初入道途时的誓言碑：‘我辈修士，当清心寡欲，不染红尘。’ 往昔执念化作清风拂面……"
            ]
        elif sin_value < 100:
            illusions = [
                f"漫天劫雷中，忽现昔日被你斩杀夺宝的同道残魂，浑身焦黑泣血厉啸：‘{character_name}！还我储物袋，还我命来！’",
                f"识海内血海翻滚，幻化出你昔日杀人夺丹时的狰狞贪婪面孔，心魔冷笑：‘你与魔修何异？有何颜面证长生之道？！’"
            ]
        else:
            illusions = [
                f"【血煞滔天·万魂锁魂】\n识海化为尸山血海！数名冤魂索命而来：‘{character_name}！你背负百道杀孽，天理难容！今日引九天玄雷将你诛灭！’",
                f"【心魔夺舍】\n无尽杀气凝聚成一尊血色魔神：‘既然杀戮由心，何不彻底散去道基，奉我为尊，永堕魔道！’"
            ]
        return random.choice(illusions)

    # ---------------- 渡劫：AI 天命判定（规则概率为先验） ----------------
    @staticmethod
    def judge_tribulation(character, rule_prob: float, target_realm: str) -> Dict[str, Any]:
        """
        由 AI 在规则成功率附近拍板渡劫成败。
        :param rule_prob: 规则引擎算出的基础成功率 (0~1)
        :return: {"success": bool, "reason": str, "source": "ai"|"rule"}
        """
        jitter = TRIBULATION_AI_JITTER
        lo = max(0.05, rule_prob - jitter)
        hi = min(0.95, rule_prob + jitter)

        brief = _character_brief(character)
        try:
            from ai.play_prompts import tribulation_prompt

            prompt = tribulation_prompt(
                who=brief,
                realm_from=character.realm.name,
                realm_to=target_realm,
                rule_prob=rule_prob,
                lifespan=character.lifespan.get_remaining_years(),
                sin=character.karma.sin_value,
                merit=character.karma.merit_value,
                dao_heart=character.karma.dao_heart,
                lo=lo,
                hi=hi,
            )
        except Exception:
            prompt = None
        data = _router_data(
            "tribulation",
            {
                "who": brief,
                "realm_from": character.realm.name,
                "realm_to": target_realm,
                "rule_prob": rule_prob,
                "lifespan": character.lifespan.get_remaining_years(),
                "sin": character.karma.sin_value,
                "merit": character.karma.merit_value,
                "dao_heart": character.karma.dao_heart,
                "lo": lo,
                "hi": hi,
            },
            actor_id=getattr(character, "id", "system"),
        )
        if data and "success" in data:
            try:
                adj = float(data.get("adj_prob", rule_prob))
            except (TypeError, ValueError):
                adj = rule_prob
            adj = max(lo, min(hi, adj))
            # 用调整后的概率再掷一次骰，避免 AI 全知；但「判定」体现在 adj
            # 用户要的是 AI 判定：直接采用 success 字段，但校验其与 adj 一致性可放宽
            success = bool(data["success"])
            # 若 AI 给出的 success 与 adj 明显矛盾（如 adj=0.9 却 fail），以 AI 为准并记录
            reason = str(data.get("reason", "天命如此"))[:120]
            return {
                "success": success,
                "adj_prob": adj,
                "reason": reason,
                "source": "ai",
                "rule_prob": rule_prob,
            }

        # 降级：规则骰
        roll = random.random()
        success = roll < rule_prob
        reason = (
            f"劫云按天道常理轰落（规则成功率 {rule_prob*100:.1f}%，掷骰 {roll*100:.1f}）"
        )
        return {
            "success": success,
            "adj_prob": rule_prob,
            "reason": reason,
            "source": "rule",
            "rule_prob": rule_prob,
        }

    # ---------------- 世界事件提案 ----------------
    @staticmethod
    def generate_world_event(
        character,
        etype: str,
        context: str = "",
        facts: Optional[FactPack] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        生成机缘/危机/异象提案。经门禁清洗后返回，或 None（用本地模板）。
        """
        if facts is None:
            facts = build_fact_pack(character)
        try:
            from ai.play_prompts import world_event_prompt

            prompt = world_event_prompt(
                who=character.name,
                etype=etype,
                context=gate.sanitize_player_text(context),
                lifespan=character.lifespan.get_remaining_years(),
                sin=character.karma.sin_value,
                location=character.location,
                facts=facts,
            )
        except Exception:
            prompt = None
        data = _router_data(
            "world_event",
            {
                "who": character.name,
                "etype": etype,
                "context": gate.sanitize_player_text(context),
                "lifespan": character.lifespan.get_remaining_years(),
                "sin": character.karma.sin_value,
                "location": character.location,
            },
            facts=facts,
            actor_id=getattr(character, "id", "system"),
        )
        if not data:
            return None
        ok, _msg, cleaned = gate.admit("event", data, facts, actor_id=character.id)
        if not ok:
            return None
        # 事件类型透传
        et = str(data.get("type", etype)).lower()
        if et not in ("fortune", "crisis", "omen"):
            et = etype
        cleaned["type"] = et
        return cleaned

    # ---------------- 心魔：选项 +「其他」----------------
    @staticmethod
    def generate_heart_demon_session(
        character,
        facts: Optional[FactPack] = None,
    ) -> Dict[str, Any]:
        """
        生成心魔回合：幻境叙事 + 固定选项 + 保底。
        返回 {narrative, options:[{id,label,style}], source}
        """
        if facts is None:
            facts = build_fact_pack(character)
        try:
            from ai.play_prompts import heart_demon_session_prompt

            prompt = heart_demon_session_prompt(
                who=character.name,
                sin=character.karma.sin_value,
                dao_heart=character.karma.dao_heart,
                lifespan=character.lifespan.get_remaining_years(),
                facts=facts,
            )
        except Exception:
            prompt = (
                "你是心魔。根据事实包写一段问心幻境（80-160字），并给出 3 个可选应对。\n"
                f"{facts.to_prompt_block()}\n"
                '输出 JSON：{"narrative":"...","options":['
                '{"id":"force","label":"硬撼心魔","style":"刚猛"},'
                '{"id":"cut","label":"自斩执念","style":"决绝"},'
                '{"id":"yield","label":"暂避锋芒","style":"隐忍"}]}'
            )
        data = _chat_json(prompt)
        narrative = ""
        options = []
        source = "local"
        if data and data.get("narrative"):
            narrative = str(data["narrative"])[:400]
            raw_opts = data.get("options") or []
            for i, o in enumerate(raw_opts[:3]):
                if isinstance(o, dict) and o.get("label"):
                    options.append({
                        "id": str(o.get("id") or f"opt{i}"),
                        "label": str(o["label"])[:20],
                        "style": str(o.get("style", ""))[:10],
                    })
            source = "ai"
        if not narrative:
            narrative = AIGateway.generate_heart_demon_text(
                character.name, character.karma.sin_value, character=character
            )
        if len(options) < 2:
            options = [
                {"id": "force", "label": "硬撼心魔", "style": "刚猛"},
                {"id": "cut", "label": "自斩执念", "style": "决绝"},
                {"id": "yield", "label": "暂避锋芒", "style": "隐忍"},
            ]
        return {
            "narrative": narrative,
            "options": options,
            "source": source,
        }

    @staticmethod
    def judge_heart_demon_choice(
        character,
        session_narrative: str,
        choice_label: str,
        is_free_text: bool = False,
        facts: Optional[FactPack] = None,
    ) -> Dict[str, Any]:
        """
        玩家选定/自由输入后，AI 判心魔结果。
        outcome ∈ pass|wound|heart_hit|dao_crack|fail|death（death 极罕见）
        """
        if facts is None:
            facts = build_fact_pack(character)
        choice = gate.sanitize_player_text(choice_label)
        try:
            from ai.play_prompts import heart_demon_judge_prompt

            prompt = heart_demon_judge_prompt(
                who=character.name,
                choice_id="" if is_free_text else choice,
                free_text=choice if is_free_text else "",
                sin=character.karma.sin_value,
                dao_heart=character.karma.dao_heart,
                session_narrative=session_narrative,
                facts=facts,
            )
        except Exception:
            prompt = (
                "你是心魔裁决者。\n"
                f"{facts.to_prompt_block()}\n幻境：{session_narrative[:300]}\n"
                f"玩家应对：{choice}\n"
                '输出：{"outcome":"...","narrative":"结果叙事","effects":{},"tribulation_mod":-0.15~0.15}'
            )
        data = _chat_json(prompt)
        if data:
            ok, _m, cleaned = gate.admit("heart_demon", data, facts, actor_id=character.id)
            if ok:
                try:
                    tmod = float(data.get("tribulation_mod", 0.0))
                except (TypeError, ValueError):
                    tmod = 0.0
                tmod = max(-0.15, min(0.15, tmod))
                cleaned["tribulation_mod"] = tmod
                cleaned["source"] = "ai"
                return cleaned

        # 本地降级：按选项粗判
        outcome, tmod, eff, text = AIGateway._local_heart_demon_result(character, choice, is_free_text)
        ok, _m, cleaned = gate.admit(
            "heart_demon",
            {"outcome": outcome, "narrative": text, "effects": eff},
            facts,
            actor_id=character.id,
        )
        if not ok:
            cleaned = {"outcome": "pass", "narrative": "心魔如潮水退去。", "effects": {}}
        cleaned["tribulation_mod"] = tmod
        cleaned["source"] = "local"
        return cleaned

    @staticmethod
    def _local_heart_demon_result(character, choice: str, is_free_text: bool):
        c = choice
        if is_free_text:
            # 自由输入：按关键词粗判，留一点随机
            if any(w in c for w in ["认", "降", "求饶", "跪"]):
                return "heart_hit", -0.10, {"dao_heart": -12}, "心魔见你气馁，趁虚而入，道心蒙尘。"
            if any(w in c for w in ["斩", "断", "忘", "弃"]):
                return "pass", 0.08, {"dao_heart": -2}, "你挥剑斩却一段执念，心魔尖啸溃散。"
            if any(w in c for w in ["同归", "自爆", "拼命", "死"]):
                return "wound", 0.05, {"lifespan_years": -2.0, "dao_heart": -5}, "以命相搏，伤敌一千自损八百。"
            return "wound", -0.02, {"dao_heart": -6}, "应对虽奇，仍被心魔擦伤神魂。"
        if c in ("force", "硬撼心魔", "刚猛"):
            if character.karma.dao_heart >= 70:
                return "pass", 0.05, {}, "道心如铁，硬撼之下心魔寸寸崩解。"
            return "wound", -0.05, {"dao_heart": -8}, "强行硬撼，心魔反噬，气血翻涌。"
        if c in ("cut", "自斩执念", "决绝"):
            return "pass", 0.10, {"dao_heart": -3}, "自斩执念，虽痛却清明，劫云都为之一滞。"
        if c in ("yield", "暂避锋芒", "隐忍"):
            return "heart_hit", -0.08, {"dao_heart": -10}, "暂避锋芒，心魔却在识海留下阴影。"
        return "wound", 0.0, {"dao_heart": -5}, "心魔纠缠不休，你勉力稳住道基。"

    # ---------------- 斗法天命（可 escalate） ----------------
    @staticmethod
    def judge_combat(
        attacker,
        defender,
        rule_hint: float = 0.5,
        facts: Optional[FactPack] = None,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        AI 判斗法结果。可 escalate：小怪背后有大佬（spawn 经门禁）。
        outcome: kill|lose|escape|escalate|twist|standoff
        """
        if facts is None:
            facts = build_fact_pack(attacker, others=[defender])
        def_brief = (
            f"{defender.name}(id={defender.id}, {defender.realm.name}, "
            f"业力{defender.karma.sin_value}, "
            f"血煞={'是' if defender.karma.is_blood_marked() else '否'})"
        )
        try:
            from ai.play_prompts import combat_prompt

            prompt = combat_prompt(
                att_brief=_character_brief(attacker),
                def_brief=def_brief,
                rule_hint=rule_hint,
                context=gate.sanitize_player_text(context),
                facts=facts,
            )
        except Exception:
            prompt = None
        data = _router_data(
            "combat",
            {
                "att_brief": _character_brief(attacker),
                "def_brief": def_brief,
                "rule_hint": rule_hint,
                "context": gate.sanitize_player_text(context),
            },
            facts=facts,
            actor_id=getattr(attacker, "id", "system"),
        )
        if data:
            ok, _m, cleaned = gate.admit("combat", data, facts, actor_id=attacker.id)
            if ok:
                cleaned["source"] = "ai"
                cleaned["rule_hint"] = rule_hint
                return cleaned

        # 本地降级：按规则先验
        import random as _r
        roll = _r.random()
        if roll < rule_hint * 0.15:
            outcome, text = "escalate", f"看似稳操胜券，{defender.name}袖中却飞出一道传讯玉符——背后有人！"
            spawn = {"name": "幕后之人", "tier": min(5, defender.realm.tier + 1), "sin": 50, "reason": f"护短{defender.name}"}
            effects = {}
        elif roll < rule_hint:
            outcome, text = "kill", f"{attacker.name}一击得手，{defender.name}道消当场。"
            spawn = None
            effects = {"sin": 30}
        elif roll < rule_hint + 0.2:
            outcome, text = "escape", f"{defender.name}见势不妙，燃血遁走，只留一地碎布。"
            spawn = None
            effects = {}
        else:
            outcome, text = "lose", f"{defender.name}技高一筹，{attacker.name}负伤遁走。"
            spawn = None
            effects = {"exp": 10}

        ok, _m, cleaned = gate.admit(
            "combat",
            {"outcome": outcome, "narrative": text, "effects": effects, "spawn": spawn},
            facts,
            actor_id=attacker.id,
        )
        if not ok:
            cleaned = {"outcome": "standoff", "narrative": "双方试探即止，各自退开。", "effects": {}}
        cleaned["source"] = "local"
        cleaned["rule_hint"] = rule_hint
        return cleaned

    # ---------------- 自由输入意图裁决 ----------------
    @staticmethod
    def judge_free_action(
        character,
        player_text: str,
        facts: Optional[FactPack] = None,
    ) -> Dict[str, Any]:
        """
        玩家自然语言 → intent/outcome/narrative/effects
        intent ∈ observe|travel|social|fight|steal|cultivate|meditate|trade|bounty|research|roleplay
        """
        if facts is None:
            facts = build_fact_pack(character)
        text = gate.sanitize_player_text(player_text)
        try:
            from ai.play_prompts import free_action_prompt

            prompt = free_action_prompt(
                who=character.name,
                words=text,
                location=character.location,
                lifespan=character.lifespan.get_remaining_years(),
                sin=character.karma.sin_value,
                facts=facts,
            )
        except Exception:
            prompt = (
                "你是修仙世界天命，裁定玩家自由言行的后果。\n"
                f"{facts.to_prompt_block()}\n玩家言行：{text}\n"
                '输出：{"intent":"...","outcome":"...","narrative":"80-160字","effects":{},'
                '"ref_ids":[],"spawn":null,"location":null}'
            )
        data = _chat_json(prompt)
        if data:
            ok, _m, cleaned = gate.admit("event", data, facts, actor_id=character.id)
            if ok:
                cleaned["intent"] = str(data.get("intent", "roleplay")).lower()
                cleaned["outcome"] = str(data.get("outcome", cleaned["intent"])).lower()
                cleaned["source"] = "ai"
                cleaned["location"] = data.get("location")
                return cleaned

        # 本地降级
        from core.free_action import _local_intent, _local_free_result
        intent = _local_intent(text)
        local = _local_free_result(character, intent, text)
        ok, _m, cleaned = gate.admit("event", local, facts, actor_id=character.id)
        if not ok:
            cleaned = {"narrative": "言行未起波澜。", "effects": {}, "outcome": "roleplay"}
        cleaned["intent"] = intent
        cleaned["source"] = "local"
        return cleaned

    # ---------------- 自创功法（保留） ----------------
    @staticmethod
    def generate_custom_art(concept: str, creator_name: str) -> Dict[str, Any]:
        """自创功法：AI 推演 + 规则品阶/功效钳制"""
        data = _chat_json(
            f"玩家【{creator_name}】希望自创一门修仙功法，理念为：'{concept}'。\n"
            "请输出严格 JSON（不要 markdown），高收益必须伴随燃寿或天劫代价：\n"
            '{"name":"功法名","rank":"MORTAL|EARTH|MYSTIC|HEAVEN|IMMORTAL",'
            '"nature":"EVIL|ORTHODOX|NEUTRAL",'
            '"cultivation_modifiers":{"exp_gain_multiplier":1.6,'
            '"lifespan_burn_per_year":0.3,"tribulation_power_add":0.2},'
            '"spells":[{"name":"神通名","effect_type":"DAMAGE|BUFF|HEAL|CONTROL","multiplier":2.0}],'
            '"lore":"40字内背景判词","effect_summary":"中文功效说明，含修炼加速/燃寿/天劫/神通"}',
            timeout=25.0,
        )
        from core.art import clamp_art, infer_rank

        if data and data.get("name") and data.get("cultivation_modifiers"):
            try:
                valid, _ = DSLValidator.validate_custom_art(data)
            except Exception:
                valid = False
            if valid:
                data["source"] = "ai"
                return clamp_art(data)
        # 本地确定性占位
        is_evil = any(w in concept for w in ["血", "煞", "魔", "骨", "噬", "吞", "杀", "阴"])
        base = {
            "name": f"残卷·{concept[:8]}" if len(concept) >= 2 else "太虚混元功",
            "nature": "EVIL" if is_evil else "ORTHODOX",
            "cultivation_modifiers": {
                "exp_gain_multiplier": 1.45 if is_evil else 1.2,
                "lifespan_burn_per_year": 0.25 if is_evil else 0.0,
                "tribulation_power_add": 0.15 if is_evil else 0.0,
            },
            "spells": [
                {
                    "name": f"噬魂{concept[:2]}刺" if is_evil else f"纯阳{concept[:2]}印",
                    "effect_type": "DAMAGE",
                    "multiplier": 1.8 if is_evil else 1.3,
                }
            ],
            "lore": (
                f"【{creator_name}】依「{concept}」自创，"
                + ("阴煞缠身，进境虽快有伤天和。" if is_evil else "法度平稳，根基尚可。")
            ),
            "source": "local",
        }
        return clamp_art(base)

