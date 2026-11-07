"""图库双端前端契约（spec: gallery-gameplay §3.8/§10.3/§10.4/§10.5，G-8/G-9 前端部分）。

- 图鉴展示表键集 == 后端 GALLERY_ASSET_KEYS（38）：JS 里人物键由境界键
  模板生成，测试按 GALLERY_REALM_KEYS 重构男/女相键后与显式键取并集比对；
- 双端源码不出现 /web/assets/（只许 /assets/ 或后端下发完整路径）；
- 双端逐接入点引用后端字段：portrait/gender/gallery/art_images/
  spells_catalog[].img、items[].img、equipped[].img+spirit、clue_chain、
  here[].avatar、omen_image；命令入口 /定相 /图鉴 /寻宝 /器灵 /温养 /灵语；
- frame-tier-1..5 双端 CSS 同名表 + JS galleryFrameClass；
- onerror 兜底存在（加载失败隐藏图位）；移动端图鉴入口在操作分区。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def _read(name):
    return (WEB / name).read_text(encoding="utf-8")


def _gallery_table_keys(js):
    """从 JS 图鉴展示表重构 139 键：境界模板键 + NPC 单人 slug 表 + 显式字面键。

    集成收口（game-feel-phase2 §9）：二期展示表的新类目键以
    pets/scenes/omen/goods 前缀字面呈现、NPC 单人键由 GALLERY_NPC_SINGLE
    slug 表程序化生成（与后端 §9.1/§9.10 同口径），旧重构口径只认
    portraits|artifacts|arts|maps 四前缀且不展开 slug 表，必然少算 77 键，
    故在此扩全前缀并展开 slug 表；断言口径（键集与后端逐字一致）不变。
    """
    m = re.search(r"GALLERY_REALM_KEYS\s*=\s*\[([^\]]+)\]", js)
    assert m, "JS 缺 GALLERY_REALM_KEYS 展示表常量"
    realms = re.findall(r'"([a-z]+)"', m.group(1))
    keys = {f"portraits/{g}-{r}" for g in ("male", "female") for r in realms}
    m2 = re.search(r"GALLERY_NPC_SINGLE\s*=\s*\[(.*?)\]\];", js, re.S)
    assert m2, "JS 缺 GALLERY_NPC_SINGLE 展示表常量"
    slugs = re.findall(r'"([a-z]+-\d+)"', m2.group(1))
    keys |= {f"portraits/npc-{s}" for s in slugs}
    keys |= set(re.findall(
        r"(?:portraits|artifacts|arts|maps|pets|scenes|omen|goods)/[a-z0-9-]+", js))
    keys.discard("portraits/male-")
    keys.discard("portraits/female-")
    return keys


def test_gallery_display_table_keys_match_backend_both_ends():
    from core.gallery_assets import GALLERY_ASSET_KEYS

    for fname in ("workbench.js", "mobile.js"):
        keys = _gallery_table_keys(_read(fname))
        assert keys == set(GALLERY_ASSET_KEYS), (
            f"{fname} 图鉴展示表键集与后端不一致：多 {sorted(keys - set(GALLERY_ASSET_KEYS))}，"
            f"少 {sorted(set(GALLERY_ASSET_KEYS) - keys)}"
        )
    print("✓ G-9：双端图鉴展示表键集 == 后端 GALLERY_ASSET_KEYS（139）")


def test_no_web_assets_prefix_anywhere():
    for fname in ("workbench.js", "mobile.js", "index.html", "mobile.html",
                  "workbench.css", "mobile.css"):
        assert "/web/assets/" not in _read(fname), f"{fname} 出现禁用旁路 /web/assets/"
    print("✓ 双端源码无 /web/assets/ 旁路")


def test_desktop_gallery_view_and_nav():
    html = _read("index.html")
    js = _read("workbench.js")
    assert 'data-view="gallery"' in html, "桌面顶栏缺第 6 主境「图鉴」导航"
    assert "renderGallery" in js and 'state.view === "gallery"' in js
    assert "gallery.unlocked" in js or "g.unlocked" in js, "图鉴点亮事实须读后端 gallery"
    # §9.2 契约变更表第6行（前端半）：称号按 §9.10 新五档 (10/40/80/120/139) 修订
    for marker in ("10", "40", "80", "120", "139", "初窥门径", "博览群真", "洞鉴乾坤", "博物通览", "图录大成"):
        assert marker in js, f"图鉴称号档缺 {marker}"
    assert "gallery-silhouette" in js, "未点亮须剪影呈现"
    print("✓ 桌面图鉴视图：导航 + renderGallery + 进度称号档 + 未点亮剪影")


def test_desktop_field_references():
    js = _read("workbench.js")
    for needle in (
        "s.portrait", "s.gender", "s.gallery", "s.art_images",
        "sp.img", "it.img", "eq.img", "sel.img", "r.avatar",
        "data.omen_image", "clue_chain", "eq.spirit", "spiritHtml",
        "checkGalleryNewly", "g.newly",
    ):
        assert needle in js, f"workbench.js 缺接入字段引用：{needle}"
    for cmd in ("/定相 男", "/定相 女", "/图鉴", "/寻宝", "/宝图",
                "/器灵", "/温养 ", "/灵语"):
        assert cmd in js, f"workbench.js 缺命令入口：{cmd}"
    print("✓ 桌面逐接入点字段引用齐全（立绘/定相/法宝/器灵/功法/宝图/奇遇/图鉴）")


def test_mobile_field_references():
    js = _read("mobile.js")
    for needle in (
        "st.portrait", "st.gender", "st.gallery", "st.art_images",
        "sp.img", "it.img", "eq.img", "r.avatar",
        "data.omen_image", "clue_chain", "eq.spirit", "spiritHtmlM",
        "checkGalleryNewly", "g.newly",
    ):
        assert needle in js, f"mobile.js 缺接入字段引用：{needle}"
    for cmd in ("/定相 男", "/定相 女", "/图鉴", "/寻宝", "/宝图",
                "/器灵", "/温养 ", "/灵语"):
        assert cmd in js, f"mobile.js 缺命令入口：{cmd}"
    print("✓ 移动逐接入点字段引用齐全")


def test_mobile_gallery_entry_in_ops_and_sanctum():
    js = _read("mobile.js")
    assert "renderGalleryOps" in js and 'id="galleryOps"' in js, "移动操作分区缺图鉴段"
    assert 'data-mview="ops"' in js, "移动命盘缺图鉴进度行入口（跳操作分区）"
    # 不新增底部导航项：mobile.html 仍为 5 分区
    html = _read("mobile.html")
    assert html.count("data-mview=") == 5, "移动底部导航必须仍为 5 项"
    print("✓ 移动图鉴入口：命盘进度行 + 操作分区图鉴段，底部导航仍 5 项")


def test_frame_tier_classes_both_ends():
    for js_name, css_name in (("workbench.js", "workbench.css"),
                              ("mobile.js", "mobile.css")):
        js, css = _read(js_name), _read(css_name)
        assert "galleryFrameClass" in js, f"{js_name} 缺品阶图框函数"
        for tier in range(1, 6):
            assert f".frame-tier-{tier}" in css, f"{css_name} 缺 .frame-tier-{tier}"
        assert "prefers-reduced-motion" in css, f"{css_name} 流光须可随 reduced-motion 关闭"
    print("✓ frame-tier-1..5 双端同名表 + JS 图框函数 + reduced-motion 关照")


def test_onerror_fallback_both_ends():
    for fname in ("workbench.js", "mobile.js"):
        js = _read(fname)
        assert "onerror" in js and "display" in js and "none" in js, (
            f"{fname} 缺 onerror 隐藏图位兜底（§3.8）"
        )
        assert "galleryImg" in js, f"{fname} 缺统一图位函数 galleryImg"
    html = _read("index.html")
    assert 'id="chatAvatar"' in html and "onerror" in html, "桌面交谈头像位缺失或无兜底"
    print("✓ onerror 兜底：双端图位加载失败隐藏，不破版")


def test_mobile_status_keys_still_subset_of_backend():
    """新增 st.* 读取不得越出后端 _status_dict（与 test_mobile_web 同口径）。"""
    import ast

    tree = ast.parse((ROOT / "server" / "world.py").read_text(encoding="utf-8"))
    sent = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_status_dict":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Dict):
                    for k in sub.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            sent.add(k.value)
    js = _read("mobile.js")
    read = set(re.findall(r"\bst\.([A-Za-z_][A-Za-z0-9_]*)", js))
    assert not (read - sent), f"mobile.js 新增读取越界键：{sorted(read - sent)}"
    print("✓ mobile.js st.* 读取仍 ⊆ 后端下发键")
