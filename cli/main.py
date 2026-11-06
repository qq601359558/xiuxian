"""
《天道因果录》交互式文字 MUD 客户端 (主运行入口)
"""
import sys
from pathlib import Path

# 确保项目根路径位于 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.prompt import Prompt
from storage.db import (
    init_db,
    CharacterRepository,
    ChronicleRepository,
    LegacyRepository,
    BountyRepository,
    KarmaLinkRepository,
    MarketListingRepository,
)
from core.models import CharacterStatus
from core.clock import WorldClock
from core.breakthrough import BreakthroughEngine
from core.combat import CombatEngine
from core.legacy import LegacyEngine, LegacyAccount
from core.bounty import BountyEngine, BountyStatus, BOUNTY_MIN_REWARD
from core.market import MarketEngine
from core.pets import PetEngine
from core.farm import FarmEngine, split_sow_args
from core.quests import QuestEngine
from core.promises import PROMISE_KIND_ALIASES, PromiseEngine
from core.council import CouncilEngine
from core.art_slots import ArtSlotEngine
from core.body_soul import BodySoulEngine
from core.heart_demon_state import DemonStateEngine
from core.books import BOOK_ITEM, BookEngine
from core.events import EventEngine
from core.heart_demon import HeartDemonEngine
from core.combat_fate import CombatFateEngine
from core.free_action import FreeActionEngine
from core.memory import RevengeEngine, record_event
from core.npc_agenda import NpcAgendaEngine
from core.npc_mind import NpcDialogueEngine, ensure_mind, attitude_toward, ATTITUDE_LABELS
from core.here import list_here, format_here
from core.profile import build_profile, format_profile, find_by_name
from core.npc_proactive import NpcProactiveEngine
from ai.gateway import AIGateway
from ai.gate import gate
from ai.facts import build_fact_pack
from config import (
    WORLD_LOCATIONS,
    SECTS_CONFIG,
    LIFESPAN_WARNING_YEARS,
    MEDITATION_MAX_HOURS,
    LEGACY_BOOSTS,
    LEGACY_MAX_BOOSTS_PER_LIFE,
    BOUNTY_FEE_RATE,
    BOUNTY_ANON_EXTRA_FEE,
    BOUNTY_ACTIVE_HOURS,
    BOUNTY_MAX_PER_TARGET,
    ITEM_CATALOG,
    MARKET_MAX_LISTINGS,
    ai_available,
    local_ai_allowed,
    ai_unavailable_message,
)
from cli.views import (
    render_character_sheet,
    render_meditation_summary,
    render_meditation_locked,
    render_tribulation_result,
    render_combat_result,
    render_scan_panel,
    render_custom_art,
    render_world_map,
    render_sect_panel,
    render_legacy_settlement,
    render_legacy_panel,
    render_birth_boost_result,
    render_bounty_board,
    render_karma_links,
    render_market_panel,
    render_world_event,
)

console = Console()
USER_ID = "local_player_01"


def seed_world_npcs():
    """预生成世界 NPC 阵容（幂等），并保证告示榜有示例血令"""
    try:
        from core.npc_roster import seed_roster
        seed_roster()
    except Exception:
        pass

    # 给血刀老祖挂示例血令（若榜上空）
    if not BountyRepository.list_all():
        try:
            import time as _time
            from core.bounty import Bounty
            target = CharacterRepository.get_by_name("血刀老祖")
            issuer = CharacterRepository.get_by_name("云鹤道人")
            if target and issuer:
                sample = Bounty(
                    issuer_id=issuer.id,
                    issuer_name=issuer.name,
                    issuer_anonymous=False,
                    target_id=target.id,
                    target_name=target.name,
                    reward=200,
                    reason="屠戮落霞散修满门，天理难容",
                    status=BountyStatus.OPEN,
                    created_at=_time.time(),
                    expires_at=_time.time() + BOUNTY_ACTIVE_HOURS * 3600.0,
                )
                BountyRepository.save(sample)
        except Exception:
            pass


def print_banner():
    banner = """
[bold gold1]
 ╔══════════════════════════════════════════════════════════════╗
 ║               《 天 道 因 果 录 》                           ║
 ║        —— 天地不仁以万物为刍狗 · 向死求仙录                  ║
 ╚══════════════════════════════════════════════════════════════╝
[/bold gold1]
[dim]· 全服灵气零和 | 寿元现实流逝 | 因果天劫反噬 | 万物皆为刍狗[/dim]
"""
    console.print(banner)
    if not ai_available() and not local_ai_allowed():
        console.print(f"[bold red]{ai_unavailable_message()}[/bold red]")
        console.print("[yellow]本作核心体验依赖服务器 AI；未配置时交谈/言行/天命不可用。[/yellow]\n")
    elif not ai_available() and local_ai_allowed():
        console.print("[yellow]⚠ 开发模式：ALLOW_LOCAL_AI=1，使用本地模板降级（非正式体验）[/yellow]\n")


# 局域网专有指令（QA2-03）：仅 LAN 服（server/world.py）实现，CLI 本地引擎
# 无派发。run_mud 派发末尾有专有提示分支（输入这些指令得到专有提示而非
# 「未知名敕令」），成员以本集合为准；帮助文本的「局域网专有」行是另一份
# 展示字面量，须与本集合保持一致（tests/test_qa2_fix_regressions.py 有
# 一致性断言防漂移）。
# 既有声明 9 个（/说 /释放 /拜师 /结拜 /交易 /宗门环 /探险 /秘境 /AI自检）
# + QA2-03 补入 19 个（web data-cmd 有按钮、server 有处理器、CLI 无本地实现；
# 逐条核对无异名等价实现，如 /纪元 的 server 实现为纪元面板、CLI /天象 只管
# 天象主题而非其别名；/榜 为六榜面板，CLI 只有单榜 /飞升榜）。
LAN_ONLY_COMMANDS = frozenset({
    "/说", "/释放", "/拜师", "/结拜", "/交易", "/宗门环", "/探险", "/秘境",
    "/AI自检",
    "/look", "/who", "/传说", "/传闻", "/公告", "/出隐", "/功法", "/叛门",
    "/大劫", "/归隐", "/挖宝", "/晋升", "/榜", "/灵气", "/生成丹药",
    "/生成妖兽", "/生成法宝", "/纪元", "/频道",
})
# 派发处 action 已被 .lower() 规范化（如 /AI自检 → /ai自检），故另备
# 小写规范形集合供派发比对（评审 M1：否则 /AI自检 成员永远命中不了）。
LAN_ONLY_COMMANDS_LOWER = frozenset(c.lower() for c in LAN_ONLY_COMMANDS)


