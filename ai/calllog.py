"""
AI 调用日志：入参/出参/状态/耗时，JSONL 落盘，供排查
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import DATA_DIR

AI_LOG_PATH = DATA_DIR / "ai_calls.jsonl"
MAX_PROMPT_CHARS = 4000
MAX_RESP_CHARS = 4000


def log_ai_call(
    *,
    kind: str,
    channel: str,
    url: str = "",
    model: str = "",
    status: str = "ok",
    http_status: Optional[int] = None,
    prompt: str = "",
    response: Any = None,
    raw_text: str = "",
    error: str = "",
    duration_ms: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        rec: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "kind": kind,
            "channel": channel,
            "url": url,
            "model": model,
            "status": status,
            "http_status": http_status,
            "duration_ms": duration_ms,
            "prompt": (prompt or "")[:MAX_PROMPT_CHARS],
            "prompt_len": len(prompt or ""),
            "raw_text": (raw_text or "")[:MAX_RESP_CHARS],
            "error": (error or "")[:500],
        }
        if response is None:
            rec["response"] = None
        elif isinstance(response, (dict, list)):
            s = json.dumps(response, ensure_ascii=False, default=str)
            if len(s) > MAX_RESP_CHARS:
                rec["response"] = s[:MAX_RESP_CHARS] + "…(截断)"
            else:
                rec["response"] = response
        else:
            rec["response"] = str(response)[:MAX_RESP_CHARS]
        if extra:
            rec["extra"] = extra
        AI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AI_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # 环形截断：最多 800 行
        try:
            lines = AI_LOG_PATH.read_text(encoding="utf-8").splitlines()
            if len(lines) > 800:
                AI_LOG_PATH.write_text("\n".join(lines[-800:]) + "\n", encoding="utf-8")
        except Exception:
            pass
    except Exception:
        pass


def tail_ai_calls(n: int = 50) -> List[Dict[str, Any]]:
    if not AI_LOG_PATH.exists():
        return []
    lines = AI_LOG_PATH.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    out.reverse()
    return out
