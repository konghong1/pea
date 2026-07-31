/**
 * 文本节点格式化工具条（内联版）。
 * 由 PeaNode 在选中单个 text 节点时渲染到 .pea-node-chrome 内，
 * 随节点平移、大小恒定（父层已 counter-scale），不再使用全局 rAF + position:fixed。
 */
interface TextNodeToolbarProps {
  editorRef: React.RefObject<HTMLDivElement | null>;
  className?: string;
  style?: React.CSSProperties;
}

export default function TextNodeToolbar({ editorRef, className = '', style }: TextNodeToolbarProps) {
  const exec = (cmd: string, value?: string) => {
    editorRef.current?.focus();
    document.execCommand(cmd, false, value);
  };

  return (
    <div
      className={`tnt-bar ${className}`}
      style={style}
      role="toolbar"
      aria-label="文本格式"
      onClick={(e) => e.stopPropagation()}
    >
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
  );
}
