"""
《天道因果录》全局常数与配置
"""
import os
from pathlib import Path
from typing import Dict

# 根目录与数据目录 (全部严格限定在 D 盘)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "tiandao.db"

# ==================== 自动加载 .env 配置文件 ====================
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                # 已存在的环境变量优先，避免 reload 时用 .env 覆盖测试/启动注入
                if k and k not in os.environ:
                    os.environ[k] = v.strip().strip("'").strip('"')

# ==================== 时间与寿元常数 ====================
# 1 游戏年 = 现实 1 天 (86400 秒)
# 1 游戏月 = 现实 2 小时 (7200 秒)
# 1 游戏日 ≈ 现实 4 分钟 (240 秒)
SECONDS_PER_GAME_YEAR = 86400.0
SECONDS_PER_GAME_MONTH = 7200.0
SECONDS_PER_GAME_DAY = 240.0

# 赛季（纪元）周期：标准档 12 现实周 = 84 现实天 = 84 游戏年
SEASON_DAYS = 84
# 纪元起点（Unix）；未设置时首次启动赛季时写入
SEASON_EPOCH_FILE = DATA_DIR / "season_epoch.txt"
SEASON_WARN_DAYS = 7  # 终局前 7 天开始大劫预告

# 闭关托管：有效收益上限（设计小时），超出部分枯坐无益（寿元仍照扣）
MEDITATION_MAX_HOURS = 24.0
# 大限预警阈值（岁 = 现实天）；闭关途中跌破此值强制提示，禁止默默坐化
LIFESPAN_WARNING_YEARS = 10.0
# 新手庇护期内（72h）闭关修为加成，方便尽快体验升级
NEWBIE_EXP_MULT = 2.0

# ==================== 运行环境与时间缩放 ====================
# GAME_ENV=test|production
#   test（默认）：闭关墙钟可加速，便于联调；TIME_SCALE 默认 120（8 设计小时 ≈ 4 分钟墙钟）
#   production：强制与现实同步（TIME_SCALE=1），忽略误配
GAME_ENV = os.getenv("GAME_ENV", "test").strip().lower()


def is_production() -> bool:
    return GAME_ENV in ("production", "prod", "live")


def time_scale() -> float:
    """闭关倍速：1=与现实 1:1；N= N 倍速。生产强制 1。"""
    if is_production():
        return 1.0
    raw = os.getenv("TIME_SCALE", "120")
    try:
        s = float(raw)
    except (TypeError, ValueError):
        s = 120.0
    return max(0.001, min(100000.0, s))


def design_hours_to_wall_seconds(hours: float) -> float:
    """设计闭关小时 → 墙钟秒"""
    return float(hours) * 3600.0 / time_scale()


def wall_to_design_seconds(wall_sec: float) -> float:
    """墙钟秒 → 设计秒（结算收益/耗寿用）"""
    return float(wall_sec) * time_scale()


def env_time_label() -> str:
    ts = time_scale()
    if is_production():
        return f"{GAME_ENV} · 闭关与现实同步 (×1)"
    return f"{GAME_ENV} · 闭关加速 ×{ts:g}（仅测试）"

# ==================== 离线庇护与逃遁失败 ====================
# 主动「闭关归隐」：脱战 + 非冲突区才可入；庇护中不可被攻击/不可转移财货
OFFLINE_PROTECT_MAX_HOURS = 72.0
# 冲突区（is_safe=False）即时下线：仓皇遁走，随身灵石折损比例区间
FLEE_STONES_LOSS_MIN = 0.10
FLEE_STONES_LOSS_MAX = 0.25
# 斗法中下线：逃遁失败，可被夺随身（比例同击杀下限）
COMBAT_LOGOUT_LOOT_MIN = 0.40
COMBAT_LOGOUT_LOOT_MAX = 0.60
# 逃遁失败冷却：窗口内禁止立刻再入庇护（现实秒）
FLEE_COOLDOWN_SECONDS = 600.0

# ==================== 灵气总量稀释 ====================
# 高阶修士门槛（大境界 tier >= 此值计入稀释）
QI_HIGH_TIER = 3  # 金丹
# 双曲稀释：mult = 1 / (1 + n * K)，避免线性把 LAN 种子 NPC 打穿到地板
QI_DILUTION_K = 0.08
QI_MULT_MIN = 0.50
QI_MULT_MAX = 1.0

