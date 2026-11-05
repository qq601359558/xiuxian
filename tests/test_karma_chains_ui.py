"""AI 天道事件链（karma-event-chains）前端岗测试：K-19 双端同源 + 呈现接线。

Spec：docs/compose/spec/karma-event-chains.md §6 / §12 K-19、K-21。
口径（照 test_qa2_dual_end / test_reincarnation_inheritance 的 /墓碑 先例）：
- server 侧走 World.handle 真实分发；
- CLI 侧以「同引擎入口」源码对齐断言钉住（cli/main.py 为交互循环不可直接
  handle 调用，仓库既有口径即源码断言），且断言 CLI 打印的正是
  KarmaChainEngine.panel_text —— 双端逐字同源由此闭合；
- Web 侧只断言通用命令路径存在（cmdForm→send→/action→handleResult），
  本轮前端零专属 UI（Spec §6.1/§13）。
隔离：沿用共享 DB + 唯一后缀；链行按 player_id 清理，自造角色收尾置死。
"""
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"
os.environ["USE_CCSWITCH"] = "0"

from config import SECONDS_PER_GAME_DAY
from core.clock import WorldClock
from core.karma_chains import KarmaChainEngine
from core.models import CharacterStatus
from server.world import World
from storage.db import CharacterRepository, KarmaChainRepository, init_db

init_db()

DAY = SECONDS_PER_GAME_DAY
LOC = "青云坊市客栈"
ROOT = Path(__file__).resolve().parent.parent


def _tag():
    return uuid.uuid4().hex[:6]


def _npc(name="面板翁"):
    c = WorldClock.create_new_character(f"npc_kui_{_tag()}_{name}", f"{name}{_tag()}")
    c.location = LOC
    CharacterRepository.save(c)
    return c


def _cleanup(*chars):
    for c in chars:
        if c is None:
            continue
        for ch in KarmaChainRepository.list_all():
            if c.id in (ch.player_id, ch.counterparty_id, ch.delivery_actor_id):
                KarmaChainRepository.delete(ch.id)
        live = CharacterRepository.get_by_id(c.id)
        if live and live.status != CharacterStatus.DEAD:
            live.status = CharacterStatus.DEAD
            CharacterRepository.save(live)


def _origin(player, npc, t0, kind="en", polarity=1, strength=3):
    return KarmaChainEngine.note_origin(
        player, npc, kind=kind, polarity=polarity, strength=strength,
        chain_key=f"uitest:{uuid.uuid4().hex[:10]}",
        origin_summary="测试起因", source_ref=f"uitest:{uuid.uuid4().hex[:8]}",
        now=t0,
    )


# ---------------- K-19 双端查询逐字一致 ----------------

def test_dual_end_panel_same_source():
    w = World(auto_tick=False)
    joined = w.join(f"链面板客{_tag()}")
    tok = joined["token"]
    char = w.get_char(tok)
    npc = _npc()
    try:
        # 无链空面板：server 文本 == 引擎同源文本（CLI 打印同一函数）
        res = w.handle(tok, "/因果链")
        assert res["ok"], res
        assert res["text"] == KarmaChainEngine.panel_text(
            CharacterRepository.get_by_id(char.id))
        assert "眼下无因果缠身" in res["text"]

        # 潜伏链：起链于 1 游戏日 + 120 秒前——面板「已过日数」在
        # ±120 秒内稳定为 1，避免跨游戏日边界的逐字比对抖动
        t0 = time.time() - DAY - 120.0
        chain = _origin(char, npc, t0)
        assert chain is not None and chain.status == "latent"
        res = w.handle(tok, "/因果链")
        assert res["ok"], res
        assert res["text"] == KarmaChainEngine.panel_text(
            CharacterRepository.get_by_id(char.id))
        assert "〔进行中〕（1/4）" in res["text"]
        assert npc.name in res["text"] and "测试起因" in res["text"]

        # 别名逐字同源
        alias = w.handle(tok, "/karma_chains")
        assert alias["ok"] and alias["text"] == res["text"]

        # 无参命令附加词：按邻近面板口径忽略不报错（/墓碑 需参口径不适用于面板）
        extra = w.handle(tok, "/因果链 旁注")
        assert extra["ok"] and extra["text"] == res["text"]

        # 无效会话：handle 既有口径
        bad = w.handle("不存在的token", "/因果链")
        assert bad["ok"] is False and "会话无效" in bad["error"]
        print("✓ K-19 server /因果链 与引擎 panel_text 逐字一致（空面板/潜伏链/别名）")
    finally:
        _cleanup(char, npc)


