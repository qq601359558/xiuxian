"""
六榜：境界 / 战力 / 凶名 / 道行（P0）+ 传奇 / 资产（展示位，P1 可加权结算）
非力量榜只发软性荣誉，不发战力奖励（防刷）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import (
    LEADERBOARD_TOP_N,
    DAOHANG_MERIT_W,
    DAOHANG_SIN_W,
    DAOHANG_HEART_W,
    SECONDS_PER_GAME_YEAR,
)
from core.models import Character, CharacterStatus
from core.combat import CombatEngine


def _alive() -> List[Character]:
    from storage.db import CharacterRepository

    return [
        c
        for c in CharacterRepository.list_all_alive()
        if c.status != CharacterStatus.DEAD and not c.lifespan.is_dead()
    ]


def _is_player(c: Character) -> bool:
    uid = str(c.user_id or "")
    return not (uid.startswith("npc_") or uid.startswith("ai_npc_") or uid.startswith("t_"))


def score_realm(c: Character) -> float:
    return c.realm.tier * 1000 + c.realm.sub_tier * 100 + (
        c.realm.current_exp / max(1, c.realm.max_exp)
    ) * 50


def score_power(c: Character) -> float:
    return CombatEngine.calculate_power(c)


def score_notoriety(c: Character) -> float:
    """凶名：业力 + 血煞加成"""
    s = float(c.karma.sin_value)
    if c.karma.is_blood_marked():
        s *= 1.3
    return s


def score_daohang(c: Character) -> float:
    """道行：功德与道心为主，业力轻微负向"""
    return (
        c.karma.merit_value * DAOHANG_MERIT_W
        + c.karma.dao_heart * DAOHANG_HEART_W
        - c.karma.sin_value * DAOHANG_SIN_W
        + c.realm.tier * 20
    )


def score_legacy_fame(c: Character) -> float:
    """传奇（P1 软展示）：境界 + 功德/业力绝对值（事迹背书）"""
    return c.realm.tier * 50 + abs(c.karma.merit_value) + abs(c.karma.sin_value) * 0.3


def score_assets(c: Character) -> float:
    return float(c.spirit_stones + c.vault_stones)


def _top(
    chars: List[Character],
    key_fn,
    reverse: bool = True,
    n: int = LEADERBOARD_TOP_N,
) -> List[Dict[str, Any]]:
    ranked = sorted(chars, key=key_fn, reverse=reverse)
    out = []
    for i, c in enumerate(ranked[:n], 1):
        out.append(
            {
                "rank": i,
                "id": c.id,
                "name": c.name,
                "realm": c.realm.name,
                "sect": c.sect or "散修",
                "is_player": _is_player(c),
                "value": round(key_fn(c), 2),
            }
        )
    return out


BOARDS = {
    "realm": ("境界榜", score_realm, True),
    "power": ("战力榜", score_power, True),
    "notoriety": ("凶名榜", score_notoriety, True),
    "daohang": ("道行榜", score_daohang, True),
    "fame": ("传奇榜", score_legacy_fame, True),
    "assets": ("资产榜", score_assets, True),
}


class LeaderboardEngine:
    @staticmethod
    def board(name: str, n: int = LEADERBOARD_TOP_N) -> Dict[str, Any]:
        if name not in BOARDS:
            return {"ok": False, "error": f"未知榜单：{name}，可选 境界/战力/凶名/道行/传奇/资产"}
        title, fn, rev = BOARDS[name]
        rows = _top(_alive(), fn, reverse=rev, n=n)
        return {"ok": True, "title": title, "board": name, "rows": rows}

    @staticmethod
    def all_boards(n: int = 8) -> Dict[str, Any]:
        chars = _alive()
        out = {}
        for key, (title, fn, rev) in BOARDS.items():
            out[key] = {"title": title, "rows": _top(chars, fn, reverse=rev, n=n)}
        return {"ok": True, "boards": out}

    @staticmethod
    def format_board(name: str, n: int = LEADERBOARD_TOP_N) -> str:
        res = LeaderboardEngine.board(name, n)
        if not res.get("ok"):
            return res.get("error", "榜单不可用")
        lines = [f"【{res['title']}】（非力量榜仅荣衔，不发战力奖励）"]
        if not res["rows"]:
            lines.append("榜上暂无生灵。")
            return "\n".join(lines)
        for row in res["rows"]:
            tag = "玩家" if row["is_player"] else "NPC"
            lines.append(
                f"{row['rank']:2d}. {row['name']}  {row['realm']}  "
                f"{row['sect']}  [{tag}]  分 {row['value']}"
            )
        return "\n".join(lines)

    @staticmethod
    def format_all(n: int = 5) -> str:
        data = LeaderboardEngine.all_boards(n)
        parts = []
        for key in ("realm", "power", "notoriety", "daohang"):
            parts.append(LeaderboardEngine.format_board(key, n))
        parts.append("（传奇榜 / 资产榜 P1 结算叙事，可用 /榜 fame|assets 查看）")
        return "\n\n".join(parts)

    @staticmethod
    def find_self_rank(user_id: str, board: str) -> Optional[Dict[str, Any]]:
        res = LeaderboardEngine.board(board, n=50)
        if not res.get("ok"):
            return None
        for row in res["rows"]:
            # 通过 name 再查
            pass
        from storage.db import CharacterRepository

        c = CharacterRepository.get_by_user_id(user_id)
        if not c:
            return None
        for row in res["rows"]:
            if row["id"] == c.id:
                return row
        return None
