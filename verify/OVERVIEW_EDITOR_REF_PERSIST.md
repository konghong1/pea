# @ 引用图片「刷新丢失 + 生成不参考」修复报告

## 用户反馈
> 把这个 @ 的图片（包）放在猫咪的身边，别改变包的样式。
> 使用刷新后这个 @ 的图片丢失。【…】而且，发送的消息并没有参考我 @ 的图片生成内容。

两个症状，同源。

## 根因
编辑框提交时，持久化内容写的是：
```ts
metaPatch.editorText = parsed.text;   // 纯文本，@ token 被剥离
```
- **Bug A（刷新丢失）**：刷新后 `initialHtml = editorText`（纯文本，无 `data-pea-ref` token）→ 编辑器里 @ 的图消失。
- **Bug B（生成不参考）**：`submit` 的 `reference_images` 来自 `getParsed().referenceImages`。token 丢失后解析不出引用 → `reference_images` 为空 → 生成不参考该图。
  - 补充：若 @ 的节点**同时连了边（upstream）**，`refIds` 仍会从边带入它；只有「纯 @ 引用、不连边」才是 Bug B 的决定性复现场景（本验证专门覆盖）。

## 修复（3 处，未动无关逻辑）
1. `NodePromptInput.tsx` — `ParsedPrompt` 新增 `html` 字段；`getParsed()` 返回 `editor.innerHTML`（含完整 @ token DOM）。
2. `NodeChatPrompt.tsx` — `metaPatch.editorText = parsed.html || parsed.text`（存完整 HTML）；兜底对象补 `html:''`。
3. `NodePromptInput.tsx` `getParsed()` 收严 `referenceImages` 解析：优先 `resolvedThumbs[id]`，**兜底**直接读节点 `data.resultUrls/resultUrl/url` 同步解析（AI 图无需异步），保证 @ token 始终是 `reference_images` 的可靠来源。
   - 另：新增 effect，在 `resolvedThumbs` 更新（刷新后 / 签名 URL 过期）时把编辑器内已存在的 @ token `<img>` 的 `src` 指向最新 URL，避免显示陈旧/失效图。

> 「包的样式别改」：本次只改 @ 引用的持久化与解析，未触碰被引用节点（包）本身的渲染，包节点外观完全不变。

## 确定性验证（Node Playwright，localhost:8088）
脚本：`verify/editor_ref_persist.cjs` —— **ALL PASS（9/9，0 console error）**

| 测试 | 断言 | 结果 |
|---|---|---|
| T1 @ 选择器插入 token（带边） | token 插入成功 | PASS |
| T1 发送时 `reference_images` 含 @ 包 | `['…BAG']` | PASS |
| T1 发送的 `editorText` 含 `data-pea-ref` | 持久化完整 HTML | PASS |
| T1 刷新后 token 仍在编辑框 | tokenCount=1 | PASS |
| T1 刷新后 token 缩略图指向包图 | src 含 BAG | PASS |
| T1 刷新后 meta 仍含 `reference_images`+`data-pea-ref` | 完整还原 | PASS |
| T2 纯 @ token（无边）插入成功 | tokenCount=1 | PASS |
| **T2 无边场景发送 `reference_images` 含 @ 包2** | `['…BAG2']` | **PASS（Bug B 决定性修复）** |
| 无 console error | errors=[] | PASS |

回归 `verify/editor_two_bugs.cjs`：**ALL PASS**（无回归）。

## 部署
`npm run build`（tsc 通过）→ `docker cp web/dist/.` → `nginx -s reload`，已部署 `localhost:8088`。

## 复现命令
```bash
cd /d/workspace/pea/verify && NODE_PATH='C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules' \
/c/Users/admin/.workbuddy/binaries/node/versions/22.22.2/node.exe verify_editor_ref_persist.cjs
```

## 给用户
硬刷新 `localhost:8088`（Ctrl+Shift+R）拿新包：@ 引用图片后刷新不再丢失，发送时生成会正确参考该图。
