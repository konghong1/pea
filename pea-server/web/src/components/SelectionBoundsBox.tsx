import { useEffect, useRef, useState } from 'react';
import { createPortal, flushSync } from 'react-dom';
import { useViewport } from 'reactflow';
import { useCanvas } from '../store/canvas';

/** 多选时若选中集合含组节点，不渲染包围框（避免与组框视觉上冲突）。 */
function selectedIncludesGroup(selectedIds: string[], nodes: any[]): boolean {
  for (const id of selectedIds) {
    const n = nodes.find((x) => x.id === id);
    if (n && n.type === 'group') return true;
  }
  return false;
}

declare global {
  interface Window {
    __peaSelDragActive?: boolean;
  }
}

/**
 * 持久选中包围框：仅在**多选**（>=2 个节点）时绘制。
 *
 * 拖拽交互（2026-08）：
 * - pointerdown 捕获阶段检测点击是否命中框体空白区域
 * - 若是：preventDefault() 阻止 ReactFlow selectionOnDrag 清除选中，
 *   设置 __peaSelDragActive=true 阻止 onPaneClick 清选中。
 * - 拖拽期间：**暂停 rAF 循环**（避免竞争），调用 setState 更新节点（边自动跟随），
 *   直接操作选择框 DOM（不调 setBounds）。
 * - 松开时：恢复 rAF 循环。
 */
