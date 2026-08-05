/**
 * 文本节点全屏编辑弹窗 —— 双击文本节点时弹出。
 *
 * 设计理念：
 *  - 玻璃态 (glassmorphism) + 现代感，与 pea 品牌风格一致
 *  - 左右分屏：左侧编辑 + 右侧实时预览
 *  - 内置格式工具栏（H1-H3 / 粗体 / 斜体 / 列表 / 引用 / 代码）
 *  - 底部状态栏：字数统计 + 保存状态
 *  - 支持 Ctrl+S 快捷保存 / Esc 关闭
 *  - 格式按「选区」或「插入点」应用：有选区只格式化选区；无选区时后续输入继承格式
 */
import { useEffect, useRef, useState, useCallback, useMemo, memo } from 'react';
import { Modal } from 'antd';

interface TextNodeEditorModalProps {
  open: boolean;
  initialHtml: string;
  onSave: (html: string) => void;
  onCancel: () => void;
}

export default function TextNodeEditorModal({ open, initialHtml, onSave, onCancel }: TextNodeEditorModalProps) {
  const editorRef = useRef<HTMLDivElement | null>(null);
  const previewRef = useRef<HTMLDivElement | null>(null);
  const [saved, setSaved] = useState(true);
  const [wordCount, setWordCount] = useState(0);
  // 工具栏激活态：光标当前所在的块级格式（h1/p/blockquote...），用于高亮反馈
  const [activeBlock, setActiveBlock] = useState('');
  // 工具栏激活态：inline 命令是否生效（bold/italic...）
  const [activeInline, setActiveInline] = useState<Record<string, boolean>>({});
  // 标记：是否由工具栏 exec 触发的 input，用于跳过不必要的同步防止重复
  const isExecRef = useRef(false);
  // rAF timer：合并快速连续的预览同步，减少重渲染频率
  const inputRafRef = useRef<number | undefined>(undefined);
  // 标记：是否已完成首次内容灌注，避免 layout effect 重复覆盖用户输入
  const seededRef = useRef(false);
  // rAF timer：合并选区变化带来的激活态同步
  const fmtRafRef = useRef<number | undefined>(undefined);
  // 原生 color input 引用，用于触发系统取色器
  const colorInputRef = useRef<HTMLInputElement>(null);
  // 点击自定义颜色按钮前暂存当前选区，避免 color input 抢焦点导致 foreColor 找不到选区
  const savedRangeRef = useRef<Range | null>(null);

  // 字数统计 helper
  const countText = useCallback((html: string) => {
    const tmp = document.createElement('div');
    tmp.innerHTML = html ?? '';
    return (tmp.innerText ?? '').replace(/\s/g, '').length;
  }, []);

  // 关键修复：Modal 经 Portal/destroyOnHidden 挂载，普通 effect 里 ref 经常为 null。
  // 用回调 ref 在编辑区 DOM 真正挂载的瞬间灌入初始 HTML 并聚焦；
  // 预览区通过 requestAnimationFrame 延迟一拍同步，确保 previewRef 已赋值。
  // seededRef 保证一次打开周期内只初始化一次，不会覆盖用户正在输入的内容。
  const setEditorRef = useCallback(
    (el: HTMLDivElement | null) => {
      editorRef.current = el;
      if (!el || seededRef.current) return;
      const html = initialHtml ?? '';
      el.innerHTML = html;
      setSaved(true);
      setWordCount(countText(html));
      seededRef.current = true;

      requestAnimationFrame(() => {
        // 同步预览区（此时 previewRef 已可用）
        if (previewRef.current) previewRef.current.innerHTML = html;
        el.focus();
        const sel = window.getSelection();
        if (sel) {
          const range = document.createRange();
          range.selectNodeContents(el);
          range.collapse(false);
          sel.removeAllRanges();
          sel.addRange(range);
        }
      });
    },
    [initialHtml, countText],
  );

  // 关闭弹窗时重置 seededRef，保证下次打开重新灌入最新 initialHtml
  useEffect(() => {
    if (!open) seededRef.current = false;
  }, [open]);

  // 同步预览区 + 字数统计（用 rAF 合并，避免高频重渲染导致闪动）。
  // 预览区用 ref 直写 innerHTML，不依赖 React state 重渲染——这是消除"编辑框/工具条闪动"的关键。
  const syncPreview = useCallback(() => {
    if (inputRafRef.current) cancelAnimationFrame(inputRafRef.current);
    inputRafRef.current = requestAnimationFrame(() => {
      const el = editorRef.current;
      if (!el) return;
      const content = el.innerHTML;
      if (previewRef.current) previewRef.current.innerHTML = content;
      setWordCount(countText(content));
      setSaved(false);
    });
  }, [countText]);

  // 同步工具栏激活态：根据当前光标所在的块标签 / inline 命令状态，高亮对应按钮。
  // 这样用户点完 H1 后，H1 按钮会亮起，清楚知道后续输入将是一级标题。
  const syncActiveFormats = useCallback(() => {
    const el = editorRef.current;
    if (!el) return;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const range = sel.getRangeAt(0);
    if (!el.contains(range.commonAncestorContainer)) return; // 选区不在编辑区，忽略

    const block = findCurrentBlock(el, range.commonAncestorContainer);
    setActiveBlock(block ? block.tagName.toLowerCase() : '');

    const next: Record<string, boolean> = {};
    for (const c of INLINE_STATE_CMDS) {
      try {
        next[c] = document.queryCommandState(c);
      } catch {
        next[c] = false;
      }
    }
    setActiveInline(next);
  }, []);

  // 用 rAF 节流选区变化，避免高频 setState 引起的重渲染/抖动
  const scheduleSyncActiveFormats = useCallback(() => {
    if (fmtRafRef.current) cancelAnimationFrame(fmtRafRef.current);
    fmtRafRef.current = requestAnimationFrame(() => {
      fmtRafRef.current = undefined;
      syncActiveFormats();
    });
  }, [syncActiveFormats]);

  // 快捷键：Ctrl+S 保存 / Esc 关闭
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    }
  };

  const exec = useCallback((cmd: string, value?: string) => {
    const el = editorRef.current;
    if (!el) return;

    // 由工具栏按钮的 onMouseDown（已 preventDefault）调用：此时编辑区焦点与选区完好，
    // execCommand 必定作用在正确选区上。先 focus 兜底，再执行命令并同步预览。
    el.focus();
    isExecRef.current = true;

    if (cmd === 'formatBlock' && value) {
      // 块级格式（H1-H3 / P / BLOCKQUOTE / PRE）按选区/插入点精细应用，
      // 不再使用原生的 formatBlock（原生会把整个段落变成目标块）。
      applyBlockFormat(el, value);
    } else {
      // inline / list / hr 继续使用原生 execCommand，浏览器已支持选区/插入点行为。
      document.execCommand(cmd, false, value);
    }

    isExecRef.current = false;
    // 同步预览 + 字数（rAF 合并，不触发整个 Modal 重渲染 → 不闪动）
    syncPreview();
    // 同步工具栏激活态高亮，让用户看见"当前处于哪种格式"
    scheduleSyncActiveFormats();
  }, [syncPreview, scheduleSyncActiveFormats]);

  // 打开系统取色器：先保存当前选区，再触发隐藏的 <input type="color"> 点击。
  // 这样用户选择颜色后，handleColorChange 可以恢复选区并正确应用 foreColor。
  const openColorPicker = useCallback(() => {
    const el = editorRef.current;
    if (!el) return;
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0) {
      const range = sel.getRangeAt(0);
      if (el.contains(range.commonAncestorContainer)) {
        savedRangeRef.current = range.cloneRange();
      }
    }
    colorInputRef.current?.click();
  }, []);

  // 原生 color input 选择颜色后的回调
  const handleColorChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const color = e.target.value;
    if (!color) return;
    const el = editorRef.current;
    if (!el) return;

    el.focus();
    const sel = window.getSelection();
    if (savedRangeRef.current && sel) {
      sel.removeAllRanges();
      sel.addRange(savedRangeRef.current);
    }

    isExecRef.current = true;
    document.execCommand('foreColor', false, color);
    isExecRef.current = false;
    syncPreview();
    scheduleSyncActiveFormats();
    savedRangeRef.current = null;
  }, [syncPreview, scheduleSyncActiveFormats]);

  // 选区变化时实时同步激活态高亮（仅 open 时监听）
  useEffect(() => {
    if (!open) return;
    const handler = () => scheduleSyncActiveFormats();
    document.addEventListener('selectionchange', handler);
    return () => document.removeEventListener('selectionchange', handler);
  }, [open, scheduleSyncActiveFormats]);

  // 清理 RAF timer，防止组件卸载后 setState
  useEffect(() => {
    return () => {
      if (inputRafRef.current) cancelAnimationFrame(inputRafRef.current);
      if (fmtRafRef.current) cancelAnimationFrame(fmtRafRef.current);
    };
  }, []);

  const handleSave = () => {
    // 直接读编辑区 DOM（非受控），无需维护 html state
    onSave(editorRef.current?.innerHTML ?? '');
    setSaved(true);
  };

  const handleCancel = () => {
    if (!saved) {
      // 有未保存的修改时提示
      const ok = confirm('有未保存的修改，确定要关闭吗？');
      if (!ok) return;
    }
    onCancel();
  };

  const handleInput = () => {
    // exec 触发时会同步调用 syncPreview，跳过此处避免重复；用户真实输入才走这里
    if (isExecRef.current) return;
    syncPreview();
    scheduleSyncActiveFormats();
  };

  // 工具栏配置：用 useMemo 避免每次输入都重建配置对象，减少重渲染
  const toolbarGroups = useMemo(
    () => [
      { label: <TneIconHeading level={1} />, title: '一级标题 (Ctrl+Alt+1)', cmd: 'formatBlock', value: 'H1' },
      { label: <TneIconHeading level={2} />, title: '二级标题 (Ctrl+Alt+2)', cmd: 'formatBlock', value: 'H2' },
      { label: <TneIconHeading level={3} />, title: '三级标题 (Ctrl+Alt+3)', cmd: 'formatBlock', value: 'H3' },
      { label: <span style={{ fontSize: 12, fontWeight: 500 }}>正文</span>, title: '正文段落', cmd: 'formatBlock', value: 'P' },
      null,
      { label: <><b>B</b></>, title: '粗体 (Ctrl+B)', cmd: 'bold' },
      { label: <em>I</em>, title: '斜体 (Ctrl+I)', cmd: 'italic' },
      { label: <u>U</u>, title: '下划线 (Ctrl+U)', cmd: 'underline' },
      { label: <s>S</s>, title: '删除线', cmd: 'strikeThrough' },
      null,
      { label: <TneIconList ordered={false} />, title: '无序列表', cmd: 'insertUnorderedList' },
      { label: <TneIconList ordered />, title: '有序列表', cmd: 'insertOrderedList' },
      null,
      { label: <>"</>, title: '引用块', cmd: 'formatBlock', value: 'BLOCKQUOTE' },
      { label: <><code style={{ fontSize: 11 }}>&lt;/&gt;</code></>, title: '行内代码', cmd: 'formatBlock', value: 'PRE' },
      { label: <>—</>, title: '分割线', cmd: 'insertHorizontalRule' },
      null,
      { label: <span className="tne-color-dot" style={{ background: '#1fa2dc' }} />, title: '蓝色', cmd: 'foreColor', value: '#1fa2dc' },
      { label: <span className="tne-color-dot" style={{ background: '#e74c3c' }} />, title: '红色', cmd: 'foreColor', value: '#e74c3c' },
      { label: <span className="tne-color-dot" style={{ background: '#27ae60' }} />, title: '绿色', cmd: 'foreColor', value: '#27ae60' },
      { label: <span className="tne-color-dot" style={{ background: '#f39c12' }} />, title: '橙色', cmd: 'foreColor', value: '#f39c12' },
      { label: <span className="tne-color-dot" style={{ background: '#111111' }} />, title: '黑色', cmd: 'foreColor', value: '#111111' },
    ],
    []
  );

  return (
    <Modal
      open={open}
      onCancel={handleCancel}
      onOk={handleSave}
      okText="保存 (Ctrl+S)"
      cancelText="取消"
      width={860}
      centered
      closable={true}
      maskClosable={false}
      className="text-node-editor-modal"
      destroyOnHidden
      styles={{
        body: { padding: 0, overflow: 'hidden' },
        header: {
          background: 'transparent',
          borderBottom: '1px solid var(--tne-border, rgba(128,128,140,0.14))',
          padding: '16px 24px',
        },
        footer: {
          borderTop: '1px solid var(--tne-border, rgba(128,128,140,0.14))',
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        },
      }}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ color: 'var(--tne-accent, #1fa2dc)', flexShrink: 0 }}>
            <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          <span style={{ fontWeight: 600, fontSize: 15 }}>文本编辑器</span>
          {!saved && (
            <span className="tne-unsaved-dot" title="未保存">●</span>
          )}
        </div>
      }
    >
      {/* 工具栏 */}
      <div className="tne-toolbar">
        {toolbarGroups.map((item, idx) =>
          item ? (
            <ToolBtn
              key={item.title}
              label={item.label}
              title={item.title}
              cmd={item.cmd}
              value={item.value}
              active={item.value ? activeBlock === item.value.toLowerCase() : !!activeInline[item.cmd]}
              onExec={exec}
            />
          ) : (
            <div key={`sep-${idx}`} className="tne-toolbar-sep" />
          )
        )}
        <button
          type="button"
          className="tne-tool-btn tne-tool-btn--color-picker"
          title="自定义颜色"
          aria-label="自定义颜色"
          onMouseDown={(e) => {
            e.preventDefault();
            openColorPicker();
          }}
        >
          <span className="tne-color-ring" />
        </button>
        <input
          ref={colorInputRef}
          type="color"
          className="tne-color-input"
          onInput={handleColorChange}
          onBlur={() => { savedRangeRef.current = null; }}
          aria-hidden="true"
        />
      </div>

      {/* 编辑区域 */}
      <div className="tne-editor-wrap">
        <div className="tne-editor-pane">
          <div className="tne-pane-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
            <span>编辑</span>
          </div>
          <div
            ref={setEditorRef}
            className="tne-editor-content"
            contentEditable
            suppressContentEditableWarning
            onInput={handleInput}
            onKeyDown={handleKeyDown}
            onKeyUp={scheduleSyncActiveFormats}
            onMouseUp={scheduleSyncActiveFormats}
            onClick={scheduleSyncActiveFormats}
          />
        </div>

        {/* 分隔条 */}
        <div className="tne-divider" />

        {/* 预览区域 */}
        <div className="tne-preview-pane">
          <div className="tne-pane-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
            <span>预览</span>
          </div>
          <div className="tne-preview-content" ref={previewRef} />
        </div>
      </div>

      {/* Footer 左侧：字数统计 */}
      <span style={{ fontSize: 12, color: 'var(--tne-muted, #888)' }}>
        {wordCount} 字符
      </span>
    </Modal>
  );
}

