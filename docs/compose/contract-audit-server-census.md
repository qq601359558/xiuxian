# 服务端静态清册（contract-audit）

基线 `cfcc878`（main `af4d689` = v0.3.11-gray.18）。方法：AST 解析 `server/world.py`（`analyze_server2.py` 逻辑，见台账方法学节）+ 真实响应抓取对照。

## 0 · 总数对照

- 顶层 `/命令` 分发分支：**189** 个（grep `action in` 计 193 行，差额 4 行系非分发行：三元表达式 2 处 `:2506/:2668` + 嵌套子检查 2 处 `:2669/:2671`）。

- 嵌套子检查：3 个（:2669 `/悟器`、:2671 `/forge`、:3908 `/摆摊`）。

- 透传 `_status_dict` 的分支：75 个；不透传：114 个（其中返回变量/调用的分支以抓取实测为准，见注）。

- `_status_dict` 顶层键：**77** 个。

- 真实响应抓取：261 个文件 + 4 条崩溃记录，分支覆盖 189/189。


## 1 · 影子别名（first-match-wins，elif 链先到先得）

| 别名 | 先生效分支 | 被遮蔽分支 | 影响 |
|---|---|---|---|
| `/omen` | :1959 `/omen`、`/天象`（天象） | :2058 `/omen`、`/奇遇`（奇遇） | `/omen` 永远走天象；目录称 `/omen` 是 `/奇遇` 别名（command_catalog.py:76）——目录与分发矛盾 |
| `/天象` | :1959（天象） | :3065 `/望气`、`/echo`、`/天象` | 仅别名项死亡，`/天象` 本体功能正常 |
| `/release` | :2375 `/放生`、`/release`（灵宠放生） | :3570 `/释放`、`/release`（释放被擒） | `/release` 永远走灵宠放生；`/释放` 本体可用，无英文别名（目录未载 `/放生`） |
| `/接令` | :3126（有守卫 `and not _is_bounty_claim`） | :3887（数字编号时生效） | 有意消歧，非遮蔽；抓取 242/243 已证两路皆通 |
| `/trade`、`/交易` | :4222（有守卫 `len(parts) >= 2`） | :4229（无参时生效） | 有意分流，非遮蔽；抓取 248/249 已证两路皆通 |
| `/help`、`/帮助`、`/指令` | :1938 | :4435（全套别名相同、无守卫） | :4435 分支不可达（死分支） |

## 2 · 189 分发分支逐分支登记

`返回键` 为静态 union（分支内全部 `return {...}` 字面键）；`变量/调用` 表示该分支返回变量或函数调用结果（键以抓取实测为准，见抓取文件）；`status` = 是否透传 `_status_dict`。

