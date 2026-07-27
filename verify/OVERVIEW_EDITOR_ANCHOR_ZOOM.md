# 编辑框 / 功能条：锚定节点 + 缩放不变形

## 用户诉求
1. 下方的编辑框和上方的功能条，都要**基于节点相对固定**（跟随节点平移）。
2. 画布放大/缩小时，两栏的**样式和大小不能变**；节点本身可放大缩小，但这两栏不变。
3. 之前的功能条样式和大小与编辑框不搭，需要统一视觉语言。

## 根因
- **编辑框**（`NodeChatPrompt`）：原实现是 `position: fixed` 浮层，靠 `rAF` + `getBoundingClientRect` 每帧追节点坐标 → 与节点平移不同步（抖动），且宽度按 `nodeWidth * zoom` 计算 → 随缩放变形。
- **功能条**（`ResultToolbar`）：本就在节点内部、随节点平移，但**没有抵消缩放**，所以画布放大时它跟着变大。

## 改动
| 文件 | 改动 |
|---|---|
| `PeaNode.tsx` | 节点根内新增锚点容器 `.pea-node-editor-anchor`（`data-pea-anchor={id}`） |
| `NodeChatPrompt.tsx` | 编辑框 `createPortal` 进选中节点内部（不再是 fixed 浮层）；移除 rAF 定位；加 `nodrag nopan` + 阻止冒泡，点编辑框不会误拖节点；保留"空间不足翻转到上方"的可见性逻辑（改在 render 用 viewport 计算） |
| `CanvasEditor.tsx` | 新增 `ZoomVarSync`：把 `1/zoom` 写入全局 CSS 变量 `--pea-inv-zoom`（仅 zoom 变化时写一次） |
| `index.css` | 两栏均 `transform: scale(var(--pea-inv-zoom))` 抵消缩放；间距用 `calc(… * var(--pea-inv-zoom))` 保持屏幕恒定；`.react-flow__node.selected{z-index:1000}` 防止被遮挡；**显式 `pointer-events:auto`** 修复锚点 `none` 继承导致的点不动 |
| 顶部功能条 | 圆角 `999px→14px`、底色与编辑框统一 `rgba(28,28,34,.96)`、按钮 `30px圆→32px圆角8px`，加 counter-scale |

## 真机验证（Node Playwright 打 `localhost:8088`，确定性可复现）
放大到 **zoom = 3** 实测：

| 指标 | zoom=1 | zoom=3 | 结论 |
|---|---|---|---|
| 节点卡片宽 | 280 | **840** | 节点随缩放变大 ✅ |
| 编辑框宽 | 520 | **520** | 恒定不变 ✅ |
| 功能条宽 | 340 | **340** | 恒定不变 ✅ |
| 功能条 scaleX | 1 | **0.3333 (=1/zoom)** | 完美抵消缩放 ✅ |
| 编辑框中心 X vs 节点中心 X | 一致 | 一致 | 相对固定、随节点平移 ✅ |

`0 console error`，`RESULT: ALL PASS`。

回归 `verify_editor_two_bugs.cjs`（之前两个严重交互 bug）同样 **ALL PASS**，无回归。

## 复现命令
```bash
cd /d/workspace/pea/verify
# 锚定+缩放验证
NODE_PATH='C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules' \
  /c/Users/admin/.workbuddy/binaries/node/versions/22.22.2/node.exe verify_editor_anchor_zoom.cjs
# 交互回归
NODE_PATH='C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules' \
  /c/Users/admin/.workbuddy/binaries/node/versions/22.22.2/node.exe verify_editor_two_bugs.cjs
```

> 浏览器直接开 `http://localhost:8088` 即为本次部署产物（已 `npm run build` + `docker cp` + `nginx -s reload`）。硬刷新（Ctrl+Shift+R）拿新包。
