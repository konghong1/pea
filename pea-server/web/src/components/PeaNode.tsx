import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Handle, Position, NodeProps } from 'reactflow';
import { useCanvas, PeaNodeData } from '../store/canvas';
import { toast } from '../store/toast';
import { useAuth } from '../store/auth';
import { api } from '../api/client';
import { getFileUrl } from '../api/files';
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
  // 文本节点的编辑态：与 selected 解耦。
  // - 单击节点 → 只选中（可拖动，不会进编辑）
  // - 双击文本节点 → 进入编辑态（contentEditable=true + 聚焦）
  // - 双击其他节点 → 无反应
  // - 失焦 / 取消选中 → 自动退出编辑态
  const [editing, setEditing] = useState(false);
  const editRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // 拖动判定：mousedown 记录起点，click 时若位移>4px 视为拖动（不选中）
  const downXY = useRef<{ x: number; y: number } | null>(null);

  const kind = data.kind;
  const isText = kind === 'text';
  const isMedia = kind === 'image' || kind === 'video' || kind === 'audio';
  const hasImage = kind === 'image' && !!(data.resultUrl || data.resultUrls?.length || data.url || data.fileKey);
  // 媒体节点是否有可展示内容（空态上传浮条互斥判断：image 用 hasImage，video/audio 用 url/fileKey/result）
  const hasMediaContent = kind === 'image'
    ? hasImage
    : !!(data.url || data.fileKey || data.resultUrl || data.resultUrls?.length);
  // 用户上传的图片（非 AI 生成结果）——不需要接收其他节点输入，隐藏左手柄
  const isUserUploadedImage = kind === 'image' && !!(data.fileKey || data.url) && !(data.resultUrl || data.resultUrls?.length);
  const def = NODE_DEF_OF(kind);
  const tagLabel = tagLabelOf(kind);

  // 将 data.aspectRatio（如 "9:16"）映射为节点尺寸
  // 仅空白节点使用；有内容后由 CSS aspect-ratio:auto 接管（按实际媒体比例包裹）
  // 关键：让「最长边」恒定 = LONG_EDGE（340px），
  // 这样切换比例时，比例里那个较大的数字（例如 9:16 与 16:9 中的"16"）
  // 永远对应相同的物理像素——9:16 的 16 是高度=340，16:9 的 16 是宽度=340，
  // 视觉上大小完全一致（修复：不同方向同比例数字尺寸不统一）。
  // 横屏/方形(w>=h)时长边是宽度，竖屏时长边是高度，短边按比例收窄。
  // 节点外壳宽度通过 CSS 变量 --pea-node-width 动态注入，内层 body-card
  // 保持 width:100% 撑满外壳，避免出现白边。
  const LONG_EDGE = 340;
  const nodeSize = useMemo(() => {
    if (!data.aspectRatio || hasMediaContent) return undefined;
    const [w, h] = data.aspectRatio.split(':').map(Number);
    if (!w || !h) return undefined;
    return w >= h
      ? { width: LONG_EDGE, height: Math.round(LONG_EDGE * (h / w)) }
      : { width: Math.round(LONG_EDGE * (w / h)), height: LONG_EDGE };
  }, [data.aspectRatio, hasMediaContent]);

  const outerStyle = nodeSize
    ? ({ '--pea-node-width': `${nodeSize.width}px` } as React.CSSProperties)
    : undefined;
  const bodyStyle: React.CSSProperties | undefined = nodeSize
    ? { height: nodeSize.height }
    : undefined;

  // text 节点：把 store 的 html 同步进可编辑区。
  useEffect(() => {
    if (isText && editRef.current && document.activeElement !== editRef.current) {
      const want = data.html ?? '';
      if (editRef.current.innerHTML.trim() !== want.trim()) editRef.current.innerHTML = want;
    }
  }, [data.html, isText]);

  // 选中 text 节点时不要自动 focus；只有进入 editing 态才聚焦。
  // （原逻辑会自动 focus，导致单击就进编辑模式、无法拖动节点。）

  // 取消选中时强制退出编辑态，避免外部选中状态改变后还残留可编辑区。
  useEffect(() => {
    if (!selected && editing) setEditing(false);
  }, [selected, editing]);

  // 双击文本节点进入编辑态；其他节点不响应。
  const onNodeDoubleClick = (e: React.MouseEvent) => {
    if (!isText) return;
    e.stopPropagation();
    e.preventDefault();
    setEditing(true);
    // 下一帧聚焦，确保 contentEditable 已切到 true
    requestAnimationFrame(() => {
      if (!editRef.current) return;
      editRef.current.focus();
      // 光标放到末尾（直觉更好）
      const sel = window.getSelection();
      if (sel) {
        const range = document.createRange();
        range.selectNodeContents(editRef.current);
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);
      }
    });
  };

  const onPickFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    const nodeMeta = data.meta ?? {};
    // 经 BFF 代理上传（multipart），服务端直写 MinIO，刷新后仍可加载；失败退回本地 blob 预览。
    let fileKey: string | undefined;
    if (useAuth.getState().user?.id != null) {
      try {
        const form = new FormData();
        form.append('file', f);
        const { data: resp } = await api.post('/files/upload', form);
        fileKey = resp.key;
      } catch {
        fileKey = undefined;
      }
    }
    const url = fileKey ? '' : URL.createObjectURL(f);
    // 替换/上传都走同一个文件输入：清掉旧的生成结果，让新上传立刻展示。
    update(id, {
      fileKey,
      url,
      resultUrl: undefined,
      resultUrls: undefined,
      resultIndex: 0,
      savedToLibrary: false,
      meta: { ...nodeMeta, fileName: f.name },
    });
    if (!fileKey) toast.error('上传失败，已用本地预览（刷新后可能丢失）');
  };

  const onEditBlur = () => {
    if (editRef.current) update(id, { html: editRef.current.innerHTML });
    setEditing(false);
  };

  return (
    <div
      className={`pea-node ${selected ? 'selected' : ''} ${hovered ? 'hover' : ''} pea-node-${kind} ${hasMediaContent ? 'pea-node-has-media' : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onMouseDown={(e) => {
        if ((e.target as HTMLElement).closest('.react-flow__handle')) return;
        downXY.current = { x: e.clientX, y: e.clientY };
      }}
      onClick={(e) => {
        const d = downXY.current;
        if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) return;
        if (!selected) select(id);
      }}
      onDoubleClick={onNodeDoubleClick}
      data-kind={kind}
      style={outerStyle}
    >
      {/* 左手柄：用户上传的图片不需要接收其他节点输入，隐藏 */}
      {!isUserUploadedImage && (
        <Handle
          type="target"
          position={Position.Left}
          className="pea-handle"
          style={{ left: -10, top: '50%', transform: 'translateY(-50%)' }}
        />
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="pea-handle"
        style={{ right: -10, top: '50%', transform: 'translateY(-50%)' }}
      />

      {/* 顶部标签：所有节点始终显示 */}
      <div className="pea-node-tag-pill">
        <span className="pea-node-tag-icon" aria-hidden>
          {def.icon}
        </span>
        <span>{tagLabel}</span>
      </div>

      {isMedia && (
        <input
          ref={fileRef}
          type="file"
          hidden
          accept={kind === 'image' ? 'image/*' : kind === 'video' ? 'video/*' : 'audio/*'}
          onChange={onPickFile}
        />
      )}

      {/* 节点主体 */}
      <div
        className={`pea-node-body-card ${hasImage ? 'pea-node-body-image-result' : ''}`}
        style={bodyStyle}
      >
        {isText ? (
          <div className="pea-node-text-wrap">
            <div
              ref={editRef}
              className={`pea-node-text-edit ${editing ? 'is-editing nodrag' : ''}`}
              contentEditable={editing}
              suppressContentEditableWarning
              data-placeholder={editing ? '' : '双击开始编辑…'}
              onInput={() => update(id, { html: editRef.current?.innerHTML })}
              onBlur={onEditBlur}
              onMouseDown={(e) => {
                // 编辑态下：阻止冒泡，避免触发节点拖动
                // 非编辑态下：preventDefault() 阻止 contentEditable 自动获取焦点，
                // 但不阻止事件冒泡，这样 ReactFlow 和父节点的 onMouseDown 都能收到事件；
                // 同时本 div 不带 nodrag，ReactFlow 才能正常发起节点拖动。
                if (editing) {
                  e.stopPropagation();
                } else {
                  e.preventDefault();
                }
              }}
            />
          </div>
        ) : isMedia ? (
          <MediaNodeBody id={id} kind={kind} data={data} hasImage={hasImage} onRequestUpload={() => fileRef.current?.click()} />
        ) : (
          <GenericNodeBody id={id} data={data} tagLabel={tagLabel} def={def} />
        )}
      </div>

      {/* 媒体节点空白态：上传悬浮条（与 ResultToolbar 完全同一浮空位置，互斥）
          仅在所有媒体无内容时显示，浮在节点外部上方；有内容后消失 */}
      {isMedia && !hasMediaContent && !data.generating && (
        <div className="pea-node-top-upload-bar" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            className="pea-node-upload-btn"
            onClick={(e) => { e.stopPropagation(); fileRef.current?.click(); }}
            aria-label="上传图片"
            title="上传图片"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
              <path d="M12 3v12" />
              <path d="M7 8l5-5 5 5" />
              <path d="M5 21h14" />
            </svg>
            <span>上传</span>
          </button>
        </div>
      )}

      {/* 编辑框锚点：NodeChatPrompt 会把节点输入栏 portal 进这个容器
          （data-pea-anchor 用于按选中节点精确匹配）。该元素缺失会导致点击节点后
          输入栏（边框框）永不弹出——这是反复回归的根因，务必保留。 */}
      <div className="pea-node-editor-anchor" data-pea-anchor={id} />
    </div>
  );
}

/* ═════════════════════════════════════════════════════════════════════════════
 * Media 节点主体（image/video/audio）
 * ═════════════════════════════════════════════════════════════════════════════ */
function MediaNodeBody({
  id,
  kind,
  data,
  hasImage,
  onRequestUpload,
}: {
  id: string;
  kind: PeaNodeKind;
  data: PeaNodeData;
  hasImage: boolean;
  onRequestUpload: () => void;
}) {
  const update = useCanvas((s) => s.updateNodeData);
  const def = NODE_DEF_OF(kind);
  const tagLabel = tagLabelOf(kind);
  const resultUrls = data.resultUrls?.length ? data.resultUrls : data.resultUrl ? [data.resultUrl] : [];
  const index = Math.max(0, Math.min(data.resultIndex ?? 0, resultUrls.length - 1));
  const currentUrl = resultUrls[index] || data.resultUrl;
  const hasResult = Boolean(currentUrl);
  // 上传态：fileKey 是 MinIO 持久化 key，渲染时再换签名下载 URL（刷新后仍可加载）。
  const [resolvedUrl, setResolvedUrl] = useState(data.url ?? '');
  useEffect(() => {
    let alive = true;
    if (data.fileKey) {
      getFileUrl(data.fileKey)
        .then((u) => { if (alive) setResolvedUrl(u); })
        .catch(() => { if (alive) setResolvedUrl(''); });
    } else {
      setResolvedUrl(data.url ?? '');
    }
    return () => { alive = false; };
  }, [data.fileKey, data.url]);
  // image/video 节点统一不显示内部 media-label：顶部 tag-pill 已承载类型标识，内部不再重复
  const showMediaLabel = !(kind === 'image' || kind === 'video');

  return (
    <div className="pea-node-media-card">
      {showMediaLabel && (
        <span className="pea-node-media-label">
          {def.icon} {tagLabel}
        </span>
      )}
      {data.generating ? (
        <div className="pea-node-generating" aria-label="生成中">
          <div className="pea-node-generate-spinner" />
          <span className="pea-node-generate-text">生成中…</span>
        </div>
      ) : hasResult ? (
        <>
          {kind === 'image' && (
            <ResultImageView
              id={id}
              data={data}
              urls={resultUrls}
              index={index}
              onIndexChange={(i) => update(id, { resultIndex: i })}
              onReplace={onRequestUpload}
              canReplace={false}
            />
          )}
          {kind === 'video' && (
            <div className="pea-node-result-media-wrap">
              <video src={currentUrl} controls className="pea-node-media-preview pea-node-result-preview" />
              <button
                type="button"
                className="pea-node-result-replace"
                onClick={(e) => {
                  e.stopPropagation();
                  onRequestUpload();
                }}
                aria-label="替换"
                title="替换"
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                  <path d="M12 3v12" />
                  <path d="M7 8l5-5 5 5" />
                  <path d="M5 21h14" />
                </svg>
                <span>替换</span>
              </button>
            </div>
          )}
          {kind === 'audio' && (
            <div className="pea-node-result-media-wrap">
              <audio src={currentUrl} controls className="pea-node-audio" />
              <button
                type="button"
                className="pea-node-result-replace"
                onClick={(e) => {
                  e.stopPropagation();
                  onRequestUpload();
                }}
                aria-label="替换"
                title="替换"
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                  <path d="M12 3v12" />
                  <path d="M7 8l5-5 5 5" />
                  <path d="M5 21h14" />
                </svg>
                <span>替换</span>
              </button>
            </div>
          )}
        </>
      ) : data.url || data.fileKey ? (
        kind === 'image' ? (
          // 上传图也走 ResultImageView（带功能条 + 保存/全屏 + 右上角替换）
          <ResultImageView
            id={id}
            data={data}
            urls={[resolvedUrl].filter(Boolean)}
            index={0}
            onIndexChange={() => {}}
            onReplace={onRequestUpload}
            canReplace={true}
          />
        ) : kind === 'video' ? (
          <video src={resolvedUrl} controls className="pea-node-media-preview" />
        ) : (
          <audio src={resolvedUrl} controls className="pea-node-audio" />
        )
      ) : (
        <div className="pea-node-media-placeholder">
          <span className="pea-node-media-placeholder-icon" aria-hidden>
            {kind === 'image' ? (
              <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.2">
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <circle cx="8.5" cy="9.5" r="1.5" />
                <path d="M3 16l5-5 4 4 3-3 6 6" />
              </svg>
            ) : kind === 'video' ? (
              <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.2">
                <rect x="3" y="5" width="18" height="14" rx="2" />
                <path d="M10 9l5 3-5 3z" fill="currentColor" stroke="none" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.2">
                <path d="M9 18V5l12-2v13" />
                <circle cx="6" cy="18" r="3" />
                <circle cx="18" cy="16" r="3" />
              </svg>
            )}
          </span>
        </div>
      )}
    </div>
  );
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 生成结果图片展示：单图/多图 + 工具条 + 角标
 * ═════════════════════════════════════════════════════════════════════════════ */
function ResultImageView({
  id,
  data,
  urls,
  index,
  onIndexChange,
  onReplace,
  canReplace,
}: {
  id: string;
  data: PeaNodeData;
  urls: string[];
  index: number;
  onIndexChange: (i: number) => void;
  onReplace: () => void;
  /** 仅用户上传图显示"替换"按钮；AI 生成图按约定不显示替换 */
  canReplace: boolean;
}) {
  const update = useCanvas((s) => s.updateNodeData);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const currentUrl = urls[index] || urls[0];

  const handleSaveToLibrary = (e: React.MouseEvent) => {
    e.stopPropagation();
    update(id, { savedToLibrary: true });
    toast.success('已保存到素材库');
  };

  const handleFullscreen = (e: React.MouseEvent) => {
    e.stopPropagation();
    setLightboxOpen(true);
  };

  const handleReplace = (e: React.MouseEvent) => {
    e.stopPropagation();
    onReplace();
  };

  return (
    <>
      <div className="pea-node-result-image-wrap">
        {/* 左上角收藏星标（装饰/状态） */}
        <button
          type="button"
          className={`pea-node-result-star ${data.savedToLibrary ? 'saved' : ''}`}
          onClick={handleSaveToLibrary}
          aria-label="保存到素材库"
          title="保存到素材库"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" stroke="none">
            <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
          </svg>
        </button>

        {/* 右上角：上传图显示"替换"按钮（始终可见）；多图时追加数量角标 */}
        <div className="pea-node-result-overlay-tr">
          {canReplace && (
            <button
              type="button"
              className="pea-node-result-replace"
              onClick={handleReplace}
              aria-label="替换"
              title="替换"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                <path d="M12 3v12" />
                <path d="M7 8l5-5 5 5" />
                <path d="M5 21h14" />
              </svg>
              <span>替换</span>
            </button>
          )}
          {urls.length > 1 && (
            <div className="pea-node-image-badge">
              <button
                type="button"
                className="pea-node-image-badge-btn pea-node-image-badge-btn-hover-right"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowPicker((v) => !v);
                }}
                aria-label={`共 ${urls.length} 张图`}
              >
                {urls.length}
                <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2" className="pea-badge-arrow">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>
              {showPicker && (
                <div className="pea-node-image-picker pea-node-image-picker-horizontal">
                  {urls.map((url, i) => (
                    <button
                      key={`${url}-${i}`}
                      type="button"
                      className={`pea-node-image-picker-item ${i === index ? 'active' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onIndexChange(i);
                        setShowPicker(false);
                      }}
                    >
                      <img src={url} alt={`结果 ${i + 1}`} />
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 主图：点击不再放大（避免误触全屏）；如需全屏请用功能条"全屏查看" */}
        <img
          src={currentUrl}
          alt={data.prompt || '生成结果'}
          className="pea-node-media-preview pea-node-result-preview"
          loading="lazy"
          draggable={false}
        />
      </div>

      {/* 功能条 */}
      <ResultToolbar
        currentUrl={currentUrl}
        onSave={handleSaveToLibrary}
        saved={!!data.savedToLibrary}
        onFullscreen={handleFullscreen}
      />

      {/* 全屏查看 */}
      {lightboxOpen && typeof document !== 'undefined' && (
        <ImageLightbox
          urls={urls}
          index={index}
          data={data}
          onClose={() => setLightboxOpen(false)}
          onIndexChange={onIndexChange}
          onSave={() => update(id, { savedToLibrary: true })}
        />
      )}
    </>
  );
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 生成结果功能条（截图7）：裁剪、3D、去背景、放大、更多、风格、保存、下载、全屏
 * ═════════════════════════════════════════════════════════════════════════════ */
