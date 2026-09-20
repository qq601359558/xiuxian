"""
玩法 Prompt 库：按系统统一「角色 + 硬约束 + 输出 schema」
只拼文案；数值/门禁仍在规则侧。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ==================== 通用片段 ====================

_JSON_ONLY = "只输出 JSON，不要 markdown 代码块，不要解释。"
_NO_CHEAT = (
    "硬约束：\n"
    "1) 不得虚构不在事实包/上下文中的人物 id、地点、已落账事件。\n"
    "2) 不得瞬移、改写纪元历、突破概率框、掉落表或任何数值权威字段。\n"
    "3) 高收益必须伴随代价叙事（燃寿/业力/反噬），与上下文一致。\n"
    "4) 文风：修仙网文白话，忌现代网梗与英文。"
)


def _facts_block(facts: Optional[Any]) -> str:
    if facts is None:
        return ""
    try:
        if hasattr(facts, "to_prompt_block"):
            return facts.to_prompt_block()
        return str(facts)
    except Exception:
        return ""


# ==================== 各玩法 Builder ====================

def combat_prompt(
    att_brief: str,
    def_brief: str,
    rule_hint: float,
    context: str = "",
    facts: Optional[Any] = None,
) -> str:
    """斗法天命：AI 在胜负倾向框内写结局提案"""
    return (
        "你是斗法天命。根据事实包裁定伏击/交手结果，允许戏剧性（小人物背后可能有人）。\n"
        f"{_facts_block(facts)}\n"
        f"攻方：{att_brief}\n"
        f"守方：{def_brief}\n"
        f"规则先验胜率约 {rule_hint:.2f}（可戏剧偏离，但不可无代价必胜）\n"
        + (f"补充：{context}\n" if context else "")
        + "outcome∈kill|lose|escape|escalate|twist|standoff。\n"
        "escalate 时 spawn 一名幕后人物（tier 1-5，sin 0-200，reason 说明关系）。\n"
        "effects 仅允许 exp/stones(可负)/lifespan_years(可负)/sin/merit/dao_heart，幅度受天道钳制。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"outcome":"...","narrative":"战报","effects":{},"ref_ids":[],"spawn":null}\n'
        f"{_NO_CHEAT}"
    )


def tribulation_prompt(
    who: str,
    realm_from: str,
    realm_to: str,
    rule_prob: float,
    lifespan: float,
    sin: int,
    merit: int,
    dao_heart: int,
    lo: float = 0.05,
    hi: float = 0.95,
) -> str:
    """大境界天劫：在规则概率框内拍板成败并写判词"""
    return (
        "你是天道劫云，裁决一名修士能否渡过天劫。"
        "必须在给定成功率区间内做最终拍板，不得无视业力/功德/寿元。\n"
        f"修士：{who}；{realm_from} → {realm_to}；寿元余约 {lifespan:.1f}；"
        f"业力 {sin} 功德 {merit} 道心 {dao_heart}\n"
        f"目标境界：{realm_to}\n"
        f"规则先验成功率：{rule_prob:.3f}（你可在 [{lo:.3f}, {hi:.3f}] 内微调后判定）\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"success\": true/false, \"adj_prob\": 0~1, \"reason\": \"一句文言天命判词\"}\n"
        f"{_NO_CHEAT}"
    )


def world_event_prompt(
    who: str,
    etype: str,
    context: str,
    lifespan: float,
    sin: int,
    location: str,
    facts: Optional[Any] = None,
) -> str:
    """机缘/危机/异象：AI 生成事件，效果必须落在 caps 内（由 EventValidator 再钳）"""
    type_cn = {"fortune": "机缘", "crisis": "危机", "omen": "异象"}.get(etype, "异象")
    return (
        f"你是修仙大世界的事件引擎。生成一则「{type_cn}」事件提案。\n"
        f"{_facts_block(facts)}\n"
        f"场景补充：{context or '行止之间'}\n"
        f"主角：{who}；地点：{location}；寿元余 {lifespan:.1f}；业力 {sin}\n"
        "要求：紧贴事实包中的境界/业力/位置/因果；高收益须有代价；"
        "人物只能引用 known id 或申请 spawn；不要出现 token/系统词。\n"
        "effects 只允许：exp/stones(可负)/lifespan_years(可负)/sin/merit/dao_heart"
        "/item(可选)/skill(可选)/blood_mark(可选)。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"type":"fortune|crisis|omen","title":"短标题","narrative":"80-160字叙事",'
        '"effects":{},"ref_ids":[],"spawn":null}\n'
        f"{_NO_CHEAT}"
    )


def heart_demon_session_prompt(
    who: str,
    sin: int,
    dao_heart: int,
    lifespan: float,
    facts: Optional[Any] = None,
) -> str:
    """心魔问心开场 + 选项"""
    return (
        "你是心魔。根据事实包写一段问心幻境（80-160字），并给出 3 个可选应对。\n"
        f"{_facts_block(facts)}\n"
        f"修士：{who}；业力 {sin}；道心 {dao_heart}；寿元余 {lifespan:.1f}\n"
        f"{_JSON_ONLY}\n"
        '输出：{"narrative":"...","options":['
        '{"id":"force","label":"硬撼心魔","style":"刚猛"},'
        '{"id":"cut","label":"自斩执念","style":"决绝"},'
        '{"id":"yield","label":"暂避锋芒","style":"隐忍"}]}\n'
        f"{_NO_CHEAT}"
    )


def heart_demon_judge_prompt(
    who: str,
    choice_id: str,
    free_text: str,
    sin: int,
    dao_heart: int,
    session_narrative: str = "",
    facts: Optional[Any] = None,
) -> str:
    """心魔选择裁定"""
    return (
        "你是心魔裁决者。玩家在问心幻境中做出应对，请判定结果。\n"
        f"{_facts_block(facts)}\n"
        f"幻境：{(session_narrative or '')[:300]}\n"
        f"玩家应对：{free_text or choice_id}\n"
        "outcome 必须是 pass|wound|heart_hit|dao_crack|fail|death 之一。\n"
        "effects 仅允许：dao_heart(可负,幅度<=20), lifespan_years(可负,幅度<=5), "
        "sin(0~20), merit(0~10)。不得给灵石/修为/物品。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"outcome":"...","narrative":"结果叙事","effects":{},"tribulation_mod":-0.15~0.15}\n'
        f"{_NO_CHEAT}"
    )


def free_action_prompt(
    who: str,
    words: str,
    location: str,
    lifespan: float,
    sin: int,
    facts: Optional[Any] = None,
) -> str:
    """自由言行：先判意图再叙事，效果由门禁钳"""
    return (
        "你是修仙世界天命，裁定玩家自由言行的后果。高自由、有戏剧，但必须贴合事实包。\n"
        f"{_facts_block(facts)}\n"
        f"修士：{who}；地点：{location}；寿元余 {lifespan:.1f}；业力 {sin}\n"
        f"玩家言行：{words}\n"
        "硬约束：不得虚构不在事实包中的人物 id；不得瞬移（travel 只叙事，真正迁跃由系统 /前往）；"
        "不得直接给巨额灵石/修为；fight 只写冲突苗头，真正击杀走 /斗法。\n"
        "intent 必须是：observe|travel|social|fight|steal|cultivate|meditate|trade|bounty|research|roleplay 之一。\n"
        "outcome 可为：observe|travel|social|fight|steal|cultivate|roleplay|twist|fortune|crisis|escalate。\n"
        "effects 只允许 exp/stones/lifespan_years/sin/merit/dao_heart/item/skill，幅度受天道钳制。\n"
        "escalate 时可 spawn 幕后人物（name/tier/sin/reason/location）。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"intent":"...","outcome":"...","narrative":"80-160字",'
        '"effects":{},"ref_ids":[],"spawn":null,"location":null}\n'
        f"{_NO_CHEAT}"
    )


def adventure_prompt(
    who: str,
    target: str,
    success: bool,
    tier: int,
    location: str,
) -> str:
    """外出探险叙事（成败已由规则骰定）"""
    result = "成功" if success else "失败"
    return (
        "你是探险旁白。规则已裁定成败，你只写过程叙事，不得改结果。\n"
        f"修士 {who}（境界阶 {tier}）于【{location}】探索【{target}】，结果：{result}。\n"
        "可附 0~1 条轻量小事件描述（不落数值）。\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"narrative\":\"80-140字\",\"event_text\":null}\n"
        f"{_NO_CHEAT}"
    )


def custom_art_prompt(creator: str, concept: str) -> str:
    """自创功法 DSL"""
    return (
        "你是天道造化。为修士推演一门自创功法，高收益必须伴随燃寿或天劫代价。\n"
        f"创者：{creator}；理念：{concept}\n"
        "exp_gain_multiplier ∈ [1.1, 2.5]；lifespan_burn_per_year ∈ [0, 1.5]；"
        "tribulation_power_add ∈ [0, 0.5]；spells multiplier ∈ [1, 3]。\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"name\":\"功法名\",\"rank\":\"MORTAL|EARTH|MYSTIC|HEAVEN|IMMORTAL\","
        "\"nature\":\"EVIL|ORTHODOX|NEUTRAL\",\"cultivation_modifiers\":{{}},"
        "\"spells\":[{{\"name\",\"effect_type\",\"multiplier\"}}],\"lore\":\"40字\","
        "\"effect_summary\":\"中文功效\"}\n"
        f"{_NO_CHEAT}"
    )


def revenge_prompt(
    who: str,
    enemy: str,
    location: str,
    ledger_brief: str,
    facts: Optional[Any] = None,
) -> str:
    """复仇回访叙事"""
    return (
        "你是因果引擎。根据已落账的血仇写一幕寻仇/回访，不得否认账上事实。\n"
        f"{_facts_block(facts)}\n"
        f"当事人 {who}；仇家 {enemy}；地点 {location}\n"
        f"相关账录：{ledger_brief}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"narrative\":\"80-150字\",\"spawned\":null,\"kind\":\"revenge|repay\"}\n"
        f"{_NO_CHEAT}"
    )


def forge_prompt(kind: str, hint: str, banned_sample: str) -> str:
    """天工造化：丹/法宝/妖兽"""
    label = {"pill": "丹药", "equip": "法宝", "monster": "妖兽"}.get(kind, kind)
    schema = {
        "pill": '{"name","grade":"凡品|人品|地品","pill_exp_mult":0.08~0.5,"price","desc"}',
        "equip": '{"name","slot":"weapon|armor|trinket","grade","power_bonus":0.02~0.12,"price","desc"}',
        "monster": '{"name","tier":1~5,"danger":0.15~0.85,"desc"}',
    }.get(kind, "{}")
    return (
        f"为修仙世界生成一种新的{label}。理念提示：{hint or '随机'}\n"
        f"禁止使用这些已有名称：{banned_sample}\n"
        f"{_JSON_ONLY}\n"
        f"输出 JSON：{schema}\n"
        f"{_NO_CHEAT}"
    )


def omen_open_prompt(title: str, template_prompt: str, loc: str, who: str) -> str:
    return (
        "润色修仙奇遇开场，50~70字，意思与模板一致，文笔可更好。\n"
        f"标题：{title}；地点：{loc or '野外'}；人物：{who or '一名修士'}。\n"
        f"模板原文：{template_prompt}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"...\"}"
    )


def omen_next_prompt(title: str, step_prompt: str, prev_choice: str) -> str:
    return (
        "续写修仙奇遇下一步，50字内，承接上一步选择。\n"
        f"标题：{title}；上一步：{prev_choice or '无'}；模板：{step_prompt}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"...\"}"
    )


def omen_outcome_prompt(title: str, choice_label: str, effect_summary: str, who: str) -> str:
    return (
        "写一句奇遇落账判词，40字内，不得改数值。\n"
        f"标题：{title}；选择：{choice_label}；落账：{effect_summary}；人物：{who}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"...\"}"
    )


def ring_accept_prompt(sect: str, label: str, lore: str, who: str) -> str:
    return (
        "写一句宗门执事派活口白，40字内。\n"
        f"宗门：{sect}；任务：{label}；原句：{lore}；弟子：{who}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"...\"}"
    )


def master_task_prompt(master: str, disciple: str, label: str) -> str:
    return (
        "写一句师父派师门任务的话，40字内。\n"
        f"师父：{master}；弟子：{disciple}；任务：{label}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"...\"}"
    )


def rumor_twist_prompt(text: str) -> str:
    return (
        "把坊间传闻改写得更口语、略添油加醋，50字内，不否认已有事实。\n"
        f"原文：{text}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"...\"}"
    )


def hunt_announce_prompt(hunter: str, target: str, loc: str) -> str:
    return (
        "写一句围剿号令，40字内，要有正气或杀气。\n"
        f"发起：{hunter}；目标：{target}；地点：{loc}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"...\"}"
    )


def graduation_prompt(master: str, disciple: str) -> str:
    return (
        "写一句出师判词，40字内。\n"
        f"师父：{master}；弟子：{disciple}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"...\"}"
    )


def collusion_prompt(
    kind: str,
    link_type: str,
    link_note: str,
    loc: str,
    a_name: str,
    a_realm: str,
    b_name: str,
    b_realm: str,
    persona_a: str = "",
    persona_b: str = "",
) -> str:
    return (
        "你是修仙世界旁白。两名修士发生一幕互动，写 80 字内叙事。\n"
        f"一幕：{kind}；关系：{link_type}（{link_note}）；地点：{loc}\n"
        f"A：{a_name}（{a_realm}）\n"
        + (f"A人设：{persona_a}\n" if persona_a else "")
        + f"B：{b_name}（{b_realm}）\n"
        + (f"B人设：{persona_b}\n" if persona_b else "")
        + f"{_JSON_ONLY}\n"
        "输出：{\"narrative\":\"80字内\"}\n"
        f"{_NO_CHEAT}"
    )


def npc_talk_prompt(**kwargs: Any) -> str:
    """NPC 交谈（kwargs 由 npc_mind 组装）"""
    persona = kwargs.get("persona") or ""
    return (
        "你是修仙世界 NPC。只说符合人设与态度的话，80字以内，不要解释设定。\n"
        f"你是：{kwargs.get('name')}（{kwargs.get('realm')}）\n"
        f"身份职分：{kwargs.get('sect','散修')}·{kwargs.get('role','')}"
        + (f"。花名册备注：{kwargs.get('roster_note')}" if kwargs.get("roster_note") else "")
        + "\n"
        + (persona + "\n" if persona else "")
        + f"性格：{kwargs.get('personality')}\n"
        f"小传：{kwargs.get('bio')}\n"
        f"对交谈对象【{kwargs.get('player')}】态度：{kwargs.get('att_cn')}（值 {kwargs.get('att_value')}）\n"
        f"对方身份：{kwargs.get('player_realm')}，随身灵石 {kwargs.get('stones')}，行囊：{kwargs.get('inv')}\n"
        f"所在：{kwargs.get('location')}（{kwargs.get('safe_cn')}；此地货单：{kwargs.get('goods')}）\n"
        f"时令：{kwargs.get('time_brief')}\n"
        f"近日见闻：{kwargs.get('events')}\n"
        f"对方说：{kwargs.get('words')}\n"
        "硬约束：\n"
        "1) 必须紧扣对方原话；按身份行事（掌柜可谈本行买卖）。\n"
        "2) 对方要买本行货时应报价或引导 /购买，不得否认自己卖本行。\n"
        "3) 敌对不可突然亲热；不虚构不在场重大事件；口吻符合【人设】。\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"台词\",\"attitude_delta\":-10~10}"
    )


def npc_agenda_prompt(**kwargs: Any) -> str:
    persona = kwargs.get("persona") or ""
    rule_narrative = kwargs.get("rule_narrative") or ""
    rule_outcome = kwargs.get("rule_outcome") or ""
    rule_target = kwargs.get("rule_target") or ""
    return (
        "你是修仙世界说书人。规则引擎已裁定本 tick 结果，你只润色叙事，不得改写已发生之事。\n"
        + (persona + "\n" if persona else "")
        + f"小传：{kwargs.get('bio')}\n"
        f"性格：{kwargs.get('personality') or '未设定'}\n"
        f"本 tick 议程：{kwargs.get('ag_cn')} — {kwargs.get('ag_note')}\n"
        f"位置：{kwargs.get('loc_name')}（{kwargs.get('safe_cn')}）\n"
        f"同场：{kwargs.get('others')}\n"
        f"近日账录：\n{kwargs.get('events')}\n"
        f"规则结果 outcome={rule_outcome or '—'} 目标={rule_target or '无'}\n"
        f"规则叙事：{rule_narrative or '（无）'}\n"
        "硬约束：禁止虚构不在账上的人物；禁止否认 outcome 已写明的击杀/夺宝/突破；"
        "不得提出新的 new_location/action；narrative 60-120字，口吻符合人设。\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"narrative\":\"润色后的叙事\"}"
    )


def npc_proactive_prompt(
    name: str,
    realm: str,
    personality: str,
    persona: str,
    player: str,
    att_cn: str,
    location: str,
) -> str:
    return (
        "你是修仙世界 NPC。玩家刚到场，按人设与态度决定是否先开口。\n"
        + (persona + "\n" if persona else "")
        + f"你是 {name}（{realm}，{personality}）\n"
        f"对 {player} 态度：{att_cn}\n"
        f"所在：{location}\n"
        f"{_JSON_ONLY}\n"
        "输出：{\"line\":\"一句搭话（<=60字）\",\"delta\":-5~5}"
    )


def trade_haggle_prompt(
    buyer: str,
    seller: str,
    item: str,
    list_price: int,
    attitude_buy_mult: float,
    who_speaks: str = "seller",
    location: str = "",
    persona_seller: str = "",
) -> str:
    """NPC 专柜讨价还价旁白/台词（价格已由规则定，AI 只演戏）"""
    final_price = max(1, int(list_price * attitude_buy_mult))
    role = "掌柜" if who_speaks == "seller" else "买家"
    return (
        f"你是坊市{role}，正在谈一笔【{item}】生意。只写台词，不改价格。\n"
        + (persona_seller + "\n" if persona_seller else "")
        + f"买家 {buyer}；卖家 {seller}；地点 {location or '坊市'}。\n"
        f"标价 {list_price} 灵石；按态度系数实际成交价 **{final_price}** 灵石（你不得改）。\n"
        "语气要像市井买卖：可抱怨、可吹捧货色，但必须落在实际价上。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"line":"一句台词<=50字"}'
    )


def trade_face_offer_prompt(
    a_name: str,
    b_name: str,
    a_stones: int,
    b_stones: int,
    a_items: str,
    b_items: str,
    location: str,
) -> str:
    """当面交易报价旁白（灵石/货已由规则锁定）"""
    return (
        "你是当面交易的旁白。双方报价已锁定，你只写一句场面话。\n"
        f"地点：{location}；A {a_name} 出灵石 {a_stones}、货：{a_items or '无'}；"
        f"B {b_name} 出灵石 {b_stones}、货：{b_items or '无'}。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"line":"一句<=50字"}'
    )


def auction_bid_prompt(
    bidder: str,
    item: str,
    amount: int,
    prev_leader: str = "",
    buyout: int = 0,
) -> str:
    """拍卖喊价旁白（出价已由规则校验落账）"""
    beat = f"，压过 {prev_leader}" if prev_leader else ""
    buy_s = f"；一口价 {buyout}" if buyout else ""
    return (
        "你是拍卖行司仪。出价已由天道账房核准，你只喊一嗓子。\n"
        f"拍品【{item}】；{bidder} 出价 {amount} 灵石{beat}{buy_s}。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"line":"一句喊价<=40字"}'
    )


def auction_settle_prompt(
    item: str,
    winner: str,
    price: int,
    seller: str,
    kind: str = "落槌",
) -> str:
    """拍卖落槌/流拍判词"""
    return (
        "你是拍卖行司仪，宣读成交或流拍。不得改价格。\n"
        f"拍品【{item}】；结果：{kind}；买家 {winner or '（无）'}；卖家 {seller}；价 {price}。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"line":"一句判词<=50字"}'
    )


def market_guild_prompt(
    who: str,
    action: str,
    item: str,
    qty: int,
    price: int,
    location: str = "青云坊市",
) -> str:
    """商会买卖一句场面话（价格规则定）"""
    return (
        "你是商会柜台伙计。买卖价格由账房规定，你只说一句迎客/交割话。\n"
        f"{who} {action}【{item}】×{qty}，计 {price} 灵石；地点 {location}。\n"
        f"{_JSON_ONLY}\n"
        '输出：{"line":"一句<=40字"}'
    )


def omen_script_prompt(
    who: str,
    location: str,
    realm: str,
    season: int = 1,
    theme: str = "",
    nearby: str = "",
) -> str:
    """
    生成一幕「奇遇节点剧本」JSON。
    只出结构与台词；effects 必须落在钳制表内，由规则再 clamp。
    """
    return (
        "你是修仙世界「奇遇编剧」。为一名修士写一幕可多轮对话的奇遇剧本。\n"
        f"修士：{who}（{realm}）；所在：{location}；纪元第 {season}。\n"
        + (f"同场可引用：{nearby}\n" if nearby else "")
        + (f"主题倾向：{theme}\n" if theme else "")
        + "要求：\n"
        "1) 标题 2~8 字；intro 一句开场；goal 一句目标（玩家要表态/付出/选择）。\n"
        "2) 2~4 名参与者（speakers），可用花名册常见身份；无则用「黑市汉子」「垂死散修」等。\n"
        "3) 节点图 start + 至少 3 个中间节点 + success/fail 终节点。\n"
        "4) 每节点：speaker、prompt（该角色台词，40~80字）、choices 2~4 个、edges 若干。\n"
        "5) choice/edge 的 to 必须是本剧本已有 node id。\n"
        "6) effects 只允许：exp(≤200) stones(±200) lifespan_years(±3) sin(≤40) merit(≤40) dao_heart(±20)；"
        "多数节点 effects 为空，代价集中在少数边。\n"
        "7) 必须有强制散场可走的 refuse 边；禁止让玩家凭空得巨款或瞬移。\n"
        "8) max_turns 6~10。\n"
        f"{_JSON_ONLY}\n"
        "输出：\n"
        '{"title":"...","speakers":["甲","乙"],"intro":"...","goal":"...",'
        '"start":"n1","max_turns":8,'
        '"nodes":{"n1":{"speaker":"甲","prompt":"...","choices":[{"id":"1","label":"...","to":"n2","effects":{}}],'
        '"edges":[{"intent":"ask|buy|refuse|threat|persuade|pay|observe","to":"n2","effects":{},"reply":"..."}]},'
        '"success":{"speaker":"旁白","prompt":"...","success":true,"effects":{},"choices":[],"edges":[]},'
        '"fail":{"speaker":"旁白","prompt":"...","fail":true,"effects":{},"choices":[],"edges":[]}}}\n'
        f"{_NO_CHEAT}"
    )


# 注册表（便于测试与文档）
PROMPT_BUILDERS = {
    "combat": combat_prompt,
    "tribulation": tribulation_prompt,
    "world_event": world_event_prompt,
    "heart_demon_session": heart_demon_session_prompt,
    "heart_demon_judge": heart_demon_judge_prompt,
    "free_action": free_action_prompt,
    "adventure": adventure_prompt,
    "custom_art": custom_art_prompt,
    "revenge": revenge_prompt,
    "forge": forge_prompt,
    "omen_open": omen_open_prompt,
    "omen_next": omen_next_prompt,
    "omen_outcome": omen_outcome_prompt,
    "ring_accept": ring_accept_prompt,
    "master_task": master_task_prompt,
    "rumor_twist": rumor_twist_prompt,
    "hunt_announce": hunt_announce_prompt,
    "graduation": graduation_prompt,
    "collusion": collusion_prompt,
    "npc_talk": npc_talk_prompt,
    "npc_agenda": npc_agenda_prompt,
    "npc_proactive": npc_proactive_prompt,
    "trade_haggle": trade_haggle_prompt,
    "trade_face_offer": trade_face_offer_prompt,
    "auction_bid": auction_bid_prompt,
    "auction_settle": auction_settle_prompt,
    "market_guild": market_guild_prompt,
    "omen_script": omen_script_prompt,
}
