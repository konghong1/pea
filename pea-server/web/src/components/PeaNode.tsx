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
  const select = useCanvas((s) => s.select);
  const selected = useCanvas((s) => s.selectedIds.includes(id));
  const [hovered, setHovered] = useState(false);
  const editRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // 拖动判定：mousedown 记录起点，click 时若位移>4px 视为拖动（不选中）
  const downXY = useRef<{ x: number; y: number } | null>(null);

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
      onMouseDown={(e) => {
        // 落在连接手柄上：交给 ReactFlow 发起连线，根节点不要拦截/选中
        if ((e.target as HTMLElement).closest('.react-flow__handle')) return;
        // 记录按下坐标，用于区分“单击选中”与“拖动节点”
        downXY.current = { x: e.clientX, y: e.clientY };
      }}
      onClick={(e) => {
        // 兜底：ReactFlow 会忽略落在 contentEditable 上的 click（文本正文），
        // 导致点文本节点正文无法选中。这里确保点击节点任意位置都能选中。
        // 真实拖动（位移>4px）不触发选中，避免拖动后误弹输入框。
        const d = downXY.current;
        if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) return;
        if (!selected) select(id);
      }}
      data-kind={kind}
    >
      {/* 左右连接手柄（截图2 ⊕ 位置）。
          注意：手柄必须能让 ReactFlow 捕获 pointerdown 以发起连线，
          因此不能在外层 wrapper 上 stopPropagation（那会掐断连线起点）。
          直接把 Handle 定位到节点边缘外侧即可，ReactFlow 原生区分“抓手柄连线”与“拖节点本体”。 */}
      <Handle
        type="target"
        position={Position.Left}
        className="pea-handle"
        style={{ left: -10, top: '50%', transform: 'translateY(-50%)' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="pea-handle"
        style={{ right: -10, top: '50%', transform: 'translateY(-50%)' }}
      />

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
            onMouseDown={(e) => e.stopPropagation()}
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
            {data.generating ? (
              <div className="pea-node-generating" aria-label="生成中">
                <div className="pea-node-generate-spinner" />
                <span className="pea-node-generate-text">生成中…</span>
              </div>
            ) : data.resultUrl ? (
              kind === 'image' ? (
                <img src={data.resultUrl} alt={data.prompt || tagLabel} className="pea-node-media-preview pea-node-result-preview" />
              ) : kind === 'video' ? (
                <video src={data.resultUrl} controls className="pea-node-media-preview pea-node-result-preview" />
              ) : (
                <audio src={data.resultUrl} controls className="pea-node-audio" />
              )
            ) : data.url ? (
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
            {data.generating ? (
              <div className="pea-node-generating" aria-label="生成中">
                <div className="pea-node-generate-spinner" />
                <span className="pea-node-generate-text">生成中…</span>
              </div>
            ) : data.resultUrl ? (
              <img src={data.resultUrl} alt={data.prompt || tagLabel} className="pea-node-result-preview" />
            ) : data.prompt ? (
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
