# 裁切功能 Bug 修复总结

## 修复日期
2026-08-27

## 修复的 Bug 总数
**17 个 Bug 全部修复完成**

---

## 🔴 P0 - 严重 Bug（3个）

### Bug 1: 裁切确认后数据未同步就关闭浮层
**文件**: `PeaNode.tsx:808-856`
**问题**: 在异步上传前就关闭浮层，失败后用户无法重试
**修复**:
- 改为上传成功后再关闭浮层
- 失败时不关闭，让用户可以重试
- 添加错误提示和重试机制

```typescript
// 修复前
setCropOpen(false); // ❌ 异步操作前就关闭
try {
  // 上传逻辑
} catch {
  // 用户看不到错误，无法重试
}

// 修复后
try {
  // 上传逻辑
  setCropOpen(false); // ✅ 成功后再关闭
  toast.success('已生成裁剪节点');
} catch {
  toast.error('裁剪失败，请重试');
  // ✅ 不关闭，让用户可以重试
}
```

---

### Bug 2: 裁切框在 zoom 变化后位置错乱
**文件**: `ImageCropOverlay.tsx:216-327`
**问题**: 从容器尺寸计算 zoom 不准确，在画布缩放后裁切框位置错误
**修复**: 从 ReactFlow viewport 读取可靠的 zoom

```typescript
// 修复前
const zoom = W > 0 ? initialFrameRect.width / W : 1; // ❌ 不可靠

// 修复后
const rfZoom = typeof window !== 'undefined' && (window as any).__rfStore?.getState?.()?.transform?.[2];
const zoom = Number.isFinite(rfZoom) && rfZoom > 0 ? rfZoom : 1; // ✅ 可靠的 zoom
```

---

### Bug 3: 拖拽时裁切框与遮罩不同步
**文件**: `ImageCropOverlay.tsx:274-296`
**问题**: 快速拖拽时遮罩可能滞后一帧，露出白边
**修复**: 使用 `requestAnimationFrame` 确保同步

```typescript
// 修复前
const move = (ev: PointerEvent) => {
  lx = ev.clientX; ly = ev.clientY;
  const next = compute(lx, ly);
  // 直接更新 DOM
  frameEl.style.transform = ...; // ❌ 可能不同步
}

// 修复后
const move = (ev: PointerEvent) => {
  lx = ev.clientX; ly = ev.clientY;
  requestAnimationFrame(() => { // ✅ 确保同步
    const next = compute(lx, ly);
    frameEl.style.transform = ...;
  });
}
```

---

## 🟡 P1 - 高优先级 Bug（4个）

### Bug 4: 裁切产物节点位置计算错误
**文件**: `PeaNode.tsx:834-841`
**问题**: 统计所有下游边导致位置跳跃
**修复**: 只统计直接作为裁切产物的下游节点

```typescript
// 修复前
const siblingCount = g.edges.filter((e) => e.source === id).length; // ❌ 所有下游边

// 修复后
const siblingCount = g.nodes.filter(n => // ✅ 只统计裁切产物节点
  n.data.clipped &&
  g.edges.some(e => e.source === id && e.target === n.id)
).length;
```

---

### Bug 5: 裁切时画布平移/缩放未完全锁定
**文件**: `CanvasEditor.tsx:1836-1887`
**问题**: 右键拖拽、Ctrl+滚轮等监听器未检查裁切状态
**修复**: 在所有画布交互监听器中检查 `cropActiveRef`

```typescript
// 修复前
const onDown = (e: PointerEvent) => {
  if (e.button !== 2) return;
  // ... 平移逻辑
}

// 修复后
const onDown = (e: PointerEvent) => {
  if (cropActiveRef.current) return; // ✅ 裁切时禁用
  if (e.button !== 2) return;
  // ... 平移逻辑
}
```

---

### Bug 6: 裁切比例切换时未保持中心
**文件**: `ImageCropOverlay.tsx:198-204`
**问题**: 切换比例时裁切框会跳到中心
**修复**: 以当前中心为基准调整尺寸

```typescript
// 修复前
setCrop(initialCropRect(W, H, originalRatio ?? null)); // ❌ 重新初始化

// 修复后
const currentCenter = { x: crop.x + crop.w / 2, y: crop.y + crop.h / 2 };
let newW = ...;
let newH = ...;
let newX = currentCenter.x - newW / 2; // ✅ 保持中心
let newY = currentCenter.y - newH / 2;
```

---

### Bug 7: 裁切导出时低分辨率警告阈值不合理
**文件**: `cropExport.ts:44`
**问题**: 只检查裁切区域的像素数，应基于目标显示尺寸判断
**修复**: 改为基于像素比（输出像素/目标物理像素）的判断

