"""
内容包：奇遇/日环/师门/结义/兑换/环境传闻（纯数据，零 AI）
效果务必落在 EVENT_EFFECT_CAPS 内。
"""
from __future__ import annotations

from typing import Any, Dict, List

# ==================== 奇遇模板（≥20，每条 2 步） ====================
EVENT_CHAIN_TEMPLATES: List[Dict[str, Any]] = [
    {
        "kind": "opportunity",
        "title": "残碑悟道",
        "steps": [
            {
                "prompt": "荒谷残碑半埋苔中，隐有道纹流转。",
                "choices": [
                    {"id": "1", "label": "静坐观碑", "effects": {"exp": 80}},
                    {"id": "2", "label": "强行拓印", "effects": {"exp": 140, "lifespan_years": -1.0, "sin": 5}},
                    {"id": "3", "label": "绕道而行", "effects": {}},
                ],
            },
            {
                "prompt": "碑底忽现一行小字……",
                "choices": [
                    {"id": "1", "label": "默记于心", "effects": {"exp": 40}},
                    {"id": "2", "label": "毁去字迹", "effects": {"sin": 8}},
                ],
            },
        ],
    },
    {
        "kind": "crisis",
        "title": "黑市兜售",
        "steps": [
            {
                "prompt": "巷尾有人兜售来历不明的玉匣，要价极低。",
                "choices": [
                    {"id": "1", "label": "买下", "effects": {"stones": -50, "exp": 60}},
                    {"id": "2", "label": "报与巡守", "effects": {"merit": 10}},
                    {"id": "3", "label": "作罢", "effects": {}},
                ],
            },
            {
                "prompt": "玉匣微温，似有活物……",
                "choices": [
                    {"id": "1", "label": "打开", "effects": {"exp": 100, "lifespan_years": -0.5}},
                    {"id": "2", "label": "封印丢弃", "effects": {"merit": 5}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "旧友托孤",
        "steps": [
            {
                "prompt": "故人临终托你护送幼童投亲。",
                "choices": [
                    {"id": "1", "label": "应下", "effects": {"merit": 15}},
                    {"id": "2", "label": "婉拒", "effects": {"dao_heart": -3}},
                    {"id": "3", "label": "谋其遗财", "effects": {"stones": 120, "sin": 20}},
                ],
            },
            {
                "prompt": "途中黑衣人拦路，要那孩子。",
                "choices": [
                    {"id": "1", "label": "死战不退", "effects": {"exp": 90, "lifespan_years": -1.5}},
                    {"id": "2", "label": "交人保命", "effects": {"sin": 12}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "山神庙夜雨",
        "steps": [
            {
                "prompt": "破庙夜雨，神像眼中似有泪痕。",
                "choices": [
                    {"id": "1", "label": "上香祝祷", "effects": {"merit": 8, "dao_heart": 3}},
                    {"id": "2", "label": "搜刮供桌", "effects": {"stones": 60, "sin": 10}},
                    {"id": "3", "label": "檐下避雨即走", "effects": {}},
                ],
            },
            {
                "prompt": "雨歇时，神像底座露出暗格。",
                "choices": [
                    {"id": "1", "label": "打开暗格", "effects": {"exp": 70}},
                    {"id": "2", "label": "重新封好", "effects": {"merit": 6}},
                ],
            },
        ],
    },
    {
        "kind": "crisis",
        "title": "夺舍残魂",
        "steps": [
            {
                "prompt": "古玉佩中传来低语，自称上古残魂欲借体一用。",
                "choices": [
                    {"id": "1", "label": "严词拒绝", "effects": {"dao_heart": 5}},
                    {"id": "2", "label": "假意应承", "effects": {"exp": 50, "sin": 5}},
                    {"id": "3", "label": "摔碎玉佩", "effects": {"merit": 8}},
                ],
            },
            {
                "prompt": "残魂暴起，直冲识海！",
                "choices": [
                    {"id": "1", "label": "死守灵台", "effects": {"exp": 80, "lifespan_years": -1.0}},
                    {"id": "2", "label": "放开心神", "effects": {"exp": 120, "sin": 15, "dao_heart": -8}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "灵泉争饮",
        "steps": [
            {
                "prompt": "山谷灵泉将涸，数名散修对峙。",
                "choices": [
                    {"id": "1", "label": "出手强夺", "effects": {"exp": 100, "sin": 18}},
                    {"id": "2", "label": "调停均分", "effects": {"exp": 50, "merit": 12}},
                    {"id": "3", "label": "转身离开", "effects": {}},
                ],
            },
            {
                "prompt": "泉底忽现一枚温润玉简。",
                "choices": [
                    {"id": "1", "label": "就地参悟", "effects": {"exp": 60}},
                    {"id": "2", "label": "带走转卖", "effects": {"stones": 90}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "剑冢残鸣",
        "steps": [
            {
                "prompt": "荒冢万剑残骸，某一柄仍在轻颤。",
                "choices": [
                    {"id": "1", "label": "拔剑", "effects": {"exp": 90, "lifespan_years": -0.8}},
                    {"id": "2", "label": "祭拜", "effects": {"merit": 10}},
                    {"id": "3", "label": "离去", "effects": {}},
                ],
            },
            {
                "prompt": "剑鸣引来看守残念。",
                "choices": [
                    {"id": "1", "label": "论剑", "effects": {"exp": 70}},
                    {"id": "2", "label": "献上灵石", "effects": {"stones": -40, "exp": 100}},
                ],
            },
        ],
    },
    {
        "kind": "crisis",
        "title": "毒瘴林",
        "steps": [
            {
                "prompt": "林中瘴气翻涌，同行者面色发青。",
                "choices": [
                    {"id": "1", "label": "以真元护体硬闯", "effects": {"exp": 60, "lifespan_years": -1.2}},
                    {"id": "2", "label": "绕开", "effects": {}},
                    {"id": "3", "label": "采瘴边灵草", "effects": {"stones": 40, "sin": 3}},
                ],
            },
            {
                "prompt": "深处有人求救。",
                "choices": [
                    {"id": "1", "label": "救", "effects": {"merit": 14, "exp": 40}},
                    {"id": "2", "label": "不救", "effects": {"dao_heart": -5}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "卦摊问命",
        "steps": [
            {
                "prompt": "坊市卦师盯着你看了半晌：「道友印堂发黑。」",
                "choices": [
                    {"id": "1", "label": "付钱听卦", "effects": {"stones": -20, "dao_heart": 4}},
                    {"id": "2", "label": "拂袖而去", "effects": {}},
                    {"id": "3", "label": "掀他摊子", "effects": {"sin": 8, "stones": 30}},
                ],
            },
            {
                "prompt": "卦师低语一个方向。",
                "choices": [
                    {"id": "1", "label": "依言而行", "effects": {"exp": 55}},
                    {"id": "2", "label": "反其道行之", "effects": {"exp": 30, "dao_heart": -2}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "商队护卫",
        "steps": [
            {
                "prompt": "商队重金聘临时护卫，路线经荒原。",
                "choices": [
                    {"id": "1", "label": "接下", "effects": {"stones": 70}},
                    {"id": "2", "label": "拒绝", "effects": {}},
                    {"id": "3", "label": "里应外合", "effects": {"stones": 150, "sin": 25}},
                ],
            },
            {
                "prompt": "夜半果然遇袭。",
                "choices": [
                    {"id": "1", "label": "力战", "effects": {"exp": 85, "lifespan_years": -0.6}},
                    {"id": "2", "label": "丢货逃跑", "effects": {"dao_heart": -6}},
                ],
            },
        ],
    },
    {
        "kind": "crisis",
        "title": "井中女声",
        "steps": [
            {
                "prompt": "枯井传来女子歌声，闻者恍惚。",
                "choices": [
                    {"id": "1", "label": "探头查看", "effects": {"exp": 40, "lifespan_years": -1.0}},
                    {"id": "2", "label": "封井", "effects": {"merit": 12}},
                    {"id": "3", "label": "装作未闻", "effects": {}},
                ],
            },
            {
                "prompt": "井壁刻着一行血字。",
                "choices": [
                    {"id": "1", "label": "拓下带走", "effects": {"exp": 50, "sin": 6}},
                    {"id": "2", "label": "抹去", "effects": {"merit": 5}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "丹房失火",
        "steps": [
            {
                "prompt": "坊市丹房走水，掌柜哀求救火。",
                "choices": [
                    {"id": "1", "label": "出手", "effects": {"merit": 10, "exp": 30}},
                    {"id": "2", "label": "趁乱取丹", "effects": {"stones": 80, "sin": 16}},
                    {"id": "3", "label": "围观", "effects": {}},
                ],
            },
            {
                "prompt": "火场中滚出一只药鼎。",
                "choices": [
                    {"id": "1", "label": "带走", "effects": {"stones": 40}},
                    {"id": "2", "label": "还给掌柜", "effects": {"merit": 8}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "论道茶会",
        "steps": [
            {
                "prompt": "青崖茶会，诸修论道，有人出言挑衅。",
                "choices": [
                    {"id": "1", "label": "据理力争", "effects": {"dao_heart": 6, "exp": 30}},
                    {"id": "2", "label": "沉默饮茶", "effects": {"dao_heart": 2}},
                    {"id": "3", "label": "拍案掀桌", "effects": {"sin": 10, "exp": 20}},
                ],
            },
            {
                "prompt": "会后有人邀你密室一叙。",
                "choices": [
                    {"id": "1", "label": "前往", "effects": {"exp": 70}},
                    {"id": "2", "label": "婉拒", "effects": {"merit": 4}},
                ],
            },
        ],
    },
    {
        "kind": "crisis",
        "title": "妖市假丹",
        "steps": [
            {
                "prompt": "妖市摊位上的「破境丹」香气逼真。",
                "choices": [
                    {"id": "1", "label": "买下", "effects": {"stones": -60}},
                    {"id": "2", "label": "识破闹事", "effects": {"merit": 9}},
                    {"id": "3", "label": "暗中调包", "effects": {"stones": 50, "sin": 14}},
                ],
            },
            {
                "prompt": "摊主袖中寒光一闪。",
                "choices": [
                    {"id": "1", "label": "迎战", "effects": {"exp": 95, "lifespan_years": -0.7}},
                    {"id": "2", "label": "认栽赔罪", "effects": {"stones": -30, "dao_heart": -3}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "古井投钱",
        "steps": [
            {
                "prompt": "村口古井传说投灵石可问前程。",
                "choices": [
                    {"id": "1", "label": "投十块", "effects": {"stones": -10, "dao_heart": 3}},
                    {"id": "2", "label": "不投", "effects": {}},
                    {"id": "3", "label": "捞别人投的", "effects": {"stones": 25, "sin": 7}},
                ],
            },
            {
                "prompt": "井水倒映出陌生的自己。",
                "choices": [
                    {"id": "1", "label": "凝视", "effects": {"exp": 45, "lifespan_years": -0.4}},
                    {"id": "2", "label": "打碎倒影", "effects": {"dao_heart": 4}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "镖箱惊魂",
        "steps": [
            {
                "prompt": "路遇翻覆镖箱，银两散落，四下无人。",
                "choices": [
                    {"id": "1", "label": "守候失主", "effects": {"merit": 16}},
                    {"id": "2", "label": "卷走", "effects": {"stones": 100, "sin": 18}},
                    {"id": "3", "label": "只取一锭", "effects": {"stones": 20, "sin": 5}},
                ],
            },
            {
                "prompt": "林中传来脚步声。",
                "choices": [
                    {"id": "1", "label": "留下说明", "effects": {"merit": 6}},
                    {"id": "2", "label": "遁走", "effects": {"dao_heart": -4}},
                ],
            },
        ],
    },
    {
        "kind": "crisis",
        "title": "雷木惊枝",
        "steps": [
            {
                "prompt": "雷击古木，树心悬着一枚焦黑果实。",
                "choices": [
                    {"id": "1", "label": "摘下吞服", "effects": {"exp": 110, "lifespan_years": -1.5}},
                    {"id": "2", "label": "收起待查", "effects": {"stones": 35}},
                    {"id": "3", "label": "不碰", "effects": {}},
                ],
            },
            {
                "prompt": "果实忽明忽暗，似在呼吸。",
                "choices": [
                    {"id": "1", "label": "再炼化", "effects": {"exp": 50, "lifespan_years": -0.8}},
                    {"id": "2", "label": "埋入土中", "effects": {"merit": 7}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "琴师问剑",
        "steps": [
            {
                "prompt": "盲眼琴师拦路：「可愿听我一曲，再借剑一观？」",
                "choices": [
                    {"id": "1", "label": "听曲借剑", "effects": {"exp": 55, "dao_heart": 3}},
                    {"id": "2", "label": "拒绝", "effects": {}},
                    {"id": "3", "label": "夺琴", "effects": {"stones": 45, "sin": 12}},
                ],
            },
            {
                "prompt": "曲终，琴师指尖滴血成符。",
                "choices": [
                    {"id": "1", "label": "接符", "effects": {"exp": 65}},
                    {"id": "2", "label": "推辞", "effects": {"merit": 5}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "雪夜借宿",
        "steps": [
            {
                "prompt": "雪夜柴门，老妇愿借宿，却盯着你的行囊。",
                "choices": [
                    {"id": "1", "label": "借宿", "effects": {"lifespan_years": 0.5}},
                    {"id": "2", "label": "露宿", "effects": {"lifespan_years": -0.3}},
                    {"id": "3", "label": "先下手", "effects": {"stones": 70, "sin": 22}},
                ],
            },
            {
                "prompt": "半夜灶下传来铁器轻响。",
                "choices": [
                    {"id": "1", "label": "装睡观察", "effects": {"exp": 40}},
                    {"id": "2", "label": "破门", "effects": {"exp": 75, "sin": 4}},
                ],
            },
        ],
    },
    {
        "kind": "crisis",
        "title": "碑林迷阵",
        "steps": [
            {
                "prompt": "入碑林后原路消失，石碑上的字在改写。",
                "choices": [
                    {"id": "1", "label": "静心破阵", "effects": {"exp": 85, "dao_heart": 4}},
                    {"id": "2", "label": "暴力轰碑", "effects": {"exp": 50, "sin": 10, "lifespan_years": -0.6}},
                    {"id": "3", "label": "坐以待毙", "effects": {"lifespan_years": -1.0}},
                ],
            },
            {
                "prompt": "阵眼处浮着一卷无字书。",
                "choices": [
                    {"id": "1", "label": "以血书之", "effects": {"exp": 70, "lifespan_years": -0.5}},
                    {"id": "2", "label": "弃之", "effects": {}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "渔翁得利",
        "steps": [
            {
                "prompt": "两修相争俱伤，储物袋落在你脚边。",
                "choices": [
                    {"id": "1", "label": "取袋", "effects": {"stones": 90, "sin": 8}},
                    {"id": "2", "label": "救人", "effects": {"merit": 18, "stones": -10}},
                    {"id": "3", "label": "视而不见", "effects": {}},
                ],
            },
            {
                "prompt": "其中一人尚有气息，抓住你的衣角。",
                "choices": [
                    {"id": "1", "label": "喂药", "effects": {"merit": 10, "exp": 35}},
                    {"id": "2", "label": "甩开", "effects": {"dao_heart": -5}},
                ],
            },
        ],
    },
    {
        "kind": "opportunity",
        "title": "灯节猜谜",
        "steps": [
            {
                "prompt": "上元灯节，商会悬谜，中者得奖。",
                "choices": [
                    {"id": "1", "label": "猜谜", "effects": {"stones": 40, "exp": 25}},
                    {"id": "2", "label": "看热闹", "effects": {}},
                    {"id": "3", "label": "顺走灯笼", "effects": {"stones": 15, "sin": 4}},
                ],
            },
            {
                "prompt": "谜底竟是某宗门暗语。",
                "choices": [
                    {"id": "1", "label": "记下", "effects": {"exp": 45}},
                    {"id": "2", "label": "忘掉", "effects": {}},
                ],
            },
        ],
    },
    {
        "kind": "crisis",
        "title": "断桥伏杀",
        "steps": [
            {
                "prompt": "断桥之上，对岸箭矢破空。",
                "choices": [
                    {"id": "1", "label": "硬闯", "effects": {"exp": 100, "lifespan_years": -1.8}},
                    {"id": "2", "label": "跃水", "effects": {"exp": 40, "lifespan_years": -0.5}},
                    {"id": "3", "label": "亮出宗门身份", "effects": {"dao_heart": 2}},
                ],
            },
            {
                "prompt": "箭手现身，竟是旧识。",
                "choices": [
                    {"id": "1", "label": "问缘由", "effects": {"exp": 50}},
                    {"id": "2", "label": "直接了结", "effects": {"sin": 15, "stones": 60}},
                ],
            },
        ],
    },
]

# ==================== 宗门日环主题（≥15） ====================
THEME_POOL: List[Dict[str, Any]] = [
    {"id": "t_explore1", "hook": "explore", "label": "剑冢清剿：外出探险一次（成功）", "lore": "执事道：剑冢妖氛重，去走一遭。"},
    {"id": "t_explore2", "hook": "explore", "label": "药圃巡护：外出探险一次（成功）", "lore": "药圃新栽，恐有妖兽践踏。"},
    {"id": "t_explore3", "hook": "explore", "label": "外围警戒：外出探险一次（成功）", "lore": "山门外围近来不太平。"},
    {"id": "t_explore4", "hook": "explore", "label": "矿脉踏勘：外出探险一次（成功）", "lore": "新矿脉需有修士走一遭。"},
    {"id": "t_explore5", "hook": "explore", "label": "古道清妖：外出探险一次（成功）", "lore": "商队投诉古道有妖。"},
    {"id": "t_donate", "hook": "donate", "label": "库房补给：上交任意货物一件", "lore": "库房见底，尔可有灵材奉上？"},
    {"id": "t_donate2", "hook": "donate", "label": "丹房供料：上交任意货物一件", "lore": "丹房催料甚急。"},
    {"id": "t_visit", "hook": "visit", "label": "山门点卯：亲至本宗总坛", "lore": "掌门有谕，回山听点。"},
    {"id": "t_visit2", "hook": "visit", "label": "祖师堂参拜：亲至本宗总坛", "lore": "朔望参拜，不可缺席。"},
    {"id": "t_hunt", "hook": "hunt", "label": "代天行诛：接下一枚除凶令", "lore": "血煞盈野，宗门欲彰正道。"},
    {"id": "t_hunt2", "hook": "hunt", "label": "缉盗文书：接下一枚除凶令", "lore": "官府与宗门联名缉盗。"},
    {"id": "t_explore6", "hook": "explore", "label": "夜巡后山：外出探险一次（成功）", "lore": "后山夜里有异响。"},
    {"id": "t_visit3", "hook": "visit", "label": "执事召见：亲至本宗总坛", "lore": "执事有话要问你。"},
    {"id": "t_donate3", "hook": "donate", "label": "炼器进料：上交任意货物一件", "lore": "器堂缺一昧辅料。"},
    {"id": "t_explore7", "hook": "explore", "label": "秘境外围：外出探险一次（成功）", "lore": "秘境外围常有流寇。"},
    {"id": "t_hunt3", "hook": "hunt", "label": "除魔卫道：接下一枚除凶令", "lore": "魔修踪迹再现。"},
]

# ==================== 师门任务（≥8） ====================
MASTER_TASKS: List[Dict[str, Any]] = [
    {"id": "herb", "label": "为师采一株【百年灵芝】交来", "need_item": "百年灵芝"},
    {"id": "patrol", "label": "赴本宗总坛巡山一周（迁跃到总坛）", "need_visit": True},
    {"id": "hunt", "label": "接下一枚除凶令（/接除凶）", "need_hunt": True},
    {"id": "herb2", "label": "寻一味【妖兽内丹】献上", "need_item": "妖兽内丹"},
    {"id": "herb3", "label": "取一株【回春露】（可坊市购得）", "need_item": "回春露"},
    {"id": "herb4", "label": "奉上【聚气丹】一枚以供试药", "need_item": "聚气丹"},
    {"id": "patrol2", "label": "回山听训：亲至本宗总坛", "need_visit": True},
    {"id": "hunt2", "label": "为师留意血煞之徒：接除凶令", "need_hunt": True},
    {"id": "herb5", "label": "寻【百年灵芝】佐药（重要）", "need_item": "百年灵芝"},
]

# ==================== 结义任务（≥4） ====================
SWORN_TASKS: List[Dict[str, Any]] = [
    {"id": "joint1", "label": "同场完成一次历练（提交时须同场）", "need_joint": True},
    {"id": "joint2", "label": "并肩立于同一处（提交时同场）", "need_joint": True},
    {"id": "joint3", "label": "肝胆相照：同场交割结义之礼", "need_joint": True},
    {"id": "joint4", "label": "共闯江湖：同场提交结义", "need_joint": True},
]

# ==================== 贡献兑换（≥10） ====================
EXCHANGE_SHOP: Dict[str, int] = {
    "聚气丹": 8,
    "回春露": 5,
    "一阶青木迷踪阵": 40,
    "玄铁护腕": 35,
    "平安符": 12,
    "玄铁剑": 55,
    "软猬甲": 50,
    "聚灵佩": 45,
    "一阶庚金剑煞阵": 70,
    "百年灵芝": 15,
    "妖兽内丹": 18,
    "藏宝图": 25,
}

# streak 解锁稀有
RARE_SHOP: Dict[str, Dict[str, Any]] = {
    "玄元聚气丹": {"price": 80, "need_streak": 3},
    "赤霄剑": {"price": 200, "need_streak": 3},
    "玄龟甲": {"price": 180, "need_streak": 3},
    "九转凝灵丹": {"price": 150, "need_streak": 5},
    "一阶白骨戮仙阵": {"price": 220, "need_streak": 5},
}

# ==================== 环境传闻模板（≥20） ====================
# {loc} {a} {b} 占位
AMBIENT_RUMORS: List[str] = [
    "有人在{loc}见到剑光冲霄，不知是哪位高人路过。",
    "坊间传{loc}夜里有女子哭声，天亮却只余露水。",
    "{a}在酒肆说，{loc}的灵泉这个月淡了许多。",
    "镖局丢了一趟镖，疑是{loc}附近的山贼所为。",
    "{a}与{b}在{loc}擦肩而过，彼此都没正眼看对方。",
    "有人收购{loc}一带的旧符纸，价格高得反常。",
    "传闻{a}闭关走火，又有人说只是在装死。",
    "{b}在告示栏前站了半日，最后叹气离去。",
    "孩童传唱：{loc}井底住着龙王的闺女。",
    "商会提高了{loc}方向的护镖银子。",
    "有人见{a}的剑上多了道新缺口。",
    "{b}最近出手阔绰，不知发了什么横财。",
    "{loc}一带的野狗夜里集体噤声，老猎户说不是好事。",
    "算命的说{loc}当有血光，问谁又不肯说。",
    "{a}把旧洞府让给了{b}，租金低得离谱。",
    "有人在{loc}捡到半张残图，转手卖了八十灵石。",
    "魔修余孽？茶馆里说得有鼻子有眼，却无人敢指认。",
    "{b}发誓要在下月前破境，同门都在赌他成不成。",
    "{loc}的桃花开得反季，丹修们很兴奋。",
    "官府在{loc}贴了海捕文书，画像模糊得认不出人。",
    "{a}的坐骑死了，他一口咬定是被人毒的。",
    "有人说{loc}地底在响，像有东西要拱出来。",
    "{b}拒绝了一门亲事，对方宗门放话要讨说法。",
    "黑市出现一批来路不明的阵盘，成色极好。",
]

# ==================== 炼丹/炼器配方 ====================
RECIPES: List[Dict[str, Any]] = [
    {
        "id": "r_juqi", "name": "聚气丹方", "kind": "pill", "output": "聚气丹",
        "materials": {"百年灵芝": 1}, "stones_fee": 15, "base_rate": 0.75,
        "req_tier": 0, "known_by_default": True, "lore": "最基础的引气丹方。",
    },
    {
        "id": "r_huichun", "name": "回春露方", "kind": "pill", "output": "回春露",
        "materials": {"百年灵芝": 1}, "stones_fee": 8, "base_rate": 0.85,
        "req_tier": 0, "known_by_default": True, "lore": "伤药，温养为主。",
    },
    {
        "id": "r_qingfeng", "name": "青锋剑谱", "kind": "equip", "output": "青锋剑",
        "materials": {"妖兽内丹": 1}, "stones_fee": 40, "base_rate": 0.70,
        "req_tier": 1, "known_by_default": True, "lore": "凡品法剑，需妖骨淬锋。",
    },
    {
        "id": "r_xuantie_wan", "name": "玄铁护腕图", "kind": "equip", "output": "玄铁护腕",
        "materials": {"妖兽内丹": 1}, "stones_fee": 30, "base_rate": 0.75,
        "req_tier": 0, "known_by_default": True, "lore": "玄铁锻腕。",
    },
    {
        "id": "r_pingan", "name": "平安符制法", "kind": "equip", "output": "平安符",
        "materials": {"百年灵芝": 1}, "stones_fee": 10, "base_rate": 0.90,
        "req_tier": 0, "known_by_default": True, "lore": "最简护身符。",
    },
    {
        "id": "r_xuanyuan", "name": "玄元聚气丹方", "kind": "pill", "output": "玄元聚气丹",
        "materials": {"百年灵芝": 2, "妖兽内丹": 1}, "stones_fee": 60, "base_rate": 0.55,
        "req_tier": 1, "known_by_default": False, "lore": "人品丹方，药力更厚。",
    },
    {
        "id": "r_jiuzhuan", "name": "九转凝灵丹方", "kind": "pill", "output": "九转凝灵丹",
        "materials": {"百年灵芝": 3, "妖兽内丹": 2}, "stones_fee": 150, "base_rate": 0.40,
        "req_tier": 2, "known_by_default": False, "lore": "地品丹方，九转方成。",
    },
    {
        "id": "r_zhuji", "name": "筑基丹方", "kind": "pill", "output": "筑基丹",
        "materials": {"百年灵芝": 2, "妖兽内丹": 1}, "stones_fee": 80, "base_rate": 0.50,
        "req_tier": 1, "known_by_default": False, "lore": "冲筑基天劫辅药。",
    },
    {
        "id": "r_xuantie_jian", "name": "玄铁剑谱", "kind": "equip", "output": "玄铁剑",
        "materials": {"妖兽内丹": 2}, "stones_fee": 90, "base_rate": 0.55,
        "req_tier": 1, "known_by_default": False, "lore": "人品重剑。",
    },
    {
        "id": "r_ruanwei", "name": "软猬甲图", "kind": "equip", "output": "软猬甲",
        "materials": {"妖兽内丹": 2, "百年灵芝": 1}, "stones_fee": 85, "base_rate": 0.55,
        "req_tier": 1, "known_by_default": False, "lore": "内甲，倒刺防身。",
    },
    {
        "id": "r_chixiao", "name": "赤霄剑谱（残）", "kind": "equip", "output": "赤霄剑",
        "materials": {"妖兽内丹": 3, "百年灵芝": 2}, "stones_fee": 200, "base_rate": 0.35,
        "req_tier": 2, "known_by_default": False, "lore": "地品法剑残谱，极难成。",
    },
    {
        "id": "r_xuangui", "name": "玄龟甲图（残）", "kind": "equip", "output": "玄龟甲",
        "materials": {"妖兽内丹": 3, "百年灵芝": 2}, "stones_fee": 180, "base_rate": 0.35,
        "req_tier": 2, "known_by_default": False, "lore": "地品内甲残图。",
    },
]

ALCHEMY_MATERIAL_POOL = ["百年灵芝", "妖兽内丹"]
