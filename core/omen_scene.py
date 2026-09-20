"""
奇遇弹窗会话：多轮节点图 · 自由句映射边 · 强制散场
effects 仍由规则落账；AI 仅可润色（可选）。
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.models import Character, CharacterStatus
from storage.db import WorldStateRepository, CharacterRepository

_KEY = "omen_scenes"
MAX_TURNS = 10
INVALID_LIMIT = 3


# intent 关键词 → 边标签
_INTENT_RULES: List[Tuple[str, List[str]]] = [
    ("buy", ["买", "要了", "成交", "买了", "付"]),
    ("refuse", ["不要", "不必", "算了", "告辞", "离开", "走", "告退"]),
    ("ask", ["问", "什么", "为何", "来历", "是什么", "哪", "多少", "价钱", "价"]),
    ("threat", ["杀", "抢", "动手", "滚", "找死", "劫"]),
    ("persuade", ["劝", "商量", "让一", "便宜", "讲理", "道友", "帮"]),
    ("pay", ["灵石", "给钱", "付你", "奉上", "孝敬"]),
    ("observe", ["看", "观察", "打量", "瞧", "环顾"]),
]


def _load() -> Dict[str, Any]:
    try:
        return WorldStateRepository.get(_KEY) or {}
    except Exception:
        return {}


def _save(d: Dict[str, Any]) -> None:
    try:
        WorldStateRepository.set(_KEY, d)
    except Exception:
        pass


# ==================== v1 剧本 ====================
# node: prompt, speaker, choices:[{id,label,to,effects}], edges:[{intent,to,effects?,reply}]
SCRIPTS: Dict[str, Dict[str, Any]] = {
    "black_market": {
        "title": "黑市兜售",
        "speaker": "黑市汉子",
        "intro": "巷尾阴影里有人压低斗笠：「道友，借一步。」",
        "goal": "弄清货色后再决定买或走",
        "start": "n1",
        "max_turns": 8,
        "nodes": {
            "n1": {
                "prompt": "汉子掀开布角，露出一只微温的玉匣。「八十灵石，不二价。」",
                "choices": [
                    {"id": "1", "label": "细问来历", "to": "n2", "effects": {}},
                    {"id": "2", "label": "直接买下", "to": "buy", "effects": {"stones": -80}},
                    {"id": "3", "label": "转身就走", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "ask", "to": "n2", "reply": "汉子左右看看：「问这么多……行，跟你说也无妨。」"},
                    {"intent": "buy", "to": "buy", "effects": {"stones": -80}, "reply": "「爽快。」匣子塞进你手里。"},
                    {"intent": "refuse", "to": "leave", "reply": "「不识货。」汉子缩回阴影。"},
                    {"intent": "threat", "to": "threat_fail", "reply": "「你敢动手？坊市巡夜的就在街口！」"},
                ],
            },
            "n2": {
                "prompt": "「前日从一具尸修身上摸来的，许是妖骨。」汉子竖起三根指头，「再加二十，说实话。」",
                "choices": [
                    {"id": "1", "label": "加钱听实话", "to": "n3", "effects": {"stones": -20}},
                    {"id": "2", "label": "八十拿走", "to": "buy", "effects": {"stones": -80}},
                    {"id": "3", "label": "不要了", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "pay", "to": "n3", "effects": {"stones": -20}, "reply": "「上道。」汉子压低声音……"},
                    {"intent": "buy", "to": "buy", "effects": {"stones": -80}, "reply": "「成交。」"},
                    {"intent": "refuse", "to": "leave", "reply": "「慢走。」"},
                    {"intent": "persuade", "to": "n2", "reply": "「少来这套，价钱没得谈。」"},
                ],
            },
            "n3": {
                "prompt": "「是截妖骨，能入药，也能惹祸。」汉子把匣子推过来，「一百灵石，连刚才的二十一起算你一百。」",
                "choices": [
                    {"id": "1", "label": "再付一百买下", "to": "buy", "effects": {"stones": -100, "exp": 40}},
                    {"id": "2", "label": "只当听过，走人", "to": "leave", "effects": {"exp": 15}},
                ],
                "edges": [
                    {"intent": "buy", "to": "buy", "effects": {"stones": -100, "exp": 40}, "reply": "「后会有期。」"},
                    {"intent": "refuse", "to": "leave", "effects": {"exp": 15}, "reply": "「算你谨慎。」"},
                ],
            },
            "buy": {
                "prompt": "交易已毕。玉匣入手微温。",
                "success": True,
                "effects": {"exp": 25},
                "choices": [],
                "edges": [],
            },
            "leave": {
                "prompt": "你退出巷子，灯火重新亮起来。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
            "threat_fail": {
                "prompt": "汉子厉声高喊，巡修脚步逼近。你只得罢手，名声却先臭了。",
                "fail": True,
                "effects": {"sin": 5, "dao_heart": -3},
                "choices": [],
                "edges": [],
            },
        },
    },
    "orphan_trust": {
        "title": "旧友托孤",
        "speaker": "垂死散修",
        "intro": "破屋中，旧识咳血抓住你的手腕。",
        "goal": "决定是否应下托孤，并面对路上拦截",
        "start": "n1",
        "max_turns": 8,
        "nodes": {
            "n1": {
                "prompt": "「孩子……送去落霞山外的柳家。」他塞来半块玉佩。",
                "choices": [
                    {"id": "1", "label": "应下", "to": "n2", "effects": {"merit": 8}},
                    {"id": "2", "label": "婉拒", "to": "leave", "effects": {"dao_heart": -2}},
                    {"id": "3", "label": "先问报酬", "to": "n2b", "effects": {}},
                ],
                "edges": [
                    {"intent": "persuade", "to": "n2", "effects": {"merit": 8}, "reply": "他长舒一口气：「好……好。」"},
                    {"intent": "ask", "to": "n2b", "reply": "「报酬？咳……玉佩便是信物，到了柳家自有重谢。」"},
                    {"intent": "refuse", "to": "leave", "effects": {"dao_heart": -2}, "reply": "「也罢……各安天命。」"},
                ],
            },
            "n2": {
                "prompt": "三日后，林间黑衣人拦路：「把孩子和玉佩留下。」",
                "choices": [
                    {"id": "1", "label": "死战不退", "to": "fight", "effects": {"lifespan_years": -1.0, "exp": 60}},
                    {"id": "2", "label": "交人保命", "to": "betray", "effects": {"sin": 12}},
                ],
                "edges": [
                    {"intent": "threat", "to": "fight", "effects": {"lifespan_years": -1.0, "exp": 60}, "reply": "刀光骤起！"},
                    {"intent": "refuse", "to": "betray", "effects": {"sin": 12}, "reply": "你松开了手。孩子的眼神暗下去。"},
                ],
            },
            "n2b": {
                "prompt": "「柳家不会亏待恩人。」他又咳出血沫，「你到底应不应？」",
                "choices": [
                    {"id": "1", "label": "应下", "to": "n2", "effects": {"merit": 8}},
                    {"id": "2", "label": "不应", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "persuade", "to": "n2", "effects": {"merit": 8}, "reply": "「多谢……」"},
                    {"intent": "refuse", "to": "leave", "reply": "他闭上眼。"},
                ],
            },
            "fight": {
                "prompt": "你护着孩子杀出重围，自己也添了新伤。",
                "success": True,
                "effects": {"merit": 12},
                "choices": [],
                "edges": [],
            },
            "betray": {
                "prompt": "你交出孩子。林中只余风声。",
                "fail": True,
                "effects": {"dao_heart": -8},
                "choices": [],
                "edges": [],
            },
            "leave": {
                "prompt": "你走出破屋。身后咳声渐弱。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
        },
    },
    "spring_dispute": {
        "title": "灵泉争饮",
        "speaker": "对峙散修",
        "intro": "山涧灵泉将涸，数名散修刀剑相向。",
        "goal": "在强夺、调停或离开之间表态，并承担后果",
        "start": "n1",
        "max_turns": 6,
        "nodes": {
            "n1": {
                "prompt": "「这泉我先到的！」「放屁，明明是我！」有人瞥向你：「你评评理，还是也想分一口？」",
                "choices": [
                    {"id": "1", "label": "出手强夺", "to": "rob", "effects": {"sin": 15, "exp": 70}},
                    {"id": "2", "label": "调停均分", "to": "peace", "effects": {"merit": 10, "exp": 35}},
                    {"id": "3", "label": "转身离开", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "threat", "to": "rob", "effects": {"sin": 15, "exp": 70}, "reply": "「找死！」"},
                    {"intent": "persuade", "to": "peace", "effects": {"merit": 10, "exp": 35}, "reply": "「……也罢，各取三分之一。」"},
                    {"intent": "refuse", "to": "leave", "reply": "无人阻你。"},
                    {"intent": "ask", "to": "n1", "reply": "「泉眼快干了，还问什么问！」"},
                ],
            },
            "rob": {
                "prompt": "你逼退众人，独饮灵泉。泉水入喉，道基却染上一层躁意。",
                "success": True,
                "effects": {"lifespan_years": -0.5},
                "choices": [],
                "edges": [],
            },
            "peace": {
                "prompt": "均分之下，虽只得一口，却无人记恨。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
            "leave": {
                "prompt": "你离开山涧，身后争执再起。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
        },
    },
    "stele": {
        "title": "残碑悟道",
        "speaker": "旁白",
        "intro": "荒谷残碑半埋苔中，隐有道纹流转。",
        "goal": "以何种方式面对残碑，并承受代价",
        "start": "n1",
        "max_turns": 6,
        "nodes": {
            "n1": {
                "prompt": "风过碑面，似有低诵。你欲如何？",
                "choices": [
                    {"id": "1", "label": "静坐观碑", "to": "sit", "effects": {"exp": 80}},
                    {"id": "2", "label": "强行拓印", "to": "rub", "effects": {"exp": 130, "lifespan_years": -1.0, "sin": 4}},
                    {"id": "3", "label": "绕道", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "observe", "to": "sit", "effects": {"exp": 80}, "reply": "你盘坐碑前，道纹渐明。"},
                    {"intent": "threat", "to": "rub", "effects": {"exp": 130, "lifespan_years": -1.0, "sin": 4}, "reply": "你强行拓印，碑体迸裂！"},
                    {"intent": "refuse", "to": "leave", "reply": "你绕开残碑。"},
                    {"intent": "ask", "to": "n1", "reply": "无人应答，只有风声。"},
                ],
            },
            "sit": {
                "prompt": "一夜坐忘，醒来时碑上字迹已淡。",
                "success": True,
                "effects": {"dao_heart": 3},
                "choices": [],
                "edges": [],
            },
            "rub": {
                "prompt": "拓片入手，识海却如针扎。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
            "leave": {
                "prompt": "残碑没入草际。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
        },
    },
    # ========== 群聊剧本 v2 ==========
    "escort_deal": {
        "title": "镖银争议",
        "speakers": ["驼爷", "柳三娘"],
        "intro": "坊市后巷，镖头驼爷与丹铺柳三娘争执一箱镖银的归属。",
        "goal": "在双方之间表态：帮谁、调停或离开",
        "start": "n1",
        "max_turns": 8,
        "nodes": {
            "n1": {
                "speaker": "驼爷",
                "prompt": "「这趟镖是老子丢的血汗，凭什么全归商会？」",
                "choices": [
                    {"id": "1", "label": "帮驼爷说话", "to": "n2a", "effects": {}},
                    {"id": "2", "label": "帮柳三娘", "to": "n2b", "effects": {}},
                    {"id": "3", "label": "调停均分", "to": "peace", "effects": {"merit": 8}},
                    {"id": "4", "label": "离开", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "persuade", "to": "peace", "effects": {"merit": 8}, "reply": "「……也罢，五五。」驼爷收刀。"},
                    {"intent": "threat", "to": "n2a", "reply": "驼爷冷笑：「有种你再说一遍？」"},
                    {"intent": "refuse", "to": "leave", "reply": "无人拦你。"},
                    {"intent": "ask", "to": "n1", "reply": "柳三娘插话：「箱里是丹材，不是银子！」"},
                ],
            },
            "n2a": {
                "speaker": "柳三娘",
                "prompt": "柳三娘急了：「道友莫听他胡吣！货单在我手里，你若帮他，便是与商会作对。」",
                "choices": [
                    {"id": "1", "label": "仍帮驼爷", "to": "side_tuo", "effects": {"stones": 40, "sin": 3}},
                    {"id": "2", "label": "改口帮三娘", "to": "side_liu", "effects": {"merit": 5}},
                    {"id": "3", "label": "退出", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "threat", "to": "side_tuo", "effects": {"stones": 40, "sin": 3}, "reply": "驼爷大笑：「够义气！」"},
                    {"intent": "persuade", "to": "side_liu", "effects": {"merit": 5}, "reply": "「还是这位明白。」"},
                    {"intent": "refuse", "to": "leave", "reply": "争执声渐远。"},
                ],
            },
            "n2b": {
                "speaker": "驼爷",
                "prompt": "驼爷按住刀柄：「小子，你站在商会那边？」",
                "choices": [
                    {"id": "1", "label": "退一步", "to": "peace", "effects": {"merit": 6}},
                    {"id": "2", "label": "硬顶", "to": "fight", "effects": {"exp": 50, "lifespan_years": -0.8}},
                    {"id": "3", "label": "离开", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "threat", "to": "fight", "effects": {"exp": 50, "lifespan_years": -0.8}, "reply": "刀光一闪！"},
                    {"intent": "persuade", "to": "peace", "effects": {"merit": 6}, "reply": "「哼，算你会说话。」"},
                    {"intent": "refuse", "to": "leave", "reply": "你抽身而退。"},
                ],
            },
            "side_tuo": {
                "speaker": "驼爷",
                "prompt": "驼爷分你四十灵石作谢仪。柳三娘冷着脸记下了你。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
            "side_liu": {
                "speaker": "柳三娘",
                "prompt": "三娘福了一福：「改日丹铺给你留一炉好丹。」",
                "success": True,
                "effects": {"merit": 4},
                "choices": [],
                "edges": [],
            },
            "peace": {
                "speaker": "旁白",
                "prompt": "五五均分，双方虽不痛快，却都认了账。",
                "success": True,
                "effects": {"merit": 6},
                "choices": [],
                "edges": [],
            },
            "fight": {
                "speaker": "旁白",
                "prompt": "你与驼爷过了几招，巡修喝止。你负伤脱身。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
            "leave": {
                "speaker": "旁白",
                "prompt": "你退出后巷，争执仍在继续。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
        },
    },
    "inn_whisper": {
        "title": "客栈夜话",
        "speakers": ["金满堂", "石猛"],
        "intro": "客栈角落，商会会长金满堂与守山弟子石猛压低声音交谈，见你来便停了口。",
        "goal": "试探二人在谈什么，并决定是否卷入",
        "start": "n1",
        "max_turns": 7,
        "nodes": {
            "n1": {
                "speaker": "金满堂",
                "prompt": "「道友请坐。只是闲话，莫多心。」金满堂笑得滴水不漏。",
                "choices": [
                    {"id": "1", "label": "追问", "to": "n2", "effects": {}},
                    {"id": "2", "label": "敬酒打哈哈", "to": "n2", "effects": {}},
                    {"id": "3", "label": "告退", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "ask", "to": "n2", "reply": "石猛酒碗一顿：「你谁啊？」"},
                    {"intent": "persuade", "to": "n2", "reply": "「坐坐坐。」金满堂给你满上一碗。"},
                    {"intent": "refuse", "to": "leave", "reply": "「慢走。」"},
                    {"intent": "threat", "to": "threat", "reply": "石猛按桌而起：「找茬？」"},
                ],
            },
            "n2": {
                "speaker": "石猛",
                "prompt": "石猛压低嗓门：「山门后崖夜里有光，会长想派人去瞧，又怕宗门怪罪。」",
                "choices": [
                    {"id": "1", "label": "愿去探看", "to": "accept", "effects": {"stones": 30}},
                    {"id": "2", "label": "装没听见", "to": "leave", "effects": {}},
                    {"id": "3", "label": "要更多报酬", "to": "n3", "effects": {}},
                ],
                "edges": [
                    {"intent": "pay", "to": "accept", "effects": {"stones": 30}, "reply": "金满堂推来一小袋灵石：「定金。」"},
                    {"intent": "refuse", "to": "leave", "reply": "「当我没说。」"},
                    {"intent": "ask", "to": "n3", "reply": "金满堂眯眼：「道友想要什么价？」"},
                ],
            },
            "n3": {
                "speaker": "金满堂",
                "prompt": "「五十，且只你我三人知晓。」",
                "choices": [
                    {"id": "1", "label": "成交", "to": "accept", "effects": {"stones": 50}},
                    {"id": "2", "label": "不干了", "to": "leave", "effects": {}},
                ],
                "edges": [
                    {"intent": "buy", "to": "accept", "effects": {"stones": 50}, "reply": "「痛快。」"},
                    {"intent": "refuse", "to": "leave", "reply": "「可惜。」"},
                ],
            },
            "accept": {
                "speaker": "旁白",
                "prompt": "你收下定金。后崖的事，来日再探。",
                "success": True,
                "effects": {"exp": 20},
                "choices": [],
                "edges": [],
            },
            "threat": {
                "speaker": "旁白",
                "prompt": "你出言不逊，被两人联手轰出客栈。",
                "fail": True,
                "effects": {"sin": 4},
                "choices": [],
                "edges": [],
            },
            "leave": {
                "speaker": "旁白",
                "prompt": "你起身告辞，背后窃语又起。",
                "success": True,
                "effects": {},
                "choices": [],
                "edges": [],
            },
        },
    },
}


def _clamp(effects: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    from core.event_chains import _clamp_effects

    return _clamp_effects(effects or {})


def _apply(c: Character, effects: Optional[Dict[str, Any]]) -> str:
    e = _clamp(effects)
    notes = []
    if e.get("exp"):
        c.realm.current_exp = min(c.realm.max_exp, c.realm.current_exp + int(e["exp"]))
        notes.append(f"修为+{int(e['exp'])}")
    if e.get("stones"):
        delta = int(e["stones"])
        if delta < 0 and c.spirit_stones < -delta:
            # 不够扣则失败调用方处理
            return "INSUFFICIENT_STONES"
        c.spirit_stones = max(0, c.spirit_stones + delta)
        notes.append(f"灵石{delta:+d}")
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
    return "，".join(notes) if notes else "无实质增减"


def _classify_intent(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "observe"
    for intent, keys in _INTENT_RULES:
        if any(k in t for k in keys):
            return intent
    return "chat"


def get_scene(player_id: str) -> Optional[Dict[str, Any]]:
    d = _load()
    rec = d.get(player_id)
    if not rec or rec.get("status") not in ("open",):
        return None
    return rec


def start_scene(c: Character, script_id: Optional[str] = None, allow_ai: bool = True) -> Dict[str, Any]:
    if c.status == CharacterStatus.DEAD or c.lifespan.is_dead():
        return {"success": False, "message": "身死道消。"}
    if c.status == CharacterStatus.MEDITATING:
        return {"success": False, "message": "闭关中无奇遇。"}
    existing = get_scene(c.id)
    if existing:
        return {"success": True, "scene": existing, "message": _render(existing, c), "opened": False}
    ai_sid = None
    if allow_ai and not script_id:
        ai_sid = try_generate_ai_script(c)
    sid = script_id or ai_sid or random.choice([k for k in SCRIPTS.keys() if not k.startswith("ai_")] or list(SCRIPTS.keys()))
    if sid not in SCRIPTS:
        sid = random.choice(list(SCRIPTS.keys()))
    sc = SCRIPTS[sid]
    speakers = sc.get("speakers") or ([sc.get("speaker")] if sc.get("speaker") and sc.get("speaker") != "旁白" else [])
    scene = {
        "id": uuid.uuid4().hex[:8],
        "script_id": sid,
        "title": sc.get("title") or "奇遇",
        "speaker": sc.get("speaker") or (speakers[0] if speakers else "旁白"),
        "speakers": speakers,
        "goal": sc.get("goal") or "",
        "node_id": sc.get("start") or "n1",
        "turns": 0,
        "max_turns": sc.get("max_turns") or MAX_TURNS,
        "invalid": 0,
        "status": "open",
        "messages": [
            {"who": "旁白", "text": sc.get("intro") or "", "ts": time.time()},
        ],
        "created_at": time.time(),
        "end_reason": "",
        "ai_generated": bool(ai_sid),
    }
    d = _load()
    d[c.id] = scene
    _save(d)
    return {
        "success": True,
        "scene": scene,
        "opened": True,
        "message": _render(scene, c),
    }


def _clamp_script_effects(nodes: Dict[str, Any]) -> None:
    for nd in nodes.values():
        if not isinstance(nd, dict):
            continue
        nd["effects"] = _clamp(nd.get("effects"))
        for ch in nd.get("choices") or []:
            if isinstance(ch, dict):
                ch["effects"] = _clamp(ch.get("effects"))
        for e in nd.get("edges") or []:
            if isinstance(e, dict):
                e["effects"] = _clamp(e.get("effects"))
        # 奇遇剧本额外收紧
        for holder in [nd] + list(nd.get("choices") or []) + list(nd.get("edges") or []):
            if not isinstance(holder, dict) or "effects" not in holder:
                continue
            eff = holder.get("effects") or {}
            if "stones" in eff:
                eff["stones"] = max(-200, min(200, int(eff["stones"])))
            if "exp" in eff:
                eff["exp"] = max(0, min(200, int(eff["exp"])))
            holder["effects"] = eff


def ingest_ai_script(data: Dict[str, Any], c: Character) -> Optional[str]:
    """把 AI 剧本钳成合法 SCRIPTS 条目，返回 script_id"""
    if not data or not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip()[:16]
    nodes = data.get("nodes")
    if not title or not isinstance(nodes, dict) or len(nodes) < 2:
        return None
    start = str(data.get("start") or "n1")
    if start not in nodes:
        start = next(iter(nodes.keys()))
    if not any(isinstance(v, dict) and v.get("success") for v in nodes.values()):
        return None
    nids = set(nodes.keys())
    for nd in nodes.values():
        if not isinstance(nd, dict):
            return None
        for ch in nd.get("choices") or []:
            if str(ch.get("to")) not in nids:
                return None
        for e in nd.get("edges") or []:
            if str(e.get("to")) not in nids:
                return None
    speakers = data.get("speakers") or []
    if not isinstance(speakers, list):
        speakers = []
    speakers = [str(s)[:12] for s in speakers[:4] if s]
    if not speakers:
        for nd in nodes.values():
            sp = str(nd.get("speaker") or "")
            if sp and sp != "旁白" and sp not in speakers:
                speakers.append(sp)
    sid = f"ai_{uuid.uuid4().hex[:8]}"
    script = {
        "title": title,
        "speakers": speakers,
        "speaker": speakers[0] if speakers else "旁白",
        "intro": str(data.get("intro") or "机缘忽至。")[:80],
        "goal": str(data.get("goal") or "作出选择")[:60],
        "start": start,
        "max_turns": max(6, min(10, int(data.get("max_turns") or 8))),
        "nodes": nodes,
    }
    _clamp_script_effects(script["nodes"])
    SCRIPTS[sid] = script
    return sid


def try_generate_ai_script(c: Character) -> Optional[str]:
    try:
        from core.ai_flavor import _consume
        from ai.gateway import _chat_json, ai_ready

        if not ai_ready():
            return None
        if not _consume():
            return None
        nearby = ""
        try:
            from core.here import list_here

            names = [x.get("name") for x in list_here(c)[:5] if x.get("name")]
            nearby = "、".join(names)
        except Exception:
            nearby = ""
        try:
            from ai.play_prompts import omen_script_prompt

            prompt = omen_script_prompt(
                who=c.name, location=c.location, realm=c.realm.name, nearby=nearby
            )
        except Exception:
            return None
        data = _chat_json(prompt, timeout=20.0)
        return ingest_ai_script(data, c)
    except Exception:
        return None


def _node(script_id: str, node_id: str) -> Dict[str, Any]:
    return (SCRIPTS.get(script_id) or {}).get("nodes", {}).get(node_id) or {}


def _render(scene: Dict[str, Any], c: Character) -> str:
    node = _node(scene["script_id"], scene["node_id"])
    speakers = scene.get("speakers") or []
    who_line = " · ".join(speakers) if speakers else (scene.get("speaker") or "旁白")
    lines = [
        f"【奇遇 · {scene['title']}】{who_line}",
        f"目标：{scene.get('goal')}",
        f"进度：第 {int(scene.get('turns') or 0)+1}/{scene.get('max_turns')} 回合 · 无效 {scene.get('invalid')}/{INVALID_LIMIT}",
    ]
    if speakers:
        lines.append("在场：" + "、".join(speakers) + "（可 @名字 指定应答）")
    lines.append("")
    for m in (scene.get("messages") or [])[-12:]:
        lines.append(f"{m.get('who')}：{m.get('text')}")
    sp = node.get("speaker") or scene.get("speaker") or "旁白"
    prompt = node.get("prompt") or ""
    if prompt and (not scene["messages"] or scene["messages"][-1].get("text") != prompt):
        lines.append(f"{sp}：{prompt}")
    choices = node.get("choices") or []
    if choices:
        opts = " | ".join(f"{x['id']}.{x['label']}" for x in choices)
        lines.append(f"选项：{opts}（/奇遇 <n> 或 /奇遇说 [@某人] <话>）")
    lines.append(f"灵石 {c.spirit_stones} · 修为 {c.realm.current_exp}/{c.realm.max_exp} · 寿元 {c.lifespan.get_remaining_years():.1f}")
    return "\n".join(lines)


def _parse_at(text: str, speakers: List[str]) -> Tuple[Optional[str], str]:
    """解析 @名字 前缀；返回 (target_name or None, 剩余话)"""
    t = (text or "").strip()
    if not t.startswith("@"):
        return None, t
    # @柳三娘 话...
    rest = t[1:]
    for name in speakers:
        if rest.startswith(name):
            return name, rest[len(name):].strip(" ：:")
    # 模糊：@后到空格
    parts = rest.split(None, 1)
    if parts:
        return parts[0], (parts[1] if len(parts) > 1 else "")
    return None, t


def _end(scene: Dict[str, Any], status: str, reason: str) -> None:
    scene["status"] = status
    scene["end_reason"] = reason
    scene["ended_at"] = time.time()
    d = _load()
    d[scene.get("player_id") or ""] = scene
    # player_id 可能未写在 scene 上，由调用方 save_scene


def save_scene(player_id: str, scene: Dict[str, Any]) -> None:
    d = _load()
    d[player_id] = scene
    _save(d)


def _finish(c: Character, scene: Dict[str, Any], status: str, reason: str, effects: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    summary = _apply(c, effects)
    scene["status"] = status
    scene["end_reason"] = reason
    save_scene(c.id, scene)
    CharacterRepository.save(c)
    tag = "奇遇了结" if status == "success" else ("奇遇散场" if status == "forced" else "奇遇终")
    try:
        from core.world_channel import WorldChannel

        if status == "success":
            WorldChannel.post(
                "chain",
                f"【奇遇】{c.name} 走通「{scene['title']}」。",
                level="info",
                actor=c.name,
                location=c.location,
            )
    except Exception:
        pass
    return {
        "success": True,
        "ended": True,
        "omen_status": status,
        "message": f"【{tag}】{reason}\n落账：{summary}",
        "scene": scene,
    }


def choose(c: Character, choice_id: str) -> Dict[str, Any]:
    scene = get_scene(c.id)
    if not scene:
        return {"success": False, "message": "当前无奇遇。/奇遇 或四处走走。"}
    node = _node(scene["script_id"], scene["node_id"])
    pick = next((x for x in (node.get("choices") or []) if str(x.get("id")) == str(choice_id)), None)
    if not pick:
        return {"success": False, "message": "无效选项。"}
    effects = pick.get("effects") or {}
    # 灵石预检
    if int(effects.get("stones") or 0) < 0 and c.spirit_stones < -int(effects["stones"]):
        return {"success": False, "message": f"灵石不足，需 {-int(effects['stones'])}。"}
    scene["messages"].append({"who": "你", "text": f"（选择）{pick['label']}", "ts": time.time()})
    scene["turns"] = int(scene.get("turns") or 0) + 1
    scene["node_id"] = pick.get("to") or scene["node_id"]
    nxt = _node(scene["script_id"], scene["node_id"])
    save_scene(c.id, scene)
    if nxt.get("success"):
        return _finish(c, scene, "success", nxt.get("prompt") or "奇遇了结。", (nxt.get("effects") or {}))
    if nxt.get("fail"):
        return _finish(c, scene, "failed", nxt.get("prompt") or "此局未成。", (nxt.get("effects") or {}))
    # 中间节点：先落 edge/choice effects
    if effects:
        sm = _apply(c, effects)
        CharacterRepository.save(c)
        scene["messages"].append({"who": "落账", "text": sm, "ts": time.time()})
        save_scene(c.id, scene)
    if int(scene.get("turns") or 0) >= int(scene.get("max_turns") or MAX_TURNS):
        return _finish(c, scene, "forced", "久拖不决，机缘散去。", {})
    return {
        "success": True,
        "ended": False,
        "message": _render(scene, c),
        "scene": scene,
    }


def say(c: Character, text: str) -> Dict[str, Any]:
    scene = get_scene(c.id)
    if not scene:
        return {"success": False, "message": "当前无奇遇会话。"}
    text = (text or "").strip()[:200]
    if not text:
        return {"success": False, "message": "你想说什么？"}
    speakers = scene.get("speakers") or []
    at_name, body = _parse_at(text, speakers)
    if at_name:
        scene["messages"].append({"who": c.name, "text": f"@{at_name} {body}".strip(), "ts": time.time()})
    else:
        scene["messages"].append({"who": c.name, "text": text, "ts": time.time()})
    intent = _classify_intent(body if at_name else text)
    node = _node(scene["script_id"], scene["node_id"])
    edge = next((e for e in (node.get("edges") or []) if e.get("intent") == intent), None)
    speaker = node.get("speaker") or scene.get("speaker") or "旁白"
    # @ 指定：若该人不在当前节点 speaker，给一句应答仍推进（或仅回一句）
    if at_name and at_name != speaker and at_name in speakers:
        extra = f"（{at_name}在旁听着）"
        scene["messages"].append({"who": at_name, "text": f"「{extra}」", "ts": time.time()})

    if not edge:
        scene["invalid"] = int(scene.get("invalid") or 0) + 1
        scene["turns"] = int(scene.get("turns") or 0) + 1
        reply = "对方皱眉，并不接话。"
        if speaker == "旁白":
            reply = "风过无痕，无人应答。"
        scene["messages"].append({"who": speaker, "text": reply, "ts": time.time()})
        if scene["invalid"] >= INVALID_LIMIT:
            save_scene(c.id, scene)
            return _finish(c, scene, "forced", "你尽说些不相干的，对方面色一沉，此局作罢。", {})
        if int(scene.get("turns") or 0) >= int(scene.get("max_turns") or MAX_TURNS):
            save_scene(c.id, scene)
            return _finish(c, scene, "forced", "久候无果，机缘散去。", {})
        save_scene(c.id, scene)
        return {"success": True, "ended": False, "intent": intent, "message": _render(scene, c), "scene": scene}

    effects = edge.get("effects") or {}
    if int(effects.get("stones") or 0) < 0 and c.spirit_stones < -int(effects["stones"]):
        scene["messages"].append({"who": speaker, "text": "「灵石不够就莫谈。」", "ts": time.time()})
        save_scene(c.id, scene)
        return {"success": True, "ended": False, "message": _render(scene, c), "scene": scene}

    reply = edge.get("reply") or "……"
    # 可选 AI 润色
    try:
        from core import ai_flavor

        tip = ai_flavor._ask(
            f"修仙奇遇对白润色，40字内，只输出 JSON {{\"line\":\"...\"}}。"
            f"角色：{speaker}；意图：{intent}；原句：{reply}",
            timeout=8.0,
        )
        if tip:
            reply = tip
    except Exception:
        pass
    scene["messages"].append({"who": speaker, "text": reply, "ts": time.time()})
    scene["turns"] = int(scene.get("turns") or 0) + 1
    scene["invalid"] = 0
    scene["node_id"] = edge.get("to") or scene["node_id"]
    save_scene(c.id, scene)

    # 边效果先落账（含跳向 success/fail）
    if effects:
        sm = _apply(c, effects)
        if sm == "INSUFFICIENT_STONES":
            return {"success": False, "message": "灵石不足。"}
        CharacterRepository.save(c)
        scene["messages"].append({"who": "落账", "text": sm, "ts": time.time()})
        save_scene(c.id, scene)

    nxt = _node(scene["script_id"], scene["node_id"])
    if nxt.get("success"):
        return _finish(c, scene, "success", nxt.get("prompt") or "奇遇了结。", nxt.get("effects") or {})
    if nxt.get("fail"):
        return _finish(c, scene, "failed", nxt.get("prompt") or "此局未成。", nxt.get("effects") or {})
    if int(scene.get("turns") or 0) >= int(scene.get("max_turns") or MAX_TURNS):
        return _finish(c, scene, "forced", "回合已尽，机缘散去。", {})
    return {"success": True, "ended": False, "intent": intent, "message": _render(scene, c), "scene": scene}


def abandon(c: Character) -> Dict[str, Any]:
    scene = get_scene(c.id)
    if not scene:
        return {"success": False, "message": "当前无奇遇。"}
    scene["messages"].append({"who": "你", "text": "（抽身而退）", "ts": time.time()})
    return _finish(c, scene, "abandoned", "你主动抽身，天道不罪。", {})
