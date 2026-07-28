# pea Creative OS — 节点状态设计语言 v1.0

> 基于 `frontend-design` skill，但严格落在系统既有 token 上（不另起配色）。
> 目标：把「失败」「生成中」两种高频状态统一成一套优雅、科技感、可复用的视觉语言。

## 1. 产品定位

- **产品**：pea Creative OS，基于无限画布的 AI 生成工作台。
- **核心对象**：画布节点（image / video / audio / text）。
- **这次要解决的状态**：生成中、生成失败、结果加载失败。
- **调性关键词**： precision instrument、信号状态、深色玻璃、克制光效。

## 2. 设计原则

1. **One signature element**：状态光轨（status rail）。失败 = 琥珀，生成中 = 青色，以同一形式「顶部 1px 渐变流光」统一节点状态语言。
2. **跟随系统 token**：不引入新主色；所有强调色派生自现有 `--pea-brand` / `--pea-lime`。
3. **克制发光**：只在主操作按钮和状态轨上使用柔光，避免霓虹夜店感。
4. **系统一致性**：节点按钮全部走统一的 `.pea-btn` 系统，不再为某个局部状态单独写按钮 CSS。

## 3. 色彩令牌

| 名称 | 变量 | 色值 | 用途 |
|------|------|------|------|
| 品牌青 | `--pea-brand` | `#1fa2dc` | 主操作、生成中 |
| 品牌青（亮） | `--pea-accent-soft` | `#5cc6ec` | 暗底辉光、状态轨 highlight |
| 警告琥珀 | `--pea-warn` | `#f59e0b` | 失败状态、重试按钮 |
| 琥珀（亮） | `--pea-warn-soft` | `#ffb454` | 失败状态轨 highlight |
| 成功绿 | `--pea-success` | `#34d399` | 成功/完成态预留 |
| 成功紫 | `--pea-purple` | `#8b5cf6` | 备用强调 |

深/浅主题差异：青色保持不变；节点区在两种主题下均为深色玻璃，保证画布一致性。

## 4. 按钮系统 `.pea-btn`

位置：`pea-server/web/src/styles/index.css` 顶部统一按钮区。

### 基础类

```html
<button class="pea-btn">默认</button>
<button class="pea-btn pea-btn--sm">小尺寸</button>
```

### 变体

| 类 | 用途 | 视觉 |
|---|---|---|
| `.pea-btn--primary` | 主操作 | 青色渐变 + 柔光 + 扫光 |
| `.pea-btn--ghost` | 次级/关闭 | 透明底 + 白色描边 |
| `.pea-btn--warn` | 失败重试/恢复 | 琥珀渐变 + 柔光 |
| `.pea-btn--quiet` | 纯文字最低存在感 | 透明 |
| `.pea-btn--light` | 亮色表面（TopNav 等） | 跟随 light 主题 token |

### 行为

- hover：`translateY(-1px)` + 辉光增强
- active：回弹 `translateY(0)`
- focus-visible：双环焦点（WCAG 2.1 AA）
- `prefers-reduced-motion`：关闭位移动画和扫光高光

## 5. 节点状态签名：status rail

两种状态共享同一视觉构件——节点内容顶部的 1px 渐变流光。

```
失败：  透明 → 琥珀亮 → 琥珀 → 琥珀亮 → 透明  （3.2s 循环）
生成中：透明 → 青色亮 → 青色 → 青色亮 → 透明  （2.4s 循环）
```

CSS 实现：`.pea-node-failure::after` / `.pea-node-generating::after`，共用 `@keyframes pea-rail-flow`。

## 6. 使用示例

### 失败卡按钮

```tsx
<div className="pea-node-failure-actions">
  <button className="pea-btn pea-btn--ghost pea-btn--sm">关闭</button>
  <button className="pea-btn pea-btn--warn pea-btn--sm">重新生成</button>
</div>
```

### 生成中面板

无需额外类：`.pea-node.is-generating` 自动触发青色光晕 + `.pea-node-generating::after` 青色 rail。

## 7. 无障碍

- 所有动画在 `prefers-reduced-motion: reduce` 下静止或降级。
- 按钮焦点环可见，不依赖 solely 颜色传达状态（rail + pulse + 文案）。
- 状态文案使用系统默认字体，保证中英文可读性。

## 8. 后续可扩展

- 将 `.pea-btn--light` 应用于 TopNav、NodeChatPrompt 发送按钮等亮色表面。
- 为「成功/完成态」增加 `--pea-success` 绿色 rail。
- 考虑把 `.pea-btn` 抽成 React 组件 `<PeaButton />`，统一 disabled/loading 状态。
