"""
世界频道：全服大事件即时消息 + GM 公告
规则权威写入；AI 不改数值。限流防噪。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from config import (
    WORLD_MSG_MAX,
    WORLD_MSG_TTL_H,
    WORLD_MSG_PER_MIN,
    GM_TOKEN,
)


class WorldMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    channel: str = "world"  # world | gm | system
    level: str = "info"     # info | major | epic | gm
    kind: str = "event"
    text: str = ""
    actor: str = ""
    location: str = ""
    season: int = 0
    ts: float = 0.0

    def board_line(self) -> str:
        tag = {
            "info": "",
            "major": "★",
            "epic": "★★",
            "gm": "【公告】",
            "system": "〔系统〕",
        }.get(self.level, "")
        prefix = f"{tag}" if tag else ""
        loc = f" @ {self.location}" if self.location else ""
        return f"{prefix}{self.text}{loc}"


# 60s 去重 + 每分钟限流（进程内即可，LAN 单进程）
_recent_keys: List[tuple] = []  # (kind+actor, ts)
_min_window_start = 0.0
_min_count = 0


def _allow(kind: str, actor: str, now: float) -> bool:
    global _min_window_start, _min_count, _recent_keys
    key = f"{kind}|{actor}"
    # 去重
    _recent_keys = [(k, t) for k, t in _recent_keys if now - t < 60.0]
    if any(k == key for k, _t in _recent_keys):
        return False
    # 限流
    if now - _min_window_start >= 60.0:
        _min_window_start = now
        _min_count = 0
    if _min_count >= WORLD_MSG_PER_MIN:
        return False
    _recent_keys.append((key, now))
    _min_count += 1
    return True


def _season_no() -> int:
    try:
        from core.season import season_info

        return int(season_info().get("season_number") or 0)
    except Exception:
        return 0


class WorldChannel:
    @staticmethod
    def post(
        kind: str,
        text: str,
        *,
        level: str = "info",
        channel: str = "world",
        actor: str = "",
        location: str = "",
        now: Optional[float] = None,
        skip_limit: bool = False,
    ) -> Optional[WorldMessage]:
        t = now if now is not None else time.time()
        text = (text or "").strip()[:160]
        if not text:
            return None
        if channel == "world" and not skip_limit:
            if not _allow(kind, actor, t):
                return None
        msg = WorldMessage(
            channel=channel,
            level=level,
            kind=kind,
            text=text,
            actor=actor[:40],
            location=location[:40],
            season=_season_no(),
            ts=t,
        )
        try:
            from storage.db import WorldMessageRepository

            WorldMessageRepository.save(msg)
            WorldMessageRepository.prune(WORLD_MSG_MAX, WORLD_MSG_TTL_H)
        except Exception:
            pass
        return msg

    @staticmethod
    def recent(
        limit: int = 20,
        since_ts: float = 0.0,
        channels: Optional[Sequence[str]] = None,
    ) -> List[WorldMessage]:
        try:
            from storage.db import WorldMessageRepository

            return WorldMessageRepository.list_recent(
                limit=limit, since_ts=since_ts, channels=channels
            )
        except Exception:
            return []

    @staticmethod
    def format_board(limit: int = 15) -> str:
        rows = WorldChannel.recent(limit=limit)
        if not rows:
            return "【世界频道】暂无消息。大事件发生时会在此播报。"
        lines = [f"【世界频道】最近 {len(rows)} 条："]
        for m in reversed(rows):  # 旧→新
            lines.append(m.board_line())
        return "\n".join(lines)

    @staticmethod
    def format_announcements(limit: int = 10) -> str:
        rows = WorldChannel.recent(limit=limit, channels=("gm", "system"))
        if not rows:
            return "【公告】暂无系统公告。"
        lines = ["【公告】"]
        for m in reversed(rows):
            lines.append(m.board_line())
        return "\n".join(lines)


def check_gm_token(token: str) -> bool:
    import config as _cfg

    secret = (getattr(_cfg, "GM_TOKEN", None) or GM_TOKEN or "").strip()
    if not secret:
        return False
    # 常量时间比较（长度不等直接 False）
    a = (token or "").encode("utf-8")
    b = secret.encode("utf-8")
    if len(a) != len(b):
        return False
    diff = 0
    for x, y in zip(a, b):
        diff |= x ^ y
    return diff == 0


def post_gm(text: str, now: Optional[float] = None) -> Optional[WorldMessage]:
    return WorldChannel.post(
        "gm",
        text,
        level="gm",
        channel="gm",
        actor="GM",
        now=now,
        skip_limit=True,
    )


def post_system(kind: str, text: str, now: Optional[float] = None) -> Optional[WorldMessage]:
    return WorldChannel.post(
        kind,
        text,
        level="system",
        channel="system",
        actor="system",
        now=now,
        skip_limit=True,
    )
