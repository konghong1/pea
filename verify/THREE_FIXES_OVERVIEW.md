# 画布三处交互问题修复 — 总结

针对画布（ReactFlow 节点编辑器）的三个交互问题，已完成修复并通过真浏览器端到端验证（16 条断言全部 PASS）。

## 问题 1：连线要连到「节点框」、连接点浮在框外固定间隔（带“弹开”）
**现象**：连线端点落在悬浮的连接点圆点上（与节点框有间隔），而不是连到节点框本身；要求线连框、连接点保持框外固定间隔并保留 hover“弹开”跟随。
**修复**：
- `PeaNode.tsx`：连接点（手柄）中心精确置于距框 `HANDLE_GAP=14px` 处（`handleOffset = -(HANDLE_GAP / zClamped + HANDLE_HALF)`，注意**只有间距 HANDLE_GAP 需反缩放，半径 HANDLE_HALF 不除 zoom**）；hover“弹开”跟随逻辑（`--pea-hx/--pea-hy` 热区跟随 + 钳制不进框）原样保留。
- `PeaEdge.tsx`：自定义边把两端点朝各自节点框方向回退**恒定** `gap = HANDLE_GAP + HANDLE_HALF`（不除以 zoom、不读 `useStore`）。
  - **关键根因（缩放回归）**：ReactFlow 的边端点 `sourceX/targetX` 在**边创建那一刻**根据当时 zoom 下手柄的 DOM 位置计算，之后 zoom 变化**不会重算**。`[PEAEDGE]` 调试日志证实：zoom=1 建边时 sourceX=720.5、gap≈20.5 正确；但 `setViewport(2)` 后 sourceX 仍为 720.5（冻结），若 gap 再按实时 zoom 算成 13.5，边会**反向越过框边约 14px**——这就是用户看到的“放大后线没连上、连接点跑进框里”。改用恒定回退量后，线恒落在框边。
  - `index.css` `.react-flow__handle.pea-handle` 增加 `transform-origin: center center !important`：ReactFlow 对手柄施加 `scale(1/zoom)` 以保持屏幕恒定大小，其默认 `transform-origin` 在左右边缘，高倍缩放时把手柄“拉”进框内；改 center 后手柄圆点永远以自身中心缩放，稳定浮在框外 HANDLE_GAP。
- `CanvasEditor.tsx`：入边统一强制 `targetHandle:'in'`（左侧框边），`onConnectEnd` 兜底；上传图不连入边。

## 问题 2：框选时节点看不见 / 触发下方节点弹框
**现象**：框选矩形不透明遮住节点；框选经过节点时下方节点的连接点 / 输入栏 / 弹框闪现。
**修复**：
- `index.css` `.react-flow__selection`：背景设为 `rgba(31,162,220,0.06)` 且强制 `!important`（ReactFlow 运行时注入的默认样式会覆盖不透明背景），`pointer-events: none !important` → 可透视、不拦截事件。
- 框选进行中给画布容器加 `.pea-selecting` 类，抑制节点 hover 手柄显隐与弹框。
- `NodeChatPrompt.tsx` / `TextNodeToolbar.tsx`：`single = selectedIds.length===1 ? selectedIds[0] : null`（去掉 `selectedId` 兜底，避免多选时误弹输入栏 / 文本工具条）。

## 问题 3：框选后点功能白屏、刷新回不去
**现象**：框选后点顶部功能按钮直接白屏，刷新也无法回到初始可用态。
**修复**：
- 新增 `ErrorBoundary.tsx`（`CanvasErrorBoundary`，class 组件）包裹 `<Flow/>`；渲染期崩溃时显示「刷新页面 / 返回工作空间」兜底 UI，避免整页卸载成白屏。
- 根因（多选误弹输入栏导致的崩溃路径）已由问题 2 的 `single` 兜底修复消除；ErrorBoundary 为防御性兜底。

## 验证（Playwright 真浏览器）
- 脚本：`verify/verify_three_fixes.py`（复用 `verify_multiselect.py` 登录流程）。
- 关键结果：**问题1几何校验** `edge_start_dx_to_box=0`（线端点精确落在源节点框边）、`edge_start_dx_to_handle=-14`（线端点在悬浮连接点左侧 14px，即连接点浮在框外间隔处）；分别把线拖到目标节点的**右侧、中心、左侧**三个落点，均成功建边且 `targetHandle==='in'`；**缩放回归校验**（`__peaSetZoom` 程序化设 2x / 0.5x）：连接点距框 `gap_a=gap_b=14px`（稳定浮框外）、线端点到框边 `edge_dx=0`（恒连框）；选择框 `pointer-events=none`、`background alpha=0.06`、节点 `opacity=1`；框选期间无输入栏 / 对话框；框选后点「打组」（多选工具条按钮实际文案为「打组」，验证脚本此前误写「打包」为测试选择器 bug，已修正为点击「打组」并断言 `.pea-group-node` 计数 0→1 真正建组）无白屏；刷新后画布回到可用态；无运行时报错。
- **环境提示**：本沙箱 `python -m venv` 无法生成可用 venv，已改为直接 `pip install playwright` 到 managed Python 并 `playwright install chromium`。

## 部署
`npm run build` → `docker cp dist/. pea-server-web-1:/usr/share/nginx/html/` → `docker exec pea-server-web-1 nginx -s reload`（web 宿主机端口 8088）。
