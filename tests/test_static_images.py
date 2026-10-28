"""
静态图片路由与 MIME 类型验证测试
"""
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.app import GameHandler


def test_static_images_exist():
    """验证 6 张本地静态图资产均已就位且非空"""
    img_dir = Path("web/images")
    expected = [
        "realm_1.jpg",
        "realm_2.jpg",
        "realm_3.jpg",
        "realm_4.jpg",
        "portrait.jpg",
        "sanctum_bg.jpg",
        "sanctum_bg_dark.png",
        "cultivator_meditating.png",
        "jade_slip_frame.png",
        "lifespan_compass.png",
    ]
    for name in expected:
        fp = img_dir / name
        assert fp.is_file(), f"Missing {name}"
        assert fp.stat().st_size > 1000, f"File {name} is suspiciously small: {fp.stat().st_size}"


def test_serve_static_image_routing():
    """验证 GameHandler._serve_static 成功路由 /images/ 与 /web/images/"""
    handler = GameHandler.__new__(GameHandler)
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = io.BytesIO()

    # 测试 /images/realm_1.jpg
    res = handler._serve_static("/images/realm_1.jpg")
    assert res is True
    handler.send_response.assert_called_with(200)
    handler.send_header.assert_any_call("Content-Type", "image/jpeg")

    # 测试 /web/images/portrait.jpg
    handler.send_response.reset_mock()
    handler.send_header.reset_mock()
    res2 = handler._serve_static("/web/images/portrait.jpg")
    assert res2 is True
    handler.send_response.assert_called_with(200)
    handler.send_header.assert_any_call("Content-Type", "image/jpeg")

    # 测试 /images/cultivator_meditating.png (PNG MIME 校验)
    handler.send_response.reset_mock()
    handler.send_header.reset_mock()
    res_png = handler._serve_static("/images/cultivator_meditating.png")
    assert res_png is True
    handler.send_response.assert_called_with(200)
    handler.send_header.assert_any_call("Content-Type", "image/png")

    # 测试不存在的图片返回 False
    res3 = handler._serve_static("/images/nonexistent_image.jpg")
    assert res3 is False


def test_workbench_js_zero_external_images():
    """验证 workbench.js 中不再存在任何 googleusercontent 境外外链"""
    content = Path("web/workbench.js").read_text(encoding="utf-8")
    assert "googleusercontent.com" not in content
    assert "handleImgFallback" in content
    assert "/images/realm_1.jpg" in content
    assert "/images/portrait.jpg" in content
