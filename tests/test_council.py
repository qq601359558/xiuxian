"""F08 长老议政：议题轮转/立场推导/投票/游说/多数决结算幂等/边界/双端/旧档兼容"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from core.clock import WorldClock
from core.models import CharacterStatus
from core.council import (
    CouncilEngine,
    stance_score,
    stance_of,
    COUNCIL_TOPICS,
    COUNCIL_VOTE_WINDOW_SECONDS,
    COUNCIL_INTERVAL_SECONDS,
    COUNCIL_LOBBY_BASE_COST,
    COUNCIL_LOBBY_MAX_PER_ELDER,
    COUNCIL_LOBBY_MAX_PER_PLAYER,
    COUNCIL_EFFECT_CAPS,
)
from storage.db import (
    CharacterRepository,
    WorldStateRepository,
    NpcAgendaRepository,
    NpcMindRepository,
    init_db,
)
from server.world import WORLD

WORLD.stop_tick()
init_db()

T0 = 1_900_000_000.0  # 注入时刻（确定性时间轴）
QY = "青云宗"
WJ = "万剑仙门"
JY = "九幽天魔宗"
SH = "四海散修商会"


def _uniq(base: str) -> str:
    return f"{base}{os.getpid() % 997}_{int(time.time() * 1000) % 1000000}"


def _tag() -> str:
    return f"{os.getpid() % 89}_{int(time.time() * 1000) % 1000000}"


def _reset(sect: str) -> None:
    WorldStateRepository.set(f"sect_council:{sect}", None)
    WorldStateRepository.set(f"sect_state:{sect}", None)


def _member(name="议政弟子", sect=QY, stones=1000):
    c = WorldClock.create_new_character(f"council_{_uniq(name)}", f"{name}{_tag()}")
    c.sect = sect
    c.sect_rank = "内门弟子"
    c.spirit_stones = stones
    CharacterRepository.save(c)
    return c


def _seat(id_, name, agenda, traits=None, virtual=False, rank="长老"):
    return {
        "id": id_, "name": name, "rank": rank, "virtual": virtual,
        "agenda_type": agenda, "traits": traits or {},
    }


def _force_session(sect, topic_id="mining", session_no=0, opened=T0):
    s = {
        "session_no": session_no, "topic_id": topic_id, "opened_at": opened,
        "closes_at": opened + COUNCIL_VOTE_WINDOW_SECONDS,
        "next_open_at": opened + COUNCIL_VOTE_WINDOW_SECONDS + COUNCIL_INTERVAL_SECONDS,
        "votes": {}, "lobby_attempts": {}, "lobby_steps": {}, "lobby_by_player": {},
        "settled": False, "result": None,
    }
    WorldStateRepository.set(f"sect_council:{sect}", s)
    return s


# ---------------- 立场推导（纯函数确定性） ----------------

def test_stance_score_deterministic_and_tables():
    for _ in range(3):
        assert stance_score("mining", "treasure", {}) == 2
        assert stance_score("mining", "treasure", {"greed": 0.8}) == 3
        assert stance_score("mining", "treasure", {"greed": 0.8, "caution": 0.9}) == 2
        assert stance_score("war", "seclusion", {}) == -2
        assert stance_score("war", "patrol", {"wrath": 0.8}) == 2
        assert stance_score("war", "patrol", {"wrath": 0.8, "caution": 0.7}) == 1
        assert stance_score("festival", "social", {}) == 2
        assert stance_score("array", "patrol", {"caution": 0.7}) == 2
        assert stance_score("recruit", "seclusion", {}) == -1
    seat = _seat("e1", "某长老", "seclusion")
    assert stance_of("mining", seat) == "oppose"
    assert stance_of("mining", seat, steps=1) == "neutral"
    assert stance_of("mining", seat, steps=2) == "support"
    assert stance_of("mining", seat, steps=9) == "support"  # 位移钳制
    print("✓ 立场推导：亲和+性情确定性，位移定档钳制")


def test_topics_effects_within_caps():
    assert [t["id"] for t in COUNCIL_TOPICS] == ["mining", "war", "festival", "recruit", "array"]
    for t in COUNCIL_TOPICS:
        for side in ("pass", "fail"):
            for key, delta in (t["effects"].get(side) or {}).items():
                assert abs(delta) <= COUNCIL_EFFECT_CAPS[key], (t["id"], side, key)
    print("✓ 议题池 5 种齐备，效果表全部在封顶之内")


# ---------------- 席位构成与虚席兜底 ----------------

def _elder_char(name, sect, rank="执法长老", agenda="treasure", traits=None):
    c = WorldClock.create_new_character(f"npc_council_{_uniq(name)}", f"{name}{_tag()}")
    c.sect = sect
    c.sect_rank = rank
    CharacterRepository.save(c)
    NpcAgendaRepository.upsert(
        npc_id=c.id, npc_name=c.name, agenda_type=agenda,
        target_hint="", note="", state="active", last_tick=0.0, progress=0,
    )
    NpcMindRepository.upsert(c.id, "贪财好利", traits or {"greed": 0.8, "caution": 0.4, "wrath": 0.2}, {})
    return c


def test_elder_seats_from_real_chars_and_virtual_fallback():
    e1 = _elder_char("席位甲", SH, agenda="treasure")
    e2 = _elder_char("席位乙", SH, rank="会长", agenda="social")
    disciple = _elder_char("席位弟子", SH, rank="内门弟子", agenda="social")
    dead = _elder_char("席位陨者", SH, agenda="social")
    dead.status = CharacterStatus.DEAD
    seats = CouncilEngine.elder_seats(SH, chars=[e1, e2, disciple, dead])
    names = [s["name"] for s in seats]
    assert e1.name in names and e2.name in names
    assert disciple.name not in names and dead.name not in names
    s1 = next(s for s in seats if s["name"] == e1.name)
    assert s1["agenda_type"] == "treasure" and s1["traits"].get("greed") == 0.8
    assert s1["virtual"] is False
    # 无在册长老 → 虚席兜底，立场由固定议程查表
    vseats = CouncilEngine.elder_seats(SH, chars=[])
    assert len(vseats) == 3 and all(s["virtual"] for s in vseats)
    stances = {s["name"]: stance_of("mining", s) for s in vseats}
    assert stances["值年虚席·甲"] == "neutral"   # patrol → 0
    assert stances["值年虚席·乙"] == "support"   # social → +1
    assert stances["值年虚席·丙"] == "oppose"    # seclusion → -1
    print("✓ 席位：NPC 长老口径过滤（弟子/陨者不入席），agenda/性情带入；虚席兜底确定性")


def test_elder_seat_without_prebuilt_agenda_mind():
    # 未预置 agenda/mind 的长老 NPC：ensure 路径自愈，席位与立场推导不崩
    c = WorldClock.create_new_character(f"npc_council_{_uniq('裸席')}", f"裸席长老{_tag()}")
    c.sect = SH
    c.sect_rank = "护法长老"
    CharacterRepository.save(c)
    seats = CouncilEngine.elder_seats(SH, chars=[c])
    assert len(seats) == 1 and seats[0]["virtual"] is False
    assert isinstance(seats[0]["agenda_type"], str) and isinstance(seats[0]["traits"], dict)
    assert stance_of("mining", seats[0]) in ("support", "oppose", "neutral")
    print("✓ 席位容错：无预置 agenda/mind 的长老自愈入席")


def test_old_save_defaults_and_state_clamp():
    _reset(JY)
    assert CouncilEngine.get_sect_state(JY) == {"vault": 1000, "prestige": 50, "morale": 50}
    WorldStateRepository.set(f"sect_state:{JY}", {"vault": -5, "prestige": 250, "morale": -1})
    assert CouncilEngine.get_sect_state(JY) == {"vault": 0, "prestige": 100, "morale": 0}
    print("✓ 旧档兼容：无 KV 自动默认；宗门状态读时钳制")


# ---------------- 议题生成与周期推进 ----------------

def test_session_lifecycle_rotation():
    _reset(QY)
    s = CouncilEngine.advance(QY, now=T0)
    assert s["session_no"] == 0 and s["topic_id"] == "mining" and not s["settled"]
    assert s["closes_at"] == T0 + COUNCIL_VOTE_WINDOW_SECONDS
    s2 = CouncilEngine.advance(QY, now=T0 + 100)  # 窗口内不重开
    assert s2["session_no"] == 0 and not s2["settled"]
    s3 = CouncilEngine.advance(QY, now=T0 + COUNCIL_VOTE_WINDOW_SECONDS)  # 到点结算
    assert s3["settled"] and s3["result"] is not None
    s4 = CouncilEngine.advance(QY, now=T0 + COUNCIL_VOTE_WINDOW_SECONDS + COUNCIL_INTERVAL_SECONDS - 1)
    assert s4["session_no"] == 0 and s4["settled"]  # 间隔期内仍是上场
    s5 = CouncilEngine.advance(QY, now=T0 + COUNCIL_VOTE_WINDOW_SECONDS + COUNCIL_INTERVAL_SECONDS)
    assert s5["session_no"] == 1 and s5["topic_id"] == "war" and not s5["settled"]  # 轮转
    print("✓ 周期推进：窗口/结算/间隔/议题轮转（now 注入确定性）")


def test_panel_interval_and_open_views():
    _reset(QY)
    m = _member("面板客", sect=QY)
    seats = [_seat("p1", "面板长老", "treasure")]
    txt = CouncilEngine.panel_text(m, now=T0, seats=seats)
    assert "开矿增收" in txt and "面板长老" in txt and "支持" in txt
    assert "金库 1000" in txt
    CouncilEngine.advance(QY, now=T0 + COUNCIL_VOTE_WINDOW_SECONDS)  # 结算
    txt2 = CouncilEngine.panel_text(m, now=T0 + COUNCIL_VOTE_WINDOW_SECONDS + 10, seats=seats)
    assert "上场议题" in txt2 and "下一场议政" in txt2
    print("✓ 面板：进行中呈现议题/立场/状态；间隔期呈现上场结果与倒计时")


# ---------------- 投票 ----------------

def test_vote_one_person_one_vote_and_change():
    _reset(WJ)
    m = _member("投票客", sect=WJ)
    n = _member("投票客二", sect=WJ)
    assert CouncilEngine.vote(m, "支持", now=T0)["success"]
    assert CouncilEngine.vote(n, "反对", now=T0)["success"]
    s = CouncilEngine.advance(WJ, now=T0 + 1)
    assert s["votes"] == {m.id: "support", n.id: "oppose"}  # 一人一票
    assert CouncilEngine.vote(m, "反对", now=T0 + 2)["success"]  # 改票覆盖
    s = CouncilEngine.advance(WJ, now=T0 + 3)
    assert s["votes"][m.id] == "oppose" and len(s["votes"]) == 2
    counts = CouncilEngine.tally(WJ, s, seats=[])
    assert counts == {"support": 0, "oppose": 2}
    r = CouncilEngine.vote(m, "骑墙", now=T0 + 4)
    assert not r["success"] and "用法" in r["message"]
    print("✓ 投票：一人一票、改票覆盖、计票只认玩家票（空席位）")


def test_vote_after_deadline_rejected():
    _reset(WJ)
    m = _member("迟到客", sect=WJ)
    CouncilEngine.advance(WJ, now=T0)
    r = CouncilEngine.vote(m, "支持", now=T0 + COUNCIL_VOTE_WINDOW_SECONDS + 1)
    assert not r["success"] and "已结算" in r["message"]
    print("✓ 投票：截止先惰性结算，后投票被拒")


# ---------------- 游说 ----------------

def _lobby_setup():
    _reset(JY)
    m = _member("游说客", sect=JY, stones=1000)
    _force_session(JY, topic_id="mining", opened=T0)
    return m


def test_lobby_success_steps_and_cost_escalation():
    m = _lobby_setup()
    seat = _seat("L1", "矿山长老", "seclusion")  # mining: -1 → 反对
    assert stance_of("mining", seat) == "oppose"
    r1 = CouncilEngine.lobby(m, "矿山长老", now=T0 + 1, seats=[seat])
    assert r1["success"] and r1["cost"] == COUNCIL_LOBBY_BASE_COST
    assert m.spirit_stones == 1000 - COUNCIL_LOBBY_BASE_COST
    s = CouncilEngine.advance(JY, now=T0 + 2)
    assert stance_of("mining", seat, int(s["lobby_steps"]["L1"])) == "neutral"
    r2 = CouncilEngine.lobby(m, "矿山长老", now=T0 + 3, seats=[seat])
    assert r2["success"] and r2["cost"] == COUNCIL_LOBBY_BASE_COST * 2  # 递增
    s = CouncilEngine.advance(JY, now=T0 + 4)
    assert stance_of("mining", seat, int(s["lobby_steps"]["L1"])) == "support"
    r3 = CouncilEngine.lobby(m, "矿山长老", now=T0 + 5, seats=[seat])
    assert not r3["success"] and "已被游说" in r3["message"]  # 第三次撞每长老上限（真实累积）
    assert m.spirit_stones == 1000 - COUNCIL_LOBBY_BASE_COST * 3  # 拒绝不扣费
    print("✓ 游说：位移一档/次、成本 60→120 递增、每长老上限真实累积触发且拒绝不扣费")


def test_lobby_resist_support_and_virtual():
    m = _lobby_setup()
    iron = _seat("L2", "铁心长老", "seclusion")  # 换 war 议题才是铁杆；mining 下 -1 可撬
    _force_session(JY, topic_id="war", opened=T0)
    r = CouncilEngine.lobby(m, "铁心长老", now=T0 + 1, seats=[iron])
    assert not r["success"] and "油盐不进" in r["message"]
    assert m.spirit_stones == 1000  # 铁杆拒绝不扣费不计次
    s = CouncilEngine.advance(JY, now=T0 + 2)
    assert not s["lobby_attempts"] and not s["lobby_by_player"]
    fan = _seat("L3", "主战长老", "revenge")  # war: +2 已支持
    r = CouncilEngine.lobby(m, "主战长老", now=T0 + 3, seats=[fan])
    assert not r["success"] and "已然赞同" in r["message"]
    virt = _seat("virtual:x:0", "值年虚席·甲", "patrol", virtual=True)
    r = CouncilEngine.lobby(m, "值年虚席·甲", now=T0 + 4, seats=[virt])
    assert not r["success"] and "虚席" in r["message"]
    r = CouncilEngine.lobby(m, "查无此人", now=T0 + 5, seats=[iron])
    assert not r["success"] and "无" in r["message"]
    print("✓ 游说：铁杆（score≤-2）拒绝不计次、已支持拒绝、虚席不可游说、查无此人")


def test_lobby_caps_and_insufficient_stones():
    # 每玩家上限走真实累积：连撬三位长老（各首次游说）后，第四位撞玩家上限
    m = _lobby_setup()
    seats = [
        _seat("P1", "巡守长老", "patrol"),     # mining: 0 中立可撬
        _seat("P2", "闭关长老", "seclusion"),  # mining: -1 反对可撬
        _seat("P3", "记仇长老", "revenge"),    # mining: -1 反对可撬
        _seat("P4", "巡山长老", "patrol"),     # 第四个目标
    ]
    for i, nm in enumerate(["巡守长老", "闭关长老", "记仇长老"]):
        r = CouncilEngine.lobby(m, nm, now=T0 + 1 + i, seats=seats)
        assert r["success"], (nm, r)
    assert m.spirit_stones == 1000 - COUNCIL_LOBBY_BASE_COST * COUNCIL_LOBBY_MAX_PER_PLAYER
    r = CouncilEngine.lobby(m, "巡山长老", now=T0 + 9, seats=seats)
    assert not r["success"] and "已游说" in r["message"]
    assert m.spirit_stones == 1000 - COUNCIL_LOBBY_BASE_COST * COUNCIL_LOBBY_MAX_PER_PLAYER
    # 灵石不足：拒绝不扣费
    poor = _member("清贫客", sect=JY, stones=10)
    r = CouncilEngine.lobby(poor, "巡山长老", now=T0 + 10, seats=seats)
    assert not r["success"] and "不足" in r["message"] and poor.spirit_stones == 10
    print("✓ 游说：每玩家上限真实累积触发；灵石不足拒绝不扣费")


# ---------------- 结算 ----------------

def _council_broadcasts() -> int:
    import core.jianghu as jianghu

    return len([
        e for e in jianghu.list_recent(limit=100, kind="sect_council")
        if SH in (e.get("summary") or "")
        and "开矿增收" in (e.get("summary") or "")
        and "通过" in (e.get("summary") or "")
    ])


def test_settle_pass_effects_and_idempotent():
    _reset(SH)
    _force_session(SH, topic_id="mining", opened=T0)
    s = CouncilEngine.advance(SH, now=T0)
    seats = [_seat("S1", "主矿长老", "treasure")]  # support
    n_broadcasts = _council_broadcasts()
    out = CouncilEngine.settle(SH, s, now=T0 + 10, seats=seats)
    assert out["result"]["passed"] is True
    assert out["result"]["effects"] == {"vault": 300, "morale": -5}
    st = CouncilEngine.get_sect_state(SH)
    assert st == {"vault": 1300, "prestige": 50, "morale": 45}
    assert _council_broadcasts() == n_broadcasts + 1  # 播报恰一次
    out2 = CouncilEngine.settle(SH, out, now=T0 + 20, seats=seats)  # 幂等重入
    assert CouncilEngine.get_sect_state(SH) == st
    assert out2["result"] == out["result"]
    # 另一份独立快照再 settle：靠 KV 复查防双重落账/双重播报
    stale = dict(out)
    stale["settled"] = False
    stale["result"] = None
    out3 = CouncilEngine.settle(SH, stale, now=T0 + 30, seats=seats)
    assert out3["settled"] and out3["result"] == out["result"]
    CouncilEngine.advance(SH, now=T0 + COUNCIL_VOTE_WINDOW_SECONDS + 5)  # 惰性再触发
    assert CouncilEngine.get_sect_state(SH) == st
    assert _council_broadcasts() == n_broadcasts + 1
    print("✓ 结算：通过落账（金库+300/士气-5）、连调/异快照/KV 复查三重幂等、播报恰一次")


def test_settle_fail_and_tie_goes_fail():
    _reset(SH)
    _force_session(SH, topic_id="mining", opened=T0)
    s = CouncilEngine.advance(SH, now=T0)
    seats = [_seat("S2", "守山长老", "seclusion")]  # oppose
    out = CouncilEngine.settle(SH, s, now=T0 + 10, seats=seats)
    assert out["result"]["passed"] is False
    assert CouncilEngine.get_sect_state(SH) == {"vault": 1000, "prestige": 50, "morale": 52}
    _reset(SH)
    _force_session(SH, topic_id="recruit", opened=T0)
    s = CouncilEngine.advance(SH, now=T0)
    tie = [_seat("S3", "主纳长老", "social"), _seat("S4", "主闭长老", "seclusion")]
    out = CouncilEngine.settle(SH, s, now=T0 + 10, seats=tie)  # 1:1 平局
    assert out["result"]["passed"] is False and out["result"]["support"] == out["result"]["oppose"] == 1
    assert CouncilEngine.get_sect_state(SH) == {"vault": 1000, "prestige": 50, "morale": 50}  # recruit 否决无效果
    print("✓ 结算：否决路径落 fail 效果；平局判否决")


def test_settle_vault_floor_and_player_votes_count():
    _reset(SH)
    WorldStateRepository.set(f"sect_state:{SH}", {"vault": 100, "prestige": 50, "morale": 50})
    s = _force_session(SH, topic_id="war", opened=T0)
    m = _member("主战弟子", sect=SH)
    s["votes"][m.id] = "support"
    WorldStateRepository.set(f"sect_council:{SH}", s)
    out = CouncilEngine.settle(SH, s, now=T0 + 10, seats=[])  # 玩家票定胜负
    assert out["result"]["passed"] is True
    st = CouncilEngine.get_sect_state(SH)
    assert st == {"vault": 0, "prestige": 62, "morale": 58}  # 金库扣至 0 不为负
    # 快照记实际落账差值：金库仅 100，名义 -150 → 实际 -100
    assert out["result"]["effects"]["vault"] == -100
    # 合并写：sect_state 中他人写入的额外键不被结算整表覆盖
    raw = WorldStateRepository.get(f"sect_state:{SH}") or {}
    raw["future_region_key"] = 7
    WorldStateRepository.set(f"sect_state:{SH}", raw)
    _force_session(SH, topic_id="recruit", session_no=3, opened=T0)
    s2 = CouncilEngine.advance(SH, now=T0)
    CouncilEngine.settle(SH, s2, now=T0 + 10, seats=[_seat("S9", "纳徒长老", "social")])
    raw2 = WorldStateRepository.get(f"sect_state:{SH}") or {}
    assert raw2.get("future_region_key") == 7
    print("✓ 结算：玩家票计入多数决；金库下限 0、声望/士气按表落账")


# ---------------- 边界：非成员 / 死亡 / 无宗门 ----------------

def test_non_member_and_dead_rejections():
    _reset(WJ)
    free = _member("散修客", sect=None)
    assert "散修无宗可议" in CouncilEngine.panel_text(free, now=T0)
    assert not CouncilEngine.vote(free, "支持", now=T0)["success"]
    assert not CouncilEngine.lobby(free, "某长老", now=T0)["success"]
    dead = _member("已陨客", sect=WJ)
    dead.status = CharacterStatus.DEAD
    assert not CouncilEngine.vote(dead, "支持", now=T0)["success"]
    assert not CouncilEngine.lobby(dead, "某长老", now=T0)["success"]
    txt = CouncilEngine.panel_text(dead, now=T0)  # 查看放行（遗容）
    assert "宗门议政" in txt
    s = CouncilEngine.advance(WJ, now=T0)
    assert not s["votes"] and not s["lobby_by_player"]  # 死人零副作用
    print("✓ 边界：散修三路拒绝；死亡投票/游说前置拒绝且零副作用，查看放行")


# ---------------- 双端 handle ----------------

def test_server_handle_flow_and_meditation_lock():
    _reset(QY)
    r = WORLD.join(f"议政服客{_uniq('')}")
    tok = r["token"]
    char = WORLD.get_char(tok)
    char.sect = QY
    char.sect_rank = "内门弟子"
    char.spirit_stones = 1000
    CharacterRepository.save(char)
    res = WORLD.handle(tok, "/议政")
    assert res["ok"] and "宗门议政" in res["text"] and "开矿增收" in res["text"], res
    res = WORLD.handle(tok, "/投票 支持")
    assert res["ok"], res
    res = WORLD.handle(tok, "/投票 反对")  # 改票
    assert res["ok"], res
    char = WORLD.get_char(tok)
    char.status = CharacterStatus.MEDITATING
    CharacterRepository.save(char)
    res = WORLD.handle(tok, "/投票 支持")
    assert not res["ok"] and "闭关" in (res.get("error") or ""), res
    res = WORLD.handle(tok, "/议政")
    assert not res["ok"] and "闭关" in (res.get("error") or ""), res
    res = WORLD.handle(tok, "/游说 丹霞子")
    assert not res["ok"] and "闭关" in (res.get("error") or ""), res
    print("✓ 双端：server handle 议政/投票/改票通路；闭关三指令（议政/投票/游说）锁门")