def print_help():
    help_text = """
[bold cyan]【天道敕令 · 常用指令】[/bold cyan]
  [bold yellow]/道身[/bold yellow]                 - 观照自身命盘、境界、剩余寿元与宗门归属
  [bold yellow]/道统[/bold yellow]                 - 查阅道统点、前世典籍与转世出身兑换目录
  [bold yellow]/地图[/bold yellow]                 - 查阅九州山海全景舆图、地脉灵气浓度与安全禁制
  [bold yellow]/宗门[/bold yellow]                 - 查阅天下仙门宗派榜、门规约束、月俸待遇与个人宗籍
  [bold yellow]/拜入 <宗门>[/bold yellow]          - 前往总坛山门参加入门考核（如：/拜入 青云宗）
  [bold yellow]/领俸禄[/bold yellow]               - 宗门弟子每过现实2小时（游戏内1个月）可领月度灵石俸禄
  [bold yellow]/议政[/bold yellow]                 - 宗门长老议政面板（本场议题/长老立场/票数/宗门状态）
  [bold yellow]/投票 <支持|反对>[/bold yellow]      - 就本场议题投票（一人一票，截止前可改票）
  [bold yellow]/游说 <长老名>[/bold yellow]          - 备礼灵石游说长老向支持松动（成本递增，有次数上限）
  [bold yellow]/前往 [地点][/bold yellow]           - 查阅灵脉或御剑迁跃（不同福地灵气浓度与危险度各异）
  [bold yellow]/闭关 <现实小时> [碎石][/bold yellow]- 步入洞府封门静修（现实时间并行！野外无阵盘则裸闭极易被杀）
  [bold yellow]/出关[/bold yellow]                 - 提前收功出定破关（按已过去现实时间结算修为）
  [bold yellow]/探查[/bold yellow]                 - 神识外放，感知方圆十里之内的修士灵压与虚实
  [bold yellow]/同场[/bold yellow]                 - 列出当前地点全部修士/NPC（性格、对你的态度、议程）
  [bold yellow]/人物 <道号>[/bold yellow]           - 详查人物档案（无参数查自己）
  [bold yellow]/名录[/bold yellow]                 - 预生成阵容一览（道号/地点/性格）
  [bold yellow]/交谈 <道号> [话][/bold yellow]      - 与同场 NPC 对话（自由文本可含赠礼/偷窃/擒拿/买卖等动作）
  [bold yellow]/突破[/bold yellow]                 - 修为圆满时引动九天雷劫，直面心魔与生死
  [bold yellow]/斗法 <道号>[/bold yellow]          - 伏击或截杀其他修士，夺取灵石（如：/斗法 陆仁贾）
  [bold yellow]/告示[/bold yellow]                 - 查阅坊市悬赏告示榜
  [bold yellow]/挂赏 <道号> <赏金> [缘由][/bold yellow]- 花灵石挂血仇悬赏（句末加「匿」可匿名）
  [bold yellow]/接令 <编号>[/bold yellow]           - 揭下告示，接令猎凶（击杀后自动领赏）
  [bold yellow]/因果[/bold yellow]                 - 查看因果关系列表（KarmaLink 仇/恩/师徒/宗门边；回访请用 /回访；server 端 /因果 为回访别名）
  [bold yellow]/回访[/bold yellow]                 - 依事件账触发因果回访（寻仇/旧怨）
  [bold yellow]/因果链[/bold yellow]               - 天道事件链面板（恩/仇/诺/血仇的发酵进度与近史；与 /因果 关系列表不同）
  [bold yellow]/坊市[/bold yellow]                 - 商会货单（当地市价）、金库寄存、玩家寄售
  [bold yellow]/行情[/bold yellow]                 - 天下行情：各区域产地价与价差、跑商路线
  [bold yellow]/版图 [区域][/bold yellow]           - 宗门势力版图：各区域主导宗门与本宗影响力
  [bold yellow]/飞升榜 [我|本纪元|道号][/bold yellow] - 历世纪念碑：已坐化前世跨纪元综合榜（现世人物看 /榜）
  [bold yellow]/天象[/bold yellow]                 - 本纪元天象主题：全服修正与剩余天数（纪元轮换）
  [bold yellow]/购买 <名目> [数量][/bold yellow]     - 向商会购货（如：/购买 一阶青木迷踪阵）
  [bold yellow]/出售 <名目> [数量][/bold yellow]     - 回售给商会（约五折）
  [bold yellow]/寄存 <数量>[/bold yellow]           - 灵石存入坊市金库（不可被夺）
  [bold yellow]/支取 <数量>[/bold yellow]           - 自金库取出灵石
  [bold yellow]/钱包[/bold yellow]                 - 账户钱包：余额与最近流水（死亡归集款项挂账户名下）
  [bold yellow]/钱包提取 <金额>[/bold yellow]       - 自账户钱包提取灵石到随身（零手续费）
  [bold yellow]/寄售 <货物> <价格>[/bold yellow]     - 将随身货物挂上寄售栏
  [bold yellow]/买寄售 <编号>[/bold yellow]         - 买下他人寄售货物
  [bold yellow]/撤单 <编号>[/bold yellow]           - 撤回自己的寄售
  [bold yellow]/典当 [物品][/bold yellow]           - 无参看当票；带物品名典当 1 件（市价五折，3 天内可赎）
  [bold yellow]/赎回 <物品>[/bold yellow]           - 按典当额+固定息赎回典当物，逾期没收
  [bold yellow]/拍卖[/bold yellow]                 - 拍卖行看板（含待开场预告与 NPC 跟价）
  [bold yellow]/上拍 <货物> <底价> [一口价][/bold yellow] - 上拍随身货物（120 分钟落槌，成交抽成 5%）
  [bold yellow]/拍 <编号> <出价>[/bold yellow]       - 竞价（出价冻结，被超价自动退回）
  [bold yellow]/出价 <金额>[/bold yellow]           - 仅一场在拍时直拍该件（多场请用 /拍）
  [bold yellow]/一口 <编号>[/bold yellow]           - 按一口价立即落槌
  [bold yellow]/撤拍 <编号>[/bold yellow]           - 撤回自己无出价的拍品
  [bold yellow]/服用 <丹药>[/bold yellow]           - 服用囊中丹药
  [bold yellow]/灵宠[/bold yellow]                 - 灵宠面板（遇兽在探险，属局域网游径；存档互通）
  [bold yellow]/契约 <兽名>[/bold yellow]          - 与待契约灵兽结契（耗灵石）
  [bold yellow]/喂养 <宠名> [丹药][/bold yellow]   - 灵石或丹药喂养灵宠
  [bold yellow]/出战 <宠名>[/bold yellow]          - 令灵宠随行出战（唯一）
  [bold yellow]/休息 <宠名>[/bold yellow]          - 令灵宠退下休息
  [bold yellow]/放生 <宠名>[/bold yellow]          - 放归灵宠于山林
  [bold yellow]/洞府[/bold yellow]                 - 洞府灵田面板（等级/地块/长势）
  [bold yellow]/开辟[/bold yellow]                 - 安全区开辟洞府（300 灵石，灵田 2 块）
  [bold yellow]/播种 <种子名> [数量][/bold yellow] - 灵田播种（种子先在坊市购买）
  [bold yellow]/收获[/bold yellow]                 - 收获全部成熟作物入行囊
  [bold yellow]/升级洞府[/bold yellow]             - 升级洞府（扩田 + 闭关加成，最高 3 级）
  [bold yellow]/委托[/bold yellow]                 - NPC 委托面板（可接/进行中）
  [bold yellow]/接委托 <NPC名|编号>[/bold yellow] - 接取一条委托链（2–4 环，同时限 1 条）
  [bold yellow]/交付[/bold yellow]                 - 向交付对象当面交付当前环
  [bold yellow]/弃委托[/bold yellow]               - 放弃进行中委托（无惩罚）
  [bold yellow]/诺言[/bold yellow]                 - 诺言账面板（进行中/待应诺/近史；唯指令立诺入账，交谈口头应承不算）
  [bold yellow]/许诺 <对象> <诺目> [参数][/bold yellow] - 立诺：赠物 <物品名>|抵达 <地点>|委托|不攻（对玩家须对方 /应诺 才生效）
  [bold yellow]/应诺 [立诺者名][/bold yellow]     - 应下他人向你立的诺（义务只在立诺者）
  [bold yellow]/毁诺 [受诺人名][/bold yellow]     - 毁弃未结之诺（已生效者按违约记账；待应诺者可无代价撤回）
  [bold yellow]/除凶[/bold yellow]                 - 除凶榜（血煞/重业者之令，发布→接令→追凶→围剿→结算）
  [bold yellow]/接令 <道号>[/bold yellow]          - 接除凶令（一人一令，单令上限 5 人；/接除凶 同）
  [bold yellow]/追凶[/bold yellow]                 - 追凶情报（区域级快照，每小时刷新，不泄确切行踪）
  [bold yellow]/弃令[/bold yellow]                 - 放弃所接除凶令（/弃除凶 同）
  [bold yellow]/心法[/bold yellow]                 - 心法槽位面板（主修 1 + 辅修 2）
  [bold yellow]/主修 <功法名>[/bold yellow]       - 定主修（闭关修为 +10%，变更有 1 小时冷却）
  [bold yellow]/辅修 <功法名>[/bold yellow]       - 纳辅修（每门斗法战力 +3%，最多 2 门）
  [bold yellow]/卸功 <功法名>[/bold yellow]       - 卸下主修或辅修
  [bold yellow]/炼体 [修炼 [n]][/bold yellow]     - 炼体副修（妖兽内丹+灵石升层：战力+1%/层、寿元+1岁/层，满 10 层）
  [bold yellow]/炼神 [修炼 [n]][/bold yellow]     - 炼神副修（百年灵芝+灵石升层：有效道心+2/层、神识+3/层，满 10 层）
  [bold yellow]/镇魔 [服丹|静坐][/bold yellow]    - 心魔长卷/镇压（魔念由杀业·血煞·反噬滋长，滋长以上会在突破问心/闭关结算时发作）
  [bold yellow]/著书 [写][/bold yellow]           - 著书立说（灵感 10 + 燃寿 1 年成书；无参看面板：灵感/声望/在持手稿）
  [bold yellow]/研读 [书名][/bold yellow]         - 研读所持亲笔手稿（他人之作首次研读得修为/道心，作者得声望）
  [bold yellow]/机缘 [机缘|危机|异象][/bold yellow]  - 主动推演一则世间事件（外出/出关后亦可能自动触发）
  [bold yellow]/做 <言行>[/bold yellow]             - 自由输入，由天命裁决后果（例：/做 我跪在坊市磕头求丹）
  [bold yellow]/世情[/bold yellow]                 - 离线江湖追赶 + NPC tick + 因果账
  [bold yellow]/天道[/bold yellow]                 - 天道导演态势；/天道 推演 强制一轮
  [bold yellow]/近况[/bold yellow]                 - 世间近况 + 与你何干 + 世间目标
  [bold yellow]/目标[/bold yellow]                 - 查看/刷新世间目标
  [bold yellow]/议程[/bold yellow]                 - 查看 NPC 当前议程一览
  [bold yellow]/自创功法 <理念>[/bold yellow]       - 消耗神识让天道为你自创独门法门（如：/自创功法 噬血炼骨）
  [bold yellow]/大事记[/bold yellow]               - 翻阅天道总账，查看近期全界因果杀戮
  [dim]局域网专有：/说 /释放 /拜师 /结拜 /交易 /宗门环 /探险 /秘境 /AI自检 /look /who /传说 /传闻 /公告 /出隐 /功法 /叛门 /大劫 /归隐 /挖宝 /晋升 /榜 /灵气 /生成丹药 /生成妖兽 /生成法宝 /纪元 /频道 等，请连 LAN 服使用[/dim]
  [bold yellow]/帮助[/bold yellow]                 - 查看本指令菜单
  [bold yellow]/退出[/bold yellow]                 - 暂离修仙界（若正在闭关，离线期间现实时间照常计时）
"""
    console.print(help_text)


def _parse_boost_keys(raw: str):
    """把 '1 2' / 'stones lifespan' 解析为 boost key 列表。

    转世继承：heirloom 可带参数 token（heirloom:<物品名>）整段保留；
    其余新键（art_memory/bond_echo）随 LEGACY_BOOSTS 目录自然支持编号/键名/中文名。
    """
    if not raw or not raw.strip():
        return []
    boosts = LegacyEngine.list_boosts()
    keys = [b["key"] for b in boosts]
    names = [b["name"] for b in boosts]
    picked = []
    picked_bases = []
    for token in raw.replace(",", " ").split():
        t = token.strip()
        if t.startswith("heirloom:") and len(t) > len("heirloom:"):
            if "heirloom" not in picked_bases:
                picked.append(t)
                picked_bases.append("heirloom")
        elif t.isdigit():
            idx = int(t) - 1
            if 0 <= idx < len(keys) and keys[idx] not in picked_bases:
                picked.append(keys[idx])
                picked_bases.append(keys[idx])
        elif t in keys and t not in picked_bases:
            picked.append(t)
            picked_bases.append(t)
        else:
            for i, name in enumerate(names):
                if t in name and keys[i] not in picked_bases:
                    picked.append(keys[i])
                    picked_bases.append(keys[i])
                    break
    return picked


