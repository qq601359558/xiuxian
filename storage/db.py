"""
SQLite 本地轻量持久化存储 (严格存放在 D 盘 data 目录下)
"""
import logging
import sqlite3
import json
import time
from typing import Optional, List, Dict
from config import DB_PATH
from core.models import Character

_log = logging.getLogger(__name__)
from core.legacy import LegacyAccount
from core.bounty import Bounty, KarmaLink, BountyStatus
from core.market import MarketListing, ListingStatus
from core.trade import AuctionLot, AuctionStatus


def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. 修士表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id TEXT PRIMARY KEY,
        user_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        data_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    """)

    # 2. 世界大事记与因果总账
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS world_chronicle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        actor_name TEXT NOT NULL,
        summary TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    """)

    # 3. 账号道统元进度（跨一世）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS player_legacy (
        user_id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    );
    """)

    # 4. 悬赏告示榜
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bounties (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        status TEXT NOT NULL,
        target_id TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    """)

    # 5. 因果关系链
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS karma_links (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    """)

    # 6. 坊市寄售挂单
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS market_listings (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        status TEXT NOT NULL,
        seller_id TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auction_lots (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        status TEXT NOT NULL,
        seller_id TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    """)

    # 7. 事件账（角色级长期记忆，供 AI 检索）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_ledger (
        event_id TEXT PRIMARY KEY,
        ts REAL NOT NULL,
        type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        actor_name TEXT NOT NULL,
        target_id TEXT,
        target_name TEXT,
        location TEXT,
        summary TEXT NOT NULL,
        effects_digest TEXT,
        chain_id TEXT,
        refs_json TEXT
    );
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ev_actor ON event_ledger(actor_id, ts DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ev_target ON event_ledger(target_id, ts DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ev_loc ON event_ledger(location, ts DESC)"
    )

    # 8. 登录会话（服务器重启后仍可续玩）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auth_sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        character_id TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_seen REAL NOT NULL
    );
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_uid ON auth_sessions(user_id)"
    )

    # 9. 账号（用户名+密码）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_login REAL
    );
    """)
    # 10. AI 生成物名称（去重排除集）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS generated_names (
        name TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        data_json TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    """)

    # 8. 角色小传（L1 摘要，压上下文用）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS character_bios (
        character_id TEXT PRIMARY KEY,
        bio_text TEXT NOT NULL,
        traits_json TEXT,
        updated_at REAL NOT NULL
    );
    """)

    # 9. NPC 议程
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS npc_agendas (
        npc_id TEXT PRIMARY KEY,
        npc_name TEXT NOT NULL,
        agenda_type TEXT NOT NULL,
        target_hint TEXT,
        note TEXT,
        state TEXT NOT NULL DEFAULT 'active',
        last_tick REAL DEFAULT 0,
        progress INTEGER DEFAULT 0,
        extra_json TEXT
    );
    """)

    # 10. NPC 心智：性格 + 对玩家态度
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS npc_minds (
        npc_id TEXT PRIMARY KEY,
        personality TEXT NOT NULL,
        traits_json TEXT,
        attitudes_json TEXT,
        updated_at REAL NOT NULL
    );
    """)

    # 11. 世界运行态 KV（秘境冷却/探索链/AI 预算/通道健康）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS world_state (
        key TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    );
    """)

    # 12. 世界频道消息
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS world_messages (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        channel TEXT NOT NULL,
        level TEXT NOT NULL,
        ts REAL NOT NULL
    );
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_wmsg_ts ON world_messages(ts DESC)"
    )

    # 13. 江湖因果账（唯一事实源投影；规则写，AI 只附叙事）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jianghu_events (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        data_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        visibility TEXT NOT NULL DEFAULT 'public',
        location TEXT DEFAULT ''
    );
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_jh_ts ON jianghu_events(created_at DESC)"
    )

    conn.commit()
    conn.close()


