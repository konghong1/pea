/**
 * 探针页（仅用于本地 E2E 排查，不参与生产构建）。
 *
 * 目的：在**不依赖后端**的前提下，用**真实的 TextNodeToolbar 组件 + 真实的 index.css**
 * 复现「文本节点选中后，上方功能条（边框框）里的 H1/粗体/颜色等全部点了没反应」。
 *
 * 这里逐行复刻 PeaNode.tsx 中 text 节点的编辑态逻辑（editing / contentEditable /
 * onMouseDown 进编辑态 / onBlur 退编辑态 / 工具条按 selected 渲染），
 * 保证复现出来的行为与真实节点一致。
 */
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import TextNodeToolbar from '../components/TextNodeToolbar';
import TextNodeEditorModal from '../components/TextNodeEditorModal';
import '../styles/index.css';

declare global {
  interface Window {
    __probe: {
      /** 编辑区当前 innerHTML */
      html: () => string;
      /** React editing 状态 */
      editing: () => boolean;
      /** 编辑区 DOM 是否真的可编辑 */
      contentEditable: () => boolean;
      /** 编辑区 class 变化次数（闪动检测） */
      classFlips: () => number;
      /** class 变化轨迹 */
      classTrace: () => string[];
      /** 当前 document.activeElement 的 class */
      active: () => string;
      /** 重置计数 */
      reset: () => void;
    };
  }
}

