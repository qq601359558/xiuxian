"""
转世与道统点：一世结算、元进度账本、降生加成
"""
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from config import (
    LEGACY_BASE_POINTS,
    LEGACY_PER_TIER,
    LEGACY_MERIT_DIVISOR,
    LEGACY_SIN_DIVISOR,
    LEGACY_SIN_PENALTY_MAX,
    LEGACY_MAX_PER_LIFE,
    LEGACY_SUICIDE_WINDOW_SECONDS,
    LEGACY_SUICIDE_THRESHOLD,
    LEGACY_SUICIDE_PENALTY,
    LEGACY_MAX_BOOSTS_PER_LIFE,
    LEGACY_BOOSTS,
    SECONDS_PER_GAME_YEAR,
    SHADOW_MIN_ABS,
    SHADOW_MAX_ENTRIES,
)
from core.models import Character, CharacterStatus, RootType


class PastLife(BaseModel):
    """前世档案摘要"""
    name: str
    realm: str
    cause: str
    lifespan_lived: float  # 约活了多少岁
    sin: int = 0
    merit: int = 0
    points_gained: int = 0
    died_at: float = 0.0


class ShadowEntry(BaseModel):
    """因果影子一条：某 NPC 与前世角色的态度/因果折算（转世后按衰减施加于新角）"""
    npc_id: str
    npc_name: str
    value: int  # 前世态度原值（-100..100）
    kind: str = "attitude"  # attitude | link（KarmaLink 折算）


class PromiseEcho(BaseModel):
    """未了之诺回声：死亡时被消散的未结诺摘要（只展示，不复活）"""
    other_name: str
    desc: str
    kind: str = ""
    role: str = ""  # 我许诺 / 诺于我


class LifeTrace(BaseModel):
    """一世留痕：死亡结算时捕获的完整快照（账户层，活过转世覆写）"""
    life_no: int  # 第几世（= 生成时的 total_lives+1）
    character_id: str  # 本世角色 id（捕获幂等键）
    name: str
    realm: str
    cause: str
    lifespan_lived: float = 0.0
    sin: int = 0
    merit: int = 0
    points_gained: int = 0  # settle 后回填，与 PastLife 同值
    died_at: float = 0.0
    sect: str = ""  # 本世宗门（空=散修）
    skills_learned: List[str] = Field(default_factory=list)  # 非默认功法名，截 12
    belongings: List[str] = Field(default_factory=list)  # 行囊+穿戴名快照（去重保序，截 20；遗物候选池）
    shadow: List[ShadowEntry] = Field(default_factory=list)
    open_promises: List[PromiseEcho] = Field(default_factory=list)


class WalletEntry(BaseModel):
    """账户钱包流水一条（余额为独立字段，不由流水重算）"""
    ts: float = 0.0
    kind: str = ""  # death_sweep / consignment_sale / auction_sale / auction_refund / wallet_withdraw
    amount: int = 0
    ref: str = ""  # 业务单据 id（寄售单 id／拍品 id／死者角色 id／withdraw:<ts>）
    note: str = ""
    # QA-D2：death_sweep 流水的随身／寄存 breakdown（显式字段，唯一主口径）。
    # 仅 death_sweep（含残差）条目有意义，且须满足 sweep_spirit + sweep_vault == amount；
    # 旧档（本字段上线前写入）的条目两字段均为 0，见 core/wallet.py 的 note 回退解析。
    sweep_spirit: int = 0
    sweep_vault: int = 0


class LegacyAccount(BaseModel):
    """账号级元进度（跨一世保留）"""
    user_id: str
    points: int = 0
    total_lives: int = 0
    total_points_earned: int = 0
    death_times: List[float] = Field(default_factory=list)
    past_lives: List[PastLife] = Field(default_factory=list)
    # 账户钱包（account-death-rework D1/D2）：余额独立于流水，≥0；旧档无此字段时补 0/[]
    wallet_stones: int = 0
    wallet_ledger: List[WalletEntry] = Field(default_factory=list)
    # 转世继承（reincarnation-inheritance §2.1）：旧档无此三字段时自动补默认值，零迁移
    traces: List[LifeTrace] = Field(default_factory=list)  # 截最近 10，与 past_lives 对齐
    shadow_applied: Dict[str, Any] = Field(default_factory=dict)  # {"life_no","char_id",...} 已施加标记
    inheritance_claims: Dict[str, int] = Field(default_factory=dict)  # {"heirloom": life_no, "art_memory": life_no}