# ==================== 六榜 ====================
LEADERBOARD_TOP_N = 10
# 道行：功德权重高于业力（非力量榜只给软性荣誉，不发战力奖励）
DAOHANG_MERIT_W = 2.0
DAOHANG_SIN_W = 0.5
DAOHANG_HEART_W = 1.0

# ==================== 秘境 / 事件链 ====================
SECRET_REALMS = {
    "落霞古洞": {
        "location": "落霞山灵泉",
        "min_tier": 1,
        "danger": 0.35,
        "open_interval_hours": 6.0,
        "desc": "落霞山深处残破古洞，偶有玉简与灵泉现世。",
    },
    "黑风绝渊裂隙": {
        "location": "黑风绝渊",
        "min_tier": 2,
        "danger": 0.55,
        "open_interval_hours": 12.0,
        "desc": "绝渊裂隙通往上古战场残片，机缘与杀劫并存。",
    },
    "万星遗迹残址": {
        "location": "万星古岛",
        "min_tier": 3,
        "danger": 0.70,
        "open_interval_hours": 24.0,
        "desc": "真仙遗迹一角，金丹以下入内多半尸骨无存。",
    },
    "剑冢残碑": {
        "location": "万剑仙门峰",
        "min_tier": 2,
        "danger": 0.40,
        "open_interval_hours": 8.0,
        "desc": "万剑外围无主剑冢，残剑如林，剑意噬人。",
    },
    "荒古兽巢": {
        "location": "青云山外围",
        "min_tier": 1,
        "danger": 0.38,
        "open_interval_hours": 6.0,
        "desc": "青云山外围兽潮巢穴，妖丹与血食之地。",
    },
    "幽冥鬼市": {
        "location": "黑风绝渊",
        "min_tier": 3,
        "danger": 0.62,
        "open_interval_hours": 16.0,
        "desc": "绝渊深处鬼市幻影，可拾阴物，亦易被勾去半条魂。",
    },
    "灵药残圃": {
        "location": "落霞山灵泉",
        "min_tier": 1,
        "danger": 0.28,
        "open_interval_hours": 10.0,
        "desc": "古药园残圃，灵芝遍地，守圃傀儡尚存。",
    },
}
# 事件链：链头开启后 N 步内可继续推进
EVENT_CHAIN_MAX_STEPS = 3

# ==================== 外出探险 ====================
ADVENTURE_FEE = 20                    # 每次盘缠（灵石）
ADVENTURE_COOLDOWN_MIN = 8.0          # 设计分钟；墙钟 = / TIME_SCALE
ADVENTURE_EXP_BASE = 45.0             # 每危险 0.1 的基础修为尺度
ADVENTURE_EXP_MAX_MULT = 3.5          # 相对 base*danger 的上限倍率
ADVENTURE_EXP_FAIL_PCT = 0.08         # 失败亏当前修为比例
ADVENTURE_STONES_BASE = 25.0
ADVENTURE_LIFESPAN_BURN_MAX = 1.5     # 设计失败最大燃寿（岁）
ADVENTURE_LOOT_P = {
    "herb": 0.35,
    "pill": 0.25,
    "equip": 0.18,
    "map": 0.06,   # 藏宝图很低
}
ADVENTURE_LOOT_MAX = 2
ADVENTURE_HERBS = ["百年灵芝", "妖兽内丹"]
ADVENTURE_PILLS = ["聚气丹", "筑基丹", "玄元聚气丹"]  # 掉落以凡/人品为主
# 挖宝稀有丹
DIG_RARE_PILLS = ["玄元聚气丹", "九转凝灵丹"]
ADVENTURE_EQUIPS = ["青锋剑", "玄铁护腕", "平安符", "玄铁剑", "软猬甲", "聚灵佩", "赤霄剑"]

# ==================== NPC 主动互动成本护栏 ====================
NPC_PROACTIVE_AI_BUDGET_PER_TICK = 3   # 每轮世界 tick 最多几次 AI 开口
NPC_PROACTIVE_LOCAL_ONLY_AFTER = True  # 超预算后降级本地模板

