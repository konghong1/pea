# 画布体验修复完成报告

## 修复内容
针对用户反馈的三处画布体验问题，已按参考图完成实现并通过真机 E2E 验证（0 console error）。

### 1. 画布控制条样式对齐 @image#1
- 文件：`pea-server/web/src/components/CanvasEditor.tsx`、`pea-server/web/src/styles/index.css`
- 左下角新增深色胶囊控制条：地图/层级（切换 MiniMap）、网格（切换背景点阵）、适配视图、缩放滑块、独立帮助按钮。
- 关键决策：自定义 ReactFlow 控件组件只渲染按钮/滑块；`<Background>` 和 `<MiniMap>` 必须作为 `<ReactFlow>` 的直接子元素，否则会被套进控件容器并覆盖控件。

### 2. 节点缩放不影响弹出输入框 / 文本工具条
- 文件：`pea-server/web/src/components/NodeChatPrompt.tsx`（重构）、`pea-server/web/src/components/TextNodeToolbar.tsx`（新增）
- 改为 `position: fixed` 视口坐标 + `requestAnimationFrame` 实时读取节点 `getBoundingClientRect()` 重定位；宽度最小 360px 并水平居中。
- 文本节点上方恢复 H1/H2/H3/¶/B/I/列表 暗色胶囊工具条（对齐 @image#2）。

### 3. 连线未命中时弹出节点选择菜单
- 文件：`pea-server/web/src/components/CanvasEditor.tsx`
- 通过 `onConnectStart` 记录源节点，`onConnect` 成功时清空；`onConnectEnd` 若未命中目标则在释放位置弹出 `EdgeNodeMenu`（文本生成 / 图片生成 / 视频生成 / 音频 / 3D 世界 Beta）。
- 选择后创建对应节点并连边；未选择则放弃；直接连接现有节点时源节点不会消失。

## 验证
- 新增 `verify/verify_canvas_fixes.py`，覆盖：
  - 控制条各按钮/滑块可见且可点击
  - 缩放滑块生效，输入框仍锚定在节点下方且宽度稳定
  - 文本工具条位于节点上方
  - 连线空放弹出选择菜单，选择后节点 2、边 1
  - 直接连接两个节点，节点数保持 2
- 运行结果：`[TOTAL console errors]: 0`，全部断言通过。
- 快速迭代方式：`npm run build` → `docker cp web/dist/. pea-server-web-1:/usr/share/nginx/html/ && docker exec pea-server-web-1 nginx -s reload`。

## 后续建议
- 当前 MiniMap 通过控制条按钮切换显示，位置设在左上角，避免与右下角 AI 气泡重叠。
- 文本格式化工具条使用 `document.execCommand`，后续如需更现代的富文本体验可替换为 Slate/Tiptap。
