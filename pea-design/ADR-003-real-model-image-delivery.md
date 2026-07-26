# ADR-003: 节点图片/视频调用真实模型 + 结果可靠送达

## Status
Accepted — 取代 ADR-002 的默认开启 Mock 路径（`PEA_FORCE_MOCK_TYPES` 已从 docker-compose 移除，默认走真实模型）

## Context
用户明确 reject 了 ADR-002 的 Mock 占位方案：

> "我让你调用模型生成图片，不是让你随便生成一张图。我是让你调用模型生成图片。排查下为啥生成不出图片。很久都不会出图。"

要求节点图片/视频**必须调用真实 Agnes 模型**，且真实成图必须**真正显示出来**。

排查"真实模型不出图"的三处根因：

1. **MinIO 转存挂死 + 裂图**：原 `agnes_provider.py` 把生成结果 re-host 到 MinIO（`minio:9000`，bucket `pea-media`）。`minio-py 7.2.11` 客户端在每次操作（`bucket_exists` / `put_object` / `set_bucket_policy`）都会挂死——即便裸 TCP 可达、health 返回 200，`gen/` 公开读策略的线程也静默未生效 → 即便上传成功也会 403 裂图。前端拿到的是不可加载的 URL。
2. **Agnes 瞬时 503 直接判失败**：`allow_mock_fallback=false`，worker 在 ~174s 后收到 HTTP 503 "Service busy" 直接标记 `FAILED`，不出图。Agnes 负载波动大，503 属瞬时故障，不应直接放弃。
3. **WS 事件丢失（最隐蔽）**：后端其实已正确产生 `done` + 真实 CDN URL，但 BFF→前端的 `job.updated` 是 Redis pub/sub **fire-and-forget**。Mock "能显示"只是因为 0.5s 就完成、事件必然命中监听；真实任务常 ~1–3 分钟，事件到达时前端 WS 已不在监听窗口 → `resultUrl` 永不回填，节点永远停在 `generating`。

## Decision
三处根因分别修复，互不耦合：

1. **直接透传提供商公网 CDN URL（绕过 MinIO）**：`agnes_provider._generate_image` / `_generate_video` 直接返回 Agnes 返回的公网 CDN URL（`https://platform-outputs.agnes-ai.space/...`），浏览器直显，不再经 MinIO 转存。作为防御，`storage.py` 给 MinIO 客户端加上 `urllib3.Timeout(connect=10, read=60)` + 重试，避免任何残留调用挂死 worker。
2. **对瞬时 5xx/超时加重试**：新增 `_post_with_retry(url, payload, headers, timeout, max_attempts=2, backoff_base=4)`，在 `requests.Timeout` / `ConnectionError` 与 HTTP 429/500/502/503 上指数退避（上限 20s）；每次尝试 read timeout 封顶 110s，快速失败而非挂 170s。已接入 image 提交、video 提交、text 调用三处。
3. **前端轮询兜底（事件 + 轮询双通道）**：`NodeChatPrompt` 在 `registerJob` 后启动 `pollNodeJobResult(jobId)`，每 3s 调 `GET /generation/jobs/:jobId`，`done` 则 `applyJobResult({ generating:false, resultUrl })`。事件先到会从 `jobNodeMap` 移除 job，轮询随即终止——**事件保速度、轮询保可靠，二者不重复回填**。

同时 `docker-compose.yml` 移除 `PEA_FORCE_MOCK_TYPES: "image,video"`（默认走真实模型）。

## Consequences
- 易：节点图片/视频调用真实 Agnes 模型，成图真实显示（CDN URL 直显），不再占位 SVG / 裂图。
- 易（可靠性）：即使 WS 事件丢失，轮询兜底保证 ~1–3 分钟的长任务结果仍回填节点。
- 易（韧性）：Agnes 瞬时 503/超时自动重试，大幅降低偶发 `FAILED`。
- 代价：真实出图耗时由模型决定（Agnes flash 实测 30–190s 波动），**无法压到 1–3s**——这是物理上限。已与用户对齐"要真实模型就不要 1–3s 假图"。
- 代价（可逆性）：`PEA_FORCE_MOCK_TYPES` 开关代码仍在 `config.py` / `llm_router.py`，如仍要联调占位图可重新加回环境变量，但默认不再开启。
- 风险：CDN URL 为 Agnes 平台外链。若将来需私有化 / 水印 / 审计，应恢复**受控存储**——届时需先修好 MinIO 客户端超时与 `gen/` 公开读策略，而非原样回滚到会挂死的旧实现。

## 验证
- `verify/verify_e17_real_image.py`：真实模型出图且 `img.pea-node-result-preview` 真正加载（`naturalWidth>0`），src 以 `https://platform-outputs.agnes-ai.space` 开头（非 mock SVG）；文本节点内容进内容区；0 非 chat console error。
