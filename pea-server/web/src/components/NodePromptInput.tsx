import { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import { createPortal } from 'react-dom';
import { Node as FlowNode } from 'reactflow';
import { useCanvas, PeaNodeData } from '../store/canvas';
import { getFileUrl, getPresignedUrl } from '../api/files';
import { PeaNodeKind } from '../constants/nodeTypes';

/**
 * 节点生成提示词富文本输入框。
 * 支持：
 *  - 普通文本输入
 *  - @ 唤出上游节点选择器（图片/文本）
 *  - 选中后插入不可编辑的内联 token，显示缩略图/文本摘要
 *  - 发送时解析为 { text, referenceImages, referencedNodeIds }
 *
 * 占位符协议：
 *  - 编辑态：DOM 中是一个 <span class="pea-ref" contenteditable=false data-node-id="n1" data-kind="image">...缩略图...</span>
 *  - 纯文本fallback：@image#n1:filename
 *  - 解析时按 DOM 顺序读取 token，确保多参考图顺序与视觉一致。
 */

export interface ParsedPrompt {
  text: string;
  referenceImages: string[];
  referencedNodeIds: string[];
  /** 编辑器完整 HTML（含 @ 引用 token），用于持久化，避免刷新后引用丢失 */
  html: string;
}

export interface NodePromptInputRef {
  getParsed: () => ParsedPrompt;
  setHtml: (html: string) => void;
  focus: (opts?: FocusOptions) => void;
  get plainText(): string;
  /** 生成带「参考图N」编号的正文（媒体 @ token 替换为编号），N 由调用方按 reference_images 顺序给定 */
  getBodyText: (refNumberById?: Map<string, number>) => string;
  /**
   * 摘除指定上游节点的 @ 引用 token（连线被删 / 上游节点被删时调用）。
   * 返回是否发生了实际变更，便于调用方决定是否同步草稿。
   */
  removeRefTokens: (nodeIds: string[]) => boolean;
}

interface UpstreamItem {
  node: FlowNode<PeaNodeData>;
  kind: PeaNodeKind;
  label: string;
  thumbUrl?: string;
  textSummary?: string;
}

interface NodePromptInputProps {
  nodeId: string;
  kind: PeaNodeKind;
  placeholder?: string;
  initialHtml?: string;
  onChange?: (html: string, plainText: string) => void;
  onSubmit?: () => void;
  /** 当通过 @ 选择器插入图片/视频引用 token 时回调,便于外部引用条同步 */
  onInsertReference?: (nodeId: string) => void;
}

/** 从节点数据提取可作为参考图/文本引用的 URL 或内容（仅浏览器内显示用）。 */
async function resolveNodeMediaUrl(node: FlowNode<PeaNodeData>): Promise<string | undefined> {
  const d = node.data;
  const urls = d.resultUrls?.length ? d.resultUrls : d.resultUrl ? [d.resultUrl] : [];
  const firstUrl = urls[0] || d.url;
  // 优先返回浏览器可直接加载的绝对 URL。
  if (firstUrl && firstUrl.startsWith('http') && !firstUrl.startsWith('//')) return firstUrl;
  if (firstUrl && firstUrl.startsWith('data:')) return firstUrl;
  if (firstUrl && firstUrl.startsWith('blob:')) return firstUrl;
  if (d.fileKey) {
    // 显示用途优先走 BFF 代理的 blob URL（同源，浏览器必然可加载，且不受 MinIO 内网/
    // CORS 限制影响）；仅当 BFF 代理失败时才退回预签名直链（可能被内网隔离导致浏览器加载失败）。
    // 注意：此处的返回值只用于「浏览器内显示」（picker 缩略图 / @ token），不会泄漏到
    // 发给模型的 reference_images（参考图走 resolveUpstreamMediaUrl 的预签名直链）。
    try {
      const blob = await getFileUrl(d.fileKey);
      if (blob) return blob;
    } catch (e) {
      console.warn('[resolveNodeMediaUrl] getFileUrl failed', { nodeId: node.id, fileKey: d.fileKey, error: e });
    }
    try {
      const pu = await getPresignedUrl(d.fileKey);
      if (pu) return pu;
    } catch (e) {
      console.warn('[resolveNodeMediaUrl] getPresignedUrl also failed', { nodeId: node.id, fileKey: d.fileKey, error: e });
    }
  }
  // 兜底：返回本站公开 CDN 相对路径 /media/...，由 nginx 反代加载（浏览器内显示）。
  // 注意：此 URL 不会发给外部模型，仅用于编辑器/picker 缩略图展示。
  if (firstUrl && firstUrl.startsWith('/media/')) return firstUrl;
  if (!firstUrl && !d.fileKey) {
    console.warn('[resolveNodeMediaUrl] no resolvable media source', { nodeId: node.id, keys: Object.keys(d) });
  }
  return undefined;
}

function getTextSummary(node: FlowNode<PeaNodeData>, max = 60): string {
  const raw = node.data.prompt || node.data.html || '';
  const text = raw.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
  if (!text) return '空文本';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

function getFileName(node: FlowNode<PeaNodeData>): string {
  const meta = (node.data.meta ?? {}) as Record<string, string>;
  if (meta.fileName) return meta.fileName;
  const url = node.data.url || node.data.resultUrl || node.data.resultUrls?.[0];
  if (url) {
    try {
      const u = new URL(url);
      const parts = u.pathname.split('/');
      const name = parts[parts.length - 1];
      if (name) return decodeURIComponent(name);
    } catch {
      // ignore
    }
  }
  return '图片';
}

function isMediaKind(k: PeaNodeKind): boolean {
  return k === 'image' || k === 'video';
}

function isTextKind(k: PeaNodeKind): boolean {
  return k === 'text';
}

function canReference(k: PeaNodeKind): boolean {
  return isMediaKind(k) || isTextKind(k);
}

/**
 * 根据当前节点类型决定可引用的上游节点类型。
 * - 图片/视频/生成节点：只能引用媒体节点作为参考图。
 * - 文本节点：可引用媒体（作为参考图）和文本（作为 prompt 来源）。
 * 这样图片节点里 @ 时不会出现连接的文本节点，避免用户误选文本作为图片参考。
 */
function canReferenceForKind(hostKind: PeaNodeKind, targetKind: PeaNodeKind): boolean {
  if (hostKind === 'image' || hostKind === 'video' || hostKind === 'generate') {
    return isMediaKind(targetKind);
  }
  return canReference(targetKind);
}

/** 在光标处插入一个不可编辑 token。
 *  kind=image 时 label 应为合法图片 URL（http(s)/data:/blob:）；
 *  若尚未解析完成，渲染为占位图标，后续由 resolvedThumbs sync effect 替换为真实图片。
 *  禁止直接用 <img src="">，否则部分浏览器会显示裂图/alt 文本，破坏视觉。
 */
function replaceWithImagePlaceholder(target: HTMLElement) {
  const fallback = document.createElement('span');
  fallback.className = 'pea-ref-thumb pea-ref-thumb-fallback-inline';
  fallback.textContent = '\u{1F5BC}';
  fallback.setAttribute('data-pea-pending', '1');
  target.replaceWith(fallback);
}

function createImageRefThumb(url: string, fileKey?: string | null): HTMLElement {
  const img = document.createElement('img');
  img.className = 'pea-ref-thumb';
  img.src = url;
  img.alt = '';
  img.loading = 'lazy';
  img.onerror = () => {
    // 真实 URL（如过期 presigned / MinIO 直连失败）加载失败时，
    // 优先尝试用 blob URL（走 BFF 代理）回显，仍失败再降级为占位图标。
    if (fileKey) {
      getFileUrl(fileKey)
        .then((blobUrl) => {
          if (blobUrl) {
            img.src = blobUrl;
            img.removeAttribute('data-pea-pending');
          } else {
            replaceWithImagePlaceholder(img);
          }
        })
        .catch(() => replaceWithImagePlaceholder(img));
    } else {
      replaceWithImagePlaceholder(img);
    }
  };
  return img;
}

function createImageRefPlaceholder(): HTMLElement {
  const span = document.createElement('span');
  span.className = 'pea-ref-thumb pea-ref-thumb-fallback-inline';
  span.textContent = '\u{1F5BC}';
  span.setAttribute('data-pea-pending', '1');
  return span;
}

function isValidImageUrl(url: unknown): url is string {
  return typeof url === 'string' && url.length > 0 && (url.startsWith('http') || url.startsWith('data:') || url.startsWith('blob:'));
}

function insertRefToken(
  editor: HTMLElement,
  nodeId: string,
  kind: PeaNodeKind,
  label: React.ReactNode,
  fileKey?: string | null,
) {
  const span = document.createElement('span');
  span.className = 'pea-ref';
  span.contentEditable = 'false';
  span.setAttribute('data-node-id', nodeId);
  span.setAttribute('data-kind', kind);
  span.setAttribute('data-pea-ref', '1');
  if (fileKey) span.setAttribute('data-file-key', fileKey);
  const inner = document.createElement('span');
  inner.className = 'pea-ref-inner';
  inner.contentEditable = 'false';
  if (kind === 'image') {
    const imgUrl = isValidImageUrl(label) ? label : '';
    inner.appendChild(imgUrl ? createImageRefThumb(imgUrl, fileKey) : createImageRefPlaceholder());
  } else if (kind === 'video') {
    const videoUrl = isValidImageUrl(label) ? label : '';
    // 视频 token 在编辑框中展示为「可识别的视频 pill」：优先显示文件名，hover/发送时解析真实 URL。
    inner.appendChild(videoUrl ? createVideoRefThumb(videoUrl, fileKey) : createVideoRefPlaceholder(getFileNameFromLabel(label)));
  } else {
    inner.innerHTML = `<span class="pea-ref-text">${label}</span>`;
  }
  span.appendChild(inner);

  const sel = window.getSelection();
  if (sel && sel.rangeCount > 0) {
    const range = sel.getRangeAt(0);
    range.deleteContents();
    range.insertNode(span);
    const zwsp = document.createTextNode('\u200B');
    span.after(zwsp);
    range.setStartAfter(zwsp);
    range.setEndAfter(zwsp);
    sel.removeAllRanges();
    sel.addRange(range);
  } else {
    editor.appendChild(span);
    editor.appendChild(document.createTextNode('\u200B'));
  }
  editor.focus({ preventScroll: true });
  renumberRefChips(editor);
}

function createVideoRefThumb(url: string, fileKey?: string | null): HTMLElement {
  const wrap = document.createElement('span');
  wrap.className = 'pea-ref-thumb pea-ref-thumb-video';
  wrap.setAttribute('data-pea-pending', '0');
  // 用视频首帧作为缩略图：video + img poster 双重保障
  const video = document.createElement('video');
  video.src = url;
  video.preload = 'metadata';
  video.muted = true;
  video.playsInline = true;
  video.className = 'pea-ref-thumb-video-el';
  video.onerror = () => {
    if (fileKey) {
      getFileUrl(fileKey)
        .then((blobUrl) => { if (blobUrl && video.parentElement) video.src = blobUrl; })
        .catch(() => { /* leave fallback icon */ });
    }
  };
  wrap.appendChild(video);
  return wrap;
}

function createVideoRefPlaceholder(label?: string): HTMLElement {
  const span = document.createElement('span');
  span.className = 'pea-ref-thumb pea-ref-thumb-fallback-inline pea-ref-thumb-video-fallback';
  span.setAttribute('data-pea-pending', '1');
  span.textContent = label || '\u{1F3AC}';
  return span;
}

function getFileNameFromLabel(label: React.ReactNode): string | undefined {
  if (typeof label === 'string') return label;
  if (typeof label === 'number') return String(label);
  return undefined;
}

/** 纯文本 fallback 格式：@image#n1:filename / @video#n1:filename */
const REF_FALLBACK_RE = /@(image|video)#([^:]+):([^\s\u200B]+)/g;

/** 根据 nodeId 在当前上游节点中查找并插入对应 token。 */
function tryInsertRefByNodeId(
  editor: HTMLElement,
  nodeId: string,
  kind: PeaNodeKind,
  resolvedThumbs: Record<string, string>,
): boolean {
  const node = useCanvas.getState().nodes.find((n) => n.id === nodeId);
  if (!node) return false;
  if (!canReferenceForKind(kind as PeaNodeKind, node.data.kind)) return false;
  const display = isTextKind(node.data.kind)
    ? getTextSummary(node)
    : (resolvedThumbs[nodeId] || getFileName(node));
  insertRefToken(editor, nodeId, node.data.kind, display, node.data.fileKey);
  return true;
}

/** 把编辑器内残留的纯文本 fallback 转换为真实 token。 */
function hydrateFallbackTokens(
  editor: HTMLElement,
  hostKind: PeaNodeKind,
  resolvedThumbs: Record<string, string>,
): boolean {
  let changed = false;
  // 遍历所有文本节点，查找 fallback 文本
  const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT, null);
  const matches: Array<{ node: globalThis.Text; start: number; kind: PeaNodeKind; nodeId: string; name: string }> = [];
  let textNode: globalThis.Node | null;
  while ((textNode = walker.nextNode())) {
    const str = textNode.textContent || '';
    REF_FALLBACK_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = REF_FALLBACK_RE.exec(str))) {
      const kind = m[1] as PeaNodeKind;
      const nodeId = m[2];
      const name = m[3];
      if (canReferenceForKind(hostKind, kind)) {
        matches.push({ node: textNode as globalThis.Text, start: m.index, kind, nodeId, name });
      }
    }
  }
  // 从后往前替换，避免 offset 漂移
  for (let i = matches.length - 1; i >= 0; i--) {
    const { node, start, kind, nodeId, name } = matches[i];
    const full = `@${kind}#${nodeId}:${name}`;
    const text = node.textContent || '';
    const before = text.slice(0, start);
    const after = text.slice(start + full.length);
    // 先创建 token
    const refNode = document.createElement('span');
    refNode.className = 'pea-ref';
    refNode.contentEditable = 'false';
    refNode.setAttribute('data-node-id', nodeId);
    refNode.setAttribute('data-kind', kind);
    refNode.setAttribute('data-pea-ref', '1');
    const upstreamNode = useCanvas.getState().nodes.find((n) => n.id === nodeId);
    if (upstreamNode?.data.fileKey) refNode.setAttribute('data-file-key', upstreamNode.data.fileKey);
    const inner = document.createElement('span');
    inner.className = 'pea-ref-inner';
    inner.contentEditable = 'false';
    if (kind === 'image') {
      const url = resolvedThumbs[nodeId];
      inner.appendChild(url ? createImageRefThumb(url, upstreamNode?.data.fileKey) : createImageRefPlaceholder());
    } else if (kind === 'video') {
      const url = resolvedThumbs[nodeId];
      inner.appendChild(url ? createVideoRefThumb(url, upstreamNode?.data.fileKey) : createVideoRefPlaceholder(name));
    } else {
      inner.innerHTML = `<span class="pea-ref-text">${name}</span>`;
    }
    refNode.appendChild(inner);
    // 替换文本节点
    const parent = node.parentNode;
    if (!parent) continue;
    if (before) parent.insertBefore(document.createTextNode(before), node);
    parent.insertBefore(refNode, node);
    if (after) parent.insertBefore(document.createTextNode(after), node);
    parent.removeChild(node);
    // token 后补零宽空格光标锚点
    const zwsp = document.createTextNode('\u200B');
    parent.insertBefore(zwsp, refNode.nextSibling);
    changed = true;
  }
  if (changed) renumberRefChips(editor);
  return changed;
}

