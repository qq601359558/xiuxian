"""
AI 提案审计日志（JSONL）
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import AUDIT_LOG_PATH


def write_audit(record: Dict[str, Any]) -> None:
    try:
        path = Path(AUDIT_LOG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(record)
        rec.setdefault("ts", time.time())
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # 审计失败不阻断游戏
        pass


def read_recent_audit(limit: int = 50) -> List[Dict[str, Any]]:
    path = Path(AUDIT_LOG_PATH)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
