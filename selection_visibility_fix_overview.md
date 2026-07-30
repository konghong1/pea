# 多选框遮挡节点问题修复总览

## 问题
框选多个节点后，选区框（selection box）覆盖在节点之上，导致框内节点信息/内容被遮挡，用户无法看清选中了什么。

## 根因
ReactFlow 的 DOM 层级：
- `.react-flow__pane`（z-index: 1）
  - `.react-flow__viewport`（承载所有 `.react-flow__node`，无 z-index）
  - `.react-flow__nodesselection`（承载选区矩形 `.react-flow__nodesselection-rect`，z-index: 3）

因为 viewport 没有 z-index，而 nodesselection 有 z-index:3，导致拖拽完成后选区矩形容器整体覆盖在节点层之上，即使选区背景已设为半透明 `rgba(31,162,220,0.06)`，节点仍被半透明层遮住。

## 修复
`pea-server/web/src/styles/index.css`：
```css
.react-flow__viewport {
  z-index: 4 !important;
}
```

将 viewport 提到 z-index:4，高于 nodesselection 的 3，同时仍低于拖拽中 `.react-flow__selection` 的 6，保证：
- 拖拽过程中选区矩形覆盖节点，提供框选视觉反馈；
- 拖拽完成后节点显示在选区背景之上，节点内容不被遮挡。

同时保留：
```css
.react-flow__selection,
.react-flow__nodesselection-rect {
  background: rgba(31, 162, 220, 0.06) !important;
  border: 1px solid var(--pea-brand, #1fa2dc) !important;
  pointer-events: none !important;
}
```

## 验证
新增脚本 `verify/verify_selection_visibility.py`：
1. 自动注册/登录/创建画布；
2. 注入两个节点；
3. 模拟拖拽框选；
4. 截图 before / during / after 三个状态。

结果：
- `selvis_after_drag_select_*.png`：选区边框可见，两个节点内容清晰可见，无遮挡。
- `verify_group_fix.py`（之前的打组修复）仍 PASS。
- `tsc --noEmit` 通过。

## 相关文件
- `pea-server/web/src/styles/index.css`
- `verify/verify_selection_visibility.py`
