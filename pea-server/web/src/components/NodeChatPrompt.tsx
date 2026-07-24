import { useEffect, useRef, useState } from 'react';
import { useViewport } from 'reactflow';
import { useCanvas } from '../store/canvas';
import { useAgent } from '../store/agent';

interface KindCfg {
  label: string;
  placeholder: string;
  model: string;
  modelIcon: string;
  params: { icon: string; text: string }[];
}

export const KIND_CFG: Record<string, KindCfg> = {
  text: {
    label: '文本',
    placeholder: '描述任何你想要生成的内容',
    model: 'Gemini 3.1 Flash Lite',
    modelIcon: '✦',
    params: [],
  },
  image: {
    label: '图片',
    placeholder: '描述任何你想要生成的内容',
    model: 'Seedream 5.0 Lite',
    modelIcon: '📊',
    params: [{ icon: '⊞', text: '1:1 · 2K' }],
  },
  video: {
    label: '视频',
    placeholder: '描述你想生成的内容，或输入 /@ 唤出素材库与快捷操作',
    model: 'Seedance 2.0 Mini',
    modelIcon: '📊',
    params: [{ icon: '⚙', text: '全能参考 · 16:9 · 480p · 5s' }, { icon: '🔊', text: '' }],
  },
  audio: {
    label: '音频',
    placeholder: '描述你想要生成的任何内容',
    model: 'Mureka V8',
    modelIcon: '🌊',
    params: [
      { icon: '♫', text: '音乐' },
      { icon: '☰', text: '自适应' },
    ],
  },
  generate: {
    label: '生成',
    placeholder: '描述你想生成的内容',
    model: 'Gemini 3.1 Flash Lite',
    modelIcon: '✦',
    params: [],
  },
};

/**
 * 节点下方全宽输入栏（对齐截图3/4/5/6）。
 * 选中单个节点时在节点正下方浮现与节点同宽的输入栏。
 *
 * 定位策略（关键修复 2026-07-24）：
 *  - 不再用 document.querySelector 实时查询节点 DOM（React 重渲期间会返回 null → 输入栏闪退）。
 *  - 改为基于 store 中的节点 position + measured width/height + reactflow viewport 变换，
 *    确定性地计算 fixed 视口坐标。位置随拖动/缩放/平移实时更新，永不闪烁、永不丢失。
 *  - 切换节点时自动恢复该节点的 data.prompt，支持“接着上次编辑的内容继续写”。
 */
