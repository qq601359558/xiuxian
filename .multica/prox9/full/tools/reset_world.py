"""
重置世界：清测试残留，保留可选备份，重新播种正式阵容
用法：
  python tools/reset_world.py           # 备份后清档并播种
  python tools/reset_world.py --keep-roster
  python tools/reset_world.py --force   # 不询问
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DB_PATH, DATA_DIR
from storage.db import init_db, CharacterRepository, ChronicleRepository
from core.npc_roster import seed_roster
from core.models import CharacterStatus
from core.npc_mind import _is_npc


def backup_db() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        return DB_PATH
    ts = time.strftime("%Y%m%d_%H%M%S")
    dest = DATA_DIR / f"tiandao_backup_{ts}.db"
    shutil.copy2(DB_PATH, dest)
    return dest


def reset(keep_roster: bool = True) -> dict:
    """删除 DB 后重建并播种。返回统计。"""
    init_db()
    # 简单方案：直接删库重来（备份已做）
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    stats = seed_roster()
    # 再补一张血令
    try:
        from core.bounty import Bounty, BountyStatus
        from storage.db import BountyRepository
        from config import BOUNTY_ACTIVE_HOURS
        target = CharacterRepository.get_by_name("血刀老祖")
        issuer = CharacterRepository.get_by_name("云鹤道人")
        if target and issuer and not BountyRepository.list_all():
            BountyRepository.save(Bounty(
                issuer_id=issuer.id,
                issuer_name=issuer.name,
                target_id=target.id,
                target_name=target.name,
                reward=200,
                reason="屠戮落霞散修满门，天理难容",
                status=BountyStatus.OPEN,
                created_at=time.time(),
                expires_at=time.time() + BOUNTY_ACTIVE_HOURS * 3600.0,
            ))
            stats["bounty"] = 1
    except Exception as e:
        stats["bounty_error"] = str(e)

    alive = CharacterRepository.list_all_alive()
    stats["alive"] = len(alive)
    stats["npcs"] = sum(1 for c in alive if _is_npc(c))
    stats["players"] = sum(1 for c in alive if not _is_npc(c))
    return stats


def main():
    ap = argparse.ArgumentParser(description="重置天道世界存档")
    ap.add_argument("--force", action="store_true", help="不询问直接重置")
    ap.add_argument("--no-backup", action="store_true", help="不备份")
    args = ap.parse_args()

    if not args.force:
        ans = input("将备份并清空当前世界存档，确认？(y/N) ").strip().lower()
        if ans != "y":
            print("已取消。")
            return

    if not args.no_backup:
        b = backup_db()
        print(f"已备份 → {b}")

    stats = reset()
    print("重置完成：")
    print(f"  阵容播种 created={stats.get('created')} skipped={stats.get('skipped')}")
    print(f"  存活角色 {stats.get('alive')}（NPC {stats.get('npcs')} / 玩家 {stats.get('players')}）")
    if stats.get("bounty"):
        print("  已挂示例血令（血刀老祖）")
    print("可重新启动 server/start.py 与网页客户端。")


if __name__ == "__main__":
    main()