def test_dual_end_lazy_advance_on_query():
    """查询前惰性推进：到期链首次查询即兑现并呈 resolved 近史（K-19 后半）。"""
    w = World(auto_tick=False)
    joined = w.join(f"链惰进客{_tag()}")
    tok = joined["token"]
    char = w.get_char(tok)
    npc = _npc("惰进翁")
    try:
        # en 链发酵 9 游戏日：起链于 10 游戏日前，查询时已过 mature_at
        t0 = time.time() - 10 * DAY
        chain = _origin(char, npc, t0)
        assert chain is not None
        assert KarmaChainRepository.get(chain.id).status == "latent"
        res = w.handle(tok, "/因果链")
        assert res["ok"], res
        got = KarmaChainRepository.get(chain.id)
        assert got.status == "resolved", got.status
        # 已兑现后面板无时间相关字段，逐字比对稳定
        assert res["text"] == KarmaChainEngine.panel_text(
            CharacterRepository.get_by_id(char.id))
        assert "〔近史〕" in res["text"] and "已兑现·恩" in res["text"]
        print("✓ K-19 查询前惰性推进生效：到期链首次查询即 resolved 近史")
    finally:
        _cleanup(char, npc)


def test_cli_dispatch_uses_same_engine_source():
    """CLI 源码对齐：/因果链 分支同命令、先 advance_for 后 panel_text 打印。"""
    cli_src = (ROOT / "cli" / "main.py").read_text(encoding="utf-8")
    assert 'action in ["/因果链", "/karma_chains"]' in cli_src
    assert "KarmaChainEngine.advance_for(player)" in cli_src
    assert "console.print(KarmaChainEngine.panel_text(player))" in cli_src
    srv_src = (ROOT / "server" / "world.py").read_text(encoding="utf-8")
    assert 'action in ("/因果链", "/karma_chains")' in srv_src
    assert "KarmaChainEngine.advance_for(char)" in srv_src
    assert "KarmaChainEngine.panel_text(char)" in srv_src
    print("✓ K-19 CLI 分发与 server 调用同一引擎入口（advance_for→panel_text）")


# ---------------- 帮助文案三者并列（C-5） ----------------

def test_help_texts_distinguish_karma_commands():
    w = World(auto_tick=False)
    help_text = w._help()
    assert "/因果链" in help_text and "天道事件链面板" in help_text
    assert "本服 /因果 为回访别名" in help_text
    assert "CLI /因果 为因果关系列表" in help_text
    assert "/因果(回访)" in help_text  # 既有 server /因果=回访 注记保留
    cli_src = (ROOT / "cli" / "main.py").read_text(encoding="utf-8")
    assert "/因果链" in cli_src and "天道事件链面板" in cli_src
    assert "因果关系列表（KarmaLink" in cli_src
    assert "server 端 /因果 为回访别名" in cli_src
    print("✓ C-5 双端帮助并列注明 /因果（server 回访别名 / CLI 关系列表）与 /因果链")


# ---------------- _status_dict 只增键（§6.1） ----------------

def test_status_dict_karma_chains_key():
    w = World(auto_tick=False)
    joined = w.join(f"链状态客{_tag()}")
    char = w.get_char(joined["token"])
    npc = _npc("状态翁")
    try:
        st = w._status_dict(CharacterRepository.get_by_id(char.id))
        assert st["karma_chains"] == {
            "active": 0, "fermenting": 0, "nearest_mature_game_days": None,
        }
        chain = _origin(char, npc, time.time())
        assert chain is not None
        st = w._status_dict(CharacterRepository.get_by_id(char.id))
        assert st["karma_chains"]["active"] == 1
        assert st["karma_chains"]["fermenting"] == 0
        assert st["karma_chains"]["nearest_mature_game_days"] == 9
        assert st["karma_chains"] == KarmaChainEngine.status_summary(
            CharacterRepository.get_by_id(char.id))
        print("✓ §6.1 _status_dict 只增 karma_chains 键且与引擎 status_summary 同源")
    finally:
        _cleanup(char, npc)


# ---------------- Web 通用命令路径（前端零专属 UI 的证据） ----------------

def test_web_generic_command_path_covers_karma_chains():
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    # 通用命令框：cmdForm 提交 → send(v) → POST /action → handleResult 渲染 text 进 feed
    assert 'id="cmdForm"' in index_html and 'id="cmdInput"' in index_html
    assert '$("cmdForm").addEventListener("submit"' in app_js
    assert 'api("/action", { token: state.token, command: c })' in app_js
    assert "handleResult(data)" in app_js
    # 本轮无专属 UI：index.html 无 /因果链 快捷按钮（Spec §6.1 前端零改动）
    assert 'data-cmd="/因果链"' not in index_html
    print("✓ Web 经通用命令框（cmdForm→/action→handleResult）可用，无专属 UI")
