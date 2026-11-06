"""
处理并将生成的核心国风视觉素材导出至 web/images/
"""
import os
import numpy as np
from PIL import Image

BRAIN_DIR = r"C:\Users\tengf\.gemini\antigravity\brain\ec7ccd39-aa0b-481e-ad8c-918ace44fe40"
DEST_DIR = r"D:\codex\xiuxian\web\images"
os.makedirs(DEST_DIR, exist_ok=True)


def process_sanctum_bg():
    src = os.path.join(BRAIN_DIR, "sanctum_bg_dark_empty_1792405076360.jpg")
    img = Image.open(src).convert("RGB")
    dest_png = os.path.join(DEST_DIR, "sanctum_bg_dark.png")
    dest_jpg = os.path.join(DEST_DIR, "sanctum_bg_dark.jpg")
    img.save(dest_png, "PNG")
    img.save(dest_jpg, "JPEG", quality=92)
    print(f"Saved sanctum_bg_dark -> {dest_png}, size={img.size}")


def process_cultivator():
    src = os.path.join(BRAIN_DIR, "cultivator_meditating_1792405100835.jpg")
    img = Image.open(src).convert("RGBA")
    arr = np.array(img, dtype=np.float32)
    
    # 根据亮度或最大通道做黑底渐变羽化抠图
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    max_val = np.maximum(r, np.maximum(g, b))
    
    # 阈值：< 15 完全透明，15 ~ 50 线性渐变羽化，> 50 完全不透明
    alpha = np.clip((max_val - 15.0) / 35.0, 0.0, 1.0) * 255.0
    arr[..., 3] = alpha
    
    out = Image.fromarray(arr.astype(np.uint8), mode="RGBA")
    dest_png = os.path.join(DEST_DIR, "cultivator_meditating.png")
    out.save(dest_png, "PNG")
    print(f"Saved cultivator_meditating -> {dest_png}, size={out.size}")


def process_jade_slip():
    src = os.path.join(BRAIN_DIR, "jade_slip_frame_1792405136199.jpg")
    img = Image.open(src).convert("RGBA")
    arr = np.array(img, dtype=np.float32)
    
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    max_val = np.maximum(r, np.maximum(g, b))
    
    # 外部黑底透明化，四角纯黑剔除
    alpha = np.clip((max_val - 12.0) / 28.0, 0.0, 1.0) * 255.0
    arr[..., 3] = alpha
    
    out = Image.fromarray(arr.astype(np.uint8), mode="RGBA")
    dest_png = os.path.join(DEST_DIR, "jade_slip_frame.png")
    out.save(dest_png, "PNG")
    print(f"Saved jade_slip_frame -> {dest_png}, size={out.size}")


def process_lifespan_compass():
    src = os.path.join(BRAIN_DIR, "lifespan_compass_1792405159216.jpg")
    img = Image.open(src).convert("RGBA")
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]
    
    # 中心坐标与圆形半径
    cy, cx = h / 2.0, w / 2.0
    radius = min(cx, cy) * 0.96
    
    y, x = np.ogrid[:h, :w]
    dist_from_center = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    max_val = np.maximum(r, np.maximum(g, b))
    
    # 颜色阈值 alpha
    color_alpha = np.clip((max_val - 15.0) / 35.0, 0.0, 1.0)
    # 边缘圆形羽化
    circle_alpha = np.clip((radius - dist_from_center) / 6.0, 0.0, 1.0)
    
    combined_alpha = color_alpha * circle_alpha * 255.0
    arr[..., 3] = combined_alpha
    
    out = Image.fromarray(arr.astype(np.uint8), mode="RGBA")
    dest_png = os.path.join(DEST_DIR, "lifespan_compass.png")
    out.save(dest_png, "PNG")
    print(f"Saved lifespan_compass -> {dest_png}, size={out.size}")


if __name__ == "__main__":
    process_sanctum_bg()
    process_cultivator()
    process_jade_slip()
    process_lifespan_compass()
    print("All visual assets processed successfully.")