# ==================== 目标系统 ====================
GOAL_MAX_ACTIVE = 6
GOAL_SOURCES = ("dao", "omen", "bounty", "sect", "season", "newbie")

# ==================== 转世与道统点 ====================
# 一世结算所得道统点：基础 + 境界贡献 + 功德加成 - 业力折损，单世封顶
LEGACY_BASE_POINTS = 1
LEGACY_PER_TIER = 2
LEGACY_MERIT_DIVISOR = 50
LEGACY_SIN_DIVISOR = 100
LEGACY_SIN_PENALTY_MAX = 3
LEGACY_MAX_PER_LIFE = 25
# 快速送死冷却：窗口内死亡次数过多则道统点减半（防自杀刷点）
LEGACY_SUICIDE_WINDOW_SECONDS = 3600.0
LEGACY_SUICIDE_THRESHOLD = 3
LEGACY_SUICIDE_PENALTY = 0.5
# 每次转世最多购买的加成项数（防滚雪球）
LEGACY_MAX_BOOSTS_PER_LIFE = 3
# 转世消费目录（成本/效果）
LEGACY_BOOSTS = {
    "stones": {
        "name": "出身灵石",
        "cost": 1,
        "desc": "降生时储物袋多 150 块灵石，便于拜山或购阵盘。",
    },
    "lifespan": {
        "name": "延寿道体",
        "cost": 2,
        "desc": "降生自然寿元额外 +8 岁，大限稍缓。",
    },
    "root": {
        "name": "洗练灵根",
        "cost": 4,
        "desc": "灵根吸收效率 +0.25（有上限），修炼更顺。",
    },
    "skill": {
        "name": "传承功法",
        "cost": 2,
        "desc": "前世道统残篇化入识海，开局自带一门额外法门。",
    },
}

# ==================== 境界与寿元配置 ====================
REALM_NAMES = [
    "凡人",       # 0
    "练气期",     # 1
    "筑基期",     # 2
    "金丹期",     # 3
    "元婴期",     # 4
    "化神期",     # 5
    "炼虚期",     # 6
    "合体期",     # 7
    "大乘期",     # 8
    "渡劫飞升"    # 9
]

SUB_TIER_NAMES = ["初期", "中期", "后期", "圆满"]

REALM_EXP_REQUIRED = {
    # 前期压缩：让新玩家尽快体会「升级→突破」；高境界仍保持长线
    1: 600,        # 练气：满有效 24h 闭关约 1～1.5 个小阶
    2: 8000,       # 筑基
    3: 50000,      # 金丹
    4: 200000,     # 元婴
    5: 800000,     # 化神
    6: 2500000,    # 炼虚
    7: 8000000,    # 合体
    8: 20000000,   # 大乘
    9: 60000000    # 渡劫
}

BREAKTHROUGH_LIFESPAN_GAIN = {
    1: (10, 20),    # 凡人 -> 练气
    2: (25, 45),    # 练气 -> 筑基 (四九天劫)
    3: (50, 90),    # 筑基 -> 金丹 (六九雷劫)
    4: (100, 180),  # 金丹 -> 元婴 (九九大劫+心魔)
    5: (200, 350),  # 元婴 -> 化神
    6: (400, 700),  # 化神 -> 炼虚
    7: (800, 1500), # 炼虚 -> 合体
    8: (2000, 5000),# 合体 -> 大乘
    9: (99999, 99999) # 飞升跳出三界
}

BASE_BREAKTHROUGH_PROB = {
    1: 0.80,  # 引气入体
    2: 0.35,  # 筑基天劫
    3: 0.20,  # 金丹雷劫
    4: 0.10,  # 元婴大劫
    5: 0.05,  # 化神
    6: 0.03,  # 炼虚
    7: 0.02,  # 合体
    8: 0.01,  # 大乘
    9: 0.005  # 飞升
}

# ==================== 因果与业力配置 ====================
KARMA_KILL_SAME_TIER = 50
KARMA_KILL_LOWER_TIER = 120
BLOOD_MARK_DURATION_SECONDS = 3 * 86400

