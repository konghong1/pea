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
  focus: () => void;
  get plainText(): string;
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

/** 从节点数据提取可作为参考图/文本引用的 URL 或内容。 */
async function resolveNodeMediaUrl(node: FlowNode<PeaNodeData>): Promise<string | undefined> {
  const d = node.data;
  const urls = d.resultUrls?.length ? d.resultUrls : d.resultUrl ? [d.resultUrl] : [];
  const firstUrl = urls[0] || d.url;
  // blob: URL 仅当前会话有效，刷新后失效；如果被持久化到 DB 重新加载后就是废链接。
  // 检测到 blob: 时跳过，继续尝试 fileKey → 签名 URL 路径。
  if (firstUrl && !firstUrl.startsWith('blob:')) return firstUrl;
  if (d.fileKey) {
    // 优先返回可外传的真实签名 URL（参考图需发给外部模型）；失败再退化为 blob 仅作显示。
    try {
      const pu = await getPresignedUrl(d.fileKey);
      if (pu) return pu;
    } catch (e) {
      console.warn('[resolveNodeMediaUrl] getPresignedUrl failed', { nodeId: node.id, fileKey: d.fileKey, error: e });
    }
    try {
      return await getFileUrl(d.fileKey);
    } catch (e) {
      console.warn('[resolveNodeMediaUrl] getFileUrl also failed', { nodeId: node.id, fileKey: d.fileKey, error: e });
      return undefined;
    }
  }
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
    const imgUrl = typeof label === 'string' && (label.startsWith('http') || label.startsWith('data:') || label.startsWith('blob:')) ? label : '';
    inner.appendChild(imgUrl ? createImageRefThumb(imgUrl, fileKey) : createImageRefPlaceholder());
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
  editor.focus();
}

export default forwardRef<NodePromptInputRef, NodePromptInputProps>(function NodePromptInput(
  { nodeId, kind, placeholder = '描述你想生成的内容，或输入 @ 引用上游节点', initialHtml = '', onChange, onSubmit, onInsertReference },
  ref,
) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState(initialHtml);
  const [plainText, setPlainText] = useState('');
  const [showPicker, setShowPicker] = useState(false);
  const [pickerPos, setPickerPos] = useState<{ left: number; top: number } | null>(null);
  const [filter, setFilter] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [upstream, setUpstream] = useState<UpstreamItem[]>([]);
  const [resolvedThumbs, setResolvedThumbs] = useState<Record<string, string>>({});
  const lastHtmlRef = useRef(initialHtml);
  const atTriggerRef = useRef<{ node: globalThis.Node; offset: number } | null>(null);
  const atTriggerActiveRef = useRef(false);

  const getUpstream = useCallback((): UpstreamItem[] => {
    const inputs = useCanvas.getState().getUpstreamInputs(nodeId);
    return inputs
      .filter((n) => canReference(n.data.kind))
      .map((n) => ({
        node: n,
        kind: n.data.kind,
        label: isTextKind(n.data.kind) ? getTextSummary(n) : getFileName(n),
      }));
  }, [nodeId]);

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
        .filter((n) => canReference(n.data.kind))
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
  }, [nodeId]);

  useEffect(() => {
    let alive = true;
    (async () => {
      const thumbs: Record<string, string> = {};
      for (const item of upstream) {
        if (isMediaKind(item.kind)) {
          const url = await resolveNodeMediaUrl(item.node);
          if (url && alive) thumbs[item.node.id] = url;
        }
      }
      if (alive) setResolvedThumbs(thumbs);
    })();
    return () => { alive = false; };
  }, [upstream]);

  // 引用 token 缩略图同步：当 resolvedThumbs 重新解析（如刷新后、上传图签名 URL 过期）时，
  // 把编辑器中已存在的 @ token 的缩略图指向最新 URL；若当前是占位图标则替换为真实 <img>。
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.querySelectorAll<HTMLElement>('[data-pea-ref="1"]').forEach((span) => {
      const id = span.getAttribute('data-node-id');
      const kind = span.getAttribute('data-kind') as PeaNodeKind;
      if (!id || !isMediaKind(kind)) return;
      const url = resolvedThumbs[id];
      if (!url) return;

      // 情况 1：当前是占位图标 -> 直接替换为真实图片
      const placeholder = span.querySelector('span.pea-ref-thumb-fallback-inline');
      if (placeholder) {
        const fileKey = span.getAttribute('data-file-key');
        placeholder.replaceWith(createImageRefThumb(url, fileKey));
        return;
      }

      // 情况 2：当前已有 <img> -> 仅当 URL 真正变化时才更新 src
      const img = span.querySelector('img.pea-ref-thumb');
      if (!img) return;
      if (img.getAttribute('src') !== url) {
        img.setAttribute('src', url);
        img.removeAttribute('data-pea-pending');
      }
    });
  }, [resolvedThumbs]);

  const syncFromEditor = useCallback(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const nextHtml = editor.innerHTML;
    const nextText = editor.innerText || '';
    if (nextHtml !== lastHtmlRef.current) {
      lastHtmlRef.current = nextHtml;
      setHtml(nextHtml);
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
      syncFromEditor();
    }
  }, [initialHtml, syncFromEditor]);

  useImperativeHandle(ref, () => ({
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
          if (url && !referenceImages.includes(url)) referenceImages.push(url);
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
    setHtml: (h) => {
      const editor = editorRef.current;
      if (editor) {
        editor.innerHTML = h;
        syncFromEditor();
      }
    },
    focus: () => editorRef.current?.focus(),
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
      } catch {
        /* 选区异常时退化为直接插入 */
      }
    }
    insertRefToken(editor, item.node.id, item.kind, display, item.node.data.fileKey);
    if (isMediaKind(item.kind)) {
      onInsertReference?.(item.node.id);
    }
    syncFromEditor();
    setShowPicker(false);
    setFilter('');
  }, [resolvedThumbs, syncFromEditor, onInsertReference]);

  /**
   * 检查光标是否位于或紧邻 pea-ref token。
   * 返回 true 如果光标在 token 内部、token 前、或 token 后的紧挨位置。
   */
  const isCursorInsideOrAdjacentToToken = useCallback((range: Range) => {
    const { startContainer, startOffset } = range;

    // 如果光标直接在文本节点内
    if (startContainer.nodeType === Node.TEXT_NODE) {
      // 检查前一个节点是否为 pea-ref token
      const prev = startContainer.previousSibling;
      if (prev && prev.nodeType === Node.ELEMENT_NODE && (prev as HTMLElement).classList.contains('pea-ref')) {
        return true;
      }
      // 检查父元素的前一个节点（防止光标在 token 的子元素内）
      const parentEl = startContainer.parentElement;
      if (parentEl) {
        const parentPrev = parentEl.previousSibling;
        if (parentPrev && parentPrev.nodeType === Node.ELEMENT_NODE && (parentPrev as HTMLElement).classList.contains('pea-ref')) {
          return true;
        }
      }
      // 检查后一个节点是否为 pea-ref token（光标在 token 后面）
      const next = startContainer.nextSibling;
      if (next && next.nodeType === Node.ELEMENT_NODE && (next as HTMLElement).classList.contains('pea-ref')) {
        return true;
      }
      if (parentEl) {
        const parentNext = parentEl.nextSibling;
        if (parentNext && parentNext.nodeType === Node.ELEMENT_NODE && (parentNext as HTMLElement).classList.contains('pea-ref')) {
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

  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault();
    const text = e.clipboardData.getData('text/plain');
    document.execCommand('insertText', false, text);
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
        onMouseDown={(e) => {
          e.stopPropagation();
        }}
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