| 行号 | 分支（动作） | 返回键 union | status | 抓取 |
|---|---|---|---|---|
| 1438 | `/look`, `/地图`, `look`, `/道身` | `ok`, `text`, `status` | 是 | `002-ro-look.json` |
| 1476 | `/legacy`, `/道统`, `/前世` | —（变量/调用返回） | 否 | `005-ro-legacy.json` |
| 1503 | `/墓碑` | `ok`, `text`, `error` | 否 | `007-ro-墓碑.json` |
| 1513 | `/因果链`, `/karma_chains` | `ok`, `text` | 否 | `008-ro-因果链.json` |
| 1524 | `/定相`, `/gender` | `ok`, `text`, `status`, `error` | 是 | `213-gender-set.json` |
| 1534 | `/图鉴`, `/gallery` | `ok`, `text`, `status` | 是 | `009-ro-图鉴.json` |
| 1544 | `/命格`, `/fate` | `ok`, `text`, `fate`, `status` | 是 | `010-ro-命格.json` |
| 1570 | `/命途`, `/fate_thread` | `ok`, `text`, `fate_thread`, `status`, `error` | 是 | `011-ro-命途.json` |
| 1605 | `/回应`, `/respond_drama` | `ok`, `text`, `status`, `drama`, `drama_pending`, `error` | 是 | `214-respond-drama-no-drama.json` |
| 1642 | `/寻宝`, `/clue` | `ok`, `text`, `status` | 是 | `012-ro-寻宝.json` |
| 1661 | `/器灵`, `/spirit` | `ok`, `text`, `status`, `error` | 是 | `013-ro-器灵.json` |
| 1690 | `/温养`, `/nourish` | `ok`, `text`, `status` | 是 | `182-nourish.json` |
| 1698 | `/灵语`, `/spirit_say` | `ok`, `text`, `status` | 是 | `183-spirit-say.json` |
| 1708 | `/wallet`, `/钱包` | `ok`, `text`, `status`, `wallet` | 是 | `014-ro-wallet.json` |
| 1716 | `/wallet_withdraw`, `/钱包提取` | `ok`, `text`, `status`, `wallet`, `error` | 是 | `215-wallet-withdraw.json` |
| 1731 | `/reborn`, `/转世` | —（变量/调用返回） | 否 | `251-reborn-via-handle.json` |
| 1752 | `/here`, `/同场` | `ok`, `text`, `count`, `here` | 否 | `016-ro-here.json` |
| 1775 | `/profile`, `/人物`, `/角色` | `ok`, `text`, `profile`, `error` | 否 | `018-ro-profile.json` |
| 1787 | `/roster`, `/名录` | `ok`, `text`, `count` | 否 | `020-ro-roster.json` |
| 1797 | `/who` | `ok`, `text` | 否 | `022-ro-who.json` |
| 1799 | `/go`, `/前往` | —（变量/调用返回） | 否 | `097-go.json` |
| 1812 | `/meditate`, `/闭关`, `/打坐` | —（变量/调用返回） | 否 | `115-meditate-1h.json` |
| 1820 | `/emerge`, `/出关` | —（变量/调用返回） | 否 | `117-emerge.json` |
| 1822 | `/reclude`, `/归隐` | `ok`, `text`, `protect` | 否 | `216-reclude.json` |
| 1834 | `/unreclude`, `/出隐` | `ok`, `text` | 否 | `217-unreclude.json` |
| 1840 | `/logout`, `/下线` | —（变量/调用返回） | 否 | `211-logout.json` |
| 1842 | `/任务`, `/tasks`, `/quest` | —（变量/调用返回） | 否 | `218-tasks.json` |
| 1847 | `/goals`, `/目标` | `ok`, `text`, `goals` | 否 | `023-ro-goals.json` |
| 1853 | `/近况`, `/briefing` | `ok`, `text`, `goals`, `related`, `entry`, `error` | 否 | `025-ro-近况.json` |
| 1879 | `/ailog`, `/ai日志`, `/ai_log` | `ok`, `text`, `items` | 否 | `026-ro-ailog.json` |
| 1895 | `/ai`, `/ai自检` | `ok`, `text`, `ai_ok`, `ai_data`, `director_quality` | 否 | `027-ro-ai.json` |
| 1938 | `/帮助`, `/help`, `/指令` | `ok`, `text`, `commands` | 否 | `028-ro-帮助.json` |
| 1948 | `/qi`, `/灵气` | `ok`, `text`, `qi` | 否 | `030-ro-qi.json` |
| 1950 | `/season`, `/纪元` | `ok`, `text`, `season` | 否 | `032-ro-season.json` |
| 1959 | `/omen`, `/天象` | `ok`, `text`, `season_theme` | 否 | `244-alias-omen.json` |
| 1978 | `/rumors`, `/传闻` | `ok`, `text` | 否 | `035-ro-rumors.json` |
| 1985 | `/channel`, `/频道` | `ok`, `text` | 否 | `037-ro-channel.json` |
| 1992 | `/notice`, `/公告` | `ok`, `text` | 否 | `039-ro-notice.json` |
| 1996 | `/gm` | `ok`, `error`, `text` | 否 | `161-gm.json` |
| 2025 | `/名物`, `/mingwu` | `ok`, `text`, `error` | 否 | `219-mingwu.json` |
| 2044 | `/追查`, `/chase` | `ok`, `text`, `chased`, `new_location`, `error` | 否 | `220-chase-noargs.json` |
| 2058 | `/omen`, `/奇遇` | `ok`, `text`, `omen_open`, `omen_inline`, `omen_image`, `status`, `omen_ended`, `omen_choices`, `omen_status`, `omen_title` | 是 | `244-alias-omen.json` |
| 2127 | `/omen_say`, `/奇遇说` | `ok`, `text`, `omen_open`, `omen_inline`, `omen_choices`, `omen_ended`, `omen_status`, `omen_image`, `intent`, `status`, `error` | 是 | `222-omen-say.json` |
| 2162 | `/legend`, `/传说`, `/典籍` | `ok`, `text` | 否 | `041-ro-legend.json` |
| 2175 | `/links`, `/关系` | `ok`, `text`, `error` | 否 | `043-ro-links.json` |
| 2185 | `/apocalypse`, `/大劫` | `ok`, `text`, `season` | 否 | `162-apocalypse.json` |
| 2197 | `/map`, `/宝图`, `/看宝图` | `ok`, `text`, `status` | 是 | `045-ro-map.json` |
| 2206 | `/dig`, `/挖宝` | `ok`, `text`, `status`, `ceremony`, `equipment`, `pill`, `stone_gain`, `wrong_location`, `target_node_name`, `target_node_id`, `bagua`, `direction_text`, `omen_inline`, `omen_title`, `omen_choices` | 是 | `099-dig-wrong-location.json` |
| 2257 | `/do`, `/做`, `/act`, `/言行` | `ok`, `error`, `rejected`, `status` | 是 | `145-free-action.json` |
| 2316 | `/equip`, `/穿戴` | `ok`, `text`, `status`, `error` | 是 | `111-equip-wear.json` |
| 2324 | `/unequip`, `/卸下` | `ok`, `text`, `error` | 否 | `113-equip-remove.json` |
| 2332 | `/pets`, `/pet`, `/灵宠` | `ok`, `text`, `status` | 是 | `074-ro-灵宠.json` |
| 2338 | `/契约`, `/contract` | `ok`, `text`, `status`, `error` | 是 | `178-contract-noargs.json` |
| 2347 | `/喂养`, `/feed` | `ok`, `text`, `status`, `error` | 是 | `179-feed-noargs.json` |
| 2359 | `/出战`, `/deploy` | `ok`, `text`, `status`, `error` | 是 | `180-deploy-noargs.json` |
| 2367 | `/休息`, `/petrest` | `ok`, `text`, `status`, `error` | 是 | `181-petrest-noargs.json` |
| 2375 | `/放生`, `/release` | `ok`, `text`, `status`, `error` | 是 | `141-pet-release-noargs.json` |
| 2383 | `/cave`, `/洞府` | `ok`, `text`, `status` | 是 | `076-ro-洞府.json` |
| 2389 | `/opencave`, `/开辟` | `ok`, `text`, `status` | 是 | `223-opencave.json` |
| 2394 | `/sow`, `/播种` | `ok`, `text`, `status`, `error` | 是 | `224-sow.json` |
| 2402 | `/harvest`, `/收获` | `ok`, `text`, `status` | 是 | `225-harvest.json` |
| 2407 | `/upgradecave`, `/升级洞府` | `ok`, `text`, `status` | 是 | `226-upgradecave.json` |
| 2412 | `/quests`, `/委托` | `ok`, `text`, `status` | 是 | `079-ro-quests.json` |
| 2421 | `/acceptquest`, `/接委托` | `ok`, `text`, `status`, `error` | 是 | `134-acceptquest-noargs.json` |
| 2429 | `/deliver`, `/交付` | `ok`, `text`, `status` | 是 | `135-deliver-noargs.json` |
| 2434 | `/abandonquest`, `/弃委托` | `ok`, `text`, `status` | 是 | `136-abandonquest-noargs.json` |
| 2439 | `/promises`, `/诺言` | `ok`, `text`, `status` | 是 | `080-ro-promises.json` |
| 2448 | `/promise`, `/许诺` | `ok`, `text`, `status`, `error` | 是 | `133-promise-noargs.json` |
| 2462 | `/acceptpromise`, `/应诺` | `ok`, `text`, `status` | 是 | `227-acceptpromise-noargs.json` |
| 2468 | `/breakpromise`, `/毁诺` | `ok`, `text`, `status` | 是 | `228-breakpromise-noargs.json` |
| 2474 | `/xinfa`, `/心法` | `ok`, `text`, `status` | 是 | `075-ro-心法.json` |
| 2480 | `/主修`, `/main_art` | `ok`, `text`, `status`, `error` | 是 | `184-main-art-noargs.json` |
| 2488 | `/辅修`, `/sub_art` | `ok`, `text`, `status`, `error` | 是 | `185-sub-art-noargs.json` |
| 2496 | `/卸功`, `/remove_art` | `ok`, `text`, `status`, `error` | 是 | `186-remove-art-noargs.json` |
| 2504 | `/body`, `/炼体`, `/soul`, `/炼神` | `ok`, `text`, `status`, `error` | 是 | `187-body.json` |
| 2527 | `/demon`, `/镇魔` | `ok`, `text`, `status`, `error` | 是 | `188-demon.json` |
| 2545 | `/write_book`, `/著书` | `ok`, `text`, `status`, `error` | 是 | `154-write-book.json` |
| 2556 | `/read_book`, `/研读` | `ok`, `text`, `status` | 是 | `155-read-book-noargs.json` |
| 2563 | `/rank`, `/榜单`, `/榜` | `ok`, `text`, `board` | 否 | `047-ro-rank.json` |
| 2575 | `/ascend`, `/飞升榜` | `ok`, `text` | 否 | `049-ro-ascend.json` |
| 2579 | `/sect`, `/宗门` | `ok`, `text` | 否 | `051-ro-sect.json` |
| 2581 | `/join_sect`, `/拜入` | `ok`, `text`, `status`, `error` | 是 | `129-join-sect-noargs.json` |
| 2589 | `/leave_sect`, `/叛门` | `ok`, `text`, `status` | 是 | `229-leave-sect.json` |
| 2594 | `/salary`, `/领俸禄`, `/俸禄` | `ok`, `text`, `status` | 是 | `130-salary.json` |
| 2599 | `/promote`, `/晋升` | `ok`, `text`, `status` | 是 | `131-promote.json` |
| 2604 | `/teach`, `/传功` | `ok`, `text`, `status`, `error` | 是 | `132-teach-noargs.json` |
| 2615 | `/adventure`, `/探险` | `ok`, `text`, `error`, `status` | 是 | `151-adventure.json` |
| 2648 | `/配方`, `/recipes` | `ok`, `text` | 否 | `069-ro-配方.json` |
| 2652 | `/炼丹`, `/炼器` | `ok`, `text`, `crafted`, `output`, `error` | 否 | `147-alchemy-noargs.json` |
| 2667 | `/悟丹`, `/悟器`, `/forge`, `/天工` | `ok`, `text`, `recipe`, `error` | 否 | `CRASH:wu-dan` |
| 2733 | `/gen_pill`, `/生成丹药` | —（变量/调用返回） | 否 | `CRASH:gen-pill` |
| 2736 | `/gen_equip`, `/生成法宝` | —（变量/调用返回） | 否 | `CRASH:gen-equip` |
| 2738 | `/gen_monster`, `/生成妖兽` | `ok`, `error` | 否 | `230-gen-monster.json` |
| 2740 | `/secret`, `/秘境` | `ok`, `text`, `scene_image` | 否 | `066-ro-secret.json` |
| 2777 | `/dungeon`, `/禁地`, `/锁妖塔`, `/古窟` | `ok`, `text`, `status`, `scene_image` | 是 | `153-dungeon.json` |
| 2812 | `/cast`, `/施法`, `/神通` | `ok`, `text`, `status` | 是 | `149-cast-noargs.json` |
| 2819 | `/cast_treasure`, `/祭法宝`, `/法宝大招` | `ok`, `text`, `status` | 是 | `150-cast-treasure-noargs.json` |
| 2825 | `/dungeon_attack`, `/出招`, `/斩击` | `ok`, `text`, `status` | 是 | `191-dungeon-attack-noargs.json` |
| 2831 | `/pick_boon`, `/择道韵`, `/领悟道韵` | `ok`, `text`, `status` | 是 | `190-pick-boon-noargs.json` |
| 2837 | `/break`, `/突破` | —（变量/调用返回） | 否 | `118-breakthrough.json` |
| 2848 | `/fight`, `/斗法` | `ok`, `error` | 否 | `146-fight-noargs.json` |
| 2852 | `/event`, `/机缘` | —（变量/调用返回） | 否 | `088-ro-event.json` |
| 2854 | `/revenge`, `/回访`, `/因果` | `ok`, `text`, `event_id` | 否 | `189-revenge.json` |
| 2862 | `/tick`, `/npc` | `ok`, `text`, `count` | 否 | `090-ro-tick.json` |
| 2867 | `/天道`, `/heaven`, `/导演` | —（变量/调用返回） | 否 | `163-heaven.json` |
| 2876 | `/世界弧`, `/arc`, `/弧` | —（变量/调用返回） | 否 | `091-ro-世界弧.json` |
| 2880 | `/世界弧应劫`, `/弧应劫`, `/应劫` | `ok`, `error` | 否 | `231-arc-respond.json` |
| 2889 | `/世情`, `/worldinfo`, `/世界演变`, `/演变` | `ok`, `text`, `actions`, `evolution` | 否 | `092-ro-世情.json` |
| 2932 | `/追`, `/follow` | `ok`, `text`, `error` | 否 | `164-follow-noargs.json` |
| 2941 | `/拜师` | `ok`, `text`, `error` | 否 | `165-apprentice-noargs.json` |
| 2948 | `/确认拜师` | `ok`, `text` | 否 | `232-confirm-apprentice-noargs.json` |
| 2955 | `/收徒` | `ok`, `text`, `error` | 否 | `233-take-apprentice-noargs.json` |
| 2962 | `/出师` | `ok`, `text` | 否 | `234-graduate-noargs.json` |
| 2967 | `/结拜` | `ok`, `text`, `error` | 否 | `166-sworn-noargs.json` |
| 2974 | `/结拜同意` | `ok`, `text` | 否 | `235-sworn-accept-noargs.json` |
| 2979 | `/绝交` | `ok`, `text`, `error` | 否 | `167-sever-noargs.json` |
| 2988 | `/叛师` | `ok`, `text`, `error` | 否 | `168-betray-noargs.json` |
| 2995 | `/师门任务` | `ok`, `text` | 否 | `236-sect-quests.json` |
| 3000 | `/交师门` | `ok`, `text` | 否 | `237-sect-quest-done-noargs.json` |
| 3005 | `/结义任务` | `ok`, `text` | 否 | `238-sworn-quests.json` |
| 3010 | `/交结义` | `ok`, `text` | 否 | `239-sworn-quest-done-noargs.json` |
| 3017 | `/贡献` | `ok`, `text` | 否 | `072-ro-贡献.json` |
| 3025 | `/上交`, `/donate` | `ok`, `text`, `status`, `error` | 是 | `169-donate-noargs.json` |
| 3037 | `/兑换` | `ok`, `text`, `status` | 是 | `073-ro-兑换.json` |
| 3044 | `/宗门环`, `/sectring` | `ok`, `text` | 否 | `071-ro-宗门环.json` |
| 3048 | `/接宗门环`, `/accepring` | `ok`, `text`, `status`, `error` | 是 | `170-acceptring-noargs.json` |
| 3057 | `/宗门势`, `/sectpower` | `ok`, `text` | 否 | `070-ro-宗门势.json` |
| 3061 | `/势力`, `/faction` | —（变量/调用返回） | 否 | `093-ro-势力.json` |
| 3065 | `/望气`, `/echo`, `/天象` | —（变量/调用返回） | 否 | `034-ro-天象.json` |
| 3074 | `/纪元回流`, `/era`, `/史笔回流` | —（变量/调用返回） | 否 | `094-ro-纪元回流.json` |
| 3078 | `/宗门令`, `/sectorder`, `/势力令` | —（变量/调用返回） | 否 | `081-ro-宗门令.json` |
| 3082 | `/接宗门令`, `/acceptorder` | `ok`, `error` | 否 | `171-acceptorder-noargs.json` |
| 3088 | `/交宗门令`, `/doneorder` | `ok`, `error` | 否 | `172-doneorder-noargs.json` |
| 3094 | `/议政`, `/council` | `ok`, `text` | 否 | `082-ro-议政.json` |
| 3098 | `/投票`, `/vote` | `ok`, `text`, `error` | 否 | `137-vote-noargs.json` |
| 3107 | `/游说`, `/lobby` | `ok`, `text`, `error` | 否 | `138-lobby-noargs.json` |
| 3118 | `/除凶`, `/hunt` | `ok`, `text` | 否 | `083-ro-除凶.json` |
| 3126 | `/接除凶`, `/接令` | `ok`, `text`, `error` | 否 | `240-accept-hunt-noargs.json` |
| 3140 | `/弃除凶`, `/弃令` | `ok`, `text` | 否 | `241-abandon-hunt-noargs.json` |
| 3145 | `/追凶`, `/track` | `ok`, `text` | 否 | `084-ro-追凶.json` |
| 3150 | `/反悬赏` | `ok`, `text` | 否 | `085-ro-反悬赏.json` |
| 3157 | `/围剿` | `ok`, `text`, `error` | 否 | `086-ro-围剿.json` |
| 3164 | `/talk`, `/交谈` | `ok`, `text`, `chat_open`, `npc`, `avatar`, `is_player`, `messages`, `old_account`, `error`, `attitude`, `source`, `bystanders` | 否 | `142-talk-npc.json` |
| 3328 | `/说`, `/say` | `ok`, `error`, `chat_ended`, `text`, `chat_open`, `npc`, `avatar`, `is_player`, `source`, `action`, `rejected` | 否 | `143-say-no-session.json` |
| 3555 | `/挂断`, `/hangup` | `ok`, `text`, `chat_ended`, `npc`, `error` | 否 | `139-hangup.json` |
| 3570 | `/释放`, `/release` | `ok`, `text`, `error` | 否 | `140-release-captive.json` |
| 3578 | `/chatpanel`, `/会话` | `ok`, `text` | 否 | `095-ro-chatpanel.json` |
| 3582 | `/agenda`, `/议程` | `ok`, `text`, `agendas` | 否 | `053-ro-agenda.json` |
| 3603 | `/bounty`, `/告示` | `ok`, `text` | 否 | `055-ro-bounty.json` |
| 3605 | `/market`, `/坊市` | `ok`, `text` | 否 | `057-ro-market.json` |
| 3607 | `/行情` | `ok`, `text` | 否 | `059-ro-行情.json` |
| 3609 | `/atlas`, `/版图` | `ok`, `text` | 否 | `060-ro-atlas.json` |
| 3612 | `/buy`, `/购买` | `ok`, `text`, `error` | 否 | `119-buy-noargs.json` |
| 3641 | `/sell`, `/出售` | `ok`, `text`, `error` | 否 | `120-sell-noargs.json` |
| 3654 | `/use`, `/服用` | `ok`, `text`, `status`, `error` | 是 | `114-pill-use-missing.json` |
| 3670 | `/deposit`, `/寄存` | `ok`, `text`, `status`, `error` | 是 | `176-deposit-noargs.json` |
| 3676 | `/withdraw`, `/支取` | `ok`, `text`, `status`, `error` | 是 | `177-withdraw-noargs.json` |
| 3683 | `/灵泉`, `/spring`, `/汲取` | `ok`, `text`, `status` | 是 | `159-spring.json` |
| 3702 | `/草园`, `/herbs`, `/采药`, `/灵草` | `ok`, `text`, `status`, `error` | 是 | `157-herbs.json` |
| 3727 | `/灵鹤`, `/crane`, `/探路` | `ok`, `text`, `status`, `overflow`, `error` | 是 | `160-crane.json` |
| 3836 | `/scan`, `/探查` | `ok`, `text`, `scan` | 否 | `158-scan.json` |
| 3846 | `/place_bounty`, `/挂赏` | `ok`, `text`, `error` | 否 | `123-place-bounty-noargs.json` |
| 3887 | `/claim_bounty`, `/接令` | `ok`, `text`, `error` | 否 | `242-claim-bounty-numeric.json` |
| 3905 | `/list_item`, `/寄售`, `/摆摊` | `ok`, `text`, `status`, `error` | 是 | `126-list-item.json` |
| 3949 | `/buy_listing`, `/买寄售` | `ok`, `text`, `status`, `error` | 是 | `127-buy-listing-noargs.json` |
| 3988 | `/cancel_listing`, `/撤单`, `/撤回` | `ok`, `text`, `status`, `error` | 是 | `128-cancel-listing-noargs.json` |
| 4015 | `/pawn`, `/典当` | `ok`, `text`, `error` | 否 | `124-pawn.json` |
| 4032 | `/redeem`, `/赎回` | `ok`, `text`, `status`, `error` | 是 | `125-redeem.json` |
| 4046 | `/收益`, `/提取收益` | `ok`, `text`, `status`, `error` | 是 | `175-earnings.json` |
| 4059 | `/捡漏`, `/盲匣`, `/解石` | `ok`, `text`, `status`, `loot`, `ceremony`, `error` | 是 | `105-blind-box-1.json` |
| 4139 | `/招徕`, `/招徕修士` | `ok`, `error`, `text`, `status`, `trade`, `haggle`, `npc`, `listing_id`, `item_name`, `original_price`, `offer_price` | 是 | `174-recruit.json` |
| 4186 | `/还价`, `/议价` | `ok`, `error`, `text`, `status` | 是 | `173-haggle-noargs.json` |
| 4222 | `/trade`, `/交易` | `ok`, `text`, `error` | 否 | `248-trade-bare.json` |
| 4229 | `/trade`, `/交易` | `ok`, `text` | 否 | `248-trade-bare.json` |
| 4234 | `/trade_offer`, `/交易出` | `ok`, `text`, `error` | 否 | `203-trade-offer.json` |
| 4247 | `/trade_accept`, `/交易同意` | `ok`, `text`, `status` | 是 | `204-trade-accept-second.json` |
| 4260 | `/trade_reject`, `/交易拒绝` | `ok`, `text`, `status` | 是 | `205-trade-reject-second.json` |
| 4274 | `/npc_goods`, `/npc货单` | `ok`, `text`, `error` | 否 | `198-npc-goods-noargs.json` |
| 4281 | `/npc_buy`, `/npc买` | `ok`, `text`, `error` | 否 | `196-npc-buy-noargs.json` |
| 4297 | `/npc_sell`, `/npc卖` | `ok`, `text`, `error` | 否 | `197-npc-sell-noargs.json` |
| 4315 | `/auction`, `/拍卖行`, `/拍卖` | `ok`, `text` | 否 | `122-auction-board.json` |
| 4320 | `/auction_list`, `/上拍` | `ok`, `text`, `error` | 否 | `121-auction-list.json` |
| 4340 | `/bid`, `/拍`, `/出价` | `ok`, `text`, `error` | 否 | `192-bid.json` |
| 4370 | `/buyout`, `/一口` | `ok`, `text`, `error` | 否 | `193-buyout-noargs.json` |
| 4379 | `/auction_cancel`, `/撤拍` | `ok`, `text`, `error` | 否 | `194-auction-cancel-noargs.json` |
| 4389 | `/create_art`, `/自创功法` | `ok`, `text`, `art`, `error` | 否 | `156-create-art.json` |
| 4421 | `/arts`, `/功法` | `ok`, `text`, `arts` | 否 | `064-ro-arts.json` |
| 4429 | `/history`, `/大事记` | `ok`, `text` | 否 | `062-ro-history.json` |
| 4435 | `/help`, `/帮助`, `/指令` | `ok`, `text` | 否 | `029-ro-help.json` |