class WorldMessageRepository:
    """世界频道仓储"""

    @staticmethod
    def save(msg) -> None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO world_messages (id, data_json, channel, level, ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json;
            """,
            (msg.id, msg.model_dump_json(), msg.channel, msg.level, msg.ts),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def list_recent(limit: int = 20, since_ts: float = 0.0, channels=None):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # channel 过滤下推到 SQL，避免 LIMIT 后再滤导致公告被 world 挤掉
        if channels:
            marks = ",".join("?" for _ in channels)
            cursor.execute(
                f"SELECT data_json FROM world_messages WHERE ts > ? AND channel IN ({marks}) "
                f"ORDER BY ts DESC LIMIT ?",
                (float(since_ts or 0.0), *channels, max(1, int(limit))),
            )
        else:
            cursor.execute(
                "SELECT data_json FROM world_messages WHERE ts > ? ORDER BY ts DESC LIMIT ?",
                (float(since_ts or 0.0), max(1, int(limit))),
            )
        rows = cursor.fetchall()
        conn.close()
        from core.world_channel import WorldMessage

        msgs = [WorldMessage.model_validate_json(r[0]) for r in rows]
        msgs.sort(key=lambda m: m.ts)
        return msgs

    @staticmethod
    def prune(keep: int = 200, ttl_hours: float = 2.0) -> int:
        import time as _t

        now = _t.time()
        cutoff = now - ttl_hours * 3600.0
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM world_messages WHERE ts < ?", (cutoff,))
        deleted_ttl = cursor.rowcount or 0
        cursor.execute(
            """
            DELETE FROM world_messages WHERE id NOT IN (
                SELECT id FROM world_messages ORDER BY ts DESC LIMIT ?
            )
            """,
            (max(10, keep),),
        )
        deleted_cap = cursor.rowcount or 0
        conn.commit()
        conn.close()
        return deleted_ttl + deleted_cap

    @staticmethod
    def count_since(ts: float, levels=None) -> int:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data_json FROM world_messages WHERE ts > ?", (float(ts or 0.0),)
        )
        rows = cursor.fetchall()
        conn.close()
        if not levels:
            return len(rows)
        from core.world_channel import WorldMessage

        allow = set(levels)
        n = 0
        for r in rows:
            try:
                m = WorldMessage.model_validate_json(r[0])
                if m.level in allow:
                    n += 1
            except Exception:
                continue
        return n


class WorldStateRepository:
    """进程无关的世界运行态（重启不失忆）"""

    @staticmethod
    def get(key: str, default=None):
        import json

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM world_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return default

    @staticmethod
    def set(key: str, value) -> None:
        import json

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO world_state (key, data_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = excluded.updated_at;
            """,
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def delete(key: str) -> None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM world_state WHERE key = ?", (key,))
        conn.commit()
        conn.close()


def _parse_character(raw: Optional[str]) -> Optional[Character]:
    """解析角色 JSON；坏数据跳过而不是拖垮整个列表查询。"""
    if not raw:
        return None
    try:
        return Character.model_validate_json(raw)
    except Exception as e:
        _log.warning("skip invalid character row: %s", e)
        return None


class CharacterRepository:
    """修士数据访问仓储"""

    @staticmethod
    def save(character: Character):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = time.time()
        character.version = getattr(character, "version", 0) + 1
        data_json = character.model_dump_json()

        cursor.execute("""
        INSERT INTO characters (id, user_id, name, status, data_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            id = excluded.id,
            name = excluded.name,
            status = excluded.status,
            data_json = excluded.data_json,
            updated_at = excluded.updated_at;
        """, (character.id, character.user_id, character.name, character.status.value, data_json, now, now))

        conn.commit()
        conn.close()

    @staticmethod
    def get_by_user_id(user_id: str) -> Optional[Character]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM characters WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return _parse_character(row[0])
        return None

    @staticmethod
    def get_by_name(name: str) -> Optional[Character]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM characters WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return _parse_character(row[0])
        return None

    @staticmethod
    def get_by_id(char_id: str) -> Optional[Character]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM characters WHERE id = ?", (char_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return _parse_character(row[0])
        return None

    @staticmethod
    def find_alive_by_name(name: str) -> Optional[Character]:
        """按道号找在世角色；唯一命中优先，否则同名取首个在世。"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data_json FROM characters WHERE name = ? AND status != 'DEAD'",
            (name,),
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return None
        return _parse_character(rows[0][0])

    @staticmethod
    def list_all_alive() -> List[Character]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM characters WHERE status != 'DEAD'")
        rows = cursor.fetchall()
        conn.close()
        out: List[Character] = []
        for r in rows:
            c = _parse_character(r[0])
            if c is not None:
                out.append(c)
        return out


class LegacyRepository:
    """账号道统元进度仓储"""

    @staticmethod
    def save(account: LegacyAccount):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO player_legacy (user_id, data_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            data_json = excluded.data_json,
            updated_at = excluded.updated_at;
        """, (account.user_id, account.model_dump_json(), time.time()))
        conn.commit()
        conn.close()

    @staticmethod
    def get_or_create(user_id: str) -> LegacyAccount:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM player_legacy WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return LegacyAccount.model_validate_json(row[0])
        account = LegacyAccount(user_id=user_id)
        LegacyRepository.save(account)
        return account


