---
name: pea-e2e-failure-verify
description: >
  Offline Playwright E2E verification of pea Creative OS node failure/edge states
  via dev-hooks injection, without requiring the real Agnes model. Use when
  verifying node UI for generation failure display, broken-image handling,
  retry cleanup, or stale-state recovery on the pea canvas.
agent_created: true
---

# pea 离线 E2E 失败态验证

当需要在 **不依赖真实 Agnes 模型**（离线、可重复、秒级）的情况下，验证 pea 画布节点在
「生成失败 / 裂图 / 重试清理 / stale state」等边界态的 UI 行为时使用本技能。

## 核心机制：dev hooks 注入

pea 画布在 **DEV 模式**或 `localStorage.__peaDevHooks === '1'` 时，会在
`window.__canvas` / `window.__ui` 暴露注入接口。这让我们能绕过真实生成链路，直接构造
任意节点状态来测试渲染分支。

```python
page.add_init_script("localStorage.setItem('__peaDevHooks','1')")
page.goto(BASE, wait_until="domcontentloaded")
```

注入节点（模拟一次生成失败）：
```js
window.__canvas.loadGraph(
  [{ id: 'n1', type: 'image', position: {x:0,y:0},
     data: { kind: 'image', label: '图', resultUrl: 'https://old.example/x.png',
             generating: false, error: '' } }],
  [], 1)
window.__canvas.select('n1')
// 模拟 WS job.updated(failed)：清旧 resultUrl + 写 error
window.__ui.applyJobResult('job_x', { status: 'failed',
  error: '上游 520', resultUrl: undefined, resultUrls: undefined })
```

## 验证脚本模板（verify/verify_image_failure_display.py）

标准 6 项断言，覆盖「失败卡 vs 裂图」这条最易踩的坑：

1. 有旧 `resultUrl` + `error` → 失败卡显示（`[data-testid="node-failure"]` count=1）
2. 同态 → **无** `<img>` 裂图（`img_count=0`）
3. 失败卡含「重新生成」按钮
4. 点重新生成 → 旧 `resultUrl` 被清理（读取 `window.__canvas.getGraph()` 断言为空）
5. 无效 URL（本地 404 路径，如 `/nonexistent-404.png`）+ 无 error → 显式「图片加载失败」占位
   （用 `onError` 触发，不依赖 `error` 字段）
6. 重试后节点进入 generating 态（真实模型不可用时此条放宽，只断言清理动作）

> 注意：无效 URL 用本地 404 路径比 `http://invalid.example.com` 更可靠地触发 `onError`；
> 等待 `2500ms` 让 `onError` 落地。

## 运行方式

```bash
# 依赖：venv 内装 playwright + chromium
python -m venv .../envs/verify
.../envs/verify/Scripts/python.exe -m playwright install chromium
# 目标服务需可达（web 容器 localhost:8088）
.../envs/verify/Scripts/python.exe verify/verify_image_failure_display.py
```

## 关联修复点（踩坑后沉淀）

节点「生成失败却显示裂图」的根因几乎永远是：**失败/重试时只置了 `error`，却忘了清
`resultUrl/resultUrls`**，导致渲染条件 `hasResult = Boolean(currentUrl)` 为真，走了 `<img>`
而不是失败卡。所有写回节点状态的入口（WS 事件、轮询兜底、重试发起、accept 失败 catch）
都必须同步清理这三个字段 + `resultIndex` + `savedToLibrary`。

## 关键红线（来自项目协作准则）

- 验证脚本失败只修脚本，**严禁**为跑通而偷偷改无关实现代码。
- Web 容器 `/usr/share/nginx/html` 是 build 产物，改源码后必须 `docker cp web/dist/.` +
  `nginx -s reload`；BFF/orchestrator 是镜像烘焙，必须 `docker compose build && up -d`。