function ResultToolbar({
  currentUrl,
  onSave,
  saved,
  onFullscreen,
}: {
  currentUrl: string;
  onSave: (e: React.MouseEvent) => void;
  saved: boolean;
  onFullscreen: (e: React.MouseEvent) => void;
}) {
  const soon = (label: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    toast.info(`${label} 即将上线`);
  };

  return (
    <div className="pea-node-result-toolbar" onClick={(e) => e.stopPropagation()}>
      <ToolbarButton label="裁剪" muted onClick={soon('裁剪')}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M6 2v14a2 2 0 0 0 2 2h14" />
          <path d="M2 6h14a2 2 0 0 1 2 2v14" />
        </svg>
      </ToolbarButton>
      <ToolbarButton label="3D" muted onClick={soon('3D 转换')}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
          <path d="M3.27 6.96L12 12.01l8.73-5.05" />
          <path d="M12 22.08V12" />
        </svg>
      </ToolbarButton>
      <ToolbarButton label="去背景" muted onClick={soon('去背景')}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M12 2a10 10 0 1 0 10 10" />
          <path d="M12 12L4.93 4.93" />
        </svg>
      </ToolbarButton>
      <ToolbarButton label="放大" muted onClick={soon('高清放大')}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M12 3v18" />
          <path d="M3 12h18" />
          <path d="M7 7l3 3" />
          <path d="M17 7l-3 3" />
          <path d="M7 17l3-3" />
          <path d="M17 17l-3-3" />
        </svg>
      </ToolbarButton>
      <ToolbarButton label="更多" muted onClick={soon('更多')}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <circle cx="12" cy="5" r="1.5" fill="currentColor" />
          <circle cx="12" cy="12" r="1.5" fill="currentColor" />
          <circle cx="12" cy="19" r="1.5" fill="currentColor" />
        </svg>
      </ToolbarButton>
      <div className="pea-node-toolbar-divider" />
      <ToolbarButton label="风格迁移" onClick={soon('风格迁移')}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <circle cx="12" cy="12" r="10" />
          <circle cx="12" cy="12" r="4" />
        </svg>
      </ToolbarButton>
      <div className="pea-node-toolbar-divider" />
      <ToolbarButton label="保存到素材库" onClick={onSave} active={saved}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          <path d="M12 11v6" />
          <path d="M9 14h6" />
        </svg>
      </ToolbarButton>
      <ToolbarButton label="下载" onClick={(e) => { e.stopPropagation(); downloadCurrent(currentUrl); }}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <path d="M7 10l5 5 5-5" />
          <path d="M12 15V3" />
        </svg>
      </ToolbarButton>
      <ToolbarButton label="全屏查看" onClick={onFullscreen}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M15 3h6v6" />
          <path d="M9 21H3v-6" />
          <path d="M21 3l-7 7" />
          <path d="M3 21l7-7" />
        </svg>
      </ToolbarButton>
    </div>
  );
}