class BountyRepository:
    """悬赏告示仓储"""

    @staticmethod
    def save(bounty: Bounty):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO bounties (id, data_json, status, target_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            data_json = excluded.data_json,
            status = excluded.status,
            target_id = excluded.target_id;
        """, (
            bounty.id,
            bounty.model_dump_json(),
            bounty.status.value,
            bounty.target_id,
            bounty.created_at,
        ))
        conn.commit()
        conn.close()

    @staticmethod
    def save_many(bounties: List[Bounty]):
        for b in bounties:
            BountyRepository.save(b)

    @staticmethod
    def list_all() -> List[Bounty]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM bounties ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [Bounty.model_validate_json(r[0]) for r in rows]

    @staticmethod
    def list_open_for_target(target_id: str) -> List[Bounty]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data_json FROM bounties WHERE target_id = ? AND status IN ('OPEN','CLAIMED')",
            (target_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [Bounty.model_validate_json(r[0]) for r in rows]


class KarmaLinkRepository:
    """因果链仓储"""

    @staticmethod
    def save(link: KarmaLink):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO karma_links (id, data_json, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json;
        """, (link.id, link.model_dump_json(), link.created_at))
        conn.commit()
        conn.close()

    @staticmethod
    def list_all() -> List[KarmaLink]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM karma_links ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [KarmaLink.model_validate_json(r[0]) for r in rows]


class MarketListingRepository:
    """坊市寄售仓储"""

    @staticmethod
    def save(listing: MarketListing):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO market_listings (id, data_json, status, seller_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            data_json = excluded.data_json,
            status = excluded.status;
        """, (
            listing.id,
            listing.model_dump_json(),
            listing.status.value,
            listing.seller_id,
            listing.created_at,
        ))
        conn.commit()
        conn.close()

    @staticmethod
    def list_all() -> List[MarketListing]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM market_listings ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [MarketListing.model_validate_json(r[0]) for r in rows]


class AuctionLotRepository:
    """拍卖仓储"""

    @staticmethod
    def save(lot: AuctionLot):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO auction_lots (id, data_json, status, seller_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            data_json = excluded.data_json,
            status = excluded.status;
        """, (
            lot.id,
            lot.model_dump_json(),
            lot.status.value,
            lot.seller_id,
            lot.created_at,
        ))
        conn.commit()
        conn.close()

    @staticmethod
    def list_all() -> List[AuctionLot]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT data_json FROM auction_lots ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [AuctionLot.model_validate_json(r[0]) for r in rows]