/** 清理编辑器内孤立/损坏的 token（无对应上游节点或 kind 不匹配）。 */
function pruneOrphanRefTokens(editor: HTMLElement, hostKind: PeaNodeKind): boolean {
  let changed = false;
  editor.querySelectorAll<HTMLElement>('[data-pea-ref="1"]').forEach((span) => {
    const id = span.getAttribute('data-node-id');
    const kind = span.getAttribute('data-kind') as PeaNodeKind | null;
    if (!id || !kind) return;
    const node = useCanvas.getState().nodes.find((n) => n.id === id);
    if (!node || !canReferenceForKind(hostKind, node.data.kind)) {
      const next = span.nextSibling;
      span.remove();
      if (next && next.nodeType === Node.TEXT_NODE && (next.textContent ?? '') === '\u200B') {
        next.parentNode?.removeChild(next);
      }
      changed = true;
    }
  });
  if (changed) renumberRefChips(editor);
  return changed;
}

/**
 * 给编辑器内所有 @ token 按「文档顺序」标注 data-ref-index（供内部/调试使用）。
 * 产品侧决定不在前端显示「参考图N」文本角标：用户只需看到图片/文本本身，
 * 编号仅在发给模型的 prompt 中通过 getBodyText + buildReferenceBlock 体现。
 */