export default function SelectionBoundsBox() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const nodes = useCanvas((s) => s.nodes);
  const { x: vx, y: vy, zoom } = useViewport();
  const _containsGroup = selectedIncludesGroup(selectedIds, nodes);

  const [bounds, setBounds] = useState<{
    left: number; top: number; width: number; height: number;
  } | null>(null);
  const rafRef = useRef<number | undefined>(undefined);
  const lastKeyRef = useRef('');
  const boxRef = useRef<HTMLDivElement>(null);

  // 用 ref 持有最新值
  const selectedIdsRef = useRef(selectedIds);
  const nodesRef = useRef(nodes);
  const vxRef = useRef(vx);
  const vyRef = useRef(vy);
  const zoomRef = useRef(zoom);
  useEffect(() => { selectedIdsRef.current = selectedIds; });
  useEffect(() => { nodesRef.current = nodes; });
  useEffect(() => { vxRef.current = vx; vyRef.current = vy; zoomRef.current = zoom; });

  // 拖拽状态
  const draggingRef = useRef(false);
  const origPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const curOffsetRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const dragStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // ── rAF 循环：更新选择框位置（非拖拽时运行）────────────────────────────
  useEffect(() => {
    if (selectedIds.length < 2) {
      setBounds(null);
      lastKeyRef.current = '';
      return;
    }

    const loop = () => {
      const rects: DOMRect[] = [];
      for (const id of selectedIds) {
        const el = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) rects.push(r);
      }
      if (rects.length > 0) {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const r of rects) {
          minX = Math.min(minX, r.left);
          minY = Math.min(minY, r.top);
          maxX = Math.max(maxX, r.right);
          maxY = Math.max(maxY, r.bottom);
        }
        const key = `${minX},${minY},${maxX},${maxY}`;
        if (lastKeyRef.current !== key) {
          lastKeyRef.current = key;
          setBounds({
            left: Math.round(minX),
            top: Math.round(minY),
            width: Math.ceil(maxX - minX),
            height: Math.ceil(maxY - minY),
          });
        }
      }
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => { if (rafRef.current != null) cancelAnimationFrame(rafRef.current); };
  }, [selectedIds.join(','), nodes.length, vx, vy, zoom]);

  // ── pointerdown 捕获：启动拖拽 ───────────────────────────────────────────
  useEffect(() => {
    if (selectedIds.length < 2) return;

    const onDown = (e: PointerEvent) => {
      if (draggingRef.current) return;
      if (e.button !== 0) return;

      const box = boxRef.current;
      if (!box) return;

      const r = box.getBoundingClientRect();
      const hitBox = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      if (!hitBox) return;

      const target = e.target as HTMLElement | null;
      if (target?.closest('.react-flow__node')) return;

      // 命中选择框空白区域
      e.preventDefault();
      draggingRef.current = true;
      window.__peaSelDragActive = true;

      // 快照节点原始位置
      const idSet = new Set(selectedIdsRef.current);
      const origPositions = new Map<string, { x: number; y: number }>();
      for (const id of selectedIdsRef.current) {
        const n = nodesRef.current.find((n) => n.id === id);
        if (n) origPositions.set(id, { x: n.position.x, y: n.position.y });
      }
      origPositionsRef.current = origPositions;

      const { x: cvx, y: cvy, z: cz } = { x: vxRef.current, y: vyRef.current, z: zoomRef.current };
      dragStartRef.current = { x: (e.clientX - cvx) / cz, y: (e.clientY - cvy) / cz };
      curOffsetRef.current = { x: 0, y: 0 };

      // 暂停 rAF 循环
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = undefined;
      }

      const onMove = (ev: PointerEvent) => {
        if (!draggingRef.current) return;
        const { x: curVx, y: curVy, z: curZoom } = { x: vxRef.current, y: vyRef.current, z: zoomRef.current };
        const curX = (ev.clientX - curVx) / curZoom;
        const curY = (ev.clientY - curVy) / curZoom;
        curOffsetRef.current = { x: curX - dragStartRef.current.x, y: curY - dragStartRef.current.y };

        // ── 更新节点位置（触发 ReactFlow 重新计算 nodeInternals，边自动跟随）──
        // 注意：这里会触发 ReactFlow 重渲，但 rAF 已暂停，所以没有竞争
        // 【修复】使用 flushSync 强制同步渲染，确保 DOM 已更新后再读取位置
        // 否则批量更新机制下读到的还是旧 DOM，导致选择框位置跳动/晃动
        flushSync(() => {
          useCanvas.setState((s) => ({
            nodes: s.nodes.map((n) => {
              if (!idSet.has(n.id)) return n;
              const orig = origPositionsRef.current.get(n.id);
              if (!orig) return n;
              return {
                ...n,
                position: { x: orig.x + curOffsetRef.current.x, y: orig.y + curOffsetRef.current.y },
              };
            }),
          }));
        });

        // ── 直接更新选择框位置（不调 setBounds，避免 React 重渲）──
        // 从当前节点状态计算（此时节点位置已更新）
        const currentNodes = useCanvas.getState().nodes;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const id of selectedIdsRef.current) {
          const el = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`);
          if (!el) continue;
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            minX = Math.min(minX, rect.left);
            minY = Math.min(minY, rect.top);
            maxX = Math.max(maxX, rect.right);
            maxY = Math.max(maxY, rect.bottom);
          }
        }
        if (boxRef.current && isFinite(minX)) {
          boxRef.current.style.left = `${Math.round(minX)}px`;
          boxRef.current.style.top = `${Math.round(minY)}px`;
          boxRef.current.style.width = `${Math.ceil(maxX - minX)}px`;
          boxRef.current.style.height = `${Math.ceil(maxY - minY)}px`;
        }
      };

      const onUp = () => {
        draggingRef.current = false;
        window.__peaSelDragActive = false;

        // 恢复 rAF 循环
        rafRef.current = undefined;

        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
    };

    window.addEventListener('pointerdown', onDown, true);
    return () => window.removeEventListener('pointerdown', onDown, true);
  }, [selectedIds.length]);

  if (!bounds || selectedIds.length < 2 || _containsGroup) return null;
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      ref={boxRef}
      className="pea-selection-bounds"
      data-testid="pea-selection-bounds"
      style={{
        left: bounds.left,
        top: bounds.top,
        width: bounds.width,
        height: bounds.height,
        pointerEvents: 'none',
        cursor: 'move',
      }}
    />,
    document.body,
  );
}

