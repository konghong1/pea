# 修复：画布内 Ctrl+滚轮触发浏览器整页缩放

## 问题
鼠标放在节点编辑框、主题 `Select` 下拉、节点参数弹层等 UI 上，按住 Ctrl/⌘ + 滚轮本意是缩放画布，却触发了浏览器整页缩放。

## 根因
原 `wheel` 守卫只挂在画布容器 `flowRef` 上。而节点编辑框浮层、`Select` 下拉、节点参数弹层（`ModelPickerPopup`/`AspectPickerPopup`/引用选择器/多选工具条/搜索弹层）都被 `createPortal` 渲染到 `document.body`，不在 `flowRef` 子树内 —— 它们的 `wheel` 事件冒泡不到守卫，于是没有被 `preventDefault()`，浏览器按默认行为对整个页面做了缩放。

## 解决方案
在 `CanvasEditor.tsx` 中把守卫从「容器局部监听」升级为「`window` 捕获阶段 + 非 passive 监听」：
- 命中 `Ctrl/⌘` 且事件目标处于画布范围内（`.pea-canvas-host` 或其 `[data-pea-canvas-portal]`/`.pea-canvas-portal` 后代）时，`preventDefault()` 拦截浏览器整页缩放；
- 目标若已在 ReactFlow 的 pane 子树内（含节点内联编辑框）→ 交给 ReactFlow 自身缩放，避免重复缩放；
- 目标落在 portal/浮层上（ReactFlow 收不到该事件）→ 由新增的 `zoomCanvasAtPointer()` 以光标为锚点手动驱动 `setViewport` 缩放；
- 普通滚轮（无 Ctrl）不拦截，保留 `panOnScroll` 的画布平移手势；裁切模式下仍全量锁定。

同时给画布内 portal 浮层打标，让守卫能识别「画布中」：
- 主题 `Select`：`popupClassName="pea-canvas-portal"`
- `NodeChatPrompt` / `NodePromptInput` / `MultiSelectToolbar` / `SearchPopover` 的 portal 根元素：`data-pea-canvas-portal`

## 改动文件
- `pea-server/web/src/components/CanvasEditor.tsx`（核心修复 + 主题 Select）
- `pea-server/web/src/components/NodeChatPrompt.tsx`
- `pea-server/web/src/components/NodePromptInput.tsx`
- `pea-server/web/src/components/MultiSelectToolbar.tsx`
- `pea-server/web/src/components/SearchPopover.tsx`

## 验证
- `tsc --noEmit` 通过。
- 行为预期：画布任意位置（含编辑框、下拉、参数弹层）Ctrl+滚轮只缩放画布，不再触发浏览器整页缩放；节点内联编辑框不重复缩放；普通滚轮平移画布不受影响。

## 运行方式
前端源码改动后需重建 web 容器（Docker 环境）：`docker compose up -d --build web`；本地 `npm run dev` 直接生效。
