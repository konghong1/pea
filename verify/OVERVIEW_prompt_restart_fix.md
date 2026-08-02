# 视频节点提示词「重启容器后丢失」——根因定位 + 修复 + 验证

## 结论先行
提示词**数据从未丢失**(MySQL `graph_json` 一直存着)。真正丢的是**编辑器渲染**:
回填逻辑用了 `??`(空值合并),空串 `localStorage` 草稿会**短路**掉服务端 `meta.editorText`,
导致刷新/重启后编辑框空白,用户以为"提示词丢了"。

## 根因(三连)
1. `NodeChatPrompt.tsx` 节点切换回填优先级:`draftRef ?? lsDraft ?? meta.editorText ?? ...`
   - `??` 只把 `null/undefined` 当空,**空串 `''` 被当有效值**。
   - 只要 `pea:draft:{canvasId}:{nodeId}` 是空串(节点刚建好 / 回填 `setHtml` 竞态回传空文本写空),
     `restored=''`,永不到 `meta.editorText` → 编辑器空白。
2. 回填 `setHtml` 触发的 `onChange` 竞态可能回传空文本,经防抖持久化**把服务端 prompt 也清空**。
3. 卸载 flush 此前用会被浏览器中断的异步 PUT(已修为 `keepalive`)。

## 修复(3 处,均在 `NodeChatPrompt.tsx`)
- 回填优先级 `??` → `||` + 空串 trim 兜底:空串草稿不再遮服务端 prompt。
- `onInputChange` 写 `localStorage` 草稿时跳过空串,杜绝空文本污染。
- 新增 `restoringRef`:回填期间抑制 `setHtml` 竞态的 `onChange` 回落,保护 store/localStorage。
- 配套:`CanvasEditor.tsx` 卸载 flush 已用 `fetch(keepalive:true)`。

## ⚠️ 部署关键教训(你"改很多次重启又丢"的症结)
此前多次修复只留在**源码**,没 `docker compose build` 重新打镜像。
你重启用 `docker compose up -d web` → 按**旧镜像**重建 → 修复全丢。
本次已执行 `docker compose build web && docker compose up -d web`,修复**烘焙进镜像**,重启真正生效。

## 验证(真实浏览器 E2E,非静态)
脚本 `verify/e2e_prompt_restart.py`(Playwright + Chromium):
登录 → 建画布 → 真实打字进视频节点 → 断言 MySQL 含 prompt
→ **`docker restart pea-server-web-1`** → 重载 → 选中节点 → 断言 store+DOM 仍有 prompt。

结果:**RESULT: PASS** ✅(对镜像级容器重跑,等价于你 `docker compose up -d` 重启场景)

构建产物:`index-DBDXUjCD.js`
