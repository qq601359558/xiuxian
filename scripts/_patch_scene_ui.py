# 一次性：替换网页场景区为「聊天主交互 + 抽屉」
from pathlib import Path

p = Path(r"D:\codex\xiuxian\web\index.html")
t = p.read_text(encoding="utf-8")
start = t.find("      <!-- 右：场景")
end = t.find("      </aside>", start)
if start < 0 or end < 0:
    print("markers", start, end)
    raise SystemExit(1)
end = end + len("      </aside>")
new = r'''      <!-- 右：场景 — 聊天主交互，功能收抽屉 -->
      <aside class="rail right scene-rail">
        <section class="card scene">
          <header class="card-h">
            <h2>此地 · 聊天为主</h2>
            <span id="zoneTag" class="tag">—</span>
          </header>
          <div class="scene-name" id="sceneName">—</div>
          <div class="scene-meta" id="sceneMeta">点同场道友开聊窗；下方抽屉收纳修行/交易等</div>
          <div class="scene-actions">
            <button class="btn-soft sm" data-cmd="/here">刷新同场</button>
            <button class="btn-soft sm" data-cmd="/做 我环顾四周">环顾四周</button>
          </div>
        </section>

        <section class="card grow chat-primary">
          <header class="card-h">
            <h2>同场修士</h2>
            <span class="muted" id="hereCount"></span>
          </header>
          <div id="hereList" class="here-list">
            <p class="empty">尚无同道 · 点人即可开聊</p>
          </div>
        </section>

        <section class="drawer-section">
          <div class="drawer-bar" role="tablist" aria-label="场景功能">
            <button type="button" class="drawer-tab" data-drawer="cultivate">修行</button>
            <button type="button" class="drawer-tab" data-drawer="market">交易</button>
            <button type="button" class="drawer-tab" data-drawer="explore">历练</button>
            <button type="button" class="drawer-tab" data-drawer="sect">仙门</button>
            <button type="button" class="drawer-tab" data-drawer="world">天下</button>
          </div>
          <div id="drawer-cultivate" class="drawer-panel hidden" data-drawer-panel="cultivate">
            <div class="drawer-hint">闭关 / 突破 / 功法 / 装备</div>
            <div class="btn-grid">
              <button class="btn-soft" data-cmd="/闭关 1">闭关 1h</button>
              <button class="btn-soft" data-cmd="/闭关 8">闭关 8h</button>
              <button class="btn-soft" data-cmd="/出关">出关</button>
              <button class="btn-soft accent" data-cmd="/突破">突破</button>
              <button class="btn-soft" data-cmd="/归隐">归隐</button>
              <button class="btn-soft" data-cmd="/出隐">出隐</button>
              <button class="btn-soft" data-cmd="/功法">我的功法</button>
              <button class="btn-soft" data-prompt="自创功法" data-cmd-prefix="/自创功法" data-placeholder="理念，如：噬血炼骨">自创功法…</button>
              <button class="btn-soft" data-prompt="穿戴" data-cmd-prefix="/穿戴" data-placeholder="装备名">穿戴…</button>
              <button class="btn-soft" data-prompt="卸下" data-cmd-prefix="/卸下" data-placeholder="装备名">卸下…</button>
              <button class="btn-soft" data-prompt="服用" data-cmd-prefix="/服用" data-placeholder="丹药名">服用…</button>
              <button class="btn-soft" data-cmd="/灵气">全服灵气</button>
            </div>
          </div>
          <div id="drawer-market" class="drawer-panel hidden" data-drawer-panel="market">
            <div class="drawer-hint">坊市买卖 / 金库 / 寄售 / 悬赏</div>
            <div class="btn-grid">
              <button class="btn-soft" data-cmd="/坊市">坊市</button>
              <button class="btn-soft" data-prompt="购买" data-cmd-prefix="/购买" data-placeholder="货名 [数量]">购买…</button>
              <button class="btn-soft" data-prompt="出售" data-cmd-prefix="/出售" data-placeholder="货名 [数量]">出售…</button>
              <button class="btn-soft" data-prompt="寄存" data-cmd-prefix="/寄存" data-placeholder="灵石" data-num="1">寄存…</button>
              <button class="btn-soft" data-prompt="支取" data-cmd-prefix="/支取" data-placeholder="灵石" data-num="1">支取…</button>
              <button class="btn-soft" data-prompt="寄售" data-cmd-prefix="/寄售" data-placeholder="货 价格">寄售…</button>
              <button class="btn-soft" data-prompt="买寄售" data-cmd-prefix="/买寄售" data-placeholder="编号" data-num="1">买寄售…</button>
              <button class="btn-soft" data-prompt="撤单" data-cmd-prefix="/撤单" data-placeholder="编号" data-num="1">撤单…</button>
              <button class="btn-soft" data-cmd="/npc货单">NPC货单</button>
              <button class="btn-soft" data-cmd="/告示">告示</button>
              <button class="btn-soft" data-prompt="挂赏" data-cmd-prefix="/挂赏" data-placeholder="道号 赏金 [缘由]">挂赏…</button>
              <button class="btn-soft" data-prompt="接令" data-cmd-prefix="/接令" data-placeholder="编号" data-num="1">接令…</button>
              <button class="btn-soft" data-cmd="/望气">望气</button>
            </div>
          </div>
          <div id="drawer-explore" class="drawer-panel hidden" data-drawer-panel="explore">
            <div class="drawer-hint">探险 / 秘境 / 机缘 / 探查</div>
            <div class="btn-grid">
              <button class="btn-soft" data-cmd="/探查">探查</button>
              <button class="btn-soft" data-cmd="/机缘">探机缘</button>
              <button class="btn-soft" data-cmd="/探险">探险列表</button>
              <button class="btn-soft" data-prompt="探险" data-cmd-prefix="/探险" data-placeholder="野外 / 秘境名">外出探险…</button>
              <button class="btn-soft" data-cmd="/秘境">天机榜</button>
              <button class="btn-soft" data-cmd="/秘境 落霞古洞">落霞古洞</button>
              <button class="btn-soft" data-cmd="/秘境 黑风绝渊裂隙">黑风裂隙</button>
              <button class="btn-soft" data-cmd="/秘境 万星遗迹残址">万星残址</button>
              <button class="btn-soft accent" data-cmd="/秘境 探">推进</button>
              <button class="btn-soft" data-cmd="/秘境 弃">放弃</button>
              <button class="btn-soft" data-cmd="/挖宝">挖宝</button>
              <button class="btn-soft" data-cmd="/除凶">除凶榜</button>
              <button class="btn-soft" data-cmd="/回访">因果回访</button>
            </div>
          </div>
          <div id="drawer-sect" class="drawer-panel hidden" data-drawer-panel="sect">
            <div class="drawer-hint">宗门 / 势力 / 宗门令</div>
            <div class="btn-grid">
              <button class="btn-soft" data-cmd="/宗门">宗门</button>
              <button class="btn-soft" data-prompt="拜入" data-cmd-prefix="/拜入" data-placeholder="宗门名">拜入…</button>
              <button class="btn-soft" data-cmd="/叛门">叛门</button>
              <button class="btn-soft" data-cmd="/领俸禄">领俸</button>
              <button class="btn-soft" data-cmd="/晋升">晋升</button>
              <button class="btn-soft" data-prompt="传功" data-cmd-prefix="/传功" data-placeholder="弟子道号">传功…</button>
              <button class="btn-soft" data-cmd="/势力">势力</button>
              <button class="btn-soft" data-cmd="/宗门令">宗门令</button>
              <button class="btn-soft" data-cmd="/宗门势">宗门势</button>
              <button class="btn-soft" data-cmd="/宗门环">日环</button>
              <button class="btn-soft" data-cmd="/贡献">贡献</button>
              <button class="btn-soft" data-cmd="/大劫">大劫</button>
              <button class="btn-soft" data-cmd="/转世">道统/转世</button>
            </div>
          </div>
          <div id="drawer-world" class="drawer-panel hidden" data-drawer-panel="world">
            <div class="drawer-hint">世界演变 / 榜 / 频道 / 史笔</div>
            <div class="btn-grid">
              <button class="btn-soft accent" data-cmd="/世情">世界演变</button>
              <button class="btn-soft" data-cmd="/天道">天道</button>
              <button class="btn-soft" data-cmd="/天道 推演">天道推演</button>
              <button class="btn-soft" data-cmd="/世界弧">世界弧</button>
              <button class="btn-soft" data-cmd="/纪元回流">纪元回流</button>
              <button class="btn-soft" data-cmd="/传说">传说</button>
              <button class="btn-soft" data-cmd="/频道">频道</button>
              <button class="btn-soft" data-cmd="/榜">六榜</button>
              <button class="btn-soft" data-cmd="/who">天下</button>
              <button class="btn-soft" data-cmd="/大事记">大事记</button>
              <button class="btn-soft" data-cmd="/因果">因果链</button>
              <button class="btn-soft" data-cmd="/帮助 天下">帮助·天下</button>
            </div>
          </div>
        </section>
      </aside>'''
t2 = t[:start] + new + t[end:]
p.write_text(t2, encoding="utf-8")
print("ok drawer-tab", t2.count("drawer-tab"), "chat-primary", t2.count("chat-primary"))
