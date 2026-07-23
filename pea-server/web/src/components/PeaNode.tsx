import { useEffect, useRef, useState } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { useCanvas, PeaNodeData } from '../store/canvas';

/**
 * 画布节点 4 大类型（对齐参考图截图3/4/5/6）：
 *  - text：节点上方"≡ Text"标签 + contentEditable 方框（占位"双击开始编辑..."）
 *  - image：节点上方圆形"上传"按钮 + 左上"Image"标签 + 图片占位图标
 *  - video：节点上方圆形"上传"按钮 + 左上"Video"标签 + 视频占位图标
 *  - audio：节点上方圆形"上传"按钮 + 左上"Audio"标签 + 音乐占位图标
 * 全部用左右两侧的连接手柄（截图2），默认透明，hover/选中时显示。
 */
export default function PeaNode({ id, data }: NodeProps<PeaNodeData>) {
  const update = useCanvas((s) => s.updateNodeData);
  const selected = useCanvas((s) => s.selectedIds.includes(id));
  const [hovered, setHovered] = useState(false);
  const editRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const kind = data.kind;
  const isText = kind === 'text';
  const isMedia = kind === 'image' || kind === 'video' || kind === 'audio';

  // text 节点：仅在挂载/切换节点时把 store 的 html 同步进可编辑区（避免输入时光标跳变）
  useEffect(() => {
    if (isText && editRef.current) {
      const want = data.html ?? '';
      if (editRef.current.innerHTML.trim() !== want.trim()) editRef.current.innerHTML = want;
    }
    // 仅在节点 id 变化时重灌内容
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // 选中 text 节点时自动聚焦可编辑区
  useEffect(() => {
    if (isText && selected && editRef.current) {
      editRef.current.focus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, id]);

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    // 真实项目走预签名直传；这里先用 objectURL 预览展示
    const url = URL.createObjectURL(f);
    update(id, { url, meta: { ...(data.meta ?? {}), fileName: f.name } });
    e.target.value = '';
  };

  return (
    <div
      className={`pea-node ${selected ? 'selected' : ''} ${hovered ? 'hover' : ''} pea-node-${kind}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      data-kind={kind}
    >
      {/* 左右连接手柄（截图2 ⊕ 位置）。handle 自己的 onPointerDown 触发连接，外层 wrapper 阻止 mousedown 冒泡到 node，
          避免 ReactFlow useDrag 把 handle 拖动当成节点拖动启动。 */}
      <span
        style={{ position: 'absolute', left: -10, top: '50%', transform: 'translateY(-50%)', width: 24, height: 24, zIndex: 10 }}
        onMouseDown={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <Handle type="target" position={Position.Left} className="pea-handle" />
      </span>
      <span
        style={{ position: 'absolute', right: -10, top: '50%', transform: 'translateY(-50%)', width: 24, height: 24, zIndex: 10 }}
        onMouseDown={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <Handle type="source" position={Position.Right} className="pea-handle" />
      </span>

      {/* 顶部：text=标签，image/video/audio=上传按钮（截图4/5/6） */}
      {isText ? (
        <div className="pea-node-tag-pill">
          <span className="pea-node-tag-icon" aria-hidden>
            ≡
          </span>
          <span>Text</span>
        </div>
      ) : (
        <>
          <button
            type="button"
            className="pea-node-upload-btn"
            onClick={(e) => {
              e.stopPropagation();
              fileRef.current?.click();
            }}
            aria-label="上传"
            title="上传"
          >
            <span aria-hidden>↑</span>
            <span>上传</span>
          </button>
          <input
            ref={fileRef}
            type="file"
            hidden
            accept={kind === 'image' ? 'image/*' : kind === 'video' ? 'video/*' : 'audio/*'}
            onChange={onPickFile}
          />
        </>
      )}

      {/* 节点主体 */}
      <div className="pea-node-body-card">
        {isText ? (
          <div
            ref={editRef}
            className="pea-node-text-edit nodrag"
            contentEditable={selected}
            suppressContentEditableWarning
            data-placeholder="双击开始编辑…"
            onInput={() => update(id, { html: editRef.current?.innerHTML })}
            onBlur={() => update(id, { html: editRef.current?.innerHTML })}
          />
        ) : (
          <div className="pea-node-media-card">
            <span className="pea-node-media-label">
              {kind === 'image' ? '🖼' : kind === 'video' ? '▷' : '♫'} {labelOf(kind)}
            </span>
            {data.url ? (
              kind === 'image' ? (
                <img src={data.url} alt={data.label} className="pea-node-media-preview" />
              ) : kind === 'video' ? (
                <video src={data.url} controls className="pea-node-media-preview" />
              ) : (
                <audio src={data.url} controls className="pea-node-audio" />
              )
            ) : (
              <div className="pea-node-media-placeholder" aria-hidden>
                {kind === 'image' ? (
                  <svg viewBox="0 0 24 24" width="56" height="56" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <rect x="3" y="4" width="18" height="16" rx="2" />
                    <circle cx="8.5" cy="9.5" r="1.5" />
                    <path d="M3 16l5-5 4 4 3-3 6 6" />
                  </svg>
                ) : kind === 'video' ? (
                  <svg viewBox="0 0 24 24" width="56" height="56" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <rect x="3" y="5" width="18" height="14" rx="2" />
                    <path d="M10 9l5 3-5 3z" fill="currentColor" stroke="none" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" width="56" height="56" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <path d="M9 18V5l12-2v13" />
                    <circle cx="6" cy="18" r="3" />
                    <circle cx="18" cy="16" r="3" />
                  </svg>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function labelOf(k: string): string {
  if (k === 'image') return 'Image';
  if (k === 'video') return 'Video';
  if (k === 'audio') return 'Audio';
  return '';
}