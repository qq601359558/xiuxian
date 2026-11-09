"""
飞升榜（F12）：历世纪念碑——只纪 player_legacy 已落账之前世，跨纪元综合排序。

与现世六榜（core/leaderboard.py，数据源为存活角色）正交：本榜数据源为
LegacyAccount.past_lives（死亡结算 settle_death 落账后才有的记录），
现世进行中的一世永不入榜。纯只读：零写盘、零 AI。
口径全文见 docs/compose/spec/ascension.md。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from config import REALM_NAMES, SUB_TIER_NAMES

ASCEND_TOP_N = 20
ASCEND_W_TIER = 1000.0
ASCEND_W_SUB = 100.0
ASCEND_W_POINTS = 10.0
ASCEND_W_AGE = 0.5
ASCEND_AGE_CAP_YEARS = 300.0

# 玩家账号口径：与 core/leaderboard.py 的 _is_player 同前缀集
_NON_PLAYER_PREFIXES = ("npc_", "ai_npc_", "t_")


def _is_player_account(user_id: Any) -> bool:
    uid = str(user_id or "")
    return not uid.startswith(_NON_PLAYER_PREFIXES)


def parse_realm(realm_name: Any) -> tuple:
    """境界全名（如「金丹期圆满」）反解 (tier, sub_tier)；无法识别按 (0, 0)。"""
    name = str(realm_name or "")
    tier, best_len = 0, -1
    for i, rn in enumerate(REALM_NAMES):
        if rn and name.startswith(rn) and len(rn) > best_len:
            tier, best_len = i, len(rn)
    sub = 0
    # Realm.name 仅对 tier 1..8 拼小阶后缀；0（凡人）与 >=9（渡劫飞升）无后缀，不解析（评审 S4）
    if best_len >= 0 and 1 <= tier <= 8:
        rest = name[best_len:]
        for j, sn in enumerate(SUB_TIER_NAMES):
            if rest.startswith(sn):
                sub = j
                break
    return tier, sub


def score_of(tier: int, sub_tier: int, points_gained: Any, lifespan_lived: Any) -> float:
    """综合分：境界档位严格主导，道统点次之，享寿小权重（封顶计入）。"""
    try:
        pts = float(points_gained or 0)
    except (TypeError, ValueError):
        pts = 0.0
    try:
        lived = float(lifespan_lived or 0)
    except (TypeError, ValueError):
        lived = 0.0
    if not math.isfinite(pts):
        pts = 0.0
    if not math.isfinite(lived):
        lived = 0.0
    return (
        tier * ASCEND_W_TIER
        + sub_tier * ASCEND_W_SUB
        + pts * ASCEND_W_POINTS
        + min(max(lived, 0.0), ASCEND_AGE_CAP_YEARS) * ASCEND_W_AGE
    )


def cause_category(cause: Any) -> str:
    """死因原文 → 大类（关键词规则，面板展示用）。"""
    text = str(cause or "")
    if "劫" in text:
        return "渡劫陨落"
    if "魔" in text:
        return "心魔入魔"
    if any(k in text for k in ("杀", "斩", "斗", "战", "仇", "凶")):
        return "陨于斗法"
    if any(k in text for k in ("寿", "坐化", "老")):
        return "寿尽坐化"
    return "道陨身死"


def season_of(died_at: Any) -> Optional[int]:
    """由坐化时间戳经赛季时钟单点（core/season.py）推导纪元号；无戳返回 None。"""
    try:
        ts = float(died_at or 0)
    except (TypeError, ValueError):
        return None
    if ts <= 0 or not math.isfinite(ts):
        return None
    try:
        from core.season import season_info

        return int(season_info(ts)["season_number"])
    except Exception:
        return None


def _sort_key(entry: Dict[str, Any]):
    died = entry.get("died_at") or 0
    died_key = float(died) if died and float(died) > 0 else math.inf
    # 末段再以死因/道统/享寿兜底，逼近严格全序（评审 S1）；全同者本就不可区分
    return (
        -entry["score"],
        died_key,
        entry["name"],
        entry["user_id"],
        entry.get("cause", ""),
        -entry.get("points_gained", 0),
        -entry.get("lifespan_lived", 0.0),
    )


def _safe_float(value: Any) -> float:
    try:
        out = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return out if math.isfinite(out) else 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class AscensionEngine:
    """飞升榜只读引擎：展开 legacy 前世 → 计分 → 确定性排序 → 面板文本。"""

    @staticmethod
    def collect_entries(accounts: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """全部玩家账号的已落账前世条目，已按榜序排定并标注全局 rank。"""
        if accounts is None:
            from storage.db import LegacyRepository

            accounts = LegacyRepository.list_all()
        entries: List[Dict[str, Any]] = []
        for acc in accounts or []:
            uid = str(getattr(acc, "user_id", "") or "")
            if not _is_player_account(uid):
                continue
            for life in getattr(acc, "past_lives", None) or []:
                tier, sub = parse_realm(getattr(life, "realm", ""))
                entries.append(
                    {
                        "user_id": uid,
                        "name": str(getattr(life, "name", "") or "无名"),
                        "realm": str(getattr(life, "realm", "") or "凡人"),
                        "tier": tier,
                        "sub_tier": sub,
                        "cause": str(getattr(life, "cause", "") or ""),
                        "cause_category": cause_category(getattr(life, "cause", "")),
                        "lifespan_lived": _safe_float(getattr(life, "lifespan_lived", 0)),
                        "points_gained": _safe_int(getattr(life, "points_gained", 0)),
                        "died_at": _safe_float(getattr(life, "died_at", 0)),
                        "season": season_of(getattr(life, "died_at", 0)),
                        "score": score_of(
                            tier,
                            sub,
                            getattr(life, "points_gained", 0),
                            getattr(life, "lifespan_lived", 0),
                        ),
                    }
                )
        entries.sort(key=_sort_key)
        for i, e in enumerate(entries, 1):
            e["rank"] = i
        return entries

    @staticmethod
    def ranked(
        season: Optional[int] = None,
        accounts: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """全局榜序；给定 season 时只留该纪元条目，rank 在过滤集内重排（global_rank 保留）。"""
        entries = AscensionEngine.collect_entries(accounts)
        if season is None:
            return entries
        out = []
        for e in entries:
            if e.get("season") == season:
                row = dict(e)
                row["global_rank"] = e["rank"]
                out.append(row)
        for i, e in enumerate(out, 1):
            e["rank"] = i
        return out

    @staticmethod
    def _row_line(e: Dict[str, Any]) -> str:
        season = f"第{e['season']}纪元" if e.get("season") else "纪元不详"
        return (
            f"{e['rank']:2d}. {e['name']}  {e['realm']}  分 {e['score']:.0f}  "
            f"享寿 {e['lifespan_lived']:.0f} 岁  {e['cause_category']}  {season}"
        )

    @staticmethod
    def _board_text(rows: List[Dict[str, Any]], header: str, empty_text: str) -> str:
        lines = [header]
        if not rows:
            lines.append(empty_text)
            return "\n".join(lines)
        lines.extend(AscensionEngine._row_line(e) for e in rows)
        return "\n".join(lines)

    @staticmethod
    def _self_text(entries: List[Dict[str, Any]], viewer_user_id: Optional[str]) -> str:
        mine = [e for e in entries if viewer_user_id and e["user_id"] == viewer_user_id]
        if not mine:
            return (
                "【飞升榜 · 我的前世】\n"
                "你尚无前世落账于此——这一世还在走着。活好这一世，坐化结算时天道自会铭记。"
            )
        best = mine[0]
        lines = [
            "【飞升榜 · 我的前世】",
            f"最佳一世：第 {best['rank']} 名 · {best['name']}（{best['realm']}，分 {best['score']:.0f}）",
        ]
        lines.extend(AscensionEngine._row_line(e) for e in mine)
        return "\n".join(lines)

    @staticmethod
    def _search_text(entries: List[Dict[str, Any]], arg: str) -> str:
        exact = [e for e in entries if e["name"] == arg]
        pool = exact or [e for e in entries if arg in e["name"]]
        if not pool:
            return f"【飞升榜】榜上无道号「{arg}」之前世落账——或尚未坐化，或道号有误。"
        best = pool[0]
        lines = [
            f"【飞升榜 · 查名】{arg}",
            f"最佳：第 {best['rank']} 名 · {best['name']}（{best['realm']}，分 {best['score']:.0f}）",
        ]
        if len(pool) > 1:
            lines.append(f"（同名/含此名之前世共 {len(pool)} 条，以上为最高名次）")
        lines.extend(AscensionEngine._row_line(e) for e in pool[:5])
        return "\n".join(lines)

    @staticmethod
    def board_rows(
        viewer: Any = None,
        arg: Optional[str] = None,
        accounts: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """飞升榜行集（/飞升榜 ascend 键；与 panel_text 的分支选择同源）。空碑为 []。"""
        viewer_user_id = str(getattr(viewer, "user_id", "") or "") or None
        viewer_name = str(getattr(viewer, "name", "") or "")
        arg = str(arg or "").strip()
        if arg == "本纪元" or arg == "本季":
            from core.season import season_info

            current = int(season_info()["season_number"])
            return AscensionEngine.ranked(season=current, accounts=accounts)[:ASCEND_TOP_N]
        entries = AscensionEngine.collect_entries(accounts)
        if arg and (arg in ("我", "自己") or arg == viewer_name or (viewer_user_id and arg == viewer_user_id)):
            return [e for e in entries if viewer_user_id and e["user_id"] == viewer_user_id]
        if arg:
            exact = [e for e in entries if e["name"] == arg]
            pool = exact or [e for e in entries if arg in e["name"]]
            return pool[:5]
        return AscensionEngine.ranked(accounts=accounts)[:ASCEND_TOP_N]

    @staticmethod
    def panel_text(
        viewer: Any = None,
        arg: Optional[str] = None,
        accounts: Optional[List[Any]] = None,
    ) -> str:
        viewer_user_id = str(getattr(viewer, "user_id", "") or "") or None
        viewer_name = str(getattr(viewer, "name", "") or "")
        arg = str(arg or "").strip()

        if arg == "本纪元" or arg == "本季":
            from core.season import season_info

            current = int(season_info()["season_number"])
            rows = AscensionEngine.ranked(season=current, accounts=accounts)[:ASCEND_TOP_N]
            return AscensionEngine._board_text(
                rows,
                f"【飞升榜 · 第{current}纪元】（本纪元名次；全局名次用 /飞升榜 查）",
                "本纪元尚无前世落账——这一纪元的纪念碑还空着。",
            )

        entries = AscensionEngine.collect_entries(accounts)

        if arg and (arg in ("我", "自己") or arg == viewer_name or (viewer_user_id and arg == viewer_user_id)):
            return AscensionEngine._self_text(entries, viewer_user_id)

        if arg:
            return AscensionEngine._search_text(entries, arg)

        rows = entries[:ASCEND_TOP_N]
        text = AscensionEngine._board_text(
            rows,
            "【飞升榜 · 历世纪念碑】（只录已坐化落账之前世；现世人物看 /榜 六榜）",
            "飞升榜尚虚位以待——还没有道友的前世落账于此。活好这一世，坐化时自有天道铭记。",
        )
        return text + "\n查己世：/飞升榜 我 · 只看本纪元：/飞升榜 本纪元"