function renumberRefChips(editor: HTMLElement) {
  const spans = Array.from(editor.querySelectorAll<HTMLElement>('[data-pea-ref="1"]'));
  spans.forEach((span, i) => {
    span.setAttribute('data-ref-index', String(i + 1));
  });
}

/**
 * 把编辑器内已存在的 @ 媒体 token 的缩略图指向最新 resolvedThumbs；
 * 若当前是占位图标则替换为真实 <img>/<video>。
 * 提取为独立函数，供「resolvedThumbs 同步 effect」与「粘贴后」两个入口复用——
 * 后者尤为关键：从另一节点复制出来的 <img src="blob:..."> 在原文档可能有效，
 * 但在目标节点上下文里若 blob 已被回收/不可达，必须重新指向当前 resolvedThumbs。
 */
function refreshTokenThumbnails(editor: HTMLElement, resolvedThumbs: Record<string, string>) {
  editor.querySelectorAll<HTMLElement>('[data-pea-ref="1"]').forEach((span) => {
    const id = span.getAttribute('data-node-id');
    const k = span.getAttribute('data-kind') as PeaNodeKind;
    if (!id || !isMediaKind(k)) return;
    const url = resolvedThumbs[id];
    if (!url) return;
    const fileKey = span.getAttribute('data-file-key');

    // 情况 1：当前是占位图标 -> 直接替换为真实媒体
    const placeholder = span.querySelector('span.pea-ref-thumb-fallback-inline');
    if (placeholder) {
      placeholder.replaceWith(k === 'video' ? createVideoRefThumb(url, fileKey) : createImageRefThumb(url, fileKey));
      return;
    }

    // 情况 2：当前已有 <img> -> 仅当 URL 真正变化时才更新 src
    const img = span.querySelector('img.pea-ref-thumb');
    if (img) {
      if (img.getAttribute('src') !== url) {
        img.setAttribute('src', url);
        img.removeAttribute('data-pea-pending');
      }
      return;
    }

    // 情况 3：当前是 video token -> 更新 video src
    const video = span.querySelector('video.pea-ref-thumb-video-el') as HTMLVideoElement | null;
    if (video && video.getAttribute('src') !== url) {
      video.setAttribute('src', url);
      video.load();
    }
  });
}

/** 把编辑器内容序列化为「纯文本复制」形式：媒体 @ token 转成 @image#id:filename，
 *  文本 @ token 展开为节点文本。这样即使用户把提示词粘贴到外部编辑器/另一节点，
 *  参考图引用信息也不丢失（目标节点的 handlePaste 会重新 hydrate 成真实 token）。 */
function getFileNameForNode(id: string): string | undefined {
  const node = useCanvas.getState().nodes.find((n) => n.id === id);
  if (!node) return undefined;
  return getFileName(node);
}

function nodeToPlain(node: globalThis.Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent || '';
  if (node.nodeType === Node.ELEMENT_NODE) {
    const el = node as HTMLElement;
    if (el.getAttribute('data-pea-ref') === '1') {
      const id = el.getAttribute('data-node-id') || '';
      const kind = el.getAttribute('data-kind') || 'image';
      if (kind === 'image' || kind === 'video') {
        const name = getFileNameForNode(id) || (kind === 'video' ? '视频' : '图片');
        return `@${kind}#${id}:${name}`;
      }
      const src = useCanvas.getState().nodes.find((n) => n.id === id);
      return src ? getTextSummary(src, 100000) : '';
    }
    let s = '';
    el.childNodes.forEach((c) => {
      s += nodeToPlain(c);
    });
    return s;
  }
  return '';
}