def prompt_reincarnation(account: LegacyAccount, user_id: str = USER_ID):
    """交互式转世降生（可选道统加成）。返回新角色。"""
    from core.wallet import wallet_summary as _ws

    console.print(
        f"[bold gold1]账户钱包 {_ws(account)['balance']} 灵石（户名：{user_id}）[/bold gold1]"
    )
    console.print("[bold gold1]【真灵入轮回】请选择本世出身……[/bold gold1]")
    name = Prompt.ask("[bold green]请赐予本世道号[/bold green]", default="厉飞雨")

    boost_keys = []
    if account.points > 0:
        render_legacy_panel(account)
        console.print(f"[cyan]道统池：{account.points} 点 · 单次至多选 {LEGACY_MAX_BOOSTS_PER_LIFE} 项[/cyan]")
        raw = Prompt.ask(
            "[bold cyan]出身加成编号（空格分隔，回车跳过）[/bold cyan]",
            default="",
        )
        boost_keys = _parse_boost_keys(raw)

    # 前世留痕（转世继承）：boosts 前捕获，覆写旧角后不可恢复
    old_trace = account.traces[-1] if account.traces else None

    # 遗物留存：选了裸 heirloom（编号/键名）而未带物品参数时，列前世行囊让玩家选件；
    # 无候选则明示跳过该项（不静默吞掉）
    if "heirloom" in boost_keys:
        if old_trace is not None and old_trace.belongings:
            console.print("[bold cyan]【遗物留存】前世行囊尚存：[/bold cyan]")
            for i, item in enumerate(old_trace.belongings, 1):
                console.print(f"  {i}. {item}")
            pick = Prompt.ask(
                "[bold cyan]选一件随真灵转世（输入编号或物品名，回车取第 1 件）[/bold cyan]",
                default="1",
            ).strip()
            chosen = None
            if pick.isdigit():
                idx = int(pick) - 1
                if 0 <= idx < len(old_trace.belongings):
                    chosen = old_trace.belongings[idx]
            elif pick in old_trace.belongings:
                chosen = pick
            if chosen is None:
                chosen = old_trace.belongings[0]
                console.print(f"[yellow]未识别所选，默认取第 1 件遗物：【{chosen}】[/yellow]")
            boost_keys = [
                f"heirloom:{chosen}" if k == "heirloom" else k for k in boost_keys
            ]
        else:
            console.print("[yellow]【遗物留存】前世无遗物可承（行囊为空或无留痕），跳过此项。[/yellow]")
            boost_keys = [k for k in boost_keys if k != "heirloom"]

    player = WorldClock.create_new_character(user_id, name)
    boost_res = LegacyEngine.apply_birth_boosts(player, account, boost_keys, old_trace=old_trace)
    if boost_keys:
        render_birth_boost_result(boost_res)
    # 因果影子（转世继承）：按 bond_echo 与否选 retention/cap 施加，落盘前完成
    from config import BOND_ECHO_CAP, BOND_ECHO_RETENTION, SHADOW_CAP, SHADOW_RETENTION
    from core.inheritance import apply_karma_shadow

    if boost_res.get("bond_echo"):
        _retention, _cap = BOND_ECHO_RETENTION, BOND_ECHO_CAP
    else:
        _retention, _cap = SHADOW_RETENTION, SHADOW_CAP
    karma_shadow = apply_karma_shadow(account, player, retention=_retention, cap=_cap)
    if karma_shadow:
        shadow_lines = "、".join(f"{s['npc_name']} {s['value']:+d}" for s in karma_shadow)
        console.print(f"[bold magenta]【因果余绪】前世余绪及身：{shadow_lines}[/bold magenta]")
    LegacyRepository.save(account)
    CharacterRepository.save(player)
    ChronicleRepository.record(
        "REINCARNATE",
        player.name,
        f"真灵转世，凡人【{player.name}】重踏仙途！"
        + (f"道统点化：{'、'.join(boost_res.get('applied', []))}。" if boost_res.get("applied") else ""),
    )
    console.print(
        f"[bold green]降生成功！自然寿元 {player.lifespan.birth_base:.0f} 岁"
        f"（现余 {player.lifespan.get_remaining_years():.1f} 岁）· 灵根 {player.spiritual_root.display_name()}"
        f" · 道统池剩余 {account.points} 点。[/bold green]\n"
    )
    console.print(
        f"[cyan]新角随身 {player.spirit_stones} 灵石；账户钱包可用 /钱包 查看、"
        f"/钱包提取 <金额> 取用。[/cyan]"
    )
    return player


def settle_and_reincarnate(player, cause: str, user_id: str = USER_ID):
    """
    本世终结：道统结算 → 展示 → 交互转世。
    返回新角色；若玩家放弃或被冷却挡下则返回 None。
    """
    account = LegacyRepository.get_or_create(user_id)

    from core.wallet import sweep_death_funds, wallet_summary

    if not player.death_settled:
        player.death_cause = cause
        player.status = CharacterStatus.DEAD
        # 资金归集（§2.3 步骤 1–4，server _settle_if_needed 同款）：在钩子与道统结算之前
        sweep = sweep_death_funds(player, account)
        LegacyRepository.save(account)
        if sweep.get("errors"):
            ChronicleRepository.record(
                "WALLET_SWEEP_PARTIAL", player.name,
                f"【{player.name}】死亡资金归集部分完成（WALLET_SWEEP_PARTIAL）："
                + "；".join(f"{e.get('step')}:{e.get('error')}" for e in sweep["errors"])
                + f"；钱包余额 {account.wallet_stones}。",
            )
        # 灵宠随主而殁（F01，一世循环）
        PetEngine.on_owner_death(player)
        # 洞府灵田随旧世荒废（F06，一世循环）
        FarmEngine.on_owner_death(player)
        # 委托链随旧世而散（F07，一世循环）
        QuestEngine.on_owner_death(player)
        # 诺言随旧世而散（F14，一世循环）：其未结诺全部消散，不判违约；
        # 被消散摘要经返回值注入 settle_death 写留痕（诺在 settle 前已消散）
        dissolved_promises = []
        try:
            dissolved_promises = PromiseEngine.on_owner_death(player) or []
        except Exception:
            dissolved_promises = []
        # 因果链随旧世而散（karma-event-chains §7.1）：紧随诺言钩子之后、
        # settle_death 之前；返回值不注入 settle_death（不进留痕）。
        try:
            from core.karma_chains import KarmaChainEngine

            KarmaChainEngine.on_owner_death(player)
        except Exception:
            pass
        settle = LegacyEngine.settle_death(
            account, player, death_cause=cause,
            dissolved_promises=dissolved_promises,
        )
        LegacyRepository.save(account)
        CharacterRepository.save(player)
        ChronicleRepository.record(
            "LEGACY_SETTLE",
            player.name,
            f"修士【{player.name}】{cause}，盖棺定论，结转道统 {settle['points_gained']} 点；"
            f"资金归集 {sweep['total']} 灵石，钱包余额 {account.wallet_stones}。",
        )
        render_legacy_settlement(settle, sweep=sweep, wallet=wallet_summary(account))
    else:
        # 迁移补扫（§5.2）：旧规则已结算行，钱包无 death_sweep 流水时补归集（幂等）
        # 评审 M1b：与 server 守卫同语义——sweep 内部处理残差，本分支恒跑 sweep。
        # QA-D1：是否打印【资金补扫】按与 server 同口径的真实变化判定
        # （sweep_has_real_change），不再按毛额 total／退款列表打印，崩溃重放不报补扫。
        from core.wallet import sweep_has_real_change as _real_change
        from core.wallet import wallet_panel_text as _wpt

        sweep = sweep_death_funds(player, account)
        LegacyRepository.save(account)
        CharacterRepository.save(player)
        if sweep.get("errors"):
            ChronicleRepository.record(
                "WALLET_SWEEP_PARTIAL", player.name,
                f"【{player.name}】死亡资金补扫部分完成（WALLET_SWEEP_PARTIAL）："
                + "；".join(f"{e.get('step')}:{e.get('error')}" for e in sweep["errors"])
                + f"；钱包余额 {account.wallet_stones}。",
            )
        if _real_change(sweep):
            console.print(
                f"[bold gold1]【资金补扫】死亡归集 {sweep['total']} 灵石，"
                f"账户钱包余额 {account.wallet_stones} 灵石。[/bold gold1]"
            )
        # 评审 S5：已结算 else 分支同样打印钱包面板（无归集时也不缺钱包展示）。
        console.print(f"[bold gold1]{_wpt(account, user_id)}[/bold gold1]")
        console.print("[dim]本世业已结算，真灵尚在轮回边缘徘徊。[/dim]")

    ok, gate_msg = LegacyEngine.check_reincarnate_gate(account)
    if not ok:
        console.print(f"[bold yellow]【轮回受阻】{gate_msg}[/bold yellow]")
        console.print("[dim]可稍后再启程序转世，道统点已入账不会丢失。[/dim]")
        return None

    choice = Prompt.ask(
        "[bold gold1]是否立刻真灵转世，重入红尘？[/bold gold1]",
        choices=["y", "n"],
        default="y",
    )
    if choice.lower() != "y":
        console.print("[dim]真灵暂驻轮回，道统已录。下次启动时可再入世。[/dim]")
        return None

    return prompt_reincarnation(account, user_id)


def ensure_alive_player(user_id: str = USER_ID):
    """启动时：若角色已死/寿尽，走结算与转世流程。返回可用角色。"""
    player = CharacterRepository.get_by_user_id(user_id)
    need_new = (player is None) or player.lifespan.is_dead() or player.status == CharacterStatus.DEAD

    if not need_new:
        return player

    if player is not None and (player.lifespan.is_dead() or player.status == CharacterStatus.DEAD):
        cause = player.death_cause or ("寿尽坐化" if player.lifespan.is_dead() else "身死道消")
        console.print(f"[bold red]道友前世已{cause}，真灵归寂……[/bold red]")
        new_player = settle_and_reincarnate(player, cause, user_id)
        if new_player is None:
            # 玩家选择暂不转世：造一具空壳占位会在下次启动再问，这里直接退出
            console.print("[dim]轮回未启，天道静候。[/dim]")
            sys.exit(0)
        return new_player

    # 全新账号首世
    account = LegacyRepository.get_or_create(user_id)
    console.print("[bold green]检测到全新真灵，即将降生修仙界。[/bold green]")
    return prompt_reincarnation(account, user_id)