/* ── 内联命令集合 ── */
const INLINE_CMDS = new Set(['bold', 'italic', 'underline', 'strikeThrough', 'foreColor']);

/* ── 块级标签集合 ── */
const BLOCK_TAGS = new Set(['p', 'h1', 'h2', 'h3', 'blockquote', 'pre', 'div']);

/* ── 需要查询激活态的 inline 命令 ── */
const INLINE_STATE_CMDS = ['bold', 'italic', 'underline', 'strikeThrough'];

/**
 * 应用块级格式：按选区包装，或在折叠选区处插入空块等待输入。
 * 替代原生 document.execCommand('formatBlock')，避免「一点按钮整段都变」的问题。
 */
function applyBlockFormat(editor: HTMLElement, tagName: string) {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return;

  editor.focus();
  const range = sel.getRangeAt(0);
  const tag = tagName.toLowerCase();

  // 选区若漂到编辑区外，兜底放到末尾
  if (!editor.contains(range.commonAncestorContainer)) {
    const fallback = document.createRange();
    fallback.selectNodeContents(editor);
    fallback.collapse(false);
    sel.removeAllRanges();
    sel.addRange(fallback);
  }

  const block = findCurrentBlock(editor, range.commonAncestorContainer);

  if (range.collapsed) {
    // 折叠选区：光标已在同类型块内 → toggle 解除；否则插入空目标块，后续输入继承格式
    if (block && block.tagName.toLowerCase() === tag) {
      unwrapBlock(block);
    } else {
      // 折叠选区：在光标处插入一个带 <br> 占位符的空目标块，并把选区移入块内。
      // 这样后续输入会落在块标签里，自然继承格式；若用完全空标签，浏览器容易把光标「漏」到块外。
      const wrapper = document.createElement(tag);
      const br = document.createElement('br');
      wrapper.appendChild(br);
      range.insertNode(wrapper);
      const newRange = document.createRange();
      newRange.setStartBefore(br);
      newRange.collapse(true);
      sel.removeAllRanges();
      sel.addRange(newRange);
    }
  } else {
    // 有选区：若选区完全位于同类型块内 → toggle 解除；否则只包装选区内容
    if (block && block.tagName.toLowerCase() === tag && isRangeInside(range, block)) {
      unwrapBlock(block);
    } else {
      const wrapper = document.createElement(tag);
      const content = range.extractContents();
      wrapper.appendChild(content);
      range.insertNode(wrapper);
      const newRange = document.createRange();
      newRange.selectNodeContents(wrapper);
      sel.removeAllRanges();
      sel.addRange(newRange);
    }
  }
}