```typescript
// 修复前
export const LOW_RES_SOURCE_PX = 200; // ❌ 固定像素数
lowResSource: sw < LOW_RES_SOURCE_PX || sh < LOW_RES_SOURCE_PX

// 修复后
export const LOW_RES_RATIO_THRESHOLD = 1.5; // ✅ 像素比阈值
const pixelRatio = outWidth / targetPhysicalPx;
lowResSource = pixelRatio < LOW_RES_RATIO_THRESHOLD;
```

---

## 🟢 P2 - 中等优先级 Bug（10个）

### Bug 8: 裁切框极小时光标判断失效
**文件**: `ImageCropOverlay.tsx:360-369`
**修复**: 使用距离判断，优先匹配更近的角/边

```typescript
// 修复前：多个条件可能同时满足
if (Math.abs(cx) <= THRESHOLD_CORNER && Math.abs(cy) <= THRESHOLD_CORNER)
  setCursor('nwse-resize');

// 修复后：使用距离判断
const dist = (x: number, y: number) => Math.hypot(cx - x, cy - y);
const distances = [
  { type: 'nw', d: dist(0, 0) },
  // ...
].sort((a, b) => a.d - b.d);

if (distances[0].d <= THRESHOLD_CORNER) {
  setCursor(...); // ✅ 匹配最近的
}
```

---

### Bug 9: 裁切工具栏在小尺寸时可能溢出节点
**文件**: `index.css:8416-8435` + `ImageCropOverlay.tsx`
**修复**: 添加边界检测，计算最佳位置

```typescript
function getToolbarStyle(crop: Rect, W: number): React.CSSProperties {
  const toolbarWidth = 300;
  let left = crop.x + crop.w / 2;

  const overflowLeft = toolbarWidth / 2 - left;
  const overflowRight = left + toolbarWidth / 2 - W;

  if (overflowLeft > 0) {
    left = toolbarWidth / 2; // ✅ 边界检测
  } else if (overflowRight > 0) {
    left = W - toolbarWidth / 2;
  }

  return { left, transform: 'translateX(-50%)' };
}
```

---

### Bug 10: 裁切时 ESC 键可能被拦截
**文件**: `ImageCropOverlay.tsx:180-184`
**修复**: 使用捕获阶段监听

```typescript
// 修复前
window.addEventListener('keydown', fn);

// 修复后
window.addEventListener('keydown', fn, true); // ✅ 捕获阶段
```

---

### Bug 11: 裁切浮层点击外部关闭逻辑有问题
**文件**: `ImageCropOverlay.tsx:188-196`
**修复**: 检查是否在裁切框内

```typescript
const fn = (e: PointerEvent) => {
  const t = e.target as HTMLElement | null;
  if (!t) return;

  const inOverlay = t.closest('[data-cropping-overlay="true"]');
  const inDropdown = t.closest('.pea-crop-dropdown, .ant-dropdown-menu');
  const inFrame = frameRef.current?.contains(t); // ✅ 检查裁切框

  if (inOverlay || inDropdown || inFrame) return;
  onCloseRef.current();
};
```

---

### Bug 12: 裁切初始化时容器尺寸测量可能失败
**文件**: `ImageCropOverlay.tsx:132-144`
**修复**: 添加重试机制

```typescript
const measureWithRetry = (): Promise<{ w: number; h: number }> => {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const measured = measureStage(containerRef.current);
      if (measured && measured.w > 0 && measured.h > 0) {
        resolve(measured); // ✅ 成功
        return;
      }

      retryCount++;
      if (retryCount >= MAX_RETRIES) {
        reject(new Error('无法获取图片容器尺寸'));
        return;
      }

      requestAnimationFrame(attempt); // ✅ 重试
    };
    attempt();
  });
};
```

---

### Bug 13: 裁切节点样式处理可能导致闪烁
**文件**: `index.css:8543-8553`
**修复**: 添加过渡动画

```css
.pea-node .pea-node-body-card {
  transition: background 0.15s ease, border 0.15s ease, box-shadow 0.15s ease, border-radius 0.15s ease; /* ✅ 平滑过渡 */
}
```

---

### Bug 14: 裁切时画布缩放变量未更新
**文件**: `ImageCropOverlay.tsx` (新增)
**修复**: 缓存进入裁切时的 zoom，退出后恢复