# 新手庇护：入世 72 现实小时且境界 ≤ 筑基初，不可被攻击/主动伤人
NEWBIE_PROTECTION_HOURS = 72.0
NEWBIE_MAX_TIER = 2          # 练气/筑基
NEWBIE_MAX_SUB_TIER = 0      # 筑基初期

# ==================== 悬赏与复仇 ====================
BOUNTY_MIN_REWARD = 20
BOUNTY_MAX_REWARD = 5000
BOUNTY_FEE_RATE = 0.10          # 挂赏手续费（坊市抽成）
BOUNTY_ANON_EXTRA_FEE = 0.05    # 匿名挂赏额外抽成
BOUNTY_ACTIVE_HOURS = 72.0      # 悬赏有效期（现实小时）
BOUNTY_HUNTER_MERIT = 15        # 领赏猎手额外功德（除凶）
BOUNTY_MAX_PER_TARGET = 5       # 同一目标最多并存悬赏数
# 因果链类型
KARMA_LINK_TYPES = ("仇", "恩", "师徒", "宗门")


# ==================== 修仙界地理大区与灵脉福地表 ====================
# 包含区域划分、管辖势力、灵气浓度倍率、安全大阵与租金
WORLD_LOCATIONS = {
    # --- 东荒·青州 ---
    "青云坊市客栈": {
        "region": "东荒·青州",
        "sect": "四海散修商会",
        "density": 1.0,
        "is_safe": True,
        "rent_per_hour": 2,
        "desc": "青州第一大散修坊市，受元婴级禁制庇护，绝灵止戈，灵气平稳。"
    },
    "青云宗外门山门": {
        "region": "东荒·青州",
        "sect": "青云宗",
        "density": 1.3,
        "is_safe": True,
        "rent_per_hour": 0,
        "desc": "正道名门青云宗山门，仙鹤腾飞，云海茫茫。散修可在此叩门接受考核。"
    },
    "宗门玄元洞府": {
        "region": "东荒·青州",
        "sect": "青云宗",
        "density": 1.8,
        "is_safe": True,
        "rent_per_hour": 15, # 青云宗弟子免费
        "desc": "青云宗三阶灵脉洞府，护山大阵日夜运转。宗门弟子可免费闭关。"
    },
    "落霞山灵泉": {
        "region": "东荒·青州",
        "sect": "无主野外",
        "density": 1.6,
        "is_safe": False,
        "rent_per_hour": 0,
        "desc": "深山无主微型灵泉，灵气活泼，常有妖兽散修争夺，需阵法自保。"
    },
    # 兼容旧配置别名
    "落霞山灵泉(野外)": {
        "region": "东荒·青州",
        "sect": "无主野外",
        "density": 1.6,
        "is_safe": False,
        "rent_per_hour": 0,
        "desc": "深山无主微型灵泉，灵气活泼，常有妖兽散修争夺，需阵法自保。"
    },

    # --- 中土·万岳 ---
    "万剑仙门峰": {
        "region": "中土·万岳",
        "sect": "万剑仙门",
        "density": 1.5,
        "is_safe": True,
        "rent_per_hour": 0,
        "desc": "插天万刃如巨剑耸立，剑气冲霄，杀伐凛冽，乃万剑仙门总坛。"
    },
    "洗剑池洞天": {
        "region": "中土·万岳",
        "sect": "万剑仙门",
        "density": 2.0,
        "is_safe": True,
        "rent_per_hour": 25, # 万剑弟子免费
        "desc": "万剑仙门四阶庚金剑脉，池水皆为纯阳剑气所化，淬体悟道绝佳。"
    },

    # --- 西陲·幽冥渊 ---
    "九幽天魔宗坛": {
        "region": "西陲·幽冥渊",
        "sect": "九幽天魔宗",
        "density": 1.6,
        "is_safe": True,
        "rent_per_hour": 0,
        "desc": "魔云遮日，骷髅为殿，魔道巨擘盘踞之所，唯强者可入。"
    },
    "黑风绝渊": {
        "region": "西陲·幽冥渊",
        "sect": "九幽天魔宗",
        "density": 2.5,
        "is_safe": False,
        "rent_per_hour": 0,
        "desc": "极阴极煞古战场绝渊，九幽魔宗外围重地，无主法外凶域，魔气狂暴！"
    },
    # 兼容旧配置别名
    "黑风绝渊(大凶)": {
        "region": "西陲·幽冥渊",
        "sect": "九幽天魔宗",
        "density": 2.5,
        "is_safe": False,
        "rent_per_hour": 0,
        "desc": "极阴极煞古战场绝渊，九幽魔宗外围重地，无主法外凶域，魔气狂暴！"
    },

    # --- 海外·乱星海 ---
    "万星古岛": {
        "region": "海外·乱星海",
        "sect": "无主绝地",
        "density": 3.0,
        "is_safe": False,
        "rent_per_hour": 0,
        "desc": "海天浩渺，上古真仙遗迹残址，五阶狂暴灵脉，大凶大机缘共存之地！"
    }
}

