"""
场景级 AI 配额：防单场景刷爆预算；超限返回可展示原因。
默认进程内计数；可选写 world_state 做跨请求共享。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

# scene_id -> 每窗口最大次数
DEFAULT_PER_MINUTE = 30
# 场景可覆盖
SCENE_LIMITS = {
    "npc_agenda": 20,
    "npc_talk": 40,
    "npc_proactive": 10,
    "combat": 25,
    "world_event": 15,
}

DEFAULT_WINDOW_SECONDS = 60.0
# 日预算（软上限，进程内；0=不启用日预算）
DEFAULT_DAILY_BUDGET = 2000


class QuotaLimiter:
    def __init__(self, window_seconds: float = DEFAULT_WINDOW_SECONDS):
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._day: Optional[str] = None
        self._day_count = 0
        self._daily_budget = DEFAULT_DAILY_BUDGET

    def _limit_for(self, scene_id: str) -> int:
        return int(SCENE_LIMITS.get(scene_id, DEFAULT_PER_MINUTE))

    def _day_key(self, now: float) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(now))

    def check(self, scene_id: str, *, now: Optional[float] = None, cost: int = 1) -> Tuple[bool, str]:
        """返回 (allowed, reason)。reason 空串表示放行。"""
        t = now or time.time()
        day = self._day_key(t)
        if day != self._day:
            self._day = day
            self._day_count = 0
        if self._daily_budget > 0 and self._day_count + cost > self._daily_budget:
            return False, f"天道日预算已尽（{self._day_count}/{self._daily_budget}），请明日再来或减少 AI 依赖"
        q = self._hits[scene_id]
        while q and t - q[0] > self.window_seconds:
            q.popleft()
        limit = self._limit_for(scene_id)
        if len(q) + cost > limit:
            return False, f"场景【{scene_id}】瞬时调用过于频繁（{limit}/{int(self.window_seconds)}s）"
        return True, ""

    def hit(self, scene_id: str, *, now: Optional[float] = None, cost: int = 1) -> None:
        t = now or time.time()
        day = self._day_key(t)
        if day != self._day:
            self._day = day
            self._day_count = 0
        self._hits[scene_id].append(t)
        self._day_count += cost

    def allow(self, scene_id: str, *, now: Optional[float] = None, cost: int = 1) -> Tuple[bool, str]:
        ok, reason = self.check(scene_id, now=now, cost=cost)
        if ok:
            self.hit(scene_id, now=now, cost=cost)
        return ok, reason

    def reset_for_tests(self) -> None:
        self._hits.clear()
        self._day = None
        self._day_count = 0


# 单例
quota = QuotaLimiter()
