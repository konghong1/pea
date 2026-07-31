# 画布连线科技感改造 · 总览

## 背景
画布连线存在三个体验问题：删除按钮是丑陋的红圆×、连线本身偏亮抢视线、看不出方向。
本轮按"科技感 + 适配背景 + 流动方向"重做整套连线和它的删除控件。

## 改造
- **连线分层（PeaEdge）**：halo 辉光 / line 主线 / flow 方向虚线 / comet 彗星光点 / interaction 命中区，共用一条贝塞尔 `d`。
- **自适应背景**：新增 `--pea-edge-idle/active/halo/comet/chip-*` 令牌，亮色 `#f4f4f7` 与暗色 `#0a0a0a` 下各取不同 alpha + blur；空闲态 alpha 0.26~0.34 + `filter: blur(0.45~0.5px)`，低对比融入背景。
- **方向感**：①线性渐变 `userSpaceOnUse`，x1/y1=source 端淡、x2/y2=target 端亮（静态可读）；②`stroke-dasharray:5 11 + dashoffset 0→-16` 一个周期无缝流动；③彗星 `pathLength=100` 归一化 + `dasharray:0.6 99.4 + dashoffset 0→-100`，归一化是关键——拖动时 d 每帧变化，CSS dashoffset 不重置时间线，SMIL `animateMotion` 会闪烁。
- **active 触发条件**：本边被选中 / source/target 在 `selectedIds` / 端点节点 `dragging=true`。空闲态不渲染 halo/flow/comet（性能）。
- **HUD 断开芯片**（替代红圆×）：30×30 SVG，扫描环自转 + 六边玻璃核心 + 上下 HUD 刻线 + 圆头 ×；hover 转琥珀色警示"即将断开"；扫描环加速；`:focus-visible` 显式焦点环；counter-scale 保持屏幕恒定尺寸。
- **a11y**：`prefers-reduced-motion` 自动关掉全部动画（渐变梯度仍在，方向可读）；`title`/ `aria-label` 描述"断开连接"。

## 关键决策
- 删除按钮不能用同一元素同时承担"内联 transform 定位"和"hover scale"——内联 transform 永远赢。把定位+counter-scale 拆到外层 `.pea-edge-del-anchor` 的 `style.transform`，hover 缩放交给内层 `<button class="pea-edge-del">`。
- 彗星动画坚决用 `pathLength=100` 归一化 + CSS dashoffset，不走 SMIL；ReactFlow 拖拽过程中 path d 每帧变化，SMIL 时间线会重置。

## 修改文件
- `pea-server/web/src/components/PeaEdge.tsx`
- `pea-server/web/src/styles/index.css`

## 验证
- `verify/verify_edge_scifi.py`（Playwright + managed python）：**22/22 PASS**，0 console error。
- 覆盖：空闲透明度+blur、选中节点→相连边 active、拖动节点→两侧相连边均 active、选中边→HUD 结构完整、点击芯片真删边、取消选择回落空闲、明/暗主题切换。
- 截图：`verify/shots/edge_01_idle.png` … `chip_05_dark_zoom.png`（含 2x DPR 镜头裁切看 HUD 细节）。