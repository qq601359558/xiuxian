"""
炼丹 / 炼器：配方 + 材料 + 开炉成功率
AI 可「悟配方」，不可凭空发货。
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from config import ITEM_CATALOG
from core.models import Character, CharacterStatus
from core.character_integrity import CharacterIntegrity, CharacterIntegrityError
from storage.db import WorldStateRepository, CharacterRepository
from core.content_pack import RECIPES, ALCHEMY_MATERIAL_POOL
from core.catalogs.pills import PILL_RECIPES
from core.catalogs.equipments import EQUIPMENT_RECIPES

_KNOWN_KEY = "known_recipes"
_WU_KEY = "wu_recipe_cd"


def _all_recipes() -> Dict[str, Dict[str, Any]]:
    combined = {r["id"]: dict(r) for r in RECIPES}
    for pr in PILL_RECIPES:
        combined[pr["id"]] = dict(pr)
    for er in EQUIPMENT_RECIPES:
        combined[er["id"]] = dict(er)
    return combined


def _load_known(user_id: str) -> List[str]:
    try:
        d = WorldStateRepository.get(_KNOWN_KEY) or {}
        return list(d.get(user_id) or [])
    except Exception:
        return []


def _save_known(user_id: str, ids: List[str]) -> None:
    try:
        d = WorldStateRepository.get(_KNOWN_KEY) or {}
        d[user_id] = list(dict.fromkeys(ids))  # 去重保序
        WorldStateRepository.set(_KNOWN_KEY, d)
    except Exception:
        pass


def ensure_default_recipes(c: Character) -> List[str]:
    known = _load_known(c.user_id)
    if known:
        return known
    known = [r["id"] for r in RECIPES if r.get("known_by_default")]
    _save_known(c.user_id, known)
    return known


def learn_recipe(c: Character, recipe_id: str) -> bool:
    known = ensure_default_recipes(c)
    if recipe_id in known:
        return False
    known.append(recipe_id)
    _save_known(c.user_id, known)
    return True


def get_recipe(name_or_id: str, known_only: bool = False, user_id: str = "") -> Optional[Dict[str, Any]]:
    book = _all_recipes()
    if name_or_id in book:
        r = book[name_or_id]
    else:
        r = None
        for x in book.values():
            if name_or_id and (name_or_id in x["name"] or x["name"] in name_or_id or name_or_id == x["output"]):
                r = x
                break
    if not r:
        return None
    if known_only and user_id:
        if r["id"] not in _load_known(user_id):
            return None
    return r


def success_rate(c: Character, recipe: Dict[str, Any]) -> float:
    rate = float(recipe.get("base_rate") or 0.5)
    rate += 0.03 * c.realm.tier
    rate += 0.001 * (c.karma.dao_heart - 50)
    return max(0.15, min(0.95, rate))


def format_book(c: Character) -> str:
    known = ensure_default_recipes(c)
    book = _all_recipes()
    lines = [
        f"【配方】已悟 {len(known)} 张 · 药材/妖材在 /道身 行囊",
        "炼制：/炼丹 <方名> · /炼器 <方名>；悟新方：/悟丹 <理念> · /悟器 <理念>",
    ]
    for rid in known:
        r = book.get(rid)
        if not r:
            continue
        mats = "、".join(f"{k}×{v}" for k, v in (r.get("materials") or {}).items())
        ok_mats = True
        for k, v in (r.get("materials") or {}).items():
            if c.inventory.count(k) + c.arrays.count(k) < v:
                ok_mats = False
                break
        mark = "✓" if ok_mats and c.spirit_stones >= r.get("stones_fee", 0) else "○"
        rate = success_rate(c, r)
        tier_ok = "境界足" if c.realm.tier >= r.get("req_tier", 0) else f"需{r.get('req_tier')}阶"
        lines.append(
            f"  {mark} [{r['kind']}] {r['name']} → {r['output']} | 材料：{mats} | "
            f"炉火 {r.get('stones_fee',0)}灵 | 成率 {rate:.0%} | {tier_ok}"
        )
    if not known:
        lines.append("  （尚未习得任何配方）")
    return "\n".join(lines)


def _take_materials(c: Character, materials: Dict[str, int], half_on_fail: bool = False) -> Optional[List[Tuple[str, int]]]:
    """校验并扣除；失败路径用 half_on_fail。返回实际扣除列表或 None（材料不足）"""
    need = []
    for item, n in (materials or {}).items():
        have = c.inventory.count(item) + c.arrays.count(item)
        if have < n:
            return None
        need.append((item, n))
    taken = []
    for item, n in need:
        left = n
        while left > 0 and item in c.inventory:
            c.inventory.remove(item)
            left -= 1
        while left > 0 and item in c.arrays:
            c.arrays.remove(item)
            left -= 1
        taken.append((item, n))
    return taken


def _return_half(c: Character, taken: List[Tuple[str, int]], kind: str) -> None:
    for item, n in taken:
        back = math.ceil(n / 2)
        for _ in range(back):
            if kind == "array":
                c.inventory.append(item)
            else:
                c.inventory.append(item)


def craft(c: Character, recipe_name: str, kind: str) -> Dict[str, Any]:
    """kind: pill|equip —— 决定用 /炼丹 还是 /炼器 的提示语"""
    action_name = f"/{'炼器' if kind == 'equip' else '炼丹'}"
    try:
        CharacterIntegrity.assert_alive(c)
        CharacterIntegrity.assert_idle(c, action=action_name)
        CharacterIntegrity.assert_bag_space(c, needed_slots=1)
    except CharacterIntegrityError as e:
        return {"success": False, "message": str(e)}

    r = get_recipe(recipe_name, known_only=True, user_id=c.user_id)
    if not r:
        # 是否未习得
        r2 = get_recipe(recipe_name)
        if r2:
            return {"success": False, "message": f"尚未习得【{r2.get('name')}】。可 /悟丹 或 /悟器，或探索得残方。"}
        return {"success": False, "message": f"未知配方：{recipe_name}。/配方 查看。"}
    if r.get("kind") != kind:
        return {"success": False, "message": f"【{r['name']}】是{'炼器' if r['kind']=='equip' else '炼丹'}方。"}
    if c.realm.tier < r.get("req_tier", 0):
        return {"success": False, "message": f"境界不足，需 {r.get('req_tier')} 阶以上。"}
    fee = int(r.get("stones_fee") or 0)
    try:
        CharacterIntegrity.assert_currency(c, fee)
    except CharacterIntegrityError as e:
        return {"success": False, "message": f"开炉需 {fee} 灵石，{e}"}

    taken = _take_materials(c, r.get("materials") or {})
    if taken is None:
        mats = "、".join(f"{k}×{v}" for k, v in (r.get("materials") or {}).items())
        return {"success": False, "message": f"材料不足，需：{mats}"}

    CharacterIntegrity.deduct_currency(c, fee)
    rate = success_rate(c, r)
    roll = random.random()
    if roll < rate:
        out = r["output"]
        cfg = ITEM_CATALOG.get(out) or {}
        if cfg.get("kind") == "array" or r["kind"] == "equip" and cfg.get("kind") == "array":
            c.arrays.append(out) if out not in c.arrays else c.inventory.append(out)
        else:
            c.inventory.append(out)
        CharacterRepository.save(c)
        try:
            from core import ai_flavor

            _ = ai_flavor  # 预留
        except Exception:
            pass
        return {
            "success": True,
            "crafted": True,
            "output": out,
            "message": (
                f"【开炉功成】按【{r['name']}】炼出【{out}】！"
                f"（成率 {rate:.0%}，炉火 {fee}）"
            ),
        }

    # 失败：材料损半
    _return_half(c, taken, r.get("kind") or "material")
    CharacterRepository.save(c)
    return {
        "success": True,
        "crafted": False,
        "message": (
            f"【开炉失败】【{r['name']}】火候未到，药力溃散。"
            f"材料折损约半，炉火 {fee} 已耗。（成率 {rate:.0%}）"
        ),
    }


def can_wu(c: Character, now: Optional[float] = None) -> Tuple[bool, str]:
    t = now if now is not None else time.time()
    try:
        d = WorldStateRepository.get(_WU_KEY) or {}
        last = float(d.get(c.user_id) or 0)
        if t - last < 86400:
            left = 86400 - (t - last)
            return False, f"悟性未复，还需约 {left/3600:.1f} 小时方可再悟新方。"
    except Exception:
        pass
    return True, ""


def mark_wu(c: Character, now: Optional[float] = None) -> None:
    t = now if now is not None else time.time()
    try:
        d = WorldStateRepository.get(_WU_KEY) or {}
        d[c.user_id] = t
        WorldStateRepository.set(_WU_KEY, d)
    except Exception:
        pass


def ingest_ai_recipe(data: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
    """把 AI 悟方提案钳成合法 recipe（不直接发货）"""
    if not data:
        return None
    name = str(data.get("name") or "").strip()[:20]
    if not name:
        return None
    mats_in = data.get("materials") or {}
    materials: Dict[str, int] = {}
    if isinstance(mats_in, dict):
        for k, v in mats_in.items():
            k = str(k).strip()
            if k not in ALCHEMY_MATERIAL_POOL and k not in ITEM_CATALOG:
                continue
            try:
                n = max(1, min(5, int(v)))
            except Exception:
                n = 1
            materials[k] = n
    if not materials:
        materials = {ALCHEMY_MATERIAL_POOL[0]: 2}
    try:
        fee = max(5, min(300, int(data.get("stones_fee") or 40)))
    except Exception:
        fee = 40
    try:
        base = max(0.25, min(0.85, float(data.get("base_rate") or 0.5)))
    except Exception:
        base = 0.5
    req_tier = max(0, min(4, int(data.get("req_tier") or 1)))
    # 产出：若指定了已有货单名则用；否则造临时产出定义
    output = str(data.get("output") or "").strip()[:20]
    if output not in ITEM_CATALOG:
        # 用配方名当产出名
        output = name.replace("方", "").replace("图", "").replace("谱", "")[:12] or name
        grade = str(data.get("grade") or ("凡品" if base > 0.6 else "人品"))
        if kind == "pill":
            try:
                mult = max(0.08, min(0.5, float(data.get("pill_exp_mult") or 0.15)))
            except Exception:
                mult = 0.15
            ITEM_CATALOG[output] = {
                "kind": "pill",
                "price": max(20, int(mult * 400)),
                "grade": grade,
                "pill_exp_mult": round(mult, 2),
                "desc": f"{grade}（悟方所出）。下次闭关修为 +{int(mult*100)}%。",
            }
        else:
            try:
                bonus = max(0.02, min(0.08, float(data.get("power_bonus") or 0.03)))
            except Exception:
                bonus = 0.03
            ITEM_CATALOG[output] = {
                "kind": "equip",
                "slot": "weapon",
                "grade": grade,
                "power_bonus": round(bonus, 3),
                "price": max(80, int(bonus * 3000)),
                "desc": f"{grade}（悟方所出）。战力 +{int(bonus*100)}%。",
            }
    rid = f"r_ai_{abs(hash(name)) % 100000}"
    recipe = {
        "id": rid,
        "name": name if "方" in name or "图" in name or "谱" in name else name + ("方" if kind == "pill" else "图"),
        "kind": kind,
        "output": output,
        "materials": materials,
        "stones_fee": fee,
        "base_rate": base,
        "req_tier": req_tier,
        "known_by_default": False,
        "lore": str(data.get("lore") or "悟自天道残篇。")[:60],
    }
    # 写入全局配方表（进程内 RECIPES 列表）
    RECIPES.append(recipe)
    return recipe


def recycle_pill(c: Character, pill_name: str, qty: int = 1) -> Dict[str, Any]:
    """
    回炉炼化：将耐药抗性过高、淘汰或闲置的丹药投入造化神炉回炉分解
    - 扣减背包中对应的丹药数量 (实体或 inventory)
    - 返还基础灵石（根据丹药价值折算 50%）
    - 提炼萃取出相应品阶的药引灵砂（如灰岩灵砂、轻灵砂、庚金砂、纯阳玉髓等）
    - 解决丹药随游戏进程贬值无用的经济痛点（实现丹道闭环经济循环）
    """
    pill_name = (pill_name or "").strip()
    if not pill_name:
        return {"success": False, "message": "请指定要回炉的丹药名称。"}
    if qty <= 0:
        return {"success": False, "message": "回炉数量必须为正整数。"}

    from core.character_integrity import CharacterIntegrity, CharacterIntegrityError
    try:
        CharacterIntegrity.assert_alive(c)
    except CharacterIntegrityError as e:
        return {"success": False, "message": str(e)}

    # 1. 校验拥有的丹药数量
    actual_count = c.inventory.count(pill_name)
    if actual_count < qty:
        return {"success": False, "message": f"囊中仅有 {actual_count} 枚【{pill_name}】，不足 {qty} 枚。"}

    # 2. 获取丹药元数据
    from config import ITEM_CATALOG
    from core.catalogs.pills import PILL_CATALOG
    cfg = PILL_CATALOG.get(pill_name) or ITEM_CATALOG.get(pill_name) or {}
    tier = int(cfg.get("tier", 1))
    price = int(cfg.get("price", cfg.get("base_price", 40)))

    # 3. 扣减丹药 (优先扣实体，同步扣 inventory)
    removed_count = 0
    while removed_count < qty:
        it = c.find_item(pill_name)
        if it:
            c.remove_item_entity(it.uid)
        else:
            if pill_name in c.inventory:
                c.inventory.remove(pill_name)
        removed_count += 1

    # 4. 计算灵石返还 (单枚返还 50% 基准价，最低 5 灵石)
    refund_per_pill = max(5, int(price * 0.50))
    total_stones = refund_per_pill * qty
    c.spirit_stones += total_stones

    # 5. 回炉药引萃取 (提炼出纯净灵砂或药材)
    RECYCLE_BYPRODUCTS = {
        1: "灰岩灵砂",
        2: "轻灵砂",
        3: "庚金砂",
        4: "纯阳玉髓",
        5: "天道造化神水"
    }
    byproduct = RECYCLE_BYPRODUCTS.get(tier, "灰岩灵砂")
    gained_byproducts = 0
    for _ in range(qty):
        if random.random() < 0.50:
            gained_byproducts += 1

    byproduct_msg = ""
    if gained_byproducts > 0:
        for _ in range(gained_byproducts):
            c.inventory.append(byproduct)
        byproduct_msg = f"，同时丹炉余烬中凝聚出【{byproduct}】×{gained_byproducts}"

    return {
        "success": True,
        "recycled_pill": pill_name,
        "qty": qty,
        "spirit_stones_gained": total_stones,
        "byproduct": byproduct if gained_byproducts > 0 else None,
        "byproduct_count": gained_byproducts,
        "message": (
            f"【丹药回炉 · 造化化生】成功将 {qty} 枚【{pill_name}】投入造化烘炉炼化！\n"
            f"析出纯净灵液，折返灵石 +{total_stones}{byproduct_msg}。\n"
            f"当前随身灵石：{c.spirit_stones}。"
        )
    }
