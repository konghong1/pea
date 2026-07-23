# 项目长期记忆 — pea Creative OS

## 目录约定（重要）
- `D:\workspace\pea\pea-design/` = **产品设计路径**：原型 HTML + 全部文档（PRD/ARCH/ROADMAP/DESIGN/TECH 等）。原 `tapnow/` 已于 2026-07-22 全量改名为 `pea-design/`，全项目字符串 tapnow→pea。
- **代码仓库放在 `pea-design/` 的同级目录**：`D:\workspace\pea\pea-server/`（`tapnow-server/` 的同名重品牌）。不要嵌套进 `pea-design/` 内。
- 即：`D:\workspace\pea\{pea-design/, pea-server/}` 平级。代码仓内结构：web/ + services/(bff, generation-orchestrator, shared) + infra/(docker, k8s, mysql/init)。

## 已锁定技术决策（终版基线，见 pea-design/ARCH-pea-Final.md）
- 架构：演进式模块化单体起步，按负载/团队边界抽服务。
- 前端 React18+TS+ReactFlow+Zustand+Tailwind+antd v5+Vite；BFF 用 Node NestJS；生成编排 Python FastAPI。
- **主库 MySQL 8**（用户拍板，非 PostgreSQL）：画布/规划用 JSON 列 + 生成列索引；向量检索后期独立上 Qdrant。
- **生成 = 调用外部大模型**（经 LiteLLM 路由+回退），Orchestrator 只编排不出图。
- 缓存/队列 Redis；媒体 S3+CDN；基建 Docker+K8s(GPU worker 池)+OTel+Prometheus。
- 三重心：生成异步解耦、积分双记账本、画布自动保存。容量基线约 10 万用户 / DAU 2 万 / 日生成 ~6k。

## 启动方式
- 项目根目录 `C:\workspace\pea\` 提供一键启动脚本：`start.sh`(Git Bash/Linux/macOS) 与 `start.cmd`(Windows 双击)。
- 二者均自动 `cd` 到 `pea-server/` 执行 `docker compose up --build` 拉起全栈（MySQL/Redis/MinIO/BFF/Orchestrator/Web）。
- 用法：`./start.sh`(前台) / `./start.sh -d`(后台+自动开浏览器) / `--down` / `--logs` / `--build`。Windows 同理 `start.cmd`。
- 前置：需安装并运行 Docker Desktop（compose 插件）。
- **Windows 批处理坑（已踩）**：`.bat`/`.cmd` 必须 **纯 ASCII（不要中文 echo/注释）+ CRLF 换行**，否则 cmd.exe 按 GBK 解读 UTF-8 中文会拆坏字节、报 `'M'/'o'/'t' 不是内部或外部命令` 这类乱码错。`.sh` 跑在 Git Bash 里 UTF-8 中文无碍。
- **`for /f ('cmd 2^>nul')` 内嵌重定向** 在某些 cmd 版本会报 `此时不应有 .` 解析错；改用 `docker compose ps -q > "%TEMP%\x.tmp" 2>nul` + `for /f %%i in (tmp) do ...` 文件读取式更安全。
- 兜底：`up.bat` 现改为**后台启动即退出**（`cd /d "%~dp0pea-server"` + `docker compose up --build -d`，末尾 ASCII echo 提示 Logs/Stop 命令）。用户明确要求"启动进 docker 就退出、不要一直刷日志"。代价：构建/启动失败不会 tail 报错，需 `docker compose logs -f` 或 `start.cmd --logs` 排查。`start.cmd -d` 等同后台模式且会自动开浏览器。

## 启动排错记录（已修）
- **orchestrator 启动崩溃**：`services/generation-orchestrator/app/main.py` 原 `Path(__file__).resolve().parents[3]` 在容器内（文件位于 `/app/app/main.py`）越界 `IndexError: 3`。已改为向上查找含 `services/shared` 的目录作为 `_ROOT`（容器→`/app`，开发→`pea-server`），同时把 `app` 包所在目录加入 `sys.path`。改完需 `docker compose up -d --build generation-orchestrator` 重建镜像。
- **web 端口 8080 被占**：宿主机 PID 6992（powershell.exe，非本项目容器）长期监听 8080，导致 web 容器 `bind` 失败。临时把 `docker-compose.yml` 里 web `ports` 由 `8080:80` 改为 `8088:80`（行内已注释）。释放 8080 后改回即可。
- compose override 的 `ports` 是**追加**而非替换：写 `docker-compose.override.yml` 加 `web.ports: ["8088:80"]` 会导致 8080+8088 并存、仍撞 8080，故改用直接改基文件。

## 产品背景
- 原型 `pea-design/pea-canvas-v12.html` 是 pea Creative OS 高保真原型，含 5 大模块（画布编辑器/电商套图/主页/社区TapTV/账户）+ 全局系统（积分Tapies/AI Provider/分享）。
- **品牌统一为 pea**：所有代码/配置/文档中不得出现 tapnow（2026-07-22 用户指令）。

## 资深开发二轮沉淀 (2026-07-23)
- **设计令牌**: `:root`/`.dark` CSS 变量 + Tailwind 调色板 + antd `ConfigProvider.token` 三方绑定, 单一源; 主色 `#1fa2dc` 青蓝, 深色 `#0a0a0a`, logo `from-pea-purple via-pea-brand to-pea-lime`。改色只动 `web/src/styles/index.css`。
- **Docker 持久卷 DDL 陷阱**: named volume 启动**不**重跑 `initdb.d/*.sql`; DDL 变更 (新枚举/列) 须 ① 更新 DDL 文件 ② PR 描述写明"对已存在卷执行 X SQL" ③ 合并人手动 ALTER ④ CI 启动 job 加 `assert-migrated.sh` (下期 T-OBS-04)。案例: `ALTER TABLE ledger_entries MODIFY COLUMN type ENUM('grant','preauth','confirm','refund') NOT NULL;` 未执行 → register 500。
- **画布快捷键语义**: Delete 删对象, Backspace 删字符; 不要让 `editing` guard 提前 return 把 Delete 吞了 (`web/src/components/CanvasEditor.tsx` 已分流)。
- **真机 E2E 闭环**: `verify/verify_e{5,7,8,9}.py` Playwright 跑 `http://localhost:8088` (web 8088, bff 宿主 **4100**), 0 console error 为硬标准; 改导航/路由须同步更新脚本选择器 (E7 用 `e7_{ts}@pea.ai` 时间戳邮箱, E8 经 `.pea-user-trigger` → "AI Provider 设置"/"账户中心")。
- **快速迭代 web**: 本地 `npm run build` → `docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/ && docker exec pea-server-web-1 nginx -s reload`, 免全量重建镜像。生产仍 `docker compose up -d --build web`。

