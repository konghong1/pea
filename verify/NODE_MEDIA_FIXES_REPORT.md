# 节点媒体交互修复 — 验证报告

**日期**：2026-07-30
**范围**：画布节点编辑框（图片/视频节点）的 4 项交互缺陷
**验证脚本**：`verify/verify_node_media_fixes.py`（Playwright E2E + 服务端持久化往返）

## 修复内容

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | 图片节点刷新后，编辑框有内容但**发送按钮置灰** | `NodePromptInput` 的 `lastHtmlRef` 初始化为 `initialHtml`，导致挂载时把还原内容写入编辑器后，`syncFromEditor` 误判「未变化」跳过 `onChange` → `setHasInput(true)` 永不触发 | `lastHtmlRef` 初始改为 `''`（哨兵值），挂载时只要内容非空必触发一次 `onChange`，正确派生 `hasInput`/`canSend` |
| 2 | 视频节点输入后刷新**内容丢失** | 同根因①（派生状态未刷新）；且原测试用 in-memory `loadGraph`，`reload` 后节点不存在 | 同①修复；验证改为真实输入 → 等待画布 autosave 落库 → `reload` → 重新 `openCanvas` 从服务端取回持久化画布 → 选中，内容正确恢复 |
| 3 | 视频上游连线缩略图显示**问号** | 引用条对视频节点仍用 `<img>`/🖼️ 占位，视频 URL 无法当图片加载 | 视频引用改用 `<video>` 元素（`VideoRefThumb`/`VideoPickerThumb`），hover 弹出播放浮层，含 `@Video` 标签 + 全屏按钮 |
| 4 | 删除连线后缩略图**未移除** | — | `removeEdge` 已正确清除上游引用关系的派生数据，回归验证通过 |

**改动文件**：
- `web/src/components/NodePromptInput.tsx`（`lastHtmlRef` 哨兵初始化）
- `web/src/components/NodeChatPrompt.tsx`（视频引用条渲染 `VideoRefThumb`、启动时 `setHasInput` 兜底）
- `web/src/styles/index.css`（视频缩略图/浮层样式，前序已加）
- `verify/verify_node_media_fixes.py`（刷新场景改用服务端持久化往返）

## 验证结果（全部 PASS）

```
[PASS] 图片节点输入后发送按钮可用
[PASS] 刷新后图片节点编辑框仍有内容
[PASS] 刷新后图片节点发送按钮可用
[PASS] 刷新后视频节点编辑框内容恢复   restored='a cat walking on a beach'
[PASS] 刷新后视频节点发送按钮可用     disabled=False
[PASS] 视频上游在引用条中显示缩略图
[PASS] 视频缩略图使用 video 元素（非问号）
[PASS] video 元素 src 正确
[PASS] hover 视频缩略图显示播放浮层
[PASS] 播放浮层包含 @Video 标签
[PASS] 删除连线后引用条中无视频缩略图
```

## 部署（如需上生产）
```
cd pea-server/web && npx vite build
docker cp dist/. pea-server-web-1:/usr/share/nginx/html/
docker exec pea-server-web-1 nginx -s reload
```