/** 查找 node 在 editor 内的最近块级祖先 */
function findCurrentBlock(editor: HTMLElement, node: Node): HTMLElement | null {
  let cur: Node | null = node;
  while (cur && cur !== editor) {
    if (cur.nodeType === Node.ELEMENT_NODE) {
      const el = cur as HTMLElement;
      if (BLOCK_TAGS.has(el.tagName.toLowerCase())) return el;
    }
    cur = cur.parentNode;
  }
  return null;
}

/** 判断 range 是否完全在 el 内部 */
function isRangeInside(range: Range, el: HTMLElement): boolean {
  return el.contains(range.startContainer) && el.contains(range.endContainer);
}

/** 解除块级包装，保留子内容并合并文本节点 */
function unwrapBlock(block: HTMLElement) {
  const parent = block.parentNode;
  if (!parent) return;
  while (block.firstChild) {
    parent.insertBefore(block.firstChild, block);
  }
  parent.removeChild(block);
  if (parent.nodeType === Node.ELEMENT_NODE) {
    (parent as HTMLElement).normalize();
  }
}

/* ── 工具栏按钮（提取为顶层 memo 组件，禁止在父组件内定义，避免每次输入都 remount） ── */
interface ToolBtnProps {
  label: React.ReactNode;
  title: string;
  cmd: string;
  value?: string;
  active?: boolean;
  onExec: (cmd: string, value?: string) => void;
}

