/**
 * 文本节点全屏编辑弹窗 —— 双击文本节点时弹出。
 *
 * 设计理念：
 *  - 玻璃态 (glassmorphism) + 现代感，与 pea 品牌风格一致
 *  - 左右分屏：左侧编辑 + 右侧实时预览
 *  - 内置格式工具栏（H1-H3 / 粗体 / 斜体 / 列表 / 引用 / 代码）
 *  - 底部状态栏：字数统计 + 保存状态
 *  - 支持 Ctrl+S 快捷保存 / Esc 关闭
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { Modal } from 'antd';

interface TextNodeEditorModalProps {
  open: boolean;
  initialHtml: string;
  onSave: (html: string) => void;
  onCancel: () => void;
}

export default function TextNodeEditorModal({ open, initialHtml, onSave, onCancel }: TextNodeEditorModalProps) {
  const [html, setHtml] = useState(initialHtml);
  const editorRef = useRef<HTMLDivElement>(null);
  const [saved, setSaved] = useState(true);
  const [wordCount, setWordCount] = useState(0);

  // 打开时把初始 HTML 灌入可编辑区（仅一次）。之后以 DOM 为唯一真源，
  // 不再用 dangerouslySetInnerHTML 回写，避免每次按键都被 React 重置导致光标跳到行首。
  useEffect(() => {
    if (open && editorRef.current) {
      editorRef.current.innerHTML = initialHtml ?? '';
      setHtml(initialHtml ?? '');
      setSaved(true);
      requestAnimationFrame(() => {
        editorRef.current?.focus();
        const sel = window.getSelection();
        if (sel && editorRef.current) {
          const range = document.createRange();
          range.selectNodeContents(editorRef.current);
          range.collapse(false);
          sel.removeAllRanges();
          sel.addRange(range);
        }
      });
    }
    // 仅在打开瞬间初始化；编辑过程中 initialHtml 不变，故不再重置，避免光标跳动
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // 字数统计
  useEffect(() => {
    const text = editorRef.current?.innerText ?? '';
    setWordCount(text.replace(/\s/g, '').length);
  }, [html]);

  // 打开时聚焦编辑器
  useEffect(() => {
    if (open && editorRef.current) {
      // 下一帧聚焦并移动光标到末尾
      requestAnimationFrame(() => {
        editorRef.current?.focus();
        const sel = window.getSelection();
        if (sel && editorRef.current) {
          const range = document.createRange();
          range.selectNodeContents(editorRef.current);
          range.collapse(false);
          sel.removeAllRanges();
          sel.addRange(range);
        }
      });
    }
  }, [open]);

  // 快捷键：Ctrl+S 保存 / Esc 关闭
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    }
  }, [html]);

  const exec = (cmd: string, value?: string) => {
    editorRef.current?.focus();
    // formatBlock 在多数浏览器要求传入带尖括号的标签名（如 <h1>），否则 Chrome 会静默失败
    const v = cmd === 'formatBlock' && value ? `<${value.toLowerCase()}>` : value;
    document.execCommand(cmd, false, v);
    // 触发 contentEditable 的 input 事件以同步 state
    editorRef.current?.dispatchEvent(new Event('input', { bubbles: true }));
  };

  const handleSave = () => {
    onSave(html);
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
    if (editorRef.current) {
      setHtml(editorRef.current.innerHTML);
      setSaved(false);
    }
  };

  /* ── 工具栏按钮 ── */
  const ToolBtn = ({ label, title, onClick }: { label: React.ReactNode; title: string; onClick: () => void }) => (
    <button type="button" className="tne-tool-btn" title={title} onClick={(e) => { e.preventDefault(); onClick(); }}>
      {label}
    </button>
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
      destroyOnClose
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
        <div className="tne-toolbar-group">
          <ToolBtn label={<TneIconHeading level={1} />} title="一级标题 (Ctrl+Alt+1)" onClick={() => exec('formatBlock', 'H1')} />
          <ToolBtn label={<TneIconHeading level={2} />} title="二级标题 (Ctrl+Alt+2)" onClick={() => exec('formatBlock', 'H2')} />
          <ToolBtn label={<TneIconHeading level={3} />} title="三级标题 (Ctrl+Alt+3)" onClick={() => exec('formatBlock', 'H3')} />
          <ToolBtn label={<span style={{ fontSize: 12, fontWeight: 500 }}>正文</span>} title="正文段落" onClick={() => exec('formatBlock', 'P')} />
        </div>
        <div className="tne-toolbar-sep" />
        <div className="tne-toolbar-group">
          <ToolBtn label={<><b>B</b></>} title="粗体 (Ctrl+B)" onClick={() => exec('bold')} />
          <ToolBtn label={<em>I</em>} title="斜体 (Ctrl+I)" onClick={() => exec('italic')} />
          <ToolBtn label={<u>U</u>} title="下划线 (Ctrl+U)" onClick={() => exec('underline')} />
          <ToolBtn label={<s>S</s>} title="删除线" onClick={() => exec('strikeThrough')} />
        </div>
        <div className="tne-toolbar-sep" />
        <div className="tne-toolbar-group">
          <ToolBtn label={<TneIconList ordered={false} />} title="无序列表" onClick={() => exec('insertUnorderedList')} />
          <ToolBtn label={<TneIconList ordered />} title="有序列表" onClick={() => exec('insertOrderedList')} />
        </div>
        <div className="tne-toolbar-sep" />
        <div className="tne-toolbar-group">
          <ToolBtn label={<>"</>} title="引用块" onClick={() => exec('formatBlock', 'BLOCKQUOTE')} />
          <ToolBtn label={<><code style={{ fontSize: 11 }}>&lt;/&gt;</code></>} title="行内代码" onClick={() => exec('formatBlock', 'PRE')} />
          <ToolBtn label={<>—</>} title="分割线" onClick={() => exec('insertHorizontalRule')} />
        </div>
        <div className="tne-toolbar-spacer" />
        <div className="tne-toolbar-group">
          <ToolBtn
            label={<span className="tne-color-dot" style={{ background: '#1fa2dc' }} />}
            title="蓝色"
            onClick={() => exec('foreColor', '#1fa2dc')}
          />
          <ToolBtn
            label={<span className="tne-color-dot" style={{ background: '#e74c3c' }} />}
            title="红色"
            onClick={() => exec('foreColor', '#e74c3c')}
          />
          <ToolBtn
            label={<span className="tne-color-dot" style={{ background: '#27ae60' }} />}
            title="绿色"
            onClick={() => exec('foreColor', '#27ae60')}
          />
          <ToolBtn
            label={<span className="tne-color-dot" style={{ background: '#f39c12' }} />}
            title="橙色"
            onClick={() => exec('foreColor', '#f39c12')}
          />
        </div>
      </div>

      {/* 编辑区域 */}
      <div className="tne-editor-wrap">
        <div className="tne-editor-pane">
          <div className="tne-pane-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
            <span>编辑</span>
          </div>
          <div
            ref={editorRef}
            className="tne-editor-content"
            contentEditable
            suppressContentEditableWarning
            onInput={handleInput}
            onKeyDown={handleKeyDown}
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
          <div className="tne-preview-content" dangerouslySetInnerHTML={{ __html: html }} />
        </div>
      </div>

      {/* Footer 左侧：字数统计 */}
      <span style={{ fontSize: 12, color: 'var(--tne-muted, #888)' }}>
        {wordCount} 字符
      </span>
    </Modal>
  );
}

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
