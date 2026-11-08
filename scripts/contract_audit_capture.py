"""Contract-audit capture harness (audit-only, no business logic).

Runs the real in-process World against a FRESH test DB and captures the real
JSON response of every reachable `/command` branch, plus the non-command
payload exits (join / dead payload / reincarnate / build_entry via join).

Usage (from repo root, with a FRESH data/ dir -- the harness refuses to run
if data/tiandao.db already exists, so it never touches a live save):
    AI_REQUIRED=0 python3 scripts/contract_audit_capture.py [--out DIR]

Outputs (git-tracked evidence):
    docs/compose/contract-audit-captures/<slug>.json   one file per capture
    docs/compose/contract-audit-captures/index.json    manifest incl. failures

Determinism notes: random.seed(20261108) is set so RNG-gated outcomes
(e.g. /捡漏 loot rolls) are re-runnable; archetype/choice-gated outcomes
(/挖宝 1 / 2 / scar_created) are deterministic given the granted map.
Captures are evidence, not fixtures: re-running may differ where the engine
is intentionally random; the manifest records the seed and the outcome seen.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("AI_REQUIRED", "0")
os.environ.setdefault("ALLOW_LOCAL_AI", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CAPTURE_SEED = 20261108


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    return str(o)


class Capturer:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = {"seed": CAPTURE_SEED, "captures": [], "failures": []}
        self.n = 0

    def save(self, slug: str, command: str, response, note: str = ""):
        self.n += 1
        fname = f"{self.n:03d}-{slug}.json"
        payload = {
            "slug": slug,
            "command": command,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "seed": CAPTURE_SEED,
            "note": note,
            "response": _jsonable(response),
            "top_keys": sorted(response.keys()) if isinstance(response, dict) else [],
        }
        (self.out_dir / fname).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        self.manifest["captures"].append({
            "slug": slug, "file": fname, "command": command, "note": note,
            "ok": bool(isinstance(response, dict) and response.get("ok")),
            "top_keys": payload["top_keys"],
        })
        return payload

    def fail(self, slug: str, command: str, err: str):
        self.manifest["failures"].append({"slug": slug, "command": command, "error": err})
        print(f"  [FAIL] {command}: {err}")

    def write_manifest(self):
        (self.out_dir / "index.json").write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/compose/contract-audit-captures")
    args = ap.parse_args()
    db = ROOT / "data" / "tiandao.db"
    if db.exists():
        print(f"REFUSAL: {db} already exists. Capture harness only runs on a "
              "fresh DB (rm -rf data/ first, or run in a scratch copy).")
        return 2
    random.seed(CAPTURE_SEED)

    from server.world import WORLD
    from storage.db import CharacterRepository

    try:
        WORLD.stop_tick()
    except Exception:
        pass

    cap = Capturer(ROOT / args.out)

    def run(token, cmd, slug, note=""):
        try:
            resp = WORLD.handle(token, cmd)
        except Exception as e:  # harness must not die on one branch
            import traceback
            cap.fail(slug, cmd, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-600:]}")
            return None
        return cap.save(slug, cmd, resp, note)

    def refresh(user_id):
        return CharacterRepository.get_by_user_id(user_id)

    def grant_stones(user_id, amount=100000):
        c = refresh(user_id)
        c.spirit_stones = amount
        CharacterRepository.save(c)

    # ---------- Phase 0: join / entry payload ----------
    j = WORLD.join("审计员", user_id="audit_user_1")
    cap.save("join", "/join 审计员", j, "join payload incl. entry + origin_card (build_entry)")
    token = j.get("token")
    assert token, f"join failed: {j}"
    grant_stones("audit_user_1")

    # ---------- Phase 1: read-only batch ----------
    readonly = [
        "/look", "/地图", "/道身", "/legacy", "/道统", "/墓碑 审计员", "/因果链",
        "/图鉴", "/命格", "/命途", "/寻宝", "/器灵", "/wallet", "/钱包",
        "/here", "/同场", "/profile", "/人物", "/roster", "/名录", "/who",
        "/goals", "/目标", "/近况", "/ailog", "/ai", "/帮助", "/help",
        "/qi", "/灵气", "/season", "/纪元", "/天象", "/rumors", "/传闻",
        "/channel", "/频道", "/notice", "/公告", "/legend", "/传说", "/links",
        "/关系", "/map", "/宝图", "/rank", "/榜单", "/ascend", "/飞升榜",
        "/sect", "/宗门", "/agenda", "/议程", "/bounty", "/告示", "/market",
        "/坊市", "/行情", "/atlas", "/版图", "/history", "/大事记", "/arts",
        "/功法", "/secret", "/秘境", "/recipes", "/配方", "/宗门势", "/宗门环",
        "/贡献", "/兑换", "/灵宠", "/心法", "/洞府", "/委托", "/诺言",
        "/quests", "/promises", "/宗门令", "/议政", "/除凶", "/追凶",
        "/反悬赏", "/围剿", "/hunt", "/event", "/机缘", "/tick",
        "/世界弧", "/世情", "/势力", "/纪元回流", "/chatpanel", "/会话",
    ]
    for cmd in readonly:
        slug = "ro-" + cmd.strip("/").split()[0].replace("/", "-") or "ro"
        run(token, cmd, slug)

    # ---------- Phase 2: movement ----------
    from core.world_grid import WorldGridEngine
    nodes = WorldGridEngine.list_nodes()
    dest = next((n for n in nodes if n.id != refresh("audit_user_1").location), nodes[0])
    run(token, f"/go {dest.base_name}", "go", f"dest node {dest.id} ({dest.base_name})")
    run(token, "/here", "here-after-go")

    # ---------- Phase 3: treasure dig (all four outcomes) ----------
    from core.treasure_system import TreasureEngine, TreasureArchetype
    from core.items import ItemKind  # noqa: F401  (kind check)

    def grant_map(archetype, tier=2):
        # ELEMENT digs do NOT consume the map (no remove_item_entity in that
        # branch), so purge leftovers first -- otherwise dig() uses maps[0],
        # i.e. a stale map from an earlier step, and the capture mislabels
        # the outcome (found the hard way: a stale ELEMENT map shadowed the
        # COMBAT map and the "defeat" capture was really a need_choice).
        c = refresh("audit_user_1")
        for it in list(c.find_items_by_kind(ItemKind.TREASURE_MAP)):
            c.remove_item_entity(it.uid)
        CharacterRepository.save(c)
        c = refresh("audit_user_1")
        node = WorldGridEngine.get_node(c.location)
        tmap = TreasureEngine.generate_treasure_map(
            c, tier=tier, preferred_target=node.id, preferred_archetype=archetype)
        c.add_item_entity(tmap)
        CharacterRepository.save(c)
        return tmap

    # wrong-location first: map targeting a far node, dig from here.
    # NOTE: c.location holds a node NAME (e.g. 青云坊市客栈); compare by
    # resolved node id, not by raw string.
    c = refresh("audit_user_1")
    cur_node = WorldGridEngine.get_node(c.location)
    far = next(n for n in nodes if n.id != (cur_node.id if cur_node else c.location))
    tmap = TreasureEngine.generate_treasure_map(
        c, tier=2, preferred_target=far.id,
        preferred_archetype=TreasureArchetype.ELEMENT_PUZZLE)
    c.add_item_entity(tmap)
    CharacterRepository.save(c)
    run(token, "/挖宝", "dig-wrong-location", "map target != current node")
    # remove the far map so later digs use the fresh on-site map
    c = refresh("audit_user_1")
    for it in list(c.find_items_by_kind(ItemKind.TREASURE_MAP)):
        c.remove_item_entity(it.uid)
    CharacterRepository.save(c)

    grant_map(TreasureArchetype.ELEMENT_PUZZLE)
    run(token, "/挖宝", "dig-element-need-choice", "ELEMENT_PUZZLE, no choice -> need_choice")
    run(token, "/挖宝 1", "dig-element-clever", "ELEMENT_PUZZLE choice 1 (巧破)")
    grant_map(TreasureArchetype.ELEMENT_PUZZLE)
    grant_stones("audit_user_1")
    before = refresh("audit_user_1").spirit_stones
    r = run(token, "/挖宝 2", "dig-brute-force",
            f"brute_force: stones before={before}; expect NO stone_gain key semantics "
            "(dispatch fills 0) and text says -40 (see §6.1)")
    after = refresh("audit_user_1").spirit_stones
    if r:
        r["note"] += f" | stones after={after} (delta {after - before})"
        (cap.out_dir / cap.manifest["captures"][-1]["file"]).write_text(
            json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    grant_map(TreasureArchetype.RUIN_HAZARD)
    run(token, "/挖宝", "dig-scar-created",
        "RUIN_HAZARD -> scar_created relic 纯阳离火印 (§6.2 reproduction input)")
    grant_map(TreasureArchetype.COMBAT)
    run(token, "/挖宝", "dig-combat",
        "COMBAT outcome as rolled (victory needs power>=~127; defeat otherwise)")

    # ---------- Phase 4: blind box / loot ----------
    grant_stones("audit_user_1")
    for i in range(6):
        run(token, "/捡漏", f"blind-box-{i+1}", f"sample {i+1}/6, RNG seed {CAPTURE_SEED}")
        grant_stones("audit_user_1")

    # ---------- Phase 5: items / equip / pills ----------
    from core.items import ItemFactory
    c = refresh("audit_user_1")
    w = ItemFactory.create_equip(name="审计试剑", tier=3, slot="weapon", base_power=60.0)
    c.add_item_entity(w)
    pill = ItemFactory.create_pill(name="审计试丹", tier=2) if hasattr(ItemFactory, "create_pill") else None
    if pill is not None:
        c.add_item_entity(pill)
    CharacterRepository.save(c)
    run(token, "/穿戴 审计试剑", "equip-wear", "wear granted tier-3 weapon")
    run(token, "/look", "look-after-equip")
    run(token, "/卸下 审计试剑", "equip-remove", "remove weapon")
    if pill is not None:
        run(token, "/服用 审计试丹", "pill-use", "use granted pill")
    run(token, "/服用 不存在的丹", "pill-use-missing", "missing pill error path")

    # ---------- Phase 6: meditation / breakthrough ----------
    run(token, "/闭关 1", "meditate-1h", "enter meditation (TIME_SCALE test env)")
    run(token, "/look", "look-meditating", "read-only while meditating")
    run(token, "/出关", "emerge", "leave meditation")
    c = refresh("audit_user_1")
    c.realm.current_exp = c.realm.max_exp
    CharacterRepository.save(c)
    run(token, "/突破", "breakthrough", "full-exp breakthrough attempt")

    # ---------- Phase 7: market / trade / misc money flows ----------
    run(token, "/购买", "buy-noargs", "usage error path")
    run(token, "/出售", "sell-noargs", "usage error path")
    run(token, "/上拍 审计试剑 100", "auction-list", "list granted item (may fail if not in bag)")
    run(token, "/拍卖行", "auction-board", "auction board read")
    run(token, "/挂赏", "place-bounty-noargs", "usage error path")
    run(token, "/典当 审计试剑", "pawn", "pawn flow")
    run(token, "/赎回 审计试剑", "redeem", "redeem flow")
    run(token, "/寄售 审计试剑 100", "list-item", "consignment list flow")
    run(token, "/买寄售", "buy-listing-noargs", "usage error path")
    run(token, "/撤单", "cancel-listing-noargs", "usage error path")

    # ---------- Phase 8: social / sect / quests ----------
    run(token, "/拜入", "join-sect-noargs", "usage error path")
    run(token, "/领俸禄", "salary", "salary claim (likely not in sect)")
    run(token, "/晋升", "promote", "promote (likely not in sect)")
    run(token, "/传功", "teach-noargs", "usage error path")
    run(token, "/许诺", "promise-noargs", "usage error path")
    run(token, "/接委托", "acceptquest-noargs", "usage error path")
    run(token, "/交付", "deliver-noargs", "usage error path")
    run(token, "/弃委托", "abandonquest-noargs", "usage error path")
    run(token, "/投票", "vote-noargs", "usage error path")
    run(token, "/游说", "lobby-noargs", "usage error path")
    run(token, "/挂断", "hangup", "hangup with no session")
    run(token, "/释放", "release-captive", "release (alias /release shadowed by pet /放生, see ledger)")
    run(token, "/放生", "pet-release-noargs", "usage error path (pet release)")

    # ---------- Phase 9: NPC chat / free action (AI-off graceful paths) ----------
    here = WORLD.handle(token, "/here")
    npc_name = None
    try:
        txt = here.get("text", "") if isinstance(here, dict) else ""
        import re as _re
        m = _re.search(r"\[NPC\]\s*([^（(]+)", txt)
        if m:
            npc_name = m.group(1).strip()
    except Exception:
        pass
    if npc_name:
        run(token, f"/交谈 {npc_name} 你好", "talk-npc", f"NPC chat with {npc_name} (AI off)")
        run(token, "/说 你好", "say-no-session", "say without session")
        run(token, "/挂断", "hangup-after-talk")
    else:
        cap.fail("talk-npc", "/交谈", "no NPC name parsed from /roster")
    run(token, "/做 打坐调息", "free-action", "free action (AI DM off-graceful path)")
    run(token, "/斗法", "fight-noargs", "usage error path")

    # ---------- Phase 10: misc engines ----------
    run(token, "/炼丹", "alchemy-noargs", "usage/error path")
    run(token, "/炼器", "forge-noargs", "usage/error path")
    run(token, "/悟丹 测试配方", "wu-dan", "AI recipe path (AI off)")
    run(token, "/施法", "cast-noargs", "usage error path")
    run(token, "/祭法宝", "cast-treasure-noargs", "usage error path")
    run(token, "/探险", "adventure", "adventure entry")
    run(token, "/秘境", "secret", "secret realm entry")
    run(token, "/禁地", "dungeon", "dungeon entry")
    run(token, "/著书 测试", "write-book", "write book flow")
    run(token, "/研读", "read-book-noargs", "usage error path")
    run(token, "/自创功法 测试", "create-art", "custom art flow (AI off)")
    run(token, "/采药", "herbs", "herb gathering")
    run(token, "/探查", "scan", "scan surroundings")
    run(token, "/汲取", "spring", "spirit spring")
    run(token, "/探路", "crane", "crane scout")
    run(token, "/gm", "gm", "GM gate (expect denial)")
    run(token, "/大劫", "apocalypse", "apocalypse read")
    run(token, "/天道", "heaven", "director read")
    run(token, "/追", "follow-noargs", "usage error path")
    run(token, "/拜师", "apprentice-noargs", "usage error path")
    run(token, "/结拜", "sworn-noargs", "usage error path")
    run(token, "/绝交", "sever-noargs", "usage error path")
    run(token, "/叛师", "betray-noargs", "usage error path")
    run(token, "/上交", "donate-noargs", "usage error path")
    run(token, "/接宗门环", "acceptring-noargs", "usage error path")
    run(token, "/接宗门令", "acceptorder-noargs", "usage error path")
    run(token, "/交宗门令", "doneorder-noargs", "usage error path")
    run(token, "/议价", "haggle-noargs", "usage error path")
    run(token, "/招徕修士", "recruit", "recruit flow")
    run(token, "/收益", "earnings", "stall earnings read")
    run(token, "/寄存", "deposit-noargs", "usage error path")
    run(token, "/支取", "withdraw-noargs", "usage error path")
    run(token, "/契约", "contract-noargs", "usage error path")
    run(token, "/喂养", "feed-noargs", "usage error path")
    run(token, "/出战", "deploy-noargs", "usage error path")
    run(token, "/休息", "petrest-noargs", "usage error path")
    run(token, "/温养", "nourish", "spirit nourish")
    run(token, "/灵语", "spirit-say", "spirit say")
    run(token, "/主修", "main-art-noargs", "usage error path")
    run(token, "/辅修", "sub-art-noargs", "usage error path")
    run(token, "/卸功", "remove-art-noargs", "usage error path")
    run(token, "/炼体", "body", "body cultivation read")
    run(token, "/镇魔", "demon", "demon suppression")
    run(token, "/回访", "revenge", "revenge revisit")
    run(token, "/择道韵", "pick-boon-noargs", "usage error path")
    run(token, "/出招", "dungeon-attack-noargs", "usage error path")
    run(token, "/拍 1 100", "bid", "bid flow (likely no auction)")
    run(token, "/一口", "buyout-noargs", "usage error path")
    run(token, "/撤拍", "auction-cancel-noargs", "usage error path")
    run(token, "/买寄售 999", "buy-listing-missing", "missing listing")
    run(token, "/npc买", "npc-buy-noargs", "usage error path")
    run(token, "/npc卖", "npc-sell-noargs", "usage error path")
    run(token, "/npc货单", "npc-goods-noargs", "usage error path")
    run(token, "/不存在的命令", "unknown-command", "unknown command error")
    run(token, "", "empty-command", "empty input")

    # ---------- Phase 11: second character + trade ----------
    j2 = WORLD.join("审计员乙", user_id="audit_user_2")
    cap.save("join-second", "/join 审计员乙", j2, "second character for trade flows")
    token2 = j2.get("token")
    if token2:
        run(token, "/交易 审计员乙", "trade-init", "initiate face-to-face trade")
        run(token, "/交易出 审计试剑", "trade-offer", "offer item in trade")
        run(token2, "/交易同意", "trade-accept-second", "counterparty accept")
        run(token2, "/交易拒绝", "trade-reject-second", "counterparty reject (after accept)")

    # ---------- Phase 12: death / reincarnate ----------
    c = refresh("audit_user_1")
    c.status = "DEAD" if isinstance(c.status, str) else c.status
    try:
        from core.models import CharacterStatus
        c.status = CharacterStatus.DEAD
    except Exception:
        pass
    c.death_cause = "审计坐化"
    try:
        c.lifespan.burn_lifespan(9999)
    except Exception:
        pass
    CharacterRepository.save(c)
    jd = WORLD.join("审计员", user_id="audit_user_1")
    cap.save("join-dead", "/join 审计员 (dead)", jd, "dead payload (§2.2: login/death exit)")
    dead_token = jd.get("token")
    run(token, "/look", "look-while-dead", "dead gate: only /转世//道统 allowed")
    run(token, "/道统", "legacy-while-dead", "dead-allowed read")
    if dead_token:
        try:
            rr = WORLD.reincarnate(dead_token)
            cap.save("reincarnate", "reincarnate()", rr, "reincarnate() direct call payload")
        except Exception as e:
            cap.fail("reincarnate", "reincarnate()", f"{type(e).__name__}: {e}")
        # also via /转世 handle on the new token if reincarnate issued one
        new_token = None
        try:
            new_token = WORLD.join("审计员", user_id="audit_user_1").get("token")
        except Exception:
            pass
        if new_token:
            run(new_token, "/look", "look-after-rebirth", "first look of new life")
    else:
        cap.fail("reincarnate", "reincarnate()", "dead join returned no token")

    # ---------- Phase 13: logout + invalid token ----------
    run(token, "/logout", "logout", "logout flow")
    try:
        resp = WORLD.handle("invalid-token-xyz", "/look")
        cap.save("invalid-token", "/look (bad token)", resp, "invalid session error")
    except Exception as e:
        cap.fail("invalid-token", "/look (bad token)", f"{type(e).__name__}: {e}")

    # ---------- Phase 13b: missing-branch sweep + shadowed-alias routing ----------
    # NOTE: Phase 12/13 cycled death + logout, so re-join for a live token.
    _rj = WORLD.join("审计员", user_id="audit_user_1")
    if _rj.get("token"):
        token = _rj["token"]
        grant_stones("audit_user_1")
    run(token, "/定相 男", "gender-set", "set gender (branch /定相)")
    run(token, "/回应 1", "respond-drama-no-drama", "/回应 with no pending drama")
    run(token, "/钱包提取 10", "wallet-withdraw", "withdraw with (likely) empty wallet")
    run(token, "/归隐", "reclude", "reclude flow")
    run(token, "/出隐", "unreclude", "unreclude flow")
    run(token, "/任务", "tasks", "task system read (branch /任务, distinct from /委托)")
    run(token, "/名物", "mingwu", "famous objects read")
    run(token, "/追查", "chase-noargs", "chase flow")
    run(token, "/奇遇", "omen-scene-start", "/奇遇 starts omen scene (branch :2058; /omen alias is shadowed by :1959)")
    run(token, "/奇遇说 你好", "omen-say", "omen scene say (needs active scene)")
    run(token, "/开辟", "opencave", "open cave (farm)")
    run(token, "/播种 灵芝", "sow", "sow in cave")
    run(token, "/收获", "harvest", "harvest cave")
    run(token, "/升级洞府", "upgradecave", "upgrade cave")
    run(token, "/应诺", "acceptpromise-noargs", "accept promise (no pending)")
    run(token, "/毁诺", "breakpromise-noargs", "break promise (no pending)")
    run(token, "/叛门", "leave-sect", "leave sect (not in sect)")
    run(token, "/悟器 测试配方", "wu-qi",
        "same handler as /悟丹 (:2667); expect same UnboundLocalError (random local)")
    run(token, "/生成丹药", "gen-pill", "gen pill flow")
    run(token, "/生成法宝", "gen-equip", "gen equip flow")
    run(token, "/生成妖兽", "gen-monster", "gen monster flow")
    run(token, "/应劫", "arc-respond", "world-arc respond")
    run(token, "/确认拜师", "confirm-apprentice-noargs", "usage error path")
    run(token, "/收徒", "take-apprentice-noargs", "usage error path")
    run(token, "/出师", "graduate-noargs", "usage error path")
    run(token, "/结拜同意", "sworn-accept-noargs", "usage error path")
    run(token, "/师门任务", "sect-quests", "sect quests read")
    run(token, "/交师门", "sect-quest-done-noargs", "usage error path")
    run(token, "/结义任务", "sworn-quests", "sworn quests read")
    run(token, "/交结义", "sworn-quest-done-noargs", "usage error path")
    run(token, "/接除凶", "accept-hunt-noargs", "accept hunt (no args)")
    run(token, "/弃除凶", "abandon-hunt-noargs", "abandon hunt (no active hunt)")
    run(token, "/接令 1", "claim-bounty-numeric", "numeric /接令 -> bounty-claim branch :3887")
    run(token, "/接令 不存在的道号", "accept-hunt-name", "non-numeric /接令 -> hunt branch :3126")
    # shadowed-alias routing evidence (first-match-wins in the elif chain)
    run(token, "/omen", "alias-omen", "alias /omen must land on :1959 天象, NOT :2058 奇遇")
    run(token, "/天象", "alias-tianxiang", "alias /天象 must land on :1959, NOT :3065 望气")
    run(token, "/release", "alias-release", "alias /release must land on :2375 pet /放生, NOT :3570 /释放")
    run(token, "/help", "alias-help", "alias /help must land on :1938, NOT :4435 duplicate")
    run(token, "/trade", "trade-bare", "bare /trade (no args) -> :4229 fallback branch")
    run(token, "/交易 审计员乙", "trade-with-arg", "/交易 with arg -> :4222 guarded branch")

    # ---------- Phase 13c: /转世 via handle (second death) ----------
    c = refresh("audit_user_1")
    try:
        from core.models import CharacterStatus as _CS
        c.status = _CS.DEAD
    except Exception:
        pass
    c.death_cause = "审计再坐化"
    try:
        c.lifespan.burn_lifespan(9999)
    except Exception:
        pass
    CharacterRepository.save(c)
    jd2 = WORLD.join("审计员", user_id="audit_user_1")
    cap.save("join-dead-2", "/join 审计员 (dead, 2nd)", jd2, "second dead payload")
    dt2 = jd2.get("token")
    if dt2:
        run(dt2, "/转世", "reborn-via-handle", "/转世 handle branch :1731 -> reincarnate")
        run(dt2, "/look", "look-after-reborn-2", "first look after 2nd rebirth")

    # ---------- Phase 14: standalone status snapshot ----------
    try:
        t3 = WORLD.join("审计员", user_id="audit_user_1").get("token")
        token = t3
        st = WORLD.handle(t3, "/look")
        cap.save("status-snapshot", "/look (status snapshot)",
                 st.get("status") if isinstance(st, dict) else st,
                 "standalone _status_dict snapshot (77 top-level keys)")
    except Exception as e:
        cap.fail("status-snapshot", "/look", f"{type(e).__name__}: {e}")

    # ---------- Phase 16: supplemental outcomes (2nd-run additions) ----------
    # /挖宝 choice 3 (free-action redirect error path)
    grant_map(TreasureArchetype.ELEMENT_PUZZLE)
    run(token, "/挖宝 3", "dig-choice-3", "ELEMENT_PUZZLE choice 3 -> free-action redirect error")
    # COMBAT defeat: crush power via dao_heart so guardian wins
    c = refresh("audit_user_1")
    try:
        c.karma.dao_heart = 1
    except Exception:
        pass
    CharacterRepository.save(c)
    grant_map(TreasureArchetype.COMBAT)
    run(token, "/挖宝", "dig-combat-defeat", "COMBAT with dao_heart=1 -> combat_defeat outcome")
    c = refresh("audit_user_1")
    try:
        c.karma.dao_heart = 50
    except Exception:
        pass
    CharacterRepository.save(c)
    # /服用 + /出售 success: two clever digs yield two real pills
    grant_map(TreasureArchetype.ELEMENT_PUZZLE)
    grant_stones("audit_user_1")
    r = WORLD.handle(token, "/挖宝 1")
    cap.save("dig-clever-for-pill", "/挖宝 1 (for pill)", r, "clever dig to obtain a real pill for /服用")
    pill_name = (r.get("pill") or {}).get("name") if isinstance(r, dict) else None
    if pill_name:
        run(token, f"/出售 {pill_name}", "sell-success", f"sell real pill {pill_name} to the market")
    else:
        cap.fail("sell-success", "/出售 <pill>", "clever dig returned no pill")
    grant_map(TreasureArchetype.ELEMENT_PUZZLE)
    grant_stones("audit_user_1")
    r2 = WORLD.handle(token, "/挖宝 1")
    cap.save("dig-clever-for-pill-2", "/挖宝 1 (for pill 2)", r2, "second clever dig for /服用")
    pill_name2 = (r2.get("pill") or {}).get("name") if isinstance(r2, dict) else None
    if pill_name2:
        run(token, f"/服用 {pill_name2}", "pill-use-success", f"use real pill {pill_name2}")
    else:
        cap.fail("pill-use-success", "/服用 <pill>", "second clever dig returned no pill")
    # cross-character market: char2 lists, char1 buys; char1 sells a pill
    j2b = WORLD.join("审计员乙", user_id="audit_user_2")
    token2b = j2b.get("token")
    if token2b:
        c2 = refresh("audit_user_2")
        from core.items import ItemFactory as _IF
        _w = _IF.create_equip(name="审计寄售剑", tier=2, slot="weapon", base_power=40.0)
        c2.add_item_entity(_w)
        c2.spirit_stones = 100000
        CharacterRepository.save(c2)
        run(token2b, "/寄售 审计寄售剑 100", "list-item-2", "char2 lists item for char1 to buy")
        try:
            from storage.db import MarketListingRepository as _MLR
            _open = [l for l in _MLR.list_all() if l.is_open() and l.item_name == "审计寄售剑"]
            if _open:
                run(token, f"/买寄售 {_open[0].id}", "buy-listing-success",
                    f"char1 buys char2 listing id={_open[0].id}")
            else:
                cap.fail("buy-listing-success", "/买寄售 <id>", "no open listing found")
        except Exception as e:
            cap.fail("buy-listing-success", "/买寄售 <id>", f"{type(e).__name__}: {e}")
    grant_stones("audit_user_1")

    cap.write_manifest()
    print(f"captures: {len(cap.manifest['captures'])}, failures: {len(cap.manifest['failures'])}")
    for f in cap.manifest["failures"]:
        print("  FAIL:", f["slug"], f["command"], f["error"][:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
