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

## 产品背景
- 原型 `pea-design/pea-canvas-v12.html` 是 pea Creative OS 高保真原型，含 5 大模块（画布编辑器/电商套图/主页/社区TapTV/账户）+ 全局系统（积分Tapies/AI Provider/分享）。
- **品牌统一为 pea**：所有代码/配置/文档中不得出现 tapnow（2026-07-22 用户指令）。