def run_mud():
    init_db()
    seed_world_npcs()
    print_banner()

    player = ensure_alive_player()

    render_character_sheet(player)
    print_help()

    while True:
        try:
            cmd = Prompt.ask("[bold cyan]天道敕令[/bold cyan]").strip()
            if not cmd:
                continue

            parts = cmd.split()
            action = parts[0].lower()

            if action in ["/退出", "exit", "quit"]:
                console.print("[dim]道友收敛真元，遁入洞府歇息……（闭关状态与寿元在世间持续流逝）[/dim]")
                break

            # ==================== 闭关状态锁死判定 ====================
            if player.status == CharacterStatus.MEDITATING:
                med_progress = WorldClock.get_meditation_progress(player)

                def _after_meditation_death(settle_res, cause_msg: str):
                    nonlocal player
                    if settle_res.get("is_fatal", False):
                        console.print(f"[bold red]☠ {cause_msg}[/bold red]")
                        player = settle_and_reincarnate(player, "洞府坐化")
                        if player is None:
                            return False
                        render_character_sheet(player)
                    return True

                if med_progress.get("is_expired", False):
                    console.print("[bold red]☠ 闭关途中寿元灯枯，洞府内响起天道丧钟……[/bold red]")
                    settle_res = WorldClock.settle_meditation(player, force_interrupt=False)
                    CharacterRepository.save(player)
                    render_meditation_summary(settle_res)
                    if not _after_meditation_death(settle_res, "闭关途中寿尽坐化！"):
                        break
                elif med_progress.get("is_completed", False):
                    console.print("[bold gold1]★ 预定闭关期满，洞府石门隆隆大开，道友大功告成出关！ ★[/bold gold1]")
                    settle_res = WorldClock.settle_meditation(player, force_interrupt=False)
                    CharacterRepository.save(player)
                    render_meditation_summary(settle_res)
                    if not _after_meditation_death(settle_res, "出关之际寿元灯枯！"):
                        break
                    # 出关后可能遇机缘/危机
                    ev = EventEngine.fire(player, context=f"自{player.location}出关")
                    if ev:
                        CharacterRepository.save(player)
                        render_world_event(ev)
                else:
                    if med_progress.get("lifespan_warning", False):
                        rem_y = med_progress.get("rem_years", 0.0)
                        console.print(
                            f"[bold red]⚠️【大限将至】闭关途中剩余寿元仅 {rem_y:.2f} 岁"
                            f"（阈值 {LIFESPAN_WARNING_YEARS:.0f}）。可输入 /出关 抉择："
                            f"突破续命、寻延寿宝，或安坐待大限。[/bold red]"
                        )
                    if med_progress.get("is_idle_sitting", False):
                        console.print(
                            f"[dim]（已过有效吐纳 {MEDITATION_MAX_HOURS:.0f} 小时窗口，其后枯坐无益）[/dim]"
                        )

                    if action in ["/出关", "exit_meditate", "finish"]:
                        console.print("[bold yellow]道友强行收功出定，提前破关而出……[/bold yellow]")
                        settle_res = WorldClock.settle_meditation(player, force_interrupt=True)
                        CharacterRepository.save(player)
                        render_meditation_summary(settle_res)
                        if not _after_meditation_death(settle_res, "破关之际寿元灯枯！"):
                            break
                        continue
                    elif action not in ["/道身", "status", "me", "/帮助", "help", "/退出", "exit", "quit", "/自创功法", "create_art", "/地图", "map", "/舆图", "/宗门", "sect", "/仙门", "/道统", "legacy", "/坊市", "market", "/告示", "bounty", "/灵宠", "pets", "pet", "/喂养", "feed", "/出战", "deploy", "/休息", "petrest", "/心法", "xinfa", "/行情", "/版图", "/atlas", "/飞升榜", "/ascend", "/洞府", "cave", "/天象", "/omen"]:
                        render_meditation_locked(
                            med_progress["remaining_seconds"],
                            med_progress["end_time"]
                        )
                        continue

            if action in ["/道身", "status", "me"]:
                render_character_sheet(player)

            elif action in ["/道统", "legacy", "/前世"]:
                account = LegacyRepository.get_or_create(USER_ID)
                render_legacy_panel(account)

            elif action in ["/墓碑"]:
                # 墓碑查询（转世继承）：与 server 同命令同文案（引擎同源）
                from core.inheritance import find_tombstone

                if len(parts) < 2:
                    console.print("[red]用法：/墓碑 <道号>[/red]")
                    continue
                tomb = find_tombstone(parts[1])
                if tomb is None:
                    console.print("江湖无此碑。")
                else:
                    console.print(tomb)

            elif action in ["/因果链", "/karma_chains"]:
                # 因果链面板（AI 天道事件链）：与 server 同命令同文案（引擎同源）；
                # 先惰性推进后呈现（照 /诺言 settle_due→panel_text 先例）
                from core.karma_chains import KarmaChainEngine

                try:
                    KarmaChainEngine.advance_for(player)
                except Exception:
                    pass
                console.print(KarmaChainEngine.panel_text(player))

            elif action in ["/定相", "/gender"]:
                # 定相（gallery-gameplay §3.3）：与 server 同命令同文案（引擎同源）
                from core import gallery as _gallery

                res = _gallery.set_gender(player, parts[1] if len(parts) > 1 else "")
                if not res.get("success"):
                    console.print(f"[red]{res.get('message', '定相失败')}[/red]")
                else:
                    CharacterRepository.save(player)
                    console.print(res["message"])

            elif action in ["/图鉴", "/gallery"]:
                # 图鉴面板（gallery-gameplay §8.5）：与 server 同源文本
                from core import gallery as _gallery

                try:
                    _gallery.unlock_from_character(player)
                except Exception:
                    pass
                console.print(_gallery.panel_text(player))

            elif action in ["/寻宝", "/clue"]:
                # 寻宝线索链（gallery-gameplay §5.3）：与 server 调同一引擎
                from core.treasure_clue import TreasureClueEngine

                arg = parts[1] if len(parts) > 1 else ""
                if not arg:
                    console.print(TreasureClueEngine.view_text(player))
                else:
                    res = (
                        TreasureClueEngine.abandon(player)
                        if arg == "弃"
                        else TreasureClueEngine.choose(player, arg)
                    )
                    if res.get("changed"):
                        CharacterRepository.save(player)
                    console.print(res.get("message", ""))

            elif action in ["/器灵", "/spirit"]:
                # 法宝器灵（gallery-gameplay §6）：与 server 同命令同文案（引擎同源）
                from core.artifact_spirit import ArtifactSpiritEngine, panel_text as _spirit_panel

                sub = parts[1] if len(parts) > 1 else ""
                if sub == "唤":
                    target_name = parts[2] if len(parts) > 2 else ""
                    if not target_name:
                        console.print("[red]用法：/器灵 唤 <器物名>（须已穿戴且天品以上）[/red]")
                    else:
                        res = ArtifactSpiritEngine.awaken(player, target_name)
                        if res.get("changed"):
                            CharacterRepository.save(player)
                        console.print(res.get("message", ""))
                else:
                    console.print(_spirit_panel(player))

            elif action in ["/温养", "/nourish"]:
                # 温养（gallery-gameplay §6.4）：与 server 调同一引擎
                from core.artifact_spirit import ArtifactSpiritEngine

                res = ArtifactSpiritEngine.nourish(player, parts[1] if len(parts) > 1 else "")
                if res.get("changed"):
                    CharacterRepository.save(player)
                console.print(res.get("message", ""))

            elif action in ["/灵语", "/spirit_say"]:
                # 灵语（gallery-gameplay §6.3）：CLI 端 AI 不可用时引擎自动走本地台词
                from core.artifact_spirit import ArtifactSpiritEngine

                words = command.strip().split(None, 1)[1] if len(command.strip().split(None, 1)) > 1 else ""
                res = ArtifactSpiritEngine.talk(player, words)
                if res.get("changed"):
                    CharacterRepository.save(player)
                console.print(res.get("message", ""))

            elif action in ["/钱包", "wallet"]:
                from core.wallet import wallet_panel_text

                account = LegacyRepository.get_or_create(USER_ID)
                console.print(f"[bold gold1]{wallet_panel_text(account, USER_ID)}[/bold gold1]")

            elif action in ["/钱包提取", "wallet_withdraw"]:
                from core.wallet import withdraw_to_character

                if player.status == CharacterStatus.DEAD or player.lifespan.is_dead():
                    console.print("[red]身死道消，钱包须转世重生后方可提取。[/red]")
                    continue
                if len(parts) < 2 or not parts[1].isdigit():
                    console.print("[red]用法：/钱包提取 <金额>（正整数，不超过钱包余额）[/red]")
                    continue
                account = LegacyRepository.get_or_create(USER_ID)
                res = withdraw_to_character(account, player, int(parts[1]))
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                LegacyRepository.save(account)
                CharacterRepository.save(player)
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/地图", "map", "/舆图"]:
                render_world_map(player.location)

            elif action in ["/宗门", "sect", "/仙门"]:
                render_sect_panel(player)

            elif action in ["/拜入", "join_sect", "join"]:
                if len(parts) < 2:
                    console.print("[red]请指明欲拜入的仙门名称！例如：/拜入 青云宗 或 /拜入 万剑仙门[/red]")
                    continue
                target_sect = parts[1]
                matched_sect = None
                for s_name in SECTS_CONFIG:
                    if target_sect in s_name:
                        matched_sect = s_name
                        break
                if not matched_sect:
                    console.print(f"[red]未知名仙门：{target_sect}，输入 /宗门 可查阅天下仙门榜。[/red]")
                    continue

                if player.sect == matched_sect:
                    console.print(f"[dim]道友本就身为【{matched_sect}】弟子，何须重复叩关！[/dim]")
                    continue

                if player.sect:
                    console.print(f"[red]道友已拜入【{player.sect}】，背负宗门因果！不可三心二意，需先叛门脱离方可改投它宗。[/red]")
                    continue

                s_cfg = SECTS_CONFIG[matched_sect]
                hq = s_cfg.get("headquarters")
                if player.location != hq:
                    console.print(f"[red]叩关受阻！【{matched_sect}】总坛山门位于【{hq}】，道友当前身在【{player.location}】。\n请先输入 [/red][bold green]/前往 {hq}[/bold green][red] 抵达山门后再行叩门考核！[/red]")
                    continue

                passed = True
                fail_reason = ""
                if matched_sect == "青云宗":
                    if player.karma.dao_heart < s_cfg.get("req_dao_heart", 60):
                        passed = False
                        fail_reason = f"道心蒙尘（当前道心 {player.karma.dao_heart}，青云宗要求道心 ≥ {s_cfg['req_dao_heart']}）"
                    elif player.karma.sin_value > s_cfg.get("max_sin", 30):
                        passed = False
                        fail_reason = f"业障缠身（当前业力 {player.karma.sin_value}，青云宗要求业力 < {s_cfg['max_sin']}）"
                    elif player.karma.is_blood_marked():
                        passed = False
                        fail_reason = "头顶血煞狼烟，乃天道通缉凶徒，被青云宗护山神将当场驱逐！"

                elif matched_sect == "万剑仙门":
                    has_elem = any(e.value in ["金", "雷"] for e in player.spiritual_root.elements)
                    if not has_elem and player.karma.dao_heart < s_cfg.get("req_dao_heart", 70):
                        passed = False
                        fail_reason = f"既非金/雷属性剑道灵根，道心亦未达 70（当前道心 {player.karma.dao_heart}），剑碑未生共鸣！"

                elif matched_sect == "九幽天魔宗":
                    if player.karma.sin_value < s_cfg.get("min_sin", 40):
                        passed = False
                        fail_reason = f"心慈手软，手无血债（当前业力 {player.karma.sin_value}，魔宗要求手沾同道之血，业力 ≥ {s_cfg['min_sin']}）！"

                if not passed:
                    console.print(f"[bold red]❌【山门拒止 · 入门考核失败】[/bold red]\n[yellow]执事堂长老审视道友命盘，冷然喝退：{fail_reason}[/yellow]")
                    continue

                player.sect = matched_sect
                player.sect_rank = "外门弟子"
                starter_arr = s_cfg.get("starter_array")
                gift_msg = ""
                if starter_arr and starter_arr not in player.arrays:
                    player.arrays.append(starter_arr)
                    gift_msg = f"\n🎁 宗门执事堂赐下本门真传阵盘：【{starter_arr}】（已收入储物袋）！"

                CharacterRepository.save(player)
                ChronicleRepository.record("JOIN_SECT", player.name, f"修士【{player.name}】叩开【{matched_sect}】山门，通过严格考核，正式拜为外门弟子！")
                console.print(f"[bold green]🎉【山门洞开 · 拜入宗门】\n恭喜道友通过重重考验，正式拜入【{matched_sect}】，位列外门弟子！{gift_msg}\n· 现可免费进入专属洞府【{s_cfg.get('cave_location')}】闭关修炼。\n· 现实每过 2 小时可输入 /领俸禄 支取月俸灵石！[/bold green]")

            elif action in ["/领俸禄", "/俸禄", "salary"]:
                res = WorldClock.claim_sect_salary(player)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/前往", "/洞天", "travel"]:
                if len(parts) < 2:
                    render_world_map(player.location)
                    continue

                dest = parts[1]
                matched = None
                for loc in WORLD_LOCATIONS:
                    if dest in loc:
                        matched = loc
                        break
                if not matched:
                    console.print(f"[red]未知名修仙福地：{dest}，输入 /地图 可查阅全界灵脉一览。[/red]")
                    continue
                if matched == player.location:
                    console.print(f"[dim]道友当前本就身处【{matched}】。[/dim]")
                    continue

                player.location = matched
                CharacterRepository.save(player)
                console.print(f"[bold green]御剑化虹！道友已遁行至【{matched}】！[/bold green]")
                # 诺言账（F14）：抵达诺核验——迁跃落点即事实
                try:
                    _pline = PromiseEngine.note_arrival(player, matched)
                    if _pline:
                        console.print(f"[bold gold1]{_pline}[/bold gold1]")
                except Exception:
                    pass
                render_character_sheet(player)
                # 行路途中可能触发机缘/危机
                ev = EventEngine.fire(player, context=f"御剑途经 {matched}")
                if ev:
                    CharacterRepository.save(player)
                    render_world_event(ev)
                    ChronicleRepository.record(
                        "EVENT", player.name,
                        f"【{ev['title']}】于{matched}：{ev['effects_summary']}"
                    )
                # 同场 NPC 可能主动搭话
                try:
                    opens = NpcProactiveEngine.maybe_engage(player, max_speakers=1)
                    for o in opens:
                        console.print(f"[bold magenta]{o.get('text','')}[/bold magenta]")
                        console.print(
                            f"[dim]{o.get('personality')} · 对你 {o.get('attitude_cn')}"
                            f" · 源 {o.get('source')}[/dim]"
                        )
                except Exception:
                    pass

            elif action in ["/闭关", "/打坐", "meditate"]:
                hours = 1.0
                stones = 0
                if len(parts) > 1:
                    try:
                        hours = float(parts[1])
                    except ValueError:
                        console.print("[red]闭关现实小时数输入有误！例如：/闭关 2 (闭关现实2小时) 或 /闭关 0.1 (闭关6分钟)[/red]")
                        continue
                if len(parts) > 2:
                    try:
                        stones = int(parts[2])
                    except ValueError:
                        pass

                loc_info = WORLD_LOCATIONS.get(player.location, {"density": 1.0, "is_safe": True, "rent_per_hour": 0})
                if not loc_info.get("is_safe", False) and not player.arrays:
                    console.print(f"[bold red]⚠️ 警告：当前身处凶险野外【{player.location}】，且储物袋中无可用阵盘！[/bold red]")
                    console.print("[yellow]野外裸露入定六识闭塞，一旦被路过修士或妖兽神识察觉，必遭灭顶伏击（扣3年寿元、被劫85%灵石、跌落境界）！[/yellow]")
                    conf = Prompt.ask("[bold red]是否仍要执意强行裸露闭关？[/bold red]", choices=["y", "n"], default="n")
                    if conf.lower() != "y":
                        console.print("[dim]道友权衡再三，按捺住了行功冲动。[/dim]")
                        continue

                start_res = WorldClock.start_meditation(player, hours, stones)
                if start_res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{start_res['message']}[/bold green]")
                else:
                    console.print(f"[bold red]{start_res['message']}[/bold red]")

            elif action in ["/出关", "exit_meditate"]:
                if player.status != CharacterStatus.MEDITATING:
                    console.print("[dim]道友并未处于闭关状态之中。[/dim]")
                else:
                    settle_res = WorldClock.settle_meditation(player, force_interrupt=True)
                    CharacterRepository.save(player)
                    render_meditation_summary(settle_res)
                    if settle_res.get("is_fatal", False):
                        console.print("[bold red]☠ 破关之际寿元灯枯！[/bold red]")
                        player = settle_and_reincarnate(player, "洞府坐化")
                        if player is None:
                            break
                        render_character_sheet(player)
                    else:
                        ev = EventEngine.fire(player, context="提前破关")
                        if ev:
                            CharacterRepository.save(player)
                            render_world_event(ev)

            elif action in ["/探查", "scan"]:
                console.print("[dim]神识如潮水般外放，扫视四方大地……[/dim]")
                all_chars = CharacterRepository.list_all_alive()
                results = CombatEngine.scan_surroundings(player, all_chars)
                render_scan_panel(results)

            elif action in ["/同场", "/here", "here"]:
                from cli.views import render_here_panel
                rows = list_here(player)
                render_here_panel(player, rows)

            elif action in ["/人物", "/profile", "/角色"]:
                target = None
                if len(parts) > 1:
                    target = find_by_name(parts[1])
                    if not target:
                        console.print(f"[red]查无此人：{parts[1]}[/red]")
                        continue
                    if target.location != player.location and target.id != player.id:
                        # 允许看远处名录人物，但标注
                        pass
                prof = build_profile(player, target)
                console.print(format_profile(player, prof))

            elif action in ["/名录", "/roster"]:
                from core.npc_roster import roster_by_sect, seed_roster
                seed_roster()  # 幂等补齐
                groups = roster_by_sect()
                total = sum(len(v) for v in groups.values())
                console.print("[bold gold1]═══ 九州修士名录 · 仙门编制 ═══[/bold gold1]")
                for sect, members in groups.items():
                    console.print(f"\n[bold cyan]【{sect}】[/bold cyan][dim]{len(members)}人[/dim]")
                    for m in members:
                        console.print(f"  · [dim]{m}[/dim]")
                console.print(f"\n[dim]共 {total} 名核心 NPC。用 /同场 看当前地点。[/dim]\n")

            elif action in ["/突破", "breakthrough"]:
                if not player.realm.is_full:
                    console.print(f"[red]修为尚未圆满（当前 {player.realm.current_exp}/{player.realm.max_exp}），强冲必死！[/red]")
                    continue

                demon_text = ""
                heart_mod = 0.0

                # 大境界渡劫：先过心魔回合（选项 + 其他）
                if player.realm.sub_tier == 3:
                    from cli.views import render_heart_demon_session, render_heart_demon_result
                    hd_session = HeartDemonEngine.start(player)
                    render_heart_demon_session(hd_session)
                    raw = Prompt.ask(
                        "[bold magenta]心魔问心：输入选项编号/标签，或直接写「其他」应对[/bold magenta]",
                        default=str(hd_session.options[0]["id"]) if hd_session.options else "yield",
                    )
                    free_text = None
                    choice_id = raw.strip()
                    # 若不是已知选项 id/label，则视为自由输入
                    known = set()
                    for opt in hd_session.options:
                        known.add(opt.get("id", ""))
                        known.add(opt.get("label", ""))
                    if choice_id not in known:
                        free_text = choice_id
                        choice_id = None
                    hd_res = HeartDemonEngine.resolve(player, hd_session, choice_id=choice_id, free_text=free_text)
                    CharacterRepository.save(player)
                    render_heart_demon_result(hd_res)
                    if hd_res.get("is_fatal"):
                        ChronicleRepository.record("DEATH", player.name, f"修士【{player.name}】渡劫问心时心魔道消！")
                        player = settle_and_reincarnate(player, "心魔道消")
                        if player is None:
                            break
                        render_character_sheet(player)
                        continue
                    demon_text = hd_res.get("narrative", "")
                    heart_mod = float(hd_res.get("tribulation_mod") or 0.0)

                res = BreakthroughEngine.attempt_breakthrough(
                    player, use_pill=False, heart_mod=heart_mod
                )
                CharacterRepository.save(player)
                render_tribulation_result(res, demon_text)

                if res["success"]:
                    ChronicleRepository.record("BREAKTHROUGH", player.name, f"修士【{player.name}】历经天劫，突破至【{res['new_realm']}】！增寿 {res['lifespan_gained']} 岁！")
                elif res.get("is_fatal", False):
                    ChronicleRepository.record("DEATH", player.name, f"修士【{player.name}】在九霄天劫中肉身灰飞湮灭，道消身死！")
                    console.print("[bold red]你已在天劫中陨落……[/bold red]")
                    player = settle_and_reincarnate(player, "渡劫陨落")
                    if player is None:
                        break
                    render_character_sheet(player)

            elif action in ["/告示", "bounty", "/悬赏榜"]:
                bounties = BountyEngine.list_board(BountyRepository.list_all())
                render_bounty_board(bounties, viewer_id=player.id)

            elif action in ["/挂赏", "place_bounty"]:
                if len(parts) < 3:
                    console.print(
                        "[red]用法：/挂赏 <道号> <赏金> [缘由]（句末加「匿」匿名）\n"
                        f"例：/挂赏 血刀老祖 200 杀师夺宝 匿[/red]"
                    )
                    continue
                target_name = parts[1]
                try:
                    reward = int(parts[2])
                except ValueError:
                    console.print("[red]赏金必须是整数灵石！[/red]")
                    continue

                anonymous = False
                reason_tokens = parts[3:]
                if reason_tokens and reason_tokens[-1] in ("匿", "匿名", "anon"):
                    anonymous = True
                    reason_tokens = reason_tokens[:-1]
                reason = " ".join(reason_tokens) if reason_tokens else "血海深仇"

                target = CharacterRepository.get_by_name(target_name)
                if not target:
                    console.print(f"[red]查无此人：{target_name}。悬赏须有明确苦主仇家。[/red]")
                    continue

                active = BountyEngine.count_active_for_target(BountyRepository.list_all(), target.id)
                if active >= BOUNTY_MAX_PER_TARGET:
                    console.print(
                        f"[yellow]【{target_name}】头上已悬 {active} 张血令，"
                        f"告示栏挤不下了（上限 {BOUNTY_MAX_PER_TARGET}）。[/yellow]"
                    )
                    continue

                res = BountyEngine.place_bounty(player, target, reward, reason, anonymous)
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue

                CharacterRepository.save(player)
                BountyRepository.save(res["bounty"])
                link = res.get("link")
                if link:
                    KarmaLinkRepository.save(link)
                ChronicleRepository.record(
                    "BOUNTY",
                    player.name,
                    f"【{res['bounty'].issuer_display()}】悬赏 {reward} 灵石取【{target.name}】性命！缘由：{reason}",
                )
                console.print(f"[bold gold1]{res['message']}[/bold gold1]")

            # /接令 消歧：纯数字编号走悬赏板（既有）；非数字道号落到下方 F15 除凶接令
            elif action in ["/接令", "claim_bounty"] and len(parts) >= 2 and parts[1].isdigit():
                idx = int(parts[1]) - 1
                board = BountyEngine.list_board(BountyRepository.list_all())
                if idx < 0 or idx >= len(board):
                    console.print("[red]告示编号不存在。[/red]")
                    continue
                bounty = board[idx]
                res = BountyEngine.claim_bounty(player, bounty)
                if not res["success"]:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")
                    continue
                BountyRepository.save(bounty)
                ChronicleRepository.record(
                    "BOUNTY_CLAIM",
                    player.name,
                    f"猎手【{player.name}】接令追杀【{bounty.target_name}】，赏金 {bounty.reward} 灵石！",
                )
                console.print(f"[bold green]{res['message']}[/bold green]")
                target = CharacterRepository.get_by_name(bounty.target_name)
                if target:
                    console.print(
                        f"[dim]行迹提示：目标常出没于【{target.location}】。"
                        f"可 /探查 后 /斗法 {target.name}。[/dim]"
                    )

            elif action in ["/因果", "karma", "/仇怨"]:
                links = KarmaLinkRepository.list_all()
                mine = BountyEngine.list_links_for(links, player.id)
                render_karma_links(mine, player.id, player.name)

            elif action in ["/坊市", "market", "/商会"]:
                open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
                render_market_panel(player, open_l)

            elif action in ["/行情"]:
                console.print(MarketEngine.trade_board(player.location))

            elif action in ["/版图", "/atlas"]:
                from core.atlas import AtlasEngine

                console.print(AtlasEngine.panel_text(player, parts[1] if len(parts) > 1 else None))

            elif action in ["/飞升榜", "/ascend"]:
                from core.ascension import AscensionEngine

                console.print(AscensionEngine.panel_text(player, parts[1] if len(parts) > 1 else None))

            elif action in ["/天象", "/omen"]:
                from core.season_theme import SeasonThemeEngine

                SeasonThemeEngine.ensure_announced()
                console.print(SeasonThemeEngine.panel_text())

            elif action in ["/购买", "buy"]:
                if len(parts) < 2:
                    console.print("[red]用法：/购买 <货名> [数量]，先 /坊市 看货单。[/red]")
                    continue
                qty = 1
                name_tokens = parts[1:]
                if name_tokens and name_tokens[-1].isdigit():
                    qty = int(name_tokens[-1])
                    name_tokens = name_tokens[:-1]
                item_name = "".join(name_tokens) if all(len(t) == 1 for t in name_tokens) else " ".join(name_tokens)
                # 模糊匹配目录
                matched = None
                for g in MarketEngine.catalog():
                    if item_name in g["name"] or g["name"] == item_name:
                        matched = g["name"]
                        break
                if not matched:
                    console.print(f"[red]商会无此货：{item_name}[/red]")
                    continue
                res = MarketEngine.buy_from_guild(player, matched, qty)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold red]{res['message']}[/bold red]")

            elif action in ["/出售", "sell"]:
                if len(parts) < 2:
                    console.print("[red]用法：/出售 <货名> [数量][/red]")
                    continue
                qty = 1
                name_tokens = parts[1:]
                if name_tokens and name_tokens[-1].isdigit():
                    qty = int(name_tokens[-1])
                    name_tokens = name_tokens[:-1]
                item_name = " ".join(name_tokens)
                res = MarketEngine.sell_to_guild(player, item_name, qty)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold red]{res['message']}[/bold red]")

            elif action in ["/寄存", "deposit"]:
                if len(parts) < 2 or not parts[1].isdigit():
                    console.print("[red]用法：/寄存 <灵石数量>[/red]")
                    continue
                res = MarketEngine.deposit_stones(player, int(parts[1]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold gold1]{res['message']}[/bold gold1]")
                else:
                    console.print(f"[bold red]{res['message']}[/bold red]")

            elif action in ["/支取", "withdraw"]:
                if len(parts) < 2 or not parts[1].isdigit():
                    console.print("[red]用法：/支取 <灵石数量>[/red]")
                    continue
                res = MarketEngine.withdraw_stones(player, int(parts[1]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold gold1]{res['message']}[/bold gold1]")
                else:
                    console.print(f"[bold red]{res['message']}[/bold red]")

            elif action in ["/寄售", "list_item"]:
                if len(parts) < 3:
                    console.print("[red]用法：/寄售 <货物名> <价格>[/red]")
                    continue
                try:
                    price = int(parts[-1])
                except ValueError:
                    console.print("[red]价格必须是整数灵石。[/red]")
                    continue
                item_name = " ".join(parts[1:-1])
                my_open = [
                    l for l in MarketListingRepository.list_all()
                    if l.seller_id == player.id and l.is_open()
                ]
                if len(my_open) >= MARKET_MAX_LISTINGS:
                    console.print(f"[yellow]寄售栏已满（上限 {MARKET_MAX_LISTINGS}），请先 /撤单。[/yellow]")
                    continue
                listing, res = MarketEngine.list_item(player, item_name, price)
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                MarketListingRepository.save(listing)
                # 著书立说（F11）：手稿上架 → 书目转 listed 并绑定单号
                if item_name == BOOK_ITEM:
                    BookEngine.on_listing_created(player, listing.id)
                CharacterRepository.save(player)
                ChronicleRepository.record(
                    "MARKET", player.name,
                    f"【{player.name}】寄售【{item_name}】标价 {price} 灵石。"
                )
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/买寄售", "buy_listing"]:
                if len(parts) < 2 or not parts[1].isdigit():
                    console.print("[red]用法：/买寄售 <编号>（先 /坊市 查看）[/red]")
                    continue
                open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(open_l):
                    console.print("[red]寄售编号不存在。[/red]")
                    continue
                listing = open_l[idx]
                # 著书立说（F11）：手稿一人至多持一本，买家已持有则不成交
                if listing.item_name == BOOK_ITEM and not BookEngine.buyer_can_hold(player):
                    console.print("[bold red]怀中已有一部手稿，先将它流通出去再买新的。[/bold red]")
                    continue
                res = MarketEngine.buy_listing(player, listing)
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                # 著书立说（F11）：手稿成交 → 书目过户买家
                if listing.item_name == BOOK_ITEM:
                    BookEngine.on_listing_sold(listing.id, player)
                # 付款给卖家（玩家或 NPC）
                seller = CharacterRepository.get_by_name(listing.seller_name)
                MarketEngine.complete_sale_payment(listing, seller)
                MarketListingRepository.save(listing)
                CharacterRepository.save(player)
                if seller:
                    CharacterRepository.save(seller)
                ChronicleRepository.record(
                    "MARKET_BUY", player.name,
                    f"【{player.name}】购得寄售【{listing.item_name}】，付 {listing.price} 灵石。"
                )
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/撤单", "cancel_listing"]:
                if len(parts) < 2 or not parts[1].isdigit():
                    console.print("[red]用法：/撤单 <编号>[/red]")
                    continue
                open_l = MarketEngine.open_listings(MarketListingRepository.list_all())
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(open_l):
                    console.print("[red]寄售编号不存在。[/red]")
                    continue
                listing = open_l[idx]
                res = MarketEngine.cancel_listing(player, listing)
                if not res["success"]:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")
                    continue
                MarketListingRepository.save(listing)
                # 著书立说（F11）：手稿撤单 → 书目回 held
                if listing.item_name == BOOK_ITEM:
                    BookEngine.on_listing_cancelled(listing.id)
                CharacterRepository.save(player)
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/典当", "pawn"]:
                from core.pawn import PawnEngine
                from storage.db import PawnTicketRepository

                if len(parts) < 2:
                    console.print(PawnEngine.panel_text(player))
                    continue
                item_name = " ".join(parts[1:])
                ticket, res = PawnEngine.pawn_item(player, item_name)
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                PawnTicketRepository.save(ticket)
                CharacterRepository.save(player)
                ChronicleRepository.record(
                    "PAWN", player.name,
                    f"【{player.name}】典当【{item_name}】得 {res['principal']} 灵石。"
                )
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/赎回", "redeem"]:
                from core.pawn import PawnEngine
                from storage.db import PawnTicketRepository

                if len(parts) < 2:
                    console.print("[red]用法：/赎回 <物品名>（先 /典当 查看当票）[/red]")
                    continue
                item_name = " ".join(parts[1:])
                ticket, res = PawnEngine.redeem_item(player, item_name)
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                PawnTicketRepository.save(ticket)
                CharacterRepository.save(player)
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/拍卖行", "/拍卖", "auction"]:
                from collections import Counter

                from core.trade import AuctionEngine, _snapshot_assets

                # 看板推进可能以新鲜副本给本人入账/退款（落槌收款、被超价退款）；
                # CLI 的 player 是长驻对象，只吸收 DB 增量回内存（不整表覆盖，
                # 防冲掉未落库改动），避免后续指令落库把结算款覆盖掉（F05 评审整改）
                _before = _snapshot_assets(player.id)
                res = AuctionEngine.board()
                _after = _snapshot_assets(player.id)
                if _before and _after:
                    player.spirit_stones += _after[0] - _before[0]
                    for _idx, _attr in ((1, "inventory"), (2, "arrays"), (3, "equipped")):
                        for _item, _n in (Counter(_after[_idx]) - Counter(_before[_idx])).items():
                            getattr(player, _attr).extend([_item] * _n)
                console.print(res["message"])

            elif action in ["/上拍", "auction_list"]:
                from core.trade import AuctionEngine

                if len(parts) < 3:
                    console.print("[red]用法：/上拍 <货名> <底价> [一口价][/red]")
                    continue
                try:
                    start_price = int(parts[-1])
                    buyout = None
                    if len(parts) >= 4:
                        buyout = int(parts[-1])
                        start_price = int(parts[-2])
                        item = "".join(parts[1:-2])
                    else:
                        item = "".join(parts[1:-1])
                except ValueError:
                    console.print("[red]价格须为整数。用法：/上拍 <货名> <底价> [一口价][/red]")
                    continue
                res = AuctionEngine.list_item(player, item, start_price, buyout)
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/拍", "/出价", "bid"]:
                from core.trade import AuctionEngine

                if len(parts) < 2:
                    console.print("[red]用法：/拍 <编号> <出价>，或 /出价 <金额>（单场直拍）[/red]")
                    continue
                if len(parts) == 2:
                    if action != "/出价":
                        console.print("[red]用法：/拍 <编号> <出价>[/red]")
                        continue
                    try:
                        amount = int(parts[1])
                    except ValueError:
                        console.print("[red]出价须为整数[/red]")
                        continue
                    open_now = AuctionEngine.open_lots()
                    if not open_now:
                        console.print("[bold red]当前无进行中的拍品。[/bold red]")
                        continue
                    if len(open_now) > 1:
                        ids = "、".join(f"#{l.id}【{l.item_name}】" for l in open_now)
                        console.print(f"[bold red]当前多件拍品在场：{ids}，请用 /拍 <编号> <出价>。[/bold red]")
                        continue
                    lot_id = open_now[0].id
                else:
                    lot_id = parts[1]
                    try:
                        amount = int(parts[2])
                    except ValueError:
                        console.print("[red]出价须为整数[/red]")
                        continue
                res = AuctionEngine.bid(player, lot_id, amount)
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/一口", "buyout"]:
                from core.trade import AuctionEngine

                if len(parts) < 2:
                    console.print("[red]用法：/一口 <编号>[/red]")
                    continue
                res = AuctionEngine.buyout(player, parts[1])
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/撤拍", "auction_cancel"]:
                from core.trade import AuctionEngine

                if len(parts) < 2:
                    console.print("[red]用法：/撤拍 <编号>[/red]")
                    continue
                res = AuctionEngine.cancel(player, parts[1])
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
                console.print(f"[bold green]{res['message']}[/bold green]")

            elif action in ["/服用", "use_pill", "eat"]:
                if len(parts) < 2:
                    console.print("[red]用法：/服用 <丹药名>[/red]")
                    continue
                item_name = " ".join(parts[1:])
                # 模糊匹配
                matched = None
                for name in player.inventory:
                    if item_name in name or name == item_name:
                        matched = name
                        break
                if not matched:
                    console.print(f"[red]囊中并无【{item_name}】。[/red]")
                    continue
                res = MarketEngine.use_pill(player, matched)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/灵宠", "pets", "pet"]:
                console.print(PetEngine.panel_text(player))

            elif action in ["/契约", "contract"]:
                if len(parts) < 2:
                    console.print("[red]用法：/契约 <兽名>[/red]")
                    continue
                res = PetEngine.contract(player, " ".join(parts[1:]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/喂养", "feed"]:
                if len(parts) < 2:
                    console.print("[red]用法：/喂养 <宠名> [丹药名][/red]")
                    continue
                from core.pets import split_feed_args

                pet_hint, pill = split_feed_args(player, parts[1:])
                res = PetEngine.feed(player, pet_hint, pill)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/出战", "deploy"]:
                if len(parts) < 2:
                    console.print("[red]用法：/出战 <宠名>[/red]")
                    continue
                res = PetEngine.deploy(player, " ".join(parts[1:]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/休息", "petrest"]:
                if len(parts) < 2:
                    console.print("[red]用法：/休息 <宠名>[/red]")
                    continue
                res = PetEngine.rest(player, " ".join(parts[1:]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/放生", "release"]:
                if len(parts) < 2:
                    console.print("[red]用法：/放生 <宠名>[/red]")
                    continue
                res = PetEngine.release(player, " ".join(parts[1:]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/洞府", "cave"]:
                console.print(FarmEngine.panel_text(player))

            elif action in ["/开辟", "opencave"]:
                res = FarmEngine.open_cave(player)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/播种", "sow"]:
                if len(parts) < 2:
                    console.print("[red]用法：/播种 <种子名> [数量][/red]")
                    continue
                seed_hint, sow_count = split_sow_args(parts[1:])
                res = FarmEngine.sow(player, seed_hint, sow_count)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/收获", "harvest"]:
                res = FarmEngine.harvest(player)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/升级洞府", "upgradecave"]:
                res = FarmEngine.upgrade_cave(player)
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/委托", "quests"]:
                if QuestEngine.settle_expired(player):
                    CharacterRepository.save(player)
                console.print(QuestEngine.panel_text(player))

            elif action in ["/接委托", "acceptquest"]:
                if len(parts) < 2:
                    console.print("[red]用法：/接委托 <NPC名或编号>（先 /委托 查看）[/red]")
                    continue
                res = QuestEngine.accept(player, " ".join(parts[1:]))
                if res["success"] or res.get("dirty"):
                    CharacterRepository.save(player)
                if res["success"]:
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/交付", "deliver"]:
                res = QuestEngine.deliver(player)
                if res["success"] or res.get("dirty"):
                    CharacterRepository.save(player)
                if res["success"]:
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/弃委托", "abandonquest"]:
                res = QuestEngine.abandon(player)
                if res["success"] or res.get("dirty"):
                    CharacterRepository.save(player)
                if res["success"]:
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/诺言", "promises"]:
                if PromiseEngine.settle_due(player, actor_obj=player):
                    CharacterRepository.save(player)
                console.print(PromiseEngine.panel_text(player))

            elif action in ["/许诺", "promise"]:
                if len(parts) < 3:
                    console.print("[red]用法：/许诺 <对象名> 赠物 <物品名> | 抵达 <地点名> | 委托 | 不攻（唯指令立诺入账，交谈口头应承不算）[/red]")
                    continue
                target = CharacterRepository.get_by_name(parts[1])
                if not target:
                    console.print(f"[red]查无此人：{parts[1]}[/red]")
                    continue
                kind = PROMISE_KIND_ALIASES.get(parts[2]) or PROMISE_KIND_ALIASES.get(parts[2].lower())
                if not kind:
                    console.print("[red]诺目须是规则四类之一：赠物 / 抵达 / 委托 / 不攻（自由口诺天道不记）[/red]")
                    continue
                res = PromiseEngine.make_promise(player, target, kind, parts[3] if len(parts) > 3 else "")
                if res["success"] or res.get("dirty"):
                    CharacterRepository.save(player)
                if res["success"]:
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/应诺", "acceptpromise"]:
                res = PromiseEngine.accept(player, parts[1] if len(parts) > 1 else "")
                if res["success"] or res.get("dirty"):
                    CharacterRepository.save(player)
                if res["success"]:
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/毁诺", "breakpromise"]:
                res = PromiseEngine.break_promise(player, parts[1] if len(parts) > 1 else "")
                if res["success"] or res.get("dirty"):
                    CharacterRepository.save(player)
                if res["success"]:
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            # 除凶令（F15）：与 server 同引擎；闭关白名单不含此组指令，天然锁门（对齐 F07）
            elif action in ["/除凶", "/hunt", "hunt"]:
                from core import hunt as _hunt

                t = _hunt.my_target(player)
                extra = f"\n你接的令：【{t.name}】@ {t.location}" if t else "\n你未接令。"
                console.print(_hunt.format_board() + extra)

            elif action in ["/接令", "/接除凶", "acceptorder"]:
                from core import hunt as _hunt

                if len(parts) < 2:
                    console.print("[red]用法：/接令 <凶犯道号>（纯数字编号为悬赏板接令）[/red]")
                    continue
                res = _hunt.accept(player, "".join(parts[1:]))
                if res.get("success"):
                    try:
                        from core.sect_contrib import sync_ring

                        sync_ring(player, "hunt")
                        CharacterRepository.save(player)
                    except Exception:
                        pass
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/追凶", "/track", "track"]:
                from core import hunt as _hunt

                res = _hunt.track(player)
                if res.get("success"):
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/弃令", "/弃除凶", "abandonorder"]:
                from core import hunt as _hunt

                res = _hunt.abandon(player)
                if res.get("success"):
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/议政", "/council", "council"]:
                console.print(CouncilEngine.panel_text(player))

            elif action in ["/投票", "/vote", "vote"]:
                if len(parts) < 2:
                    console.print("[red]用法：/投票 支持|反对[/red]")
                    continue
                res = CouncilEngine.vote(player, parts[1])
                if res["success"] or res.get("dirty"):
                    CharacterRepository.save(player)
                if res["success"]:
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/游说", "/lobby", "lobby"]:
                if len(parts) < 2:
                    console.print("[red]用法：/游说 <长老名>[/red]")
                    continue
                res = CouncilEngine.lobby(player, "".join(parts[1:]))
                if res["success"] or res.get("dirty"):
                    CharacterRepository.save(player)
                if res["success"]:
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/心法", "xinfa"]:
                console.print(ArtSlotEngine.panel_text(player))

            elif action in ["/主修", "main_art"]:
                if len(parts) < 2:
                    console.print("[red]用法：/主修 <功法名>[/red]")
                    continue
                res = ArtSlotEngine.set_main(player, " ".join(parts[1:]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/辅修", "sub_art"]:
                if len(parts) < 2:
                    console.print("[red]用法：/辅修 <功法名>[/red]")
                    continue
                res = ArtSlotEngine.add_sub(player, " ".join(parts[1:]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/卸功", "remove_art"]:
                if len(parts) < 2:
                    console.print("[red]用法：/卸功 <功法名>[/red]")
                    continue
                res = ArtSlotEngine.remove(player, " ".join(parts[1:]))
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/炼体", "body", "/炼神", "soul"]:
                # 炼体/炼神双修（F10）：无参=面板；「修炼 [n]」=逐层精进（闭关白名单不含此指令，天然锁门）
                track = "body" if action in ["/炼体", "body"] else "soul"
                sub = parts[1] if len(parts) > 1 else ""
                if sub in ("修炼", "train"):
                    times = 1
                    if len(parts) > 2:
                        try:
                            times = int(parts[2])
                        except Exception:
                            times = 1
                    res = (BodySoulEngine.train_body(player, times) if track == "body"
                           else BodySoulEngine.train_soul(player, times))
                    if res["success"]:
                        CharacterRepository.save(player)
                        console.print(f"[bold green]{res['message']}[/bold green]")
                    else:
                        console.print(f"[bold yellow]{res['message']}[/bold yellow]")
                elif sub:
                    console.print(f"[red]用法：/{'炼体' if track == 'body' else '炼神'} 或 /{'炼体' if track == 'body' else '炼神'} 修炼 [次数][/red]")
                else:
                    console.print(BodySoulEngine.panel_text(player, track))

            elif action in ["/镇魔", "demon", "/demon"]:
                # 心魔长期状态（F16）：无参=面板（打开即惰性结算魔念）；服丹/静坐=镇压（与 server 同引擎同口径）
                sub = parts[1] if len(parts) > 1 else ""
                if sub in ("服丹", "pill"):
                    res = DemonStateEngine.suppress_pill(player)
                    if res["success"]:
                        CharacterRepository.save(player)
                        console.print(f"[bold green]{res['message']}[/bold green]")
                    else:
                        console.print(f"[bold yellow]{res['message']}[/bold yellow]")
                elif sub in ("静坐", "calm"):
                    res = DemonStateEngine.suppress_calm(player)
                    if res["success"]:
                        CharacterRepository.save(player)
                        console.print(f"[bold green]{res['message']}[/bold green]")
                    else:
                        console.print(f"[bold yellow]{res['message']}[/bold yellow]")
                elif sub:
                    console.print("[red]用法：/镇魔 或 /镇魔 服丹 或 /镇魔 静坐[/red]")
                else:
                    console.print(DemonStateEngine.panel_text(player))
                    CharacterRepository.save(player)

            elif action in ["/著书", "write_book", "/write_book"]:
                # 著书立说（F11）：无参=面板；「写」=燃寿著书（与 server 同引擎同口径）
                sub = parts[1] if len(parts) > 1 else ""
                if sub in ("写", "write"):
                    res = BookEngine.write_book(player)
                    if res["success"]:
                        CharacterRepository.save(player)
                        console.print(f"[bold green]{res['message']}[/bold green]")
                    else:
                        console.print(f"[bold yellow]{res['message']}[/bold yellow]")
                elif sub:
                    console.print("[red]用法：/著书 或 /著书 写[/red]")
                else:
                    console.print(BookEngine.panel_text(player))

            elif action in ["/研读", "read_book", "/read_book"]:
                # 研读（F11）：展卷所持手稿；首次研读结算收益与作者声望（引擎内幂等）
                hint = cmd.strip().split(None, 1)[1] if len(cmd.strip().split(None, 1)) > 1 else ""
                res = BookEngine.read_book(player, hint.strip())
                if res["success"]:
                    CharacterRepository.save(player)
                    console.print(f"[bold green]{res['message']}[/bold green]")
                else:
                    console.print(f"[bold yellow]{res['message']}[/bold yellow]")

            elif action in ["/机缘", "event", "/事件", "/推演"]:
                etype = None
                if len(parts) > 1:
                    m = {"机缘": "fortune", "危机": "crisis", "异象": "omen",
                         "fortune": "fortune", "crisis": "crisis", "omen": "omen"}
                    etype = m.get(parts[1])
                ev = EventEngine.fire(player, etype=etype, context="主动推演天机", force=True)
                if ev:
                    CharacterRepository.save(player)
                    render_world_event(ev)
                    ChronicleRepository.record(
                        "EVENT", player.name,
                        f"【{ev['title']}】{ev['narrative'][:40]}…（{ev['effects_summary']}）"
                    )
                else:
                    console.print("[dim]神识推演一片混沌，暂无天机。[/dim]")

            elif action in ["/做", "do", "/言行"]:
                if len(parts) < 2:
                    console.print("[red]用法：/做 <你的言行>\n例：/做 我在坊市打听血刀老祖的行踪[/red]")
                    continue
                raw = " ".join(parts[1:])
                console.print("[dim]天道垂听……[/dim]")
                res = FreeActionEngine.resolve(player, raw)
                if not res.get("ok"):
                    console.print(f"[bold red]{res.get('error', '言行无果')}[/bold red]")
                    continue
                CharacterRepository.save(player)
                spawned = res.get("spawned")
                if spawned:
                    CharacterRepository.save(spawned)
                from cli.views import render_free_action
                render_free_action(res)
                ChronicleRepository.record(
                    "FREE", player.name,
                    f"【{player.name}】{res.get('intent')}: {raw[:30]} → {res.get('effects_summary','')}"
                )
                if spawned:
                    console.print(
                        f"[bold red]⚠ 暗处有人现身：【{spawned.name}】@{spawned.location}[/bold red]"
                    )

            elif action in ["/回访", "revenge"]:
                # 注意：/因果 在 CLI 专指因果链查看；回访请用 /回访
                rv = RevengeEngine.force_callback(player)
                if not rv:
                    console.print("[dim]账上暂无可供回访的血仇旧怨。[/dim]")
                    continue
                CharacterRepository.save(player)
                if rv.get("spawned"):
                    CharacterRepository.save(rv["spawned"])
                console.print(f"[bold magenta]{rv.get('text','')}[/bold magenta]")
                if rv.get("spawned"):
                    console.print(
                        f"[bold red]⚠【{rv['spawned'].name}】已现世于【{rv['spawned'].location}】[/bold red]"
                    )

            elif action in ["/天道", "/heaven", "/导演"]:
                try:
                    from core.world_director import handle_heaven_command

                    parts = action.split() + (line.split()[1:] if len(line.split()) > 1 else [])
                    # 保持与 LAN 一致：parts[0]=指令
                    raw_parts = line.strip().split()
                    res = handle_heaven_command(raw_parts[0], raw_parts)
                    console.print(res.get("text", ""))
                    if not res.get("ok") and res.get("director", {}).get("source") == "error":
                        console.print(f"[yellow]{res.get('message') or res.get('text')}[/yellow]")
                except Exception as e:
                    console.print(f"[red]天道导演不可用：{e}[/red]")

            elif action in ["/世情", "/npc", "npctick"]:
                # 离线追赶：玩家不在时世界仍在动
                try:
                    from core.world_director import WorldDirector
                    from core.jianghu_sim import JianghuSimulator, format_offline_report

                    off = JianghuSimulator.simulate_offline()
                    if off.get("waves"):
                        console.print("[bold gold1]═══ 离线江湖 ═══[/bold gold1]")
                        console.print(format_offline_report(off))
                    drows = WorldDirector.schedule_lines(limit=3)
                    if drows:
                        console.print("[bold magenta]═══ 天道导演 ═══[/bold magenta]")
                        for row in drows:
                            console.print(row)
                except Exception as e:
                    console.print(f"[dim]离线结算跳过：{e}[/dim]")
                acted = NpcAgendaEngine.tick_world(max_npcs=4, force=True)
                if not acted:
                    console.print("[dim]本轮 NPC 皆在静观。[/dim]")
                else:
                    console.print("[bold gold1]═══ 世间他人动向 ═══[/bold gold1]")
                    for r in acted:
                        console.print(f"· [dim]{r.get('text','')}[/dim]")
                    # 落公账
                    ChronicleRepository.record(
                        "NPC", "天道",
                        "；".join(f"{r.get('npc')}:{(r.get('narrative') or '')[:20]}" for r in acted[:3])
                    )
                try:
                    import core.jianghu as jianghu
                    console.print("[bold gold1]═══ 江湖因果账 ═══[/bold gold1]")
                    console.print(jianghu.format_brief(8))
                except Exception:
                    pass

            elif action in ["/近况", "/briefing", "/wangshi"]:
                try:
                    from core.jianghu_sim import JianghuSimulator, format_offline_report

                    off = JianghuSimulator.simulate_offline()
                    if off.get("events"):
                        console.print(format_offline_report(off))
                except Exception:
                    pass
                from core.briefing import format_cli
                from core.goals import evaluate_and_complete
                try:
                    done = evaluate_and_complete(player)
                    if done:
                        CharacterRepository.save(player)
                        for g in done:
                            console.print(f"[green]【目标达成】{g.get('title')}（{g.get('done_reason','')}）[/green]")
                except Exception:
                    pass
                console.print(format_cli(player))

            elif action in ["/目标", "/goals"]:
                from core.goals import format_goals
                console.print("[bold cyan]═══ 世间目标 ═══[/bold cyan]")
                console.print(format_goals(player))

            elif action in ["/议程", "/agenda"]:
                rows = NpcAgendaEngine.list_agendas()
                if not rows:
                    console.print("[dim]暂无 NPC 议程档案（可先 /世情 触发建档）。[/dim]")
                else:
                    console.print("[bold cyan]═══ NPC 议程榜 ═══[/bold cyan]")
                    for a in rows[:20]:
                        sec = f" | 副:{a.get('secondary_cn')}" if a.get("secondary_cn") else ""
                        console.print(
                            f"· [yellow]{a['npc_name']}[/yellow]："
                            f"[bold]{a.get('agenda_cn', a['agenda_type'])}[/bold] — "
                            f"{a.get('note','')[:28]} "
                            f"[dim](进度 {a.get('progress',0)}/5{sec})[/dim]"
                        )
                    console.print("[dim]主议程权重约 60%，副议程随 tick 抽选；进度满 5 换新目标。[/dim]")

            elif action in ["/交谈", "/talk", "say"]:
                if len(parts) < 2:
                    console.print("[red]用法：/交谈 <道号> [想说的话][/red]")
                    continue
                target = CharacterRepository.get_by_name(parts[1])
                if not target:
                    console.print(f"[red]此地查无【{parts[1]}】。[/red]")
                    continue
                if target.id == player.id:
                    console.print("[red]自言自语？[/red]")
                    continue
                words = " ".join(parts[2:]) if len(parts) > 2 else ""
                res = NpcDialogueEngine.talk(target, player, words)
                if not res.get("ok"):
                    console.print(f"[yellow]{res.get('error')}[/yellow]")
                    continue
                console.print(f"[bold magenta]{res.get('text','')}[/bold magenta]")
                console.print(
                    f"[dim]性格：{res.get('personality')} · 态度：{res.get('attitude_cn')}"
                    f"（{res.get('attitude_delta'):+d}）· 源：{res.get('source')}[/dim]"
                )

            elif action in ["/斗法", "attack"]:
                if len(parts) < 2:
                    console.print("[red]请指明欲伏击斗法的道友名号！例如：/斗法 陆仁贾[/red]")
                    continue
                target_name = parts[1]
                target = CharacterRepository.get_by_name(target_name)
                if not target:
                    console.print(f"[red]方圆百里并未探查到名为【{target_name}】的修士踪迹！[/red]")
                    continue
                if target.id == player.id:
                    console.print("[red]自残元神，恐生心魔！[/red]")
                    continue

                res = CombatFateEngine.resolve_ambush(player, target, use_ai=True, context="野外伏击")
                if not res.get("success"):
                    console.print(f"[bold red]{res.get('message','动手失败')}[/bold red]")
                    continue
                CharacterRepository.save(player)
                CharacterRepository.save(target)
                spawned = res.get("spawned")
                if spawned:
                    CharacterRepository.save(spawned)
                render_combat_result({
                    "report": res.get("report") or res.get("narrative", ""),
                    "outcome": res.get("outcome"),
                    "source": res.get("source"),
                })
                console.print(f"[dim]天命来源：{res.get('source')} · 结局 {res.get('outcome')}[/dim]")

                if res.get("target_died", False):
                    ChronicleRepository.record("KILL", player.name, f"修士【{player.name}】于伏击中斩杀【{target.name}】！")
                    open_bs = BountyRepository.list_open_for_target(target.id)
                    if open_bs:
                        pay = BountyEngine.settle_on_kill(player, target, open_bs)
                        BountyRepository.save_many(open_bs)
                        CharacterRepository.save(player)
                        if pay.get("message"):
                            console.print(f"[bold gold1]{pay['message']}[/bold gold1]")
                    all_links = KarmaLinkRepository.list_all()
                    feud = BountyEngine.ensure_feud_link(
                        all_links, player, target, note=f"伏击杀戮于 {player.location}"
                    )
                    if feud:
                        KarmaLinkRepository.save(feud)

                if spawned:
                    ChronicleRepository.record(
                        "SPAWN", spawned.name,
                        f"【{spawned.name}】现身【{spawned.location}】——{spawned.realm.name}，来意不善！"
                    )
                    console.print(
                        f"[bold red]⚠ 新角色入世：【{spawned.name}】在【{spawned.location}】"
                        f"（{spawned.realm.name}）[/bold red]"
                    )

            elif action in ["/自创功法", "create_art"]:
                concept = parts[1] if len(parts) > 1 else "吞噬他人精血壮大肉身"
                console.print(f"[dim]识海沉浮，神识推演【{concept}】之天地玄机……[/dim]")
                art = AIGateway.generate_custom_art(concept, player.name)
                render_custom_art(art)
                player.skills.append(art["name"])
                CharacterRepository.save(player)

            elif action in ["/大事记", "history"]:
                events = ChronicleRepository.get_recent(5)
                console.print("[bold gold1]═══ 九州天道大事纪 ═══[/bold gold1]")
                for e in events:
                    console.print(f"· [dim]{e}[/dim]")

            elif action in ["/帮助", "help"]:
                print_help()

            elif action in LAN_ONLY_COMMANDS_LOWER:
                console.print(
                    f"[yellow]【局域网专有】{action} 仅在局域网服可用，请连 LAN 服使用。[/yellow]"
                )

            else:
                console.print(f"[red]未知名敕令: {action}，输入 /帮助 查阅天道指引。[/red]")

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]元神归位，退出天道因果录。[/dim]")
            break


if __name__ == "__main__":
    run_mud()
