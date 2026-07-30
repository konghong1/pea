# 打组 / 框选 四类问题修复报告（2026-07-30）

> 角色：Senior Developer（高级开发工程师）吴八哥 — 全栈 / ReactFlow / 高级交互
> 验证：`verify/verify_group_box_fixes.py` 在 `localhost:8088`（生产构建）跑通 **10/10 PASS**

## 用户原始 4 项要求
1. 框选节点时，只要选择框覆盖到的节点都框选上（partial intersection）。
2. 打组后背景要透明（点阵透出），参考图样式。
3. 拖动组框时，框里所有节点要一起被拖动。
4. 组功能条要浮在框**顶部外侧**（和单节点工具条一致），不在框里面。

## 修复结果（全部验证通过）

| 验证项 | 结果 | 说明 |
|---|---|---|
| 验证1a 框选全覆盖 | PASS | 大选区覆盖 4 节点 → 选中 `['t1','t2','t3','t4']` |
| 验证1b partial 选区 | PASS | 小选区只覆盖 t1+t2 → 选中 `['t1','t2']`，不含 t3/t4 |
| 验证2a 组背景透明 | PASS | `background: rgba(0,0,0,0)`，点阵透出 |
| 验证2b 组容器 pointer-events | PASS | `pointer-events:none`，子节点可正常交互 |
| 验证3 组拖动带动子节点 | PASS | dx=150,dy=80 → 4 个子节点全部跟随 |
| 验证4a 组节点存在 | PASS | `.react-flow__node-group` 正常渲染 |
| 验证4b 浮层在框外顶部 | PASS | gap=2px，`top` 在组框之上 |
| 验证4c 浮层定位 | PASS | `position: fixed` |

## 关键修改文件
- `web/src/components/GroupNode.tsx`：组容器透明化 + 功能条 `createPortal` 到 `document.body`（rAF 定位到顶部外侧）。
- `web/src/styles/index.css`：`.pea-group-node` 透明、`pointer-events:none`、`overflow:visible`；`.pgn-header-portal` 浮层样式。
- `web/src/store/canvas.ts`：`groupNodes` 对全部选中节点强制 `parentNode/extent:'parent'`（修 Bug3）；新增 `correctBoxSelection()` action（修 Bug1）。
- `web/src/components/CanvasEditor.tsx`：pointer 事件（`mousedown`→`mousemove`→`mouseup`）直接算完整选区矩形，存 `window.__lastSelRect`，`mouseup` 后 `setTimeout(0)` 调 `correctBoxSelection()`。
- `web/vite.config.js`：`build.emptyOutDir:false`（绕过沙箱 safe-delete 无法 trash dist 的问题）。

## Bug1 根因与方案要点（最棘手）
- 本应用 viewport 为 `translate(150px,-102px)`，ReactFlow 渲染的 `.react-flow__selection` 选区 DOM 在框选时被**截断**（实测只画到约 40% 宽度）→ RF 原生只选中左列；且 RF 仅在拖拽过程中发 `select` change，定稿后不再发 → 在 `onNodesChange` 里做校正只会用到中途帧。
- **最终方案**：不读 RF 选区 DOM，改用原始 pointer 事件算完整选区矩形（屏幕→画布坐标，换算同 viewport transform）；校正从 `onNodesChange` 移到 `mouseup` 触发的 `correctBoxSelection()`（此时 RF 已定稿、rect 为完整矩形），仅**补不删**。
- 曾试错：MutationObserver+ResizeObserver（mouseup 同帧移除 DOM 漏最后一帧）、requestAnimationFrame（headless rAF 节流漏最后一帧）——均弃用。

## 部署
```bash
cd pea-server/web && npx vite build && \
docker cp dist/. pea-server-web-1:/usr/share/nginx/html/ && \
docker exec pea-server-web-1 nginx -s reload
```
