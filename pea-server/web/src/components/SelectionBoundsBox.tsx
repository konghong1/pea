import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useViewport } from 'reactflow';
import { useCanvas } from '../store/canvas';

/**
 * 持久选中包围框：仅在**多选**（>=2 个节点）时绘制。
 *
 * 设计要点：
 * - 单选时节点自身的 1.5px 蓝边 + box-shadow 已经清楚地表达了"已选中"，
 *   再叠一个外层蓝框会出现"两个框"（用户反馈：拖走节点后还能看到框）。
 *   因此单选（selectedIds.length === 1）直接返回 null，把视觉重心留给节点本身。
 * - 多选时仍按选中节点的 DOM 包围盒（min/max 四边）绘制一个透明填充矩形框，
 *   明确标示当前选中了哪些节点。
 * - 实时 rAF 跟随节点拖动 / 视口缩放，保证框始终贴合选中节点。
 * - pointer-events:none + portal 到 body，不拦截节点交互。
 */
export default function SelectionBoundsBox() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const nodes = useCanvas((s) => s.nodes);
  const { x, y, zoom } = useViewport();

  const [bounds, setBounds] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const rafRef = useRef<number>();
  const lastKeyRef = useRef('');

  useEffect(() => {
    // 单选：节点自身已有 1.5px 蓝边 + ring box-shadow，足够表达选中态。
    // 多选时才需要这个外层 bounds 框把多个节点圈出来。
    if (selectedIds.length < 2) {
      setBounds(null);
      lastKeyRef.current = '';
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const update = () => {
      const rects: DOMRect[] = [];
      for (const id of selectedIds) {
        const el = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        // 过滤掉尚未完成测量或已被隐藏的节点
        if (r.width > 0 && r.height > 0) rects.push(r);
      }
      if (rects.length === 0) return;

      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const r of rects) {
        minX = Math.min(minX, r.left);
        minY = Math.min(minY, r.top);
        maxX = Math.max(maxX, r.right);
        maxY = Math.max(maxY, r.bottom);
      }

      const key = `${minX.toFixed(1)},${minY.toFixed(1)},${maxX.toFixed(1)},${maxY.toFixed(1)}`;
      if (lastKeyRef.current !== key) {
        lastKeyRef.current = key;
        // 关键修复（问题3）：坐标取整。原值来自 getBoundingClientRect() 的 sub-pixel 小数，
        // 配 1.5px 边框在 fractional 位置时会偶发不渲染，表现为「上/下边框时有时无」。
        // left/top 用 round 落到整数像素起点，width/height 用 ceil 保证框始终完整包住节点。
        setBounds({
          left: Math.round(minX),
          top: Math.round(minY),
          width: Math.ceil(maxX - minX),
          height: Math.ceil(maxY - minY),
        });
      }
    };

    const loop = () => {
      update();
      rafRef.current = requestAnimationFrame(loop);
    };

    update();
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [selectedIds.join(','), nodes.length, x, y, zoom]);

  if (!bounds || selectedIds.length < 2) return null;
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="pea-selection-bounds"
      data-testid="pea-selection-bounds"
      style={{
        left: bounds.left,
        top: bounds.top,
        width: bounds.width,
        height: bounds.height,
      }}
    />,
    document.body,
  );
}
