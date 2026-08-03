/**
 * 文本节点格式化工具条（内联版）—— 升级版。
 *
 * 由 PeaNode 在选中单个 text 节点时渲染到 .pea-node-chrome 内，
 * 随节点平移、大小恒定（父层已 counter-scale）。
 *
 * 升级内容：
 *  - 全部使用 SVG 图标替代文字标签
 *  - 新增：下划线 / 删除线 / 引用 / 行内代码 / 分割线
 *  - 新增：4色快速选色器
 *  - 每个按钮带 tooltip 提示
 */
interface TextNodeToolbarProps {
  editorRef: React.RefObject<HTMLDivElement | null>;
  className?: string;
  style?: React.CSSProperties;
}

export default function TextNodeToolbar({ editorRef, className = '', style }: TextNodeToolbarProps) {
  const exec = (cmd: string, value?: string) => {
    editorRef.current?.focus();
    // formatBlock 在多数浏览器要求传入带尖括号的标签名（如 <h1>），否则 Chrome 会静默失败
    const v = cmd === 'formatBlock' && value ? `<${value.toLowerCase()}>` : value;
    document.execCommand(cmd, false, v);
  };

  /* ── 图标按钮组件 ── */
  const Btn = ({
    title,
    children,
    onClick,
    colorDot,
  }: {
    title: string;
    children?: React.ReactNode;
    onClick: () => void;
    colorDot?: string;
  }) => (
    <button
      type="button"
      className={`tnt-btn${colorDot ? ' tnt-btn-color' : ''}`}
      aria-label={title}
      title={title}
      // 关键：mousedown 阶段 preventDefault，点击按钮时不让编辑区失焦/丢失选区，
      // 否则 execCommand 会因选区丢失而对「错误位置」或「无选区」生效，表现成"点了没反应"。
      onMouseDown={(e) => e.preventDefault()}
      onClick={(e) => { e.preventDefault(); onClick(); }}
    >
      {colorDot ? <span className="tnt-color-dot" style={{ background: colorDot }} /> : children}
    </button>
  );

  const Sep = () => <span className="tnt-sep" />;

  return (
    <div
      className={`tnt-bar ${className}`}
      style={style}
      role="toolbar"
      aria-label="文本格式"
      onClick={(e) => e.stopPropagation()}
    >
      {/* ── 标题组 ── */}
      <Btn title="一级标题" onClick={() => exec('formatBlock', 'H1')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M4 12h8"/><path d="M4 6v12"/><path d="M12 6v12"/><path d="M18 10a2 2 0 114 0c0 1.1-.9 2-2 2h-2"/></svg>
      </Btn>
      <Btn title="二级标题" onClick={() => exec('formatBlock', 'H2')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M4 12h8"/><path d="M4 6v12"/><path d="M12 6v12"/><path d="M17.5 10.5h.05"/><path d="M17.5 13.5h.05"/></svg>
      </Btn>
      <Btn title="三级标题" onClick={() => exec('formatBlock', 'H3')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M4 12h8"/><path d="M4 6v12"/><path d="M12 6v12"/><path d="M17 11h3M18.5 9.5v3"/></svg>
      </Btn>
      <Btn title="正文段落" onClick={() => exec('formatBlock', 'P')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M17 10H3M17 14H3M17 18H7M21 6H3"/></svg>
      </Btn>

      <Sep />

      {/* ── 字体样式组 ── */}
      <Btn title="粗体 (Ctrl+B)" onClick={() => exec('bold')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M7 4h5.5a3.5 3.5 0 010 7H7V4zM7 11h6.5a3.5 3.5 0 010 7H7v-7z"/></svg>
      </Btn>
      <Btn title="斜体 (Ctrl+I)" onClick={() => exec('italic')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="19" y1="4" x2="10" y2="4"/><line x1="14" y1="20" x2="5" y2="20"/><line x1="15" y1="4" x2="9" y2="20"/></svg>
      </Btn>
      <Btn title="下划线 (Ctrl+U)" onClick={() => exec('underline')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 4v6a6 6 0 0012 0V4"/><line x1="4" y1="20" x2="20" y2="20"/></svg>
      </Btn>
      <Btn title="删除线" onClick={() => exec('strikeThrough')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M16 4H9a3 3 0 000 6h6a3 3 0 010 6H7"/><line x1="4" y1="12" x2="20" y2="12"/></svg>
      </Btn>

      <Sep />

      {/* ── 列表组 ── */}
      <Btn title="无序列表" onClick={() => exec('insertUnorderedList')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="5" cy="6" r="1.5" fill="currentColor" stroke="none"/><circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="5" cy="18" r="1.5" fill="currentColor" stroke="none"/></svg>
      </Btn>
      <Btn title="有序列表" onClick={() => exec('insertOrderedList')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><line x1="10" y1="6" x2="21" y2="6"/><line x1="10" y1="12" x2="21" y2="12"/><line x1="10" y1="18" x2="21" y2="18"/><text x="4" y="7.5" fontSize="7" fill="currentColor" stroke="none" fontWeight="600">1</text><text x="4" y="13.5" fontSize="7" fill="currentColor" stroke="none" fontWeight="600">2</text><text x="4" y="19.5" fontSize="7" fill="currentColor" stroke="none" fontWeight="600">3</text></svg>
      </Btn>

      <Sep />

      {/* ── 特殊格式组 ── */}
      <Btn title="引用块" onClick={() => exec('formatBlock', 'BLOCKQUOTE')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M3 21c3 0 7-1 7-5V4c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V21zm10 0c3 0 7-1 7-5V4c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3z" opacity="0.85"/></svg>
      </Btn>
      <Btn title="行内代码" onClick={() => exec('formatBlock', 'PRE')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
      </Btn>
      <Btn title="分割线" onClick={() => exec('insertHorizontalRule')}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><line x1="3" y1="12" x2="21" y2="12"/></svg>
      </Btn>

      <Sep />

      {/* ── 颜色选择组 ── */}
      <Btn title="蓝色" colorDot="#1fa2dc" onClick={() => exec('foreColor', '#1fa2dc')} />
      <Btn title="红色" colorDot="#e74c3c" onClick={() => exec('foreColor', '#e74c3c')} />
      <Btn title="绿色" colorDot="#27ae60" onClick={() => exec('foreColor', '#27ae60')} />
      <Btn title="橙色/警告" colorDot="#f39c12" onClick={() => exec('foreColor', '#f39c12')} />
    </div>
  );
}
