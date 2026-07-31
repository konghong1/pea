# pea Creative OS — 长期记忆（精简）

## 目录/品牌/技术栈
- `pea-design/`=原型/PRD/ARCH；`pea-server/`=代码（web/ + services/{bff,generation-orchestrator,shared} + infra/），两者平级勿嵌套。品牌统一 **pea**，禁 tapnow。
- 栈：React18+TS+ReactFlow+Zustand+Tailwind+antd v5+Vite；BFF NestJS；编排 Python FastAPI；MySQL8(JSON+生成列)；生成走外部大模型(LiteLLM)。

## 启动/部署
- 根 `start.sh`/`start.cmd` → `cd pea-server && docker compose up --build`；web 宿主端口 **8088**。
- 快速迭代 web：本地 `npm run build` → `docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/ && docker exec pea-server-web-1 nginx -s reload`。
- Windows .bat/.cmd 必须纯 ASCII+CRLF，否则 GBK 拆坏 UTF-8。

## ⚠️ 出网/代理（勿回退）
- 服务器 `.env` 设 `PEA_PROXY_FIX=0` 即直连（bff/orchestrator/agnes 已 `trust_env=False`/`proxies=None` 直连 apihub）。
- 要代理：`PEA_PROXY_FIX=1` + `PEA_EGRESS_PROXY=http://host.docker.internal:<port>`，代理须监听 `0.0.0.0` 且真实出境；**严禁**用死代理 `host.docker.internal:33210`（开发沙箱专属，服务器上 ECONNREFUSED）。

## ⚠️ Docker 持久卷 DDL 陷阱
- named volume 不重跑 `initdb.d/*.sql` → schema 漂移。新 DDL：① 改 `01-schema.sql` ② 在 `infra/mysql/assert-migrated.sh` 追加断言；`dbmigrate` 一次性服务 + `depends_on: service_completed_successfully`。

## 节点 Chrome 分层缩放（勿回退）
- `.pea-node-chrome`(外层,纯flow,**禁 transform:scale**)承载 NodeBadge(等比缩放)；`.pea-node-chrome-fixed`(内层,abs+counter-scale)承载交互控件(屏幕恒定)。缩放源 `--pea-node-inv-zoom`。

## ⚠️ 协作红线
- 验证脚本因选择器/路径/token 错失败 → **只修脚本**，严禁为跑通验证改无关实现。E2E 注入须先 `localStorage.__peaDevHooks='1'`（`CanvasEditor` 仅 DEV/该flag 暴露 `window.__canvas`/`window.__ui`）。token=`localStorage['pea_token']`；建画布走 `/canvases`(无/api)。

## 节点媒体按钮约定
- 星标仅AI图(`resultUrl`存在)；替换仅上传图(`!isGenerated`)；存素材库仅AI图。

## ⚠️ 参考图 URL 约定（关键）
- 发外部模型(Agnes)须真实可下载地址。**禁止**把 `getFileUrl` 的 `blob:` 当参考图(编排器会丢弃)。**禁止**把相对路径 `/media/...` 当参考图（同样被丢弃）。上传图/AI生成图作参考图用 `getPresignedUrl(fileKey)`。前端 `resolveUpstreamMediaUrl`/`resolveNodeMediaUrl`/`getParsed()` 均须校验 `startsWith('http')`。多图用 `buildReferenceBlock()` 按序编号拼到 prompt 前。
- **视频参考图特殊**：Agnes 视频 API 的 `image` 字段只接受 http(s) URL（**不认 data URI**，图片接口的 `extra_body.image[]` 可以）。编排器 `_ensure_http_refs_for_video()` 将 data URI 转存到公开 `gen/` 前缀 → CDN URL。**生产必须设 `PEA_CDN_BASE_URL` 为公网可达地址**（localhost 对外部模型不可达）。
  ⚠️ **`PEA_CDN_BASE_URL` 绝不可用私网 IP/域名**（如 `192.168.x.x`、`10.x`、`127.x`、`localhost`、相对路径 `/media`）——外部模型(Agnes)在公网，路由不到你们内网。用户机器在 192.168.31.x 家庭/办公局域网，此地址对 Agnes 不可达。
  ✅ **本地联调方案**：用 `ngrok`/`cloudflared tunnel`/`frp` 把本机 8088 暴露到公网临时域名，再把 `PEA_CDN_BASE_URL` 设成该临时域名；生产则填真实公网域名或云存储(COS/OSS/S3)公开桶。

## 画布关键坑
- 选区自管：zustand `selectedIds`/`selectedId`，勿用 `.react-flow__node.selected`。
- `ConnectionMode.Loose` 入边 `onConnect` 强制 `targetHandle='in'`(左侧固定)。
- 连线端点恒定回退 `gap=HANDLE_GAP+HANDLE_HALF`，**绝不除 zoom/读 useStore**；`.pea-handle` 须 `transform-origin:center center !important` + `pointer-events:all !important`。
- 组：`groupNodes` padding 已收紧(16→0 严格包裹)；`moveNodeToGroup` 只更新 parentNode/childrenIds+坐标转换，不再重算 group 尺寸。删 group 须同步清理 `parentNode===id` 子节点防白屏。
- **组布局 `reLayoutGroup`**：单元格尺寸取子节点实测 width/height 最大值（勿写死 220/180）；fallback 默认 **340/340**（对齐 CSS `.pea-node { width:340px }`）；宫格列数 `Math.ceil(sqrt(n))` 封顶4列（勿用 `min(3,n)`，否则≤3节点=单行=水平无区别）；**GAP=32, PAD=24**（间距舒适）。