## 3 · `_status_dict`（server/world.py:4551–5060）顶层键

| 键 | 值来源（静态） |
|---|---|
| `name` | `c.name` |
| `version` | `getattr(c, 'version', 1)` |
| `realm` | `c.realm.name` |
| `origin` | `_origin_block` |
| `fate` | `_fate_block` |
| `location_image` | `_location_image` |
| `relations_recent` | `_rel_recent` |
| `relations_marks` | `_rel_marks` |
| `location` | `c.location` |
| `stones` | `c.spirit_stones` |
| `vault` | `c.vault_stones` |
| `wallet` | `_wallet_block` |
| `past_life` | `_past_life` |
| `karma_chains` | `_karma_chains` |
| `gender` | `_gender_val` |
| `portrait` | `_portrait_val` |
| `gallery` | `_gallery_block` |
| `art_images` | `_art_images` |
| `sin` | `c.karma.sin_value` |
| `merit` | `c.karma.merit_value` |
| `exp` | `f'{c.realm.current_exp}/{c.realm.max_exp}'` |
| `rem_years` | `round(c.lifespan.get_remaining_years(), 2)` |
| `dead` | `c.status == CharacterStatus.DEAD or c.lifespan.is_dead()` |
| `status` | `c.status.value if isinstance(c.status, CharacterStatus) else str(c.status)` |
| `status_cn` | `status_cn(c.status)` |
| `root` | `c.spiritual_root.display_name()` |
| `root_eff` | `round(c.spiritual_root.efficiency, 2)` |
| `dao_heart` | `c.karma.dao_heart` |
| `skills` | `list(c.skills[:8])` |
| `inventory` | `list(c.inventory)` |
| `arrays` | `list(c.arrays)` |
| `pet` | `{'name': _ap.name, 'species': _ap.species, 'level': pet_level_for(_ap.growth), 'intimacy': _ap.intimacy, 'img'` |
| `pets_count` | `len([p for p in c.pets or [] if p.state != 'dead'])` |
| `cave` | `FarmEngine.cave_summary(c)` |
| `arts` | `{'main': getattr(c, 'main_art', '') or '', 'sub': list(getattr(c, 'sub_arts', None) or [])}` |
| `body_soul` | `{'body': BodySoulEngine.body_level(c), 'soul': BodySoulEngine.soul_level(c)}` |
| `heart_demon_state` | `DemonStateEngine.summary(c)` |
| `books` | `{'inspiration': int(getattr(c, 'inspiration', 0) or 0), 'prestige': int(getattr(c, 'prestige', 0) or 0)}` |
| `season_theme` | `self._season_theme_summary()` |
| `blood_marked` | `c.karma.is_blood_marked()` |
| `lifespan_warning` | `c.lifespan.get_remaining_years() <= LIFESPAN_WARNING_YEARS` |
| `meditating` | `c.status == CharacterStatus.MEDITATING` |
| `is_meditating` | `c.status == CharacterStatus.MEDITATING` |
| `sect` | `sect_name` |
| `rank` | `sect_rank` |
| `sect_contribution` | `getattr(c, 'sect_contribution', 0)` |
| `sect_streak` | `streak` |
| `salary` | `salary` |
| `salary_claimable` | `salary_claimable` |
| `salary_cd_sec` | `salary_cd_sec` |
| `can_promote` | `can_promote` |
| `next_rank` | `next_rank` |
| `promote_req_tier` | `promote_req_tier` |
| `sect_ring` | `ring_info` |
| `sects_catalog` | `sects_catalog` |
| `unread_messages` | `unread_msgs` |
| `newbie_protected` | `prot` |
| `newbie_left_hours` | `round(prot_left / 3600.0, 1) if prot else 0` |
| `protect` | `ProtectionEngine.status_text(c)` |
| `conflict_zone` | `is_conflict_zone(c.location)` |
| `qi_mult` | `round(qi_mod.global_qi_multiplier(), 3)` |
| `crane_pending_item` | `getattr(c, 'crane_pending_item', None)` |
| `max_bag_slots` | `getattr(c, 'MAX_BAG_SLOTS', 64)` |
| `is_bag_full` | `c.is_bag_full() if hasattr(c, 'is_bag_full') else len(getattr(c, 'items', [])) >= 64` |
| `equipped` | `equipped_list` |
| `items` | `[{'uid': getattr(it, 'uid', getattr(it, 'id', f'it_{idx}')), 'img': _item_imgs.get(getattr(it, 'uid', getattr(` |
| `stall_earnings` | `getattr(c, 'stall_earnings', 0)` |
| `stall_items` | `[{'id': l.id, 'name': l.item_name, 'price': l.price, 'kind': l.kind, 'created_at': l.created_at, 'seller_name'` |
| `market_listings` | `[{'id': l.id, 'name': l.item_name, 'price': l.price, 'tax': max(1, int(l.price * 0.05)), 'kind': l.kind, 'sell` |
| `dungeon` | `DungeonEngine.get_session(c.id)` |
| `spells_catalog` | `_spells_catalog` |
| `dungeon_floors` | `[{'floor': f_k, 'name': f_v['name'], 'tier_name': f_v['tier_name'], 'min_tier': f_v['min_tier']} for f_k, f_v ` |
| `combat` | `c.combat.model_dump() if hasattr(c, 'combat') and hasattr(c.combat, 'model_dump') else {}` |
| `soul` | `c.soul.model_dump() if hasattr(c, 'soul') and hasattr(c.soul, 'model_dump') else {}` |
| `equip_slots` | `c.equip_slots.model_dump() if hasattr(c, 'equip_slots') and hasattr(c.equip_slots, 'model_dump') else {}` |
| `professions` | `c.professions.model_dump() if hasattr(c, 'professions') and hasattr(c.professions, 'model_dump') else {}` |
| `quest` | `{'publisher': c.active_quest.publisher_name, 'ring': f'{min(c.active_quest.ring_index + 1, len(c.active_quest.` |

