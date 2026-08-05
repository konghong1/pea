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
  /**
   * 通知宿主节点进入编辑态。
   * 工具条是按「节点被选中」渲染的，而编辑区只有在 editing 态才 contentEditable=true；
   * exec 会先同步打开 DOM 的 contentEditable，再用这个回调把 React 状态补齐，
   * 否则下一次 render 会把 contentEditable 重新关掉。
   */
  onRequestEditing?: () => void;
  /** execCommand 之后把最新 HTML 回写 store（execCommand 不保证触发 React onInput） */
  onAfterExec?: (html: string) => void;
  className?: string;
  style?: React.CSSProperties;
}

/** 作用于「选区」的内联命令：没有选区时执行等于没效果，需要先把整段选上 */
const INLINE_CMDS = new Set(['bold', 'italic', 'underline', 'strikeThrough', 'foreColor']);

export default function TextNodeToolbar({
  editorRef,
  onRequestEditing,
  onAfterExec,
  className = '',
  style,
}: TextNodeToolbarProps) {
  const exec = (cmd: string, value?: string) => {
    const el = editorRef.current;
    if (!el) return;

    // ① 自愈可编辑态 —— 本次修复的根因所在。
    //    工具条的可见条件是「节点被选中」(isSingleSelected)，
    //    但编辑区的可编辑条件是「editing 态」(contentEditable={editing})，两者并不一致：
    //    新建节点自动选中、框选、以及点过下方输入栏被 blur 之后，都处于
    //    「工具条看得见、编辑区 contentEditable=false」的状态。
    //    此时 document.execCommand 会静默返回 false、DOM 毫无变化，
    //    表现就是用户说的「这个边框框功能全部不能使用」。
    //    这里必须**同步**打开 DOM（不能等 React 下一帧），因为 execCommand
    //    要求在当前事件里就存在可编辑目标。
    if (!el.isContentEditable) {
      el.setAttribute('contenteditable', 'true');
      onRequestEditing?.();
    }

    el.focus({ preventScroll: true });

    // ② 修复选区 —— 第二个「点了没反应」的来源。
    //    焦点可能刚从下方输入栏/工具条移回来，此时 selection 要么为空、
    //    要么落在编辑区之外，execCommand 会作用到错误位置或直接失效。
    const sel = window.getSelection();
    const range = sel && sel.rangeCount > 0 ? sel.getRangeAt(0) : null;
    const inside = !!range && el.contains(range.commonAncestorContainer);
    // 内联命令在光标折叠时只影响「之后输入的字」，用户点了看不到任何变化，
    // 因此折叠状态下直接把整段选上，让点击必有可见效果。
    const needSelectAll = !inside || (INLINE_CMDS.has(cmd) && range!.collapsed);

    if (needSelectAll && sel) {
      const r = document.createRange();
      r.selectNodeContents(el);
      sel.removeAllRanges();
      sel.addRange(r);
    }

    // formatBlock 在多数浏览器要求传入带尖括号的标签名（如 <h1>），否则 Chrome 会静默失败
    const v = cmd === 'formatBlock' && value ? `<${value.toLowerCase()}>` : value;
    document.execCommand(cmd, false, v);

    // ③ 回写 store：强制打开的 contentEditable 场景下不能只依赖 React 的 onInput
    onAfterExec?.(el.innerHTML);
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
