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
- 兜底：`up.bat` 极简版（仅 `cd /d "%~dp0pea-server"` + `docker compose up --build`），无循环/参数/重定向，确保"把项目直接起来"一定可用。

## 启动排错记录（已修）
- **orchestrator 启动崩溃**：`services/generation-orchestrator/app/main.py` 原 `Path(__file__).resolve().parents[3]` 在容器内（文件位于 `/app/app/main.py`）越界 `IndexError: 3`。已改为向上查找含 `services/shared` 的目录作为 `_ROOT`（容器→`/app`，开发→`pea-server`），同时把 `app` 包所在目录加入 `sys.path`。改完需 `docker compose up -d --build generation-orchestrator` 重建镜像。
- **web 端口 8080 被占**：宿主机 PID 6992（powershell.exe，非本项目容器）长期监听 8080，导致 web 容器 `bind` 失败。临时把 `docker-compose.yml` 里 web `ports` 由 `8080:80` 改为 `8088:80`（行内已注释）。释放 8080 后改回即可。
- compose override 的 `ports` 是**追加**而非替换：写 `docker-compose.override.yml` 加 `web.ports: ["8088:80"]` 会导致 8080+8088 并存、仍撞 8080，故改用直接改基文件。

## 产品背景
- 原型 `pea-design/pea-canvas-v12.html` 是 pea Creative OS 高保真原型，含 5 大模块（画布编辑器/电商套图/主页/社区TapTV/账户）+ 全局系统（积分Tapies/AI Provider/分享）。
- **品牌统一为 pea**：所有代码/配置/文档中不得出现 tapnow（2026-07-22 用户指令）。