function ToolbarButton({
  label,
  children,
  onClick,
  active,
  muted,
}: {
  label: string;
  children: React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  active?: boolean;
  muted?: boolean;
}) {
  return (
    <button
      type="button"
      className={`pea-node-toolbar-btn ${active ? 'active' : ''} ${muted ? 'muted' : ''}`}
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}

function downloadCurrent(url: string) {
  if (!url) return;
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noreferrer';
  a.download = 'pea-generate.png';
  a.click();
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 全屏查看 Lightbox（截图10）：左侧大图 + 底部缩略图 + 右侧信息面板
 * ═════════════════════════════════════════════════════════════════════════════ */
function ImageLightbox({
  urls,
  index,
  data,
  onClose,
  onIndexChange,
  onSave,
}: {
  urls: string[];
  index: number;
  data: PeaNodeData;
  onClose: () => void;
  onIndexChange: (i: number) => void;
  onSave: () => void;
}) {
  const [current, setCurrent] = useState(index);
  const [fileSize, setFileSize] = useState<string>('-');
  const currentUrl = urls[current] || urls[0];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') setCurrent((i) => Math.max(0, i - 1));
      if (e.key === 'ArrowRight') setCurrent((i) => Math.min(urls.length - 1, i + 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, urls.length]);

  useEffect(() => {
    let cancelled = false;
    fetch(currentUrl, { method: 'HEAD', mode: 'cors' })
      .then((r) => {
        const len = r.headers.get('content-length');
        if (len && !cancelled) setFileSize(formatBytes(Number(len)));
      })
      .catch(() => {
        // 跨域/失败时静默保持 -
      });
    return () => { cancelled = true; };
  }, [currentUrl]);

  return createPortal(
    <div className="pea-node-lightbox" onClick={onClose}>
      <button type="button" className="pea-node-lightbox-close" onClick={onClose} aria-label="关闭">
        ×
      </button>

      {/* 左侧：大图 + 切换箭头 + 底部缩略图 */}
      <div className="pea-node-lightbox-left" onClick={(e) => e.stopPropagation()}>
        {urls.length > 1 && (
          <button
            type="button"
            className="pea-node-lightbox-arrow left"
            onClick={() => setCurrent((i) => Math.max(0, i - 1))}
            disabled={current === 0}
            aria-label="上一张"
          >
            ‹
          </button>
        )}
        <img className="pea-node-lightbox-img" src={currentUrl} alt="生成结果" />
        {urls.length > 1 && (
          <button
            type="button"
            className="pea-node-lightbox-arrow right"
            onClick={() => setCurrent((i) => Math.min(urls.length - 1, i + 1))}
            disabled={current === urls.length - 1}
            aria-label="下一张"
          >
            ›
          </button>
        )}
        {urls.length > 1 && (
          <div className="pea-node-lightbox-counter">
            {current + 1} / {urls.length}
          </div>
        )}
        {urls.length > 1 && (
          <div className="pea-node-lightbox-thumbs">
            {urls.map((url, i) => (
              <button
                key={`${url}-${i}`}
                type="button"
                className={i === current ? 'active' : ''}
                onClick={() => setCurrent(i)}
              >
                <img src={url} alt={`缩略图 ${i + 1}`} />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 右侧：信息面板 */}
      <div className="pea-node-lightbox-info" onClick={(e) => e.stopPropagation()}>
        <div className="pea-node-lightbox-info-header">提示词</div>
        <div className="pea-node-lightbox-prompt">{data.prompt || '—'}</div>

        <div className="pea-node-lightbox-info-header" style={{ marginTop: 24 }}>信息</div>
        <InfoRow label="模型" value={String(data.meta?.modelName || data.meta?.model || 'Agnes AI')} />
        <InfoRow label="质量" value={String(data.meta?.resolution || data.params?.resolution || '1K')} />
        <InfoRow label="宽高比" value={String(data.meta?.aspectRatio || data.params?.aspectRatio || '1:1')} />
        <InfoRow label="文件大小" value={fileSize} />
        <InfoRow label="日期" value={new Date().toLocaleDateString('zh-CN')} />
        <InfoRow label="创建者" value={String(data.meta?.creator || '—')} />

        <div className="pea-node-lightbox-actions">
          <button type="button" className="pea-node-lightbox-action primary" onClick={onSave}>
            设为主图
          </button>
          <button type="button" className="pea-node-lightbox-action" onClick={() => { onIndexChange(current); onClose(); }}>
            Apply to canvas
          </button>
          <button type="button" className="pea-node-lightbox-action" onClick={() => downloadCurrent(currentUrl)}>
            下载
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="pea-node-lightbox-info-row">
      <span className="pea-node-lightbox-info-label">{label}</span>
      <span className="pea-node-lightbox-info-value">{value}</span>
    </div>
  );
}

function formatBytes(n: number) {
  if (!n || Number.isNaN(n)) return '-';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 通用节点主体（generate / 其他）
 * ═════════════════════════════════════════════════════════════════════════════ */
function GenericNodeBody({
  id,
  data,
  tagLabel,
  def,
}: {
  id: string;
  data: PeaNodeData;
  tagLabel: string;
  def: { icon: string; label: string };
}) {
  return (
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
            <div className="pea-node-result-image-wrap">
              <img src={data.resultUrl} alt={data.prompt || tagLabel} className="pea-node-media-preview pea-node-result-preview" />
            </div>
          ) : data.prompt ? (
            <div className="pea-node-generic-prompt">{data.prompt}</div>
          ) : (
            <div className="pea-node-generic-hint">选中后在下方输入栏描述生成内容</div>
          )}
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
