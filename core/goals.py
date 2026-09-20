"""
玩家世间目标系统。

既有契约（server/world.py · tests/test_phase1_rules.py）：
  GoalEngine.ensure_goals / add_opportunity / reject
  on_breakthrough_major / sync_progress / format_board / list_for

江湖因果扩展：sync_progress / ensure 时从因果账补齐与世界相关目标（扬名/复仇等）。
AI 只可解释，不直接发放数值。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from core.models import Character, CharacterStatus
from config import GOAL_MAX_ACTIVE, GOAL_SOURCES

# 展示用中文
KINDS = {
    "dao": "道途",
    "omen": "机缘",
    "bounty": "悬赏",
    "sect": "宗门",
    "season": "纪元",
    "newbie": "新入",
    "avenge": "复仇",
    "fame": "扬名",
    "survive": "避劫",
    "legacy": "道统",
}

# 不可拒绝的目标源
NON_REJECTABLE = {"dao"}

SOURCE_TEMPLATES = {
    "dao": ("问道长生", "稳固道基，勤修不辍，境界自会有进。"),
    "newbie": ("初入红尘", "先熟悉坊市与天道规则，活下去才有仙缘。"),
    "season": ("纪元大势", "本纪元周期有限，留意终局前的天象与榜单。"),
}


def _gid(source: str) -> str:
    return f"g_{source}_{uuid.uuid4().hex[:8]}"


def _active_goals(character: Character) -> List[Dict[str, Any]]:
    return [g for g in (character.goals or []) if g.get("status") == "active"]


def _has_source(character: Character, source: str) -> bool:
    return any(g.get("source") == source for g in _active_goals(character))


class GoalEngine:
    """六类源目标引擎 + 江湖因果投影"""

    @staticmethod
    def ensure_goals(character: Character) -> List[Dict[str, Any]]:
        if not character:
            return []
        if not isinstance(character.goals, list):
            character.goals = []
        now = time.time()
        # 过期清理（7 天）
        for g in character.goals:
            if g.get("status") == "active" and now - float(g.get("created_at") or 0) > 7 * 86400:
                g["status"] = "expired"

        def _add(source: str, title: str, detail: str, **extra) -> None:
            active_n = len([g for g in character.goals if g.get("status") == "active"])
            # 基础三类不限满额挤占；扩展类留出 add_opportunity 余量
            base = source in ("dao", "newbie", "season")
            limit = GOAL_MAX_ACTIVE if base else max(4, GOAL_MAX_ACTIVE - 2)
            if active_n >= limit:
                return
            if _has_source(character, source) and source not in ("omen",):
                return
            character.goals.append({
                "id": _gid(source),
                "source": source,
                "title": title,
                "detail": detail,
                "status": "active",
                "progress": 0,
                "created_at": now,
                **extra,
            })

        # 基础三类（测试硬约束）
        _add("dao", *SOURCE_TEMPLATES["dao"])
        _add("newbie", *SOURCE_TEMPLATES["newbie"])
        _add("season", *SOURCE_TEMPLATES["season"])

        active_n = len([g for g in character.goals if g.get("status") == "active"])
        if active_n < 5:
            if character.sect:
                _add("sect", f"效力【{character.sect}】", "完成日环、上交贡献或除凶，为宗门立功。", target=character.sect)
            else:
                _add("sect", "寻一门庭", "散修无依，可择正魔宗门拜入。")

        if character.karma.is_blood_marked():
            _add("avenge", "血煞缠身", "身负血煞，宜避祸或主动除凶。")

        # 江湖投影：近日因果（不占满，给秘境机缘留位）
        try:
            import core.jianghu as jianghu

            active_n = len([g for g in character.goals if g.get("status") == "active"])
            if active_n < 5:
                mine = jianghu.project_related(character.id, limit=6)
                if not _has_source(character, "fame"):
                    _add(
                        "fame",
                        "扬名立万",
                        "江湖多事，宜在斗法/宗门/除凶中留下名号。",
                        progress=min(2, len(mine)),
                    )
            active_n = len([g for g in character.goals if g.get("status") == "active"])
            if active_n < GOAL_MAX_ACTIVE:
                for e in jianghu.list_recent(limit=6):
                    if "夺" in (e.get("summary") or "") or e.get("kind") in ("npc_agenda",):
                        if not _has_source(character, "omen"):
                            _add("omen", "机缘未远", f"坊间传闻：{(e.get('summary') or '')[:60]}", ref=e.get("id", ""))
                        break
        except Exception:
            pass

        return character.goals

    @staticmethod
    def add_opportunity(character: Character, title: str, detail: str) -> Dict[str, Any]:
        """外部事件挂接机缘目标（秘境等）。机缘类允许超基础配额，上限仍为 GOAL_MAX_ACTIVE。"""
        GoalEngine.ensure_goals(character)
        # 若 ensure 已写入 omen（江湖传闻），先降其优先级为 superseded，保证外部机缘可挂接
        if len(_active_goals(character)) >= GOAL_MAX_ACTIVE:
            for g in character.goals or []:
                if g.get("status") == "active" and g.get("source") == "omen":
                    g["status"] = "superseded"
                    break
        if len(_active_goals(character)) >= GOAL_MAX_ACTIVE:
            return {"success": False, "error": "世间目标已满，可先 /目标 处理。"}
        goal = {
            "id": _gid("omen"),
            "source": "omen",
            "title": str(title)[:40],
            "detail": str(detail)[:200],
            "status": "active",
            "progress": 0,
            "created_at": time.time(),
        }
        character.goals.append(goal)
        return {"success": True, "goal": goal}

    @staticmethod
    def reject(character: Character, goal_id: str) -> Dict[str, Any]:
        for g in character.goals or []:
            if g.get("id") != goal_id:
                continue
            if g.get("source") in NON_REJECTABLE:
                return {"success": False, "error": "道途目标不可弃。"}
            if g.get("status") != "active":
                return {"success": False, "error": "该目标非进行中。"}
            g["status"] = "rejected"
            g["done_at"] = time.time()
            return {"success": True, "goal": g, "message": f"已放下【{g.get('title')}】。"}
        return {"success": False, "error": "未找到该目标。"}

    @staticmethod
    def complete(character: Character, goal_id: str, reason: str = "") -> Optional[Dict[str, Any]]:
        for g in character.goals or []:
            if g.get("id") == goal_id and g.get("status") == "active":
                g["status"] = "done"
                g["done_at"] = time.time()
                g["done_reason"] = reason[:120]
                return g
        return None

    @staticmethod
    def on_breakthrough_major(character: Character) -> None:
        """大境界突破：刷新道途/纪元目标"""
        GoalEngine.ensure_goals(character)
        now = time.time()
        for g in character.goals or []:
            if g.get("status") == "active" and g.get("source") in ("dao", "season"):
                g["status"] = "done"
                g["done_at"] = now
                g["done_reason"] = f"突破至 {character.realm.name}"
        # 重新生成
        for g in character.goals or []:
            if g.get("status") == "active" and g.get("source") in ("dao", "season"):
                g["status"] = "superseded"
        GoalEngine.ensure_goals(character)

    @staticmethod
    def sync_progress(character: Character) -> List[Dict[str, Any]]:
        """按规则状态刷新进度；尝试完成。返回本次完成列表。"""
        GoalEngine.ensure_goals(character)
        completed: List[Dict[str, Any]] = []
        now = time.time()
        for g in list(character.goals or []):
            if g.get("status") != "active":
                continue
            src = g.get("source")
            # 道途：有修为增长则进度缓慢前进
            if src == "dao":
                try:
                    g["progress"] = int(character.realm.tier)
                except Exception:
                    pass
            if src == "fame":
                try:
                    import core.jianghu as jianghu
                    mine = [
                        e for e in jianghu.project_related(character.id, limit=10)
                        if character.id in (e.get("actor_ids") or [])
                    ]
                    g["progress"] = min(3, len(mine))
                    if len(mine) >= 2:
                        hit = GoalEngine.complete(character, g["id"], reason="江湖已有名号痕迹")
                        if hit:
                            completed.append(hit)
                except Exception:
                    pass
            if src == "survive" and not character.karma.is_blood_marked():
                hit = GoalEngine.complete(character, g["id"], reason="血煞已消")
                if hit:
                    completed.append(hit)
            if src == "newbie":
                try:
                    if not character.is_newbie_protected(now):
                        # 入世已久仍在则进度打满但不强制完成
                        g["progress"] = 1
                except Exception:
                    pass
        return completed

    @staticmethod
    def list_for(character: Character) -> List[Dict[str, Any]]:
        return [g for g in (character.goals or []) if g.get("status") == "active"]

    @staticmethod
    def format_board(character: Character) -> str:
        items = GoalEngine.list_for(character)
        if not items:
            return "暂无世间目标。可 /世情 观察江湖，或 /近况 查看。"
        lines = [f"=== 世间目标（{len(items)}/{GOAL_MAX_ACTIVE}）· {character.name} ==="]
        for g in items:
            kn = KINDS.get(g.get("source", ""), g.get("source", ""))
            prog = g.get("progress") or 0
            lines.append(f"  · 【{kn}】{g.get('title')} — {g.get('detail','')}（进度 {prog}）")
        return "\n".join(lines)


# ---------- 兼容 briefing / CLI 的函数式接口 ----------

def ensure_goals(character: Character) -> List[Dict[str, Any]]:
    return GoalEngine.ensure_goals(character)


def format_goals(character: Character) -> str:
    return GoalEngine.format_board(character)


def evaluate_and_complete(character: Character) -> List[Dict[str, Any]]:
    return GoalEngine.sync_progress(character)


def get_goals(character_id: str) -> List[Dict[str, Any]]:
    """按 id 读目标（近况等场景）。"""
    try:
        from storage.db import CharacterRepository
        c = CharacterRepository.get_by_id(character_id)
        if not c:
            return []
        return list(c.goals or [])
    except Exception:
        return []
