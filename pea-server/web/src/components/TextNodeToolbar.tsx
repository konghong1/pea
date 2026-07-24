import { useEffect, useRef, useState } from 'react';
import { useViewport } from 'reactflow';
import { useCanvas } from '../store/canvas';

/**
 * 文本节点浮动格式化工具条（对齐截图2）。
 * 当选中单个 text 节点时，在节点正上方浮现暗色胶囊工具条，
 * 提供 H1/H2/H3/段落/加粗/斜体/列表等富文本命令。
 */
export default function TextNodeToolbar() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const selectedId = useCanvas((s) => s.selectedId);
  const nodes = useCanvas((s) => s.nodes);
  const viewport = useViewport();

  const single = selectedIds.length === 1 ? selectedIds[0] : selectedId;
  const sel = single ? nodes.find((n) => n.id === single) : null;

  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const rafRef = useRef<number>();
  const lastPosRef = useRef('');

  useEffect(() => {
    if (!sel || sel.data.kind !== 'text' || !single) {
      setPos(null);
      return;
    }

    const updatePos = () => {
      const el = document.querySelector(
        `.react-flow__node[data-id="${single}"]`,
      ) as HTMLElement | null;
      if (!el) {
        setPos(null);
        return;
      }
      const r = el.getBoundingClientRect();
      const left = Math.round(r.left + r.width / 2);
      const top = Math.round(r.top - 48);
      const key = `${left},${top}`;
      if (lastPosRef.current !== key) {
        lastPosRef.current = key;
        setPos({ left, top });
      }
    };

    const loop = () => {
      updatePos();
      rafRef.current = requestAnimationFrame(loop);
    };
    updatePos();
    rafRef.current = requestAnimationFrame(loop);
    window.addEventListener('resize', updatePos);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      window.removeEventListener('resize', updatePos);
    };
  }, [sel, single, viewport.x, viewport.y, viewport.zoom]);

  if (!sel || sel.data.kind !== 'text' || !pos) return null;

  const exec = (cmd: string, value?: string) => {
    const editor = document.querySelector(
      `.react-flow__node[data-id="${single}"] .pea-node-text-edit`,
    ) as HTMLElement | null;
    if (!editor) return;
    editor.focus();
    document.execCommand(cmd, false, value);
  };

  return (
    <div
      className="text-node-toolbar"
      style={{ left: pos.left, top: pos.top }}
      role="toolbar"
      aria-label="文本格式"
    >
      <div className="tnt-bar">
        <button type="button" className="tnt-color" aria-label="颜色" onClick={() => exec('foreColor', '#0984E3')} />
        <span className="tnt-sep" />
        <button type="button" className="tnt-btn" onClick={() => exec('formatBlock', 'H1')}>
          H1
        </button>
        <button type="button" className="tnt-btn" onClick={() => exec('formatBlock', 'H2')}>
          H2
        </button>
        <button type="button" className="tnt-btn" onClick={() => exec('formatBlock', 'H3')}>
          H3
        </button>
        <button type="button" className="tnt-btn" onClick={() => exec('formatBlock', 'P')}>
          ¶
        </button>
        <span className="tnt-sep" />
        <button type="button" className="tnt-btn" onClick={() => exec('bold')}>
          B
        </button>
        <button type="button" className="tnt-btn italic" onClick={() => exec('italic')}>
          I
        </button>
        <button type="button" className="tnt-btn" onClick={() => exec('insertUnorderedList')}>
          ☰
        </button>
        <button type="button" className="tnt-btn" onClick={() => exec('insertOrderedList')}>
          1.
        </button>
      </div>
    </div>
  );
}
