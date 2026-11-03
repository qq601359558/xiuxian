"""
《天道因果录》核心领域模型
"""
import uuid
import time
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from config import (
    REALM_NAMES,
    SUB_TIER_NAMES,
    REALM_EXP_REQUIRED,
    SECONDS_PER_GAME_YEAR
)


class RootType(str, Enum):
    WASTE = "WASTE"       # 伪灵根 (四/五行杂灵根)
    TRUE = "TRUE"         # 真灵根 (二/三行灵根)
    HEAVEN = "HEAVEN"     # 天灵根 (单属性天之骄子)
    MUTANT = "MUTANT"     # 异灵根 (风/雷/冰/暗)


class Element(str, Enum):
    METAL = "金"
    WOOD = "木"
    WATER = "水"
    FIRE = "火"
    EARTH = "土"
    WIND = "风"
    THUNDER = "雷"
    ICE = "冰"


class SpiritualRoot(BaseModel):
    """灵根资质"""
    root_type: RootType
    elements: List[Element]
    efficiency: float = 1.0  # 修炼灵气吸收倍率 (0.6 ~ 2.5)

    def display_name(self) -> str:
        elem_str = "·".join([e.value for e in self.elements])
        type_map = {
            RootType.WASTE: "伪灵根",
            RootType.TRUE: "真灵根",
            RootType.HEAVEN: "天灵根",
            RootType.MUTANT: "异灵根"
        }
        return f"{type_map[self.root_type]} ({elem_str})"


class Realm(BaseModel):
    """境界数据"""
    tier: int = 1         # 0:凡人, 1:练气, 2:筑基, 3:金丹, 4:元婴, 5:化神...
    sub_tier: int = 0     # 0:初, 1:中, 2:后, 3:圆满
    current_exp: int = 0  # 当前修为

    @property
    def name(self) -> str:
        t_name = REALM_NAMES[self.tier] if self.tier < len(REALM_NAMES) else "通天神魔"
        if self.tier == 0 or self.tier >= 9:
            return t_name
        return f"{t_name}{SUB_TIER_NAMES[self.sub_tier]}"

    @property
    def max_exp(self) -> int:
        return REALM_EXP_REQUIRED.get(self.tier, 999999999)

    @property
    def is_full(self) -> bool:
        return self.current_exp >= self.max_exp


class Lifespan(BaseModel):
    """寿元系统 (现实时间对齐)"""
    birth_base: float                 # 出生随机寿元 (岁 = 现实天)
    accumulated_gain: float = 0.0     # 突破历次增寿累计 (岁)
    death_timestamp: float            # 预定坐化真实纪元时间戳 (Unix Timestamp)

    def get_remaining_years(self, current_time: Optional[float] = None) -> float:
        """惰性计算当前剩余寿元（单位：岁）"""
        now = current_time or time.time()
        remaining_seconds = max(0.0, self.death_timestamp - now)
        return remaining_seconds / SECONDS_PER_GAME_YEAR

    def is_dead(self, current_time: Optional[float] = None) -> bool:
        """是否已寿尽坐化"""
        return self.get_remaining_years(current_time) <= 0.0

    def add_lifespan(self, years: float):
        """增寿：直接推后死亡时间戳"""
        self.accumulated_gain += years
        self.death_timestamp += years * SECONDS_PER_GAME_YEAR

    def burn_lifespan(self, years: float):
        """燃寿（施展秘术/天道反噬）：提前死亡时间戳"""
        self.death_timestamp -= years * SECONDS_PER_GAME_YEAR


