# E7 全局系统 G — 可视化验证报告

## 环境
- **目标**: http://localhost:8088 (pea-server-web 容器, Docker Compose)
- **浏览器**: Playwright Chromium (headless), viewport 1440x900
- **测试账号**: verify@pea.ai / password123 (VerifyBot)
- **时间**: 2026-07-22 21:18 CST

## 验证结果：13/13 PASS, 0 console error

| # | 验证项 | 结果 | 截图 |
|---|---|---|---|
| 01 | 登录页渲染 (pea Creative OS 卡片) | PASS | 01_login.png |
| 02 | 注册表单切换 ("创建你的工作区") | PASS | 02_register_form.png |
| 03 | 注册+进入工作空间 (ReactFlow 画布渲染) | PASS | 03_workspace_canvas.png |
| 04 | 顶栏积分显示 (1000 Tapies) | PASS | (同03) |
| 05 | SPA导航-主页 | PASS | 04_home.png |
| 06 | SPA导航-电商套图 | PASS | 05_ecom.png |
| 07 | SPA导航-TapTV | PASS | 06_tvtv.png |
| 08 | SPA导航-竞技场 | PASS | 07_arena.png |
| 09 | SPA返回工作空间 (画布常驻不卸载) | PASS | 08_back_to_canvas.png |
| 10 | 通知中心抽屉 + 欢迎种子通知 | PASS | 09_notification_center.png |
| 11 | 分享复制链接 (Toast 反馈) | PASS | 10_share_toast.png |
| 12 | 用户菜单 (统计卡+13项菜单+退出登录) | PASS | 11_user_menu.png |
| 13 | 深色主题切换 (htmlClass=dark) | PASS | 12_dark_theme.png |

## 运行期质量
- Console error: **0**
- Page error: **0**
- 所有交互响应 < 2s

## 关键视觉确认（人工审阅）
1. **TopNav 完整性**: Logo + 画布标题栏 + 5 导航项(激活态青紫渐变下划线) + 余额按钮 + 分享图标 + 铃铛(未读角标) + 主题 Segmented + 用户头像 → **全部到位**
2. **SPA 切换**: 5 个页面切换流畅, 画布在 workspace 页常驻(hidden 不卸载), 回切时 ReactFlow 仍存在 → **FR-G1 满足**
3. **通知中心**: 右侧 Drawer, 种子通知"欢迎来到 pea"正确展示, 打开即标记已读 → **FR-G6 满足**
4. **分享**: 点击后 Toast "链接已复制到剪贴板"出现(headless 中走 execCommand 降级路径, 显示 URL) → **FR-G5 满足**
5. **用户菜单**: 下拉含完整 13 项(主页/个人主页/通知/礼包超市/订阅/教程/帮助/快捷键/反馈/Discord/联系我们/退出登录), 用户统计卡(作品/关注者/关注中), 退出为红色 danger 样式 → **FR-M5-07 满足**
6. **深色主题**: 点击"深"后整页切换至暗色模式, html class="dark", 导航/画布/面板均跟随 → **FR-G3 满足**

## 结论
E7 全局系统 G **可视化验证全部通过**, 可进入下一阶段开发。