# ==================== 天下仙门与宗门阵营配置 ====================
SECTS_CONFIG = {
    "青云宗": {
        "name": "青云宗",
        "alignment": "正道名门",
        "desc": "道法自然，清静修身，门规森严，禁止同道相残。坐拥东荒三阶灵脉。",
        "headquarters": "青云宗外门山门",
        "cave_location": "宗门玄元洞府",
        "req_dao_heart": 60,
        "max_sin": 30,
        "monthly_salary": 25,
        "starter_array": "一阶青木迷踪阵",
        "rules_tip": "道心需≥60，业力需<30且无血煞，同门相残将遭执法堂追杀！"
    },
    "万剑仙门": {
        "name": "万剑仙门",
        "alignment": "杀伐中立",
        "desc": "以剑入道，宁折不弯。门人皆擅杀伐御剑，攻守兼备，以战养战。",
        "headquarters": "万剑仙门峰",
        "cave_location": "洗剑池洞天",
        "req_dao_heart": 70,
        "max_sin": 100,
        "monthly_salary": 30,
        "starter_array": "一阶庚金剑煞阵",
        "rules_tip": "道心需≥70或身具金/雷灵根，入门战力攻伐提升20%！"
    },
    "九幽天魔宗": {
        "name": "九幽天魔宗",
        "alignment": "魔道巨擘",
        "desc": "弱肉强食，胜者为尊。盘踞极煞绝渊，允许同门夺宝，唯力是从。",
        "headquarters": "九幽天魔宗坛",
        "cave_location": "黑风绝渊",
        "req_dao_heart": 0,
        "min_sin": 40,
        "monthly_salary": 35,
        "starter_array": "一阶白骨戮仙阵",
        "rules_tip": "业力需≥40（双手沾血），杀人不损道心，但天劫威力增加20%！"
    },
    "四海散修商会": {
        "name": "四海散修商会",
        "alignment": "散修同盟",
        "desc": "无拘无束的散修中立商会，一切以灵石说话，自由自在，不沾因果。",
        "headquarters": "青云坊市客栈",
        "cave_location": "青云坊市客栈",
        "req_dao_heart": 0,
        "monthly_salary": 0,
        "starter_array": None,
        "rules_tip": "无任何门槛，无月俸，无免费洞府，自食其力。"
    }
}

# ==================== 坊市交易与寄存 ====================
MARKET_DEPOSIT_FEE_RATE = 0.05   # 寄存保管费（存入时抽）
MARKET_WITHDRAW_FEE_RATE = 0.0   # 取出不再收费
MARKET_SELL_BACK_RATE = 0.50     # 回收给商会的折扣
MARKET_LISTING_FEE_RATE = 0.10   # 玩家挂单手续费
MARKET_MAX_LISTINGS = 8          # 单人同时挂单上限

# ---- 拍卖行 ----
AUCTION_DURATION_MIN = 120       # 拍卖时长（现实分钟）
AUCTION_MIN_INCREMENT = 1        # 最低加价（另有 5% 比例步长取大）
AUCTION_SETTLE_FEE_RATE = 0.05   # 成交后向卖家抽成
AUCTION_MAX_LOTS = 5             # 单人同时上拍上限

# ---- 当面交易 ----
TRADE_TIMEOUT_MIN = 10           # 会话超时（现实分钟）

