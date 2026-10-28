---
feature: offline-images-and-fallback
status: completed
updated: 2026-10-15
branch: feat/character-integrity-and-audit-rules
---

# 局域网离线图片本地化与国风水墨优雅兜底 (Offline Images & Ink Fallback)

## 1. 痛点与目标 (Problem & Goals)
- **痛点**：前端 `workbench.js` 中的仙山全景、修士真人立绘和四大秘境探险图卷，硬编码引用了 Google 境外 CDN（`lh3.googleusercontent.com`）。在局域网内其他未配置科学上网代理的设备（手机/平板/局域网电脑）访问时，图片加载失败；又因外层容器写死 `bg-slate-900` 与深色遮罩，导致图片位置呈现为一片死黑块。
- **目标**：
  1. 将 6 张高清 JPEG 资产完整持久化保存至 `web/images/`。
  2. `server/app.py` 支持 `/images/` 与 `/web/images/` 路由及正确的 `image/jpeg` 等 MIME 头。
  3. `web/workbench.js` 统一引用本地相对路径 `/images/...`。
  4. 增加 `onerror` 国风水墨渐变与 SVG 意境占位兜底，即使图片丢失或离线也绝不出现难看黑块。

## 2. 详细改动清单 (Implementation Plan)
- **静态资源 (`web/images/`)**：
  - `realm_1.jpg`: 落霞灵泉
  - `realm_2.jpg`: 落霞古洞 / 黑风绝渊
  - `realm_3.jpg`: 黑风绝渊裂隙
  - `realm_4.jpg`: 万星遗迹 / 万星古岛
  - `portrait.jpg`: 太素仙尊道身真影
  - `sanctum_bg.jpg`: 仙山云海全景画卷
- **服务端静态路由 (`server/app.py`)**：
  - 增加 `/images/` 前缀到 `web/images/` 的路由映射。
  - 增加 `.jpg` / `.jpeg` (`image/jpeg`)、`.png` (`image/png`)、`.webp` (`image/webp`) MIME 处理。
- **前端适配与兜底 (`web/workbench.js`)**：
  - 定义 `const ASSETS = { ... }` 统一管理图片路径。
  - 注入全局 `handleImgFallback(img, title)`，当图片加载失败时安全切换为矢量国风印记，防止循环触发。
  - 仙山云海全景背景添加 CSS 国风水墨渐变底层。

## 3. 验收任务 (Acceptance Criteria)
- [x] T1: `web/images/` 存放全部 6 张 JPEG 图像，文件字节完整有效。
- [x] T2: `server/app.py` 能成功响应 `/images/*.jpg` 请求，状态码 200，`Content-Type: image/jpeg`。
- [x] T3: `web/workbench.js` 中的 Google CDN 境外外链全部清零，全部替换为 `/images/...`。
- [x] T4: `handleImgFallback` 容灾生效，测试或篡改路径时不发生死循环，且呈现水墨占位。
- [x] T5: 运行相关单元测试与系统回归测试全绿通过。
