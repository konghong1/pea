# 图片节点样式提质 + 移除点图放大

## 背景
用户反馈两点：① 图片节点展示样式很丑；② 点击图片时不要放大（指点击图片弹出全屏 Lightbox）。
参考页 `superdesign.dev` 需登录，无法抓取其样式 —— 已如实告知，请用户发截图以便 1:1 还原。本次先按 premium 标准在本地代码做提质。

## 改动清单

### 1. 移除「点图放大」（`web/src/components/PeaNode.tsx`）
- `ResultImageView` 主图 `<img onClick={handleFullscreen}>` 已删除，改为 `loading="lazy"` + `draggable={false}`。
- 工具栏「全屏查看」按钮保留（是独立动作，不是"点图放大"）；如也不需要可告知删除。

### 2. 样式提质（`web/src/styles/index.css`）
- **结果图容器** `.pea-node-result-image-wrap`：圆角 12px→16px，加 1px 细边框 + 柔和投影，hover 用边框/光晕微交互替代缩放。
- **主图** 去掉 `cursor: zoom-in`（改 `default`），hover 由 `scale(1.01)` 改为 `brightness(1.04)`，消除"放大"观感。
- **功能条** `.pea-node-result-toolbar` 玻璃质感提质（blur 14px + saturate）。
- **工具栏占桩降权**：`ToolbarButton` 新增 `muted` prop；裁剪/3D/去背景/放大/更多 五个"即将上线"按钮半透明（0.45），仅「风格迁移 / 保存到素材库 / 下载 / 全屏查看」保持醒目 —— 解决廉价拥挤感。

## 验证
改动仅涉及 CSS + 一处 onClick 移除 + 一个可选 prop，风险极低，未触发构建/E2E。需要时可 `npm run build` + `docker cp` 部署核对。

## 交付物
- `image-node-preview.html`：独立预览，1:1 复刻新图片节点样式，浏览器直接打开即可看效果。
