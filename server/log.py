"""
结构化运行日志：裁决/指令/门禁/庇护，落盘 data/server.log
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from config import DATA_DIR

LOG_PATH = DATA_DIR / "server.log"


def log_event(
    kind: str,
    message: str = "",
    **fields: Any,
) -> None:
    """写一条 JSONL 日志。kind 建议：CMD / DECISION / GATE / PROTECT / QI / GOAL / SEASON / ERROR"""
    try:
        payload: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "kind": kind,
            "msg": message,
        }
        if fields:
            payload.update(fields)
        line = json.dumps(payload, ensure_ascii=False)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def tail(n: int = 20) -> str:
    """最近 n 行日志文本（调试用）"""
    if not LOG_PATH.exists():
        return ""
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[-n:])
