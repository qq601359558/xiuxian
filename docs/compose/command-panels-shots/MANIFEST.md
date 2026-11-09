# 命令回复面板化 §8 截图清单（生成器产物，返工 2026-11-09）

口径：面板 HTML 由真实面板块渲染，数据为合同审计真实抓取 + Spec 附录 A 合成 payload；
样式为真实 workbench.css / mobile.css 内联。沙盒无法加载 Tailwind CDN，工具类由页内
垫片实现面板实际用到的 4 个文字色类 + 2 个字号，布局比生产环境疏松——内容/数值/
颜色以真实 CSS 为准。PNG 由 node tests/shoot_command_panels.mjs 全页实拍（CDP）。

共 186 页（HTML + PNG 各一）。

| 源页 | 任务 | 命令 | 端 | 主题 |
|---|---|---|---|---|
| sc-p0-desktop-light.html | CP-01/02 | /profile + /look | desktop | light |
| sc-p0-desktop-dark.html | CP-01/02 | /profile + /look | desktop | dark |
| sc-p0-mobile-light.html | CP-01/02 | /profile + /look | mobile | light |
| sc-p0-mobile-dark.html | CP-01/02 | /profile + /look | mobile | dark |
| sc-waves-desktop-light.html | P1/P2/P3/附录代表 | 8 项合页 | desktop | light |
| sc-waves-desktop-dark.html | P1/P2/P3/附录代表 | 8 项合页 | desktop | dark |
| sc-waves-mobile-light.html | P1/P2/P3/附录代表 | 8 项合页 | mobile | light |
| sc-cp01-profile-desktop-light.html | CP-01 | /profile | desktop | light |
| sc-cp01-profile-mobile-light.html | CP-01 | /profile | mobile | light |
| sc-cp02-look-desktop-light.html | CP-02 | /look | desktop | light |
| sc-cp02-look-mobile-light.html | CP-02 | /look | mobile | light |
| sc-cp03-here-desktop-light.html | CP-03 | /here | desktop | light |
| sc-cp03-here-mobile-light.html | CP-03 | /here | mobile | light |
| sc-cp04-nearby-desktop-light.html | CP-04 | /近况 | desktop | light |
| sc-cp04-nearby-mobile-light.html | CP-04 | /近况 | mobile | light |
| sc-cp05-goals-desktop-light.html | CP-05 | /目标 | desktop | light |
| sc-cp05-goals-mobile-light.html | CP-05 | /目标 | mobile | light |
| sc-cp06-tasks-desktop-light.html | CP-06 | /任务 | desktop | light |
| sc-cp06-tasks-mobile-light.html | CP-06 | /任务 | mobile | light |
| sc-cp07-rank-desktop-light.html | CP-07 | /榜 | desktop | light |
| sc-cp07-rank-mobile-light.html | CP-07 | /榜 | mobile | light |
| sc-cp08-secret-desktop-light.html | CP-08 | /秘境 | desktop | light |
| sc-cp08-secret-mobile-light.html | CP-08 | /秘境 | mobile | light |
| sc-cp09-world-desktop-light.html | CP-09 | /世情 | desktop | light |
| sc-cp09-world-mobile-light.html | CP-09 | /世情 | mobile | light |
| sc-cp10-clue-desktop-light.html | CP-10 | /寻宝 | desktop | light |
| sc-cp10-clue-mobile-light.html | CP-10 | /寻宝 | mobile | light |
| sc-cp11-spirit-desktop-light.html | CP-11 | /器灵 | desktop | light |
| sc-cp11-spirit-mobile-light.html | CP-11 | /器灵 | mobile | light |
| sc-cp12-arts-desktop-light.html | CP-12 | /功法 | desktop | light |
| sc-cp12-arts-mobile-light.html | CP-12 | /功法 | mobile | light |
| sc-cp13-gallery-desktop-light.html | CP-13 | /图鉴 | desktop | light |
| sc-cp13-gallery-mobile-light.html | CP-13 | /图鉴 | mobile | light |
| sc-cp14-market-desktop-light.html | CP-14 | /坊市 | desktop | light |
| sc-cp14-market-mobile-light.html | CP-14 | /坊市 | mobile | light |
| sc-cp15-auction-desktop-light.html | CP-15 | /拍卖行 | desktop | light |
| sc-cp15-auction-mobile-light.html | CP-15 | /拍卖行 | mobile | light |
| sc-cp16-hunt-desktop-light.html | CP-16 | /除凶 | desktop | light |
| sc-cp16-hunt-mobile-light.html | CP-16 | /除凶 | mobile | light |
| sc-cp17-sect-desktop-light.html | CP-17 | /宗门 | desktop | light |
| sc-cp17-sect-mobile-light.html | CP-17 | /宗门 | mobile | light |
| sc-cp18-fatethread-desktop-light.html | CP-18 | /命途 | desktop | light |
| sc-cp18-fatethread-mobile-light.html | CP-18 | /命途 | mobile | light |
| sc-cp19-map-desktop-light.html | CP-19 | /宝图 | desktop | light |
| sc-cp19-map-mobile-light.html | CP-19 | /宝图 | mobile | light |
| sc-cp20-help-desktop-light.html | CP-20 | /帮助 | desktop | light |
| sc-cp20-help-mobile-light.html | CP-20 | /帮助 | mobile | light |
| sc-cp21-who-desktop-light.html | CP-21 | /who | desktop | light |
| sc-cp21-who-mobile-light.html | CP-21 | /who | mobile | light |
| sc-cp22-agenda-desktop-light.html | CP-22 | /议程 | desktop | light |
| sc-cp22-agenda-mobile-light.html | CP-22 | /议程 | mobile | light |
| sc-cp23-bounty-desktop-light.html | CP-23 | /告示 | desktop | light |
| sc-cp23-bounty-mobile-light.html | CP-23 | /告示 | mobile | light |
| sc-cp24-heaven-desktop-light.html | CP-24 | /天道 | desktop | light |
| sc-cp24-heaven-mobile-light.html | CP-24 | /天道 | mobile | light |
| sc-cp25-arcs-desktop-light.html | CP-25 | /世界弧 | desktop | light |
| sc-cp25-arcs-mobile-light.html | CP-25 | /世界弧 | mobile | light |
| sc-cp26-createart-desktop-light.html | CP-26 | /自创功法 | desktop | light |
| sc-cp26-createart-mobile-light.html | CP-26 | /自创功法 | mobile | light |
| sc-cp27-fate-desktop-light.html | CP-27 | /命格 | desktop | light |
| sc-cp27-fate-mobile-light.html | CP-27 | /命格 | mobile | light |
| sc-cp28-respond-desktop-light.html | CP-28 | /回应 | desktop | light |
| sc-cp28-respond-mobile-light.html | CP-28 | /回应 | mobile | light |
| sc-cp29a-links-desktop-light.html | CP-29 | /因果 | desktop | light |
| sc-cp29a-links-mobile-light.html | CP-29 | /因果 | mobile | light |
| sc-cp29b-relation-desktop-light.html | CP-29 | /关系 | desktop | light |
| sc-cp29b-relation-mobile-light.html | CP-29 | /关系 | mobile | light |
| sc-cp30-faction-desktop-light.html | CP-30 | /势力 | desktop | light |
| sc-cp30-faction-mobile-light.html | CP-30 | /势力 | mobile | light |
| sc-cp31-sectorder-desktop-light.html | CP-31 | /宗门令 | desktop | light |
| sc-cp31-sectorder-mobile-light.html | CP-31 | /宗门令 | mobile | light |
| sc-cp32-sectpower-desktop-light.html | CP-32 | /宗门势 | desktop | light |
| sc-cp32-sectpower-mobile-light.html | CP-32 | /宗门势 | mobile | light |
| sc-cp33a-contribution-desktop-light.html | CP-33 | /贡献 | desktop | light |
| sc-cp33a-contribution-mobile-light.html | CP-33 | /贡献 | mobile | light |
| sc-cp33b-redeem-desktop-light.html | CP-33 | /兑换 | desktop | light |
| sc-cp33b-redeem-mobile-light.html | CP-33 | /兑换 | mobile | light |
| sc-cp34-scan-desktop-light.html | CP-34 | /探查 | desktop | light |
| sc-cp34-scan-mobile-light.html | CP-34 | /探查 | mobile | light |
| sc-cp35-npcgoods-desktop-light.html | CP-35 | /npc货单 金满堂 | desktop | light |
| sc-cp35-npcgoods-mobile-light.html | CP-35 | /npc货单 金满堂 | mobile | light |
| sc-cp36-channel-desktop-light.html | CP-36 | /频道 | desktop | light |
| sc-cp36-channel-mobile-light.html | CP-36 | /频道 | mobile | light |
| sc-cp37-legend-desktop-light.html | CP-37 | /传说 | desktop | light |
| sc-cp37-legend-mobile-light.html | CP-37 | /传说 | mobile | light |
| sc-cp38-era-desktop-light.html | CP-38 | /纪元回流 | desktop | light |
| sc-cp38-era-mobile-light.html | CP-38 | /纪元回流 | mobile | light |
| sc-cp39-trade-desktop-light.html | CP-39 | /交易 | desktop | light |
| sc-cp39-trade-mobile-light.html | CP-39 | /交易 | mobile | light |
| sc-cp40-sectquests-desktop-light.html | CP-40 | /师门任务 | desktop | light |
| sc-cp40-sectquests-mobile-light.html | CP-40 | /师门任务 | mobile | light |
| sc-cp41-mingwu-desktop-light.html | CP-41 | /名物 | desktop | light |
| sc-cp41-mingwu-mobile-light.html | CP-41 | /名物 | mobile | light |
| sc-cp42-sectring-desktop-light.html | CP-42 | /宗门环 | desktop | light |
| sc-cp42-sectring-mobile-light.html | CP-42 | /宗门环 | mobile | light |
| sc-cp43-apocalypse-desktop-light.html | CP-43 | /大劫 | desktop | light |
| sc-cp43-apocalypse-mobile-light.html | CP-43 | /大劫 | mobile | light |
| sc-cp44-ai-desktop-light.html | CP-44 | /ai | desktop | light |
| sc-cp44-ai-mobile-light.html | CP-44 | /ai | mobile | light |
| sc-cp45-ailog-desktop-light.html | CP-45 | /AI日志 | desktop | light |
| sc-cp45-ailog-mobile-light.html | CP-45 | /AI日志 | mobile | light |
| sc-cp49-pet-desktop-light.html | CP-49 | /灵宠 | desktop | light |
| sc-cp49-pet-mobile-light.html | CP-49 | /灵宠 | mobile | light |
| sc-cp50-cave-desktop-light.html | CP-50 | /洞府 | desktop | light |
| sc-cp50-cave-mobile-light.html | CP-50 | /洞府 | mobile | light |
| sc-cp51-mindart-desktop-light.html | CP-51 | /心法 | desktop | light |
| sc-cp51-mindart-mobile-light.html | CP-51 | /心法 | mobile | light |
| sc-cp52-wallet-desktop-light.html | CP-52 | /钱包 | desktop | light |
| sc-cp52-wallet-mobile-light.html | CP-52 | /钱包 | mobile | light |
| sc-cp53-prices-desktop-light.html | CP-53 | /行情 | desktop | light |
| sc-cp53-prices-mobile-light.html | CP-53 | /行情 | mobile | light |
| sc-cp54-atlas-desktop-light.html | CP-54 | /版图 | desktop | light |
| sc-cp54-atlas-mobile-light.html | CP-54 | /版图 | mobile | light |
| sc-cp55-tombstone-desktop-light.html | CP-55 | /墓碑 审计员 | desktop | light |
| sc-cp55-tombstone-mobile-light.html | CP-55 | /墓碑 审计员 | mobile | light |
| sc-cp56-chains-desktop-light.html | CP-56 | /因果链 | desktop | light |
| sc-cp56-chains-mobile-light.html | CP-56 | /因果链 | mobile | light |
| sc-cp57-quests-desktop-light.html | CP-57 | /委托 | desktop | light |
| sc-cp57-quests-mobile-light.html | CP-57 | /委托 | mobile | light |
| sc-cp58-promises-desktop-light.html | CP-58 | /诺言 | desktop | light |
| sc-cp58-promises-mobile-light.html | CP-58 | /诺言 | mobile | light |
| sc-cp59-recipes-desktop-light.html | CP-59 | /配方 | desktop | light |
| sc-cp59-recipes-mobile-light.html | CP-59 | /配方 | mobile | light |
| sc-cp60a-bodysoul-desktop-light.html | CP-60 | /炼体 | desktop | light |
| sc-cp60a-bodysoul-mobile-light.html | CP-60 | /炼体 | mobile | light |
| sc-cp60b-bodysoul-desktop-light.html | CP-60 | /炼神 | desktop | light |
| sc-cp60b-bodysoul-mobile-light.html | CP-60 | /炼神 | mobile | light |
| sc-cp61-demon-desktop-light.html | CP-61 | /镇魔 | desktop | light |
| sc-cp61-demon-mobile-light.html | CP-61 | /镇魔 | mobile | light |
| sc-cp62-ascend-desktop-light.html | CP-62 | /飞升榜 | desktop | light |
| sc-cp62-ascend-mobile-light.html | CP-62 | /飞升榜 | mobile | light |
| sc-cp63-legacy-desktop-light.html | CP-63 | /道统 | desktop | light |
| sc-cp63-legacy-mobile-light.html | CP-63 | /道统 | mobile | light |
| sc-cp64a-recipe-desktop-light.html | CP-64 | /悟丹 随机 | desktop | light |
| sc-cp64a-recipe-mobile-light.html | CP-64 | /悟丹 随机 | mobile | light |
| sc-cp64b-recipe-desktop-light.html | CP-64 | /悟器 随机 | desktop | light |
| sc-cp64b-recipe-mobile-light.html | CP-64 | /悟器 随机 | mobile | light |
| sc-cp65-council-desktop-light.html | CP-65 | /议政 | desktop | light |
| sc-cp65-council-mobile-light.html | CP-65 | /议政 | mobile | light |
| sc-cp66-swornquests-desktop-light.html | CP-66 | /结义任务 | desktop | light |
| sc-cp66-swornquests-mobile-light.html | CP-66 | /结义任务 | mobile | light |
| sc-cp07-rank-desktop-dark.html | CP-07 | /榜 | desktop | dark |
| sc-cp07-rank-mobile-dark.html | CP-07 | /榜 | mobile | dark |
| sc-cp09-world-desktop-dark.html | CP-09 | /世情 | desktop | dark |
| sc-cp09-world-mobile-dark.html | CP-09 | /世情 | mobile | dark |
| sc-cp17-sect-desktop-dark.html | CP-17 | /宗门 | desktop | dark |
| sc-cp17-sect-mobile-dark.html | CP-17 | /宗门 | mobile | dark |
| sc-cp24-heaven-desktop-dark.html | CP-24 | /天道 | desktop | dark |
| sc-cp24-heaven-mobile-dark.html | CP-24 | /天道 | mobile | dark |
| sc-cp27-fate-desktop-dark.html | CP-27 | /命格 | desktop | dark |
| sc-cp27-fate-mobile-dark.html | CP-27 | /命格 | mobile | dark |
| sc-cp31-sectorder-desktop-dark.html | CP-31 | /宗门令 | desktop | dark |
| sc-cp31-sectorder-mobile-dark.html | CP-31 | /宗门令 | mobile | dark |
| sc-cp38-era-desktop-dark.html | CP-38 | /纪元回流 | desktop | dark |
| sc-cp38-era-mobile-dark.html | CP-38 | /纪元回流 | mobile | dark |
| sc-cp43-apocalypse-desktop-dark.html | CP-43 | /大劫 | desktop | dark |
| sc-cp43-apocalypse-mobile-dark.html | CP-43 | /大劫 | mobile | dark |
| sc-cp44-ai-desktop-dark.html | CP-44 | /ai | desktop | dark |
| sc-cp44-ai-mobile-dark.html | CP-44 | /ai | mobile | dark |
| sc-cp53-prices-desktop-dark.html | CP-53 | /行情 | desktop | dark |
| sc-cp53-prices-mobile-dark.html | CP-53 | /行情 | mobile | dark |
| sc-cp59-recipes-desktop-dark.html | CP-59 | /配方 | desktop | dark |
| sc-cp59-recipes-mobile-dark.html | CP-59 | /配方 | mobile | dark |
| sc-cp63-legacy-desktop-dark.html | CP-63 | /道统 | desktop | dark |
| sc-cp63-legacy-mobile-dark.html | CP-63 | /道统 | mobile | dark |
| sc-cp46-47-48-mobile-light.html | CP-46/47/48 | /探险·/挖宝·/望气 | mobile | light |
| sc-cp46-adventure-mobile-light.html | CP-46 | /探险 落霞古洞 | mobile | light |
| sc-cp47-dig-mobile-light.html | CP-47 | /挖宝 | mobile | light |
| sc-cp48-wangqi-mobile-light.html | CP-48 | /望气 | mobile | light |
| sc-cp48-qiyu-mobile-light.html | CP-48 | /奇遇 | mobile | light |
| sc-cp48-jiyuan-mobile-light.html | CP-48 | /机缘 | mobile | light |
| sc-empty-gaoshi-desktop-light.html | AC-10 | /告示（空态） | desktop | light |
| sc-empty-gaoshi-mobile-light.html | AC-10 | /告示（空态） | mobile | light |
| sc-empty-zongmenhuan-desktop-light.html | AC-10 | /宗门环（空态） | desktop | light |
| sc-empty-zongmenhuan-mobile-light.html | AC-10 | /宗门环（空态） | mobile | light |
| sc-empty-lingchong-desktop-light.html | AC-10 | /灵宠（空态） | desktop | light |
| sc-empty-lingchong-mobile-light.html | AC-10 | /灵宠（空态） | mobile | light |
| sc-empty-qiling-desktop-light.html | AC-10 | /器灵（空态） | desktop | light |
| sc-empty-qiling-mobile-light.html | AC-10 | /器灵（空态） | mobile | light |
| sc-empty-xunbao-desktop-light.html | AC-10 | /寻宝（空态） | desktop | light |
| sc-empty-xunbao-mobile-light.html | AC-10 | /寻宝（空态） | mobile | light |
| sc-empty-desktop-light.html | AC-10 | /命格·/洞府·/灵宠·/坊市·/委托（空态合页） | desktop | light |
| sc-regress-tupo-desktop-light.html | SC-回归 | /突破（(a) 类形态未动） | desktop | light |
| sc-regress-wabao-desktop-light.html | SC-回归 | /挖宝（(a) 类形态未动） | desktop | light |
| sc-regress-jiaotan-desktop-light.html | SC-回归 | /交谈（(a) 类形态未动） | desktop | light |
| sc-regress-qiyu-desktop-light.html | SC-回归 | /奇遇（(a) 类形态未动） | desktop | light |
