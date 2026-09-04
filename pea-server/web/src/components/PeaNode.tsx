import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Handle, Position, NodeProps } from 'reactflow';
import { useCanvas, PeaNodeData, getGroupingActive } from '../store/canvas';
import { toast } from '../store/toast';
import { useAuth } from '../store/auth';
import { api } from '../api/client';
import { getFileUrl, getPresignedUrl } from '../api/files';
import { NODE_DEF_OF, PeaNodeKind } from '../constants/nodeTypes';
import NodeIcon, { GeneratingBadge, UploadBadge, kindColor } from './NodeIcon';
import TextNodeToolbar from './TextNodeToolbar';
import TextNodeEditorModal from './TextNodeEditorModal';
import TechLoader from './TechLoader';
import SaveToLibraryModal from './SaveToLibraryModal';
import { assetsApi, ASSET_ASSETS_CHANGED_EVENT, type AssetScope } from '../api/assets';
import { retryNodeGeneration, pollNodeJobResult } from '../lib/nodeGeneration';
import {
  acceptsUpstreamInput,
  isGeneratedMediaNode,
  isUserUploadedMediaNode,
} from '../lib/nodeSemantics';
import { getNodeSize, simplifyRatio } from '../lib/nodeSize';
import ImageCropOverlay from './ImageCropOverlay';
import AngleCubeOverlay, { type AngleCubeParams } from './AngleCubeOverlay';
import { acceptNodeGenerationJob } from '../api/catalog';

/** 数值夹取，用于连接点跟随鼠标的小范围限制 */
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** 读取本地图片文件的真实宽高比。失败时返回 undefined，调用方使用默认比例。 */
function detectImageAspectRatio(file: File): Promise<string | undefined> {
  return new Promise((resolve) => {
    const img = new Image();
    const objectUrl = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(simplifyRatio(img.naturalWidth, img.naturalHeight));
    };
    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(undefined);
    };
    img.src = objectUrl;
  });
}

/**
 * 连接点(手柄圆点)内缘距节点框的间距（flow 坐标 px）。
 * 设计：连接点是一个浮在节点框外、与节点同缩放的小圆点（hover 时显现并带“弹开”跟随）；
 * 真正的连线端点要连到“节点框”上，而不是这个悬浮点。PeaEdge 会按手柄中心到框边的距离
 * 把边端点回退到框边。
 */
export const HANDLE_GAP = 14;
/** 手柄直径（flow 坐标 13px）的一半。手柄中心距框 = HANDLE_GAP + HANDLE_HALF，
 *  PeaEdge 回退量同此值，使连线端点精确落在节点框边。 */
export const HANDLE_HALF = 6.5;

/**
 * 画布节点渲染：
 *  - text：顶部标签（图标+Text） + contentEditable 方框
 *  - image/video/audio：顶部上传按钮 + 媒体标签（图标+label） + 预览/占位
 *  - generate/其他：顶部标签 + 通用卡片占位，避免未知 kind 渲染崩坏
 * 全部用左右两侧的连接手柄，默认透明，hover/选中时显示。
 */