## 视图模型
- `useUi().active`：home/workspace/canvas(隐藏TopNav)。画布回项目列表走头部下拉，勿用 TopNav「工作空间」。

## 易复发 Bug
- 文本节点拖动失效：编辑态 `stopPropagation`；非编辑态 `e.preventDefault()`(保冒泡)防 contentEditable 自动聚焦吞 mousedown。
- 组节点删除必须批量清子节点（见上，否则白屏）。

## 画布节点交互（已修复，勿回退）
- `.pea-node` **禁加 transform 过渡**：ReactFlow 拖拽时每帧直接写 `.react-flow__node` 的 `transform: translate3d`，CSS transform 过渡会与之冲突造成拖拽卡顿/抖动（用户误判为“工具栏乱跑”）。hover/选中反馈只用 box-shadow，下沉到 `.pea-node-body-card`。
- 选中态表达：单选靠节点自身 `1.5px` ring(box-shadow) + `@keyframes pea-node-select` ripple 动画；**外层 `.pea-selection-bounds` 仅多选(>=2)才画**（见 `SelectionBoundsBox.tsx`），避免“两个框”。
- 验证脚本：`verify/verify_select_anim_4fixes.py`（Playwright + managed python），10/10 PASS。

## ⚠️ Shift+点击 多选（已修复）
- 现象：Shift+点击 节点得到 `selectedIds=[]`（4 种点击方式均复现）。
- 根因：ReactFlow「受控选中」双重驱动——应用 `onNodeClick` 的 `toggleSelect` 与 `onNodesChange` 响应 ReactFlow 自身 `select` change（`canvas.ts` 的 `hasSelectChanges` 分支）互相覆盖，Shift+点击 时 ReactFlow 的 select change 把 `toggleSelect` 的结果清空。
- 修复（`CanvasEditor.tsx`）：`multiSelectionKeyCode="Shift"` + `selectionKeyCode={null}`（框选仍走 `selectionOnDrag`），且 `onNodeClick` 在 `e.shiftKey` 时直接 `return`（不再调 `toggleSelect`），把 Shift+点击 多选完全交给 ReactFlow 处理并同步到 `selectedIds`。已验证 `selectedIds=['n1','n2']` 且 `.pea-selection-bounds` 出现。

## 连线科技感分层（PeaEdge，勿回退）
- 分层 SVG path 全部共用贝塞尔 d：①`.pea-edge-halo` ②`.pea-edge-line` ③`.pea-edge-flow` ④`.pea-edge-comet` ⑤`.react-flow__edge-interaction`(22px 命中区)。
- `active` = 当前边被选中 或 source/target 节点在 `selectedIds` / `n.dragging=true`；只有 active 才挂 ①③④，空闲只画 ②⑤ → 性能。
- **方向性**：方向渐变 `linearGradient gradientUnits="userSpaceOnUse"` `x1=sX,y1=sY`（source 端淡）→ `x2=tX,y2=tY`（target 端亮）。渐变 ID = `pea-edge-grad-${id}`，随边 ID 唯一化。
- **流动**：`stroke-dasharray:5 11` + 动画 `stroke-dashoffset:0→-16`（=一个 dasharray 周期，无缝）；**彗星**：`pathLength=100` 归一化 + `dasharray:0.6 99.4` + `dashoffset:0→-100`。归一化是关键——拖动节点时 d 每帧变，SMIL `animateMotion` 会重置时间线闪烁，CSS dashoffset 不会。
- 命中区需透明 path + `strokeWidth=22` + 透明度命中。
- 主题令牌 `--pea-edge-idle`/`-hover`/`-active`/`-halo`/`-flow-*`/`-comet` 在 `:root` / `.dark` 各取不同值；空闲色背景 alpha 0.26~0.34 浮起融入。
- 删除芯片 = `<div class="pea-edge-del-anchor">`（仅定位 + counter-scale 内联 transform，**内联样式吃样式表 transform** → hover 缩放必须放内层 `<button class="pea-edge-del">` 上）+ 30×30 SVG：`.pea-edge-del-ring`(扫描环自转) + `.pea-edge-del-hex`(六边玻璃核) + `.pea-edge-del-tick`(HUD 上下刻) + `.pea-edge-del-x`(圆头×)；hover 转琥珀 `--pea-warn`。
- `prefers-reduced-motion`：自动关 flow/comet 动画 + 扫描环；渐变梯度仍在，方向可读。
- 验证脚本：`verify/verify_edge_scifi.py`（22/22 PASS）。