## 画布选择模型（关键坑，2026-07-23 四轮）
- **ReactFlow 受控节点的内部选区在本项目不持久**：节点拖拽正常，但点击/框选的 `.selected` 状态不生效（受控 `nodes` 回写把 ReactFlow 内部选区冲掉，且 `onNodesChange` 收不到 select change）。**结论**：画布选区一律用 zustand 自管（`selectedIds: string[]` + 主 `selectedId`），`PeaNode.selected` 读 `selectedIds.includes(id)`；不要用 ReactFlow 的 `.react-flow__node.selected` 或 NodeProps.selected。
- **Shift 框选自管实现**：`panOnDrag={[1,2]}`（右键/中键拖拽平移，左键留给框选），在画布容器 `onMouseDownCapture`/监听 pane 的 shift+左键拖拽，用屏幕坐标 `.react-flow__node` 的 `getBoundingClientRect` 做**相交**判定（非全包含，对齐原型），调 `setSelection(ids)`；矩形用 `.pea-sel-box`(fixed, pointer-events:none)。左键平移被牺牲，改用右键拖拽/滚轮缩放（已在 E12 真机验证）。
- **浮动文本工具条**：选中单个 text 节点时浮现 `.text-node-toolbar`(fixed, `transform:translateX(-50%)` 居中在节点正上方)，用 `useViewport()` 跟随平移缩放重定位；按钮 `onMouseDown` 须 `preventDefault` 保住可编辑区焦点，再用 `document.execCommand('formatBlock'/'bold'/..., value)` 作用于 `.pea-node-text-edit`(contentEditable + `nodrag`)，并写回 `store.html`。`execCommand('bold')` 必须非折叠选区（Playwright 用 `Range.selectNodeContents` 而非 triple-click 才稳）。
- **右击"添加并连接"**：`canvas.addConnected(fromId)` 在源节点右侧 +30px 新建 generate 节点并用默认 handle 边连接（store 内 `addEdge` 等价：`{id, source, target}`），上下文菜单顺序对齐原型：复制节点 / ➕ 添加并连接 / 🗑 删除节点。
- 真机验证 `verify/verify_e12.py`（浮动工具条 H1-H3/B/I、Shift 框选、添加并连接）全绿 0 console error；E5/E11 回归全绿。

