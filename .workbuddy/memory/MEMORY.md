# 项目长期记忆 — pea Creative OS

## 目录约定（重要）
- `D:\workspace\pea\pea-design/` = 产品设计路径（原型 HTML + PRD/ARCH/ROADMAP/DESIGN/TECH）。
- `D:\workspace\pea\pea-server/` = 代码仓库，与 `pea-design/` 平级（勿嵌套）。结构：web/ + services/(bff, generation-orchestrator, shared) + infra/(docker, k8s, mysql)。
- 品牌统一为 **pea**，全仓不得出现 tapnow（2026-07-22 指令）。

## 已锁定技术决策（基线，见 pea-design/ARCH-pea-Final.md）
- 演进式模块化单体；前端 React18+TS+ReactFlow+Zustand+Tailwind+antd v5+Vite；BFF Node NestJS；生成编排 Python FastAPI。
- **主库 MySQL 8**（用户拍板）：JSON 列 + 生成列索引；向量检索后期独立上 Qdrant。
- 生成 = 调外部大模型（LiteLLM 路由+回退），Orchestrator 只编排。Redis 缓存/队列；Docker+K8s；OTel+Prometheus。
- 三重心：生成异步解耦、积分双记账本、画布自动保存。容量 ~10万用户/DAU2万/日生成6k。

## 启动方式
- 根 `C:\workspace\pea\`：`start.sh`(Git Bash)/`start.cmd`(Windows 双击) → `cd pea-server && docker compose up --build`。`./start.sh -d` 后台+开浏览器；`--down`/`--logs`/`--build`。需 Docker Desktop（compose 插件）。
- **Windows .bat/.cmd 坑**：必须纯 ASCII（勿中文 echo/注释）+ CRLF，否则 GBK 拆坏 UTF-8 中文报乱码命令错。`.sh` 在 Git Bash 无碍。
- 快速迭代 web：本地 `npm run build` → `docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/ && docker exec pea-server-web-1 nginx -s reload`。生产仍 `docker compose up -d --build web`。

## 启动排错（已修）
- web 端口：宿主机 8080 被 PID 6992(powershell) 占用 → `docker-compose.yml` web `ports` 改 `8088:80`（注释已留，释放后改回）。
- orchestrator 启动崩溃：`main.py` 原 `parents[3]` 越界 → 改为向上查含 `services/shared` 的 `_ROOT`，并 `sys.path` 加 app 包目录。改完 `docker compose up -d --build generation-orchestrator`。
- compose override 的 `ports` 是**追加**非替换，故直接改基文件而非 override。

## ⚠️ Docker 持久卷 DDL 陷阱（关键，2026-07-24 已根治）
- named volume 启动**不**重跑 `initdb.d/*.sql`；源码 DDL 变更（新枚举/列）不会自动生效 → 运行库与期望 schema 漂移。
- **典型故障**：`ledger_entries.type` 缺 `'grant'` → 注册插 `type='grant'` 开户赠金流水时 500 "internal error"。
- **根治（T-OBS-04 已落地，2026-07-24）**：新增 `infra/mysql/assert-migrated.sh`（幂等自检，等待 MySQL→断言 `ledger_entries.type` 含 `'grant'`→缺失则 `ALTER TABLE ... MODIFY COLUMN type ENUM('grant','preauth','confirm','refund') NOT NULL`），并在 `docker-compose.yml` 加 `dbmigrate` 一次性服务（mysql:8.0 跑脚本后退出），`bff`/`generation-orchestrator` 的 `depends_on` 加 `dbmigrate: condition: service_completed_successfully`。**每次 `docker compose up` 自动自愈**。
- 后续引入 DDL 变更：① 更新 `01-schema.sql`；② 在 `assert-migrated.sh` 追加对应断言；③ 合并人无需再手动 ALTER。

## 设计令牌
- `:root`/`.dark` CSS 变量 + Tailwind 调色板 + antd `ConfigProvider.token` 三方绑定单一源；主色 `#1fa2dc`，深色 `#0a0a0a`，logo `from-pea-purple via-pea-brand to-pea-lime`。改色只动 `web/src/styles/index.css`。

## 真机 E2E 闭环
- `verify/verify_e{5,7,8,9,12}.py` Playwright 跑 `http://localhost:8088`（web 8088，bff 宿主 **4100**），0 console error 为硬标准。
- 改导航/路由须同步更新脚本选择器（E7 用 `e{ts}@pea.ai` 时间戳邮箱；E8 经 `.pea-user-trigger` → "AI Provider 设置"/"账户中心"）。
- 节点 hit-test：选节点用 `.pea-node[data-kind="X"]`；菜单用真实鼠标 `page.mouse.click` 中心坐标（DOM `.click()` 在 React18 被事件代理吞）。

## 画布关键坑（2026-07-23，已验证）
- **选区自管**：ReactFlow 受控节点内部 `.selected` 不持久 → 用 zustand `selectedIds[]`+主 `selectedId`，`PeaNode.selected` 读 `includes(id)`；勿用 `.react-flow__node.selected`/`NodeProps.selected`。
- **Shift 框选**：`panOnDrag={[1,2]}`（右/中键平移，左键框选）；容器 `onMouseDownCapture` 监听 shift+左键，屏幕坐标 `.react-flow__node` 的 `getBoundingClientRect` **相交**判定（非全包含）调 `setSelection`；矩形 `.pea-sel-box`(fixed)。
- **浮动浮层**：`NodeChatPrompt`/`TextNodeToolbar` 必须 `position:fixed`+视口坐标+`requestAnimationFrame` 实时读 `getBoundingClientRect` 重定位，勿放 ReactFlow viewport 内。
- **连接手柄**：默认 `opacity:0` 隐藏，hover/selected 显示；**勿**用 `.react-flow__node:hover .pea-handle`（Tailwind purge 剥离 `:hover`）→ 改用 `PeaNode` 内 `useState` 控 `.hover` 类。全部 Left/Right。
- **AI 聊天**：`AgentPanel` 升到 `Workspace` 层级固定最右 380px；默认只显 `.pea-agent-bubble`，展开为 `.pea-agent-panel`。已删 `Inspector.tsx`。
- **Escape**：`CanvasEditor` 监听 `Escape`→`clearSelection()`，否则手柄常显。
