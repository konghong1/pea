# 视频节点对齐图片节点（修复说明 + 团队约定）

> 资深开发者修复记录 · 2026-07-28

## 问题
用户反馈视频节点与图片节点不一致，集中在三点：

1. **视频节点没和图片节点一样** —— 图片节点有收藏星标、替换按钮、多图角标、功能条、全屏 Lightbox；视频节点此前只是一段裸 `<video>` + 一个写死的替换按钮，缺一堆交互。
2. **生成的视频没占满节点框** —— 视频有内容时 `body-card` 被强制 `min-height:280px + padding:14px`，视频本身还被 `max-height:252px` 压成小窗，四周留白，看起来"没填满"。
3. **替换按钮约定错了** —— 图片节点规则是「上传媒体才显示替换，AI 生成结果不显示」；但旧视频/音频代码**反了**：AI 生成视频反而有替换、上传视频反而没有。

## 修复内容

### 1. 统一渲染组件（`web/src/components/PeaNode.tsx`）
- 把 `ResultImageView` 泛化为 **`ResultMediaView`**，对 `image / video / audio` 通用。
- `MediaNodeBody` 的「AI 生成结果 / 用户上传 / 空态」三个分支现在都走 `ResultMediaView`。
- 视频/音频现在拥有与图片**完全一致**的能力：左上角收藏星标、右上角替换、多结果角标+选择器、底部功能条（裁剪/3D/去背景/放大/更多/风格迁移/保存素材库/下载/全屏）、全屏 Lightbox。
- `ImageLightbox` → **`MediaLightbox`**（带 `kind` 参数）：视频/音频在 Lightbox 内渲染 `<video>/<audio>`，缩略图非图片显示 ▶/♪ 图标；下载文件名按真实扩展名推导。

### 2. 替换按钮约定（核心规则，务必遵守）
```ts
// 仅「用户上传的媒体」显示替换；AI 生成结果不显示
const canReplace = !!(data.fileKey || data.url) && !hasResult;
```
这条规则在 `ResultMediaView` 里统一生效，image/video/audio 行为一致。**以后新增媒体类型直接复用 `ResultMediaView`，不要裸写 `<video>`/`<audio>`。**

### 3. 占满节点框（`web/src/styles/index.css`）
- 视频 `has-media` 的 `body-card` 改为与图片一致：`padding:0` + `aspect-ratio:auto`，节点尺寸由视频原始比例决定。
- 新增 `.pea-node-result-video-wrap` / `.pea-node-result-audio-wrap` 容器，`width:100%`，视频 `width:100% / object-fit:cover / max-height:420px` 占满宽度、按原始比例包裹（不裁切）。
- 删除已无引用的 `.pea-node-result-media-wrap` 死代码；新增 `.pea-node-lightbox-audio` / `.pea-node-media-picker-thumb`。

## 验证
- `tsc -b && vite build`：0 错误（3267 modules）。
- 已部署：`docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/` + `nginx -s reload`，线上已生效。

## 给团队的方法论
- **媒体节点的「替换」按钮约定是图片节点的硬规则**：上传有、AI 生成无。任何新媒体类型都要复用 `ResultMediaView`，避免再次把约定写反。
- **节点内媒体要"占满框"**：有内容时让 `body-card` 由媒体原始比例撑开（去 padding / `aspect-ratio:auto`），媒体本身 `width:100%`，而不是给固定 `min-height` + 小 `max-height` 把媒体压成小窗。
- **复用优于局部定制**：图片节点已经打磨好的星标 / 功能条 / Lightbox，视频直接复用，不要各写一套，否则很快样式与行为漂移。