function serializeEditorForCopy(editor: HTMLElement): string {
  let out = '';
  editor.childNodes.forEach((c) => {
    out += nodeToPlain(c);
  });
  return out.replace(/\u200B/g, '');
}

/** 清理旧版持久化 HTML 中残留的「参考图N」角标，避免产品改版后仍显示旧文本。 */
function stripLegacyRefBadges(editor: HTMLElement) {
  editor.querySelectorAll('.pea-ref-badge').forEach((badge) => {
    badge.parentNode?.removeChild(badge);
  });
}

/**
 * 把光标移动到富文本编辑器内容的末尾。
 * 用途：还原/刷新后重新回填编辑框内容时，让光标停在文本末尾，
 * 而不是浏览器默认的「内容起始位置」——否则用户继续输入会插到最前面。
 */
function placeCaretAtEnd(el: HTMLElement) {
  el.focus({ preventScroll: true });
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false); // false = 折叠到末尾
  const sel = window.getSelection();
  if (sel) {
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

export default forwardRef<NodePromptInputRef, NodePromptInputProps>(function NodePromptInput(
  { nodeId, kind, placeholder = '描述你想生成的内容，或输入 @ 引用上游节点', initialHtml = '', onChange, onSubmit, onInsertReference },
  ref,
) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [html, setHtmlState] = useState(initialHtml);
  const [plainText, setPlainText] = useState('');
  const [showPicker, setShowPicker] = useState(false);
  const [pickerPos, setPickerPos] = useState<{ left: number; top: number } | null>(null);
  const [filter, setFilter] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [upstream, setUpstream] = useState<UpstreamItem[]>([]);
  const [resolvedThumbs, setResolvedThumbs] = useState<Record<string, string>>({});
  // 关键修复：lastHtmlRef 初始必须为「与挂载内容不同」的哨兵值，
  // 否则 didInit 把 initialHtml 写入编辑器后，syncFromEditor 会判定
  // nextHtml === lastHtmlRef.current 而跳过 onChange —— 导致从 meta.editorText
  // 还原的内容（如图片/视频节点刷新后恢复）不会触发 setHasInput，发送按钮持续置灰。
  const lastHtmlRef = useRef('');
  const atTriggerRef = useRef<{ node: globalThis.Node; offset: number } | null>(null);
  const atTriggerActiveRef = useRef(false);

  const getUpstream = useCallback((): UpstreamItem[] => {
    const inputs = useCanvas.getState().getUpstreamInputs(nodeId);
    return inputs
      .filter((n) => canReferenceForKind(kind, n.data.kind))
      .map((n) => ({
        node: n,
        kind: n.data.kind,
        label: isTextKind(n.data.kind) ? getTextSummary(n) : getFileName(n),
      }));
  }, [nodeId, kind]);

  useEffect(() => {
    const load = async () => {
      const items = getUpstream();
      setUpstream(items);
      const thumbs: Record<string, string> = {};
      for (const item of items) {
        if (isMediaKind(item.kind)) {
          const url = await resolveNodeMediaUrl(item.node);
          if (url) thumbs[item.node.id] = url;
        }
      }
      setResolvedThumbs(thumbs);
    };
    load();
  }, [getUpstream, nodeId]);

  useEffect(() => {
    const unsub = useCanvas.subscribe((s) => {
      const items = s.getUpstreamInputs(nodeId)
        .filter((n) => canReferenceForKind(kind, n.data.kind))
        .map((n) => ({
          node: n,
          kind: n.data.kind,
          label: isTextKind(n.data.kind) ? getTextSummary(n) : getFileName(n),
        }));
      setUpstream((prev) => {
        const same =
          prev.length === items.length && prev.every((p, i) => p.node.id === items[i]?.node.id);
        return same ? prev : items;
      });
    });
    return unsub;
  }, [nodeId, kind]);

  // 上游媒体源指纹：直接读取 store 中上游节点的 fileKey/url/resultUrl/resultUrls。
  // 关键修复：之前从 `upstream` 数组引用派生，但 subscribe effect 在节点数据变化
  // （如上传图回填 fileKey、AI 生成回填 resultUrl）时会保留同一数组引用，导致指纹不变、
  // 缩略图永不刷新（picker 不显示图片、已插入 @ token 裂图）。改为每次 store 变化时
  // 重新计算指纹，仅当媒体源真的变了才更新，从而可靠触发缩略图重新解析。
  const [mediaKey, setMediaKey] = useState('');

  const computeMediaKey = useCallback(() => {
    const items = useCanvas
      .getState()
      .getUpstreamInputs(nodeId)
      .filter((n) => canReferenceForKind(kind, n.data.kind))
      .map((n) => {
        const d = n.data;
        const urls = (d.resultUrls || []).join(',');
        return `${n.id}:${d.fileKey || ''}:${d.url || ''}:${d.resultUrl || ''}:${urls}`;
      })
      .join('|');
    setMediaKey((prev) => (prev === items ? prev : items));
  }, [nodeId, kind]);

  // 挂载时计算一次
  useEffect(() => {
    computeMediaKey();
  }, [computeMediaKey]);

  // store 任意变化都重算指纹（computeMediaKey 内部保证值不变时不触发更新，避免无谓刷新）
  useEffect(() => {
    const unsub = useCanvas.subscribe(() => {
      computeMediaKey();
    });
    return unsub;
  }, [computeMediaKey]);

  useEffect(() => {
    if (!mediaKey) return;
    let alive = true;
    const items = useCanvas
      .getState()
      .getUpstreamInputs(nodeId)
      .filter((n) => canReferenceForKind(kind, n.data.kind));
    (async () => {
      const thumbs: Record<string, string> = {};
      for (const n of items) {
        if (isMediaKind(n.data.kind)) {
          const url = await resolveNodeMediaUrl(n);
          if (url && alive) thumbs[n.id] = url;
        }
      }
      if (alive) setResolvedThumbs(thumbs);
    })();
    return () => {
      alive = false;
    };
  }, [mediaKey, nodeId, kind]);

  // 引用 token 缩略图同步：当 resolvedThumbs 重新解析（如刷新后、上传图签名 URL 过期）时，
  // 把编辑器中已存在的 @ token 的缩略图指向最新 URL；若当前是占位图标则替换为真实 <img>/<video>。
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    refreshTokenThumbnails(editor, resolvedThumbs);
  }, [resolvedThumbs]);

  const syncFromEditor = useCallback(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const nextHtml = editor.innerHTML;
    const nextText = editor.innerText || '';
    if (nextHtml !== lastHtmlRef.current) {
      lastHtmlRef.current = nextHtml;
      setHtmlState(nextHtml);
      setPlainText(nextText);
      onChange?.(nextHtml, nextText);
    }
  }, [onChange]);

  // 仅在挂载时按 initialHtml 初始化一次。之后切换节点由父组件通过 setHtml 显式还原，
  // 这里不再随 initialHtml 变化反复回填——否则用户清空文本后，initialHtml 回退到
  // editorText(旧 prompt) 会把旧文本重新顶回来(用户反馈「删光文本又全冒出来」)。
  const didInitRef = useRef(false);
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || didInitRef.current) return;
    didInitRef.current = true;
    const init = initialHtml || '';
    if (editor.innerHTML !== init) {
      editor.innerHTML = init;
      stripLegacyRefBadges(editor);
      // 关键修复：把纯文本 fallback（如 @image#n1:name）转换回真实 token，
      // 并清理已不存在上游节点的孤立 token。这在复制提示词/跨节点粘贴后尤为重要。
      const changed1 = hydrateFallbackTokens(editor, kind, resolvedThumbs);
      const changed2 = pruneOrphanRefTokens(editor, kind);
      if (changed1 || changed2) {
        syncFromEditor();
      }
      renumberRefChips(editor);
    }
    // 还原内容后把光标停在末尾（修复：刷新/打开节点后光标停在开头，
    // 用户继续输入会插到最前面）。仅在有内容时聚焦；空的新节点保持原行为
    // （由节点切换 effect 的 setTimeout(focus) 处理，避免无谓抢焦点）。
    if (init) placeCaretAtEnd(editor);
  }, [initialHtml, syncFromEditor, kind, resolvedThumbs]);

  useImperativeHandle(ref, () => ({
    removeRefTokens: (nodeIds: string[]) => {
      const editor = editorRef.current;
      if (!editor || !nodeIds.length) return false;
      const kill = new Set(nodeIds);
      let changed = false;
      editor.querySelectorAll<HTMLElement>('[data-pea-ref="1"]').forEach((span) => {
        const id = span.getAttribute('data-node-id');
        if (!id || !kill.has(id)) return;
        // 连同 token 后的零宽空格光标锚点一起清掉，避免残留不可见字符
        const next = span.nextSibling;
        if (next && next.nodeType === Node.TEXT_NODE && (next.textContent ?? '') === '\u200B') {
          next.parentNode?.removeChild(next);
        }
        span.remove();
        changed = true;
      });
      if (changed) {
        renumberRefChips(editor);
        syncFromEditor();
      }
      return changed;
    },
    getParsed: () => {
      const editor = editorRef.current;
      if (!editor) return { text: '', referenceImages: [], referencedNodeIds: [], html: '' };
      const refSpans = Array.from(editor.querySelectorAll('[data-pea-ref="1"]'));
      const referencedNodeIds: string[] = [];
      const referenceImages: string[] = [];
      refSpans.forEach((span) => {
        const id = span.getAttribute('data-node-id');
        const k = span.getAttribute('data-kind') as PeaNodeKind;
        if (!id) return;
        referencedNodeIds.push(id);
        if (isMediaKind(k)) {
          // 优先用预解析的缩略图 URL（含上传图签名 URL）；
          // 兜底：resolvedThumbs 尚未就绪时，直接从节点 data 同步解析
          // （AI 生成图有 resultUrls/url，无需异步），避免 token 在场却解析为空。
          let url: string | null | undefined = resolvedThumbs[id];
          if (!url) {
            const node = useCanvas.getState().nodes.find((n) => n.id === id);
            if (node) {
              const d = node.data;
              const urls = d.resultUrls?.length ? d.resultUrls : d.resultUrl ? [d.resultUrl] : [];
              url = urls[0] || d.url || null;
            }
          }
          // blob: 和相对路径(/media/...) 仅浏览器内/反代可达，模型侧无法下载（编排器会静默丢弃），
          // 参考图真实可外传地址由 resolveUpstreamMediaUrl 的预签名直链提供，
          // 因此这里不把非 http(s) URL 纳入 reference_images，避免发送无效参考。
          if (url && url.startsWith('http') && !url.startsWith('//') && !referenceImages.includes(url)) referenceImages.push(url);
        }
      });
      let text = '';
      const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
        acceptNode: (n: globalThis.Node) => {
          if ((n as HTMLElement).getAttribute?.('data-pea-ref') === '1') return NodeFilter.FILTER_ACCEPT;
          if (n.nodeType === globalThis.Node.TEXT_NODE) return NodeFilter.FILTER_ACCEPT;
          return NodeFilter.FILTER_SKIP;
        },
      } as any);
      let node: globalThis.Node | null = walker.nextNode();
      while (node) {
        if ((node as HTMLElement).getAttribute?.('data-pea-ref') === '1') {
          const id = (node as HTMLElement).getAttribute('data-node-id');
          const k = (node as HTMLElement).getAttribute('data-kind') as PeaNodeKind;
          if (id && isTextKind(k)) {
            const src = useCanvas.getState().nodes.find((n) => n.id === id);
            const t = src ? getTextSummary(src, 10000) : '';
            if (t) text += t;
          }
        } else {
          text += node.textContent || '';
        }
        node = walker.nextNode();
      }
      text = text.replace(/\u200B/g, ' ').replace(/\s+/g, ' ').trim();
      return { text, referenceImages, referencedNodeIds, html: editor.innerHTML };
    },
    /**
     * 生成「带参考图编号」的正文文本，供拼装最终 prompt 使用。
     * 遍历编辑器：媒体类 @ token 按其节点 id 映射为「参考图N」（N 由调用方按 reference_images
     * 数组顺序给定，保证与参考图说明块编号一致）；文本类 @ token 仍展开为节点文本；其余正文原样保留。
     * 这样模型拿到的用户指令里直接出现「参考图1/2/3」，与说明块一一对应，不会混淆。
     */
    getBodyText: (refNumberById?: Map<string, number>) => {
      const editor = editorRef.current;
      if (!editor) return '';
      let text = '';
      const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
        acceptNode: (n: globalThis.Node) => {
          if ((n as HTMLElement).getAttribute?.('data-pea-ref') === '1') return NodeFilter.FILTER_ACCEPT;
          if (n.nodeType === globalThis.Node.TEXT_NODE) return NodeFilter.FILTER_ACCEPT;
          return NodeFilter.FILTER_SKIP;
        },
      } as any);
      let node: globalThis.Node | null = walker.nextNode();
      while (node) {
        if ((node as HTMLElement).getAttribute?.('data-pea-ref') === '1') {
          const id = (node as HTMLElement).getAttribute('data-node-id');
          const k = (node as HTMLElement).getAttribute('data-kind') as PeaNodeKind;
          if (id && isMediaKind(k)) {
            const num = refNumberById?.get(id);
            if (num) text += `参考图${num}`;
          } else if (id && isTextKind(k)) {
            const src = useCanvas.getState().nodes.find((n) => n.id === id);
            const t = src ? getTextSummary(src, 10000) : '';
            if (t) text += t;
          }
        } else {
          text += node.textContent || '';
        }
        node = walker.nextNode();
      }
      text = text.replace(/\u200B/g, ' ').replace(/\s+/g, ' ').trim();
      return text;
    },
    setHtml: (h) => {
      const editor = editorRef.current;
      if (editor) {
        editor.innerHTML = h;
        stripLegacyRefBadges(editor);
        // 切换节点/粘贴后：把纯文本 fallback 转换回 token，并清理孤立 token。
        hydrateFallbackTokens(editor, kind, resolvedThumbs);
        pruneOrphanRefTokens(editor, kind);
        renumberRefChips(editor);
        // 还原/刷新后把光标放到内容末尾，而非浏览器默认的起始位置
        // （修复：刷新/打开节点后光标停在开头，用户继续输入会插到最前面）。
        placeCaretAtEnd(editor);
        // 强制同步状态并触发 onChange：父组件切换节点恢复内容时，必须让外部
        // 重新计算 canSend 等派生状态，否则发送按钮等会停留在旧状态。
        const nextHtml = editor.innerHTML;
        const nextText = editor.innerText || '';
        lastHtmlRef.current = nextHtml;
        setHtmlState(nextHtml);
        setPlainText(nextText);
        onChange?.(nextHtml, nextText);
      }
    },
  focus: (opts?: FocusOptions) => editorRef.current?.focus(opts),
    get plainText() {
      return editorRef.current?.innerText || '';
    },
  }), [resolvedThumbs, syncFromEditor]);

  const filteredUpstream = upstream.filter((u) => {
    const q = filter.toLowerCase();
    return u.label.toLowerCase().includes(q) || u.node.id.toLowerCase().includes(q);
  });

  const openPicker = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const vw = window.innerWidth;
    const pickerWidth = 240;
    const left = Math.min(Math.max(10, rect.left), vw - pickerWidth - 10);
    const top = rect.bottom + 8;
    setPickerPos({ left, top });
    setFilter('');
    setActiveIndex(0);
    setShowPicker(true);
  }, []);

  const insertRef = useCallback((item: UpstreamItem) => {
    const editor = editorRef.current;
    if (!editor) return;
    const display = isTextKind(item.kind) ? item.label : (resolvedThumbs[item.node.id] || item.label);
    const at = atTriggerRef.current;
    atTriggerRef.current = null;
    atTriggerActiveRef.current = false;
    if (at) {
      try {
        const sel = window.getSelection();
        const endNode = sel?.anchorNode ?? at.node;
        const endOffset = sel?.anchorOffset ?? at.offset + 1;
        const range = document.createRange();
        range.setStart(at.node, at.offset);
        range.setEnd(endNode, endOffset);
        sel?.removeAllRanges();
        sel?.addRange(range);
        range.deleteContents();
      } catch {
        /* 选区异常时退化为直接插入 */
      }
    }
    insertRefToken(editor, item.node.id, item.kind, display, item.node.data.fileKey);
    if (isMediaKind(item.kind)) {
      onInsertReference?.(item.node.id);
    }
    // 关键修复：插入后立即尝试刷新缩略图。
    // 如果 resolvedThumbs 已有 URL → 占位符立刻被替换为真实图片；
    // 如果 URL 还在异步解析中 → 本次无操作，后续 resolvedThumbs 更新时 effect 会补上。
    refreshTokenThumbnails(editor, resolvedThumbs);
    syncFromEditor();
    setShowPicker(false);
    setFilter('');
  }, [resolvedThumbs, syncFromEditor, onInsertReference]);

  /**
   * 检查光标是否位于或紧邻 pea-ref token。
   * 返回 true 如果光标在 token 内部、token 前、或 token 后的紧挨位置。
   * 注意：token 后面会插入一个零宽空格占位文本，浏览器可能把后续输入合并进该文本节点，
   * 因此不能仅因前一个兄弟是 token 就返回 true，必须要求 offset 处于文本节点边界。
   */
  const isCursorInsideOrAdjacentToToken = useCallback((range: Range) => {
    const { startContainer, startOffset } = range;

    // 如果光标直接在文本节点内
    if (startContainer.nodeType === Node.TEXT_NODE) {
      const textLen = startContainer.textContent?.length ?? 0;
      // 检查前一个节点是否为 pea-ref token：仅在文本节点开头才算紧贴 token 左边界
      const prev = startContainer.previousSibling;
      if (
        prev &&
        prev.nodeType === Node.ELEMENT_NODE &&
        (prev as HTMLElement).classList.contains('pea-ref') &&
        startOffset === 0
      ) {
        return true;
      }
      // 检查父元素的前一个节点（防止光标在 token 的子元素内）
      const parentEl = startContainer.parentElement;
      if (parentEl) {
        const parentPrev = parentEl.previousSibling;
        if (
          parentPrev &&
          parentPrev.nodeType === Node.ELEMENT_NODE &&
          (parentPrev as HTMLElement).classList.contains('pea-ref') &&
          startOffset === 0
        ) {
          return true;
        }
      }
      // 检查后一个节点是否为 pea-ref token：仅在文本节点末尾才算紧贴 token 右边界
      const next = startContainer.nextSibling;
      if (
        next &&
        next.nodeType === Node.ELEMENT_NODE &&
        (next as HTMLElement).classList.contains('pea-ref') &&
        startOffset === textLen
      ) {
        return true;
      }
      if (parentEl) {
        const parentNext = parentEl.nextSibling;
        if (
          parentNext &&
          parentNext.nodeType === Node.ELEMENT_NODE &&
          (parentNext as HTMLElement).classList.contains('pea-ref') &&
          startOffset === textLen
        ) {
          return true;
        }
      }
      return false;
    }

    // 如果光标直接在元素节点内（比如 token 的内部 span）
    if (startContainer.nodeType === Node.ELEMENT_NODE && (startContainer as HTMLElement).classList.contains('pea-ref')) {
      return true;
    }

    return false;
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (showPicker) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % Math.max(1, filteredUpstream.length));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + Math.max(1, filteredUpstream.length)) % Math.max(1, filteredUpstream.length));
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        const item = filteredUpstream[activeIndex];
        if (item) insertRef(item);
        return;
      }
      if (e.key === 'Escape') {
        atTriggerRef.current = null;
        atTriggerActiveRef.current = false;
        setShowPicker(false);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit?.();
      return;
    }
    if (e.key === 'Backspace') {
      const sel = window.getSelection();
      if (sel && sel.rangeCount > 0) {
        const range = sel.getRangeAt(0);
        if (range.collapsed) {
          // 情况 A: 清空 @ 触发器（光标精确停在触发位置时，只关 picker，不删字）
          const at = atTriggerRef.current;
          if (at && range.startContainer === at.node && range.startOffset === at.offset) {
            atTriggerRef.current = null;
            atTriggerActiveRef.current = false;
            setShowPicker(false);
            return;
          }

          // 仅当「光标紧贴 token 左侧边界」(文本容器内 offset===0 且前一个兄弟是 token)
          // 或「光标落在 token 内部」时，才拦截并删除该 token；
          // 其余情况一律交给浏览器默认行为删除普通文本字符——
          // 这样用户删除自己输入的字时，不会再误删 @ 引用的图片/文本。
          const start = range.startContainer;
          const prevEl = start.previousSibling as globalThis.Node | null;
          const parentEl = start.parentElement;
          const prevSibling = parentEl ? parentEl.previousSibling : null;
          const prev = prevEl || (prevSibling as globalThis.Node | null);

          const insideToken =
            start.nodeType === Node.ELEMENT_NODE &&
            (start as HTMLElement).getAttribute?.('data-pea-ref') === '1';

          const atTokenLeftBoundary =
            prev != null &&
            (prev as HTMLElement).getAttribute?.('data-pea-ref') === '1' &&
            // 文本容器：必须 offset===0(光标紧贴 token 左缘)才删；
            // 元素容器(如 caret 落在 token 后的编辑区)：不限制 offset。
            (start.nodeType !== Node.TEXT_NODE || range.startOffset === 0);

          if (insideToken || atTokenLeftBoundary) {
            e.preventDefault();
            const target = insideToken ? start : prev!;
            target.parentNode?.removeChild(target);
            syncFromEditor();
            atTriggerRef.current = null;
            atTriggerActiveRef.current = false;
            return;
          }
        }
      }
    }
  };

  const handleInput = () => {
    syncFromEditor();
    const editor = editorRef.current;
    if (!editor) return;
    renumberRefChips(editor);
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const range = sel.getRangeAt(0);
    const node = range.startContainer as globalThis.Node;
    const text = node.textContent || '';
    const offset = range.startOffset;
    const before = text.slice(0, offset);

    // 关键修复 1：如果光标在或紧邻 pea-ref token，立即清除 @ 触发状态并关闭 picker
    // 这确保用户在引用 token 附近编辑时，不会意外激活 @ 选择器
    const insideOrAdjacent = isCursorInsideOrAdjacentToToken(range);
    if (insideOrAdjacent) {
      atTriggerRef.current = null;
      atTriggerActiveRef.current = false;
      setShowPicker(false);
      return;
    }

    // 关键修复 2：只在光标真正紧挨着 '@' 字符时触发 picker（@ 后面紧接着光标）
    const atIdx = before.lastIndexOf('@');
    if (atIdx >= 0) {
      const query = before.slice(atIdx + 1);
      if (!query.includes(' ')) {
        const distance = offset - (atIdx + 1);
        // ONLY trigger when cursor is immediately after '@' (distance == 0 means cursor at @ char)
        if (distance === 0) {
          setFilter(query);
          atTriggerRef.current = { node, offset: atIdx };
          atTriggerActiveRef.current = true;
          const rect = range.getBoundingClientRect();
          const vw = window.innerWidth;
          const pickerWidth = 240;
          const left = Math.min(Math.max(10, rect.left), vw - pickerWidth - 10);
          const top = rect.bottom + 8;
          setPickerPos({ left, top });
          setActiveIndex(0);
          setShowPicker(true);
          return;
        }
      }
    }

    // 如果光标远离 '@' 符号，且没有活跃的 @ 触发，则关闭 picker
    if (showPicker && !atTriggerActiveRef.current) {
      atTriggerRef.current = null;
      atTriggerActiveRef.current = false;
      setShowPicker(false);
    }
  };

  /**
   * 复制处理：接管浏览器默认复制，主动以「富文本 HTML + 纯文本 fallback」双格式写入剪贴板。
   * - text/html：原始编辑器 innerHTML（含 data-pea-ref 结构），本应用内跨节点粘贴时
   *   能 100% 还原 @ token 结构，不依赖浏览器对 contentEditable 的序列化偏好。
   * - text/plain：把 @ token 序列化为 @image#id:filename（文本 token 展开为节点文本），
   *   即使粘贴到外部编辑器或另一节点失去 HTML，也能经 handlePaste 的 fallback 分支重新 hydrate。
   * 这是「复制提示词到另一节点显示不出来」问题的根因修复：之前依赖浏览器默认序列化，
   * 跨文档/跨应用复制时 data-* 结构经常丢失，导致 @ 引用塌缩为纯文本或彻底消失。
   */
  const handleCopy = (e: React.ClipboardEvent<HTMLDivElement>) => {
    const editor = editorRef.current;
    if (!editor) return;
    const html = editor.innerHTML;
    const plain = serializeEditorForCopy(editor);
    e.clipboardData.setData('text/html', html);
    e.clipboardData.setData('text/plain', plain);
    e.preventDefault();
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault();
    const editor = editorRef.current;
    if (!editor) return;

    // 优先尝试粘贴 HTML（保留 @ token 结构）。来自本应用内编辑框的复制通常带 text/html。
    const html = e.clipboardData.getData('text/html');
    if (html && /<[^>]+data-pea-ref/i.test(html)) {
      document.execCommand('insertHTML', false, html);
      stripLegacyRefBadges(editor);
      hydrateFallbackTokens(editor, kind, resolvedThumbs);
      pruneOrphanRefTokens(editor, kind);
      renumberRefChips(editor);
      // 关键：从另一节点复制出来的 <img src="blob:..."> 在目标节点上下文里可能不可达，
      // 用当前 resolvedThumbs 把缩略图重新指向正确地址，避免裂图/占位。
      refreshTokenThumbnails(editor, resolvedThumbs);
      syncFromEditor();
      return;
    }

    const text = e.clipboardData.getData('text/plain');
    if (!text) return;

    // 如果粘贴的纯文本包含 fallback 引用（如 @image#n1:filename），
    // 先按普通文本插入，再统一 hydrate 成 token。
    document.execCommand('insertText', false, text);
    if (REF_FALLBACK_RE.test(text)) {
      stripLegacyRefBadges(editor);
      if (hydrateFallbackTokens(editor, kind, resolvedThumbs)) {
        renumberRefChips(editor);
        refreshTokenThumbnails(editor, resolvedThumbs);
      }
    }
    syncFromEditor();
  };

  // ── 关键修复：点击后强制把光标定位到「点击坐标所在位置」──
  // 根因：浏览器默认的 click→caret 在以下场景失准——
  //  ① 编辑框含 image 引用 token（<span contenteditable=false>）时，某些浏览器
  //     （特别是含中文 IME 组合态的 WebKit/Blink）会把 caret 落到 token 邻近
  //     文本节点的 offset 0，表现为「点击中段，caret 永远在第一个字符前」。
  //  ② 父组件 NodeChatPrompt 频繁 re-render，DOM 同步/选择回填时序竞争，
  //     偶尔也会把 caret 推回 0 位置。
  // 方案：mouseup 后用 document.caretPositionFromPoint(x, y) 反算真实点击位置，
  //      与浏览器默认设置一致时 no-op，不同时显式 setSelection 覆盖。
  //      兼容旧版 Safari 用 document.caretRangeFromPoint。
  const placeCaretFromPoint = useCallback((clientX: number, clientY: number) => {
    const editor = editorRef.current;
    if (!editor) return;
    let targetNode: Node | null = null;
    let targetOffset = 0;
    // 直接以 document 为 this 调用（解构为独立 fn 会丢 this 触发 "Illegal invocation"）
    const docAny = document as any;
    if (typeof docAny.caretPositionFromPoint === 'function') {
      const p = docAny.caretPositionFromPoint(clientX, clientY);
      if (p && p.offsetNode && editor.contains(p.offsetNode)) {
        targetNode = p.offsetNode;
        targetOffset = p.offset;
      }
    } else if (typeof docAny.caretRangeFromPoint === 'function') {
      const r = docAny.caretRangeFromPoint(clientX, clientY);
      if (r && r.startContainer && editor.contains(r.startContainer)) {
        targetNode = r.startContainer;
        targetOffset = r.startOffset;
      }
    }
    if (!targetNode) return;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const cur = sel.getRangeAt(0);
    if (cur.startContainer === targetNode && cur.startOffset === targetOffset) return;
    // 越界保护：pea-ref 内部（contenteditable=false）不作为 caret 落点
    if ((targetNode as HTMLElement).getAttribute?.('data-pea-ref') === '1') {
      // 落到 token 内时：默认放 token 后
      const token = targetNode as HTMLElement;
      const parent = token.parentNode;
      if (parent) {
        const idx = Array.prototype.indexOf.call(parent.childNodes, token);
        targetNode = parent;
        targetOffset = idx + 1;
      }
    }
    const range = document.createRange();
    range.setStart(targetNode, targetOffset);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
  }, []);

  const handleMouseUp = (e: React.MouseEvent<HTMLDivElement>) => {
    // 仅在编辑器内点击才矫正
    if (e.target !== e.currentTarget && !(e.currentTarget as HTMLElement).contains(e.target as Node)) return;
    placeCaretFromPoint(e.clientX, e.clientY);
  };

  useEffect(() => {
    if (!showPicker) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (editorRef.current?.contains(t)) return;
      if (t.closest('.pea-ref-picker')) return;
      atTriggerRef.current = null;
      atTriggerActiveRef.current = false;
      setShowPicker(false);
    };
    window.addEventListener('mousedown', onDoc);
    return () => window.removeEventListener('mousedown', onDoc);
  }, [showPicker]);

  return (
    <div className="node-prompt-input-wrap">
      <div
        ref={editorRef}
        className="node-prompt-editor"
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        onCopy={handleCopy}
        onMouseDown={(e) => {
          e.stopPropagation();
        }}
        onMouseUp={handleMouseUp}
      />

      {showPicker && pickerPos && createPortal(
        <div
          className="pea-ref-picker"
          style={{ left: pickerPos.left, top: pickerPos.top, position: 'fixed', zIndex: 100 }}
          role="listbox"
          aria-label="引用上游节点"
        >
          <div className="pea-ref-picker-head">
            引用上游节点
          </div>
          {filteredUpstream.length === 0 && (
            <div className="pea-ref-picker-empty">暂无可用上游节点</div>
          )}
          {filteredUpstream.map((item, idx) => (
            <button
              key={item.node.id}
              type="button"
              className={`pea-ref-picker-item ${idx === activeIndex ? 'active' : ''}`}
              onClick={() => insertRef(item)}
              onMouseEnter={() => setActiveIndex(idx)}
              role="option"
              aria-selected={idx === activeIndex}
            >
              {isTextKind(item.kind) ? (
                <span className="pea-ref-picker-icon">📝</span>
              ) : item.kind === 'video' ? (
                <VideoPickerThumb url={resolvedThumbs[item.node.id]} label={item.label} />
              ) : resolvedThumbs[item.node.id] ? (
                <img
                  className="pea-ref-picker-thumb"
                  src={resolvedThumbs[item.node.id]}
                  alt=""
                  loading="lazy"
                />
              ) : (
                <span className="pea-ref-picker-icon pea-ref-picker-thumb-fallback">🖼️</span>
              )}
              <span className="pea-ref-picker-label">{item.label}</span>
              <span className="pea-ref-picker-kind">{item.kind}</span>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
});

/* ═════════════════════════════════════════════════════════════════════════════
 * 视频引用缩略图：hover 时在固定浮层内自动播放，替代之前的「问号」占位。
 * ═════════════════════════════════════════════════════════════════════════════ */
function VideoPickerThumb({ url, label }: { url?: string; label: string }) {
  const thumbRef = useRef<HTMLVideoElement>(null);
  const [showPopover, setShowPopover] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  const handleEnter = (e: React.MouseEvent) => {
    thumbRef.current?.play().catch(() => {});
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const width = 220;
    const height = 150;
    let left = rect.left + rect.width / 2 - width / 2;
    let top = rect.bottom + 10;
    if (left + width > vw - 12) left = vw - width - 12;
    if (left < 12) left = 12;
    if (top + height > vh - 12) top = rect.top - height - 10;
    setPos({ left, top });
    setShowPopover(true);
  };

  const handleLeave = () => {
    thumbRef.current?.pause();
    setShowPopover(false);
  };

  if (!url) {
    return <span className="pea-ref-picker-icon pea-ref-picker-thumb-fallback">🎬</span>;
  }

  return (
    <>
      <video
        ref={thumbRef}
        className="pea-ref-picker-thumb pea-ref-picker-video-thumb"
        src={url}
        muted
        loop
        playsInline
        preload="metadata"
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
      />
      {showPopover && pos && createPortal(
        <div
          className="pea-ref-video-popover"
          style={{ left: pos.left, top: pos.top, position: 'fixed', zIndex: 120 }}
          onMouseEnter={() => setShowPopover(true)}
          onMouseLeave={() => setShowPopover(false)}
        >
          <div className="pea-ref-video-popover-tag">
            <span>@Video</span>
            <span className="pea-ref-video-popover-label">{label}</span>
          </div>
          <video
            className="pea-ref-video-popover-player"
            src={url}
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
          />
          <div className="pea-ref-video-popover-toolbar">
            <button type="button" title="全屏" aria-label="全屏" onClick={() => {
              const el = document.querySelector('.pea-ref-video-popover-player') as HTMLVideoElement | null;
              el?.requestFullscreen?.().catch(() => {});
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
            </button>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
