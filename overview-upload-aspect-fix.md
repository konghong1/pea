# 上传图片节点比例自适应修复

## 问题现象

用户上传一张横向图片后，图片节点仍按默认 `9:16` 竖向框展示（通过 `object-fit: cover` 裁剪显示）。点击「裁剪/截图」时，`ImageCropOverlay` 按图片真实比例渲染，导致图片突然变成横向，与节点日常显示不一致。

## 根因

`PeaNode.tsx` 的 `onPickFile` 在上传/替换图片时只更新了 `fileKey` / `url` / `meta` 等字段，**没有读取图片真实宽高比并更新 `data.aspectRatio`**。节点框尺寸始终由默认 `9:16` 决定，因此出现「节点一种比例、截图时另一种比例」的错位。

## 修复方案

1. **上传时自动检测图片真实比例**
   - 在 `PeaNode.tsx` 新增 `detectImageAspectRatio(file)`，通过 `URL.createObjectURL` + `Image.naturalWidth/Height` 读取本地文件比例。
   - `onPickFile` 中对 `kind === 'image'` 的文件调用该函数，并将结果写回 `data.aspectRatio`；检测失败时保持原比例兜底。

2. **复用比例归约逻辑**
   - 将原位于 `PeaNode.tsx` 底部的 `simplifyRatio` 提取到 `lib/nodeSize.ts` 并导出，供上传检测与后续裁剪结果节点复用。

3. **验证**
   - 新增 `verify/node_size.test.ts`，覆盖 `simplifyRatio` 与 `getNodeSize` 的核心比例/尺寸计算。
   - `npm run typecheck`、`npm test`、`npm run build` 全部通过。

## 关键改动

- `pea-server/web/src/components/PeaNode.tsx`
  - 新增 `detectImageAspectRatio`。
  - `onPickFile` 写入 `aspectRatio: detectedAspectRatio ?? data.aspectRatio`。
  - 从 `lib/nodeSize` 导入 `simplifyRatio`。

- `pea-server/web/src/lib/nodeSize.ts`
  - 导出 `simplifyRatio(w, h)`。

- `verify/node_size.test.ts`（新增）
  - 验证常见分辨率的最简比例与节点尺寸计算。

## 影响范围

- 仅影响用户主动上传/替换的图片节点；AI 生成结果的比例仍由生成参数控制，不会被覆盖。
- 视频/音频节点保持现有默认比例，不受本次改动影响。