### 3.1 条件键（仅在某条件下出现的键）

`_status_dict` 的 77 个顶层键**近乎无条件全量下发**：键集合不随分支变化，条件只体现在**值可空**（键在、无值时为 `null`/`[]`/`{}`），而非键缺失。实测快照（`status-snapshot.json`，新角）中值为 `null` 的键：`pet`（无灵宠时）、`cave`（未开辟洞府时）、`next_rank`（无宗门时）、`crane_pending_item`（无待取仙物时）、`dungeon`（无禁地会话时）、`quest`（无进行中委托时）。前端凡读这 6 键皆须判空——桌面/移动均已判空（见台账一致行）。

唯一以 `if` 分支控制**子键集合**的是 `sect_ring`（:4665）：仅 `sect_name` 在场时才含 `day/accepted/done/themes` 子键；无宗门时 `sect_ring` 为 `{}`。其余嵌套块（`arts/fate/gallery/origin/equipped[].stats` 等）键集合固定。

## 4 · 非 `/命令` 出口

| 出口 | 行号 | 返回键 |
|---|---|---|
| `join`（`_join_locked` 拼装 `**snap` + 只增键） | :587 | `**snap`（token/user_id/username/character_id/name/realm/location/rem_years/legacy_points/lives/is_new_life/resumed + 见抓取 `001-join.json`）+ `newbie_feed`、`first_night`、`entry`、`origin_card` |
| 死者 payload（join 死者分支） | :919–931 | 见抓取 `join-dead.json`：`ok/dead/ceremony/token/user_id/username/character_id/name/realm/location/rem_years/legacy_points/lives/is_new_life/resumed/death_cause/legacy/wallet/settlement/consignment_open_count/lock_fallback/session_issued/settlement_pending/settled` |
| `reincarnate` | :1004 起，返回 :1112 | `ok/text/karma_shadow/settle/boosts_applied/legacy_points/wallet/sweep/name/realm/location/rem_years/origin_card/ceremony`（抓取 `reincarnate.json`） |
| `legacy_info`（`/道统` 本体） | :976–983 | `ok/error` 或 `ok/points/lives/earned/past_lives/traces/karma_shadow/boosts/max_boosts/alive/death_cause`（`/道统` 分发再补 `text`） |
| `build_entry`（core/briefing.py:57） | :478 附近 | `entry`：`version/since/generated_at/lines{fate,chains,relations}/queue[{kind,priority,title,text,ref_id,target,ts,options?}]/highlight/rest_count/empty/empty_text/proactive{text,npc}` |
| `_breakthrough` | :5324–5417 | `ok/error` 或 `ok/pending_heart_demon/text/heart_demon_options` 或 `ok/text/success/fatal/death/status/legacy/sweep/death_cause/ceremony/ceremony_next` |
| `_meditate` / `_emerge` | :5254–5302 | `ok/text/status`（`_emerge` 经 `_append_natural_omen` 追加奇遇键） |
| `logout` | :4483–4507 | `ok/text` 或 `ok/text/logout_kind/lost_stones` |
| 心魔前置路径（handle 内，分发前） | :1208–1297 | `ok/text/heart_demon/death/status/legacy/sweep/death_cause`（+ `ceremony/ceremony_next/tribulation{success,fatal,new_realm}` 当突破继发时） |
| 生死/被擒/闭关门禁（handle 内，分发前） | :1371–1435 | `ok/error/status`（+ `dead: true` / `meditating: true`） |

