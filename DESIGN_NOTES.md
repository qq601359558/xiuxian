# DESIGN_NOTES — 天道因果录工作台

## 方向
「日常高频工作台」：先回答「世界怎样了 / 同场有谁 / 我下一步做什么」，再收纳指令。
不是 KPI 卡墙，不是终端换皮。

## Token
- 深色默认（游戏夜修）+ 浅色（白天）
- 品牌金 #C9A227；状态：玉成功 / 血危险 / 雾次要
- 标题衬线（系统栈），正文 system-ui，数据 mono

## 结构
- 顶栏：品牌 + 服务器 + 在线 + 主题
- 天道盘：连续状态条（非卡片）
- 左：迁跃地点列表
- 中：动态时间线 | 同场列表 | 世界分区
- 底：敕令/自由发言输入 + 补全
- 聊天主从：点同场 → 右侧/抽屉详情聊窗

## 组件（离线自研，风格对齐 shadcn/Aceternity 质感）
列表、详情、Tab、抽屉、Command Palette、Toast、Skeleton、Empty、Error、Offline

## 状态
加载/空/错误/离线；Esc 关面板；focus-visible；prefers-reduced-motion

## 演进
- 旧 web/ 保留；本工作台为 cwd index.html 入口，并同步 web/ 供局域网服