export default function PeaNode({ id, data }: NodeProps<PeaNodeData>) {
  const update = useCanvas((s) => s.updateNodeData);
  const selectedIdsArr = useCanvas((s) => s.selectedIds);
  const clearSelection = useCanvas((s) => s.clearSelection);
  const selected = selectedIdsArr.includes(id);
  // 多选（框选 / Shift 多选）时抑制单节点自身的「选中边框 + 功能条」，
  // 只保留透明组选框 + 多选工具条，避免多个节点功能框堆叠干扰（需求3）。
  const isMulti = selectedIdsArr.length > 1;
  const isSingleSelected = selected && !isMulti;
  const [hovered, setHovered] = useState(false);
  // 文本节点的编辑态：与 selected 解耦。
  // - 单击节点 → 只选中（可拖动，不会进编辑）
  // - 双击文本节点 → 弹出全屏编辑弹窗 (TextNodeEditorModal)
  // - 双击其他节点 → 无反应
  // - 失焦 / 取消选中 → 自动退出编辑态
  const [editing, setEditing] = useState(false);
  const [editorModalOpen, setEditorModalOpen] = useState(false);
  const [cropping, setCropping] = useState(false);
  // 角度魔方：单一数据源取自 store（cubeOpenNodeId），不用 meta 持久化，
  // 避免节点重挂载后误把面板恢复出来。
  const cubeOpenNodeId = useCanvas((s) => s.cubeOpenNodeId);
  const cubeOpen = cubeOpenNodeId === id;
  const editRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const chromeRef = useRef<HTMLDivElement>(null);
  // 交互控件宿主（counter-scale 子层）：ResultToolbar 通过 portal 挂到这里，
  // 不能挂到外层 chrome，否则功能条会跟着画布缩放变得点不动。
  const chromeFixedRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // 持有当前节点的文件 Object URL，用于组件卸载时释放，防止内存泄漏
  const objectUrlRef = useRef<string>('');
  const kind = data.kind;
  const isText = kind === 'text';
  const isMedia = kind === 'image' || kind === 'video' || kind === 'audio';
  const hasImage = kind === 'image' && !!(data.resultUrl || data.resultUrls?.length || data.url || data.fileKey);
  // 媒体节点是否有可展示内容（空态上传浮条互斥判断：image 用 hasImage，video/audio 用 url/fileKey/result）
  const hasMediaContent = kind === 'image'
    ? hasImage
    : !!(data.url || data.fileKey || data.resultUrl || data.resultUrls?.length);
  // 用户自己上传的媒体（图片/视频/音频，非 AI 生成结果）——不需要接收其他节点输入，
  // 隐藏左侧输入连接点。与「AI 生成结果」区分：AI 生成结果来自上游/生成流，仍可能需要接收上游输入。
  // 判定统一收敛到 lib/nodeSemantics，避免与画布连线校验 / 徽章 / 编辑框显隐各写一套而漂移。
  const isUserUploadedMedia = isUserUploadedMediaNode(data);
  // 有上游输入连接时，媒体节点内容将由上游提供，不再展示上传入口（视频/音频与图片保持一致）
  const upstreamInputs = useCanvas((s) => s.getUpstreamInputs(id));
  const hasUpstreamInput = upstreamInputs.length > 0;
  const tagLabel = tagLabelOf(kind);

  // ── 连接点随画布缩放（不再 counter-scale）──────────────────────────────
  // 用户反馈：缩小时连接点相对节点框显得很大，要求像节点框一样随画布缩放。
  // 因此去掉 scale(1/zoom)：手柄 width/height 13px 是 flow 坐标值，视觉上随 zoom
  // 自然缩放；中心距框 HANDLE_GAP+HANDLE_HALF 也是 flow 坐标恒定值。
  //
  // ── chrome 层缩放策略（2026-07-31 重构，勿回退）──────────────────────────
  // 历史问题：整个 .pea-node-chrome（标题徽章 + 功能条 + 上传条）被统一 counter-scale，
  // 导致「标题屏幕大小恒定、节点框随画布缩放」→ 标题/节点的比例在 zoom 0.25~3 之间
  // 变化 12 倍（实测 badge/card = 0.77 → 0.13），缩小时标题甚至比节点框还宽。
  //
  // 现在拆成两层，各自独立：
  //   1. 外层 .pea-node-chrome —— 不做任何 counter-scale，纯 flow 坐标，
  //      标题徽章因此与节点框严格等比缩放（相对大小恒定）。
  //   2. 内层 .pea-node-chrome-fixed —— 只包交互控件（功能条 / 上传条 / 文本工具条），
  //      仍做 counter-scale 保证按钮在任何缩放下都是可点击的屏幕尺寸。
  //
  // counter-scale 的缩放源：使用全局 CSS 变量 --pea-inv-zoom（由 ZoomVarSync 组件更新），
  // 避免每个节点都订阅 ReactFlow store 导致 zoom 变化时全量重渲。
  // --pea-node-inv-zoom 作为节点级 fallback，优先使用全局变量。
  const chromeStyle = { '--pea-node-inv-zoom': 'var(--pea-inv-zoom, 1)' } as React.CSSProperties;
  // 读取当前 zoom 值用于手柄跟随计算（从 CSS 变量读取，不触发重渲）
  const zoomRef = useRef(1);
  useEffect(() => {
    const updateZoom = () => {
      const el = rootRef.current;
      if (el) {
        const invZoom = parseFloat(getComputedStyle(el).getPropertyValue('--pea-node-inv-zoom') || '1');
        zoomRef.current = invZoom ? 1 / invZoom : 1;
      }
    };
    // 初始读取
    updateZoom();
    // 监听全局 CSS 变量变化（通过 MutationObserver 监听 root 样式变化）
    const observer = new MutationObserver(updateZoom);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['style'] });
    return () => observer.disconnect();
  }, []);
  const handleOffset = -(HANDLE_GAP + HANDLE_HALF);

  // 节点框尺寸标准（锁定，不再随内容跳变）：
  // - 每个 kind 都有「标准比例」，data.aspectRatio 可覆盖（用户在比例选择器里改）。
  // - 横屏(w>=h)：宽度恒为 FIXED_EDGE（340px），高度按比例缩小；
  //   竖屏(w<h)：高度恒为 FIXED_EDGE（340px），宽度按比例缩小；
  //   正方形：340×340。
  // - 这样不同比例节点视觉面积接近（~68k px²），但形状明显不同，一眼可辨。
  // - 无论空态/有内容，框尺寸永远锁定，媒体用 object-fit:cover 填满锁定框。
  const nodeSize = useMemo(() => getNodeSize(data.aspectRatio, kind), [kind, data.aspectRatio]);

  const outerStyle = { '--pea-node-width': `${nodeSize.width}px` } as React.CSSProperties;
  const bodyStyle: React.CSSProperties = { height: nodeSize.height };

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

  // 组件卸载时释放 Object URL，防止内存泄漏
  useEffect(() => {
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = '';
      }
    };
  }, []);

  // 打开全屏编辑弹窗时，主动取消底层节点选中并退出编辑态。
  // 否则弹窗盖住画布后，TextNodeToolbar 和 NodeChatPrompt 输入栏仍依赖 selectedIds 显示，
  // 用户在弹窗内点击/聚焦会造成底层 editing/hover 状态抖动，表现为一闪一闪。
  useEffect(() => {
    if (editorModalOpen) {
      setEditing(false);
      clearSelection();
    }
  }, [editorModalOpen, clearSelection]);

  // 进入编辑态时聚焦编辑区，并把光标放到内容末尾（避免后续输入插到最前面）。
  // 同时保证功能条 execCommand 操作的是一个真正可编辑的区域。
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

  // 双击文本节点弹出全屏编辑弹窗；其他节点不响应。
  const onNodeDoubleClick = (e: React.MouseEvent) => {
    if (!isText) return;
    e.stopPropagation();
    e.preventDefault();
    setEditorModalOpen(true);
  };

  // 弹窗保存回调
  const onEditorModalSave = (html: string) => {
    update(id, { html });
    setEditorModalOpen(false);
  };

  const onPickFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    const nodeMeta = data.meta ?? {};
    // 读取本地图片真实比例，让节点框随上传内容自适应。
    // 修复：上传横向图后节点仍按默认 9:16 显示，导致截图/裁剪时露出原图比例而视觉不一致。
    const detectedAspectRatio = kind === 'image' ? await detectImageAspectRatio(f) : undefined;
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
    // 释放旧的 Object URL，防止内存泄漏
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = '';
    }
    const url = fileKey ? '' : URL.createObjectURL(f);
    objectUrlRef.current = url;
    // 替换/上传都走同一个文件输入：清掉旧的生成结果，让新上传立刻展示。
    update(id, {
      fileKey,
      url,
      resultUrl: undefined,
      resultUrls: undefined,
      resultIndex: 0,
      savedToLibrary: false,
      isFavorite: false,
      // 用户上传图片时按真实比例更新节点框；检测失败则保持原比例。
      aspectRatio: detectedAspectRatio ?? data.aspectRatio,
      meta: { ...nodeMeta, fileName: f.name, fileSize: f.size, uploadAt: new Date().toISOString() },
    });
    if (!fileKey) toast.error('上传失败，已用本地预览（刷新后可能丢失）');
  };

  const onEditBlur = (e: React.FocusEvent<HTMLDivElement>) => {
    if (editRef.current) update(id, { html: editRef.current.innerHTML });
    // 焦点落到「本节点自己的 UI」上时不要退出编辑态。
    //   - .tnt-bar        节点上方格式功能条
    //   - .node-input-bar 节点下方输入栏（边框框）
    //   - .tne-modal      文本节点全屏编辑弹窗
    // 否则会连锁出两个用户可见的 bug：
    //   1) contentEditable 被关掉 → 之后点功能条的 H1/粗体/颜色全部静默失效；
    //   2) is-editing class 瞬时增删 → 编辑框和功能条「刷闪」。
    const next = e.relatedTarget as HTMLElement | null;
    if (next?.closest?.('.tnt-bar, .node-input-bar, .tne-modal')) return;
    setEditing(false);
  };

  return (
    <div
      ref={rootRef}
      data-node-id={id}
      className={`pea-node ${selected && !isMulti ? 'selected' : ''} ${hovered ? 'hover' : ''} pea-node-${kind} ${hasMediaContent ? 'pea-node-has-media' : ''} ${data.generating ? 'is-generating' : ''} ${cropping ? 'is-cropping' : ''} ${cubeOpen ? 'is-cube-mode' : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => {
        setHovered(false);
        // 鼠标移出节点：所有连接点跟随偏移归零
        const el = rootRef.current;
        if (el) {
          el.style.setProperty('--pea-hx-l', '0px');
          el.style.setProperty('--pea-hy-l', '0px');
          el.style.setProperty('--pea-hx-r', '0px');
          el.style.setProperty('--pea-hy-r', '0px');
        }
      }}
      onMouseMove={(e) => {
        // ── 连接点独立热区跟随逻辑（带弹回边界）────────────────────
        // 直接跟随光标，但把手柄中心钳制在「节点框外」区域：
        // 左/右 handle 的内缘不能越过节点框边，即光标把它往框里推时，
        // 手柄会停在框边外缘（弹回），不会压进节点框。
        const el = rootRef.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        const mx = e.clientX;
        const my = e.clientY;
        const z = Math.max(zoomRef.current, 0.1);

        const HOT_RADIUS = 45;        // 热区半径（屏幕 px）
        const FOLLOW_MAX_X = 14;      // 向外最大跟随距离（屏幕 px）
        const FOLLOW_MAX_Y = 18;      // 垂直方向最大跟随距离（屏幕 px）
        const VERTICAL_MARGIN = 12;   // 上下不贴边留的余量（屏幕 px）

        // 手柄不能越过框边：内缘最多贴到框边。以 hover 时最大可见尺寸(19px, 半宽 9.5)为界，
        // 保证无论基础态(13px)还是 hover 态(19px)手柄，其内缘都不进入节点框。
        const half = HANDLE_HALF * z;                 // 基础手柄半宽(13px)
        const halfHit = 9.5 * z;                       // hover 态手柄半宽(19px)，弹回/跟随边界按最大可见尺寸
        // 手柄靠 right/left 定位的是「外缘」，故静止中心 = 框边 ± 偏移 ∓ 手柄半宽
        const cxOffset = (HANDLE_GAP + HANDLE_HALF) * z;
        const leftRestCx = r.left - cxOffset + halfHit;
        const rightRestCx = r.right + cxOffset - halfHit;
        const restCy = r.top + r.height / 2;

        const leftMaxCx = r.left - halfHit;   // 左 handle 最右允许位置(内缘贴框)
        const leftMinCx = leftRestCx - FOLLOW_MAX_X;
        const rightMinCx = r.right + halfHit; // 右 handle 最左允许位置(内缘贴框)
        const rightMaxCx = rightRestCx + FOLLOW_MAX_X;
        const cyMin = r.top + half + VERTICAL_MARGIN;
        const cyMax = r.bottom - half - VERTICAL_MARGIN;

        const distLeft = Math.hypot(mx - leftRestCx, my - restCy);
        const distRight = Math.hypot(mx - rightRestCx, my - restCy);

        if (distLeft < HOT_RADIUS && distLeft <= distRight) {
          const actualCx = clamp(mx, leftMinCx, leftMaxCx);
          const actualCy = clamp(my, cyMin, cyMax);
          const dx = actualCx - leftRestCx;
          const dy = actualCy - restCy;
          el.style.setProperty('--pea-hx-l', `${dx.toFixed(1)}px`);
          el.style.setProperty('--pea-hy-l', `${dy.toFixed(1)}px`);
          el.style.setProperty('--pea-hx-r', '0px');
          el.style.setProperty('--pea-hy-r', '0px');
        } else if (distRight < HOT_RADIUS) {
          const actualCx = clamp(mx, rightMinCx, rightMaxCx);
          const actualCy = clamp(my, cyMin, cyMax);
          const dx = actualCx - rightRestCx;
          const dy = actualCy - restCy;
          el.style.setProperty('--pea-hx-l', '0px');
          el.style.setProperty('--pea-hy-l', '0px');
          el.style.setProperty('--pea-hx-r', `${dx.toFixed(1)}px`);
          el.style.setProperty('--pea-hy-r', `${dy.toFixed(1)}px`);
        } else {
          // 鼠标不在任何 handle 热区：都归零（显示在初始位置）
          el.style.setProperty('--pea-hx-l', '0px');
          el.style.setProperty('--pea-hy-l', '0px');
          el.style.setProperty('--pea-hx-r', '0px');
          el.style.setProperty('--pea-hy-r', '0px');
        }
      }}
      onDoubleClick={onNodeDoubleClick}
      data-kind={kind}
      style={{ ...outerStyle, '--pea-hx-l': '0px', '--pea-hy-l': '0px', '--pea-hx-r': '0px', '--pea-hy-r': '0px' } as React.CSSProperties}
    >
      {/* 左手柄：用户上传的图片/视频/音频不需要接收其他节点输入，隐藏（判定见 lib/nodeSemantics） */}
      {/* 裁剪模式下隐藏连接手柄，避免遮挡裁剪交互 */}
      {acceptsUpstreamInput(data) && !cropping && (
        <Handle
          type="target"
          id="in"
          position={Position.Left}
          className="pea-handle pea-handle-left"
          onMouseEnter={() => setHovered(true)}
          style={{
            left: handleOffset,
            top: '50%',
            // 独立跟随变量：--pea-hx-l / --pea-hy-l
            '--pea-hx': 'var(--pea-hx-l)',
            '--pea-hy': 'var(--pea-hy-l)',
          } as React.CSSProperties}
        >
          <HandleGlyph />
        </Handle>
      )}
      {!cropping && (
        <Handle
          type="source"
          id="out"
          position={Position.Right}
          className="pea-handle pea-handle-right"
          onMouseEnter={() => setHovered(true)}
          style={{
            right: handleOffset,
            top: '50%',
            // 独立跟随变量：--pea-hx-r / --pea-hy-r
            '--pea-hx': 'var(--pea-hx-r)',
            '--pea-hy': 'var(--pea-hy-r)',
          } as React.CSSProperties}
        >
          <HandleGlyph />
        </Handle>
      )}

      {/* 节点 Chrome 层：标识、功能条（portal）、上传条统一放在节点框之外，
          不撑大 .react-flow__node 的 bounding box。
          - 外层不做 counter-scale → 标题徽章与节点框等比缩放（相对大小恒定）；
          - 内层 .pea-node-chrome-fixed 做 counter-scale → 交互控件屏幕大小恒定。 */}
      <div className="pea-node-chrome" ref={chromeRef} style={chromeStyle} data-zoom={zoomRef.current.toFixed(2)}>
        {!cropping && <NodeBadge id={id} kind={kind} data={data} />}
        <div className="pea-node-chrome-fixed" ref={chromeFixedRef}>
          {isText && isSingleSelected && (
            <TextNodeToolbar
              editorRef={editRef}
              // 工具条按「选中」显示，编辑区按「editing」才可编辑。
              // 用户在未进入编辑态时点格式按钮，工具条会同步打开 DOM 的 contentEditable，
              // 这里把 React 状态补齐，避免下一次 render 又把它关掉。
              onRequestEditing={() => setEditing(true)}
              onAfterExec={(html) => update(id, { html })}
            />
          )}
          {isMedia && !hasMediaContent && !data.generating && !hasUpstreamInput && (
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
        </div>
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
                if (editing) {
                  // 编辑态：阻止冒泡，避免触发节点拖动
                  e.stopPropagation();
                } else if (isText) {
                  // 文本节点：单击文本区直接进编辑态（而非发起拖动），
                  // 这样功能条(H1/粗体等)和直接输入都能用；节点拖动改由标题徽章发起。
                  // 打组进行中：抑制节点编辑态，防止子节点功能条/编辑框闪现。
                  // 用 setTimeout 延迟 setEditing：让 ReactFlow 的 onNodeClick 先完成选中，
                  // 再检查是否真的选中了本节点，避免选中过程中提前触发编辑框。
                  e.stopPropagation();
                  if (!editing && !getGroupingActive()) {
                    window.setTimeout(() => {
                      if (!useCanvas.getState().selectedIds.includes(id) || getGroupingActive()) return;
                      setEditing(true);
                    }, 0);
                  }
                } else {
                  // 非文本节点非编辑态：阻止 contentEditable 自动获取焦点，但允许冒泡给 ReactFlow 拖动
                  e.preventDefault();
                }
              }}
            />
          </div>
        ) : isMedia ? (
          <MediaNodeBody id={id} kind={kind} data={data} hasImage={hasImage} onRequestUpload={() => fileRef.current?.click()} chromeRef={chromeFixedRef} onCropChange={setCropping} />
        ) : (
          <GenericNodeBody id={id} data={data} tagLabel={tagLabel} kind={kind} />
        )}
      </div>

      {/* 编辑框锚点：NodeChatPrompt 会把节点输入栏 portal 进这个容器
          （data-pea-anchor 用于按选中节点精确匹配）。该元素缺失会导致点击节点后
          输入栏（边框框）永不弹出——这是反复回归的根因，务必保留。
          角度魔方打开时，AngleCubeOverlay 也会 portal 到此替代输入框。 */}
      <div className="pea-node-editor-anchor" data-pea-anchor={id} />

      {/* 文本节点全屏编辑弹窗（双击触发） */}
      <TextNodeEditorModal
        open={editorModalOpen}
        initialHtml={data.html ?? ''}
        onSave={onEditorModalSave}
        onCancel={() => setEditorModalOpen(false)}
      />
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
  chromeRef,
  onCropChange,
}: {
  id: string;
  kind: PeaNodeKind;
  data: PeaNodeData;
  hasImage: boolean;
  onRequestUpload: () => void;
  chromeRef: React.RefObject<HTMLDivElement | null>;
  onCropChange?: (open: boolean) => void;
}) {
  const selectedIdsArr = useCanvas((s) => s.selectedIds);
  const selected = selectedIdsArr.includes(id);
  const update = useCanvas((s) => s.updateNodeData);
  const tagLabel = tagLabelOf(kind);
  const resultUrls = data.resultUrls?.length ? data.resultUrls : data.resultUrl ? [data.resultUrl] : [];
  const index = Math.max(0, Math.min(data.resultIndex ?? 0, resultUrls.length - 1));
  // 是否有 AI 生成结果（与"用户上传"互斥）
  const hasResult = Boolean(resultUrls[index] || data.resultUrl);
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
  // image/video 节点统一不显示内部 media-label：顶部 tag-pill 已承载类型标识，内部不再重复。
  // 仅 audio 在内部保留类型标识。
  const showMediaLabel = kind === 'audio';
  // 「替换」按钮约定：仅用户上传的媒体才显示（与图片节点一致）；AI 生成结果不显示替换。
  const isUserUploaded = isUserUploadedMediaNode(data);
  const canReplace = isUserUploaded;

  if (data.generating) {
    return (
      <div className="pea-node-media-card">
        {showMediaLabel && (
          <span className="pea-node-media-label">
            <NodeIcon kind={kind} size={12} /> {tagLabel}
          </span>
        )}
        <div className="pea-node-generating" aria-label="生成中">
          <TechLoader label="生成中…" />
        </div>
      </div>
    );
  }

  if (data.error && !hasResult && !resolvedUrl) {
    return (
      <div className="pea-node-media-card">
        {showMediaLabel && (
          <span className="pea-node-media-label">
            <NodeIcon kind={kind} size={12} /> {tagLabel}
          </span>
        )}
        <NodeGenFailure id={id} error={data.error} />
      </div>
    );
  }

  // AI 生成结果：统一走 ResultMediaView（与图片节点完全一致的星标/替换/多结果/功能条/全屏）
  if (hasResult) {
    return (
      <ResultMediaView
        id={id}
        kind={kind}
        data={data}
        urls={resultUrls}
        index={index}
        onIndexChange={(i) => update(id, { resultIndex: i })}
        onReplace={onRequestUpload}
        canReplace={false}
        showMediaLabel={showMediaLabel}
        chromeRef={chromeRef}
        onCropChange={onCropChange}
      />
    );
  }

  // 用户上传的媒体：同样走 ResultMediaView，替换按钮可见
  if (data.url || data.fileKey) {
    return (
      <ResultMediaView
        id={id}
        kind={kind}
        data={data}
        urls={[resolvedUrl].filter(Boolean)}
        index={0}
        onIndexChange={() => {}}
        onReplace={onRequestUpload}
        canReplace={true}
        showMediaLabel={showMediaLabel}
        chromeRef={chromeRef}
        onCropChange={onCropChange}
      />
    );
  }

  // 空态占位
  return (
    <div className="pea-node-media-card">
      {showMediaLabel && (
        <span className="pea-node-media-label">
          <NodeIcon kind={kind} size={12} /> {tagLabel}
        </span>
      )}
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
    </div>
  );
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 生成结果媒体展示（image / video / audio 通用）：单/多结果 + 工具条 + 角标
 * 统一复用图片节点的交互：左上角收藏星标、右上角替换（仅上传）、多结果角标/选择、功能条、全屏。
 * 视频节点此前是裸 <video> + 硬编码替换按钮，且与图片节点行为不一致；现统一到此组件。
 * ═════════════════════════════════════════════════════════════════════════════ */
function ResultMediaView({
  id,
  kind,
  data,
  urls,
  index,
  onIndexChange,
  onReplace,
  canReplace,
  showMediaLabel,
  chromeRef,
  onCropChange,
}: {
  id: string;
  kind: PeaNodeKind;
  data: PeaNodeData;
  urls: string[];
  index: number;
  onIndexChange: (i: number) => void;
  onReplace: () => void;
  /** 仅用户上传媒体显示"替换"按钮；AI 生成结果按约定不显示替换 */
  canReplace: boolean;
  showMediaLabel: boolean;
  chromeRef: React.RefObject<HTMLDivElement | null>;
  onCropChange?: (open: boolean) => void;
}) {
  const [chromeReady, setChromeReady] = useState(false);
  useLayoutEffect(() => { setChromeReady(true); }, []);
  const update = useCanvas((s) => s.updateNodeData);
  const addNode = useCanvas((s) => s.addNode);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const [savingToLibrary, setSavingToLibrary] = useState(false);
  const [cropOpen, setCropOpen] = useState(false);
  // 角度魔方：单一数据源取自 store（cubeOpenNodeId），不持久化到 meta，
  // 这样关闭后再点节点只会显示节点编辑框、不会误恢复面板。
  const cubeOpenNodeId = useCanvas((s) => s.cubeOpenNodeId);
  const setCubeOpenNodeId = useCanvas((s) => s.setCubeOpenNodeId);
  const cubeOpen = cubeOpenNodeId === id;
  // 面板可见性随节点选中态联动：点空白取消选中即隐藏，点节点选中即显示
  const selected = useCanvas((s) => s.selectedIds.includes(id));
  // 多选时抑制魔方面板，避免框选多个节点时误显
  const isMulti = useCanvas((s) => s.selectedIds.length > 1);
  const imageWrapRef = useRef<HTMLDivElement>(null);  // 图片容器 ref，裁切组件用它测量尺寸并原地覆盖
  // 角度魔方锚点：与 NodeChatPrompt 同一机制，确保 DOM 挂载后才 portal
  const [cubeAnchorEl, setCubeAnchorEl] = useState<HTMLElement | null>(null);
  const liveCubeAnchor = cubeOpen && typeof document !== 'undefined'
    ? (document.querySelector<HTMLElement>(`.pea-node-editor-anchor[data-pea-anchor="${id}"]`) ?? null)
    : null;
  useEffect(() => {
    if (liveCubeAnchor) {
      setCubeAnchorEl(liveCubeAnchor);
    } else if (!cubeOpen) {
      setCubeAnchorEl(null);
    }
  }, [liveCubeAnchor, cubeOpen, id]);
  useEffect(() => {
    onCropChange?.(cropOpen);
  }, [cropOpen, onCropChange]);
  // 兼容性兜底：历史节点可能保存了外部模型视角的公网 CDN URL（如花生壳域名），
  // 当浏览器无法访问该域名时，fallback 到同域 /media/<key> 重试。
  const [fallbackUrl, setFallbackUrl] = useState<string | null>(null);
  const currentUrl = fallbackUrl || urls[index] || urls[0];

  // URL 变化时重置加载错误状态与兜底
  useEffect(() => {
    setMediaError(false);
    setFallbackUrl(null);
  }, [urls[index]]);

  // 生成参数徽章：在结果生成后才展示比例/画质
  // 读取策略：优先 genParams（image 节点写入位置），其次 meta.resolution（video 节点写入位置），
  // 两者取第一个有值的字段，避免视频节点显示 undefined。
  const _gp = (data.meta?.genParams ?? {}) as Record<string, unknown>;
  const _directMeta = (data.meta ?? {}) as Record<string, unknown>;
  const _resFromMeta = String(_directMeta.resolution ?? _gp.resolution);
  const _hasGenParams = Boolean(data.resultUrl || data.resultUrls?.length) && (_gp.aspectRatio || _resFromMeta && _resFromMeta !== 'undefined');
  const _displayRatio = _hasGenParams ? (String(_gp.aspectRatio) || undefined) : undefined;
  const _displayResolution = _hasGenParams ? (_resFromMeta && _resFromMeta !== 'undefined' ? _resFromMeta : undefined) : undefined;
  const objectKeyForImport = useMemo(() => extractObjectKey(data, currentUrl), [data, currentUrl]);
  const defaultAssetName = useMemo(() => {
    const fileName = (data.meta?.fileName as string) || data.label || '未命名';
    return fileName;
  }, [data]);

  const doImportAsset = async (payload: {
    scope: AssetScope;
    folderId: number | null;
    isFavorite?: boolean;
  }) => {
    if (!objectKeyForImport || savingToLibrary) return;
    setSavingToLibrary(true);
    try {
      await assetsApi.importAsset(
        objectKeyForImport,
        defaultAssetName,
        payload.scope,
        payload.folderId ?? undefined,
        payload.isFavorite,
      );
      // 收藏与保存到素材库拆分为两个独立状态
      update(id, payload.isFavorite ? { isFavorite: true } : { savedToLibrary: true });
      // 通知素材面板即时刷新（如收藏夹已打开，可立即看到新收藏的素材）
      window.dispatchEvent(new CustomEvent(ASSET_ASSETS_CHANGED_EVENT));
      toast.success(payload.isFavorite ? '已收藏到素材库' : '已保存到素材库');
    } catch {
      toast.error(payload.isFavorite ? '收藏到素材库失败' : '保存到素材库失败');
    } finally {
      setSavingToLibrary(false);
    }
  };

  const handleSaveToLibrary = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.isFavorite) {
      toast.info('该素材已收藏');
      return;
    }
    // 星标保持一键收藏：个人根目录 + 标记收藏
    doImportAsset({ scope: 'personal', folderId: null, isFavorite: true });
  };

  const handleToolbarSave = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.savedToLibrary) {
      toast.info('该素材已保存到素材库');
      return;
    }
    setSaveModalOpen(true);
  };

  const handleModalSave = async (payload: { scope: AssetScope; folderId: number | null }) => {
    await doImportAsset({ ...payload, isFavorite: false });
  };

  const handleFullscreen = (e: React.MouseEvent) => {
    e.stopPropagation();
    setLightboxOpen(true);
  };

  const handleCrop = (e: React.MouseEvent) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('pea:center-node', { detail: { id } }));
    setCropOpen(true);
  };

  const handleCropClose = () => {
    setCropOpen(false);
  };

  const handleCropConfirm = async (croppedDataUrl: string, size: { width: number; height: number }) => {
    // Bug 1: 修复 - 成功后再关闭浮层
    let payload: Partial<PeaNodeData>;
    const timestamp = Date.now();
    // Bug 17: 添加时间戳文件名
    let cropMeta: Record<string, unknown> = {
      fileName: `裁剪_${timestamp}.png`,
      fileSize: 0,
      croppedFrom: id,
      croppedAt: new Date().toISOString(),
    };

    try {
      const blob = await (await fetch(croppedDataUrl)).blob();
      const form = new FormData();
      form.append('file', blob, `裁剪_${timestamp}.png`);
      const { data: resp } = await api.post('/files/upload', form);
      payload = { fileKey: resp.key as string };
      // 截图产物记录原始文件大小，lightbox 信息面板才能正确显示「文件大小」
      cropMeta = { ...cropMeta, fileSize: blob.size };
    } catch (err) {
      payload = { url: croppedDataUrl };
      toast.warning('裁剪结果已使用本地预览保存（刷新后可能丢失）');
      // Bug 1: 不关闭浮层，让用户可以重试
      return;
    }

    const g = useCanvas.getState();
    const src = g.nodes.find((n) => n.id === id);
    // 输出节点使用裁剪结果的实际宽高比，不继承源节点的 aspectRatio
    const aspectRatio = simplifyRatio(size.width, size.height);
    const newSize = getNodeSize(aspectRatio, 'image');
    const srcSize = getNodeSize(src?.data.aspectRatio, src?.data.kind ?? 'image');

    // Bug 4: 修复 - 只统计直接作为裁切产物的下游节点
    const siblingCount = g.nodes.filter(n =>
      n.data.clipped &&
      g.edges.some(e => e.source === id && e.target === n.id)
    ).length;

    const srcRight = (src?.position.x ?? 0) + srcSize.width;
    const pos: { x: number; y: number } = {
      // 多次截图沿源节点右侧横向错开排列，避免重叠
      x: srcRight + 80 + siblingCount * (newSize.width + 80),
      y: src?.position.y ?? 0,
    };

    const newId = addNode({
      kind: 'image',
      label: 'Clipping diagram',
      aspectRatio,
      meta: cropMeta,
      clipped: true, // 让裁剪产物节点显示左侧输入 handle，接收来自源节点的连线
      ...payload,
    } as PeaNodeData, pos);

    if (newId) {
      // 直接建立 source → 新节点的连线，保留源节点已有的其他下游边（并列而非串链）。
      g.addEdges([{ id: `e-${id}-${newId}`, source: id, target: newId, sourceHandle: 'out', targetHandle: 'in', type: 'pea' }]);
      setCropOpen(false); // Bug 1: 成功后再关闭
      toast.success('已生成裁剪节点');
    }
  };

  const handleCube = (e: React.MouseEvent) => {
    e.stopPropagation();
    window.dispatchEvent(new CustomEvent('pea:center-node', { detail: { id, mode: 'cube' } }));
    setCubeOpenNodeId(id);
    // 同时选中节点，确保魔方面板可见（面板需要 selected 条件）
    useCanvas.getState().select(id);
  };

  const handleCubeClose = () => {
    setCubeOpenNodeId(null);
  };

  const handleCubeConfirm = async (cube: AngleCubeParams) => {
    setCubeOpenNodeId(null);

    // 取当前图片可外传的参考图 URL（与节点聊天提交保持同一套规则）
    const urls = data.resultUrls?.length ? data.resultUrls : data.resultUrl ? [data.resultUrl] : [];
    const firstUrl = urls[0] || data.url;
    let refUrl: string | undefined;
    if (firstUrl && (firstUrl.startsWith('http') || firstUrl.startsWith('data:'))) {
      refUrl = firstUrl;
    } else if (firstUrl && firstUrl.startsWith('/media/')) {
      refUrl = firstUrl;
    } else if (data.fileKey) {
      refUrl = await getPresignedUrl(data.fileKey);
    }
    if (!refUrl) {
      toast.error('无法读取当前图片，请检查图片是否已上传或刷新后重试');
      return;
    }

    const prompt = `多角度生成：以参考图主体为基础，生成水平旋转 ${cube.rotation}°、上下倾斜 ${cube.tilt}°、缩放 ${cube.zoom} 的视角${cube.wideAngle ? '，使用广角镜头' : ''}。保持人物/主体、风格、光线、背景与参考图严格一致。`;

    // 按源节点比例生成同尺寸图片，n 固定为 1，确保余额只扣 1 张
    const arText = data.aspectRatio || '9:16';
    const [arW, arH] = arText.split(':').map(Number);
    const LONG_EDGE = 1024;
    let width = LONG_EDGE;
    let height = LONG_EDGE;
    if (arW && arH) {
      if (arW >= arH) {
        width = LONG_EDGE;
        height = Math.round(LONG_EDGE * (arH / arW));
      } else {
        height = LONG_EDGE;
        width = Math.round(LONG_EDGE * (arW / arH));
      }
    }
    const params: Record<string, unknown> = {
      reference_images: [refUrl],
      n: 1,
      width,
      height,
      size: `${width}x${height}`,
    };

    const g = useCanvas.getState();
    const src = g.nodes.find((n) => n.id === id);
    const newSize = getNodeSize(data.aspectRatio, 'image');
    const srcSize = getNodeSize(src?.data.aspectRatio, src?.data.kind ?? 'image');
    const siblingCount = g.edges.filter((e) => e.source === id).length;
    const srcRight = (src?.position.x ?? 0) + srcSize.width;
    const pos = {
      x: srcRight + 80 + siblingCount * (newSize.width + 80),
      y: src?.position.y ?? 0,
    };

    const newId = addNode(
      {
        kind: 'image',
        label: '多角度',
        aspectRatio: data.aspectRatio,
        generating: true,
        clipped: true,
        meta: {
          angleCube: { rotation: cube.rotation, tilt: cube.tilt, zoom: cube.zoom, wideAngle: cube.wideAngle },
        },
      } as PeaNodeData,
      pos,
    );

    try {
      const res = await acceptNodeGenerationJob({
        type: 'image',
        prompt,
        model: cube.modelId,
        params,
        priority: 'normal',
        idempotencyKey: `angle-${id}-${Date.now()}`,
      });
      useCanvas.getState().registerJob(res.jobId, newId);
      useCanvas.getState().updateNodeData(newId, { lastJobId: res.jobId }, false);
      pollNodeJobResult(res.jobId);
      toast.success('多角度生成已受理');
    } catch (e: any) {
      const msg = e?.response?.data?.message || e?.message || '多角度生成受理失败';
      useCanvas.getState().updateNodeData(newId, { generating: false, error: msg }, false);
      toast.error(msg);
    }
  };

  const handleReplace = (e: React.MouseEvent) => {
    e.stopPropagation();
    onReplace();
  };

  const handleMediaError = (originalUrl: string) => {
    if (fallbackUrl) {
      setMediaError(true);
      return;
    }
    try {
      const u = new URL(originalUrl, window.location.href);
      if (u.pathname.startsWith('/media/')) {
        setFallbackUrl(u.pathname);
        return;
      }
    } catch {
      // ignore malformed url
    }
    setMediaError(true);
  };

  // 不同媒体类型使用不同的结果容器类名（视频沿用图片一样的"占满节点框"布局）
  const wrapClass =
    kind === 'image' ? 'pea-node-result-image-wrap'
    : kind === 'video' ? 'pea-node-result-video-wrap'
    : 'pea-node-result-audio-wrap';

  return (
    <>
      <div className={wrapClass} ref={imageWrapRef}>
        {!cropOpen && _displayRatio && (
          <span className="pea-node-gen-params-badge">{_displayRatio}{_displayResolution ? " · " + _displayResolution : ""}</span>
        )}

        {showMediaLabel && (
          <span className="pea-node-media-label">
            <NodeIcon kind={kind} size={12} /> {tagLabelOf(kind)}
          </span>
        )}

        {/* 左上角收藏星标（一键收藏到素材库）——裁剪时隐藏 */}
        {!cropOpen && (
          <button
            type="button"
            className={`pea-node-result-star ${data.isFavorite ? 'saved' : ''} ${savingToLibrary ? 'saving' : ''}`}
            onClick={handleSaveToLibrary}
            aria-label="收藏"
            title={data.isFavorite ? '已收藏' : savingToLibrary ? '收藏中…' : '收藏'}
            disabled={savingToLibrary}
          >
            {savingToLibrary ? (
              <span className="pea-node-result-star-spinner" aria-hidden />
            ) : (
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" stroke="none">
                <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
              </svg>
            )}
          </button>
        )}

        {/* 右上角：上传媒体显示"替换"按钮；多结果时追加数量角标——裁剪时隐藏 */}
        <div className="pea-node-result-overlay-tr">
          {canReplace && !cropOpen && (
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
          {urls.length > 1 && !cropOpen && (
            <div className="pea-node-image-badge">
              <button
                type="button"
                className="pea-node-image-badge-btn pea-node-image-badge-btn-hover-right"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowPicker((v) => !v);
                }}
                aria-label={`共 ${urls.length} 个`}
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
                      {kind === 'image' ? (
                        <img src={url} alt={`结果 ${i + 1}`} />
                      ) : (
                        <span className="pea-node-media-picker-thumb" aria-hidden>
                          {kind === 'video' ? '▶' : '♪'}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 主媒体：图片/视频/音频统一渲染 */}
        {mediaError || !currentUrl ? (
          <div className="pea-node-result-image-error" role="img" aria-label="媒体加载失败">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.2">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <circle cx="8.5" cy="9.5" r="1.5" />
              <path d="M3 16l5-5 4 4 3-3 6 6" />
              <path d="M22 2L2 22" />
            </svg>
            <span>媒体加载失败</span>
          </div>
        ) : kind === 'video' ? (
          <video
            src={currentUrl}
            controls
            className="pea-node-media-preview pea-node-result-preview"
            onError={() => handleMediaError(currentUrl)}
          />
        ) : kind === 'audio' ? (
          <audio src={currentUrl} controls className="pea-node-media-preview" />
        ) : (
          // 裁切时保留原图占位（visibility:hidden）以维持节点高度，裁切浮层叠在其上；
          // 视觉上只有裁切浮层的图片，不会出现"多张图"感，也不会因高度塌陷导致裁切框尺寸错乱
          // 注意：移除 loading="lazy" 避免图片延迟加载导致的模糊问题（点击节点才变清晰）
          <img
            src={currentUrl}
            alt={data.prompt || '生成结果'}
            className="pea-node-media-preview pea-node-result-preview"
            draggable={false}
            onError={() => handleMediaError(currentUrl)}
            style={cropOpen ? { visibility: 'hidden', pointerEvents: 'none' } : undefined}
          />
        )}

        {/* 图片裁剪浮层：原地渲染在图片容器内，无全屏暗化遮罩。
            覆盖整个容器（position:absolute;inset:0），内部居中显示放大图片+裁切框+工具栏。
            节点原图已设 visibility:hidden 避免重复显示。 */}
        {kind === 'image' && cropOpen && (
          <ImageCropOverlay
            url={currentUrl}
            containerRef={imageWrapRef}
            onClose={handleCropClose}
            onConfirm={handleCropConfirm}
          />
        )}
      </div>

      {/* 功能条：portal 到节点 Chrome 层，与标识/上传条统一堆叠在节点框外；裁剪时隐藏 */}
      {chromeReady && chromeRef.current && !cropOpen && createPortal(
        <ResultToolbar
          currentUrl={currentUrl}
          onSave={handleToolbarSave}
          saved={!!data.savedToLibrary}
          onFullscreen={handleFullscreen}
          onCrop={handleCrop}
          onCube={handleCube}
        />,
        chromeRef.current
      )}

      {/* 角度魔方面板：portal 到编辑锚点（替代 NodeChatPrompt 输入框），相对节点固定。
          可见性由 cubeOpenNodeId + 节点选中态共同决定：
          - 点空白 / 取消选中 → 面板隐藏（保留原行为）
          - 点该节点选中 → 面板显示
          - 刷新后 openCanvas 自动恢复选中 + cubeOpenNodeId → 面板显示
          - 仅点面板右上角 × 才清空 cubeOpenNodeId 关闭 */}
      {cubeOpen && selected && !isMulti && currentUrl && cubeAnchorEl && createPortal(
        <AngleCubeOverlay
          nodeId={id}
          url={currentUrl}
          onClose={handleCubeClose}
          onConfirm={handleCubeConfirm}
        />,
        cubeAnchorEl,
      )}

      {/* 全屏查看 */}
      {lightboxOpen && typeof document !== 'undefined' && (
        <MediaLightbox
          kind={kind}
          urls={urls}
          index={index}
          data={data}
          onClose={() => setLightboxOpen(false)}
          onIndexChange={onIndexChange}
          onSave={() => setSaveModalOpen(true)}
          saved={!!data.savedToLibrary}
        />
      )}

      <SaveToLibraryModal
        open={saveModalOpen}
        onClose={() => setSaveModalOpen(false)}
        defaultName={defaultAssetName}
        onSave={handleModalSave}
      />
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
  onCrop,
  onCube,
}: {
  currentUrl: string;
  onSave: (e: React.MouseEvent) => void;
  saved: boolean;
  onFullscreen: (e: React.MouseEvent) => void;
  onCrop: (e: React.MouseEvent) => void;
  onCube: (e: React.MouseEvent) => void;
}) {
  const soon = (label: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    toast.info(`${label} 即将上线`);
  };

  return (
    <div className="pea-node-result-toolbar" onClick={(e) => e.stopPropagation()}>
      <ToolbarButton label="裁剪" onClick={onCrop}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M6 2v14a2 2 0 0 0 2 2h14" />
          <path d="M2 6h14a2 2 0 0 1 2 2v14" />
        </svg>
      </ToolbarButton>
      <ToolbarButton label="角度魔方" onClick={onCube}>
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
      <ToolbarButton label="保存" onClick={onSave} active={saved}>
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
  const clean = url.split('?')[0];
  const ext = clean.includes('.') ? clean.split('.').pop()! : 'png';
  a.download = `pea-generate.${ext}`;
  a.click();
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 全屏查看 Lightbox（截图10）：左侧大图 + 底部缩略图 + 右侧信息面板
 * ═════════════════════════════════════════════════════════════════════════════ */
function MediaLightbox({
  kind,
  urls,
  index,
  data,
  onClose,
  onIndexChange,
  onSave,
  saved,
}: {
  kind: PeaNodeKind;
  urls: string[];
  index: number;
  data: PeaNodeData;
  onClose: () => void;
  onIndexChange: (i: number) => void;
  onSave: () => void;
  saved: boolean;
}) {
  const [current, setCurrent] = useState(index);
  const [fileSize, setFileSize] = useState<string>('-');
  const [imgDims, setImgDims] = useState<{ width: number; height: number } | null>(null);
  const currentUrl = urls[current] || urls[0];
  const isUserUploaded = isUserUploadedMediaNode(data);
  const meta = (data.meta ?? {}) as Record<string, unknown>;

  const handleSave = () => {
    if (saved) return;
    onSave();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') setCurrent((i) => Math.max(0, i - 1));
      if (e.key === 'ArrowRight') setCurrent((i) => Math.min(urls.length - 1, i + 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, urls.length]);

  // 文件大小：优先使用上传/截图时记录的 meta.fileSize；否则尝试 HEAD 读取 content-length。
  useEffect(() => {
    setFileSize('-');
    // 兼容 number 与 string（后端序列化/旧数据可能把 fileSize 存成字符串）
    const rawSize = meta.fileSize;
    const cachedSize = typeof rawSize === 'number' ? rawSize : typeof rawSize === 'string' ? Number(rawSize) : undefined;
    if (cachedSize != null && !Number.isNaN(cachedSize)) {
      setFileSize(formatBytes(cachedSize));
      return;
    }
    let cancelled = false;
    // HEAD 失败时fallback到 GET range=0-0，避免 MinIO 预签名 URL 的 CORS 限制导致大小拿不到
    const fetchSize = async () => {
      try {
        const r = await fetch(currentUrl, { method: 'HEAD', mode: 'cors' });
        const len = r.headers.get('content-length');
        if (len && !cancelled) setFileSize(formatBytes(Number(len)));
        return;
      } catch {
        // ignore HEAD failure
      }
      try {
        const r = await fetch(currentUrl, { method: 'GET', mode: 'cors', headers: { Range: 'bytes=0-0' } });
        const len = r.headers.get('content-range')?.split('/').pop() ?? r.headers.get('content-length');
        if (len && !cancelled) setFileSize(formatBytes(Number(len)));
      } catch {
        // 跨域/失败时静默保持 -
      }
    };
    fetchSize();
    return () => { cancelled = true; };
  }, [currentUrl, meta.fileSize]);

  // 真实图片尺寸：加载后读取 naturalWidth/Height，用于用户上传素材或兜底生成图比例。
  const handleImgLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    setImgDims({ width: img.naturalWidth, height: img.naturalHeight });
  };

  // 主媒体与缩略图按类型渲染（图片用 <img>，视频/音频用对应控件）
  const renderMain = (url: string) =>
    kind === 'video' ? (
      <video className="pea-node-lightbox-img" src={url} controls />
    ) : kind === 'audio' ? (
      <audio className="pea-node-lightbox-audio" src={url} controls />
    ) : (
      <img className="pea-node-lightbox-img" src={url} alt="生成结果" onLoad={handleImgLoad} />
    );

  // 宽高比展示：上传图用真实尺寸比例；生成图用 meta/params 中的配置，缺失时按真实尺寸兜底。
  const realAspectRatio = useMemo(() => {
    if (imgDims) return simplifyRatio(imgDims.width, imgDims.height);
    return undefined;
  }, [imgDims]);

  const displayAspectRatio = isUserUploaded
    ? (realAspectRatio || '—')
    : String(meta.aspectRatio || data.params?.aspectRatio || realAspectRatio || '—');

  // 模型/质量仅对 AI 生成结果有意义；用户上传素材不应显示 Agnes AI / 1K 等默认值。
  const displayModel = isUserUploaded
    ? '—'
    : String(meta.modelName || meta.model || '—');
  const displayResolution = isUserUploaded
    ? '—'
    : String(meta.resolution || data.params?.resolution || '—');

  // 创建者：用户上传显示当前用户；生成结果显示 meta.creator。
  const user = useAuth((s) => s.user);
  const displayCreator = isUserUploaded
    ? (user?.displayName || '我')
    : String(meta.creator || '—');

  // 日期：上传时间优先，否则生成时间 / 当前时间。
  const displayDate = useMemo(() => {
    const raw = meta.uploadAt || meta.createdAt || meta.generatedAt;
    if (typeof raw === 'string') {
      const d = new Date(raw);
      if (!Number.isNaN(d.getTime())) return d.toLocaleDateString('zh-CN');
    }
    if (typeof raw === 'number') return new Date(raw).toLocaleDateString('zh-CN');
    return new Date().toLocaleDateString('zh-CN');
  }, [meta]);

  // 用户上传时把「提示词」区域改为文件名，避免空白提示词显得信息缺失。
  const promptHeader = isUserUploaded ? '文件名' : '提示词';
  const promptValue = isUserUploaded
    ? String(meta.fileName || data.label || '—')
    : (data.prompt || '—');

  return createPortal(
    <div className="pea-node-lightbox" onClick={onClose}>
      <button type="button" className="pea-node-lightbox-close" onClick={onClose} aria-label="关闭">
        ×
      </button>

      {/* 左侧：大媒体 + 切换箭头 + 底部缩略图 */}
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
        {renderMain(currentUrl)}
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
                {kind === 'image' ? (
                  <img src={url} alt={`缩略图 ${i + 1}`} />
                ) : (
                  <span className="pea-node-media-picker-thumb" aria-hidden>
                    {kind === 'video' ? '▶' : '♪'}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 右侧：信息面板 */}
      <div className="pea-node-lightbox-info" onClick={(e) => e.stopPropagation()}>
        <div className="pea-node-lightbox-info-header">{promptHeader}</div>
        <div className="pea-node-lightbox-prompt">{promptValue}</div>

        <div className="pea-node-lightbox-info-header" style={{ marginTop: 24 }}>信息</div>
        <InfoRow label="模型" value={displayModel} />
        <InfoRow label="质量" value={displayResolution} />
        <InfoRow label="宽高比" value={displayAspectRatio} />
        <InfoRow label="文件大小" value={fileSize} />
        <InfoRow label="日期" value={displayDate} />
        <InfoRow label="创建者" value={displayCreator} />

        <div className="pea-node-lightbox-actions">
          <button
            type="button"
            className={`pea-node-lightbox-action primary ${saved ? 'saved' : ''}`}
            onClick={handleSave}
            disabled={saved}
          >
            {saved ? '已保存' : '保存到素材库'}
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

/**
 * 从节点数据中提取可导入素材库的 MinIO 对象 key。
 * 优先使用持久化的 fileKey；否则从 /media/<key> 或预签名 URL 中解析。
 */
function extractObjectKey(data: PeaNodeData, currentUrl: string): string | null {
  if (data.fileKey) return data.fileKey;

  const candidates = [
    data.resultUrl,
    ...(data.resultUrls ?? []),
    data.url,
    currentUrl,
  ].filter(Boolean) as string[];

  for (const raw of candidates) {
    const key = urlToObjectKey(raw);
    if (key) return key;
  }
  return null;
}

function urlToObjectKey(url: string): string | null {
  if (!url) return null;
  // 本站 CDN 相对路径 /media/<key>
  if (url.startsWith('/media/')) {
    return decodeURIComponent(url.slice(7).split('?')[0]);
  }
  try {
    const u = new URL(url, window.location.href);
    if (u.pathname.startsWith('/media/')) {
      return decodeURIComponent(u.pathname.slice(7).split('?')[0]);
    }
    // 预签名 URL 中 bucket 路径格式 /pea-media/<key>
    const parts = u.pathname.split('/').filter(Boolean);
    if (parts.length >= 2 && parts[0] === 'pea-media') {
      return decodeURIComponent(parts.slice(1).join('/'));
    }
  } catch {
    // ignore malformed URL
  }
  return null;
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 节点生成失败卡：科技风任务终端状态卡
 *
 * 把后端原始错误 (e.g. "submit error: image HTTP 520: ...") 归类成用户友好的
 * { title, hint, detail } 三段，避免把 HTML 错误页 / 堆栈直接糊到节点上。
 * 视觉方向：深色玻璃底 + 顶部琥珀状态边 + 角括号脉冲指示 + 青蓝重试按钮，
 * 让失败态成为画布「命令面板」的一部分，而非突兀的警告弹窗。
 * ═════════════════════════════════════════════════════════════════════════════ */

/** 清理提示词中的原始引用标记，避免 @image#id:filename 等内部协议泄露到 UI。
 *  - @image#xxx / @video#xxx  →  「图片」/「视频」（保留语义但隐藏内部 id 和文件名）
 *  - 多余的连续空白              →  单个空格
 */
const REF_FALLBACK_CLEAN_RE = /@(image|video)#([^\s]+):([^\s\u200B]*)/g;
function sanitizePromptForDisplay(raw?: string): string {
  if (!raw?.trim()) return '';
  return raw
    .replace(/<[^>]+>/g, '')
    .replace(REF_FALLBACK_CLEAN_RE, (_m, kind) => kind === 'video' ? '🎬 视频' : '🖼 图片')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/** 把后端原始错误归类为 { title, hint, detail }. */
function parseGenError(raw: string): { title: string; hint: string; detail: string | null } {
  const s = String(raw || '').trim();
  // 视频上游队列满 (video_queue_full): 上游明示 "retry later", 是可自愈的限流,
  // 不应误显示成「生成服务暂不可用 / 已自动退款」(编排器已放大重试桥接饱和窗口)。
  if (/video_queue_full/i.test(s)) {
    return {
      title: '视频生成队列繁忙',
      hint: '上游视频服务暂时满负荷，已自动重试；若持续请稍后再试。',
      detail: s,
    };
  }
  // HTTP 5xx / Cloudflare 5xx — 上游异常
  const http = s.match(/HTTP\s*(\d{3})/i);
  if (http) {
    const code = +http[1];
    if (code === 429) {
      return { title: '请求过于频繁', hint: '请稍候片刻再试。', detail: s };
    }
    if (code === 408 || /timeout|timed out/i.test(s)) {
      return { title: '生成超时', hint: '本次生成耗时过长，可点击重新生成。', detail: s };
    }
    if (code >= 500 && code < 600) {
      return {
        title: '生成服务暂不可用',
        hint: '上游接口返回异常，已自动退款。可稍后再试。',
        detail: s,
      };
    }
  }
  // 仅 timeout 字样, 无 HTTP
  if (/timeout|timed out/i.test(s)) {
    return { title: '生成超时', hint: '本次生成耗时过长，可点击重新生成。', detail: s };
  }
  // 模型不可用
  if (/unavailable|disabled|not\s*enabled/i.test(s)) {
    return { title: '模型暂不可用', hint: '请尝试更换模型后重试。', detail: s };
  }
  // 并发上限
  if (s.includes('并发')) {
    return { title: '已达并发上限', hint: '完成其他任务后再试。', detail: s };
  }
  // 退款 / 余额
  if (/refund|退款|余额|tapies/i.test(s)) {
    return { title: '本次生成未消耗次数', hint: '可点击重新生成继续尝试。', detail: s };
  }
  // 默认
  return {
    title: '生成失败',
    hint: '可点击重新生成继续尝试。',
    detail: s.length > 60 ? s : null,
  };
}

/** 媒体/生成节点卡片底部：回显用户填写的提示词与关键参数（修复"提示词没回显"）。
 *  多行截断（line-clamp）而非滚动条，保持卡片精致。 */
function NodePromptEcho({ data }: { data: PeaNodeData }) {
  // 优先使用用户原始输入（editorText），避免机器 prompt 泄露内部标记
  const rawEditorText = (data.meta?.editorText as string)?.trim();
  const rawPrompt = data.prompt?.trim();
  const p = rawEditorText || sanitizePromptForDisplay(rawPrompt);
  if (!p) return null;
  const params = data.params as Record<string, unknown> | undefined;
  const meta = data.meta as Record<string, unknown> | undefined;
  const bits: string[] = [];
  const aspect = params?.aspect_ratio ?? meta?.aspectRatio;
  const resolution = params?.resolution ?? meta?.resolution;
  if (aspect) bits.push(`比例 ${aspect}`);
  if (resolution) bits.push(`${resolution}`);
  if (params?.duration != null) bits.push(`时长 ${params.duration}s`);
  if (params?.audio_enabled != null) bits.push(params.audio_enabled ? '含音频' : '静音');
  if (params?.gen_mode) bits.push(`模式 ${params.gen_mode}`);
  const refs = Array.isArray(params?.reference_images) ? (params!.reference_images as unknown[]).length : 0;
  if (refs > 0) bits.push(`${refs} 张参考图`);
  const model = params?.model ?? meta?.modelId;
  if (model) bits.push(`${model}`);
  return (
    <div className="pea-node-prompt-echo" title={p}>
      <span className="pea-node-prompt-echo-label">提示词</span>
      <p className="pea-node-prompt-echo-text">{p}</p>
      {bits.length > 0 && <div className="pea-node-prompt-echo-params">{bits.join(' · ')}</div>}
    </div>
  );
}

function NodeGenFailure({ id, error }: { id: string; error: string }) {
  const update = useCanvas((s) => s.updateNodeData);
  const [dialogOpen, setDialogOpen] = useState(false);
  const parsed = useMemo(() => parseGenError(error), [error]);

  return (
    <div className="pea-node-failure" role="alert">
      <div className="pea-node-failure-head">
        <div className="pea-node-failure-mark" aria-hidden title="任务异常">
          {/* 科技风状态指示：角括号 + 脉冲琥珀点，替代传统警告圆圈 */}
          <span className="pea-node-failure-pulse" />
        </div>
        <div className="pea-node-failure-titles">
          <div className="pea-node-failure-title">{parsed.title}</div>
          <div className="pea-node-failure-hint">{parsed.hint}</div>
        </div>
      </div>
      <div className="pea-node-failure-actions">
        {parsed.detail && (
          <button
            type="button"
            className="pea-btn pea-btn--ghost pea-btn--sm"
            onClick={(e) => { e.stopPropagation(); setDialogOpen(true); }}
          >查看详情</button>
        )}
        <button
          type="button"
          className="pea-btn pea-btn--ghost pea-btn--sm"
          onClick={(e) => { e.stopPropagation(); update(id, { error: undefined }); }}
        >关闭</button>
        <button
          type="button"
          className="pea-btn pea-btn--warn pea-btn--sm"
          onClick={(e) => { e.stopPropagation(); retryNodeGeneration(id); }}
        >重新生成</button>
      </div>
      {dialogOpen && (
        <GenErrorDialog
          title={parsed.title}
          detail={parsed.detail ?? error}
          raw={error}
          onClose={() => setDialogOpen(false)}
        />
      )}
    </div>
  );
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 错误详情弹层：把冗长原始错误从「节点内联滚动」改为「浮层展示」。
 * - portal 到 body，避免被画布缩放/裁剪。
 * - 毛玻璃遮罩 + 居中科技卡，Esc / 点击遮罩关闭，支持一键复制原文。
 * ═════════════════════════════════════════════════════════════════════════════ */
function GenErrorDialog({
  title,
  detail,
  raw,
  onClose,
}: {
  title: string;
  detail: string;
  raw: string;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      toast.success('错误详情已复制');
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error('复制失败，请手动选择文本');
    }
  };

  return createPortal(
    <div className="pea-error-dialog-backdrop" onClick={onClose} role="presentation">
      <div
        className="pea-error-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="错误详情"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="pea-error-dialog-head">
          <span className="pea-error-dialog-icon" aria-hidden>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3 2 20h20L12 3Z" />
              <path d="M12 9v5" />
              <path d="M12 17h.01" />
            </svg>
          </span>
          <div className="pea-error-dialog-titles">
            <div className="pea-error-dialog-title">{title}</div>
            <div className="pea-error-dialog-sub">生成任务失败原因</div>
          </div>
          <button
            type="button"
            className="pea-error-dialog-close"
            aria-label="关闭"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <pre className="pea-error-dialog-body">{detail}</pre>
        <footer className="pea-error-dialog-foot">
          <button type="button" className="pea-btn pea-btn--ghost pea-btn--sm" onClick={copy}>
            {copied ? '已复制' : '复制错误'}
          </button>
          <button type="button" className="pea-btn pea-btn--sm" onClick={onClose}>
            知道了
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

/* ═════════════════════════════════════════════════════════════════════════════
 * 通用节点主体（generate / 其他）
 * ═════════════════════════════════════════════════════════════════════════════ */
function GenericNodeBody({
  id,
  data,
  tagLabel,
  kind,
}: {
  id: string;
  data: PeaNodeData;
  tagLabel: string;
  kind: PeaNodeKind;
}) {
  return (
    <div className="pea-node-generic-card">
          <div className="pea-node-generic-icon" aria-hidden>
            <NodeIcon kind={kind} size={36} />
          </div>
          <div className="pea-node-generic-label">{tagLabel}</div>
          {data.generating ? (
            <div className="pea-node-generating" aria-label="生成中">
              <TechLoader label="生成中…" />
            </div>
          ) : data.error && !data.resultUrl ? (
            <NodeGenFailure id={id} error={data.error} />
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

/* ═════════════════════════════════════════════════════════════════════════════
 * 节点顶部独立徽章：图标 + 可编辑名称
 * - 浮在节点框上方，不与 body-card 一体
 * - 名称 hover 显示编辑笔，点击后 inline 编辑（无编辑框外观）
 * - 媒体节点根据 AI 生成 / 用户上传显示不同默认名与状态徽标
 * ═════════════════════════════════════════════════════════════════════════════ */
function NodeBadge({
  id,
  kind,
  data,
}: {
  id: string;
  kind: PeaNodeKind;
  data: PeaNodeData;
}) {
  const update = useCanvas((s) => s.updateNodeData);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // 媒体节点：判断是 AI 生成结果还是用户上传（统一判定，见 lib/nodeSemantics）
  const isUserUploadedMedia = isUserUploadedMediaNode(data);
  const isGeneratedMedia = isGeneratedMediaNode(data);

  // 默认标签：上传媒体偏“资源”语义，生成媒体偏“生成”语义
  const defaultLabel = useMemo(() => {
    if (isGeneratedMedia) {
      const map: Record<string, string> = { image: '图片生成', video: '视频生成', audio: '音频生成' };
      return map[kind] || tagLabelOf(kind);
    }
    if (isUserUploadedMedia) {
      const map: Record<string, string> = { image: '图片', video: '视频', audio: '音频' };
      return map[kind] || tagLabelOf(kind);
    }
    return tagLabelOf(kind);
  }, [kind, isGeneratedMedia, isUserUploadedMedia]);

  const displayLabel = data.label || defaultLabel;

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDraft(displayLabel);
    setEditing(true);
  };

  const commit = () => {
    const value = draft.trim();
    if (value && value !== defaultLabel) {
      update(id, { label: value });
    } else {
      // 清空或等于默认值：恢复自动标签
      update(id, { label: undefined });
    }
    setEditing(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    e.stopPropagation();
    if (e.key === 'Enter') {
      commit();
    } else if (e.key === 'Escape') {
      setEditing(false);
    }
  };

  const onBlur = () => {
    commit();
  };

  const color = kindColor(kind);
  const isGenerated = isGeneratedMedia || kind === 'generate';

  return (
    <div
      className={`pea-node-badge ${isGenerated ? 'is-generated' : ''} ${isUserUploadedMedia ? 'is-uploaded' : ''}`}
      style={{ '--pea-node-badge-color': color } as React.CSSProperties}
      onDoubleClick={(e) => e.stopPropagation()}
    >
      <span className="pea-node-badge-icon" aria-hidden>
        <NodeIcon kind={kind} size={13} color={color} />
      </span>

      {editing ? (
        <input
          ref={inputRef}
          type="text"
          className="pea-node-badge-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={onBlur}
          onClick={(e) => e.stopPropagation()}
          maxLength={18}
        />
      ) : (
        <button
          type="button"
          className="pea-node-badge-label"
          onClick={startEdit}
          title="点击修改名称"
        >
          <span className="pea-node-badge-text">{displayLabel}</span>
          {isGeneratedMedia && (
            <span className="pea-node-badge-dot generated" aria-hidden>
              <GeneratingBadge size={9} />
            </span>
          )}
          {isUserUploadedMedia && (
            <span className="pea-node-badge-dot uploaded" aria-hidden>
              <UploadBadge size={9} />
            </span>
          )}
          <span className="pea-node-badge-edit" aria-hidden>
            <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
          </span>
        </button>
      )}
    </div>
  );
}

/* 连接点图标：科技感「连接端口」——外环 + 旋转虚线转子 + 发光核心。
   缩小时仍清晰可辨，悬停/连线时转子旋转。 */
function HandleGlyph() {
  return (
    <svg className="pea-handle-glyph" viewBox="0 0 24 24" aria-hidden>
      <circle className="hg-ring" cx="12" cy="12" r="7.5" />
      <circle className="hg-rotor" cx="12" cy="12" r="10" />
      <circle className="hg-core" cx="12" cy="12" r="3.2" />
    </svg>
  );
}

function tagLabelOf(k: string): string {
  // 与 nodeTypes.ts 的中文标签保持一致，作为徽章默认名称的唯一来源
  return NODE_DEF_OF(k).label;
}