class ChronicleRepository:
    """世界事件总账"""

    @staticmethod
    def record(event_type: str, actor_name: str, summary: str):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO world_chronicle (event_type, actor_name, summary, created_at)
        VALUES (?, ?, ?, ?)
        """, (event_type, actor_name, summary, time.time()))
        conn.commit()
        conn.close()

    @staticmethod
    def get_recent(limit: int = 5) -> List[str]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT summary, created_at FROM world_chronicle
        ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]


class JianghuEventRepository:
    """江湖因果账仓储：结构化世界事件唯一真相源"""

    @staticmethod
    def append(rec: Dict) -> None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO jianghu_events
            (id, kind, data_json, created_at, visibility, location)
            VALUES (?,?,?,?,?,?)
            """,
            (
                rec.get("id"),
                rec.get("kind") or "unknown",
                json.dumps(rec, ensure_ascii=False),
                float(rec.get("created_at") or time.time()),
                rec.get("visibility") or "public",
                rec.get("location") or "",
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def list_recent(limit: int = 20, since: Optional[float] = None, kind: Optional[str] = None) -> List[Dict]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        q = "SELECT data_json FROM jianghu_events WHERE 1=1"
        args: list = []
        if since is not None:
            q += " AND created_at > ?"
            args.append(float(since))
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(max(1, int(limit)))
        cursor.execute(q, args)
        rows = cursor.fetchall()
        conn.close()
        out = []
        for r in rows:
            try:
                out.append(json.loads(r[0]))
            except Exception:
                continue
        return out

    @staticmethod
    def query_related(character_id: str, limit: int = 10) -> List[Dict]:
        """当事人/目标相关的近期事件（内存过滤，账量有限）"""
        rows = JianghuEventRepository.list_recent(limit=max(limit * 8, 40))
        cid = str(character_id)
        out = []
        for ev in rows:
            actors = [str(x) for x in (ev.get("actor_ids") or [])]
            targets = [str(x) for x in (ev.get("target_ids") or [])]
            refs = [str(x) for x in (ev.get("ref_ids") or [])]
            if cid in actors or cid in targets or cid in refs:
                out.append(ev)
            if len(out) >= limit:
                break
        return out


class EventLedgerRepository:
    """角色事件账（长期记忆检索源）"""

    @staticmethod
    def append(
        event_id: str,
        ts: float,
        type: str,
        actor_id: str,
        actor_name: str,
        summary: str,
        target_id: Optional[str] = None,
        target_name: Optional[str] = None,
        location: Optional[str] = None,
        effects_digest: str = "",
        chain_id: Optional[str] = None,
        refs: Optional[List[str]] = None,
    ):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO event_ledger
            (event_id, ts, type, actor_id, actor_name, target_id, target_name,
             location, summary, effects_digest, chain_id, refs_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id, ts, type, actor_id, actor_name,
                target_id, target_name, location,
                summary[:200], effects_digest[:120], chain_id,
                json.dumps(refs or [], ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def query_for_memory(
        character_id: str,
        location: Optional[str] = None,
        limit: int = 8,
    ) -> List[dict]:
        """按当事人/地点检索近期事件，时间倒序"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT event_id, ts, type, actor_id, actor_name, target_id, target_name,
                   location, summary, effects_digest, chain_id
            FROM event_ledger
            WHERE actor_id = ? OR target_id = ? OR (location = ? AND ? IS NOT NULL)
            ORDER BY ts DESC
            LIMIT ?
            """,
            (character_id, character_id, location, location, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        out = []
        for r in rows:
            out.append({
                "event_id": r[0], "ts": r[1], "type": r[2],
                "actor_id": r[3], "actor_name": r[4],
                "target_id": r[5], "target_name": r[6],
                "location": r[7], "summary": r[8],
                "effects_digest": r[9], "chain_id": r[10],
            })
        return out

    @staticmethod
    def query_feud_pairs(character_id: str, limit: int = 5) -> List[dict]:
        """拉与自己相关的杀戮/仇怨类事件（复仇工作流用）"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT event_id, ts, type, actor_id, actor_name, target_id, target_name,
                   location, summary
            FROM event_ledger
            WHERE (actor_id = ? OR target_id = ?)
              AND type IN ('KILL','BOUNTY','FEUD','FREE','COMBAT','REVENGE')
            ORDER BY ts DESC
            LIMIT ?
            """,
            (character_id, character_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "event_id": r[0], "ts": r[1], "type": r[2],
                "actor_id": r[3], "actor_name": r[4],
                "target_id": r[5], "target_name": r[6],
                "location": r[7], "summary": r[8],
            }
            for r in rows
        ]


class CharacterBioRepository:
    """角色小传（L1）"""

    @staticmethod
    def save(character_id: str, bio_text: str, traits: Optional[dict] = None):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO character_bios (character_id, bio_text, traits_json, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(character_id) DO UPDATE SET
                bio_text = excluded.bio_text,
                traits_json = excluded.traits_json,
                updated_at = excluded.updated_at
            """,
            (character_id, bio_text[:400], json.dumps(traits or {}, ensure_ascii=False), time.time()),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get(character_id: str) -> Optional[str]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT bio_text FROM character_bios WHERE character_id = ?", (character_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None


class NpcAgendaRepository:
    """NPC 议程仓储（一 NPC 一活跃目标）"""

    @staticmethod
    def upsert(
        npc_id: str,
        npc_name: str,
        agenda_type: str,
        target_hint: str = "",
        note: str = "",
        state: str = "active",
        last_tick: float = 0.0,
        progress: int = 0,
        extra: Optional[dict] = None,
    ):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO npc_agendas
            (npc_id, npc_name, agenda_type, target_hint, note, state, last_tick, progress, extra_json)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(npc_id) DO UPDATE SET
                npc_name = excluded.npc_name,
                agenda_type = excluded.agenda_type,
                target_hint = excluded.target_hint,
                note = excluded.note,
                state = excluded.state,
                last_tick = excluded.last_tick,
                progress = excluded.progress,
                extra_json = excluded.extra_json
            """,
            (
                npc_id, npc_name, agenda_type, target_hint, note,
                state, last_tick, progress,
                json.dumps(extra or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get(npc_id: str) -> Optional[dict]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT npc_id, npc_name, agenda_type, target_hint, note, state, last_tick, progress, extra_json "
            "FROM npc_agendas WHERE npc_id = ?",
            (npc_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        extra = {}
        try:
            extra = json.loads(row[8] or "{}")
        except Exception:
            extra = {}
        return {
            "npc_id": row[0], "npc_name": row[1], "agenda_type": row[2],
            "target_hint": row[3] or "", "note": row[4] or "",
            "state": row[5], "last_tick": row[6] or 0.0,
            "progress": row[7] or 0, "extra": extra,
        }

    @staticmethod
    def list_all() -> List[dict]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT npc_id, npc_name, agenda_type, target_hint, note, state, last_tick, progress, extra_json "
            "FROM npc_agendas ORDER BY last_tick ASC"
        )
        rows = cursor.fetchall()
        conn.close()
        out = []
        for row in rows:
            extra = {}
            try:
                extra = json.loads(row[8] or "{}")
            except Exception:
                pass
            out.append({
                "npc_id": row[0], "npc_name": row[1], "agenda_type": row[2],
                "target_hint": row[3] or "", "note": row[4] or "",
                "state": row[5], "last_tick": row[6] or 0.0,
                "progress": row[7] or 0, "extra": extra,
            })
        return out

    @staticmethod
    def mark_tick(npc_id: str, last_action: str = "", progress: Optional[int] = None, state: Optional[str] = None):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if progress is None and state is None:
            cursor.execute(
                "UPDATE npc_agendas SET last_tick = ?, note = CASE WHEN ? != '' THEN ? ELSE note END WHERE npc_id = ?",
                (time.time(), last_action, last_action, npc_id),
            )
        elif state is None:
            cursor.execute(
                "UPDATE npc_agendas SET last_tick = ?, progress = ?, note = CASE WHEN ? != '' THEN ? ELSE note END WHERE npc_id = ?",
                (time.time(), progress, last_action, last_action, npc_id),
            )
        else:
            cursor.execute(
                "UPDATE npc_agendas SET last_tick = ?, state = ?, progress = COALESCE(?, progress), "
                "note = CASE WHEN ? != '' THEN ? ELSE note END WHERE npc_id = ?",
                (time.time(), state, progress, last_action, last_action, npc_id),
            )
        conn.commit()
        conn.close()


class NpcMindRepository:
    """NPC 心智：性格标签 + 对玩家态度"""

    @staticmethod
    def upsert(
        npc_id: str,
        personality: str,
        traits: Optional[dict] = None,
        attitudes: Optional[dict] = None,
    ):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO npc_minds (npc_id, personality, traits_json, attitudes_json, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(npc_id) DO UPDATE SET
                personality = excluded.personality,
                traits_json = excluded.traits_json,
                attitudes_json = excluded.attitudes_json,
                updated_at = excluded.updated_at
            """,
            (
                npc_id,
                personality[:80],
                json.dumps(traits or {}, ensure_ascii=False),
                json.dumps(attitudes or {}, ensure_ascii=False),
                time.time(),
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get(npc_id: str) -> Optional[dict]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT personality, traits_json, attitudes_json FROM npc_minds WHERE npc_id = ?",
            (npc_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        traits, attitudes = {}, {}
        try:
            traits = json.loads(row[1] or "{}")
        except Exception:
            pass
        try:
            attitudes = json.loads(row[2] or "{}")
        except Exception:
            pass
        return {"personality": row[0], "traits": traits, "attitudes": attitudes}

    @staticmethod
    def set_attitude(npc_id: str, other_id: str, value: int, label: str = ""):
        """value: -100 仇视 ~ 0 中立 ~ +100 友善"""
        value = max(-100, min(100, int(value)))
        if label not in ("hostile", "wary", "neutral", "friendly", "ally"):
            if value <= -40:
                label = "hostile"
            elif value <= -15:
                label = "wary"
            elif value >= 40:
                label = "ally"
            elif value >= 15:
                label = "friendly"
            else:
                label = "neutral"
        mind = NpcMindRepository.get(npc_id) or {"personality": "?", "traits": {}, "attitudes": {}}
        attitudes = dict(mind.get("attitudes") or {})
        attitudes[other_id] = {"value": value, "label": label}
        NpcMindRepository.upsert(
            npc_id,
            mind.get("personality", "?"),
            mind.get("traits") or {},
            attitudes,
        )
        return attitudes[other_id]


class AuthSessionRepository:
    """登录会话持久化：服务器重启后凭 token 续玩"""

    @staticmethod
    def save(token: str, user_id: str, character_id: str, name: str):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        now = time.time()
        cur.execute(
            """
            INSERT INTO auth_sessions (token, user_id, character_id, name, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(token) DO UPDATE SET
                user_id = excluded.user_id,
                character_id = excluded.character_id,
                name = excluded.name,
                last_seen = excluded.last_seen;
            """,
            (token, user_id, character_id, name, now, now),
        )
        # 同一账号仅保留最新 5 条会话，防膨胀
        cur.execute(
            """
            DELETE FROM auth_sessions WHERE user_id = ? AND token NOT IN (
                SELECT token FROM auth_sessions WHERE user_id = ? ORDER BY last_seen DESC LIMIT 5
            );
            """,
            (user_id, user_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get(token: str) -> Optional[dict]:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT token, user_id, character_id, name, last_seen FROM auth_sessions WHERE token = ?",
            (token,),
        )
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE auth_sessions SET last_seen = ? WHERE token = ?", (time.time(), token))
            conn.commit()
        conn.close()
        if not row:
            return None
        return {
            "token": row[0],
            "user_id": row[1],
            "character_id": row[2],
            "name": row[3],
            "last_seen": row[4],
        }

    @staticmethod
    def delete(token: str):
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()

    @staticmethod
    def latest_for_user(user_id: str) -> Optional[dict]:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT token, user_id, character_id, name FROM auth_sessions WHERE user_id = ? ORDER BY last_seen DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {"token": row[0], "user_id": row[1], "character_id": row[2], "name": row[3]}


class AccountRepository:
    """用户名密码账号"""

    @staticmethod
    def create(username: str, password_hash: str, salt: str) -> Optional[str]:
        import uuid as _uuid

        uid = f"acct_{_uuid.uuid4().hex[:12]}"
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO accounts (user_id, username, password_hash, salt, created_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uid, username, password_hash, salt, time.time(), time.time()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return None
        conn.close()
        return uid

    @staticmethod
    def get_by_username(username: str) -> Optional[dict]:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, username, password_hash, salt FROM accounts WHERE username = ?",
            (username,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "user_id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "salt": row[3],
        }

    @staticmethod
    def touch_login(user_id: str):
        conn = sqlite3.connect(DB_PATH)
        conn.cursor().execute(
            "UPDATE accounts SET last_login = ? WHERE user_id = ?",
            (time.time(), user_id),
        )
        conn.commit()
        conn.close()


class GeneratedNameRepository:
    """AI 生成物：名称去重与属性落库"""

    @staticmethod
    def save(name: str, kind: str, data: dict) -> bool:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO generated_names (name, kind, data_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO NOTHING
                """,
                (name, kind, json.dumps(data, ensure_ascii=False), time.time()),
            )
            conn.commit()
            ok = cur.rowcount > 0
        except Exception:
            ok = False
        finally:
            conn.close()
        return ok

    @staticmethod
    def all_names() -> set:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM generated_names")
        rows = {r[0] for r in cur.fetchall()}
        conn.close()
        return rows

    @staticmethod
    def get(name: str) -> Optional[dict]:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT data_json FROM generated_names WHERE name = ?", (name,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    @staticmethod
    def list_kind(kind: str, limit: int = 20):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT name, data_json FROM generated_names WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
            (kind, limit),
        )
        rows = cur.fetchall()
        conn.close()
        out = []
        for n, j in rows:
            try:
                d = json.loads(j)
            except Exception:
                d = {}
            d["name"] = n
            out.append(d)
        return out