# ---- NPC 专柜态度系数 ----
NPC_PRICE_FRIENDLY_BUY = 0.90
NPC_PRICE_NEUTRAL_BUY = 1.00
NPC_PRICE_HOSTILE_BUY = 1.20
NPC_PRICE_FRIENDLY_SELL = 1.10
NPC_PRICE_NEUTRAL_SELL = 1.00
NPC_PRICE_HOSTILE_SELL = 0.80
NPC_ATTITUDE_FRIENDLY = 40
NPC_ATTITUDE_HOSTILE = -40

# ==================== 世界频道 / GM / 事件链 / 传说 ====================
WORLD_MSG_MAX = 200
WORLD_MSG_TTL_H = 2.0
WORLD_MSG_PER_MIN = 6
CHANNEL_KILL_MIN_TIER = 3
CHANNEL_AUCTION_MIN_PRICE = 500
CHANNEL_TRADE_MIN_SUM = 800
# GM Token：.env 设 GM_TOKEN=xxx；/gm <token> <文案>
GM_TOKEN = os.getenv("GM_TOKEN", "").strip()
LEGEND_MAX = 80
EVENT_CHAIN_MAX_ACTIVE_GLOBAL = 8
EVENT_CHAIN_TIMEOUT_MIN = 30
EVENT_CHAIN_TRIGGER_TRAVEL = 0.08
EVENT_CHAIN_TRIGGER_ADVENTURE = 0.10
# 商会固定货单：kind = array/pill/material
ITEM_CATALOG = {
    "一阶青木迷踪阵": {"kind": "array", "price": 120, "desc": "一阶护道阵盘，野外闭关可撑罡气。"},
    "一阶庚金剑煞阵": {"kind": "array", "price": 180, "desc": "攻伐阵盘，结界带反击。"},
    "一阶白骨戮仙阵": {"kind": "array", "price": 200, "desc": "魔道凶阵，业力深者用之更烈。"},
    # 丹药：grade 品阶；pill_exp_mult = 下次闭关修为加成（越高越强，也越贵）
    "聚气丹": {
        "kind": "pill", "price": 40, "grade": "凡品", "pill_exp_mult": 0.15,
        "desc": "凡品。下次闭关修为 +15%，出关耗尽（本世限 1 次）。",
    },
    "玄元聚气丹": {
        "kind": "pill", "price": 180, "grade": "人品", "pill_exp_mult": 0.30,
        "desc": "人品。下次闭关修为 +30%，出关耗尽（本世限 1 次）。",
    },
    "九转凝灵丹": {
        "kind": "pill", "price": 520, "grade": "地品", "pill_exp_mult": 0.50,
        "desc": "地品。下次闭关修为 +50%，出关耗尽（本世限 1 次）。",
    },
    "筑基丹": {"kind": "pill", "price": 150, "grade": "人品", "desc": "冲击筑基天劫时可提升成功率。"},
    "回春露": {
        "kind": "pill", "price": 22, "grade": "凡品", "pill_exp_mult": 0.08,
        "heal_lifespan": 1.0,
        "desc": "凡品伤药。下次闭关 +8% 修为，并回春 1 岁寿元（比聚气丹便宜，加成更弱）。",
    },
    "妖兽内丹": {"kind": "material", "price": 80, "desc": "炼丹炼器材料，亦可直接换灵石。"},
    "百年灵芝": {"kind": "material", "price": 55, "desc": "温养道基的药材。"},
    # 装备：slot=weapon|armor|trinket；grade 品阶；power_bonus 战力加成/件
    "青锋剑": {"kind": "equip", "slot": "weapon", "grade": "凡品", "power_bonus": 0.03, "price": 220,
        "desc": "凡品法剑。战力 +3%。"},
    "玄铁护腕": {"kind": "equip", "slot": "armor", "grade": "凡品", "power_bonus": 0.03, "price": 160,
        "desc": "凡品护腕。战力 +3%。"},
    "平安符": {"kind": "equip", "slot": "trinket", "grade": "凡品", "power_bonus": 0.02, "price": 80,
        "desc": "凡品护身符。战力 +2%。"},
    "玄铁剑": {"kind": "equip", "slot": "weapon", "grade": "人品", "power_bonus": 0.05, "price": 480,
        "desc": "人品重剑。战力 +5%。"},
    "软猬甲": {"kind": "equip", "slot": "armor", "grade": "人品", "power_bonus": 0.05, "price": 420,
        "desc": "人品软甲。战力 +5%。"},
    "聚灵佩": {"kind": "equip", "slot": "trinket", "grade": "人品", "power_bonus": 0.04, "price": 360,
        "desc": "人品玉佩。战力 +4%。"},
    "赤霄剑": {"kind": "equip", "slot": "weapon", "grade": "地品", "power_bonus": 0.08, "price": 1200,
        "desc": "地品飞剑。战力 +8%。"},
    "玄龟甲": {"kind": "equip", "slot": "armor", "grade": "地品", "power_bonus": 0.08, "price": 1100,
        "desc": "地品玄甲。战力 +8%。"},
    "避尘珠": {"kind": "equip", "slot": "trinket", "grade": "地品", "power_bonus": 0.06, "price": 900,
        "desc": "地品宝珠。战力 +6%。"},
    "斩仙剑": {"kind": "equip", "slot": "weapon", "grade": "天品", "power_bonus": 0.12, "price": 5000,
        "desc": "天品古剑。战力 +12%（极稀有）。"},
    "藏宝图": {"kind": "map", "price": 300, "desc": "残破藏宝图，标注某处洞天（后续可挖宝）。"},
}