## 5 · `core/` 直接构造响应 dict 的返回点（代表）

| 位置 | 返回键 |
|---|---|---|
| `TreasureEngine.dig`（core/treasure_system.py:379） | `success/message` + 按 outcome：`need_choice/archetype`；`outcome/equipment/pill/stone_gain`（巧破/战利/遗物）；`outcome/equipment`（brute_force，**无 `stone_gain`**——见台账 CA-002）；`outcome/message`（combat_defeat，无 equipment/stone_gain）；`wrong_location/target_node_name/target_node_id/bagua/direction_text`（错位） |
| `/捡漏` 内联构造（server/world.py:4059） | `ok/text/status/loot/ceremony`（ceremony 仅 tier4 relic 达幕）；成本 80 灵石只写文本，无字段 |
| `attempt_breakthrough`（core/breakthrough.py，经 `_breakthrough`） | `message/success/is_fatal/is_major/new_realm` 等（经 `_breakthrough` 转 `{ok,text,success,fatal,death,status,legacy,sweep,death_cause,ceremony,ceremony_next}`） |
| `FreeAction`（core/free_action.py:195） | `ok/intent/outcome/narrative/effects_summary/spawned/source/event_id/text`（**无 `target_died`**；`target_died` 只由斗法路径下发） |
| `HeartDemonEngine.resolve`（core/heart_demon.py:56） | `success/message/is_fatal`（失败路）或 `success/outcome/narrative/effects_summary/tribulation_mod/is_fatal/source/demon` |
| `handle_task_command`（core/tasks.py:456） | `ok/text` 或 `{defs,tasks,text}`（board，见抓取 `tasks.json`） |