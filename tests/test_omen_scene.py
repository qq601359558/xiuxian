"""
奇遇弹窗会话
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db import init_db, CharacterRepository, WorldStateRepository
from core.clock import WorldClock
from core import omen_scene as os
from config import WORLD_LOCATIONS


def _c(name="遇客", stones=300):
    c = WorldClock.create_new_character(f"om_{name}", name)
    c.spirit_stones = stones
    c.born_at = time.time() - 80 * 3600.0
    CharacterRepository.save(c)
    return c


def test_start_and_choose_success():
    init_db()
    WorldStateRepository.delete(os._KEY)
    c = _c("选客")
    r = os.start_scene(CharacterRepository.get_by_id(c.id), script_id="stele")
    assert r["success"] and r.get("opened")
    # 选 1 静坐 → sit 成功
    r2 = os.choose(CharacterRepository.get_by_id(c.id), "1")
    assert r2["success"] is True
    assert r2.get("ended") is True
    assert r2.get("omen_status") == "success"
    c2 = CharacterRepository.get_by_id(c.id)
    assert c2.realm.current_exp >= 0  # 有落账路径
    print("✓ 选项走通成功节点")


def test_free_text_and_force_end():
    init_db()
    WorldStateRepository.delete(os._KEY)
    c = _c("闲聊客")
    os.start_scene(CharacterRepository.get_by_id(c.id), script_id="black_market")
    # 无效闲聊 3 次
    for _ in range(3):
        r = os.say(CharacterRepository.get_by_id(c.id), "今天天气哈哈哈")
        if r.get("ended"):
            break
    assert r.get("ended") is True
    assert r.get("omen_status") == "forced"
    print("✓ 无效闲聊强制散场")


def test_intent_buy_edge():
    init_db()
    WorldStateRepository.delete(os._KEY)
    c = _c("买客", stones=200)
    os.start_scene(CharacterRepository.get_by_id(c.id), script_id="black_market")
    r = os.say(CharacterRepository.get_by_id(c.id), "我买了")
    assert r["success"] is True
    # 买 → buy 节点 success
    assert r.get("ended") is True
    c2 = CharacterRepository.get_by_id(c.id)
    assert c2.spirit_stones == 200 - 80 + 0  # buy edge -80 then success +exp only
    print("✓ 自由句映射购买边", c2.spirit_stones)


def test_group_scene_and_at():
    init_db()
    WorldStateRepository.delete(os._KEY)
    c = _c("群客")
    r = os.start_scene(CharacterRepository.get_by_id(c.id), script_id="escort_deal")
    assert r["success"]
    assert "驼爷" in r["message"] and "柳三娘" in r["message"]
    assert "在场" in r["message"]
    # @ 驼爷 问
    r2 = os.say(CharacterRepository.get_by_id(c.id), "@驼爷 这箱里到底是什么")
    assert r2["success"] is True
    assert r2.get("intent") == "ask"
    print("✓ 群聊剧本 + @解析")


def test_parse_at():
    names = ["驼爷", "柳三娘"]
    assert os._parse_at("@驼爷 来", names)[0] == "驼爷"
    assert os._parse_at("@柳三娘你好", names)[0] == "柳三娘"
    assert os._parse_at("你好", names)[0] is None
    print("✓ _parse_at")


def test_ai_script_ingest():
    init_db()
    WorldStateRepository.delete(os._KEY)
    c = _c("编客")
    data = {
        "title": "夜市残卷",
        "speakers": ["书贩"],
        "intro": "灯下有人兜售残卷。",
        "goal": "决定买或走",
        "start": "n1",
        "max_turns": 6,
        "nodes": {
            "n1": {
                "speaker": "书贩",
                "prompt": "「残卷五十灵石。」",
                "choices": [
                    {"id": "1", "label": "买", "to": "ok", "effects": {"stones": -50}},
                    {"id": "2", "label": "走", "to": "ok", "effects": {}},
                ],
                "edges": [{"intent": "buy", "to": "ok", "effects": {"stones": -50}, "reply": "「拿去。」"}],
            },
            "ok": {
                "speaker": "旁白",
                "prompt": "交易了结。",
                "success": True,
                "effects": {"exp": 10, "stones": 99999},
                "choices": [],
                "edges": [],
            },
        },
    }
    sid = os.ingest_ai_script(data, c)
    assert sid and sid.startswith("ai_")
    sc = os.SCRIPTS[sid]
    # 超额 stones 被钳制
    assert abs(int(sc["nodes"]["ok"]["effects"].get("stones") or 0)) <= 200
    r = os.start_scene(CharacterRepository.get_by_id(c.id), script_id=sid, allow_ai=False)
    assert r["success"] and r["scene"]["script_id"] == sid
    print("✓ AI 剧本入册并钳制 effects")


def test_status_sync_fields():
    init_db()
    WorldStateRepository.delete(os._KEY)
    c = _c("同步客")
    r = os.start_scene(CharacterRepository.get_by_id(c.id), allow_ai=False)
    text = r["message"]
    assert "灵石" in text and "修为" in text
    print("✓ 渲染含灵石/修为")


if __name__ == "__main__":
    test_start_and_choose_success()
    test_free_text_and_force_end()
    test_intent_buy_edge()
    test_group_scene_and_at()
    test_parse_at()
    test_ai_script_ingest()
    test_status_sync_fields()
    print("\n✅ omen_scene 测试通过")
