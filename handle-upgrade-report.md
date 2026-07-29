# 连接点（Handle）升级报告

## 问题
画布缩小时连接点找不到、悬停无放大反馈、间距太紧、图标缺乏科技感。

## 方案：反缩放 + 科技端口图标

### 核心技术：Counter-Scale 反缩放
ReactFlow 通过 CSS `transform: scale(zoom)` 缩放整个视口，导致连接点随节点一起被压成 3px（zoom=0.3 时）。

**解法**：在 `PeaNode.tsx` 中通过 `useViewport()` 获取当前 zoom 值，给 Handle 内联 `transform: scale(1/zoom)`。
同时将间距偏移量设为 `handleOffset = -GAP / zoom`，使间距同样恒定。

效果：**连接点在任何缩放下都保持恒定屏幕尺寸（13px）和恒定间距（11px）**。

### 科技感图标设计
替换原实心圆点为 SVG「**连接端口**」图标：
- **外环** (`hg-ring`)：品牌色细圆环，标识连接区域
- **转子** (`hg-rotor`)：白色虚线旋转环，悬停/连线时启动动画
- **核心** (`hg-core`)：品牌色实心圆 + 辉光，视觉焦点

### 三级尺寸状态
| 状态 | 尺寸 | 辉光 | 转子 |
|------|------|------|------|
| 静止 | 13px | 柔光 3px | 隐藏 |
| 悬停/选中 | 19px (+46%) | 强光 7px | 旋转 3.2s |
| 连线拖拽中 | 22px | 脉冲 10px | 快转 1.6s |

### 间距优化
HANDLE_GAP 从原来的 -10px（紧贴/重叠）→ **24px 屏幕恒定间距**，实测近缘间隙 **+11px**（之前是 -6px 重叠）。

## 修改文件
1. **`pea-server/web/src/components/PeaNode.tsx`**
   - 新增 `useViewport` 导入与反缩放计算（inv, handleOffset）
   - 新增 `<HandleGlyph />` SVG 组件（科技端口图标）
   - 两个 `<Handle>` 改用内联 style 注入反缩放 transform + 恒定间距 offset
   - HANDLE_GAP = 24

2. **`pea-server/web/src/styles/index.css`**
   - 完全重写 `.react-flow__handle.pea-handle` 及相关规则（~80 行 → 新科技端口样式）
   - 新增 `.pea-handle-glyph` / `.hg-ring` / `.hg-core` / `.hg-rotor` SVG 子元素样式
   - 新增 `@keyframes pea-handle-spin` 转子旋转动画
   - 修复 `.connectionindicator` 级联问题（不再默认放大到 22px）

## 验证结果（Playwright 自动化，7/7 PASS）

```
[PASS] 默认 ~13px 级尺寸          实测: 13px
[PASS] 缩小后尺寸恒定(±4px)      实测: 13px (不变)
[PASS] 悬停放大                  实测: 13→19px (+46%)
[PASS] 缩小后间距恒定(±6px)      实测: 11px (不变)
[PASS] 间距明显(>6px)            实测: +11px (之前 -6px 重叠)
[PASS] 科技图标 SVG 渲染         实测: 4 个 glyph (每节点 2 手柄×2 节点)
[PASS] 无运行时报错              实测: 0 错误
```

截图验证：
- `verify/shots/v1_default.png` — 默认态：清晰可见的科技端口图标
- `verify/shots/v3_hover.png` — 悬停态：尺寸增大 + 转子旋转
- `verify/shots/v2_zoomout.png` — 缩小后：手柄保持恒定尺寸

## 技术要点
- **反缩放不会影响 ReactFlow 的连线逻辑**：ReactFlow 用 `getBoundingClientRect()` 计算连接端点，反缩放后返回的是正确的屏幕坐标
- **transform-origin 方向性**：左手柄 `right center`（向左生长），右手柄 `left center`（向右生长），确保放大时远离节点框
- **`.connectionindicator` 陷阱**：ReactFlow v11 对所有可连接手柄常驻此类名，不能用作"拖拽中"的判断依据；仅 `.connectingfrom` 可靠表示正在拖拽的源手柄
