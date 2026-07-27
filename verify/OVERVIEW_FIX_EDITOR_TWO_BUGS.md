# 编辑框两个交互 Bug 修复验证报告

> 验证日期：2026-07-27 · 运行环境：Docker `localhost:8088`（生产构建）
> 验证方式：真机 Playwright E2E（Node），确定性、可复现。

## 一、Bug1 — 删光文本后旧文本又冒出来

**现象**：图片节点编辑框里把文本全部删除后，文本又整段冒回来。

**根因**（两处叠加）：
1. `NodeChatPrompt.tsx` 的 `onInputChange` 在内容为空时执行 `delete draftRef.current[single]`，清空了草稿缓存。
2. `NodePromptInput.tsx` 的初始化 `useEffect` 依赖 `[initialHtml, syncFromEditor]`，一旦 `initialHtml` 变化就把 `editor.innerHTML` 重新写回 `initialHtml`。

→ 删空 → `draftRef` 被清空 → `initialHtml = draftRef ?? sel.data.meta.editorText ?? ''` 回退到**持久化的旧 prompt** → effect 把旧文本重新顶回编辑器。

**修复**：
- `NodePromptInput` 初始化 effect 改为**仅挂载时执行一次**（`didInitRef` 守卫），之后不再随 `initialHtml` 反复回填；节点切换由父组件 `setHtml` 显式还原。
- `onInputChange` 空内容时**不再 delete** `draftRef[single]`，保留为空字符串，避免回退到旧 prompt。

## 二、Bug2 — 删自己输入的字却先删 @ 引用的图片

**现象**：`@` 一张图片后，想删掉自己输入的文字，结果每次退格先删掉的是那张 `@` 图片。

**根因**：`NodePromptInput.tsx` 的 `handleKeyDown` Backspace 分支用 `isCursorInsideOrAdjacentToToken(range)` 判断。当光标落在 `@` token **后面**的自己文本里时，token 恰是 previousSibling → `insideOrAdjacent = true` → 直接 `removeChild(token)`，完全无视光标在文本中的真实位置。

**修复**：Backspace 删 token 收紧为**仅当**：
- 光标紧贴 token 左缘（文本容器内 `offset === 0` 且前一个兄弟是 token），或
- 光标落在 token 内部（contenteditable=false 原子单元）

其余情况一律交给浏览器默认行为，删普通文本字符。`@` token 左缘退格仍可正常删除（边界行为保留，未改过头）。

## 三、确定性验证证据（同一脚本跑 8088）

脚本：`verify/verify_editor_two_bugs.cjs`

| 测试 | 结果 | 关键证据 |
|---|---|---|
| Bug1 删光文本 | PASS | 注入 `editorText='一只橘猫坐在窗台'`→全选删除→`after.text=''`（未回退） |
| Bug2 删自己字 | PASS | `@` 插入 token(count=1)→输入 `abc`→退格 3 次→`tokenCount=1, text=''`（@图仍在、自己字删掉） |
| Bug2 边界 | PASS | 再退格 2 次→`tokenCount=0`（token 在左缘仍可删，未改过头） |

**RESULT: ALL PASS** —— 0 console error / 0 pageerror。

## 四、可复现命令
```bash
cd /d/workspace/pea/verify
NODE_PATH='C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules' \
  /c/Users/admin/.workbuddy/binaries/node/versions/22.22.2/node.exe \
  verify_editor_two_bugs.cjs
```

## 五、部署确认
`npm run build`（tsc 通过，无类型错误）+ `docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/` + `nginx -s reload`，新构建已部署到 8088。浏览器硬刷新（Ctrl+Shift+R）即可拿到新包。
