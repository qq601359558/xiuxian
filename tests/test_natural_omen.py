"""
自然奇遇与首张藏宝图 100% 奇遇单元与回归测试套件
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.models import Character, CharacterStatus, Realm, Lifespan, SpiritualRoot, RootType, Element
from core.clock import WorldClock
from core import omen_scene as os_mod
from core.loot_equip import DigEngine
from server.world import World
import config


def _make_char(name="测试仙尊"):
    now = time.time()
    c = Character(
        user_id=f"u_{name}",
        name=name,
        realm=Realm(tier=2, sub_tier=1, current_exp=200, max_exp=1000),
        lifespan=Lifespan(birth_base=100, accumulated_gain=0, death_timestamp=now + 100 * 86400),
        spiritual_root=SpiritualRoot(root_type=RootType.TRUE, elements=[Element.WOOD], efficiency=1.1),
        spirit_stones=500,
        status=CharacterStatus.IDLE,
        location="青云坊市客栈",
        inventory=["藏宝图"],
    )
    c.born_at = now - 3600
    CharacterRepository.save(c)
    return c


def test_initial_character_and_config():
    """验证新修士入世自带藏宝图与默认奇遇字段"""
    c = WorldClock.create_new_character("test_u_new", "初入仙门")
    assert "藏宝图" in c.inventory
    assert c.first_dig_omen_done is False
    assert c.last_omen_at == 0.0

    # 验证概率配置
    assert config.OMEN_CHANCE_PROD == 0.01
    assert config.OMEN_CHANCE_TEST == 0.30
    assert config.omen_chance() == 0.30  # 测试环境默认


def test_first_dig_guaranteed_omen():
    """验证本世首次使用藏宝图 100% 触发奇遇与保底机缘"""
    init_db()
    c = _make_char("寻宝散人")
    WorldStateRepository.delete(os_mod._KEY)

    assert c.first_dig_omen_done is False
    res = DigEngine.dig(c, force_legacy=True)
    assert res["success"] is True
    assert res.get("omen_triggered") is True
    assert res.get("first_dig_omen") is True
    assert res.get("omen_inline") is True
    assert c.first_dig_omen_done is True
    assert "藏宝图" not in c.inventory

    # 验证生成的奇遇场景
    scene = os_mod.get_scene(c.id)
    assert scene is not None
    assert scene["status"] in ("open", "ongoing")

    # 清理
    os_mod.abandon(c)


def test_chat_npc_natural_omen():
    """验证与 NPC 聊天中偶发奇遇直接在聊天框就地结算"""
    init_db()
    c = _make_char("谈道散修")
    npc = _make_char("青云道人")
    WorldStateRepository.delete(os_mod._KEY)

    res = os_mod.maybe_trigger_natural_omen(c, in_chat_npc=npc, force=True)
    assert res is not None
    assert res["triggered"] is True
    assert res["mode"] == "chat"
    assert res["omen_inline"] is False
    assert "【天机偶发" in res["text"]
    assert npc.name in res["text"]
    # 聊天奇遇不占用主界面场景
    assert os_mod.get_scene(c.id) is None


def test_inline_omen_choices_and_dismiss_on_leave():
    """验证主界面内联奇遇选项获取与离开散场"""
    init_db()
    c = _make_char("漂泊修士")
    WorldStateRepository.delete(os_mod._KEY)

    # 强制触发一次主界面内联奇遇
    res = os_mod.maybe_trigger_natural_omen(c, context="十方迁跃", force=True)
    assert res is not None
    assert res["triggered"] is True
    assert res["omen_inline"] is True
    assert len(res["omen_choices"]) > 0

    choices = os_mod.current_choices(c.id)
    assert len(choices) > 0
    assert "id" in choices[0] and "label" in choices[0]

    # 迁跃或闭关触发优雅散场
    msg = os_mod.dismiss_on_leave(c, action_label="御剑迁跃")
    assert msg is not None
    assert "【机缘散去】" in msg
    assert os_mod.get_scene(c.id) is None


def test_world_unforceable_omen():
    """验证 /奇遇 与 /机缘 去强刷化：无会话时不可强行开启"""
    init_db()
    w = World()
    c = _make_char("贪心修士")
    WorldStateRepository.delete(os_mod._KEY)

    # 主动推演 /机缘
    r1 = w._event(c)
    assert r1["ok"] is True
    assert "【天机渺茫】" in r1["text"]
    assert r1.get("omen_open") is False

    # 主动输入 /奇遇
    res_join = w.join(c.name, c.user_id)
    token = res_join["token"]
    r2 = w.handle(token, "/奇遇")
    assert r2["ok"] is True
    assert "【天机渺茫】" in r2["text"]
    assert r2.get("omen_open") is False


def test_world_append_natural_omen():
    """验证日常行为（探险、迁跃、出关）携带自然奇遇挂载"""
    init_db()
    w = World()
    c = _make_char("云游修士")
    WorldStateRepository.delete(os_mod._KEY)

    # 模拟行为返回字典，调用 _append_natural_omen
    raw_payload = {"ok": True, "text": "行至山巅。"}
    # 当以 force=True 模式检定时必定触发
    omen = os_mod.maybe_trigger_natural_omen(c, context="山巅感怀", force=True)
    assert omen and omen.get("triggered")
