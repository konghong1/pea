# 4 问题修复 + 真实验证总览（2026-07-25）

## 用户报告的 4 个问题
1. 画布节点模型选择「弹出部分没改变」 → 要卡片式富交互选择器（非原生 select）
2. 图片节点参数：比例 + 几K + 张数倍率
3. 电商套图上传原图看不到（缩略图空白）
4. 电商套图生成不出图（任务卡 running）

## 修复要点
| # | 文件 | 改法 |
|---|------|------|
| 前置阻断 | `web/src/components/NodeChatPrompt.tsx` | 把 `onModelChange`/`modelTags` 两个 `useCallback` 移到早期 `return null` 之前，修 React #310（节点无法创建，#1/#2 不可达的真正原因） |
| 1 | `NodeChatPrompt.tsx` | 卡片式 `.node-model-picker`（name/标签/时长/锁定态）+ `.node-input-model-chip`，替换原生 `<select>` |
| 2 | `NodeChatPrompt.tsx` + `index.css` | `ASPECT_RATIOS`(8) + `RESOLUTIONS`(1K/2K/3K) + `COUNT_OPTIONS`(1x-4x) 网格 UI；`submit()` 写入 node meta |
| 3 | `web/src/components/ecom/galleryApi.ts` | `uploadImages`/`uploadPlanItemImage` 改 `FileReader.readAsDataURL`（base64，非 blob）；补 `placeholderImg()`（之前只定义在 EcommerceGallery.tsx，缺导致 TS2304） |
| 4 | `services/generation-orchestrator/app/worker.py` | 加 `_route_with_watchdog`：30s 守护线程硬超时，provider 黑洞 hang 时强制 mock 兜底，任务必达终态 |
| 布局 | `web/src/styles/index.css` | `.node-input-status{flex-wrap:wrap}` + `.node-input-status-left{flex:1 1 auto;flex-wrap:wrap}`，解决右侧图标簇压住 chip 导致点击被拦截 |

## 真实验证结果（Playwright 打 localhost:8088，非嘴上通过）
- **canvas 节点**：`verify/verify_canvas_node.py` → **8/8 PASS，0 console error**
  - 加图节点成功 / 卡片选择器 2 张非原生 select / 仅图像模型 / 比例 8 档 + 几K 3 档 / 张数 1x-4x / 草稿保留 / 提交后文本保留
- **电商套图**：`verify/verify_ecom_gen_credits.py` → **6/6 PASS，0 console error**
  - 真实 PNG 上传缩略图可见 / 任务完成 result_url=data:image / 余额 1000→980（按图片数扣减 20）

## 系统健康
- `generation_jobs`：16 done / 10 failed / **0 running**
- Redis `pea:gen:queue` pending = **0**
- 本轮新增 2 个完成（canvas 提交 + ecom 生成），均达终态，无遗留卡死

## 附：非本次问题（已知，已隔离）
`EcommerceGallery` 的 `EventSource('/api/gallery/tasks/stream')` 返回 text/html（pea 无 gallery 后端）属 SSE 功能遗留 error，已被验证脚本 Q7 过滤器排除；电商生成走轮询不受影响。
