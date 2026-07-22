# Batch 2 验证报告 — E8 主页/账户 + E7 AI Provider 配置

**日期**: 2026-07-22
**验证工具**: Playwright (Chromium headless, 1440×900)
**验证脚本**: `verify_e8.py`
**截图目录**: `verify_shots/e8_*.png`

---

## 验收结果: ✅ 全部通过

| # | 检查项 | 任务 | 结果 |
|---|--------|------|------|
| 1 | 主页「最近项目」可见 + 项目卡片渲染 | T-M3-01 | ✅ 6 个项目卡片 |
| 2 | 设置页 Provider 卡片列表 (5个) | T-G-06 | ✅ |
| 3 | Provider 开关切换 (Mock 视频生成 ON→OFF) | T-G-06 | ✅ |
| 4 | 设为默认 (Seedance 2.0 → 默认) | T-G-06 | ✅ |
| 5 | **刷新后持久化**: mock-video 仍关闭 / seedance 仍默认 | T-G-06 | ✅ |
| 6 | 账户中心: 标题 + Tapies 余额 + 积分流水 | T-M5-01 | ✅ |
| 7 | Console errors | 全局 | **0** |

## 截图清单

| 文件 | 内容 |
|------|------|
| `e8_01_home.png` | 主页 Workspace — 欢迎、快捷操作、6 个项目卡片、新建项目按钮 |
| `e8_02_settings.png` | AI Provider 设置 — 5 张 Provider 卡片（初始状态） |
| `e8_03_settings_toggled.png` | 切换后 — Mock 视频生成已关闭，Seedance 2.0 为默认（紫色边框+默认标签） |
| `e8_04_settings_persist.png` | 刷新后持久化确认 — 状态保持不变 |
| `e8_05_account.png` | 账户中心 — VerifyBot 资料、1000 Tapies 余额、积分流水空状态 |

## 新增/修改文件清单

### 后端 (BFF)
- `services/bff/src/modules/providers/providers.dto.ts` — UpdateProviderDto
- `services/bff/src/modules/providers/providers.service.ts` — list(种子)/update(开关+默认)
- `services/bff/src/modules/providers/providers.controller.ts` — GET/PATCH /providers
- `services/bff/src/modules/providers/providers.module.ts`
- `services/bff/src/app.module.ts` — 注册 ProvidersModule
- `services/bff/src/modules/canvases/canvases.controller.ts` — +GET /canvases (list)
- `services/bff/src/modules/canvases/canvases.service.ts` — +list(userId)
- `infra/mysql/init/01-schema.sql` — +ai_providers 表

### 前端 (Web)
- `web/src/components/pages/Home.tsx` — 升级为真实工作台 (T-M3-01)
- `web/src/components/pages/Settings.tsx` — AI Provider 设置页 (T-G-06/T-M5-02)
- `web/src/components/pages/Account.tsx` — 账户中心 (T-M5-01)
- `web/src/store/ui.ts` — PageKey 增加 settings/account
- `web/src/store/canvas.ts` — +openCanvas(id) 动作
- `web/src/components/Workspace.tsx` — 路由 Settings/Account
- `web/src/components/TopNav.tsx` — NAV 增加账户/设置
- `web/src/components/UserMenu.tsx` — 菜单增加账户中心/AI Provider设置入口
- `web/vite.config.ts` — proxy 增加 /providers
- `infra/docker/nginx.conf` — proxy regex 增加 providers

### 验证
- `verify_e8.py` — Playwright 自动化验证脚本

## 发现与修复的 Bug

1. **PATCH 404 "provider not found"**: `providers.service.ts` 的 `update()` 方法用 `const [cur] = await query(...)` 解构取首行对象后检查 `.length`，但对象无 `.length` 属性导致始终抛出 NotFoundException。修复：改用数组变量 `found` 检查 `.length`。
2. **nginx/vite 缺少 `/providers` 代理**: 新增的 providers API 路径未加入 nginx 反代正则和 Vite dev proxy，导致前端请求返回 SPA HTML 而非 JSON。两处均已补全。

## 下一步建议

- **Batch 3**: E9 社区 TapTV (T-M4-01 feed/发布, T-M4-02 作品互动, T-M4-03 竞技场)
- **Batch 4**: E10 质量门 (T-OBS-01 测试基线, T-OBS-03 性能基准)
- **Latent bug 待修**: billing preauthorize 幂等检查存在相同解构模式 (`[existing]` vs 数组)，可能导致重复扣费（当前仅影响并发场景）