function ProbeTextNode() {
  const editRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState(false);
  const [editing, setEditing] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [html, setHtml] = useState('这是一段用于验证格式化功能的文本内容。');

  const isSingleSelected = selected;

  // ── 以下 3 段逐行复刻 PeaNode.tsx ─────────────────────────────
  // 1) store html → DOM（PeaNode L146-151）
  useEffect(() => {
    if (editRef.current && document.activeElement !== editRef.current) {
      if (editRef.current.innerHTML.trim() !== html.trim()) editRef.current.innerHTML = html;
    }
  }, [html]);

  // 2) 取消选中时强制退出编辑态（PeaNode L157-159）
  useEffect(() => {
    if (!selected && editing) setEditing(false);
  }, [selected, editing]);

  // 3) 进入编辑态时聚焦 + 光标到末尾（PeaNode L163-176）
  useEffect(() => {
    if (editing && editRef.current) {
      const el = editRef.current;
      el.focus();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      const sel = window.getSelection();
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(range);
      }
    }
  }, [editing]);

  // 4) 打开全屏编辑弹窗时取消选中并退出编辑态（PeaNode L180-186 修复版）
  useEffect(() => {
    if (modalOpen) {
      setEditing(false);
      setSelected(false);
    }
  }, [modalOpen]);

  // onEditBlur（复刻 PeaNode L224-235 修复版）
  const onEditBlur = (e: React.FocusEvent<HTMLDivElement>) => {
    if (editRef.current) setHtml(editRef.current.innerHTML);
    const next = e.relatedTarget as HTMLElement | null;
    if (next?.closest?.('.tnt-bar, .node-input-bar, .tne-modal')) return;
    setEditing(false);
  };

  // ── 探针挂载 ───────────────────────────────────────────────
  // 计数必须放 ref：MutationObserver 若随 editing 重建，跨编辑态的抖动就统计不到了
  const flipsRef = useRef(0);
  const traceRef = useRef<string[]>([]);
  const editingRef = useRef(editing);
  editingRef.current = editing;

  useEffect(() => {
    const el = editRef.current;
    if (!el) return;
    const mo = new MutationObserver((recs) => {
      for (const r of recs) {
        if (r.attributeName === 'class' || r.attributeName === 'contenteditable') {
          flipsRef.current += 1;
          traceRef.current.push(
            `${r.attributeName}=${(r.target as HTMLElement).getAttribute(r.attributeName!)}`,
          );
        }
      }
    });
    mo.observe(el, { attributes: true, attributeFilter: ['class', 'contenteditable'] });
    window.__probe = {
      html: () => editRef.current?.innerHTML ?? '',
      editing: () => editingRef.current,
      contentEditable: () => !!editRef.current?.isContentEditable,
      classFlips: () => flipsRef.current,
      classTrace: () => traceRef.current.slice(),
      active: () => (document.activeElement as HTMLElement)?.className ?? '',
      reset: () => {
        flipsRef.current = 0;
        traceRef.current.length = 0;
      },
    };
    return () => mo.disconnect();
  }, []);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: '#0d0d12',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      // 点击空白 = 取消选中
      onMouseDown={() => setSelected(false)}
    >
      <div
        id="probe-node"
        className={`pea-node ${selected ? 'selected' : ''} pea-node-text`}
        style={{ '--pea-node-width': '360px', position: 'relative' } as React.CSSProperties}
        onMouseDown={(e) => {
          // 点节点任意位置 = 选中（复刻 ReactFlow 的选中行为）
          e.stopPropagation();
          setSelected(true);
        }}
      >
        {/* 节点 chrome：工具条按 isSingleSelected 渲染（复刻 PeaNode L352-355） */}
        <div className="pea-node-chrome" data-zoom="1.00">
          <div className="pea-node-chrome-fixed">
            {isSingleSelected && (
              <TextNodeToolbar
                editorRef={editRef}
                onRequestEditing={() => setEditing(true)}
                onAfterExec={(h) => setHtml(h)}
              />
            )}
          </div>
        </div>

        <div className="pea-node-body-card" style={{ height: 220 }}>
          <div className="pea-node-text-wrap">
            <div
              id="probe-edit"
              ref={editRef}
              className={`pea-node-text-edit ${editing ? 'is-editing nodrag' : ''}`}
              contentEditable={editing}
              suppressContentEditableWarning
              data-placeholder={editing ? '' : '双击开始编辑…'}
              onInput={() => setHtml(editRef.current?.innerHTML ?? '')}
              onBlur={onEditBlur}
              onMouseDown={(e) => {
                // 复刻 PeaNode L402-415 的 text 分支
                e.stopPropagation();
                setSelected(true);
                if (!editing) setEditing(true);
              }}
            />
          </div>
        </div>

        {/* 模拟下方「边框框」输入栏：复刻 NodeChatPrompt 的 node-input-bar
            （只保留会抢焦点的按钮，用于验证点它是否把编辑态踢掉 + 闪动）。 */}
        {isSingleSelected && (
          <div className="pea-node-editor-anchor">
            <div
              id="probe-input-bar"
              className="node-input-bar node-chat-prompt nodrag nopan placed-below"
              onMouseDown={(e) => e.stopPropagation()}
            >
              <div className="node-input-status">
                <div className="node-input-status-left">
                  <button id="probe-model-chip" type="button" className="node-input-model-chip">
                    <span className="node-model-chip-name">模型</span>
                  </button>
                </div>
                <div className="node-input-status-right">
                  <button id="probe-mic" type="button" className="node-input-icon-btn">
                    🎤
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 测试入口：模拟「已选中但未进入编辑态」这一真实可达状态
          （新建节点自动选中 / 框选 / 点过输入栏后 blur 都会落到这个状态）。 */}
      <button
        id="probe-select-only"
        style={{ position: 'fixed', left: 8, top: 8, zIndex: 99999 }}
        onMouseDown={(e) => {
          e.stopPropagation();
          e.preventDefault();
        }}
        onClick={() => setSelected(true)}
      >
        select-only
      </button>

      {/* 双击文本节点弹出的全屏编辑弹窗（问题①） */}
      <button
        id="probe-open-modal"
        style={{ position: 'fixed', left: 110, top: 8, zIndex: 99999 }}
        onMouseDown={(e) => {
          e.stopPropagation();
          e.preventDefault();
        }}
        onClick={() => setModalOpen(true)}
      >
        open-modal
      </button>
      <TextNodeEditorModal
        open={modalOpen}
        initialHtml={html}
        onSave={(h) => {
          setHtml(h);
          setModalOpen(false);
        }}
        onCancel={() => setModalOpen(false)}
      />
    </div>
  );
}

createRoot(document.getElementById('probe-root')!).render(<ProbeTextNode />);
