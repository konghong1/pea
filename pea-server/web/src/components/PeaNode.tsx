import { useEffect, useRef, useState } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { useCanvas, PeaNodeData } from '../store/canvas';
import { NODE_DEF_OF, PeaNodeKind } from '../constants/nodeTypes';

/**
 * 画布节点渲染：
 *  - text：顶部标签（图标+Text） + contentEditable 方框
 *  - image/video/audio：顶部上传按钮 + 媒体标签（图标+label） + 预览/占位
 *  - generate/其他：顶部标签 + 通用卡片占位，避免未知 kind 渲染崩坏
 * 全部用左右两侧的连接手柄，默认透明，hover/选中时显示。
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
  const def = NODE_DEF_OF(kind);
  const tagLabel = tagLabelOf(kind);

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

      {/* 顶部：text=标签，image/video/audio=上传按钮，其他=标签 */}
      {isText || !isMedia ? (
        <div className="pea-node-tag-pill">
          <span className="pea-node-tag-icon" aria-hidden>
            {def.icon}
          </span>
          <span>{tagLabel}</span>
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
        ) : isMedia ? (
          <div className="pea-node-media-card">
            <span className="pea-node-media-label">
              {def.icon} {tagLabel}
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
        ) : (
          <div className="pea-node-generic-card">
            <div className="pea-node-generic-icon" aria-hidden>
              {def.icon}
            </div>
            <div className="pea-node-generic-label">{tagLabel}</div>
            {data.prompt ? (
              <div className="pea-node-generic-prompt">{data.prompt}</div>
            ) : (
              <div className="pea-node-generic-hint">选中后在下方输入栏描述生成内容</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function tagLabelOf(k: string): string {
  const map: Record<string, string> = {
    text: 'Text',
    image: 'Image',
    video: 'Video',
    audio: 'Audio',
    generate: 'Generate',
    agent: 'Agent',
    story: 'Story',
    world3d: '3D World',
    camera: 'Camera',
    light: 'Light',
    playlist: 'Playlist',
    replace: 'Replace',
    ref: 'Ref',
  };
  return map[k] ?? NODE_DEF_OF(k).label;
}
