# 项目长期记忆 — pea Creative OS（精简版）

## 目录与基线
- `pea-design/`=产品原型/PRD/ARCH；`pea-server/`=代码（web/ + services/{bff,generation-orchestrator,shared} + infra/）。两者平级，勿嵌套。品牌统一 **pea**，禁 tapnow。
- 技术栈：React18+TS+ReactFlow+Zustand+Tailwind+antd v5+Vite；BFF NestJS；编排 Python FastAPI；主库 MySQL8(JSON列+生成列)；生成走外部大模型(LiteLLM)。三重心：生成异步解耦/积分双记账本/画布自动保存。

## 启动与排错
- 根目录 `start.sh`/`start.cmd` → `cd pea-server && docker compose up --build`。web 宿主端口 **8088**(原 8080 被占，留注释)。
- 快速迭代 web：本地 `npm run build` → `docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/ && docker exec pea-server-web-1 nginx -s reload`；生产改仍 `docker compose up -d --build web`。
- **Windows .bat/.cmd 必须纯 ASCII + CRLF**，否则 GBK 拆坏 UTF-8 中文乱码。

## ⚠️ 出网/代理三大陷阱（2026-07-29 定案，勿回退）
- `PEA_PROXY_FIX` 服务器无本地代理必须=0；`PEA_AI_GATEWAY` 默认**空**（不兜底）。严禁再把 `host.docker.internal:33210` 写成任何默认值——那是开发机专属代理，服务器上会把真实错误掩盖成 `ECONNREFUSED 172.17.0.1:33210`。
- 死代理防护已双端落地：bff `bootstrap-proxy.ts`（探测失败→**清 HTTP(S)_PROXY env**，axios 才获救）+ orchestrator `main.py:_ensure_proxy_strategy()`。
- `dns-override.yml` 的 extra_hosts IP 必须用 **DoH**（dns.google/cloudflare）验证；境内 UDP DNS（含 223.5.5.5）对 apihub.agnes-ai.com 会被抢答假 IP。当前真实 IP=Cloudflare 104.18.18.62/104.18.19.62。
- 部署前先在服务器跑 `pea-server/check-egress.sh` 判定直连/需代理，按结论配 .env。

## ⚠️ Docker 持久卷 DDL 陷阱（关键）
- named volume 启动不重跑 `initdb.d/*.sql`，源码 DDL 变更不自动生效 → schema 漂移。
- 根治(T-OBS-04)：`infra/mysql/assert-migrated.sh` 幂等自检 + `dbmigrate` 一次性服务，`bff`/`orchestrator` 的 `depends_on` 加 `condition: service_completed_successfully`。**新 DDL：① 改 `01-schema.sql` ② 在脚本追加断言**。

## ⚠️ 协作红线（2026-07-27 用户明确）
- 验证脚本因「选择器错/路径错/token key 错」失败 → **只修脚本**，严禁为跑通验证去偷偷改无关实现代码。
- 验证常见坑：① 注册先点「没有账号？去注册」，昵称框 `input[placeholder="可选"]` 才出现；② token=`localStorage['pea_token']`（非 `'token'`）；③ 建画布走 `/canvases`（**无 `/api` 前缀**）；④ dev(5174) 别用 `wait_until="networkidle"`，用 `domcontentloaded`+`wait_for_selector`。
- 生产 E2E 注入式测试须先 `localStorage.__peaDevHooks='1'` 并刷新（`CanvasEditor` 仅 DEV 或该 flag 时暴露 `window.__canvas`/`window.__ui`）。

## 节点媒体按钮约定（勿擅自改）
- 收藏星标：仅 AI 生成图(`resultUrl/resultUrls` 存在)显示；上传图不显示。
- 替换按钮：仅用户上传图(`!isGenerated`)有；AI 生成图不要替换。
- 保存到素材库：仅 AI 图。多图有角标+抽屉。

## ⚠️ 参考图 URL 约定（关键，2026-07-27 晚确认）
- 参考图要发给**外部模型**(Agnes)，必须是模型可下载的真实地址（`http(s):` 或 `data:`）。
- 上传图存的是 `fileKey`，前端 `getFileUrl` 返回的是 **`blob:` 地址**（仅浏览器内 `<img>` 显示用），**绝不能**当作参考图 URL 发给后端——编排器 `param_adapters._normalize_refs` 会静默丢弃 `blob:`/`相对` 路径，导致"参考图没上传"。
- 正确做法：上传图作参考图时用 `getPresignedUrl(fileKey)`（调 `GET /files/url?key=`，返回 1h 有效真实可外传签名 URL）。`NodePromptInput.resolveNodeMediaUrl` 与 `NodeChatPrompt.resolveUpstreamMediaUrl` 已优先走 presigned。
- 多图提示词编排：在 `NodeChatPrompt.submit()` 用 `buildReferenceBlock()` 把参考图按上传顺序编号 + 角色（主体/风格背景）+ 文件名为一段【参考图 N】说明，拼到 prompt 最前，降低模型混淆；编号顺序须与 `reference_images` 数组一致。
- 线上验证参考图是否真上传：查 orchestrator worker 日志 `[adapter] agnes image refs=N ...` 与 `[agnes] image ... payload=...` 是否含 `extra_body.image`。
- 模型能力限制：Agnes 2.1 Flash `extra_body.image` 是"风格/内容参考"，非像素级复刻；"一模一样"需求靠 prompt 强化不保证 100%，真要像素级一致需 img2img/inpainting 路径（未做）。

