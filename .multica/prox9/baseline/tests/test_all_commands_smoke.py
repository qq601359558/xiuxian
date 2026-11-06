"""
全量指令冒烟：对 LAN World.handle 批量执行，记录 ok/error/exception。
不依赖外网；AI 类指令在无 KEY 时应返回可预期失败而非崩溃。
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ.setdefault("AI_REQUIRED", "0")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.world import WORLD  # noqa: E402  # 构造世界（auto_tick 可关）


def main():
    # 关闭后台 tick，避免并发干扰
    try:
        WORLD.stop_tick()
    except Exception:
        pass

    name = "指令自测员"
    j = WORLD.join(name, user_id="cmd_smoke_p1")
    token = j.get("token")
    assert token, j
    print(f"join ok: {j.get('name')} token={token[:8]}…")

    cmds = [
        # 只读
        "/help", "/帮助",
        "/look", "/地图", "/道身",
        "/here", "/同场",
        "/who",
        "/profile", "/人物", "/角色",
        "/roster", "/名录",
        "/legacy", "/道统",
        "/goals", "/目标",
        "/agenda", "/议程",
        "/bounty", "/告示",
        "/market", "/坊市",
        "/rank", "/榜单", "/榜",
        "/sect", "/宗门",
        "/season", "/纪元",
        "/qi", "/灵气",
        "/rumors", "/传闻",
        "/links", "/关系",
        "/legend", "/传说", "/典籍",
        "/channel", "/频道",
        "/history", "/大事记",
        "/recipes", "/配方",
        "/secret", "/秘境",
        "/除凶", "/hunt",
        "/宗门势", "/sectpower",
        "/宗门环", "/sectring",
        "/贡献",
        "/兑换",
        "/世情", "/worldinfo",
        "/ailog", "/AI日志",
        "/mingwu", "/名物",
        "/chatpanel", "/会话",
        "/status",  # CLI-only alias — 服端应未知或提示
        # 状态变更（轻）
        "/go", "/前往",
        "/scan", "/探查",
        "/meditate", "/闭关",
        "/emerge", "/出关",
        "/buy", "/购买",
        "/sell", "/出售",
        "/use", "/服用",
        "/deposit", "/寄存",
        "/withdraw", "/支取",
        "/list_item", "/寄售",
        "/buy_listing", "/买寄售",
        "/cancel_listing", "/撤单",
        "/place_bounty", "/挂赏",
        "/claim_bounty", "/接令",
        "/join_sect", "/拜入",
        "/salary", "/领俸禄", "/俸禄",
        "/promote", "/晋升",
        "/teach", "/传功",
        "/donate", "/上交",
        "/adventure", "/探险",
        "/dig", "/挖宝",
        "/equip", "/穿戴",
        "/unequip", "/卸下",
        "/omen", "/奇遇",
        "/omen_say", "/奇遇说",
        "/event", "/机缘",
        "/do", "/做",
        "/revenge", "/回访", "/因果",
        "/fight", "/斗法",
        "/talk", "/交谈",
        "/say", "/说",
        "/tick", "/npc",
        "/trade", "/交易",
        "/trade_offer", "/交易出",
        "/trade_accept", "/交易同意",
        "/trade_reject", "/交易拒绝",
        "/auction", "/拍卖行",
        "/auction_list", "/上拍",
        "/bid", "/拍",
        "/buyout", "/一口",
        "/auction_cancel", "/撤拍",
        "/npc_goods", "/npc货单",
        "/npc_buy", "/npc买",
        "/npc_sell", "/npc卖",
        "/拜师",
        "/确认拜师",
        "/收徒",
        "/出师",
        "/结拜",
        "/结拜同意",
        "/绝交",
        "/叛师",
        "/叛门", "/leave_sect",
        "/师门任务",
        "/交师门",
        "/结义任务",
        "/交结义",
        "/接除凶",
        "/弃除凶",
        "/反悬赏",
        "/围剿",
        "/追", "/follow",
        "/追查", "/chase",
        "/release", "/释放",
        "/hangup", "/挂断",
        "/reclude", "/归隐",
        "/unreclude", "/出隐",
        "/break", "/突破",
        "/create_art", "/自创功法",
        "/gen_pill", "/生成丹药",
        "/gen_equip", "/生成法宝",
        "/gen_monster", "/生成妖兽",
        "/forge", "/天工",
        "/悟丹",
        "/悟器",
        "/炼丹",
        "/炼器",
        "/apocalypse", "/大劫",
        "/notice", "/公告",
        "/ai", "/AI自检",
        "/gm",
        "/reborn", "/转世",
        "/logout", "/下线",
        # 错误用法
        "/购买",
        "/斗法",
        "/前往不存在之地_xyz",
        "/随便乱打的指令",
        "/因果",  # 服端=回访；CLI=因果链 → 语义冲突点
    ]

    results = []
    for c in cmds:
        try:
            r = WORLD.handle(token, c)
            ok = bool(r.get("ok")) if isinstance(r, dict) else None
            err = (r.get("error") or r.get("text") or "")[:80] if isinstance(r, dict) else str(r)[:80]
            kind = "OK" if ok else ("ERR" if ok is False else "?")
            results.append((c, kind, err))
        except Exception as e:
            results.append((c, "CRASH", f"{type(e).__name__}: {e}"))
            traceback.print_exc()

    print()
    print("=" * 72)
    print("指令冒烟结果")
    print("=" * 72)
    crashes = []
    errors = []
    unknownish = []
    oks = []
    for c, kind, msg in results:
        if kind == "CRASH":
            crashes.append((c, msg))
            print(f"  [CRASH] {c} → {msg}")
        elif kind == "ERR":
            errors.append((c, msg))
            print(f"  [ERR]   {c} → {msg}")
        else:
            oks.append((c, msg))
    print()
    print(f"合计 {len(results)}：OK {len(oks)} · ERR {len(errors)} · CRASH {len(crashes)}")
    if crashes:
        print("\n⚠ CRASH 必须修：")
        for c, m in crashes:
            print(f"  {c}: {m}")

    # 语义冲突探针：/因果 在服端行为
    r1 = WORLD.handle(token, "/因果")
    r2 = WORLD.handle(token, "/回访")
    r3 = WORLD.handle(token, "/links")
    print()
    print("语义探针：")
    print(f"  /因果  → ok={r1.get('ok')} text={(r1.get('text') or r1.get('error') or '')[:60]}")
    print(f"  /回访  → ok={r2.get('ok')} text={(r2.get('text') or r2.get('error') or '')[:60]}")
    print(f"  /关系  → ok={r3.get('ok')} text={(r3.get('text') or r3.get('error') or '')[:60]}")

    print()
    print("ERR 明细（前 40）：")
    for c, m in errors[:40]:
        print(f"  {c}: {m}")

    return 0 if not crashes else 1


if __name__ == "__main__":
    sys.exit(main())
