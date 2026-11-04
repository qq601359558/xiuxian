"""
账户钱包与死亡资金归集（account-death-rework §2.2–§2.3、§2.7、§5.2）。

记账原则（spec §2.1）：
- 资金守恒：划转＝一边减、一边加，同一调用内完成，禁止复制式入账。
- 钱包是账户的唯一死后归宿；死行清零后，任何仍以旧角色 id 为目标的付款都是 bug。
- 单据幂等：入账前查流水 ref，已存在则跳过。
- NPC（user_id 以 npc_/ai_npc_ 开头）无账户行，不走钱包。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from core.legacy import LegacyAccount, WalletEntry
from core.models import Character, CharacterStatus

WALLET_LEDGER_KEEP = 50


def is_npc_user(user_id: str) -> bool:
    uid = user_id or ""
    return uid.startswith("npc_") or uid.startswith("ai_npc_")


def wallet_summary(account: LegacyAccount) -> Dict[str, Any]:
    """钱包查询块（§2.6/§2.8：余额＋最近流水，供 /login 死者 payload、/转世、_status_dict）"""
    entries = [
        {
            "ts": e.ts,
            "kind": e.kind,
            "amount": e.amount,
            "ref": e.ref,
            "note": e.note,
        }
        for e in (account.wallet_ledger or [])[-5:]
    ]
    return {
        "balance": max(0, int(account.wallet_stones or 0)),
        "entries": entries,
        "ledger": entries,
    }


def wallet_panel_text(account: LegacyAccount, username: str = "") -> str:
    """CLI /钱包 与 server /钱包 的面板文本（§2.8：户名／余额／最近 5 条／提取指引）"""
    summary = wallet_summary(account)
    lines = [
        f"【账户钱包】户名：{username or account.user_id} · 余额：{summary['balance']} 灵石",
    ]
    if summary["entries"]:
        for e in summary["entries"]:
            sign = "+" if e["amount"] >= 0 else ""
            lines.append(f"  · {e['kind']} {sign}{e['amount']} 灵石（{e['note'] or e['ref']}）")
    else:
        lines.append("  · 暂无流水。")
    lines.append("提取：/钱包提取 <金额>（钱包 −n，角色随身 ＋n，零手续费）")
    return "\n".join(lines)


def credit_wallet_status(
    account: LegacyAccount,
    amount: int,
    kind: str,
    ref: str,
    note: str = "",
    sweep_spirit: int = 0,
    sweep_vault: int = 0,
) -> str:
    """钱包入账，拆开旧 credit_wallet 的 False 语义（评审 S6）：

    - "credited"：本次入账；
    - "duplicate"：ref 已在保留的最近 50 条流水中，已付过，不得双记（正常，调用方视为已付）；
    - "skipped"：金额 ≤0，无入账。
    流水截断后旧 ref 落出窗口时，单据终态（SOLD／EXPIRED 等）是第二道防线（spec §2.7）。
    """
    amount = int(amount or 0)
    if amount <= 0:
        return "skipped"
    if any((e.ref or "") == ref for e in (account.wallet_ledger or [])):
        return "duplicate"
    account.wallet_stones = max(0, int(account.wallet_stones or 0) + amount)
    account.wallet_ledger.append(
        WalletEntry(
            ts=time.time(),
            kind=kind,
            amount=amount,
            ref=ref,
            note=note or "",
            sweep_spirit=int(sweep_spirit or 0),
            sweep_vault=int(sweep_vault or 0),
        )
    )
    account.wallet_ledger = account.wallet_ledger[-WALLET_LEDGER_KEEP:]
    return "credited"


def credit_wallet(
    account: LegacyAccount,
    amount: int,
    kind: str,
    ref: str,
    note: str = "",
    sweep_spirit: int = 0,
    sweep_vault: int = 0,
) -> bool:
    """钱包入账（逻辑层 ref 唯一约束）。返回 True=本次入账，False=跳过（金额≤0 或 ref 已存在）。

    调用方负责在入账后保存账户行（LegacyRepository.save），且须先写钱包流水再保存
    单据终态（spec §2.7.2）。余额钳制下限 0，流水只保留最近 50 条。
    需要区分 duplicate 与 skipped 时用 credit_wallet_status。
    sweep_spirit/sweep_vault 仅 death_sweep（含残差）入账时传，写入流水 breakdown。
    """
    return (
        credit_wallet_status(
            account, amount, kind, ref, note, sweep_spirit, sweep_vault
        )
        == "credited"
    )


def death_sweep_breakdown(entry: WalletEntry) -> Optional[tuple]:
    """取一条 death_sweep 流水的（随身，寄存）breakdown；取不到返回 None。

    主口径是 WalletEntry.sweep_spirit/sweep_vault 显式字段（须与 amount 加总一致）。
    兼容回退：本字段上线前写入的旧条目两字段均为 0 但 amount > 0，此时解析
    note 中的「随身 X＋寄存 Y」——旧 note 格式由 sweep 步骤②统一写出，解析失败返回 None。
    """
    spirit = int(entry.sweep_spirit or 0)
    vault = int(entry.sweep_vault or 0)
    if (spirit, vault) != (0, 0) or int(entry.amount or 0) == 0:
        return (spirit, vault)
    import re

    m = re.search(r"随身\s*(\d+)＋寄存\s*(\d+)", entry.note or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def sweep_has_real_change(details: Dict[str, Any]) -> bool:
    """sweep 是否产生真实变化（QA-D1：server 已结算分支与 CLI 已结算分支同口径）。

    只认实际入账／真实状态变化：首笔／残差实际入账、拍卖退款实际入账、
    议政票作废、当票没收。ref 已存在而跳过的重放、崩溃重放均不在此列，
    故无真实变化时 server 返回 None、CLI 不打印【资金补扫】。
    注意：details.errors（步骤异常）不在此列——异常仍由调用方另记
    WALLET_SWEEP_PARTIAL 大事记，不单独触发 backfilled／补扫打印。
    """
    return bool(
        details.get("sweep_credited")
        or details.get("residual_credited")
        or details.get("auction_credited")
        or details.get("council_voided")
        or details.get("pawn_forfeits")
    )


def has_wallet_ref(account: LegacyAccount, ref: str) -> bool:
    return any((e.ref or "") == ref for e in (account.wallet_ledger or []))


def withdraw_to_character(
    account: LegacyAccount,
    char: Character,
    amount: int,
) -> Dict[str, Any]:
    """钱包提取（§2.7.4）：n 为正整数且 n ≤ wallet 时，wallet −n 且角色随身 ＋n。

    只改内存对象；调用方须同步保存账户行与角色行，任一保存失败则整体失败回显。
    """
    try:
        n = int(amount)
    except (TypeError, ValueError):
        return {"success": False, "message": "提取金额须为正整数。"}
    if n <= 0:
        return {"success": False, "message": "提取金额须为正整数。"}
    balance = int(account.wallet_stones or 0)
    if n > balance:
        return {
            "success": False,
            "message": f"钱包仅有 {balance} 灵石，不足提取 {n}。",
        }
    account.wallet_stones = balance - n
    char.spirit_stones = int(char.spirit_stones or 0) + n
    account.wallet_ledger.append(
        WalletEntry(
            ts=time.time(),
            kind="wallet_withdraw",
            amount=-n,
            ref=f"withdraw:{time.time():.6f}",
            note=f"提取到角色【{char.name}】随身",
        )
    )
    account.wallet_ledger = account.wallet_ledger[-WALLET_LEDGER_KEEP:]
    return {
        "success": True,
        "amount": n,
        "wallet": account.wallet_stones,
        "stones": char.spirit_stones,
        "message": (
            f"【钱包提取】钱包 −{n} 灵石／随身 ＋{n} 灵石。"
            f"钱包余额 {account.wallet_stones}｜随身 {char.spirit_stones}。"
        ),
    }


def sweep_death_funds(char: Character, account: LegacyAccount) -> Dict[str, Any]:
    """死亡资金归集（spec §2.3，顺序即契约；双入口 CLI/server 共用同一实现）。

    步骤：① 当面交易会话取消（锁定资金先退回行，再归集）→ ② 随身＋寄存入钱包、
    死行清零（单据 ref=死者角色 id，幂等）→ ③ 拍卖领先出价退款＋拍品回起拍
    （ref=拍品 id）→ ④ 未结算议政场次死者票作废 → ⑤ OPEN 当票按逾期口径没收
    （本金不另记，已在步骤 ② 的随身中）。
    NPC 不走钱包；调用方负责保存账户行与死者角色行（本函数内拍卖／议政／当票
    的单据保存由各引擎落库，钱包行在各入账步后即保存，满足 §2.7.2 先钱包后单据）。
    返回明细 dict（供死亡结算页／大事记／死者 payload 展示）。
    """
    details: Dict[str, Any] = {
        "spirit": 0,
        "vault": 0,
        "total": 0,
        "auction_refunds": [],
        "council_voided": 0,
        "pawn_forfeits": [],
        "trade_cancelled": False,
        "skipped_npc": False,
        # 评审 M5：拍卖／议政／当票／交易四步的异常不再静默吞掉，记日志＋带 errors；
        # 评审 S3：寄售在售单数（按 seller_user_id／seller_id 计 OPEN 单）。
        "errors": [],
        "residual_credited": False,
        "sweep_credited": False,
        # QA-D1/D2：total 只计本次实际入账；auction_refunds 只含实际入账的退款；
        # ref 已存在而跳过的入账（崩溃重放／重复退款）记 0，不进上述两项，
        # 统一记入 skipped（{kind, ref, amount, reason}）；auction_credited 表示
        # 本次确有拍卖退款入账；replay 表示步骤②判定为首笔崩溃重放。
        "auction_credited": False,
        "replay": False,
        "skipped": [],
        "consignment_open_count": 0,
    }
    if is_npc_user(char.user_id or ""):
        details["skipped_npc"] = True
        return details

    from storage.db import (
        AuctionLotRepository,
        CharacterRepository,
        LegacyRepository,
    )

    # ① 当面交易会话取消：锁定灵石／物品退回双方行（死者侧退回后由步骤 ② 归集）
    try:
        from core.trade import TradeEngine

        cancelled = TradeEngine.cancel_for_death(char.id)
        details["trade_cancelled"] = bool(cancelled)
    except Exception as exc:  # M5：交易步异常记日志＋进 errors，不静默
        logger.error("sweep trade cancel failed for %s: %s", char.id, exc)
        details["trade_cancelled"] = False
        details["errors"].append({"step": "trade", "error": str(exc)})
    # 取消会话落库的是 DB 副本；把死者行最新余额同步回传入对象，避免调用方旧对象覆盖
    try:
        fresh = CharacterRepository.get_by_id(char.id)
        if fresh is not None:
            char.spirit_stones = fresh.spirit_stones
            char.vault_stones = fresh.vault_stones
    except Exception:
        pass

    # ② 随身＋寄存：ref=死者角色 id 幂等；已入账过则跳过入账，但仍清零（死行清零原则）。
    # QA-D2：首笔崩溃重放（账户已保存 death_sweep、死行未清零保存）不能再走残差——
    # 残差 ref 与首笔 ref 不同，旧逻辑会把同一笔钱再记一次。现先查首笔流水的
    # breakdown（显式字段，旧条目回退解析 note）：与当前行内（随身，寄存）完全
    # 相等 → 判定为崩溃重放：只清零、不入账、置 replay 标志、记 skipped；
    # 不等 → 走评审 M1 残差逻辑：残差 ref 由（角色 id＋残差金额）派生，
    # 两次 sweep 之间新落入的、金额不同的残差 → 不同 ref → 正常入账；
    # 残差 ref 已存在 → 残差崩溃重放，跳过不双记（见 spec §2.7.7）。
    # 本步异常不捕获、直接上传：调用方不得在随身归集失败后把 death_settled 置真。
    # 关键门限：重放判定只在 death_settled 为假时适用。death_settled 真意味着
    # 道统结算已完成且死行已随结算保存（两调用方均在结算后才保存死行），
    # 此后行内余额只可能是结算后新落入的钱，必须走残差——无此门限时，
    # 已结算行落入的同额新钱会被误判为重放而清零丢弃（QA-D1 CLI 用例即此情形）。
    # 残余边界（spec §2.7.7 诚实记录）：未结算但死行已清零保存、之后又落入
    # 同额新钱时，仍会被误判为重放而清零不入账；另，已结算行补扫首笔本身
    # 在“账户已保存、死行未保存”的极窄窗口崩溃时，重放会走残差而双记。
    # 两者均需漏网付款＋同额＋特定崩溃点叠加，主路径死行付款已全部改道钱包，
    # 残差只是最后一道网，仍属已知边界。
    spirit = max(0, int(char.spirit_stones or 0))
    vault = max(0, int(char.vault_stones or 0))
    total = spirit + vault
    already = has_wallet_ref(account, char.id)
    first_entry = next(
        (
            e
            for e in (account.wallet_ledger or [])
            if (e.ref or "") == char.id and e.kind == "death_sweep"
        ),
        None,
    )
    if total > 0 and not already:
        if credit_wallet(
            account,
            total,
            "death_sweep",
            char.id,
            f"死亡归集：随身 {spirit}＋寄存 {vault}（{char.name}）",
            sweep_spirit=spirit,
            sweep_vault=vault,
        ):
            LegacyRepository.save(account)
            details["sweep_credited"] = True
        else:
            details["skipped"].append(
                {"kind": "death_sweep", "ref": char.id, "amount": total, "reason": "duplicate"}
            )
    elif total > 0 and already:
        first_breakdown = death_sweep_breakdown(first_entry) if first_entry is not None else None
        if (
            first_breakdown is not None
            and first_breakdown == (spirit, vault)
            and not getattr(char, "death_settled", False)
        ):
            details["replay"] = True
            details["skipped"].append(
                {"kind": "death_sweep", "ref": char.id, "amount": total, "reason": "crash_replay"}
            )
        else:
            residual_ref = f"{char.id}:residual:{spirit}:{vault}"
            if not has_wallet_ref(account, residual_ref):
                if credit_wallet(
                    account,
                    total,
                    "death_sweep",
                    residual_ref,
                    f"死亡归集残差：随身 {spirit}＋寄存 {vault}（{char.name}）",
                    sweep_spirit=spirit,
                    sweep_vault=vault,
                ):
                    LegacyRepository.save(account)
                    details["residual_credited"] = True
                else:
                    details["skipped"].append(
                        {"kind": "death_sweep", "ref": residual_ref, "amount": total, "reason": "duplicate"}
                    )
            else:
                details["skipped"].append(
                    {"kind": "death_sweep", "ref": residual_ref, "amount": total, "reason": "duplicate"}
                )
    details["spirit"] = spirit
    details["vault"] = vault
    char.spirit_stones = 0
    char.vault_stones = 0

    # ③ 拍卖领先出价退款＋回起拍（此前被超价者早已在 _apply_bid 时退过款，
    # 故 OPEN 单上除领先者外无其他 frozen 资金）
    try:
        for lot in AuctionLotRepository.list_all():
            if not lot.is_open():
                continue
            is_leader = (
                (lot.leader_user_id or "") == (char.user_id or "")
                or (lot.leader_id or "") == char.id
            )
            if not is_leader or lot.bid_count <= 0:
                continue
            bid = int(lot.current_bid or 0)
            if bid > 0:
                # QA-D1：只有实际入账才进 auction_refunds／计 total；ref 已存在
                # 的崩溃重放记 0，记 skipped，不再按毛额计入（拍品仍须回起拍，
                # 退款本身崩溃前已入账，不因跳过而重复或滞留）。
                if credit_wallet(
                    account,
                    bid,
                    "auction_refund",
                    lot.id,
                    f"拍卖退款：【{lot.item_name}】领先出价退还",
                ):
                    LegacyRepository.save(account)
                    details["auction_credited"] = True
                    details["auction_refunds"].append(
                        {"lot_id": lot.id, "item": lot.item_name, "amount": bid}
                    )
                else:
                    details["skipped"].append(
                        {"kind": "auction_refund", "ref": lot.id, "amount": bid, "reason": "duplicate"}
                    )
            lot.leader_id = None
            lot.leader_user_id = None
            lot.leader_name = None
            lot.current_bid = lot.start_price
            lot.bid_count = 0
            AuctionLotRepository.save(lot)
    except Exception as exc:  # M5：拍卖步异常记日志＋进 errors，不静默
        logger.error("sweep auction refund failed for %s: %s", char.id, exc)
        details["errors"].append({"step": "auction", "error": str(exc)})

    # ④ 议政票作废（仅未结算场次；已结算快照不动）
    try:
        from core.council import CouncilEngine

        details["council_voided"] = CouncilEngine.void_dead_votes(char)
    except Exception as exc:  # M5
        logger.error("sweep council void failed for %s: %s", char.id, exc)
        details["council_voided"] = 0
        details["errors"].append({"step": "council", "error": str(exc)})

    # ⑤ 当票没收（逾期口径；本金已在步骤 ② 的随身中，不另记）
    try:
        from core.pawn import PawnEngine

        forfeited = PawnEngine.forfeit_all(char.id)
        details["pawn_forfeits"] = [
            {"ticket_id": t.id, "item": t.item_name, "redeem": t.redeem_cost()}
            for t in forfeited
        ]
    except Exception as exc:  # M5
        logger.error("sweep pawn forfeit failed for %s: %s", char.id, exc)
        details["pawn_forfeits"] = []
        details["errors"].append({"step": "pawn", "error": str(exc)})

    # S3：寄售在售单数（展示用；取数失败时记日志、置 0，不阻断归集）
    try:
        from storage.db import MarketListingRepository

        details["consignment_open_count"] = sum(
            1
            for lst in MarketListingRepository.list_all()
            if lst.is_open()
            and ((lst.seller_user_id or "") == (char.user_id or "") or lst.seller_id == char.id)
        )
    except Exception as exc:
        logger.warning("sweep consignment count failed for %s: %s", char.id, exc)
        details["consignment_open_count"] = 0

    # QA-D1：合计行＝本次实际入账额（首笔／残差入账额＋实际入账的拍卖退款），
    # 与钱包增量一致。spirit/vault 仍为清零前行内观测额：正常路径（首笔／残差
    # 入账）下 total == spirit + vault + 退款合计，与 S1 口径一致；崩溃重放／
    # 跳过路径下入账额为 0 或部分，total 小于观测额，差额见 details["skipped"]。
    credited_sweep = (
        details["spirit"] + details["vault"]
        if (details["sweep_credited"] or details["residual_credited"])
        else 0
    )
    details["total"] = credited_sweep + sum(
        int(r.get("amount") or 0) for r in details["auction_refunds"]
    )
    return details