const ToolBtn = memo(({ label, title, cmd, value, active, onExec }: ToolBtnProps) => (
  <button
    type="button"
    className={`tne-tool-btn${active ? ' tne-tool-btn--active' : ''}`}
    title={title}
    aria-label={title}
    aria-pressed={active}
    data-active={active ? '1' : undefined}
    onMouseDown={(e) => {
      e.preventDefault();
      onExec(cmd, value);
    }}
  >
    {label}
  </button>
));
ToolBtn.displayName = 'ToolBtn';

/* ── 内联 SVG 图标组件 ── */

function TneIconHeading({ level }: { level: 1 | 2 | 3 }) {
  const size = level === 1 ? 16 : level === 2 ? 14 : 12;
  const weight = level === 1 ? 700 : level === 2 ? 600 : 500;
  return <span style={{ fontSize: size, fontWeight: weight, lineHeight: 1 }}>H{level}</span>;
}

function TneIconList({ ordered }: { ordered: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      {ordered ? (
        <>
          <line x1="10" y1="6" x2="21" y2="6" /><line x1="10" y1="12" x2="21" y2="12" /><line x1="10" y1="18" x2="21" y2="18" />
          <text x="3" y="8" fontSize="9" fill="currentColor" stroke="none" fontWeight="600">1</text>
          <text x="3" y="14" fontSize="9" fill="currentColor" stroke="none" fontWeight="600">2</text>
          <text x="3" y="20" fontSize="9" fill="currentColor" stroke="none" fontWeight="600">3</text>
        </>
      ) : (
        <>
          <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
          <circle cx="4" cy="6" r="1.5" fill="currentColor" stroke="none" /><circle cx="4" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle cx="4" cy="18" r="1.5" fill="currentColor" stroke="none" />
        </>
      )}
    </svg>
  );
}
