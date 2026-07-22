# Batch 3 验证报告 — E9 社区 TapTV (T-M4-01/02/03)

**验证时间**：2026-07-22
**验证方式**：Playwright 无头 Chromium 可视化验证（登录 → 各交互链路 → 全程 0 console error）
**结果**：**9/9 检查通过，0 console error** ✅

## 验证项明细

| # | 检查项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | 登录后离开登录页 | PASS | verify@pea.ai 登录成功 |
| 2 | feed 渲染卡片 ≥ 4 | PASS | 实际 6 张（含 1 张本次自动发布） |
| 3 | 发布作品后卡片 +1 | PASS | 5 → 6（POST /works 落库并即时上屏） |
| 4 | 作品详情抽屉打开 | PASS | Drawer 渲染文案 + 计数 |
| 5 | 点赞切换计数 +1 | PASS | 0 → 1（POST /works/:id/like，计数实时维护） |
| 6 | 收藏切换计数 +1 | PASS | 0 → 1（POST /works/:id/favorite） |
| 7 | 评论内容出现在详情 | PASS | 发评论 → 评论列表追加 |
| 8 | 竞技场 Non-Goal 明确 | PASS | 文案"已明确移出 MVP 范围"可见 |
| 9 | 0 console error | PASS | 全程 0 报错 |

## 关键修复（自测中撞到的真实崩溃）

**崩溃根因**：`TapTV.tsx` 渲染时 `JSON.parse(w.media_urls)`，而 `works.media_urls` 是 **MySQL JSON 列**，mysql2 读出来已是**数组 `[]`** 而非字符串。`JSON.parse([])` 将数组强转空串 → `Unexpected end of JSON input` → **TapTV 渲染抛错 → React 整树卸载**（URL 退回 `/`，所有页面消失）。

这正是 E9 此前"卡在自测中"的真实原因——不是没测，是**自测中真撞到了崩溃**。

**修复**：
- `hasMedia()` 兼容 `数组 / 字符串 / null` 三种形态，不再裸 `JSON.parse`。
- 顺手把 canvas 两条 `JSON.parse(graph_json)`（挂载路径隐患，空串/`null` 同样会崩）也改成防御式。

## 本轮新增/修改文件

**后端**
- `services/bff/src/modules/community/` 新模块：community.dto / service / controller / module
  - `GET /works`（feed，含作者/计数/liked_by_me/favorited_by_me）
  - `POST /works`（发布）
  - `GET /works/:id`、`POST/DELETE /works/:id/like`、`POST/DELETE /works/:id/favorite`、`GET/POST /works/:id/comments`
- `infra/mysql/init/01-schema.sql` + 运行库：`works` 加 `likes_count/comments_count/favorites_count`；新建 `work_likes / work_favorites / work_comments` 三表
- `app.module.ts` 注册 CommunityModule
- `infra/docker/nginx.conf` + `web/vite.config.ts`：补 `/works` 反向代理（与 `/providers` 同模式）

**前端**
- `web/src/components/pages/TapTV.tsx`：重写为真实社区（发布弹窗 + 卡片流 + 详情抽屉 + 点赞/收藏/评论切换）
- `web/src/components/pages/Arena.tsx`：澄清竞技场 Non-Goal 占位

## 附带修复的遗留 bug
- `providers.service.update()` 解构取首行对象误查 `.length` → 恒 404（Batch 2 已修）
- nginx/vite 遗漏 `/providers`、`/works` 代理路径（Batch 2/3 已修）
- antd v5 无图标主按钮文本插入间隔空格（`'发 布'`），Playwright 精确文本匹配失效 → 验证脚本改按类名定位

## 验证产物
- `verify_e9.py`（Playwright 验证脚本）
- `verify_shots/e9_01_feed.png` ~ `e9_06_arena.png`（9 张过程截图）