```typescript
const [cachedZoom, setCachedZoom] = useState<number | null>(null);

useEffect(() => {
  if (!cachedZoom) {
    const zoom = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--pea-inv-zoom') || '1');
    setCachedZoom(zoom); // ✅ 缓存
  }
  return () => {
    if (cachedZoom) {
      document.documentElement.style.setProperty('--pea-inv-zoom', String(cachedZoom)); // ✅ 恢复
    }
  };
}, [cachedZoom]);
```

---

### Bug 15: 裁切自定义比例输入没有校验
**文件**: `ImageCropOverlay.tsx:476-490`
**修复**: 添加校验和错误提示

```typescript
const validate = (w: string, h: string): { valid: boolean; w?: number; h?: number } => {
  const wNum = parseFloat(w);
  const hNum = parseFloat(h);

  if (!Number.isFinite(wNum) || !Number.isFinite(hNum)) {
    setError('请输入有效数字'); // ✅ 校验
    return { valid: false };
  }

  if (wNum <= 0 || hNum <= 0) {
    setError('宽高必须大于 0');
    return { valid: false };
  }

  if (wNum > 10000 || hNum > 10000) {
    setError('宽高不能超过 10000');
    return { valid: false };
  }

  setError(null);
  return { valid: true, w: wNum, h: hNum };
};
```

---

### Bug 16: 裁切时图片可能未完全加载就显示
**文件**: `ImageCropOverlay.tsx:132-144`
**修复**: 检查图片尺寸

```typescript
loadImage(url).then(img => {
  if (!alive) return;

  // ✅ 检查图片尺寸
  if (img.naturalWidth <= 0 || img.naturalHeight <= 0) {
    toast.error('图片尺寸无效，无法裁剪');
    onClose();
    return;
  }

  naturalRef.current = { w: img.naturalWidth, h: img.naturalHeight };
  // ...
});
```

---

### Bug 17: 裁切产物节点缺少文件名元数据
**文件**: `PeaNode.tsx:811`
**修复**: 添加时间戳文件名和元数据

```typescript
const timestamp = Date.now();
const cropMeta: Record<string, unknown> = {
  fileName: `裁剪_${timestamp}.png`, // ✅ 时间戳文件名
  fileSize: blob.size,
  croppedFrom: id, // ✅ 来源节点
  croppedAt: new Date().toISOString(),
};
```

---

## 📊 Bug 修复统计

| 级别 | 数量 | 状态 |
|------|------|------|
| P0（严重） | 3 | ✅ 全部修复 |
| P1（高优） | 4 | ✅ 全部修复 |
| P2（中等） | 10 | ✅ 全部修复 |
| **总计** | **17** | **✅ 全部修复** |

---

## 🧪 建议测试场景

### P0 Bug 测试
1. **Bug 1**: 上传失败后检查是否可以重试
2. **Bug 2**: 在不同缩放级别下测试裁切框位置
3. **Bug 3**: 快速拖拽裁切框检查是否同步

### P1 Bug 测试
4. **Bug 4**: 多次裁切后检查节点位置是否正确
5. **Bug 5**: 裁切时测试右键拖拽和 Ctrl+滚轮是否被锁定
6. **Bug 6**: 切换比例检查裁切框是否保持中心
7. **Bug 7**: 裁切小区域检查分辨率警告

### P2 Bug 测试
8. **Bug 8**: 缩小裁切框到极小尺寸测试光标
9. **Bug 9**: 在边缘位置测试工具栏是否溢出
10. **Bug 10**: 裁切时按 ESC 测试是否关闭
11. **Bug 11**: 点击裁切框外部测试关闭逻辑
12. **Bug 12**: 快速打开裁切测试容器尺寸测量
13. **Bug 13**: 进入/退出裁切测试样式过渡
14. **Bug 14**: 裁切时缩放画布测试 counter-scale
15. **Bug 15**: 输入 0、负数、极大值测试自定义比例
16. **Bug 16**: 上传损坏图片测试错误处理
17. **Bug 17**: 多次裁切检查文件名是否唯一

---

## 📝 修改的文件列表

1. `pea-server/web/src/components/ImageCropOverlay.tsx` - 完整重构
2. `pea-server/web/src/components/PeaNode.tsx` - 修复裁切确认逻辑
3. `pea-server/web/src/components/CanvasEditor.tsx` - 添加裁切锁定检查
4. `pea-server/web/src/components/cropExport.ts` - 改进分辨率判断
5. `pea-server/web/src/styles/index.css` - 添加过渡动画和错误样式

---

## ✅ 修复验证

所有修复已完成并保存。建议按照上述测试场景进行端到端验证。

**修复完成时间**: 2026-08-27 14:30
**修复工程师**: AI Assistant
**修复方法**: 系统性代码审查 + 最佳实践应用
