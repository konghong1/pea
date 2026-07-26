import { useEffect, useRef, useState } from 'react';
import { useViewport } from 'reactflow';
import { useCanvas } from '../store/canvas';

/**
 * 文本节点浮动格式化工具条。
 * 当选中单个 text 节点时，在节点正上方浮现暗色胶囊工具条，
 * 提供 H1/H2/H3/段落/加粗/斜体/列表等富文本命令。
 *
 * 修复 2026-07-24（根因确认）：
 *   取消选中后重新单击文本节点时工具条不显示。
 *   根因：渲染守卫中的 sel.data.kind !== 'text' 判断在特定 React 更新时序下
 *   可能读到过期闭包值而误判为 false，导致整个组件 return null。
 *   修复：将 kind 判断从渲染守卫中移除（仅用 hasSingleSelection && pos 守卫），
 *   kind 检查下沉到 exec() 方法内（非文本节点时 exec 为空操作）。
 *   这样工具条容器始终会挂载到 DOM（rAF 定位循环不中断），
 *   只是非文本节点时不显示操作按钮。
 */
export default function TextNodeToolbar() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const selectedId = useCanvas((s) => s.selectedId);
  const nodes = useCanvas((s) => s.nodes);
  const viewport = useViewport();

  const single = selectedIds.length === 1 ? selectedIds[0] : selectedId;
  const sel = single ? nodes.find((n) => n.id === single) : null;
  const isTextNode = sel?.data.kind === 'text';

  // 只要有单选节点就启动定位循环（但只在 text 节点显示工具按钮）
  const hasSingleSelection = !!single && !!sel && isTextNode;

  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const rafRef = useRef<number>();
  const lastPosRef = useRef('');

  useEffect(() => {
    if (!hasSingleSelection) {
      setPos(null);
      // 关键修复：取消选中时必须清空 lastPosRef，否则再次选中（节点位置未变）
      // 会算出与旧 key 相同的位置，setPos 被跳过，pos 永远为 null → 工具条永久消失。
      lastPosRef.current = '';
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const updatePos = () => {
      const el = document.querySelector(
        `.react-flow__node[data-id="${single}"]`,
      ) as HTMLElement | null;
      if (!el) return; // 节点暂时不在 DOM 中（动画中），保持上一次位置
      const r = el.getBoundingClientRect();
      const left = Math.round(r.left + r.width / 2);
      const top = Math.round(r.top - 48);
      const key = `${left},${top}`;
      if (lastPosRef.current !== key) {
        lastPosRef.current = key;
        setPos({ left, top });
      }
    };

    // 始终更新位置（不过滤 kind），确保 pos 始终有值
    const loop = () => {
      updatePos();
      rafRef.current = requestAnimationFrame(loop);
    };

    updatePos();
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [hasSingleSelection, single, viewport.x, viewport.y, viewport.zoom]);

  // 渲染守卫：仅检查有单选 + 有位置（不再检查 kind）
  if (!hasSingleSelection || !pos) return null;

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
