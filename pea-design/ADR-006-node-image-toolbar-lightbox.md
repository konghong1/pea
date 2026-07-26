# ADR-006: 节点生成图片的工具条、多图角标与全屏查看 Lightbox

## Status
Accepted

## Context
用户按参考截图要求，图片节点在模型生成结果后需要：
1. 结果图上方悬浮功能条（裁剪 / 3D / 去背景 / 放大 / 更多 / 风格 / 保存到素材库 / 下载 / 全屏查看）。
2. 多图结果时右上角显示数字角标，点击展开小图选择。
3. 全屏查看为复杂 Lightbox：左侧大图 + 底部缩略图 + 左右切换 + 右侧信息面板（提示词、模型、质量、宽高比、文件大小、日期、创建者）。
4. 本期先落地「保存到素材库」与「全屏查看」，其余按钮样式占位、点击提示「即将上线」。

## Decision
1. **数据模型扩展** `PeaNodeData`：
   - `resultUrls?: string[]`：支持同一次生成返回多张结果图。
   - `resultIndex?: number`：当前展示第几张。
   - `savedToLibrary?: boolean`：保存到素材库状态（本期本地状态，后续对接 API）。
   - `params?: Record<string, unknown>`：生成参数，供 Lightbox 信息面板展示。
2. **回填逻辑**：`NodeChatPrompt` 在 WS/轮询收到 `done` 时，同时写入 `resultUrl` 与 `resultUrls[0]`，并写入 `params`。
3. **组件拆分** `PeaNode.tsx`：
   - `MediaNodeBody`：媒体节点主体。
   - `ResultImageView`：单图/多图渲染、角标、工具条挂载点。
   - `ResultToolbar`：功能条（SVG 图标 + title/aria-label）。
   - `ImageLightbox`：全屏查看（`createPortal` 挂到 `document.body`，避开 ReactFlow viewport transform）。
4. **样式**：`index.css` 新增深色胶囊工具条、星标、多图角标下拉、Lightbox 左右布局与信息面板。
5. **验证**：新增 `verify/verify_e19_node_image_toolbar.py`：真实模型出图 → 工具条出现 → 保存高亮 → Lightbox 打开 → ESC 关闭 → 0 console error。

## Consequences
- **Pros**: 节点图片交互对齐参考设计；多图数据结构就位，后续 Agnes 多图 (`n>1`) 直接可用；工具条用 aria-label 便于 E2E 与无障碍。
- **Cons**: Lightbox 信息面板的「文件大小」依赖 `HEAD` 请求 CORS，跨域失败时显示 `-`，不影响主功能。
