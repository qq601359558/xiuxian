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


def print_help():
    help_text = """
[bold cyan]【天道敕令 · 常用指令】[/bold cyan]
  [bold yellow]/道身[/bold yellow]                 - 观照自身命盘、境界、剩余寿元与宗门归属
  [bold yellow]/道统[/bold yellow]                 - 查阅道统点、前世典籍与转世出身兑换目录
  [bold yellow]/地图[/bold yellow]                 - 查阅九州山海全景舆图、地脉灵气浓度与安全禁制
  [bold yellow]/宗门[/bold yellow]                 - 查阅天下仙门宗派榜、门规约束、月俸待遇与个人宗籍
  [bold yellow]/拜入 <宗门>[/bold yellow]          - 前往总坛山门参加入门考核（如：/拜入 青云宗）
  [bold yellow]/领俸禄[/bold yellow]               - 宗门弟子每过现实2小时（游戏内1个月）可领月度灵石俸禄
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
  [bold yellow]/因果[/bold yellow]                 - 查看个人仇怨恩义因果链（回访请用 /回访）
  [bold yellow]/回访[/bold yellow]                 - 依事件账触发因果回访（寻仇/旧怨）
  [bold yellow]/坊市[/bold yellow]                 - 商会货单、金库寄存、玩家寄售
  [bold yellow]/购买 <名目> [数量][/bold yellow]     - 向商会购货（如：/购买 一阶青木迷踪阵）
  [bold yellow]/出售 <名目> [数量][/bold yellow]     - 回售给商会（约五折）
  [bold yellow]/寄存 <数量>[/bold yellow]           - 灵石存入坊市金库（不可被夺）
  [bold yellow]/支取 <数量>[/bold yellow]           - 自金库取出灵石
  [bold yellow]/寄售 <货物> <价格>[/bold yellow]     - 将随身货物挂上寄售栏
  [bold yellow]/买寄售 <编号>[/bold yellow]         - 买下他人寄售货物
  [bold yellow]/撤单 <编号>[/bold yellow]           - 撤回自己的寄售
  [bold yellow]/服用 <丹药>[/bold yellow]           - 服用囊中丹药
  [bold yellow]/机缘 [机缘|危机|异象][/bold yellow]  - 主动推演一则世间事件（外出/出关后亦可能自动触发）
  [bold yellow]/做 <言行>[/bold yellow]             - 自由输入，由天命裁决后果（例：/做 我跪在坊市磕头求丹）
  [bold yellow]/世情[/bold yellow]                 - 离线江湖追赶 + NPC tick + 因果账
  [bold yellow]/天道[/bold yellow]                 - 天道导演态势；/天道 推演 强制一轮
  [bold yellow]/近况[/bold yellow]                 - 世间近况 + 与你何干 + 世间目标
  [bold yellow]/目标[/bold yellow]                 - 查看/刷新世间目标
  [bold yellow]/议程[/bold yellow]                 - 查看 NPC 当前议程一览
  [bold yellow]/自创功法 <理念>[/bold yellow]       - 消耗神识让天道为你自创独门法门（如：/自创功法 噬血炼骨）
  [bold yellow]/大事记[/bold yellow]               - 翻阅天道总账，查看近期全界因果杀戮
  [dim]局域网专有：/说 /释放 /拜师 /结拜 /交易 /拍卖 /除凶 /宗门环 /探险 /秘境 /AI自检 等，请连 LAN 服使用[/dim]
  [bold yellow]/帮助[/bold yellow]                 - 查看本指令菜单
  [bold yellow]/退出[/bold yellow]                 - 暂离修仙界（若正在闭关，离线期间现实时间照常计时）
"""
    console.print(help_text)


def _parse_boost_keys(raw: str):
    """把 '1 2' / 'stones lifespan' 解析为 boost key 列表"""
    if not raw or not raw.strip():
        return []
    boosts = LegacyEngine.list_boosts()
    keys = [b["key"] for b in boosts]
    names = [b["name"] for b in boosts]
    picked = []
    for token in raw.replace(",", " ").split():
        t = token.strip()
        if t.isdigit():
            idx = int(t) - 1
            if 0 <= idx < len(keys) and keys[idx] not in picked:
                picked.append(keys[idx])
        elif t in keys and t not in picked:
            picked.append(t)
        else:
            for i, name in enumerate(names):
                if t in name and keys[i] not in picked:
                    picked.append(keys[i])
                    break
    return picked


def prompt_reincarnation(account: LegacyAccount, user_id: str = USER_ID):
    """交互式转世降生（可选道统加成）。返回新角色。"""
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

    player = WorldClock.create_new_character(user_id, name)
    boost_res = LegacyEngine.apply_birth_boosts(player, account, boost_keys)
    if boost_keys:
        render_birth_boost_result(boost_res)
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
    return player


def settle_and_reincarnate(player, cause: str, user_id: str = USER_ID):
    """
    本世终结：道统结算 → 展示 → 交互转世。
    返回新角色；若玩家放弃或被冷却挡下则返回 None。
    """
    account = LegacyRepository.get_or_create(user_id)

    if not player.death_settled:
        player.death_cause = cause
        player.status = CharacterStatus.DEAD
        settle = LegacyEngine.settle_death(account, player, death_cause=cause)
        LegacyRepository.save(account)
        CharacterRepository.save(player)
        ChronicleRepository.record(
            "LEGACY_SETTLE",
            player.name,
            f"修士【{player.name}】{cause}，盖棺定论，结转道统 {settle['points_gained']} 点。",
        )
        render_legacy_settlement(settle)
    else:
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
                    elif action not in ["/道身", "status", "me", "/帮助", "help", "/退出", "exit", "quit", "/自创功法", "create_art", "/地图", "map", "/舆图", "/宗门", "sect", "/仙门", "/道统", "legacy", "/坊市", "market", "/告示", "bounty"]:
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

            elif action in ["/接令", "claim_bounty"]:
                if len(parts) < 2 or not parts[1].isdigit():
                    console.print("[red]用法：/接令 <告示编号>（先输入 /告示 查看）[/red]")
                    continue
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
                res = MarketEngine.buy_listing(player, listing)
                if not res["success"]:
                    console.print(f"[bold red]{res['message']}[/bold red]")
                    continue
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
                CharacterRepository.save(player)
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

            else:
                console.print(f"[red]未知名敕令: {action}，输入 /帮助 查阅天道指引。[/red]")

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]元神归位，退出天道因果录。[/dim]")
            break


if __name__ == "__main__":
    run_mud()