export default function NodeChatPrompt() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const selectedId = useCanvas((s) => s.selectedId);
  const nodes = useCanvas((s) => s.nodes);
  const update = useCanvas((s) => s.updateNodeData);
  const push = useAgent((s) => s.push);
  const setOpen = useAgent((s) => s.setOpen);
  const viewport = useViewport();

  const single = selectedIds.length === 1 ? selectedIds[0] : selectedId;
  const sel = single ? nodes.find((n) => n.id === single) : null;

  const [rect, setRect] = useState<{ left: number; top: number; width: number } | null>(null);
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const prevSingleRef = useRef<string | null>(null);
  // 按节点 id 缓存输入草稿：切换节点再切回时"接着上次编辑的内容继续写"
  const draftRef = useRef<Record<string, string>>({});
  // rAF 循环保持位置实时同步（拖动/缩放/平移时输入栏跟随节点）
  const rafRef = useRef<number>();
  const lastRectRef = useRef('');

  // 节点切换：恢复该节点的草稿（优先）/已保存 prompt，否则清空
  useEffect(() => {
    if (!single) {
      setText('');
      prevSingleRef.current = null;
      return;
    }
    if (single !== prevSingleRef.current) {
      prevSingleRef.current = single;
      const node = nodes.find((n) => n.id === single);
      const restored = draftRef.current[single] ?? node?.data.prompt ?? '';
      setText(restored);
      setTimeout(() => inputRef.current?.focus(), 60);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [single, nodes]);

  // 确定性定位：优先读取节点真实渲染底边（getBoundingClientRect），
  // rAF 循环保持拖动/缩放/平移时输入栏始终跟随节点。
  // 仅在无选中节点时停止循环。
  useEffect(() => {
    if (!sel || !single) {
      setRect(null);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const compute = (): { left: number; top: number; width: number } | null => {
      const nodeEl = document.querySelector(
        `.react-flow__node[data-id="${single}"]`,
      ) as HTMLElement | null;
      if (nodeEl) {
        const r = nodeEl.getBoundingClientRect();
        const anchorBottom = r.bottom;
        const centerX = r.left + r.width / 2;
        const width = Math.max(360, Math.round(r.width));
        return { left: Math.round(centerX - width / 2), top: Math.round(anchorBottom + 16), width };
      }
      // DOM 不可用时回退到 viewport 变换计算
      const { x: vx, y: vy, zoom } = viewport;
      const fx = sel.position.x;
      const fy = sel.position.y;
      const w = (sel.width ?? 260) * zoom;
      const h = (sel.height ?? 160) * zoom;
      const screenX = fx * zoom + vx;
      const screenY = fy * zoom + vy;
      const width = Math.max(360, Math.round(w));
      return { left: Math.round(screenX + w / 2 - width / 2), top: Math.round(screenY + h + 16), width };
    };

    const loop = () => {
      const next = compute();
      if (next) {
        const key = `${next.left},${next.top},${next.width}`;
        if (lastRectRef.current !== key) {
          lastRectRef.current = key;
          setRect(next);
        }
      }
      rafRef.current = requestAnimationFrame(loop);
    };

    // 立即算一次
    const initial = compute();
    if (initial) setRect(initial);

    // 启动 rAF 循环
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [sel, single, viewport.x, viewport.y, viewport.zoom, sel?.position.x, sel?.position.y, sel?.width, sel?.height]);

  if (!sel || !rect || !single) return null;

  const kind = sel.data.kind;
  const cfg = KIND_CFG[kind] ?? KIND_CFG.text;

  const submit = () => {
    const t = text.trim();
    if (!t) return;
    // 写入节点 prompt：既便于提交后恢复，也作为生成/对话的上下文
    update(single, { prompt: t });
    push('user', `[${sel.data.label || cfg.label}] ${t}`);
    setOpen(true);
    draftRef.current[single] = '';
    setText('');
    // 提交后保持输入栏打开，方便连续输入
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setText('');
    }
  };

  return (
    <div
      className="node-input-bar node-chat-prompt"
      style={{ left: rect.left, top: rect.top, width: rect.width, position: 'fixed' }}
      role="dialog"
      aria-label={`对 ${cfg.label} 节点提问`}
      data-kind={kind}
    >
      <div className="node-input-tools">
        {(kind === 'image' || kind === 'video') && (
          <button type="button" className="node-input-tool" title="特效/灵感" aria-label="特效">
            ✦
          </button>
        )}
        <button type="button" className="node-input-tool" title="附件" aria-label="附件">
          +
        </button>
      </div>
      <textarea
        ref={inputRef}
        className="node-input-textarea node-chat-prompt-input"
        placeholder={cfg.placeholder}
        value={text}
        rows={2}
        onChange={(e) => {
          const v = e.target.value;
          setText(v);
          if (single) draftRef.current[single] = v;
        }}
        onKeyDown={onKey}
        onMouseDown={(e) => e.stopPropagation()}
      />
      <div className="node-input-status">
        <div className="node-input-status-left">
          <span className="node-input-model" title={cfg.model}>
            <span className="node-input-model-icon" aria-hidden>
              {cfg.modelIcon}
            </span>
            <span>{cfg.model}</span>
          </span>
          {cfg.params.map((p, i) => (
            <span key={i} className="node-input-param">
              <span className="node-input-param-icon" aria-hidden>
                {p.icon}
              </span>
              <span>{p.text}</span>
            </span>
          ))}
        </div>
        <div className="node-input-status-right">
          <button type="button" className="node-input-icon-btn" title="语音输入" aria-label="语音">
            🎤
          </button>
          {kind !== 'audio' && (
            <span className="node-input-icon-btn" title="1× 倍速">1×</span>
          )}
          <span className="node-input-tapies" title="Tapies 余额">
            <span className="node-input-tapies-icon" aria-hidden>
              💎
            </span>
            <span>{kind === 'text' ? '1' : '-'}</span>
          </span>
          <button
            type="button"
            className="node-input-send node-chat-prompt-send"
            title="发送 (Enter)"
            aria-label="发送"
            disabled={!text.trim()}
            onMouseDown={(e) => e.preventDefault()}
            onClick={submit}
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  );
}
