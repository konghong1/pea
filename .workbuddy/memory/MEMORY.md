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
- 发外部模型(Agnes)须真实可下载地址。**禁止**把 `getFileUrl` 的 `blob:` 当参考图(编排器会丢弃)。上传图作参考图用 `getPresignedUrl(fileKey)`。多图用 `buildReferenceBlock()` 按序编号拼到 prompt 前。

## 画布关键坑
- 选区自管：zustand `selectedIds`/`selectedId`，勿用 `.react-flow__node.selected`。
- `ConnectionMode.Loose` 入边 `onConnect` 强制 `targetHandle='in'`(左侧固定)。
- 连线端点恒定回退 `gap=HANDLE_GAP+HANDLE_HALF`，**绝不除 zoom/读 useStore**；`.pea-handle` 须 `transform-origin:center center !important` + `pointer-events:all !important`。
- 组：`groupNodes` padding 已收紧(16→0 严格包裹)；`moveNodeToGroup` 只更新 parentNode/childrenIds+坐标转换，不再重算 group 尺寸。删 group 须同步清理 `parentNode===id` 子节点防白屏。

## 视图模型
- `useUi().active`：home/workspace/canvas(隐藏TopNav)。画布回项目列表走头部下拉，勿用 TopNav「工作空间」。

## 易复发 Bug
- 文本节点拖动失效：编辑态 `stopPropagation`；非编辑态 `e.preventDefault()`(保冒泡)防 contentEditable 自动聚焦吞 mousedown。
- 组节点删除必须批量清子节点（见上，否则白屏）。
