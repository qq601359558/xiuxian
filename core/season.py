"""
赛季（纪元）时钟与天地大劫预告
标准档：SEASON_DAYS 现实天 = 一纪元；未飞升者终局强制转世（P0 先做倒计时与预告）
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from config import SEASON_DAYS, SEASON_EPOCH_FILE, SEASON_WARN_DAYS


def _load_epoch() -> float:
    if SEASON_EPOCH_FILE.exists():
        try:
            return float(SEASON_EPOCH_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    now = time.time()
    SEASON_EPOCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEASON_EPOCH_FILE.write_text(str(now), encoding="utf-8")
    return now


def season_info(now: Optional[float] = None) -> Dict[str, Any]:
    t = now if now is not None else time.time()
    epoch = _load_epoch()
    season_seconds = SEASON_DAYS * 86400.0
    elapsed = max(0.0, t - epoch)
    season_number = int(elapsed // season_seconds) + 1
    in_season_sec = elapsed % season_seconds
    day_in_season = in_season_sec / 86400.0
    remain_sec = season_seconds - in_season_sec
    remain_days = remain_sec / 86400.0
    remain_real_days = max(0.0, remain_days)
    # 纪元最后一刻（<1 小时）即视为大劫已至
    is_final_week = remain_real_days <= SEASON_WARN_DAYS
    is_ended = remain_real_days <= 0.02 or remain_sec <= 3600.0
    return {
        "season_number": season_number,
        "day_in_season": round(day_in_season, 2),
        "total_days": SEASON_DAYS,
        "remain_real_days": round(remain_real_days, 2),
        "is_final_week": is_final_week,
        "is_ended": is_ended,
        "epoch": epoch,
        "game_years_left": int(remain_real_days),  # 1 游戏年 = 1 现实天
    }


def season_status_text(now: Optional[float] = None) -> str:
    info = season_info(now)
    base = (
        f"第 {info['season_number']} 纪元 · 第 {info['day_in_season']:.1f} 天"
        f"/共 {info['total_days']} 天（余约 {info['remain_real_days']:.1f} 天）"
    )
    if info["is_ended"]:
        return base + " —— 天地大劫已至，未飞升者将应劫转世。"
    if info["is_final_week"]:
        return base + f" —— ⚠ 大劫预兆：终局前 {SEASON_WARN_DAYS} 日，天象有异，宜早做飞升或转世准备。"
    return base + " —— 灵机尚稳，可从容修行。"


def set_epoch(epoch_ts: float) -> None:
    SEASON_EPOCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEASON_EPOCH_FILE.write_text(str(epoch_ts), encoding="utf-8")


def settle_apocalypse(now: Optional[float] = None) -> Dict[str, Any]:
    """
    天地大劫结算：全服未死修士应劫，道统落账，纪元重开。
    由 world 层调用；此处只给纪元推进与统计骨架。
    """
    t = now if now is not None else time.time()
    info = season_info(t)
    if not info.get("is_ended"):
        return {
            "ok": False,
            "message": (
                f"大劫未至（余约 {info['remain_real_days']:.1f} 天）。"
                "可用 /纪元 查看倒计时。"
            ),
        }
    # 开启新纪元
    ended = int(info["season_number"] or 0)
    set_epoch(t)
    try:
        from core import rumors

        rumors.note_apocalypse(ended)
    except Exception:
        pass
    try:
        from core.world_channel import WorldChannel
        from core.legends import write_apocalypse_legends

        WorldChannel.post(
            "apocalypse",
            f"【大劫】第 {ended} 纪元终了，未飞升者皆应劫转世，新纪元开启。",
            level="epic",
            actor="天道",
            skip_limit=True,
        )
        write_apocalypse_legends(ended, now=t)
    except Exception:
        pass
    return {
        "ok": True,
        "ended_season": ended,
        "message": f"【天地大劫】第 {ended} 纪元终了，新纪元开启。",
        "new_epoch": t,
    }
