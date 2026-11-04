"""
账户死亡资金归集 · 迁移演练脚本（account-death-rework §5 / 评审 M4、T15）。

只跑演练库，绝不碰真实存档：
- 默认 --data-dir 未给时，在系统临时目录新建演练数据目录；
- 显式 --data-dir 若解析后等于仓库真实 data/ 目录，直接拒绝退出；
- 演练库为空时以 --seed-demo（默认开）植入三类演练数据：
  已死未转世行（待补扫）、旧寄售单（可回填 1 单＋不可考 1 单）、已转世账户 1 个；
- 迁移本身只做三件事：已死未转世行补扫（sweep，ref 幂等）、旧单回填
  seller_user_id、不可考旧单列入封存清单（不删除、不改价、不成交）；
- 已转世账户仅计数、不估算金额（旧行已被覆写，金额已不可考，见 spec §5.4）。

用法：
  python tools/migrate_account_death.py [--data-dir DIR] [--no-seed-demo]
报告打印到 stdout（人类可读，含三类计数与封存清单）。
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import CharacterStatus

REAL_DATA_DIR = (ROOT / "data").resolve()


def _fail(msg: str) -> int:
    print(f"拒绝执行：{msg}", file=sys.stderr)
    return 2


def _seed_demo() -> dict:
    """植入演练数据（仅演练库）。返回种子标识，供报告核对。"""
    from storage.db import (
        CharacterRepository,
        LegacyRepository,
        MarketListingRepository,
    )
    from core.clock import WorldClock
    from core.models import CharacterStatus as _CS
    from core.market import MarketListing, ListingStatus

    # 1）已死未转世行：随身 300＋寄存 50，death_settled 已真、钱包无流水
    dead = WorldClock.create_new_character("demo_dead_01", "演练死者")
    dead.spirit_stones = 300
    dead.vault_stones = 50
    dead.status = _CS.DEAD
    dead.death_settled = True
    CharacterRepository.save(dead)
    # 2）已转世账户：旧世已结算、新角存活——仅计数，不估金额
    old = WorldClock.create_new_character("demo_reborn_01", "演练旧世")
    old.status = _CS.DEAD
    old.death_settled = True
    CharacterRepository.save(old)
    acc = LegacyRepository.get_or_create("demo_reborn_01")
    acc.total_lives = 1
    LegacyRepository.save(acc)
    new = WorldClock.create_new_character("demo_reborn_01", "演练新世")
    CharacterRepository.save(new)
    # 3）旧寄售单：可回填（seller_id 命中死行）1 单；不可考（seller_id 查无此人）1 单
    MarketListingRepository.save(MarketListing(
        seller_id=dead.id, seller_user_id="", seller_name=dead.name,
        item_name="百年灵芝", kind="material", price=250,
        status=ListingStatus.OPEN, created_at=time.time(),
    ))
    MarketListingRepository.save(MarketListing(
        seller_id="ghost_seller_id", seller_user_id="", seller_name="查无此人道号",
        item_name="百年灵芝", kind="material", price=200,
        status=ListingStatus.OPEN, created_at=time.time(),
    ))
    return {"dead_id": dead.id, "reborn_uid": "demo_reborn_01"}


def run_migration(data_dir: Path, seed_demo: bool) -> dict:
    """在 data_dir 指向的演练库上执行迁移，返回报告 dict（并由调用方打印）。"""
    import storage.db as _db

    data_dir.mkdir(parents=True, exist_ok=True)
    _db.DB_PATH = data_dir / "tiandao.db"
    from storage.db import (
        CharacterRepository,
        LegacyRepository,
        MarketListingRepository,
        init_db,
    )
    from core.wallet import sweep_death_funds

    init_db()
    if seed_demo:
        from storage.db import CharacterRepository as _CR

        if _CR.get_by_user_id("demo_dead_01") is None:
            _seed_demo()

    # ① 已死未转世行补扫：death_settled 已真且钱包无 death_sweep 流水。
    # 死行枚举：直接读 characters 全量 data_json（仓储无全量列表接口）。
    swept_rows = 0
    swept_amount = 0
    import sqlite3

    conn = sqlite3.connect(str(_db.DB_PATH))
    try:
        rows = conn.execute("SELECT data_json FROM characters").fetchall()
    finally:
        conn.close()
    from core.models import Character as _Char

    for (blob,) in rows:
        try:
            char = _Char.model_validate_json(blob)
        except Exception:
            continue
        if char.status != CharacterStatus.DEAD and not char.lifespan.is_dead():
            continue
        if not char.death_settled:
            continue
        account = LegacyRepository.get_or_create(char.user_id)
        if any(e.ref == char.id for e in account.wallet_ledger):
            continue
        before = account.wallet_stones
        details = sweep_death_funds(char, account)
        LegacyRepository.save(account)
        CharacterRepository.save(char)
        swept_rows += 1
        swept_amount += int(account.wallet_stones - before)

    # ② 旧寄售单回填：seller_user_id 为空的 OPEN 单，seller_id 命中现世／死行即回填
    backfilled = 0
    sealed = []
    for listing in MarketListingRepository.list_all():
        if not listing.is_open() or listing.seller_user_id:
            continue
        target = None
        if listing.seller_id:
            target = CharacterRepository.get_by_id(listing.seller_id)
        if target is not None and target.user_id:
            listing.seller_user_id = target.user_id
            MarketListingRepository.save(listing)
            backfilled += 1
        else:
            sealed.append({
                "id": listing.id, "item": listing.item_name,
                "price": listing.price, "seller_name": listing.seller_name,
            })

    # ③ 已转世账户仅计数：total_lives／past_lives 非零且现世角色存活
    reborn_count = 0
    for account in LegacyRepository.list_all():
        if not (account.total_lives or account.past_lives):
            continue
        cur = CharacterRepository.get_by_user_id(account.user_id)
        if cur is not None and cur.status != CharacterStatus.DEAD and not cur.lifespan.is_dead():
            reborn_count += 1

    return {
        "data_dir": str(data_dir),
        "swept_rows": swept_rows,
        "swept_amount": swept_amount,
        "backfilled_listings": backfilled,
        "sealed_listings": sealed,
        "reborn_accounts": reborn_count,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="账户死亡迁移演练（只跑演练库）")
    ap.add_argument("--data-dir", default="", help="演练数据目录（缺省为系统临时目录）")
    ap.add_argument("--no-seed-demo", action="store_true", help="不对空演练库植入演示数据")
    args = ap.parse_args(argv)

    if args.data_dir:
        data_dir = Path(args.data_dir).expanduser().resolve()
        if data_dir == REAL_DATA_DIR:
            return _fail("该目录就是仓库真实 data/ 目录，演练脚本不得在真实存档上运行。")
        if (data_dir / "tiandao.db").resolve() == (REAL_DATA_DIR / "tiandao.db").resolve():
            return _fail("该路径就是真实存档 tiandao.db，演练脚本不得在真实存档上运行。")
    else:
        data_dir = Path(tempfile.mkdtemp(prefix="tiandao-migrate-demo-"))

    report = run_migration(data_dir, seed_demo=not args.no_seed_demo)
    print(f"迁移演练报告（演练库：{report['data_dir']}，真实存档未动）")
    print(f"已补扫死行：{report['swept_rows']} 行，归集金额：{report['swept_amount']} 灵石")
    print(f"回填寄售单：{report['backfilled_listings']} 单")
    print(f"不可考封存单：{len(report['sealed_listings'])} 单")
    for s in report["sealed_listings"]:
        print(f"  · 封存：单号 {s['id']}【{s['item']}】标价 {s['price']} 灵石，卖家 {s['seller_name']}（不删除、不改价、暂封成交）")
    print(f"已转世账户数：{report['reborn_accounts']} 个（仅计数，不估算金额——旧行已被覆写，金额不可考，不得凭空补发，见 spec §5.4）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
