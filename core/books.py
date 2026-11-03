"""著书立说引擎（F11）

闭环：攒灵感（探险/委托/突破既有事实钩子）→ 燃寿著书（灵感 10 + 寿元 1 年）
→ 亲笔手稿经坊市寄售流通 → 他人首次研读得一次性修为/道心 → 作者得声望（按本封顶）。

设计要点（spec: docs/compose/spec/books.md）：
- 物品层只有固定名「亲笔手稿」，不入 ITEM_CATALOG；每「本」书的元数据存 books 表。
- 任一角色同时至多持有 1 本手稿（含寄售中），绑定恒唯一；研读须同时满足
  「行囊有手稿 ∧ 书目 holder 为本人 ∧ state=held」，fail-closed 防逃逸通道刷收益。
- 数值全规则：品质按境界 tier 定，研读收益/声望按品质常量表；AI 只起名/写序言，
  离线或不合格即降级本地模板。
"""
import random
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.models import Character, CharacterStatus

# ---------------- 常量（数值归规则） ----------------
BOOK_ITEM = "亲笔手稿"

INSPIRATION_CAP = 60                # 灵感存量封顶
INSPIRATION_FROM_EXPLORE = 1        # 探险成功
INSPIRATION_FROM_QUEST = 2          # 委托链整链完成
INSPIRATION_FROM_BREAKTHROUGH = 3   # 突破成功

BOOK_INSPIRATION_COST = 10          # 著书耗灵感
BOOK_LIFESPAN_COST_YEARS = 1.0      # 著书燃寿（游戏年，走 lifespan.burn_lifespan）
BOOK_MIN_REMAINING_YEARS = 1.0      # 燃寿后须保留的寿元线（剩余须严格大于 成本+此值）

# 研读收益（按品质；exp 远低于 EVENT_EFFECT_CAPS.exp=800，dao_heart 低于 caps 20）
READ_REWARDS: Dict[str, Dict[str, int]] = {
    "下品": {"exp": 60, "dao_heart": 1},
    "中品": {"exp": 150, "dao_heart": 2},
    "上品": {"exp": 300, "dao_heart": 3},
}
# 作者声望：每位新读者首次研读结算一次；单本书累计封顶
PRESTIGE_PER_READ: Dict[str, int] = {"下品": 2, "中品": 3, "上品": 5}
BOOK_PRESTIGE_CAP = 10

QUALITY_BY_TIER = [(4, "上品"), (2, "中品"), (0, "下品")]  # tier 下限 → 品质（降序匹配）

# 本地模板池（AI 不可用/不合格时的书名与序言；{name}=作者名）
TITLE_TEMPLATES: Dict[str, List[str]] = {
    "下品": ["{name}游记", "{name}杂录", "山野拾遗", "{name}手札"],
    "中品": ["{name}问道录", "云游心经", "{name}见闻考", "沧海拾珠"],
    "上品": ["{name}证道篇", "天人感应录", "{name}长生策", "大道拾遗"],
}
PREFACE_TEMPLATES: List[str] = [
    "余修行半生，所见所闻尽付此卷，后来者观之可鉴。",
    "道不可言，姑且以文字记其万一，聊备后来者参详。",
    "此卷所载皆亲历之事，虚言妄语天道共弃。",
    "焚香沐手，方敢落笔；字字心血，愿与同道共勉。",
]


