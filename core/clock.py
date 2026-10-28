"""
天道时钟与寿元计算引擎 (严格现实时间与游戏时间并行版本)
"""
import time
import random
from typing import Tuple, Dict, Any, List, Optional
from config import (
    SECONDS_PER_GAME_YEAR,
    SECONDS_PER_GAME_MONTH,
    SECONDS_PER_GAME_DAY,
    WORLD_LOCATIONS,
    SECTS_CONFIG,
    MEDITATION_MAX_HOURS,
    LIFESPAN_WARNING_YEARS,
    design_hours_to_wall_seconds,
    wall_to_design_seconds,
    time_scale,
    is_production,
    env_time_label,
)
from core.models import (
    Character,
    Realm,
    Lifespan,
    SpiritualRoot,
    RootType,
    Element,
    CharacterStatus,
    MeditationSession,
    ArrayFormation,
)


class WorldClock:
    """天道全局时钟"""
    
    @staticmethod
    def now() -> float:
        return time.time()

    @staticmethod
    def format_game_time(timestamp: float) -> str:
        """将现实时间戳格式化为纪元天道历"""
        base_epoch = 1767225600.0  # 纪元元年基准
        elapsed_seconds = max(0.0, timestamp - base_epoch)
        game_years = int(elapsed_seconds / SECONDS_PER_GAME_YEAR) + 1
        rem_sec = elapsed_seconds % SECONDS_PER_GAME_YEAR
        game_months = int(rem_sec / SECONDS_PER_GAME_MONTH) + 1
        rem_month_sec = rem_sec % SECONDS_PER_GAME_MONTH
        game_days = int(rem_month_sec / SECONDS_PER_GAME_DAY) + 1
        return f"天道纪元 {game_years}年 · {game_months}月{game_days}日"

    @staticmethod
    def create_new_character(user_id: str, name: str) -> Character:
        """凡人入世：生成一名新修士（随机灵根与寿元）"""
        now = time.time()
        # 1. 随机出生寿元 70 ~ 100 岁 (现实天)
        birth_lifespan = random.uniform(70.0, 100.0)
        death_timestamp = now + (birth_lifespan * SECONDS_PER_GAME_YEAR)

        # 2. 随机灵根
        r = random.random()
        all_elements = [Element.METAL, Element.WOOD, Element.WATER, Element.FIRE, Element.EARTH]
        if r < 0.50:
            count = random.choice([4, 5])
            elems = random.sample(all_elements, count)
            root = SpiritualRoot(root_type=RootType.WASTE, elements=elems, efficiency=0.75)
        elif r < 0.85:
            count = random.choice([2, 3])
            elems = random.sample(all_elements, count)
            root = SpiritualRoot(root_type=RootType.TRUE, elements=elems, efficiency=1.1)
        elif r < 0.95:
            mutant_elem = random.choice([Element.WIND, Element.THUNDER, Element.ICE])
            root = SpiritualRoot(root_type=RootType.MUTANT, elements=[mutant_elem], efficiency=1.6)
        else:
            single_elem = random.choice(all_elements)
            root = SpiritualRoot(root_type=RootType.HEAVEN, elements=[single_elem], efficiency=2.2)

        char = Character(
            user_id=user_id,
            name=name,
            realm=Realm(tier=1, sub_tier=0, current_exp=0),
            lifespan=Lifespan(
                birth_base=birth_lifespan,
                accumulated_gain=0.0,
                death_timestamp=death_timestamp
            ),
            spiritual_root=root,
            spirit_stones=150,
            status=CharacterStatus.IDLE,
            meditation=MeditationSession(),
            location="青云坊市客栈",
            arrays=[],  # 初始散修背包空空，无阵盘
            inventory=["藏宝图"],  # 入世自带 1 张藏宝图，首次 /挖宝 100% 触发奇遇
        )
        return char

    @staticmethod
    def start_meditation(
        character: Character, 
        hours_planned: float = 1.0, 
        stones_to_pledge: int = 0
    ) -> Dict[str, Any]:
        """
        发起闭关：进入 MEDITATING 状态，现实时间开始锁定计时
        :param hours_planned: 计划闭关现实小时数 (现实1小时 ≈ 游戏内15.2天)
        :param stones_to_pledge: 投入碎石加速的灵石
        """
        now = time.time()
        if character.status == CharacterStatus.DEAD or character.lifespan.is_dead(now):
            return {"success": False, "message": "寿元已竭，肉身已朽，无法闭关！"}

        if character.status == CharacterStatus.MEDITATING:
            return {"success": False, "message": "道友已在闭关洞府之中，不可重复入定！"}

        if hours_planned <= 0:
            return {"success": False, "message": "闭关现实时长必须大于 0 小时！"}

        # 单次闭关计划上限 72 现实小时（可过夜/离线托管），有效收益仍只计前 24 小时
        if hours_planned > MEDITATION_MAX_HOURS * 3:
            return {
                "success": False,
                "message": (
                    f"单次闭关至多计划 {MEDITATION_MAX_HOURS * 3:.0f} 现实小时；"
                    f"有效收益仅前 {MEDITATION_MAX_HOURS:.0f} 小时，其后枯坐虚耗寿元。"
                ),
            }
        will_idle_sit = hours_planned > MEDITATION_MAX_HOURS

        # 检查寿元（闭关不得坐化于洞府：所需寿元须严格小于剩余寿元）
        rem_years = character.lifespan.get_remaining_years(now)
        game_years_needed = hours_planned / 24.0
        if rem_years <= game_years_needed:
            return {
                "success": False,
                "message": f"道友剩余寿元仅剩 {rem_years:.2f} 岁，不足以支撑闭关 {hours_planned} 小时（需要耗寿 {game_years_needed:.2f} 岁），若强行闭关必坐化于洞府中！"
            }

        # 预告：闭关结束时将跌破大限阈值
        after_years_est = rem_years - game_years_needed
        near_death_warning = after_years_est < LIFESPAN_WARNING_YEARS

        # 检查地点与租金 (若为本门弟子使用本门洞府，则享免租特权)
        loc_info = WORLD_LOCATIONS.get(character.location, {"density": 1.0, "is_safe": True, "rent_per_hour": 0})
        base_rent = loc_info.get("rent_per_hour", 0)
        is_sect_disciple = bool(character.sect and character.sect == loc_info.get("sect"))
        rent = 0 if is_sect_disciple else int(hours_planned * base_rent)

        if rent > 0:
            if character.spirit_stones < rent:
                return {
                    "success": False,
                    "message": f"在此【{character.location}】闭关需缴纳租金 {rent} 灵石，道友囊中仅有 {character.spirit_stones} 灵石，灵石不足！"
                }
            character.spirit_stones -= rent

        # 部署野外大阵 (若是野外危险区，必须背包有阵盘才可激活；无阵盘则裸露闭关)
        deployed_array = None
        array_msg = ""
        if not loc_info.get("is_safe", False):
            if character.arrays:
                array_name = character.arrays[0]
                deployed_array = ArrayFormation(
                    name=array_name,
                    max_durability=2000,
                    current_durability=2000,
                    concealment_bonus=120,
                    counter_damage=60,
                    is_active=True
                )
                array_msg = f"\n🛡️【阵法护体】野外凶险，已在洞口插下阵旗，激活【{array_name}】（罡气结界 2000 点，隐匿 +120）！"
            else:
                array_msg = f"\n⚠️【荒野裸露闭关】储物袋中无阵盘！你在荒郊旷野露天吐纳，六识闭塞！若遭路过修士或妖兽伏击，将无阵可依，必遭惨痛重创！"

        actual_stones = min(character.spirit_stones, stones_to_pledge)

        # 锁定状态：墙钟时长按环境倍速换算（生产 ×1，测试可加速）
        end_time = now + design_hours_to_wall_seconds(hours_planned)
        character.status = CharacterStatus.MEDITATING
        character.meditation = MeditationSession(
            is_active=True,
            start_time=now,
            end_time=end_time,
            hours_planned=hours_planned,
            stones_pledged=actual_stones,
            array=deployed_array
        )

        game_days = int(game_years_needed * 365)
        if is_sect_disciple and base_rent > 0:
            rent_str = f"（享受【{character.sect}】本门弟子特权，免收洞府租金 {int(hours_planned * base_rent)} 灵石）"
        elif rent > 0:
            rent_str = f"（已扣除租金 {rent} 灵石）"
        else:
            rent_str = "（野外无主之地，零租金）"

        warning_msg = ""
        if will_idle_sit:
            warning_msg += (
                f"\n⚠️【枯坐预警】有效吐纳仅前 {MEDITATION_MAX_HOURS:.0f} 现实小时，"
                f"其后 {hours_planned - MEDITATION_MAX_HOURS:.1f} 小时再无修为进境，只空耗寿元。"
            )
        if near_death_warning:
            warning_msg += (
                f"\n⚠️【大限预警】此番闭关结束，剩余寿元将不足 {LIFESPAN_WARNING_YEARS:.0f} 岁"
                f"（约 {after_years_est:.2f} 岁）。闭关途中若跌破阈值会强制警示，可随时 /出关 抉择。"
            )
        if getattr(character, "pill_exp_mult", 0) > 0:
            warning_msg += (
                f"\n【丹药加成】{character.pill_exp_note or '丹药'} 药力将在本次闭关修为上 ×"
                f"{1 + character.pill_exp_mult:.2f}"
            )

        return {
            "success": True,
            "start_time": now,
            "end_time": end_time,
            "hours_planned": hours_planned,
            "game_days_expected": game_days,
            "stones_pledged": actual_stones,
            "location": character.location,
            "density": loc_info.get("density", 1.0),
            "is_naked": deployed_array is None and not loc_info.get("is_safe", False),
            "will_idle_sit": will_idle_sit,
            "near_death_warning": near_death_warning,
            "rem_years_before": rem_years,
            "rem_years_after_est": after_years_est,
            "time_scale": time_scale(),
            "wall_hours": hours_planned / max(time_scale(), 1e-9),
            "env": env_time_label(),
            "message": (
                f"【遁入洞府 · 闭关锁门】\n"
                f"道友于【{character.location}】步入静室闭关入定，封绝外界杂音！{rent_str}\n"
                f"· 此地灵气浓度：{loc_info.get('density', 1.0):.1f}x （吐纳进境加成）\n"
                f"· 计划闭关 {hours_planned:.2f} 小时 (世间将过 {game_days} 天)"
                + (
                    f"\n· ⏱【测试加速】{env_time_label()}，墙钟约 {hours_planned / max(time_scale(), 1e-9):.2f} 小时"
                    if time_scale() != 1.0 else ""
                )
                + f"\n· 预定出关时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}{array_msg}"
                f"{warning_msg}\n"
                f"⚠️ 闭关期间不可探查、不可斗法！如遇急事可输入 /出关 提前出关。"
            )
        }



    @staticmethod
    def get_meditation_progress(character: Character, now: Optional[float] = None) -> Dict[str, Any]:
        """获取当前闭关实时倒计时与状态"""
        if not character.meditation.is_active or character.status != CharacterStatus.MEDITATING:
            return {"is_meditating": False}

        current_time = now or time.time()
        start = character.meditation.start_time
        end = character.meditation.end_time

        elapsed_sec = max(0.0, current_time - start)
        rem_sec = end - current_time

        total_sec = max(1.0, end - start)
        pct = min(1.0, elapsed_sec / total_sec)

        is_completed = rem_sec <= 0.0

        rem_years = character.lifespan.get_remaining_years(current_time)
        lifespan_warning = rem_years <= LIFESPAN_WARNING_YEARS
        # 闭关途中寿元耗尽：必须强制出关结算，禁止默默坐化
        is_expired = character.lifespan.is_dead(current_time)
        # 设计秒（收益/枯坐窗口按设计小时，不按墙钟）
        elapsed_design_sec = wall_to_design_seconds(elapsed_sec)
        remaining_design_sec = wall_to_design_seconds(max(0.0, rem_sec))
        effective_sec = min(elapsed_design_sec, MEDITATION_MAX_HOURS * 3600.0)
        is_idle_sitting = elapsed_design_sec > MEDITATION_MAX_HOURS * 3600.0 + 1.0

        return {
            "is_meditating": True,
            "is_completed": is_completed,
            "elapsed_seconds": elapsed_sec,
            "remaining_seconds": max(0.0, rem_sec),
            "elapsed_design_seconds": elapsed_design_sec,
            "remaining_design_seconds": remaining_design_sec,
            "remaining_design_hours": remaining_design_sec / 3600.0,
            "elapsed_design_hours": elapsed_design_sec / 3600.0,
            "time_scale": time_scale(),
            "progress_pct": pct,
            "end_time": end,
            "array": character.meditation.array,
            "rem_years": rem_years,
            "lifespan_warning": lifespan_warning,
            "is_expired": is_expired,
            "effective_seconds": effective_sec,
            "is_idle_sitting": is_idle_sitting,
            "force_settle": is_completed or is_expired or lifespan_warning,
        }

    @staticmethod
    def settle_meditation(
        character: Character,
        force_interrupt: bool = False,
        now: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        出关结算：根据现实流逝时间与地点灵气浓度，严格结算修为与寿元
        :param force_interrupt: 是否为主动提前破关
        """
        current_time = now or time.time()
        if not character.meditation.is_active or character.status != CharacterStatus.MEDITATING:
            return {"success": False, "message": "道友并未处于闭关状态之中。"}

        session = character.meditation
        start = session.start_time
        end = session.end_time

        # 天道无情：闭关途中寿尽则截断到死亡时刻，不得默默吞掉
        death_ts = character.lifespan.death_timestamp
        settle_boundary = min(current_time, end)
        died_in_cave = death_ts <= settle_boundary and death_ts > start
        if died_in_cave:
            settle_boundary = death_ts

        actual_elapsed_wall = max(0.0, settle_boundary - start)
        # 设计时长：墙钟 × 倍速（生产 ×1）
        actual_elapsed_sec = wall_to_design_seconds(actual_elapsed_wall)
        actual_real_hours = actual_elapsed_sec / 3600.0

        consumed_game_years = actual_elapsed_sec / SECONDS_PER_GAME_YEAR
        consumed_game_days = int(actual_elapsed_sec / SECONDS_PER_GAME_DAY)

        before_years = character.lifespan.get_remaining_years(current_time)
        before_exp = character.realm.current_exp

        # 扣除寿元（按设计流逝，含枯坐时段）
        character.lifespan.burn_lifespan(consumed_game_years)
        # 自创功法额外燃寿（每闭关年）
        try:
            from core.art import total_burn_per_year
            art_burn = total_burn_per_year(getattr(character, "custom_arts", None))
        except Exception:
            art_burn = 0.0
        if art_burn > 0 and not died_in_cave:
            character.lifespan.burn_lifespan(consumed_game_years * art_burn)
        after_years = character.lifespan.get_remaining_years(current_time)

        # 有效收益窗口：超过 MEDITATION_MAX_HOURS 枯坐无益，寿元照扣
        effective_sec = min(actual_elapsed_sec, MEDITATION_MAX_HOURS * 3600.0)
        effective_hours = effective_sec / 3600.0
        is_idle_sitting = actual_elapsed_sec > MEDITATION_MAX_HOURS * 3600.0 + 1.0

        # 地点灵气浓度加成
        loc_info = WORLD_LOCATIONS.get(character.location, {"density": 1.0, "is_safe": True})
        density_mult = loc_info.get("density", 1.0)

        # 全服灵气稀释（高阶修士越多，吐纳越慢）
        try:
            from core.qi import global_qi_multiplier
            qi_mult = global_qi_multiplier()
        except Exception:
            qi_mult = 1.0

        # 基础修为产出 = 基础率 * 有效小时 * 灵根加成 * 地点灵气 * 全服稀释 * 功法
        try:
            from core.art import best_exp_multiplier
            art_mult = best_exp_multiplier(getattr(character, "custom_arts", None))
        except Exception:
            art_mult = 1.0
        newbie_mult = 1.0
        try:
            from config import NEWBIE_EXP_MULT
            if character.is_newbie_protected(current_time):
                newbie_mult = NEWBIE_EXP_MULT
        except Exception:
            pass
        pill_mult = 1.0 + max(0.0, float(getattr(character, "pill_exp_mult", 0.0) or 0.0))
        base_exp_per_hour = 28.0 * (1.0 + character.realm.tier * 0.4)
        raw_gain = (
            base_exp_per_hour
            * effective_hours
            * character.spiritual_root.efficiency
            * density_mult
            * qi_mult
            * art_mult
            * newbie_mult
            * pill_mult
        )

        # 碎石加速结算（按有效时长占比）
        time_ratio = min(1.0, actual_elapsed_sec / max(1.0, wall_to_design_seconds(end - start)))
        actual_stones_burned = int(session.stones_pledged * time_ratio)
        actual_stones_burned = min(character.spirit_stones, actual_stones_burned)
        character.spirit_stones -= actual_stones_burned
        stone_bonus_mult = 1.0 + min(1.0, (actual_stones_burned / 50.0) * 0.5)

        # 心境判定
        roll = random.random()
        event_title = "气定神闲 · 循序渐进"
        event_desc = f"在【{character.location}】吐纳，精纯天地灵气周流全身。"
        event_multiplier = 1.0

        if died_in_cave:
            event_title = "【洞府坐化 · 大限已至】"
            event_desc = "闭关途中寿元灯枯，肉身于静室中悄然坐化，真灵散入天地……"
            event_multiplier = 0.0
        elif is_idle_sitting:
            event_title = "【枯坐虚耗 · 收效甚微】"
            event_desc = (
                f"有效吐纳仅前 {MEDITATION_MAX_HOURS:.0f} 现实小时，"
                f"其后枯坐只是空耗光阴与寿元，再无进境。"
            )
        elif roll < 0.15:
            event_multiplier = 1.6
            event_title = "【天人交感 · 大顿悟】"
            event_desc = "入定之时灵光乍现，神识与天地灵脉共鸣，修为暴涨 60%！"
        elif roll < 0.25:
            event_multiplier = 0.7
            event_title = "【尘缘纷扰 · 杂念丛生】"
            event_desc = "静室之中杂念偶生，难以彻底入寂，吐纳略打折扣。"

        if force_interrupt and not died_in_cave:
            event_title = "【急事强退 · 提前破关】"
            event_desc = f"道友在闭关途中强行收功破关，按实际闭关 {actual_real_hours:.2f} 小时结算修为。"

        final_gain = int(raw_gain * stone_bonus_mult * event_multiplier)
        character.realm.current_exp = min(character.realm.max_exp, before_exp + final_gain)
        actual_gain = character.realm.current_exp - before_exp

        # 恢复状态，收起阵法
        is_fatal = False
        if died_in_cave or character.lifespan.is_dead(current_time):
            character.status = CharacterStatus.DEAD
            character.meditation = MeditationSession(is_active=False)
            is_fatal = True
        else:
            character.status = CharacterStatus.IDLE
            character.meditation = MeditationSession(is_active=False)
        # 丹药药力：本次闭关已用则耗尽
        pill_note = getattr(character, "pill_exp_note", "") or ""
        if pill_mult > 1.0 and pill_note:
            character.pill_exp_mult = 0.0
            character.pill_exp_note = ""

        world_rumors = [] if is_fatal else WorldClock.generate_ambient_events(consumed_game_years)
        if died_in_cave:
            world_rumors = ["洞府石门自此紧闭，再无人见道友出关；数日后同道破门，唯余枯骨与未竟功法。"]

        return {
            "success": True,
            "is_interrupted": force_interrupt,
            "is_fatal": is_fatal,
            "died_in_cave": died_in_cave,
            "is_idle_sitting": is_idle_sitting,
            "hours": actual_real_hours,
            "actual_real_hours": actual_real_hours,
            "effective_hours": effective_hours,
            "time_scale": time_scale(),
            "consumed_days": consumed_game_days,
            "consumed_years": consumed_game_years,
            "before_years": before_years,
            "after_years": after_years,
            "before_exp": before_exp,
            "after_exp": character.realm.current_exp,
            "exp_gained": actual_gain,
            "max_exp": character.realm.max_exp,
            "stones_burned": actual_stones_burned,
            "location": character.location,
            "density_mult": density_mult,
            "qi_multiplier": qi_mult,
            "newbie_mult": newbie_mult,
            "pill_mult": pill_mult,
            "event_title": event_title,
            "event_desc": event_desc,
            "is_bottleneck": character.realm.is_full,
            "world_rumors": world_rumors,
            "message": event_desc if is_fatal else "",
        }

    @staticmethod
    def generate_ambient_events(game_years_passed: float) -> List[str]:
        """闭关期间外界因果事件推演"""
        pool = [
            "黑风峡谷深处传出古修墓穴开启异象，数位筑基修士为争残卷大打出手；",
            "青云坊市商行大拍会落幕，传闻一柄极品灵剑拍出了十二万灵石天价；",
            "正道巡查使在落霞山诛灭了一名红名魔修，天地显现功德祥云；",
            "天地灵脉流转，全服微型灵脉产出略微稀薄，灵石愈显珍贵；",
            "传闻有隐世老怪于东海之滨寿尽坐化，洞府遗迹现世引发群雄围堵。"
        ]
        count = 1 if game_years_passed < 0.5 else 2
        return random.sample(pool, min(count, len(pool)))
    @staticmethod
    def claim_sect_salary(character: Character, now: Optional[float] = None) -> Dict[str, Any]:
        """领取宗门月俸 (现实每 2 小时 = 游戏内 1 个月)"""
        current_time = now or time.time()
        if not character.sect:
            return {
                "success": False,
                "message": "道友乃一介散修，无门无派，何来宗门俸禄？可输入 /地图 探寻仙门山门拜入宗门。"
            }

        
        sect_cfg = SECTS_CONFIG.get(character.sect)
        if not sect_cfg:
            return {"success": False, "message": f"未知的宗门势力：{character.sect}"}
            
        salary = sect_cfg.get("monthly_salary", 0)
        if salary <= 0:
            return {"success": False, "message": f"【{character.sect}】乃散修商会同盟，自力更生，不发放常务月俸。"}

        # 冷却周期：现实 7200 秒 = 2 小时 = 游戏内 1 个月
        interval = SECONDS_PER_GAME_MONTH
        elapsed = current_time - character.last_salary_time
        if elapsed < interval and character.last_salary_time > 0.0:
            rem_sec = interval - elapsed
            mins = int(rem_sec // 60)
            secs = int(rem_sec % 60)
            return {
                "success": False,
                "message": f"本月俸禄已支取！距离下次发放月俸还需现实时间：{mins}分{secs}秒（游戏历每月初发放一次）。"
            }

        character.spirit_stones += salary
        character.last_salary_time = current_time
        return {
            "success": True,
            "salary": salary,
            "message": f"【宗门俸禄发放】执事堂核验无误，为【{character.sect} · {character.sect_rank}】发放本月月俸：{salary} 块灵石！"
        }

    @staticmethod
    def meditate(character: Character, hours_to_meditate: float = 1.0) -> Tuple[int, float, str]:
        """旧接口兼容"""
        return 0, 0.0, "请使用现实闭关流程"