class KarmaLedger(BaseModel):
    """因果与业力账本"""
    sin_value: int = 0           # 业力值 (杀戮/掠夺)
    merit_value: int = 0         # 功德值 (除恶/护法)
    dao_heart: int = 100         # 道心值 (0~100)
    blood_mark_until: float = 0.0 # 血煞持续到的时间戳

    def is_blood_marked(self, now: Optional[float] = None) -> bool:
        t = now or time.time()
        return t < self.blood_mark_until

    def add_sin(self, value: int, now: Optional[float] = None):
        t = now or time.time()
        self.sin_value += value
        # 沾染血煞 3 天
        self.blood_mark_until = max(self.blood_mark_until, t + 3 * SECONDS_PER_GAME_YEAR)

    def add_merit(self, value: int):
        self.merit_value += value
        # 功德消解部分业力
        self.sin_value = max(0, self.sin_value - value // 2)


class CharacterStatus(str, Enum):
    IDLE = "IDLE"             # 游荡闲适
    MEDITATING = "MEDITATING" # 闭关吐纳
    IN_FIGHT = "IN_FIGHT"     # 斗法搏杀
    DEAD = "DEAD"             # 寿终坐化/身死道消
    CAPTURED = "CAPTURED"     # 被擒（会话内绑人成功）


STATUS_CN = {
    CharacterStatus.IDLE: "闲适",
    CharacterStatus.MEDITATING: "闭关",
    CharacterStatus.IN_FIGHT: "斗法",
    CharacterStatus.DEAD: "陨落",
    CharacterStatus.CAPTURED: "被擒",
}


def status_cn(status: Any) -> str:
    if isinstance(status, CharacterStatus):
        return STATUS_CN.get(status, status.value)
    try:
        return STATUS_CN.get(CharacterStatus(str(status)), str(status))
    except Exception:
        return str(status)


class ArrayFormation(BaseModel):
    """闭关防护大阵与结界"""
    name: str = "一阶青木迷踪阵"
    max_durability: int = 1500
    current_durability: int = 1500
    concealment_bonus: int = 120     # 隐匿加成
    counter_damage: int = 60         # 杀阵反击伤害
    is_active: bool = False


class SpiritPet(BaseModel):
    """灵宠（F01）：随角色一世存续；主人坐化则灵宠殁"""
    species: str                      # 物种名（见 core/pets.py 物种池）
    name: str                         # 个体名（默认同物种，重名加序）
    growth: int = 0                   # 成长值（等级由 core.pets.level_for 推导）
    intimacy: int = 10                # 亲密度 0~100
    active: bool = False              # 是否出战中（全角色唯一，由 PetEngine 维护）
    state: str = "rest"               # follow 随行 / rest 休息 / dead 已殁
    met_at: float = 0.0               # 结契时间戳


class FarmPlot(BaseModel):
    """灵田地块（F06）：一块地一茬作物；成熟只看墙钟时间戳，惰性结算"""
    crop: str = ""                    # 所种种子名（见 core/farm.py FARM_CROPS），空 = 空地
    planted_at: float = 0.0           # 播种现实 Unix 时间戳
    matures_at: float = 0.0           # 成熟现实 Unix 时间戳


class QuestRing(BaseModel):
    """委托链一环（F07）：核验只认既有事实（当面交付/行囊物品/探险计数）"""
    kind: str                         # deliver 送信 / fetch 寻物 / slay 除妖
    desc: str = ""                    # 规则模板文案（发布时写死）
    deliver_npc_id: str = ""          # 交付对象：送信=收信人，寻物/除妖=发布者本人
    deliver_npc_name: str = ""
    item_name: str = ""               # fetch 目标物品名
    need: int = 1                     # slay 需成功探险次数；fetch 恒 1
    progress: int = 0                 # slay 已计数（探险落账钩子写入）


class QuestChain(BaseModel):
    """NPC 委托链（F07）：奖励在成链时定价写死，完成时一次发放"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    publisher_id: str
    publisher_name: str
    rings: List[QuestRing] = Field(default_factory=list)
    ring_index: int = 0               # 当前环下标（0 起）
    accepted_at: float = 0.0          # 接取前为 0（offers 预览态）
    expires_at: float = 0.0
    reward_stones: int = 0
    reward_merit: int = 0


class MeditationSession(BaseModel):
    """现实闭关会话（现实时间与游戏世界时间严格并行）"""
    is_active: bool = False
    start_time: float = 0.0          # 闭关开始现实 Unix 时间戳
    end_time: float = 0.0            # 预定出关现实 Unix 时间戳
    hours_planned: float = 0.0       # 计划闭关现实小时数
    stones_pledged: int = 0          # 投入碎石加速的灵石数
    array: Optional[ArrayFormation] = None # 部署的防护大阵


class Character(BaseModel):
    """修士完整核心实体"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_id: str
    name: str
    realm: Realm
    lifespan: Lifespan
    spiritual_root: SpiritualRoot
    karma: KarmaLedger = Field(default_factory=KarmaLedger)
    spirit_stones: int = 100       # 随身未绑定灵石
    status: CharacterStatus = CharacterStatus.IDLE
    meditation: MeditationSession = Field(default_factory=MeditationSession)
    location: str = "青云坊市客栈"   # 当前坐标/场景
    stealth_active: bool = False   # 是否开启敛息潜行
    skills: List[str] = Field(default_factory=lambda: ["吐纳术", "御剑术"])
    custom_arts: List[Dict[str, Any]] = Field(default_factory=list)  # 自创功法完整 DSL
    # 心法槽位（F02）：默认空槽 = 未装配 = 旧行为；art_slot_changed_at=0 表示从未变更（免冷却）
    main_art: str = ""  # 主修功法名（须在 skills 中）
    sub_arts: List[str] = Field(default_factory=list)  # 辅修功法名（最多 ART_SUB_MAX 门）
    art_slot_changed_at: float = 0.0  # 上次成功调整槽位的现实时间戳（冷却用）
    equipped: List[str] = Field(default_factory=list)  # 已穿戴装备名
    arrays: List[str] = Field(default_factory=list) # 持有的阵盘行囊
    sect: Optional[str] = None     # 所属宗门 (None 代表无门无派散修)
    sect_rank: str = "散修"         # 门派地位 (散修/外门弟子/内门弟子/执事长老)
    sect_contribution: int = 0     # 宗门贡献（上交/日环）
    last_salary_time: float = 0.0  # 上次领取宗门月俸现实时间戳
    death_cause: Optional[str] = None  # 死因（寿尽/渡劫/斗法等），转世结算用
    death_settled: bool = False  # 本世是否已做过道统结算（防重复发点）
    vault_stones: int = 0        # 坊市寄存灵石（不可被夺、不可被查抄）
    inventory: List[str] = Field(default_factory=list)  # 随身未绑定杂物名（阵盘仍用 arrays）
    captor_id: Optional[str] = None  # 被擒时擒拿者 id
    used_pills: List[str] = Field(default_factory=list)  # 本世已服用过的丹药名（防重复嗑）
    # 丹药闭关加成：服聚气丹后下次闭关修为 ×(1+mult)，结算后清零
    pill_exp_mult: float = 0.0
    pill_exp_note: str = ""
    born_at: float = Field(default_factory=lambda: time.time())  # 入世时刻（新手庇护用）
    # 离线归隐庇护
    offline_protected_until: float = 0.0
    reclusion_active: bool = False
    last_combat_at: float = 0.0
    combat_lock_until: float = 0.0
    flee_cooldown_until: float = 0.0
    adventure_cd_until: float = 0.0
    # 目标（六类目标源，可接可拒）
    goals: List[Dict[str, Any]] = Field(default_factory=list)
    # 灵宠（F01）：本世所养灵宠；待契约灵兽物种名（探险遇兽后写入，空=无）
    pets: List[SpiritPet] = Field(default_factory=list)
    pending_pet_species: str = ""
    # 洞府灵田（F06）：0 = 无洞府；地块数由等级推导（见 core/farm.py），旧档自动补默认
    cave_level: int = 0
    farm_plots: List[FarmPlot] = Field(default_factory=list)
    # NPC 委托链（F07）：进行中至多 1 条（见 core/quests.py）；随旧世消散，旧档自动补默认
    active_quest: Optional[QuestChain] = None
    quest_cooldown_until: float = 0.0  # 链了结后的接取冷却截止时间戳
    # 炼体/炼神双修（F10）：副修层数 0–10（见 core/body_soul.py）；随旧世消散，旧档自动补默认
    body_level: int = 0  # 炼体层数（战力/寿元微增）
    soul_level: int = 0  # 炼神层数（有效道心/神识加成）
    # 著书立说（F11）：灵感（探险/委托/突破钩子积攒，著书消耗）与个人声望（著书被研读结算）；旧档自动补默认
    inspiration: int = 0  # 灵感存量（封顶见 core/books.py INSPIRATION_CAP）
    prestige: int = 0     # 个人声望（与宗门声望、功德分账）
    # 心魔长期状态（F16）：魔念值与惰性推导锚点（阶段纯推导不落库，见 core/heart_demon_state.py）；随旧世消散，旧档自动补默认
    demon_seed: float = 0.0      # 魔念值：0=无种；阶段阈值 40 滋长 / 90 临发
    demon_anchor_at: float = 0.0 # 惰性结算锚点时间戳；0=从未同步（首同步只建基线不追溯）
    demon_sin_seen: int = 0      # 上次同步见过的业力值（杀业增量推导基线）
    demon_calm_at: float = 0.0   # 上次静坐镇魔时间戳（冷却用）

    def is_newbie_protected(self, now: Optional[float] = None) -> bool:
        """新手庇护：72h 内且境界 ≤ 筑基初"""
        from config import NEWBIE_PROTECTION_HOURS, NEWBIE_MAX_TIER, NEWBIE_MAX_SUB_TIER
        t = now or time.time()
        if t - self.born_at >= NEWBIE_PROTECTION_HOURS * 3600.0:
            return False
        if self.realm.tier > NEWBIE_MAX_TIER:
            return False
        if self.realm.tier == NEWBIE_MAX_TIER and self.realm.sub_tier > NEWBIE_MAX_SUB_TIER:
            return False
        return True

    def newbie_protect_until(self) -> float:
        from config import NEWBIE_PROTECTION_HOURS
        return self.born_at + NEWBIE_PROTECTION_HOURS * 3600.0

    def display_summary(self) -> Dict[str, Any]:
        """展示用关键属性字典"""
        rem_years = self.lifespan.get_remaining_years()
        days_int = int((rem_years % 1.0) * 365)
        years_int = int(rem_years)
        sect_display = f"{self.sect} · {self.sect_rank}" if self.sect else "四海散修"
        return {
            "id": self.id,
            "name": self.name,
            "realm": self.realm.name,
            "exp": f"{self.realm.current_exp} / {self.realm.max_exp}",
            "root": self.spiritual_root.display_name(),
            "lifespan_str": f"{years_int}岁 {days_int}天",
            "spirit_stones": self.spirit_stones,
            "sin": self.karma.sin_value,
            "merit": self.karma.merit_value,
            "dao_heart": self.karma.dao_heart,
            "is_blood_marked": self.karma.is_blood_marked(),
            "status": self.status.value,
            "location": self.location,
            "sect": self.sect,
            "sect_rank": self.sect_rank,
            "sect_display": sect_display
        }