class Book(BaseModel):
    """一「本」书的元数据（books 表 data_json；物品本体是行囊中的固定名手稿）"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    author_id: str
    author_name: str
    title: str = ""
    preface: str = ""
    quality: str = "下品"
    created_at: float = 0.0
    holder_id: str = ""          # 当前持有者（寄售中仍为卖家）
    holder_name: str = ""
    state: str = "held"          # held 在持 / listed 寄售中 / gifted 已赠予（终态）
    listing_id: str = ""         # state=listed 时的寄售单 id
    readers: List[str] = Field(default_factory=list)  # 已受益读者 char id（幂等锚）
    prestige_paid: int = 0       # 本书已结算给作者的声望累计（封顶锚）


def quality_for_tier(tier: int) -> str:
    for lo, q in QUALITY_BY_TIER:
        if tier >= lo:
            return q
    return "下品"


class BookEngine:
    """著书立说裁决引擎（双端共用单点）"""

    # ---------------- 灵感 ----------------
    @staticmethod
    def gain_inspiration(char: Character, amount: int) -> int:
        """灵感入账（既有事实钩子调用）：钳至 INSPIRATION_CAP，返回实际新增。"""
        if amount <= 0:
            return 0
        before = int(getattr(char, "inspiration", 0) or 0)
        after = min(INSPIRATION_CAP, before + amount)
        char.inspiration = after
        return after - before

    # ---------------- 书目存取（仓储懒加载，防循环导入） ----------------
    @staticmethod
    def _repo():
        from storage.db import BookRepository

        return BookRepository

    @staticmethod
    def book_held_by(char_id: str) -> Optional[Book]:
        """某角色当前持有（含寄售中）的唯一书目；无则 None。"""
        try:
            for b in BookEngine._repo().list_all():
                if b.holder_id == char_id and b.state in ("held", "listed"):
                    return b
        except Exception:
            return None
        return None

    @staticmethod
    def _book_by_listing(listing_id: str) -> Optional[Book]:
        try:
            for b in BookEngine._repo().list_all():
                if b.listing_id and b.listing_id == listing_id:
                    return b
        except Exception:
            return None
        return None

    @staticmethod
    def _save(book: Book) -> None:
        try:
            BookEngine._repo().save(book)
        except Exception:
            pass

    # ---------------- 书名/序言（AI 只叙事，规则先定品质） ----------------
    @staticmethod
    def _try_ai_title(author: Character, quality: str) -> Optional[Dict[str, str]]:
        """AI 起名：仅在通道可用时尝试；任何异常/不合格返回 None 走模板。"""
        try:
            from ai.gateway import _chat_text, ai_available

            if not ai_available():
                return None
            raw = _chat_text(
                "为一位修仙者亲笔所著的修行手稿起书名并写一句序言。\n"
                f"作者道号：{author.name}；境界：{author.realm.name}；品质：{quality}。\n"
                "只输出两行：第一行是书名（2-10 个汉字，不带书名号）；"
                "第二行是一句序言（不超过 40 个汉字）。不要解释。",
                timeout=8.0,
            )
            if not raw:
                return None
            lines = [ln.strip().strip("《》\"'「」 　") for ln in raw.strip().splitlines() if ln.strip()]
            if len(lines) < 2:
                return None
            title, preface = lines[0], lines[1]
            if not (2 <= len(title) <= 14) or len(preface) > 80:
                return None
            return {"title": title, "preface": preface}
        except Exception:
            return None

    @staticmethod
    def _template_title(author: Character, quality: str, rng: random.Random) -> Dict[str, str]:
        pool = TITLE_TEMPLATES.get(quality, TITLE_TEMPLATES["下品"])
        title = rng.choice(pool).replace("{name}", author.name)
        preface = rng.choice(PREFACE_TEMPLATES)
        return {"title": title, "preface": preface}

    @staticmethod
    def make_title_preface(
        author: Character, quality: str, rng: Optional[random.Random] = None
    ) -> Dict[str, str]:
        ai = BookEngine._try_ai_title(author, quality)
        if ai:
            return ai
        return BookEngine._template_title(author, quality, rng or random.Random())

    # ---------------- 著书 ----------------
    @staticmethod
    def write_book(
        char: Character,
        now: Optional[float] = None,
        rng: Optional[random.Random] = None,
    ) -> Dict[str, Any]:
        """著书：校验全过才扣费落账（灵感+燃寿先扣、成书后建目），失败零变更。"""
        t = now if now is not None else time.time()
        if char.status == CharacterStatus.DEAD or char.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，笔墨无从落纸。"}
        if BOOK_ITEM in char.inventory or BookEngine.book_held_by(char.id) is not None:
            return {
                "success": False,
                "message": "怀中已有一部手稿未曾流通，先将它寄售或赠人，方好另起新篇。",
            }
        inspiration = int(getattr(char, "inspiration", 0) or 0)
        if inspiration < BOOK_INSPIRATION_COST:
            return {
                "success": False,
                "message": (
                    f"灵感未足（{inspiration}/{BOOK_INSPIRATION_COST}）："
                    "多历练些——探险、委托、突破皆可积攒灵感。"
                ),
            }
        remaining = char.lifespan.get_remaining_years(t)
        if remaining <= BOOK_LIFESPAN_COST_YEARS + BOOK_MIN_REMAINING_YEARS:
            return {
                "success": False,
                "message": (
                    f"寿元将尽（余 {remaining:.1f} 年），著书须燃寿 {BOOK_LIFESPAN_COST_YEARS:.0f} 年"
                    f"且余寿须过 {BOOK_MIN_REMAINING_YEARS:.0f} 年——不可再耗心血于笔墨。"
                ),
            }
        quality = quality_for_tier(int(char.realm.tier))
        naming = BookEngine.make_title_preface(char, quality, rng=rng)
        # 落账：扣灵感 → 燃寿（既有路径）→ 得手稿 → 建书目
        char.inspiration = inspiration - BOOK_INSPIRATION_COST
        char.lifespan.burn_lifespan(BOOK_LIFESPAN_COST_YEARS)
        char.inventory.append(BOOK_ITEM)
        book = Book(
            author_id=char.id,
            author_name=char.name,
            title=naming["title"],
            preface=naming["preface"],
            quality=quality,
            created_at=t,
            holder_id=char.id,
            holder_name=char.name,
            state="held",
        )
        BookEngine._save(book)
        return {
            "success": True,
            "book": book,
            "message": (
                f"【著书立说】焚膏继晷，燃寿 {BOOK_LIFESPAN_COST_YEARS:.0f} 年、耗灵感 {BOOK_INSPIRATION_COST}，"
                f"终成一卷【{book.title}】（{quality}）。\n"
                f"序言：{book.preface}\n"
                "手稿已收入行囊：可 /寄售 亲笔手稿 <价> 付坊市流通，他人阅读受益，你亦随之扬名。"
            ),
        }

    # ---------------- 研读 ----------------
    @staticmethod
    def read_book(char: Character, hint: str = "", now: Optional[float] = None) -> Dict[str, Any]:
        """研读所持手稿：首次（非作者）结算收益+作者声望，readers/prestige_paid 双锚幂等。"""
        t = now if now is not None else time.time()
        if char.status == CharacterStatus.DEAD or char.lifespan.is_dead(t):
            return {"success": False, "message": "身死道消，无从展卷。"}
        if BOOK_ITEM not in char.inventory:
            return {
                "success": False,
                "message": "行囊中并无【亲笔手稿】。可去坊市 /买寄售 他人之作，或先 /著书 自撰一卷。",
            }
        book = BookEngine.book_held_by(char.id)
        if book is None or book.state != "held":
            return {
                "success": False,
                "message": "怀中这部手稿来历不明、无字可读（无字天书）。",
            }
        hint = (hint or "").strip()
        if hint and hint not in book.title and hint not in book.author_name:
            return {
                "success": False,
                "message": f"怀中所持乃【{book.author_name}】所著《{book.title}》，并无「{hint}」。",
            }
        head = (
            f"【展卷】《{book.title}》（{book.quality}）· 著者【{book.author_name}】\n"
            f"序言：{book.preface}"
        )
        if book.author_id == char.id:
            return {"success": True, "gained": False,
                    "message": head + "\n自家文字烂熟于心，重读并无新的进益。"}
        if char.id in book.readers:
            return {"success": True, "gained": False,
                    "message": head + "\n此卷已研读过，心得不再重复。"}

        reward = READ_REWARDS.get(book.quality, READ_REWARDS["下品"])
        before_exp = char.realm.current_exp
        char.realm.current_exp = max(
            0, min(char.realm.max_exp, before_exp + int(reward["exp"]))
        )
        exp_gain = char.realm.current_exp - before_exp
        dh_before = char.karma.dao_heart
        char.karma.dao_heart = max(0, min(100, dh_before + int(reward["dao_heart"])))
        dh_gain = char.karma.dao_heart - dh_before

        # 幂等锚先落：读者入册 + 声望额度累加，再结算作者（作者不在世则跳过）
        book.readers.append(char.id)
        prestige_gain = 0
        per = int(PRESTIGE_PER_READ.get(book.quality, 0))
        if book.prestige_paid < BOOK_PRESTIGE_CAP:
            prestige_gain = min(per, BOOK_PRESTIGE_CAP - book.prestige_paid)
        if prestige_gain > 0:
            book.prestige_paid += prestige_gain
            try:
                from storage.db import CharacterRepository

                author = CharacterRepository.get_by_id(book.author_id)
                if author is not None and author.id != char.id:
                    author.prestige = int(getattr(author, "prestige", 0) or 0) + prestige_gain
                    CharacterRepository.save(author)
            except Exception:
                pass
        BookEngine._save(book)
        try:
            import core.jianghu as jianghu

            jianghu.append_event(
                kind="book",
                actor_ids=[char.id],
                actor_names=[char.name],
                target_ids=[book.author_id],
                location=char.location,
                summary=f"【{char.name}】展卷研读【{book.author_name}】所著《{book.title}》，颇有所得",
                rule_result={"exp": exp_gain, "dao_heart": dh_gain, "prestige": prestige_gain},
                narrative="",
                ref_ids=[char.id, book.author_id],
                source="rule",
            )
        except Exception:
            pass
        fame_line = (
            f"\n著者【{book.author_name}】声名随之远播（声望 +{prestige_gain}）。"
            if prestige_gain > 0 else ""
        )
        return {
            "success": True,
            "gained": True,
            "exp_gain": exp_gain,
            "dao_heart_gain": dh_gain,
            "prestige_gain": prestige_gain,
            "message": (
                head
                + f"\n掩卷长思：修为 +{exp_gain} · 道心 +{dh_gain}。"
                + fame_line
            ),
        }

    # ---------------- 流通绑定钩子（寄售/赠予，双端指令层在成功后调用） ----------------
    @staticmethod
    def on_listing_created(seller: Character, listing_id: str) -> None:
        book = BookEngine.book_held_by(seller.id)
        if book is not None and book.state == "held":
            book.state = "listed"
            book.listing_id = listing_id
            BookEngine._save(book)

    @staticmethod
    def on_listing_sold(listing_id: str, buyer: Character) -> None:
        book = BookEngine._book_by_listing(listing_id)
        if book is not None:
            book.holder_id = buyer.id
            book.holder_name = buyer.name
            book.state = "held"
            book.listing_id = ""
            BookEngine._save(book)

    @staticmethod
    def on_listing_cancelled(listing_id: str) -> None:
        book = BookEngine._book_by_listing(listing_id)
        if book is not None:
            book.state = "held"
            book.listing_id = ""
            BookEngine._save(book)

    @staticmethod
    def on_gifted(giver: Character, npc: Character) -> None:
        book = BookEngine.book_held_by(giver.id)
        if book is not None and book.state == "held":
            book.state = "gifted"
            book.holder_id = npc.id
            book.holder_name = npc.name
            book.listing_id = ""
            BookEngine._save(book)

    @staticmethod
    def buyer_can_hold(buyer: Character) -> bool:
        """买寄售手稿前校验：一人同时至多持一本。"""
        return BOOK_ITEM not in buyer.inventory and BookEngine.book_held_by(buyer.id) is None

    # ---------------- 面板 ----------------
    @staticmethod
    def panel_text(char: Character, now: Optional[float] = None) -> str:
        t = now if now is not None else time.time()
        inspiration = int(getattr(char, "inspiration", 0) or 0)
        prestige = int(getattr(char, "prestige", 0) or 0)
        remaining = char.lifespan.get_remaining_years(t)
        lines = [
            "【著书立说】笔墨载道，留名后世",
            f"灵感 {inspiration}/{INSPIRATION_CAP}（探险 +{INSPIRATION_FROM_EXPLORE} · "
            f"委托达成 +{INSPIRATION_FROM_QUEST} · 突破 +{INSPIRATION_FROM_BREAKTHROUGH}）",
            f"声望 {prestige}",
        ]
        book = BookEngine.book_held_by(char.id)
        if book is not None:
            state_cn = "寄售中" if book.state == "listed" else "在持"
            lines.append(
                f"在持手稿：《{book.title}》（{book.quality}，著者 {book.author_name}，{state_cn}，"
                f"已被 {len(book.readers)} 人研读）——/研读 展卷，或 /寄售 亲笔手稿 <价> 流通。"
            )
        else:
            can = (
                inspiration >= BOOK_INSPIRATION_COST
                and remaining > BOOK_LIFESPAN_COST_YEARS + BOOK_MIN_REMAINING_YEARS
                and char.status != CharacterStatus.DEAD
            )
            nxt = quality_for_tier(int(char.realm.tier))
            lines.append(
                f"著书成本：灵感 {BOOK_INSPIRATION_COST} + 燃寿 {BOOK_LIFESPAN_COST_YEARS:.0f} 年"
                f"（燃后须余 {BOOK_MIN_REMAINING_YEARS:.0f} 年以上；以你当下境界成书为【{nxt}】）"
                + ("——万事俱备，/著书 写 即可落笔。" if can else "——尚有欠缺，见上方灵感与寿元。")
            )
        mine = []
        try:
            mine = [b for b in BookEngine._repo().list_all() if b.author_id == char.id]
        except Exception:
            mine = []
        if mine:
            lines.append("你历年所著：")
            for b in sorted(mine, key=lambda x: x.created_at):
                state_cn = {"held": "在持", "listed": "寄售中", "gifted": "已赠人"}.get(b.state, b.state)
                lines.append(
                    f"  · 《{b.title}》（{b.quality}，{state_cn}，读者 {len(b.readers)} 人，"
                    f"已结声望 {b.prestige_paid}/{BOOK_PRESTIGE_CAP}）"
                )
        return "\n".join(lines)
