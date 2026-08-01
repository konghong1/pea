# pea Creative OS — 长期记忆（精简）

## ⚠️ 生成文档目录纪律（勿犯）
- **AI 产出的所有报告/概览/验证文档（`*_overview.md`、`*_report.md`、`*_fix.md`、`*_debug_report.md` 等）一律放 `.workbuddy/artifacts/`**，严禁散落在项目根目录。参照：e5-e9 验证报告、overview.md 已在该目录。
- 设计类文档（PRD/ARCH/ADR）归属 `pea-design/`；代码 README 归属 `pea-server/`，不在此列。

## 目录/品牌/技术栈
- `pea-design/`=原型/PRD/ARCH；`pea-server/`=代码（web/ + services/{bff,generation-orchestrator,shared} + infra/），两者平级勿嵌套。品牌统一 **pea**，禁 tapnow。
- 栈：React18+TS+ReactFlow+Zustand+Tailwind+antd v5+Vite；BFF NestJS；编排 Python FastAPI；MySQL8(JSON+生成列)；生成走外部大模型(LiteLLM)。

## 启动/部署
- 根 `start.sh`/`start.cmd` → `cd pea-server && docker compose up --build`；web 宿主端口 **8088**。
- 快速迭代 web：本地 `npm run build` → `docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/ && docker exec pea-server-web-1 nginx -s reload`。
- **⚠️ 验证纪律（勿犯）**：`npm run build` = `tsc -b && vite build`。直连 `vite build` 会绕过 tsc 类型检查给假绿灯（曾漏掉 CanvasEditor 漏 import `useMemo`）。改 TS 后务必跑完整 `npm run build`，或至少 `node_modules/typescript/bin/tsc -b` 先过。
- **⚠️ Python 编排器镜像烤死（勿回退）**：`generation-orchestrator` 容器 `Mounts:[]`，源码无挂载，跑的是构建时烤进的镜像。改 `services/generation-orchestrator/**` 后**必须** `docker compose up -d --build generation-orchestrator` 重建镜像才固化；单纯 `docker restart` 用旧镜像会回退 bug。`docker cp` 只能临时修运行中的容器。镜像 Dockerfile=`infra/docker/orchestrator.Dockerfile`（把 `services/generation-orchestrator/` 拷进 `/app`）。
- **容器内验证语法/方法归属**：`python -c "..."` 多行 + `| head` 会因 SIGPIPE 吞掉输出。改用 `docker cp` 脚本进容器，再 `docker exec ... sh -c "cd /app && PYTHONPATH=/app python /tmp/x.py"`。判断"方法是否真在类里"用 `ast.parse` 后列 `ClassDef.body` 的 `FunctionDef.lineno`（`py_compile` 通过≠方法在类里，游离/嵌套都合法）。
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
- **图片 vs 视频的参考图策略(已重构为 Strategy)**: Agnes **图像**接口(`/v1/images/generations` 的 `extra_body.image[]`)**支持 base64 内联** —— 编排器把内部/相对 URL 经 MinIO 直下转 base64 直接内联,**图片生成根本不经公网**(无需配 PEA_CDN_BASE_URL/隧道); 只有 **视频**接口 `image` 字段只认 http(s) URL(不认 data URI), 才需 `_ensure_http_refs_for_video()` 转存公开 `gen/` 前缀 → CDN URL。参考图解析在 `app/param_adapters.py`: `Base64InlineStrategy`(图片) / `PublicUrlStrategy`(视频), 由各 ImageParamAdapter 声明 `ref_strategy`。
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
- **新增 API 前缀须同步代理白名单**：`infra/docker/nginx.conf` 的 location 正则 与 `web/vite.config.ts` 的 proxy 都需包含该前缀。漏配→该路由落到 SPA 回退返回 index.html，前端当数组用(.map/.some)→整树崩溃白屏且 routePersist 持久化导致刷新复现（案例：`/orders` 漏配致「订阅套餐」页白屏，2026-08-01 修）。列表类接口响应用 `api/client.ts` 的 `asArray()` 归一化兜底。
  - **已重构：`/api` 统一前缀（2026-08-01）**：所有 BFF 接口现在统一以 `/api` 为前缀 —— BFF `main.ts` 注册 `app.setGlobalPrefix('api')`，前端 `api/client.ts` 的 `baseURL='/api'`，nginx 用 `location /api/ { proxy_pass http://bff:4000; }` 一条规则覆盖（**注意：`proxy_pass` 末尾不要带 `/`，否则会剥掉 `/api` 前缀，BFF 找不到路由**）。vite dev proxy 同理：**`/api: { target }` 即可，不要写 `rewrite: (p) => p.replace(/^\/api/, '')`**。前端直接 `fetch()` 调 API 的（如 `NodeChatPrompt.tsx` 的 `/chat/stream`）必须显式写 `/api/...`，绕过 baseURL。以后加新 controller **不用再动 nginx / vite proxy**。