# ==================== 世界事件（机缘/危机）====================
# 每次外出/出关后触发事件的概率
EVENT_TRIGGER_CHANCE = 0.45
# 事件类别权重
EVENT_WEIGHTS = {
    "fortune": 45,  # 机缘
    "crisis": 35,   # 危机
    "omen": 20,     # 异象（轻叙事/轻微数值）
}
# 规则引擎对 AI 提案的效果钳制（防幻觉超模）
EVENT_EFFECT_CAPS = {
    "exp": 800,
    "stones_gain": 300,
    "stones_lose": 200,
    "lifespan_gain": 15.0,
    "lifespan_burn": 8.0,
    "sin": 40,
    "merit": 40,
    "dao_heart": -20,  # 下限变化幅度（绝对值）
}
# AI 判定渡劫时，允许在规则成功率附近的抖动幅度
TRIBULATION_AI_JITTER = 0.15

# ==================== AI 门禁与审计 ====================
# 单位时间（现实秒）内 AI 可改数值的次数上限（防刷）
GATE_RATE_WINDOW_SECONDS = 60.0
GATE_RATE_MAX_MUTATIONS = 20
# 提案中人物引用必须已在事实包 known_ids 内；spawn 需走白名单
GATE_ALLOW_SPAWN = True
GATE_SPAWN_MAX_PER_PROPOSAL = 1
# 审计日志路径
AUDIT_LOG_PATH = DATA_DIR / "ai_audit.jsonl"

# ==================== 局域网服 ====================
LAN_HOST = os.getenv("LAN_HOST", "0.0.0.0")
LAN_PORT = int(os.getenv("LAN_PORT", "8765"))
# 后台 NPC 议程 tick 间隔（秒）；0 = 关闭自动 tick
NPC_TICK_INTERVAL_SECONDS = float(os.getenv("NPC_TICK_INTERVAL", "120"))

# ==================== 天道导演 M1（AI 主导走向） ====================
# tick 循环里导演侧的墙钟闸（比 NPC tick 更疏）
DIRECTOR_TICK_INTERVAL_SECONDS = float(os.getenv("DIRECTOR_TICK_INTERVAL", "600"))
# 两次成功 run 之间的最小间隔（force 可越过）
DIRECTOR_MIN_INTERVAL_SECONDS = float(os.getenv("DIRECTOR_MIN_INTERVAL", "480"))
# 同时最多活跃指令
DIRECTOR_MAX_ACTIVE = int(os.getenv("DIRECTOR_MAX_ACTIVE", "3"))
# 单条指令默认存活
DIRECTOR_TTL_SECONDS = float(os.getenv("DIRECTOR_TTL", "3600"))
# 机缘目标最多投给几名在线玩家
DIRECTOR_GOAL_FANOUT = int(os.getenv("DIRECTOR_GOAL_FANOUT", "5"))
# 指令类型白名单
DIRECTOR_TYPES = frozenset(
    {
        "omen",
        "secret_realm_pressure",
        "blood_tide",
        "sect_tension",
        "calamity_forecast",
    }
)
# 提案 effects 强制剥离的数值权威键
DIRECTOR_STRIP_EFFECT_KEYS = frozenset(
    {
        "exp",
        "stones",
        "lifespan_years",
        "sin",
        "merit",
        "dao_heart",
        "power",
        "death",
        "kill",
        "target_player",
        "item",
        "skill",
        "spawn",
    }
)