class LegacyEngine:
    """道统传承裁决引擎"""

    @staticmethod
    def compute_points(character: Character) -> Dict[str, Any]:
        """按本世成就估算可结转的道统点（未计自杀惩罚）"""
        tier = character.realm.tier
        sin = character.karma.sin_value
        merit = character.karma.merit_value

        base = LEGACY_BASE_POINTS
        tier_pts = tier * LEGACY_PER_TIER
        merit_pts = merit // LEGACY_MERIT_DIVISOR
        sin_penalty = min(LEGACY_SIN_PENALTY_MAX, sin // LEGACY_SIN_DIVISOR)

        raw = max(0, base + tier_pts + merit_pts - sin_penalty)
        capped = min(LEGACY_MAX_PER_LIFE, raw)
        return {
            "base": base,
            "tier_points": tier_pts,
            "merit_points": merit_pts,
            "sin_penalty": sin_penalty,
            "raw": raw,
            "capped": capped,
        }

    @staticmethod
    def _recent_death_count(account: LegacyAccount, now: float) -> int:
        window_start = now - LEGACY_SUICIDE_WINDOW_SECONDS
        return sum(1 for t in account.death_times if t >= window_start)

    # ---------------- 留痕快照（reincarnation-inheritance §2.2） ----------------
    @staticmethod
    def _snapshot_shadow(character: Character) -> List[ShadowEntry]:
        """态度快照 + KarmaLink 折算合并：同 NPC 只保留绝对值大者，
        按 |value| 降序截 SHADOW_MAX_ENTRIES。仓储惰性导入避循环。"""
        from storage.db import CharacterRepository, KarmaLinkRepository, NpcMindRepository

        merged: Dict[str, ShadowEntry] = {}
        # 态度：遍历全部 mind 行，取对本世角色 |value| ≥ 门槛者
        try:
            minds = NpcMindRepository.list_all()
        except Exception:
            minds = []
        for mind in minds:
            npc_id = mind.get("npc_id") or ""
            att = (mind.get("attitudes") or {}).get(character.id)
            if not att:
                continue
            try:
                value = int(att.get("value") or 0)
            except (TypeError, ValueError):
                continue
            if abs(value) < SHADOW_MIN_ABS:
                continue
            npc = CharacterRepository.get_by_id(npc_id)
            if npc is None:
                continue  # NPC 名取不到则跳过该条
            merged[npc_id] = ShadowEntry(
                npc_id=npc_id, npc_name=npc.name, value=value, kind="attitude",
            )
        # KarmaLink：对端为 NPC 的行按类型折算（恩/师徒/结拜→+，仇/怨→−，断及其余跳过）
        sign_by_type = {"恩": 1, "师徒": 1, "结拜": 1, "仇": -1, "怨": -1}
        try:
            links = KarmaLinkRepository.list_all()
        except Exception:
            links = []
        for link in links:
            if not link.involves(character.id):
                continue
            sign = sign_by_type.get(link.link_type)
            if sign is None:
                continue
            other_id, other_name = link.other_side(character.id)
            other = CharacterRepository.get_by_id(other_id)
            if other is None:
                continue
            uid = str(other.user_id or "")
            if not (uid.startswith("npc_") or uid.startswith("ai_npc_")):
                continue  # 玩家间关系不折算入影子（只入痕迹清单展示，见 §2.3）
            magnitude = max(10, min(40, int(link.strength or 0) * 10))
            entry = ShadowEntry(
                npc_id=other_id, npc_name=other_name,
                value=sign * magnitude, kind="link",
            )
            cur = merged.get(other_id)
            if cur is None or abs(entry.value) > abs(cur.value):
                merged[other_id] = entry
        out = sorted(merged.values(), key=lambda e: -abs(e.value))
        return out[:SHADOW_MAX_ENTRIES]

    @staticmethod
    def _build_trace(
        account: LegacyAccount,
        character: Character,
        death_cause: str,
        lived: float,
        gained: int,
        current_time: float,
        dissolved_promises: Optional[List[Dict[str, Any]]],
    ) -> LifeTrace:
        # skills：排除默认二术，截 12
        skills_learned = [
            s for s in (character.skills or []) if s not in ("吐纳术", "御剑术")
        ][:12]
        # belongings：行囊+穿戴去重保序，截 20（阵盘 arrays 不入池，见 spec §3）
        belongings: List[str] = []
        for item in list(character.inventory or []) + list(character.equipped or []):
            if item and item not in belongings:
                belongings.append(item)
        belongings = belongings[:20]
        echoes: List[PromiseEcho] = []
        for d in (dissolved_promises or [])[:5]:
            if isinstance(d, PromiseEcho):
                echoes.append(d)
            elif isinstance(d, dict):
                echoes.append(PromiseEcho(
                    other_name=str(d.get("other_name") or ""),
                    desc=str(d.get("desc") or ""),
                    kind=str(d.get("kind") or ""),
                    role=str(d.get("role") or ""),
                ))
        return LifeTrace(
            life_no=account.total_lives + 1,
            character_id=character.id,
            name=character.name,
            realm=character.realm.name,
            cause=death_cause,
            lifespan_lived=round(lived, 1),
            sin=character.karma.sin_value,
            merit=character.karma.merit_value,
            points_gained=gained,
            died_at=current_time,
            sect=character.sect or "",
            skills_learned=skills_learned,
            belongings=belongings,
            shadow=LegacyEngine._snapshot_shadow(character),
            open_promises=echoes,
        )

    @staticmethod
    def settle_death(
        account: LegacyAccount,
        character: Character,
        death_cause: str = "身死道消",
        now: Optional[float] = None,
        dissolved_promises: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        本世终结：归档前世、结算道统点并入账。
        必须只调用一次（由 CLI 死亡流程保证）。

        dissolved_promises：调用方（server/CLI）在 settle 前经
        PromiseEngine.on_owner_death 取得的被消散未结诺摘要，写入本世留痕；
        未传参（直接调用）时留痕的未了之诺为空。
        """
        current_time = now or time.time()

        # MF-1 崩溃重放闸门（评审修订）：调用方先 save(account) 后 save(char)，
        # 两步间崩溃必然重入 settle；traces 中已有本角色留痕即本世已结算，
        # 直接返回幂等结果，不再入账/归档/大事记/传闻（首次结算不受影响）。
        for existing in account.traces:
            if existing.character_id == character.id:
                breakdown = LegacyEngine.compute_points(character)
                return {
                    "success": True,
                    "already_settled": True,
                    "points_gained": 0,
                    "points_raw": breakdown["capped"],
                    "penalty_applied": False,
                    "recent_deaths": LegacyEngine._recent_death_count(
                        account, current_time,
                    ),
                    "breakdown": breakdown,
                    "past_life": None,
                    "trace": existing,
                    "account_points": account.points,
                    "total_lives": account.total_lives,
                    "cause": death_cause,
                }

        # 若角色尚未标 DEAD，补标
        if character.status != CharacterStatus.DEAD:
            character.status = CharacterStatus.DEAD
        if character.death_cause is None:
            character.death_cause = death_cause
        character.death_settled = True

        breakdown = LegacyEngine.compute_points(character)
        raw_pts = breakdown["capped"]

        recent = LegacyEngine._recent_death_count(account, current_time)
        penalty_applied = recent >= LEGACY_SUICIDE_THRESHOLD
        gained = int(raw_pts * LEGACY_SUICIDE_PENALTY) if penalty_applied else raw_pts

        # 约活了多少岁：出生基数 + 突破增寿（近似本世寿元消耗）
        lived = character.lifespan.birth_base + character.lifespan.accumulated_gain

        past = PastLife(
            name=character.name,
            realm=character.realm.name,
            cause=death_cause,
            lifespan_lived=round(lived, 1),
            sin=character.karma.sin_value,
            merit=character.karma.merit_value,
            points_gained=gained,
            died_at=current_time,
        )

        # 留痕（与 PastLife 同源同次生成；character_id 幂等防崩溃重放双记）
        trace: Optional[LifeTrace] = None
        trace_is_new = False
        for existing in account.traces:
            if existing.character_id == character.id:
                trace = existing
                break
        if trace is None:
            trace = LegacyEngine._build_trace(
                account, character, death_cause, lived, gained,
                current_time, dissolved_promises,
            )
            trace_is_new = True

        account.points += gained
        account.total_points_earned += gained
        account.total_lives += 1
        account.death_times.append(current_time)
        # 只保留最近 20 次死亡时间戳
        account.death_times = account.death_times[-20:]
        account.past_lives.append(past)
        account.past_lives = account.past_lives[-10:]
        if trace_is_new:
            account.traces.append(trace)
            account.traces = account.traces[-10:]

        # 世界可见留痕：墓碑大事记 + 死亡传闻（失败不阻断结算，静默包裹）
        if trace_is_new:
            try:
                from storage.db import ChronicleRepository

                ChronicleRepository.record(
                    "TOMBSTONE", character.name,
                    f"{character.name} · {character.realm.name} · {death_cause} · "
                    f"享寿 {round(lived, 1)} 岁 · 业 {character.karma.sin_value} "
                    f"德 {character.karma.merit_value}",
                )
            except Exception:
                pass
            try:
                from core import rumors as _rumors

                _rumors.add_rumor(
                    f"听闻【{character.name}】{death_cause}，一世道途就此终了，江湖自此少了一位故人。",
                    origin=character.location or "",
                    tags=["death", "tombstone"],
                    truth=1.0,
                    now=current_time,
                )
            except Exception:
                pass

        return {
            "success": True,
            "points_gained": gained,
            "points_raw": raw_pts,
            "penalty_applied": penalty_applied,
            "recent_deaths": recent + 1,
            "breakdown": breakdown,
            "past_life": past,
            "trace": trace,
            "account_points": account.points,
            "total_lives": account.total_lives,
            "cause": death_cause,
        }

    @staticmethod
    def check_reincarnate_gate(
        account: LegacyAccount,
        now: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        是否允许立刻转世。
        仅「连续极速送死」时短暂锁转世，避免自杀刷点后马上再死。
        """
        current_time = now or time.time()
        recent = LegacyEngine._recent_death_count(account, current_time)
        if recent >= LEGACY_SUICIDE_THRESHOLD + 2:
            oldest_in_window = min(
                t for t in account.death_times
                if t >= current_time - LEGACY_SUICIDE_WINDOW_SECONDS
            )
            wait = int(LEGACY_SUICIDE_WINDOW_SECONDS - (current_time - oldest_in_window))
            wait = max(1, wait)
            return False, (
                f"真灵连遭重创，短时间内陨落过多（{recent} 次），需静养 {wait} 秒"
                f"待神魂稳固后方可再入轮回。"
            )
        return True, ""

    @staticmethod
    def list_boosts() -> List[Dict[str, Any]]:
        out = []
        for key, cfg in LEGACY_BOOSTS.items():
            out.append({
                "key": key,
                "name": cfg["name"],
                "cost": cfg["cost"],
                "desc": cfg["desc"],
            })
        return out

    @staticmethod
    def apply_birth_boosts(
        character: Character,
        account: LegacyAccount,
        boost_keys: List[str],
        *,
        old_trace: Optional[LifeTrace] = None,
    ) -> Dict[str, Any]:
        """
        转世降生时消费道统点，为新角色附加轻量出身优势。
        :param boost_keys: 如 ["stones", "lifespan"]；遗物用参数式 token
            "heirloom:<物品名>"（仅 heirloom 可带 param，其余带 param 视为非法）。
        :param old_trace: 前世留痕（heirloom/art_memory 的候选源）；未传时
            回退 account.traces[-1]（无痕迹则两项校验失败、不扣点）。

        继承抉择口径（spec §2.4）：先校验（候选存在、未领、点数足）→ 再扣点
        → 再落效果 → 置 claims；任一校验失败该项进 errors、不扣点、不置标记。
        bond_echo 在本函数内不直接生效：只扣点并作为已购标记经返回值
        "bond_echo" 报告给调用方（server/CLI 转世编排），由调用方据此为
        本次 apply_karma_shadow 选 retention/cap（见 core/inheritance.py）。
        """
        applied: List[str] = []
        errors: List[str] = []
        spent = 0
        bond_echo_bought = False

        trace = old_trace
        if trace is None and account.traces:
            trace = account.traces[-1]

        # 解析 token（key 或 key:param）+ 按 base key 去重且限量
        parsed: List[Tuple[str, Optional[str], str]] = []
        seen_bases: List[str] = []
        for raw in boost_keys:
            token = str(raw or "").strip()
            if not token:
                continue
            if ":" in token:
                base, param = token.split(":", 1)
                base, param = base.strip(), param.strip()
            else:
                base, param = token, None
            if base in seen_bases:
                continue
            seen_bases.append(base)
            parsed.append((base, param, token))

        if len(parsed) > LEGACY_MAX_BOOSTS_PER_LIFE:
            return {
                "success": False,
                "bond_echo": False,
                "message": (
                    f"单次转世至多选择 {LEGACY_MAX_BOOSTS_PER_LIFE} 项出身加成，"
                    f"天道不容贪求。"
                ),
            }

        # MF-2 先规划后执行（评审修订）：art_memory 候选在任何效果落账前
        # 一次算定，避免同批 skill 先授予后 art 按旧候选空扣。规划口径：
        # 同批 skill 将授予 = 残篇表首门角色未学者；art 候选依次取
        # skills_learned / 残篇表中第一个不在「角色已学 ∪ 同批 skill
        # 将授予」中的；正反序规划结果一致，执行阶段只用规划值不重算。
        _residuals = ("御风诀", "龟息敛气术", "小周天引气法", "血遁残篇")
        _planned_skill_grant: Optional[str] = None
        if "skill" in seen_bases:
            for _sk in _residuals:
                if _sk not in character.skills:
                    _planned_skill_grant = _sk
                    break
        _planned_art_candidate: Optional[str] = None
        if "art_memory" in seen_bases and trace is not None:
            _excluded = set(character.skills or [])
            if _planned_skill_grant:
                _excluded.add(_planned_skill_grant)
            for _sk in (trace.skills_learned or []):
                if _sk not in _excluded:
                    _planned_art_candidate = _sk
                    break
            if _planned_art_candidate is None:
                for _sk in _residuals:
                    if _sk not in _excluded:
                        _planned_art_candidate = _sk
                        break

        for key, param, token in parsed:
            cfg = LEGACY_BOOSTS.get(key)
            if not cfg:
                errors.append(f"未知道统传承：{token}")
                continue
            if param is not None and key != "heirloom":
                errors.append(f"传承【{cfg['name']}】不可带参数：{token}")
                continue
            cost = cfg["cost"]

            # ---- 新抉择先行校验（失败不扣点、不置标记，可改选） ----
            heirloom_item: Optional[str] = None
            art_candidate: Optional[str] = None
            claim_life_no: Optional[int] = None
            if key == "heirloom":
                if not param:
                    errors.append("【遗物留存】须指明遗物：heirloom:<物品名>（取自前世行囊）。")
                    continue
                if trace is None:
                    errors.append("【遗物留存】无前世痕迹，无遗物可承。")
                    continue
                if account.inheritance_claims.get("heirloom") == trace.life_no:
                    errors.append(f"【遗物留存】第 {trace.life_no} 世的遗物已领取，不可重领。")
                    continue
                if param not in (trace.belongings or []):
                    errors.append(f"【遗物留存】前世行囊中并无【{param}】，不可凭空取物。")
                    continue
                heirloom_item = param
                claim_life_no = trace.life_no
            elif key == "art_memory":
                # 观察1（评审修订）：必须有来源世痕迹才能领取，claims
                # 一律以 trace.life_no 为键（不再用合成 life_no 防撞键误拒）
                if trace is None:
                    errors.append("【前世心法】无前世痕迹，无心法可忆。")
                    continue
                life_no = trace.life_no
                if account.inheritance_claims.get("art_memory") == life_no:
                    errors.append(f"【前世心法】第 {life_no} 世的心法记忆已唤醒，不可重领。")
                    continue
                # 执行规划好的候选，不再临时重算（MF-2）
                art_candidate = _planned_art_candidate
                if not art_candidate:
                    errors.append("【前世心法】前世无功法可忆，残篇亦已尽数习得。")
                    continue
                claim_life_no = life_no

            if account.points < cost:
                errors.append(f"道统点不足，无法兑换【{cfg['name']}】（需 {cost}）")
                continue

            # ---- 扣点 → 落效果 → 置标记 ----
            account.points -= cost
            spent += cost
            if key == "stones":
                character.spirit_stones += 150
            elif key == "lifespan":
                character.lifespan.add_lifespan(8.0)
            elif key == "root":
                new_eff = min(2.5, character.spiritual_root.efficiency + 0.25)
                character.spiritual_root.efficiency = new_eff
            elif key == "skill":
                extras = ["御风诀", "龟息敛气术", "小周天引气法", "血遁残篇"]
                for sk in extras:
                    if sk not in character.skills:
                        character.skills.append(sk)
                        break
            elif key == "heirloom":
                # 移入新角行囊（不穿戴）；旧行将被转世覆写，消费以 claims 标记为准
                character.inventory.append(heirloom_item)  # type: ignore[arg-type]
                account.inheritance_claims["heirloom"] = int(claim_life_no)  # type: ignore[arg-type]
            elif key == "art_memory":
                if art_candidate not in character.skills:
                    character.skills.append(art_candidate)  # type: ignore[arg-type]
                account.inheritance_claims["art_memory"] = int(claim_life_no)  # type: ignore[arg-type]
            elif key == "bond_echo":
                bond_echo_bought = True
            applied.append(cfg["name"])

        return {
            "success": len(applied) > 0 or (not boost_keys),
            "applied": applied,
            "spent": spent,
            "errors": errors,
            "bond_echo": bond_echo_bought,
            "remaining_points": account.points,
            "message": (
                f"道统点化：已继承【{'、'.join(applied)}】，消耗 {spent} 点。"
                if applied
                else "本世未兑换任何道统传承。"
            ) + (("；" + "；".join(errors)) if errors else ""),
        }

    @staticmethod
    def default_account(user_id: str) -> LegacyAccount:
        return LegacyAccount(user_id=user_id)