## 画布节点交互（已修复，勿回退）
- `.pea-node` **禁加 transform 过渡**：ReactFlow 拖拽时每帧直接写 `.react-flow__node` 的 `transform: translate3d`，CSS transform 过渡会与之冲突造成拖拽卡顿/抖动（用户误判为“工具栏乱跑”）。hover/选中反馈只用 box-shadow，下沉到 `.pea-node-body-card`。
- 选中态表达：单选靠节点自身 `1.5px` ring(box-shadow) + `@keyframes pea-node-select` ripple 动画；**外层 `.pea-selection-bounds` 仅多选(>=2)才画**（见 `SelectionBoundsBox.tsx`），避免“两个框”。
- 验证脚本：`verify/verify_select_anim_4fixes.py`（Playwright + managed python），10/10 PASS。

## ⚠️ Shift+点击 多选（已修复）
- 现象：Shift+点击 节点得到 `selectedIds=[]`（4 种点击方式均复现）。
- 根因：ReactFlow「受控选中」双重驱动——应用 `onNodeClick` 的 `toggleSelect` 与 `onNodesChange` 响应 ReactFlow 自身 `select` change（`canvas.ts` 的 `hasSelectChanges` 分支）互相覆盖，Shift+点击 时 ReactFlow 的 select change 把 `toggleSelect` 的结果清空。
- 修复（`CanvasEditor.tsx`）：`multiSelectionKeyCode="Shift"` + `selectionKeyCode={null}`（框选仍走 `selectionOnDrag`），且 `onNodeClick` 在 `e.shiftKey` 时直接 `return`（不再调 `toggleSelect`），把 Shift+点击 多选完全交给 ReactFlow 处理并同步到 `selectedIds`。已验证 `selectedIds=['n1','n2']` 且 `.pea-selection-bounds` 出现。

## 连线科技感分层（PeaEdge v2，勿回退）
- **7 层**（共用贝塞尔 d）：①`.pea-edge-halo` ②`.pea-edge-line`(+arrow marker) ③`.pea-edge-flow` ④`.pea-edge-beads` ⑤`.pea-edge-comet` ⑥`.pea-edge-src-pulse` ⑦`.react-flow__edge-interaction`(22px 命中区)。
- `active` = 当前边被选中 或 source/target 节点在 `selectedIds` / `n.dragging=true`；只有 active 才挂 ①③④⑤⑥，空闲只画 ②⑦ → 性能。
- **方向三重保障**：① target 端 chevron 箭头(SVG marker, orient=auto) ② 彗星脉冲(单颗亮粒子全程飞行) ③ 方向渐变(source 淡→target 亮)。
- **方向箭头**：`<marker id=gradId-arrow>` chevron path `M 1 1 L 8 5 L 1 9`，`markerUnits=userSpaceOnUse`，主线 `markerEnd=active?url(#arrow):markerEnd`。
- **彗星脉冲**（⑤）：`pathLength=100` + `dasharray:5 95` + `dashoffset:0→-100`，4px stroke + `drop-shadow(0 0 5px glow)`。归一化是关键——拖动节点时 d 每帧变，CSS dashoffset 不重置不闪烁。
- **数据光点**（④ beads）：`dasharray:2 22` 3px stroke，**无 drop-shadow**（v2 移除模糊→锐利）。辉光感交给彗星层。
- **源点脉冲**（⑥）：`<circle>` + `transform:scale(0.6→3)` + `opacity:0.7→0`，`transform-box:fill-box`。
- **流动虚线**（③ flow）：`dasharray:6 14` 2.5px stroke + `dashoffset:0→-20`。
- 主题令牌 `--pea-edge-idle`/`-hover`/`-active`/`-halo`/`-flow-*`/`-comet`/`-arrow`/`-src-pulse` 在 `:root` / `.dark` 各取不同值。
- 删除芯片 = `<div class="pea-edge-del-anchor">`（仅定位 + counter-scale 内联 transform，**内联样式吃样式表 transform** → hover 缩放必须放内层 `<button class="pea-edge-del">` 上）+ 30×30 SVG：`.pea-edge-del-ring`(扫描环自转) + `.pea-edge-del-hex`(六边玻璃核) + `.pea-edge-del-tick`(HUD 上下刻) + `.pea-edge-del-x`(圆头×)；hover 转琥珀 `--pea-warn`。
- `prefers-reduced-motion`：自动关 flow/beads/comet/src-pulse 动画 + 扫描环；渐变梯度+箭头仍在，方向可读。
