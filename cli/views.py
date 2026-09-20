"""
文字 MUD 终端视图渲染器 (基于 Rich 库打造古典沉浸式排版)
"""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from core.models import Character, CharacterStatus
from core.clock import WorldClock

console = Console()


def render_character_sheet(char: Character):
    """渲染【九州道鉴 · 命身】精美面板"""
    rem_years = char.lifespan.get_remaining_years()
    years_int = int(rem_years)
    days_int = int((rem_years % 1.0) * 365)

    # 寿元颜色：>30 岁青色，10~30 岁黄色，<10 岁赤红并警告
    if char.status == CharacterStatus.DEAD or rem_years <= 0:
        lifespan_color = "bold red"
        lifespan_str = "[已寿尽坐化 · 真灵消散]"
    elif rem_years < 10.0:
        lifespan_color = "bold red"
        lifespan_str = f"{years_int}岁 {days_int}天 (⚠️ 大限将至·五衰临头)"
    elif rem_years < 30.0:
        lifespan_color = "bold yellow"
        lifespan_str = f"{years_int}岁 {days_int}天 (光阴无多)"
    else:
        lifespan_color = "bold cyan"
        lifespan_str = f"{years_int}岁 {days_int}天"

    # 血煞状态
    marked = char.karma.is_blood_marked()
    blood_status = "[bold red]【血煞狼烟·被天道通缉】[/bold red]" if marked else "[green]无煞[/green]"

    # 闭关状态
    med_status = ""
    if char.status == CharacterStatus.MEDITATING:
        progress = WorldClock.get_meditation_progress(char)
        rem_sec = progress.get("remaining_seconds", 0.0)
        mins = int(rem_sec // 60)
        secs = int(rem_sec % 60)
        med_status = f"\n[bold yellow]⚡【闭关静修中】距离预定出关还剩现实时间：{mins}分{secs}秒 (输入 /出关 可提前出关)[/bold yellow]"
        if progress.get("is_expired"):
            med_status += "\n[bold red]☠【洞府大限】寿元灯枯，肉身已衰！出关将结算坐化。[/bold red]"
        elif progress.get("lifespan_warning"):
            rem_y = progress.get("rem_years", 0.0)
            med_status += f"\n[bold red]⚠️【大限将至】闭关途中剩余寿元仅 {rem_y:.2f} 岁，可 /出关 抉择延寿或突破。[/bold red]"
        elif progress.get("is_idle_sitting"):
            med_status += "\n[dim]（已过有效吐纳窗口，其后枯坐无益）[/dim]"

    from config import WORLD_LOCATIONS
    loc_info = WORLD_LOCATIONS.get(char.location, {"density": 1.0, "is_safe": True})
    safety_tag = "[green]安全大阵庇护[/green]" if loc_info.get("is_safe", True) else "[bold red]凶险野外·可被攻杀[/bold red]"
    sect_str = f"{char.sect} · {char.sect_rank}" if char.sect else "四海散修"
    array_display = "、".join(char.arrays) if char.arrays else "[red]无阵盘(野外裸露)[/red]"

    content = f"""
[bold gold1]道号[/bold gold1]：{char.name:<12} [bold gold1]宗门[/bold gold1]：{sect_str}
[bold cyan]境界[/bold cyan]：{char.realm.name:<12} [bold cyan]修为[/bold cyan]：{char.realm.current_exp} / {char.realm.max_exp} {"[green](圆满·可渡劫)[/green]" if char.realm.is_full else ""}
[bold magenta]命格[/bold magenta]：{char.spiritual_root.display_name()}
[{lifespan_color}]寿元[/{lifespan_color}]：{lifespan_str}
[bold yellow]灵石[/bold yellow]：{char.spirit_stones} 块 [dim]金库 {char.vault_stones}[/dim]           [bold blue]道心[/bold blue]：{char.karma.dao_heart} / 100
[bold red]因果[/bold red]：业力 {char.karma.sin_value} | 功德 {char.karma.merit_value}  {blood_status}
[bold green]福地[/bold green]：{char.location} [dim](灵气浓度 {loc_info.get('density', 1.0):.1f}x | {safety_tag})[/dim]
[bold dim]身负法门：{"、".join(char.skills)} | 持有阵盘：{array_display}[/bold dim]{med_status}
"""

    now_str = WorldClock.format_game_time(WorldClock.now())
    panel = Panel(
        content.strip(),
        title=f"[bold green]═══ 九州天鉴 · {now_str} ═══[/bold green]",
        border_style="cyan"
    )
    console.print(panel)


def render_meditation_locked(rem_sec: float, end_time: float):
    """闭关期间动作拦截锁定提示"""
    import time
    minutes = int(rem_sec // 60)
    seconds = int(rem_sec % 60)
    time_str = f"{minutes}分 {seconds}秒" if minutes < 60 else f"{minutes//60}小时 {minutes%60}分"
    end_str = time.strftime('%H:%M:%S', time.localtime(end_time))
    content = f"""
[bold yellow]道友正处于洞府闭关静修之中！[/bold yellow]
[dim]· 神识内敛入定，肉身受洞府禁制守护，此期间[bold red]不可探查、不可斗法、不可突破、不可外出[/bold red]！[/dim]
[bold cyan]· 距离出关还剩现实时间[/bold cyan]：[bold red]{time_str}[/bold red] [dim](预定出关时间：{end_str})[/dim]
[dim]· 如遇紧急事宜欲强行出定，可输入 [/dim][bold green]/出关[/bold green][dim] 提前破关（按实际闭关现实时间结算修为与寿元）。[/dim]
"""
    panel = Panel(content.strip(), title="[bold red]◆ 洞府闭关 · 禁足入寂 ◆[/bold red]", border_style="yellow")
    console.print(panel)


def render_meditation_summary(res: dict):
    """渲染极其醒目的闭关与光阴流转战报"""
    if not res.get("success", False):
        console.print(Panel(f"[bold red]{res.get('message', '结算失败')}[/bold red]", title="闭关失败", border_style="red"))
        return

    if res.get("is_fatal", False) or res.get("died_in_cave", False):
        content = f"""
[bold red]☠ 洞府坐化 · 大限已至 ☠[/bold red]
[dim]{res.get('event_desc', res.get('message', '闭关途中寿元耗尽，肉身于静室中悄然坐化。'))}[/dim]
[yellow]本世道途至此终结，可重启程序真灵转世，重踏仙途。[/yellow]
"""
        console.print(Panel(content.strip(), title="☠ 大限坐化 ☠", border_style="red"))
        return

    # 寿元前后对比
    b_years = int(res["before_years"])
    b_days = int((res["before_years"] % 1.0) * 365)
    a_years = int(res["after_years"])
    a_days = int((res["after_years"] % 1.0) * 365)
    
    # 进度条
    exp_pct = min(1.0, res["after_exp"] / max(1, res["max_exp"]))
    bar_len = 20
    filled = int(bar_len * exp_pct)
    bar_str = "█" * filled + "░" * (bar_len - filled)

    stone_str = f" (消耗 {res['stones_burned']} 块灵石聚灵加速)" if res['stones_burned'] > 0 else ""
    bottleneck_str = "\n[bold gold1]⚡【瓶颈显现】真元已经满溢丹田，可随时输入 [/bold gold1][bold green]/突破[/bold green][bold gold1] 引动九天雷劫！[/bold gold1]" if res["is_bottleneck"] else ""

    rumors_text = "\n".join([f"  · [dim]{r}[/dim]" for r in res.get("world_rumors", [])])

    idle_str = ""
    if res.get("is_idle_sitting"):
        idle_str = "\n[bold yellow]⚠️ 有效吐纳已封顶，其后为枯坐虚耗（寿元照扣、修为无增）。[/bold yellow]"

    near_death_str = ""
    if a_years < 10:
        near_death_str = "\n[bold red]⚠️【大限将至】寿元不足 10 岁，宜速图突破或寻延寿之宝！[/bold red]"

    hours_show = res.get("actual_real_hours", res.get("hours", 0.0))
    eff_show = res.get("effective_hours", hours_show)

    content = f"""
[bold cyan]⏳ 光阴更迭[/bold cyan]：闭关苦修 {hours_show:.1f} 小时 [dim](有效吐纳 {eff_show:.1f}h · 世间已度过 {res['consumed_days']} 天 / {res['consumed_years']:.2f} 游戏年)[/dim]
[bold red]💀 寿元扣减[/bold red]：{b_years}岁 {b_days}天 ──► [bold yellow]{a_years}岁 {a_days}天[/bold yellow] [bold red](-{res['consumed_days']}天，大限逼近！)[/bold red]
[bold green]⚡ 修为进境[/bold green]：{res['before_exp']} ──► [bold green]{res['after_exp']} / {res['max_exp']}[/bold green] [bold cyan](+{res['exp_gained']})[/bold cyan]{stone_str}
[dim]   进度 [{bar_str}] {int(exp_pct * 100)}%[/dim]

[bold magenta]📜 心境气象[/bold magenta]：{res['event_title']}
   [dim]{res['event_desc']}[/dim]

[bold yellow]🌍 世事沧桑 · 闭关期间外界传闻[/bold yellow]：
{rumors_text}{idle_str}{near_death_str}{bottleneck_str}
"""
    panel = Panel(
        content.strip(),
        title="[bold green]═══ 闭关坐照 · 光阴如箭 ═══[/bold green]",
        border_style="green"
    )
    console.print(panel)


def render_tribulation_result(result: dict, heart_demon: str = ""):
    """渲染渡劫天劫战报"""
    if heart_demon:
        demon_panel = Panel(
            f"[bold magenta]{heart_demon}[/bold magenta]",
            title="[bold red]◆ 域外天魔 · 识海问心 ◆[/bold red]",
            border_style="red"
        )
        console.print(demon_panel)

    if result["success"]:
        panel = Panel(
            f"[bold green]{result['message']}[/bold green]",
            title="[bold gold1]★ 紫霄雷劫 · 功成圆满 ★[/bold gold1]",
            border_style="green"
        )
    else:
        panel = Panel(
            f"[bold red]{result['message']}[/bold red]",
            title="[bold red]☠ 天道劫雷 · 功败垂成 ☠[/bold red]",
            border_style="red"
        )
    console.print(panel)


def render_combat_result(result: dict):
    """渲染斗法搏杀战报"""
    color = "green" if not result.get("target_died", False) else "bold red"
    panel = Panel(
        result["report"],
        title="[bold red]⚔ 荒野斗法 · 杀机一瞬 ⚔[/bold red]",
        border_style=color
    )
    console.print(panel)


def render_scan_panel(results: list):
    """渲染神识探查雷达"""
    if not results:
        console.print(Panel("[dim]方圆二十里内山风猎猎，草木寂寂，并未探知任何活人灵压波动。[/dim]", title="神识探查"))
        return

    table = Table(title="[bold cyan]神识扫描感知列表[/bold cyan]", border_style="blue")
    table.add_column("目标编号", style="dim")
    table.add_column("探查情报", style="bold")

    for i, r in enumerate(results, 1):
        table.add_row(f"#{i}", r["description"])

    console.print(table)


def render_custom_art(art: dict):
    """渲染自创功法成果"""
    mods = art["cultivation_modifiers"]
    content = f"""
[bold gold1]功法道名[/bold gold1]：{art['name']} [{art['rank']}阶 · {'魔道' if art['nature'] == 'EVIL' else '正道'}]
[bold green]造化收益[/bold green]：
  · 修炼速度倍率提升至：{mods['exp_gain_multiplier']}x
  · 附带杀伐神通：{art['spells'][0]['name']} (威力倍率 {art['spells'][0]['multiplier']}x)

[bold red]天道反噬与代价[/bold red]：
  · 每年额外损耗寿元：{mods['lifespan_burn_per_year']} 岁
  · 突破天劫威力提升：+{int(mods['tribulation_power_add']*100)}%

[dim italic]"{art.get('lore', '')}"[/dim italic]
"""
    panel = Panel(content.strip(), title="[bold magenta]★ 天地顿悟 · 绝学自成 ★[/bold magenta]", border_style="magenta")
    console.print(panel)


def render_world_map(current_loc: str):
    """渲染九州山海乾坤舆图与灵脉分布表"""
    from config import WORLD_LOCATIONS

    map_art = """
[bold cyan]                 【海外·乱星海】[/bold cyan]
                        │
                [bold magenta]★ 万星古岛 (3.0x 绝地)[/bold magenta]
                        │ (海天极境)
[bold red]【西陲·幽冥渊】[/bold red] ───────┼─────── [bold green]【东荒·青州】[/bold green]
      │                 │                 │
九幽天魔宗坛      [bold yellow]【中土·万岳】[/bold yellow]     青云宗外门山门 / 宗门玄元洞府 (1.8x)
      │                 │                 │
黑风绝渊 (2.5x)    万剑仙门峰         青云坊市客栈 (1.0x 安全)
                  洗剑池洞天(2.0x)    落霞山灵泉 (1.6x 野外)
"""
    console.print(Panel(map_art.strip(), title="[bold gold1]═══ 九州山海乾坤舆图 ═══[/bold gold1]", border_style="gold1"))

    table = Table(title="[bold cyan]九州灵脉与洞天福地一览[/bold cyan]", border_style="cyan")
    table.add_column("地理大区", style="yellow")
    table.add_column("灵脉福地", style="bold")
    table.add_column("管辖势力", style="magenta")
    table.add_column("灵气浓度", style="cyan")
    table.add_column("安全禁制", style="green")
    table.add_column("洞府租金", style="white")
    table.add_column("地脉秘境说明", style="dim")

    for loc_name, info in WORLD_LOCATIONS.items():
        if "(" in loc_name:
            continue
        is_current = (loc_name == current_loc)
        name_display = f"📍 [bold gold1]{loc_name} (当前所在)[/bold gold1]" if is_current else loc_name
        safe_str = "[green]安全大阵[/green]" if info["is_safe"] else "[bold red]杀戮荒野[/bold red]"
        rent_str = f"{info['rent_per_hour']} 灵石/时" if info['rent_per_hour'] > 0 else "[green]免费[/green]"
        density_str = f"{info['density']:.1f}x"
        table.add_row(
            info.get("region", "未知"),
            name_display,
            info.get("sect", "散修"),
            density_str,
            safe_str,
            rent_str,
            info.get("desc", "")
        )

    console.print(table)
    console.print("[dim]提示：输入 [/dim][bold green]/前往 <地名>[/bold green][dim] 可御剑遁行至对应灵脉。[/dim]\n")


def render_sect_panel(char: Character):
    """渲染宗门势力与个人门派宗籍"""
    from config import SECTS_CONFIG

    current_sect_info = f"[bold gold1]道友当前门派[/bold gold1]：[bold green]{char.sect or '四海散修'} · {char.sect_rank}[/bold green]"
    if char.sect:
        sect_data = SECTS_CONFIG.get(char.sect, {})
        salary_val = sect_data.get('monthly_salary', 0)
        salary_str = f"{salary_val} 灵石/月" if salary_val > 0 else "无"
        current_sect_info += f"\n· 门派月俸标准：{salary_str} (输入 /领俸禄 可领取)"
        current_sect_info += f"\n· 宗门专属洞府：{sect_data.get('cave_location')} (免收洞府租金)"
    else:
        current_sect_info += "\n· 散修之身自由无拘，无宗门月俸。输入 /拜入 <宗门> 可参加入门考核。"


    console.print(Panel(current_sect_info, title="[bold cyan]◆ 个人门派宗籍 ◆[/bold cyan]", border_style="cyan"))

    table = Table(title="[bold gold1]九州天下仙门榜[/bold gold1]", border_style="gold1")
    table.add_column("宗门名称", style="bold yellow")
    table.add_column("阵营立意", style="magenta")
    table.add_column("总坛山门", style="cyan")
    table.add_column("门派月俸", style="green")
    table.add_column("入门赐予", style="blue")
    table.add_column("考核条件与门规约束", style="white")

    for s_name, s_info in SECTS_CONFIG.items():
        starter = s_info.get("starter_array") or "无"
        salary = f"{s_info.get('monthly_salary', 0)} 灵石" if s_info.get('monthly_salary', 0) > 0 else "无"
        table.add_row(
            s_name,
            s_info.get("alignment", "中立"),
            s_info.get("headquarters", "坊市"),
            salary,
            starter,
            s_info.get("rules_tip", "")
        )

    console.print(table)
    console.print("[dim]拜入宗门：前往各派总坛山门（如输入 [/dim][bold green]/前往 青云宗外门山门[/bold green][dim]），输入 [/dim][bold green]/拜入 青云宗[/bold green][dim] 叩关。[/dim]\n")


def render_legacy_settlement(settle: dict):
    """一世终结 · 转世结算面板"""
    past = settle.get("past_life")
    bd = settle.get("breakdown", {})
    lines = [
        f"[bold red]☠ 本世道途已终 ☠[/bold red]",
        f"[bold]死因[/bold]：{settle.get('cause', '身死道消')}",
    ]
    if past:
        lines.append(
            f"[bold]盖棺[/bold]：{past.name} · {past.realm} · 约享寿 {past.lifespan_lived} 岁"
            f"（业力 {past.sin} / 功德 {past.merit}）"
        )
    lines.append("")
    lines.append("[bold cyan]【道统点结算】[/bold cyan]")
    lines.append(
        f"  基础入册 {bd.get('base', 0)} + 境界 {bd.get('tier_points', 0)}"
        f" + 功德 {bd.get('merit_points', 0)} - 业力折损 {bd.get('sin_penalty', 0)}"
        f" = {bd.get('raw', 0)}（单世封顶后 {bd.get('capped', 0)}）"
    )
    if settle.get("penalty_applied"):
        lines.append(
            f"  [bold yellow]⚠ 短时间连续陨落，本世道统点减半"
            f"（实得 {settle.get('points_gained', 0)}）[/bold yellow]"
        )
    else:
        lines.append(f"  [bold green]实得道统点 +{settle.get('points_gained', 0)}[/bold green]")
    lines.append(
        f"  [bold gold1]道统池：{settle.get('account_points', 0)} 点"
        f"（累计 {settle.get('total_lives', 0)} 世）[/bold gold1]"
    )
    lines.append("")
    lines.append("[dim]道统点可于转世降生时兑换出身优势；亦可输入 /道统 查看前世与兑换目录。[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold red]═══ 一世终结 · 真灵归寂 ═══[/bold red]",
        border_style="red"
    ))


def render_legacy_panel(account):
    """道统池与前世一览"""
    content = (
        f"[bold gold1]道统点[/bold gold1]：{account.points} 点\n"
        f"[bold]累计转世[/bold]：{account.total_lives} 世 · "
        f"历史共得 {account.total_points_earned} 点"
    )
    console.print(Panel(content, title="[bold cyan]◆ 道统传承 ◆[/bold cyan]", border_style="cyan"))

    if account.past_lives:
        table = Table(title="[bold]前世典籍（最近最多 10 世）[/bold]", border_style="magenta")
        table.add_column("道号", style="yellow")
        table.add_column("终境", style="cyan")
        table.add_column("死因", style="red")
        table.add_column("约享寿", style="white")
        table.add_column("业/德", style="white")
        table.add_column("道统点", style="green")
        for p in reversed(account.past_lives):
            table.add_row(
                p.name,
                p.realm,
                p.cause,
                f"{p.lifespan_lived} 岁",
                f"{p.sin}/{p.merit}",
                f"+{p.points_gained}",
            )
        console.print(table)
    else:
        console.print("[dim]尚无前世记载，此乃第一世。[/dim]")

    from core.legacy import LegacyEngine
    boosts = LegacyEngine.list_boosts()
    btable = Table(title="[bold]转世出身兑换目录[/bold]", border_style="green")
    btable.add_column("编号", style="bold")
    btable.add_column("传承", style="yellow")
    btable.add_column("道统点", style="cyan")
    btable.add_column("效果", style="white")
    for i, b in enumerate(boosts, 1):
        btable.add_row(str(i), b["name"], str(b["cost"]), b["desc"])
    console.print(btable)
    console.print(
        "[dim]降生时可选择至多 3 项；亦可在转世提示中输入编号（如 1 2）。"
        "单次转世最多 3 项，防滚雪球。[/dim]\n"
    )


def render_birth_boost_result(boost_res: dict):
    """降生时道统点化结果"""
    if boost_res.get("applied"):
        console.print(
            f"[bold green]【道统点化】{boost_res.get('message', '')}[/bold green]"
        )
    elif boost_res.get("errors"):
        console.print(f"[bold yellow]{boost_res.get('message', '')}[/bold yellow]")


def render_bounty_board(bounties, viewer_id: str = ""):
    """坊市告示榜"""
    from core.bounty import BountyStatus

    if not bounties:
        console.print("[dim]告示栏空空如也，今日九州无赏可领。[/dim]\n")
        return

    table = Table(title="[bold gold1]坊市告示榜 · 悬赏血令[/bold gold1]", border_style="gold1")
    table.add_column("编号", style="bold")
    table.add_column("目标", style="red")
    table.add_column("赏金", style="yellow")
    table.add_column("苦主", style="cyan")
    table.add_column("缘由", style="white")
    table.add_column("状态", style="magenta")
    table.add_column("猎手", style="green")

    for i, b in enumerate(bounties, 1):
        status_map = {
            BountyStatus.OPEN: "[green]待猎[/green]",
            BountyStatus.CLAIMED: f"[yellow]已接令[/yellow]",
            BountyStatus.COMPLETED: "[dim]已销案[/dim]",
            BountyStatus.EXPIRED: "[dim]已过期[/dim]",
            BountyStatus.CANCELLED: "[dim]已撤回[/dim]",
        }
        hunter = b.hunter_name or "—"
        if b.hunter_id == viewer_id:
            hunter = f"[bold]{hunter}（阁下）[/bold]"
        table.add_row(
            str(i),
            b.target_name,
            f"{b.reward} 灵石",
            b.issuer_display(),
            b.reason[:18],
            status_map.get(b.status, b.status.value),
            hunter,
        )
    console.print(table)
    console.print(
        "[dim]接令：[/dim][bold green]/接令 <编号>[/bold green]"
        "  [dim]挂赏：[/dim][bold green]/挂赏 <道号> <赏金> [缘由][/bold green]"
        "  [dim]匿名加「匿」[/dim]\n"
    )


def render_karma_links(links, self_id: str, self_name: str):
    """个人因果链"""
    if not links:
        console.print("[dim]因果清白，与天下修士暂无仇怨恩义纠缠。[/dim]\n")
        return

    table = Table(title=f"[bold]因果纠缠 · {self_name}[/bold]", border_style="magenta")
    table.add_column("对方", style="yellow")
    table.add_column("关系", style="red")
    table.add_column("强度", style="cyan")
    table.add_column("记述", style="white")

    type_style = {"仇": "red", "恩": "green", "师徒": "cyan", "宗门": "magenta"}
    for link in links:
        _oid, other_name = link.other_side(self_id)
        t = link.link_type
        style = type_style.get(t, "white")
        table.add_row(
            other_name,
            f"[{style}]{t}[/{style}]",
            str(link.strength),
            link.note[:36],
        )
    console.print(table)
    console.print("[dim]血仇在身者，击杀可结案领赏；亦可 /挂赏 对方。[/dim]\n")


def render_market_panel(char: Character, listings=None):
    """坊市：金库、货单、寄售"""
    from core.market import MarketEngine

    if listings is None:
        listings = []

    vault_line = (
        f"[bold gold1]坊市金库[/bold gold1]：{char.vault_stones} 灵石 "
        f"[dim]（寄存不可被夺）[/dim] | [bold yellow]随身[/bold yellow]：{char.spirit_stones} 灵石"
    )
    inv = "、".join(char.inventory) if char.inventory else "[dim]无[/dim]"
    arr = "、".join(char.arrays) if char.arrays else "[dim]无[/dim]"
    bag = (
        f"[bold]随身阵盘[/bold]：{arr}\n"
        f"[bold]随身杂物[/bold]：{inv}"
    )
    console.print(Panel(
        f"{vault_line}\n{bag}",
        title=f"[bold cyan]◆ 青云坊市 · {char.name} 行囊 ◆[/bold cyan]",
        border_style="cyan",
    ))

    goods = MarketEngine.catalog()
    gtable = Table(title="[bold gold1]商会货单（可 /购买 /出售）[/bold gold1]", border_style="gold1")
    gtable.add_column("编号", style="bold")
    gtable.add_column("名目", style="yellow")
    gtable.add_column("类别", style="magenta")
    gtable.add_column("标价", style="cyan")
    gtable.add_column("说明", style="white")
    kind_cn = {"array": "阵盘", "pill": "丹药", "material": "材料"}
    for i, g in enumerate(goods, 1):
        gtable.add_row(str(i), g["name"], kind_cn.get(g["kind"], g["kind"]), f"{g['price']}", g["desc"])
    console.print(gtable)

    if listings:
        ltable = Table(title="[bold]玩家寄售（可 /买寄售 <编号>）[/bold]", border_style="green")
        ltable.add_column("编号", style="bold")
        ltable.add_column("货物", style="yellow")
        ltable.add_column("标价", style="cyan")
        ltable.add_column("卖家", style="magenta")
        for i, l in enumerate(listings, 1):
            ltable.add_row(str(i), l.item_name, f"{l.price}", l.seller_name)
        console.print(ltable)
    else:
        console.print("[dim]寄售栏暂无在售货物。[/dim]")

    console.print(
        "[dim]寄存：[/dim][bold green]/寄存 <数量>[/bold green]"
        "  [dim]支取：[/dim][bold green]/支取 <数量>[/bold green]\n"
        "[dim]寄售：[/dim][bold green]/寄售 <货物> <价格>[/bold green]"
        "  [dim]撤单：[/dim][bold green]/撤单 <编号>[/bold green]"
        "  [dim]服用：[/dim][bold green]/服用 <丹药>[/bold green]\n"
    )


def render_world_event(event: dict):
    """世界事件（机缘/危机/异象）面板"""
    if not event:
        return
    type_cn = {"fortune": "机缘", "crisis": "危机", "omen": "异象"}.get(event.get("type"), "异象")
    border = {"fortune": "green", "crisis": "red", "omen": "magenta"}.get(event.get("type"), "cyan")
    src = "AI" if event.get("source") == "ai" else "天道模板"
    content = f"""
[bold]{event.get('title', '无名')}[/bold] [dim]（{type_cn} · {src}）[/dim]

{event.get('narrative', '')}

[bold yellow]因果落账[/bold yellow]：{event.get('effects_summary', '无实质增减')}
"""
    console.print(Panel(
        content.strip(),
        title=f"[bold]═══ 世间异动 · {type_cn} ═══[/bold]",
        border_style=border,
    ))


def render_heart_demon_session(session):
    """心魔回合：幻境 + 选项"""
    lines = ["[bold magenta]" + session.narrative + "[/bold magenta]", ""]
    lines.append("[bold cyan]【问心应对】[/bold cyan]")
    for i, opt in enumerate(session.options, 1):
        style = opt.get("style") or ""
        lines.append(f"  [bold yellow]{i}[/bold yellow]. {opt.get('label','')} [dim]{style}[/dim]  [dim](id={opt.get('id')})[/dim]")
    lines.append("  [bold]其他[/bold]. 直接输入你的破法（自由应对，由 AI 裁定）")
    console.print(Panel(
        "\n".join(lines),
        title="[bold red]◆ 域外天魔 · 识海问心 ◆[/bold red]",
        border_style="red",
    ))


def render_heart_demon_result(res: dict):
    """心魔裁定结果"""
    if not res.get("success", True) and res.get("message"):
        console.print(f"[yellow]{res['message']}[/yellow]")
        return
    outcome_cn = {
        "pass": "过关", "wound": "受创", "heart_hit": "道心受挫",
        "dao_crack": "道基有损", "fail": "败于心魔", "death": "心魔道消",
    }.get(res.get("outcome", ""), res.get("outcome", ""))
    tmod = res.get("tribulation_mod", 0.0)
    tmod_s = f"{tmod:+.2f}" if tmod else "±0"
    src = "AI" if res.get("source") == "ai" else "天道"
    content = f"""
[bold]{outcome_cn}[/bold] [dim]（{src} · 对天劫修正 {tmod_s}）[/dim]

{res.get('narrative', '')}

[bold yellow]落账[/bold yellow]：{res.get('effects_summary', '无')}
"""
    border = "green" if res.get("outcome") == "pass" else "red"
    console.print(Panel(content.strip(), title="[bold]═══ 问心已定 ═══[/bold]", border_style=border))


def render_free_action(res: dict):
    """自由输入裁决面板"""
    intent = res.get("intent", "roleplay")
    outcome = res.get("outcome", "")
    src = "AI" if res.get("source") == "ai" else "天道"
    content = f"""
[bold cyan]意图[/bold cyan]：{intent} [dim]· 结局 {outcome} · {src}[/dim]

{res.get('narrative', '')}

[bold yellow]落账[/bold yellow]：{res.get('effects_summary', '无实质增减')}
"""
    border = "magenta" if outcome in ("crisis", "escalate", "steal") else "cyan"
    console.print(Panel(content.strip(), title="[bold]═══ 天命裁决 · 言行 ═══[/bold]", border_style=border))


def render_here_panel(viewer, rows):
    """当前地点同场修士一览"""
    from config import WORLD_LOCATIONS
    loc = WORLD_LOCATIONS.get(viewer.location, {})
    safe = "[green]安全[/green]" if loc.get("is_safe", True) else "[bold red]凶险[/bold red]"
    header = (
        f"[bold gold1]{viewer.location}[/bold gold1] · {loc.get('region','')} · {safe} · "
        f"灵气 {loc.get('density',1.0)}"
    )
    console.print(Panel(header, title="[bold cyan]◆ 同场一览 ◆[/bold cyan]", border_style="cyan"))

    if not rows:
        console.print("[dim]此地暂无其他修士灵压。[/dim]\n")
        return

    table = Table(title=f"[bold]同场共 {len(rows)} 人[/bold]", border_style="green")
    table.add_column("道号", style="yellow")
    table.add_column("境界", style="cyan")
    table.add_column("身份", style="white")
    table.add_column("宗门", style="magenta")
    table.add_column("性格", style="blue")
    table.add_column("对你", style="bold")
    table.add_column("议程", style="dim")
    table.add_column("标记", style="red")

    for r in rows:
        att = r.get("attitude_cn") or "—"
        av = r.get("attitude_value", 0)
        if r.get("is_npc"):
            if av <= -40:
                att_s = f"[bold red]{att}[/bold red]"
            elif av <= -15:
                att_s = f"[yellow]{att}[/yellow]"
            elif av >= 15:
                att_s = f"[green]{att}[/green]"
            else:
                att_s = att
            identity = f"NPC·{r.get('rank') or ''}".strip("·")
            pers = r.get("personality") or "—"
            ag = r.get("agenda") or "—"
            ag_note = r.get("agenda_note") or ""
            ag_s = f"{ag} {ag_note}".strip()
        else:
            att_s = "—"
            identity = "玩家"
            pers = "—"
            ag_s = "—"
        marks = []
        if r.get("blood_marked"):
            marks.append("血煞")
        if r.get("stealth"):
            marks.append("敛息")
        mark_s = "/".join(marks) if marks else ""
        table.add_row(
            r["name"], r["realm"], identity, r.get("sect") or "散修",
            pers, att_s, ag_s, mark_s,
        )
    console.print(table)
    console.print(
        "[dim]可用：[/dim][bold green]/交谈 <道号>[/bold green]"
        "  [bold green]/斗法 <道号>[/bold green]"
        "  [dim]（探查可看更模糊的灵压）[/dim]\n"
    )



