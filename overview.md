# 主题控件改下拉（2026-07-24 22:28）

## 用户反馈
原来 TopNav 顶部的主题控件是 antd `Segmented`（浅 / 深 / 跟随 三个分段按钮），要求改为下拉选择（`Select`）样式，并在画布右上角也加一份同样的下拉。

## 改动
1. **`web/src/components/TopNav.tsx`**
   - 把 `Segmented` 换成 antd `Select`，共用 class `.pea-theme-select`；
   - 选项标签从 `浅 / 深 / 跟随` 改为 `浅色 / 深色 / 跟随系统`，更完整；
   - 后缀箭头 `▾` 替换默认图标，视觉更克制。
2. **`web/src/components/CanvasEditor.tsx`**
   - 在 `CanvasActions` 的最左侧新增同样的 `Select`（`useTheme()` 注入 `mode/setMode`）；
   - **不**用 `<Tooltip>` 包裹（hover 残留文字会跟下拉面板挤在一起，已验证）。
3. **`web/src/styles/index.css`**
   - 新增 `.pea-theme-select` 紧凑胶囊样式（32px 高、`border-radius:999px`、hover/open 高亮 brand 色），与 `.pea-canvas-tapies` / `.pea-canvas-community` 视觉一致。

## 验证（真机）
- TopNav `.pea-theme-select` 计数 = 1，画布 `.pea-canvas-actions .pea-theme-select` 计数 = 1；
- 选项内容一致：`['浅色', '深色', '跟随系统']`；
- 从任一处切换主题 → 整站即时生效；
- console error = 0。

## 截图
- `verify/_canvas_layout/15_canvas_theme_select_closed.png` — 画布关掉下拉
- `verify/_canvas_layout/16_canvas_theme_select_open.png` — 画布下拉打开（无 Tooltip 残留）
- `verify/_canvas_layout/19_topnav_theme_select_open.png` — TopNav 下拉打开

## 部署
构建产物 `index-D--CFiaQ.js`（CSS `index-C3x9bVgx.css`）已 `docker cp` + `nginx -s reload` 生效。