## 画布 UI 重设计（2026-07-23 六轮）
- **左侧工具栏紧凑化**：去掉 `.pea-toolbar` 的 `bottom:60px`，`.pea-toolbar-bottom` 改 `margin-top:8px`，头像紧挨功能按钮。
- **节点连接手柄默认隐藏**：Handle 加 `className="pea-handle"`；CSS 默认 `opacity:0`+透明背景/边框，hover/selected 时显示。**不要**用 `.react-flow__node:hover .pea-handle`，Tailwind purge 会剥离生产构建中的 `:hover` 选择器；改用 `PeaNode` 内 `useState`+`onMouseEnter/onMouseLeave` 控制 `.hover` 类。
- **AI 聊天独立为右下角气泡 + 右侧固定侧边栏**：`AgentPanel` 重写，默认 `open:false` 只显示 `.pea-agent-bubble`（52px 深色圆形图标）；展开为 `.pea-agent-panel`（right:0, width:380px, 全高固定侧边栏），对齐参考图。
- **添加节点菜单（AddNodeMenu）**：双击空白处或点工具栏 ➕ 弹出 `.pea-add-menu`（深色 300px 圆角面板）：三段分组「添加节点 / 辅助工具 / 添加资源」，菜单项含图标+标题+副标题+蓝点（dot）+ Beta 标签；hover 高亮。菜单位置记录双击点坐标。`libOpen:boolean` 已废弃，改用 `libAt:{x,y}|null`。菜单组件用了 `<div fixed inset-0 z-40 onClick=onClose>` 背景遮罩 + `<div pea-add-menu>` 兄弟，**Playwright 测试时记得用真实鼠标点击（page.mouse.click 中心坐标），DOM `.click()` 在 React 18 会被事件代理吞掉**。
- **画布节点 4 类视觉（PeaNode v3）**：
  - text：顶部"≡ Text"小标签 + contentEditable 方框（占位"双击开始编辑…"）
  - image/video/audio：顶部圆形"↑ 上传"按钮 + 左上 kind 标签（🖼 Image / ▷ Video / ♫ Audio）+ SVG 媒体占位
  - **连接手柄全部改 Left/Right**（之前是 Top/Bottom，对齐截图2 ⊕）
  - upload 走 objectURL 预览（真实链路预签名直传后续接）
- **节点下方全宽输入栏（NodeChatPrompt → node-input-bar）**：
  - 宽度 = 节点宽度（用 getBoundingClientRect 取），不再居中浮动
  - 顶部工具行：text/audio 一个 +；image/video 多一个 ✦（特效）
  - 中部 textarea 按类型切换占位
  - 底部状态行：左侧模型+参数（KIND_CFG 字典配置：text=Gemini / image=Seedream+1:1·2K / video=Seedance+全能参考16:9·480p·5s / audio=Mureka+音乐+自适应）；右侧 🎤/1×(text/image/video)/Tapies/↑
  - Tapies 数字：text 显示「1」，其他显示「-」（占位）
  - audio 类型不显示 ✦ 和 1×
- **Playwright 节点 hit-test 坑**：`.pea-node` 选中目标会被 `.pea-node-body-card` 子元素拦截 click，需要 `.first.click(force=True)` 或直接点 body-card 中心；ReactFlow 的 `.react-flow__node` 外层不带 data-kind，选节点用 `.pea-node[data-kind="X"]`。
- **添加节点位置**：add 函数用 `libAt` 屏幕坐标 → `screenToFlowPosition` 转画布坐标，避免节点叠在一起。**v2 升级**：`AgentPanel` 移出 `CanvasEditor` 升到 `Workspace` 层级，使其固定在最右 380px（不再被画布容器裁切），同时**删除 `Inspector.tsx` 引用**——"选中一个节点以查看 / 编辑属性" 占位彻底没了。**新增 `NodeChatPrompt` 组件**：选中单个节点（取 `selectedId` 而非 `selectedIds.length===1`，因为 `addNode` 只写 `selectedId`）时在节点正下方水平居中浮现紧凑输入框，提交后向 `useAgent.push` 推用户消息并 `setOpen(true)` 自动展开聊天面板；若是 generate 节点，提示词同时回写到 `node.prompt`。随 `useViewport()` 跟随平移缩放重定位。
- **移除画布底部 Composer**：旧 `<Composer>` 输入条删除；同时移除 `<MiniMap />`，避免与右下角气泡重叠形成白色面板。
- **Escape 清空选区**：`CanvasEditor` 监听 `Escape` 调用 `clearSelection()`，否则按 Escape 无法取消节点选中、手柄始终显示。
- 验证脚本：`verify/verify_ui_redesign.py`（v1 基础）/`verify/verify_ui_redesign_v2.py`（含 NodeChatPrompt 场景），均 0 console error；v2 关键断言：panel 右边距 0px、宽 380px、chat-prompt top>node bottom 且水平居中、Escape 后 chat-prompt 自动隐藏。

## 画布固定浮层与自定义控件（2026-07-23 八轮）
- **节点缩放不能影响弹出的输入框/工具条**：`NodeChatPrompt`/`TextNodeToolbar` 必须用 `position: fixed` + 视口坐标，并用 `requestAnimationFrame` 实时读取节点 `getBoundingClientRect()` 重定位；不能放在 ReactFlow viewport 内部或用 `position: absolute` 依赖父容器。
- **自定义 ReactFlow 控件不要嵌套 `<Background>` 或 `<MiniMap>`**：自定义控件组件若直接返回 `<Background>`，ReactFlow 会把它放进该控件的 panel 容器，导致背景只覆盖控件区域并遮住控件本身。应让 `Background`/`MiniMap` 作为 `<ReactFlow>` 的直接子元素，控件只负责渲染按钮/滑块。
- **连线空放创建节点**：用 `onConnectStart` 记录源节点，`onConnect` 成功时清空记录；`onConnectEnd` 若记录仍在说明未命中目标，弹出节点选择菜单创建新节点并连边，避免节点"消失"的错觉。