# ==================== NPC 议程 ====================
# 每次世界 tick 最多推进多少名 NPC（控成本）
NPC_TICK_MAX = 5
# NPC 行动冷却（现实秒），防刷屏
NPC_COOLDOWN_SECONDS = 180.0
# 议程类型与默认优先级
NPC_AGENDA_TYPES = {
    "revenge": "寻仇",
    "treasure": "夺宝",
    "avoid": "避劫",
    "patrol": "游历",
    "mentor": "收徒",
}
# 初始议程种子（按 NPC 名）
NPC_SEED_AGENDAS = {
    "血刀老祖": {"type": "revenge", "target_hint": "正道修士", "note": "血债累累，伺机报复"},
    "陆仁贾": {"type": "avoid", "target_hint": "", "note": "散修求稳，避开凶域"},
    "云鹤道人": {"type": "patrol", "target_hint": "", "note": "巡查东荒，除魔卫道"},
}


# ==================== AI 模型接口配置 ====================
# 支持任何 OpenAI 兼容协议的大模型（如 DeepSeek, 阿里通义千问, 智谱, 本地 Ollama 等）
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# 是否走本机 CC Switch（Claude Code 本地代理）
# USE_CCSWITCH=1：从 ~/.claude/settings.json 读 ANTHROPIC_BASE_URL / 模型，调 /v1/messages
USE_CCSWITCH = os.getenv("USE_CCSWITCH", "0") in ("1", "true", "True")


def load_ccswitch_env() -> Dict[str, str]:
    """读取 Claude Code / CC Switch 写入的 settings.json（只读）"""
    import json
    from pathlib import Path

    p = Path.home() / ".claude" / "settings.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return dict(data.get("env") or {})
    except Exception:
        return {}


def ccswitch_runtime() -> Dict[str, str]:
    """USE_CCSWITCH 时的运行时参数；空 dict 表示未启用或读失败"""
    if not USE_CCSWITCH:
        return {}
    env = load_ccswitch_env()
    base = env.get("ANTHROPIC_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL") or ""
    # 优先 sonnet 映射名（cc-switch 常把真实模型写在 *_MODEL_NAME）
    model = (
        os.getenv("CCSWITCH_MODEL")
        or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL_NAME")
        or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
        or "claude-sonnet-4-6"
    )
    token = env.get("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_AUTH_TOKEN") or "PROXY_MANAGED"
    if not base:
        return {}
    return {
        "base": base.rstrip("/"),
        "model": model,
        "token": token,
    }


# ==================== AI 运行模式 ====================
# 正式体验：必须有服务器 AI，无 Key 时核心交互直接拒绝（不是静默套话）
# 开发/单测：ALLOW_LOCAL_AI=1 时允许本地模板降级
AI_REQUIRED = os.getenv("AI_REQUIRED", "1") not in ("0", "false", "False")
ALLOW_LOCAL_AI = os.getenv("ALLOW_LOCAL_AI", "0") in ("1", "true", "True")


def ai_available() -> bool:
    if USE_CCSWITCH and ccswitch_runtime().get("base"):
        return True
    return bool(LLM_API_KEY)


def local_ai_allowed() -> bool:
    """是否允许本地模板降级（仅开发/测试）"""
    return ALLOW_LOCAL_AI


def ai_unavailable_message() -> str:
    return (
        "【天道未启】未配置服务器 AI（LLM_API_KEY），"
        "交谈/言行/天命裁决无法进行。请在 .env 配置 LLM_API_BASE、LLM_API_KEY、LLM_MODEL。"
    )

