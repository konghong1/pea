# 打组功能 UI/交互优化总结

## 问题分析
用户反馈当前打组功能存在以下问题：
1. 打组后节点没有贴着选择框，间隙过大。
2. 顶部共同工具条没有选择框顶部中间对齐。
3. 工具条/选择框样式不够科技感、不够简洁美观。
4. 解组按钮藏在布局下拉菜单里，不符合直觉。
5. 拖出节点后，选择框会收缩到只剩最后一个节点。
6. 节点无法拖入 group。
7. 期望打组后选择框大小固定，不因拖入/拖出而改变。

## 改动方案

### 1. 选择框固定大小 + 节点贴合
- **文件**: `pea-server/web/src/store/canvas.ts`
- 将创建 group 时的内边距从 `28px` 收紧到 `16px`。
- 重写 `moveNodeToGroup`：
  - 拖出 group 时只解除 `parentNode`、更新 `childrenIds`，不再重新计算并缩小 group 尺寸。
  - 拖入 group 时只添加 `parentNode`、更新 `childrenIds`，不再重新计算并放大 group 尺寸。
  - 坐标转换保留当前视觉位置，避免节点跳动。

### 2. 工具条居中
- **文件**: `pea-server/web/src/components/GroupNode.tsx`
- Portal 工具条位置改为 `left = r.left + r.width / 2`。
- CSS 增加 `transform: translateX(-50%)`，使工具条严格居中于选择框顶部。
- 调整 `HEADER_GAP` 与 `HEADER_HEIGHT`，让工具条与选择框保持清晰呼吸间距。

### 3. 解组外置
- **文件**: `pea-server/web/src/components/GroupNode.tsx`
- 从布局下拉菜单中移除「解组」。
- 在最外层功能条新增独立的「解组」按钮（带 `GroupOutlined` 图标）。
- 新增 `.pgn-actions-sep` 分隔线与 `.pgn-ungroup` 危险态 hover 样式。

### 4. 科技感 UI 升级
- **文件**: `pea-server/web/src/styles/index.css`
- **Group 选择框**：透明背景 + 1.5px 细边框 + 品牌青色柔光，选中时外发光增强，子节点透出画布点阵。
- **顶部工具条**：改为深色圆角胶囊（`border-radius: 999px`），毛玻璃背景，按钮胶囊化并带微抬升 hover。
- **左侧标识**：白色状态圆点 + 组图标 + 组名，简洁识别。
- **Light 模式**：补齐工具条、按钮、解组、分隔线的亮色适配。

## 验证
- `npm run build` 通过，TypeScript 无错误。
- 已将 `dist/` 复制到 `pea-server-web-1` 容器并 reload nginx。

## 涉及文件
- `pea-server/web/src/store/canvas.ts`
- `pea-server/web/src/components/GroupNode.tsx`
- `pea-server/web/src/styles/index.css`
