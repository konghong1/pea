# 选区框残留（"两个框"）问题修复总览

## 问题现象

用户反馈：框选节点或打组后，鼠标松开仍能看到一个浅蓝色半透明的大选区矩形覆盖在节点上方，与节点自身的选中边框同时存在，形成明显的"两个框"。

## 根因分析

问题来自两个独立但叠加的来源：

1. **ReactFlow 的 `.react-flow__nodesselection-rect` 被样式化后始终显示**
   - 项目 CSS 把 `.react-flow__nodesselection-rect` 设成了实线+半透明填充（与截图一致）。
   - 之前的修复只在「非多选」状态隐藏它；但用户截图正是**多选/框选后**的状态，因此该矩形仍然可见，和每个节点的选中边框叠加。

2. **自接管的 `pea-selection-overlay` 在 mouseup 后不会淡出**
   - `SelectionOverlay` 用 `requestAnimationFrame` 轮询 `window.__selDragging`。
   - 它的 `useEffect` 依赖数组为空，导致 `tick` 闭包中的 `rect` 永远是初始值 `null`。
   - 拖拽结束、``__selDragging=false` 后，`else if (rect && rect.active)` 判断的是闭包里的旧 `null`，永远走不进 fade-out 分支，overlay 一旦显示就不会消失。

## 修复内容

| 文件 | 改动 | 说明 |
|---|---|---|
| `pea-server/web/src/styles/index.css` | 1. 把 `.react-flow__nodesselection-rect` 从「非多选时隐藏」改为**所有状态隐藏**。<br>2. 去掉之前给它的背景/边框样式，避免被 RF 运行时注入覆盖后重新可见。 | 彻底消除 RF 选中集合矩形与节点选中边框叠加的"两个框"。单选/多选/框选都只靠节点自身边框 + 我们自己的 `pea-selection-overlay` 反馈。 |
| `pea-server/web/src/components/CanvasEditor.tsx` | 修复 `SelectionOverlay` 的 stale closure：引入 `rectRef`，在 rAF 循环中读取最新 `rect`，确保拖拽结束后能进入 fade-out 分支并移除 DOM。 | 解决"鼠标放开选择框不消失"。 |
| `pea-server/web/src/store/canvas.ts` | 保留之前改动：`groupNodes` 在 `clearSelection()` 后调用 `select(gid)`。 | 打组完成后主动选中 group 容器，给用户明确反馈。 |

## 关键代码片段

### SelectionOverlay 修复

```tsx
function SelectionOverlay() {
  const [rect, setRect] = useState<... | null>(null);
  // rAF 循环在挂载时只创建一次，必须读 ref 才能拿到最新 rect
  const rectRef = useRef(rect);
  useEffect(() => { rectRef.current = rect; }, [rect]);

  useEffect(() => {
    let raf = 0;
    let hideTimer: ReturnType<typeof setTimeout> | null = null;
    const tick = () => {
      const w = window as any;
      const last = w.__lastSelRect;
      const flag = !!w.__selDragging;
      const currentRect = rectRef.current;

      if (flag && last) {
        // ... 绘制选区
      } else if (currentRect && currentRect.active) {
        setRect({ ...currentRect, active: false });
        if (!hideTimer) {
          hideTimer = setTimeout(() => { setRect(null); hideTimer = null; }, 120);
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); if (hideTimer) clearTimeout(hideTimer); };
  }, []);
  // ...
}
```

### CSS 彻底隐藏 nodesselection-rect

```css
.react-flow__selection,
.react-flow__nodesselection-rect {
  display: none !important;
}
```

## 验证结果

- `npx tsc --noEmit` 通过。
- `verify/verify_group_fix.py` 通过：打组后只剩 group 容器边框 + 顶部 group 工具条，无残留选区框。
- 新增 `verify/verify_selection_box_fix.py` 通过：
  - 初始状态无选区矩形。
  - 真实拖拽框选两个节点后，`selectedIds = ['n1', 'n2']`。
  - `.react-flow__nodesselection-rect` 即使仍在 DOM 中，其 `display` 也为 `none`（不可见）。
  - `.pea-selection-overlay` 在 mouseup 后 120ms 内淡出并移除。
  - 点击画布空白取消选择后无残留。

## 截图

- 拖拽中（自接管 overlay 正常显示）：`verify/shots/selbox_during_drag_*.png`
- 框选完成（无残留大选区框）：`verify/shots/selbox_after_drag_*.png`
- 取消选择后（完全干净）：`verify/shots/selbox_cleared_*.png`
- 打组完成（无叠加选区框）：`verify/shots/grpf_after_group_*.png`