## 画布关键坑
- 选区自管：用 zustand `selectedIds[]`+`selectedId`，`PeaNode.selected` 读 `includes(id)`；勿用 `.react-flow__node.selected`。
- Shift 框选：`panOnDrag={[1,2]}`；浮动浮层(`NodeChatPrompt`/`TextNodeToolbar`)必须 `position:fixed`+rAF 读 `getBoundingClientRect` 重定位。
- 连接手柄：用 `PeaNode` 内 `useState` 控 `.hover` 类，勿用 `.react-flow__node:hover .pea-handle`(Tailwind purge 剥离)。
- 节点点击命中：菜单/选择用真实鼠标 `page.mouse.click` 中心坐标（DOM `.click()` 被 React 事件代理吞）。
- `window.__canvas`：注入节点=`loadGraph(nodes,edges,version)`+`select(id)`；注入边=`onConnect({source,target})`（非 `addEdge`）。

## 视图模型（三态路由）
- `useUi().active`：`home`(占位)/`workspace`(项目列表)/`canvas`(画布，隐藏 TopNav，头部下拉返回)。`PageKey` 须含 `'workspace'`；画布回项目列表走头部下拉，勿用 TopNav「工作空间」。

## Bug 修复记录（2026-07-27）
- **文本节点拖动失效**（深层原因）：contentEditable 在 mousedown 时自动获得焦点（browser default），这会导致 ReactFlow 的 drag handler 不识别这次 mousedown 为有效 node drag 起点（目标被视为 input-like 元素）。同时外层 downXY 也无法记录坐标。解决方案：在 `PeaNode.tsx` text edit div 的 onMouseDown 中，编辑态下 `stopPropagation()` 防止触发拖动；非编辑态下 `e.preventDefault()` 阻止浏览器自动聚焦 contentEditable，但**不阻止事件冒泡**，使 ReactFlow 和外层节点都能接收事件。双击进入编辑态后锁定，避免误拖。
- **编辑框（输入栏）闪烁消失**：点击选中节点时，NodeChatPrompt 下方的输入栏会瞬间消失后重现。原因是在 render 阶段通过 DOM 查询 `.pea-node-editor-anchor`，React 更新期间新选中的节点锚点尚未挂载，查询返回 null 导致组件 unmount。解决方案：改用 `useRef` + `useEffect` 缓存 anchorElement，只在 single 变化时重新查询，渲染阶段直接使用缓存值避免中途返回 null。
- **节点 Hover 光标异常显示箭头/I-beam**：文本区域显示 I 型光标而非预期的抓手光标。方案：在 CSS 中添加 `.pea-node * { cursor: inherit !important; }` 强制所有子元素继承节点的 grab 光标；编辑态特殊保留 `.pea-node-text-edit.is-editing { cursor: text }` 以维持文本编辑体验。
- **节点悬停视觉反馈增强**：添加 `.pea-node:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.1); transition: transform 0.15s ease, box-shadow 0.15s ease; }` 带来轻微上浮磁吸效果，提升交互质感。
- **编辑框不渲染（anchorEl 时序）**：`NodeChatPrompt` 用 `useRef`+`useEffect([single])` 缓存 anchor，effect 赋值不触发重渲染 + 仅在 single 变化时跑一次。首次选中时锚点 DOM 未挂载→查到 null → single 不再变 → 永远不渲染。**修复**：改为每次渲染同步 `querySelector` + `useState` 触发重渲染；切换节点时保留旧 anchor 防闪烁。
- **@ picker 缩略图黑方块**：上传图节点（仅 fileKey）在 `resolveNodeMediaUrl` 中 `getPresignedUrl`/`getFileUrl` 双失败 → 返回 undefined → `<img src="">` + CSS `background:#000` = 黑方块。**修复**：① blob: URL 检测跳过（防 DB 持久化的失效 blob URL 提前返回）；② 失败时 console.warn；③ picker 渲染降级为 🖼️ 图标（`.pea-ref-picker-thumb-fallback`）替代黑方块。
- **Docker 构建缓存陷阱**：Windows Git Bash 下 `docker compose up -d --build web` 可能用缓存层导致源码修改未入镜像。可靠部署方式：本地 `NODE_OPTIONS="--use-system-ca" npm run build` + `docker cp web/dist/. container:/usr/share/nginx/html/` + `docker exec container nginx -s reload`。
