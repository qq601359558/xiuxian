"""
统一指令目录：补全 / 帮助 / 模糊匹配共用
每条：cmd（主指令，以/开头）、aliases、usage、desc、category
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# category 顺序即展示顺序
CATEGORY_ORDER = [
    "core",
    "world",
    "cultivate",
    "social",
    "market",
    "combat",
    "faction",
    "ai",
    "other",
]

CATEGORY_CN = {
    "core": "观照与出入",
    "world": "天下与演变",
    "cultivate": "修炼历练",
    "social": "人际因果",
    "market": "坊市交易",
    "combat": "斗法除凶",
    "faction": "宗门势力",
    "ai": "天道与 AI",
    "other": "其他",
}

# 注意：desc 写「作用」；usage 写「怎么用」
COMMANDS: List[Dict[str, Any]] = [
    # 观照
    {"cmd": "/look", "aliases": ["/道身", "/look"], "usage": "/look", "desc": "观照自身：境界、寿元、灵石、位置、望气", "category": "core"},
    {"cmd": "/here", "aliases": ["/同场"], "usage": "/here", "desc": "列出同场修士与简要状态", "category": "core"},
    {"cmd": "/who", "aliases": ["/天下"], "usage": "/who", "desc": "天下名录：全服存活修士", "category": "core"},
    {"cmd": "/profile", "aliases": ["/人物", "/角色"], "usage": "/profile", "desc": "人物详情：命盘/心智/目标/回写投影", "category": "core"},
    {"cmd": "/go", "aliases": ["/前往"], "usage": "/go <地点>", "desc": "迁跃到指定地点", "category": "core"},
    {"cmd": "/join", "aliases": ["/登入"], "usage": "/join <道号>", "desc": "登入局域网大世界（恢复或新建一世）", "category": "core"},
    {"cmd": "/帮助", "aliases": ["/help", "/helpme"], "usage": "/帮助 [关键字]", "desc": "指令帮助；可按关键字模糊筛选", "category": "core"},
    {"cmd": "/退出", "aliases": ["/quit"], "usage": "/退出", "desc": "暂离修仙界（闭关仍按现实计时）", "category": "core"},

    # 天下
    {"cmd": "/世情", "aliases": ["/世界演变", "/演变", "/worldinfo"], "usage": "/世情 [简]", "desc": "世界演变总览：天道/弧/势力/望气/史笔一页看", "category": "world"},
    {"cmd": "/天道", "aliases": ["/heaven", "/导演"], "usage": "/天道 [推演]", "desc": "天道导演态势；推演=强制 AI 提案一轮", "category": "world"},
    {"cmd": "/世界弧", "aliases": ["/arc", "/弧"], "usage": "/世界弧 [推进 <id>]", "desc": "世界弧预兆→升级→决算；可强制推进", "category": "world"},
    {"cmd": "/世界弧应劫", "aliases": ["/弧应劫", "/应劫"], "usage": "/世界弧应劫 <弧id> 应劫|避祸", "desc": "对世界弧表态：应劫或避祸，决算时有回响", "category": "world"},
    {"cmd": "/望气", "aliases": ["/echo", "/天象"], "usage": "/望气 [己]", "desc": "望气天下凶地/坊市恐慌；加「己」看自身回写", "category": "world"},
    {"cmd": "/纪元回流", "aliases": ["/era", "/史笔回流"], "usage": "/纪元回流 [重建]", "desc": "史笔如何影响下一拍天道提案权重", "category": "world"},
    {"cmd": "/传说", "aliases": ["/legend", "/典籍"], "usage": "/传说 [纪元号]", "desc": "跨纪元史笔与回流摘要", "category": "world"},
    {"cmd": "/频道", "aliases": ["/channel"], "usage": "/频道 [n]", "desc": "世界新闻流：击杀/导演/围剿等大事", "category": "world"},
    {"cmd": "/公告", "aliases": ["/notice"], "usage": "/公告", "desc": "系统/GM 公告", "category": "world"},
    {"cmd": "/传闻", "aliases": ["/rumors"], "usage": "/传闻 [n]", "desc": "坊间传闻池（可能被扭曲）", "category": "world"},
    {"cmd": "/灵气", "aliases": ["/qi"], "usage": "/灵气", "desc": "全服灵气稀释：高阶修士越多修炼越慢", "category": "world"},
    {"cmd": "/纪元", "aliases": ["/season"], "usage": "/纪元", "desc": "赛季/大劫倒计时与天象", "category": "world"},
    {"cmd": "/榜", "aliases": ["/rank", "/榜单"], "usage": "/榜 [境界|战力|凶名|道行|…]", "desc": "六榜与势力投影", "category": "world"},
    {"cmd": "/秘境", "aliases": ["/secret"], "usage": "/秘境 [名|探|弃]", "desc": "秘境天机榜；进入探索步进", "category": "world"},
    {"cmd": "/告示", "aliases": ["/bountyboard"], "usage": "/告示", "desc": "悬赏告示榜", "category": "world"},
    {"cmd": "/大事记", "aliases": ["/chronicle"], "usage": "/大事记", "desc": "天道总账：近期全界大事", "category": "world"},
    {"cmd": "/近况", "aliases": [], "usage": "/近况", "desc": "世间近况 + 与你何干 + 目标", "category": "world"},
    {"cmd": "/任务", "aliases": ["/tasks", "/quest"], "usage": "/任务 [接|弃] [id]", "desc": "指引任务：初玩教学与日常委托，有明确赏格", "category": "core"},
    {"cmd": "/目标", "aliases": ["/goals"], "usage": "/目标", "desc": "查看/刷新世间目标（可接可拒）", "category": "world"},
    {"cmd": "/议程", "aliases": ["/agenda"], "usage": "/议程", "desc": "NPC 当前议程一览", "category": "world"},

    # 修炼
    {"cmd": "/闭关", "aliases": ["/meditate"], "usage": "/闭关 [小时]", "desc": "挂机闭关吐纳（有有效窗口，枯坐无益）", "category": "cultivate"},
    {"cmd": "/出关", "aliases": [], "usage": "/出关", "desc": "结束闭关并结算", "category": "cultivate"},
    {"cmd": "/突破", "aliases": ["/break"], "usage": "/突破", "desc": "引动大境界天劫（须修为圆满）", "category": "cultivate"},
    {"cmd": "/归隐", "aliases": [], "usage": "/归隐 [h]", "desc": "闭关归隐，进入离线庇护", "category": "cultivate"},
    {"cmd": "/出隐", "aliases": ["/下线"], "usage": "/出隐", "desc": "离开归隐/下线庇护状态", "category": "cultivate"},
    {"cmd": "/探险", "aliases": ["/adventure"], "usage": "/探险 [野外|秘境]", "desc": "外出历练：机缘、挖宝、杀劫", "category": "cultivate"},
    {"cmd": "/机缘", "aliases": ["/event"], "usage": "/机缘 [机缘|危机|异象]", "desc": "主动推演一则世间事件", "category": "cultivate"},
    {"cmd": "/奇遇", "aliases": ["/omen"], "usage": "/奇遇", "desc": "奇遇事件链（若有进行中可推进）", "category": "cultivate"},
    {"cmd": "/自创功法", "aliases": ["/createart"], "usage": "/自创功法 <理念>", "desc": "让天道为你创一门独门功法", "category": "cultivate"},
    {"cmd": "/功法", "aliases": ["/arts"], "usage": "/功法", "desc": "查看已学功法", "category": "cultivate"},
    {"cmd": "/穿戴", "aliases": ["/equip"], "usage": "/穿戴 <装备>", "desc": "穿戴装备，获得战力加成", "category": "cultivate"},
    {"cmd": "/卸下", "aliases": ["/unequip"], "usage": "/卸下 <装备>", "desc": "卸下指定装备", "category": "cultivate"},
    {"cmd": "/挖宝", "aliases": ["/dig"], "usage": "/挖宝", "desc": "使用藏宝图挖掘机缘/杀劫", "category": "cultivate"},

    # 社交
    {"cmd": "/交谈", "aliases": ["/talk"], "usage": "/交谈 <道号> [话]", "desc": "与 NPC/玩家交谈（会话）", "category": "social"},
    {"cmd": "/说", "aliases": [], "usage": "/说 <话>", "desc": "在当前会话中开口", "category": "social"},
    {"cmd": "/挂断", "aliases": [], "usage": "/挂断", "desc": "结束当前交谈会话", "category": "social"},
    {"cmd": "/做", "aliases": ["/言行"], "usage": "/做 <自然言行>", "desc": "自由言行：AI 判意图，规则落账", "category": "social"},
    {"cmd": "/因果", "aliases": ["/关系链"], "usage": "/因果", "desc": "个人仇怨恩义因果链", "category": "social"},
    {"cmd": "/关系", "aliases": [], "usage": "/关系 [道号]", "desc": "查看与他人的关系边", "category": "social"},
    {"cmd": "/回访", "aliases": ["/revenge"], "usage": "/回访", "desc": "依事件账触发因果回访", "category": "social"},
    {"cmd": "/拜师", "aliases": [], "usage": "/拜师 <道号>", "desc": "向对方提出拜师", "category": "social"},
    {"cmd": "/收徒", "aliases": [], "usage": "/收徒 <道号>", "desc": "向对方提出收徒", "category": "social"},
    {"cmd": "/结拜", "aliases": [], "usage": "/结拜 <道号>", "desc": "提出结拜（需同场）", "category": "social"},
    {"cmd": "/传功", "aliases": [], "usage": "/传功 <弟子>", "desc": "指点后进，消耗灵石获功德", "category": "social"},
    {"cmd": "/师门任务", "aliases": [], "usage": "/师门任务", "desc": "查看师徒日课", "category": "social"},
    {"cmd": "/名物", "aliases": [], "usage": "/名物", "desc": "名物录：知名物品/人物线索", "category": "social"},
    {"cmd": "/追查", "aliases": [], "usage": "/追查 <线索>", "desc": "追查名物或事件线索", "category": "social"},

    # 坊市
    {"cmd": "/坊市", "aliases": ["/market"], "usage": "/坊市", "desc": "商会货单、寄存、寄售一览", "category": "market"},
    {"cmd": "/购买", "aliases": ["/buy"], "usage": "/购买 <货名> [数量]", "desc": "向商会购货（恐慌时可能涨价）", "category": "market"},
    {"cmd": "/出售", "aliases": ["/sell"], "usage": "/出售 <货名> [数量]", "desc": "回售给商会（约五折，恐慌时更低）", "category": "market"},
    {"cmd": "/服用", "aliases": [], "usage": "/服用 <丹药>", "desc": "服用囊中丹药", "category": "market"},
    {"cmd": "/寄存", "aliases": [], "usage": "/寄存 <灵石>", "desc": "灵石存入坊市金库（不可被夺）", "category": "market"},
    {"cmd": "/支取", "aliases": [], "usage": "/支取 <灵石>", "desc": "自金库取出灵石", "category": "market"},
    {"cmd": "/寄售", "aliases": [], "usage": "/寄售 <货> <价>", "desc": "将货物挂上寄售栏", "category": "market"},
    {"cmd": "/买寄售", "aliases": [], "usage": "/买寄售 <编号>", "desc": "买下他人寄售货物", "category": "market"},
    {"cmd": "/撤单", "aliases": [], "usage": "/撤单 <编号>", "desc": "撤回自己的寄售", "category": "market"},
    {"cmd": "/交易", "aliases": [], "usage": "/交易 <道号>", "desc": "向对方发起当面交易", "category": "market"},
    {"cmd": "/拍卖行", "aliases": ["/auction"], "usage": "/拍卖行", "desc": "拍卖行货单", "category": "market"},
    {"cmd": "/npc货单", "aliases": [], "usage": "/npc货单", "desc": "查看 NPC 私柜货单", "category": "market"},

    # 战斗
    {"cmd": "/斗法", "aliases": ["/fight"], "usage": "/斗法 <道号>", "desc": "伏击/斗法其他修士（可夺未绑定财货）", "category": "combat"},
    {"cmd": "/探查", "aliases": ["/scan"], "usage": "/探查", "desc": "神识外放，探查周遭", "category": "combat"},
    {"cmd": "/除凶", "aliases": ["/hunt"], "usage": "/除凶", "desc": "除凶榜：血煞/重业名单", "category": "combat"},
    {"cmd": "/接除凶", "aliases": [], "usage": "/接除凶 <道号>", "desc": "接除凶令，限时缉凶", "category": "combat"},
    {"cmd": "/弃除凶", "aliases": [], "usage": "/弃除凶", "desc": "放弃当前除凶令", "category": "combat"},
    {"cmd": "/围剿", "aliases": [], "usage": "/围剿 <道号>", "desc": "同场号令围剿（须已接令且对方血煞）", "category": "combat"},
    {"cmd": "/反悬赏", "aliases": [], "usage": "/反悬赏", "desc": "花灵石反悬赏盯上你的猎人", "category": "combat"},
    {"cmd": "/挂赏", "aliases": [], "usage": "/挂赏 <道号> <赏金> [缘由] [匿]", "desc": "花灵石挂血仇悬赏", "category": "combat"},
    {"cmd": "/接令", "aliases": [], "usage": "/接令 <编号>", "desc": "揭下告示悬赏令", "category": "combat"},

    # 宗门势力
    {"cmd": "/宗门", "aliases": ["/sect"], "usage": "/宗门", "desc": "天下仙门一览与自身宗籍", "category": "faction"},
    {"cmd": "/拜入", "aliases": [], "usage": "/拜入 <宗门>", "desc": "在总坛山门叩关拜入宗门", "category": "faction"},
    {"cmd": "/叛门", "aliases": [], "usage": "/叛门", "desc": "脱离当前宗门（道心受损）", "category": "faction"},
    {"cmd": "/领俸禄", "aliases": ["/salary"], "usage": "/领俸禄", "desc": "领取宗门月俸", "category": "faction"},
    {"cmd": "/晋升", "aliases": [], "usage": "/晋升", "desc": "宗门内阶位晋升", "category": "faction"},
    {"cmd": "/势力", "aliases": ["/faction"], "usage": "/势力 [令]", "desc": "宗门关系/宗门令/围剿总览", "category": "faction"},
    {"cmd": "/宗门令", "aliases": ["/sectorder"], "usage": "/宗门令", "desc": "列出可接宗门令", "category": "faction"},
    {"cmd": "/接宗门令", "aliases": ["/acceptorder"], "usage": "/接宗门令 <令id>", "desc": "接取宗门令", "category": "faction"},
    {"cmd": "/交宗门令", "aliases": ["/doneorder"], "usage": "/交宗门令 <令id>", "desc": "完成宗门令并领贡献", "category": "faction"},
    {"cmd": "/宗门势", "aliases": ["/sectpower"], "usage": "/宗门势", "desc": "各宗实力条 + 敌对/围剿摘要", "category": "faction"},
    {"cmd": "/宗门环", "aliases": ["/sectring"], "usage": "/宗门环", "desc": "今日宗门日环主题", "category": "faction"},
    {"cmd": "/接宗门环", "aliases": [], "usage": "/接宗门环 <1|2|3>", "desc": "接取一条宗门日环", "category": "faction"},
    {"cmd": "/贡献", "aliases": [], "usage": "/贡献", "desc": "查看宗门贡献与兑换目录", "category": "faction"},
    {"cmd": "/上交", "aliases": [], "usage": "/上交 <物品>", "desc": "上交物资换宗门贡献", "category": "faction"},
    {"cmd": "/兑换", "aliases": [], "usage": "/兑换 <物品>", "desc": "用贡献兑换阵盘/丹药等", "category": "faction"},
    {"cmd": "/大劫", "aliases": ["/apocalypse"], "usage": "/大劫", "desc": "纪元终局结算（须大劫已至）", "category": "faction"},
    {"cmd": "/转世", "aliases": ["/legacy"], "usage": "/转世 [名] [加成]", "desc": "查看道统/转世出身加成", "category": "faction"},

    # AI
    {"cmd": "/ai", "aliases": ["/ai自检"], "usage": "/ai", "desc": "AI 通道探测 + 天道导演链路自检", "category": "ai"},
    {"cmd": "/AI日志", "aliases": ["/ailog"], "usage": "/AI日志 [n]", "desc": "最近 AI 调用日志", "category": "ai"},
    {"cmd": "/gm", "aliases": [], "usage": "/gm <token> <文案>", "desc": "管理员发布公告", "category": "ai"},

    # 其他 LAN
    {"cmd": "/释放", "aliases": [], "usage": "/释放", "desc": "释放被擒 NPC（若有）", "category": "other"},
    {"cmd": "/会话", "aliases": [], "usage": "/会话", "desc": "查看当前交谈会话状态", "category": "other"},
]


def _norm_cmd(c: str) -> str:
    c = (c or "").strip()
    if not c:
        return ""
    if not c.startswith("/"):
        c = "/" + c
    return c


def all_entries() -> List[Dict[str, Any]]:
    """展平为补全项：每条含 cmd / label / desc / usage / category"""
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in COMMANDS:
        primary = _norm_cmd(row.get("cmd"))
        if not primary or primary in seen:
            continue
        seen.add(primary)
        aliases = [_norm_cmd(a) for a in (row.get("aliases") or []) if a]
        out.append(
            {
                "cmd": primary,
                "aliases": aliases,
                "usage": row.get("usage") or primary,
                "desc": row.get("desc") or "",
                "category": row.get("category") or "other",
                "category_cn": CATEGORY_CN.get(row.get("category") or "other", "其他"),
            }
        )
    return out


def _score(entry: Dict[str, Any], query: str) -> float:
    """模糊匹配分：前缀 > 包含 > 别名 > 描述包含"""
    q = (query or "").strip().lower()
    if not q:
        return 0.0
    if not q.startswith("/"):
        q_path = "/" + q
    else:
        q_path = q
    cmd = entry["cmd"].lower()
    aliases = [a.lower() for a in entry.get("aliases") or []]
    desc = (entry.get("desc") or "").lower()
    usage = (entry.get("usage") or "").lower()

    best = 0.0
    if cmd == q_path or cmd == q:
        best = max(best, 100.0)
    if cmd.startswith(q_path) or cmd.startswith(q):
        best = max(best, 80.0 - (len(cmd) - len(q_path)))
    for a in aliases:
        if a == q_path or a == q:
            best = max(best, 90.0)
        if a.startswith(q_path) or a.startswith(q):
            best = max(best, 70.0)
    # 去掉斜杠后子串
    core = q.lstrip("/")
    if core and core in cmd.lstrip("/"):
        best = max(best, 55.0)
    if core and any(core in a.lstrip("/") for a in aliases):
        best = max(best, 50.0)
    if core and (core in desc or core in usage):
        best = max(best, 35.0)
    # 拼音无关的多字包含（中文子串）
    if core and len(core) >= 2:
        if core in desc:
            best = max(best, 40.0)
        if core in cmd:
            best = max(best, 45.0)
    return best


def search_commands(query: str, limit: int = 12) -> List[Dict[str, Any]]:
    """模糊搜索指令，返回带 score 的列表"""
    entries = all_entries()
    q = (query or "").strip()
    if not q:
        # 空查询：给常用优先序（category 顺序）
        cat_rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
        ranked = sorted(entries, key=lambda e: (cat_rank.get(e["category"], 99), e["cmd"]))
        return [{**e, "score": 0.0} for e in ranked[:limit]]
    scored = []
    for e in entries:
        s = _score(e, q)
        if s > 0:
            scored.append({**e, "score": s})
    scored.sort(key=lambda x: (-x["score"], x["cmd"]))
    return scored[:limit]


def format_help(query: str = "", limit: int = 80) -> str:
    """文本帮助：可带关键字过滤"""
    q = (query or "").strip()
    rows = search_commands(q, limit=limit) if q else all_entries()
    lines = ["【敕令目录】输入 / 后可继续键入以模糊筛选；网页输入框支持上下键选择"]
    if q:
        lines.append(f"筛选：「{q}」共 {len(rows)} 条")
    current = None
    for e in rows:
        cat = e.get("category_cn") or e.get("category")
        if cat != current:
            current = cat
            lines.append(f"\n■ {cat}")
        lines.append(f"  {e.get('usage') or e.get('cmd')}  — {e.get('desc')}")
    if not rows:
        lines.append("  （无匹配指令）")
    lines.append("\n完整列表亦可查阅 /帮助；场景按钮见网页「世间/修行/宗门」页。")
    return "\n".join(lines)


def catalog_json() -> Dict[str, Any]:
    return {
        "ok": True,
        "count": len(all_entries()),
        "categories": [{"id": c, "name": CATEGORY_CN.get(c, c)} for c in CATEGORY_ORDER],
        "commands": all_entries(),
    }
