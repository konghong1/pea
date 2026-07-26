import { useEffect, useRef, useState } from 'react';
import { useCanvas } from '../store/canvas';
import { promptRewriter } from '../lib/promptRewriter';
import type { PromptMediaType, StyleTemplate } from '../lib/promptRewriter';

/**
 * PromptRewritePanel — 文本节点提示词改写面板
 *
 * 功能：
 * 1. 在节点内部提供输入框，用户输入简短词语/描述
 * 2. 选择风格模板（写实、动漫、电影级等）
 * 3. 点击"改写"按钮，调用本地引擎生成高质量提示词
 * 4. 支持图片/视频两种媒体类型的提示词
 *
 * 完全独立于 Agent 聊天框，不调用同一接口
 */

const STYLE_OPTIONS: { value: StyleTemplate; label: string; icon: string }[] = [
  { value: 'auto', label: '智能匹配', icon: '✨' },
  { value: 'realistic', label: '写实摄影', icon: '📷' },
  { value: 'cinematic', label: '电影级', icon: '🎬' },
  { value: 'anime', label: '动漫', icon: '🎨' },
  { value: 'artistic', label: '艺术插画', icon: '🖼️' },
  { value: 'cyberpunk', label: '赛博朋克', icon: '🌃' },
  { value: 'fantasy', label: '奇幻', icon: '🐉' },
  { value: 'watercolor', label: '水彩', icon: '💧' },
  { value: 'minimal', label: '极简', icon: '⬜' },
  { value: '3d-render', label: '3D渲染', icon: '💎' },
];

const MEDIA_TYPE_OPTIONS: { value: PromptMediaType; label: string; icon: string }[] = [
  { value: 'image', label: '图片提示词', icon: '🖼️' },
  { value: 'video', label: '视频提示词', icon: '🎥' },
];

export default function PromptRewritePanel() {
  const selectedIds = useCanvas((s) => s.selectedIds);
  const nodes = useCanvas((s) => s.nodes);
  const updateNodeData = useCanvas((s) => s.updateNodeData);

  // 只处理选中的单个文本节点
  const nodeId = selectedIds.length === 1 ? selectedIds[0] : null;
  const node = nodeId ? nodes.find((n) => n.id === nodeId) : null;
  const isText = node?.data.kind === 'text';

  const [inputValue, setInputValue] = useState('');
  const [style, setStyle] = useState<StyleTemplate>('auto');
  const [mediaType, setMediaType] = useState<PromptMediaType>('image');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 当选中节点变化时，重置状态
  useEffect(() => {
    if (!isText) {
      setExpanded(false);
      setResult(null);
      return;
    }
    // 节点有原始 html 内容时，从中提取纯文本作为预填值
    if (node?.data.html) {
      const text = node.data.html.replace(/<[^>]*>/g, '').trim();
      if (text && text.length < 200) {
        setInputValue(text);
      }
    }
  }, [nodeId, isText, node?.data.html]);

  // 展开面板时自动聚焦输入框
  useEffect(() => {
    if (expanded && inputRef.current) {
      inputRef.current.focus();
    }
  }, [expanded]);

  /**
   * 执行改写
   */
  const handleRewrite = () => {
    if (!inputValue.trim()) return;

    setLoading(true);
    setResult(null);

    // 使用本地引擎改写（非 API 调用，毫秒级响应）
    setTimeout(() => {
      try {
        const rewriteResult = promptRewriter.rewrite(inputValue.trim(), {
          mediaType,
          style,
          autoEnhance: true,
        });

        setResult(rewriteResult.rewritten);
      } catch (err) {
        console.error('[PromptRewritePanel] 改写失败:', err);
        setResult('改写失败，请重试');
      } finally {
        setLoading(false);
      }
    }, 300); // 模拟微小延迟，给用户反馈感
  };

  /**
   * 应用结果到节点
   */
  const handleApply = () => {
    if (!result || !nodeId) return;

    updateNodeData(nodeId, {
      html: `<p>${result}</p>`,
    });

    setResult(null);
    setInputValue('');
    setExpanded(false);
  };

  /**
   * 复制结果到剪贴板
   */
  const handleCopy = async () => {
    if (!result) return;

    try {
      await navigator.clipboard.writeText(result);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 静默失败
    }
  };

  // 未选中文本节点 → 不渲染
  if (!isText) return null;

  return (
    <div className="prompt-rewrite-panel">
      {/* 展开/收起按钮 */}
      <button
        className="prompt-rewrite-toggle"
        onClick={() => setExpanded(!expanded)}
        title={expanded ? '收起改写面板' : '打开提示词改写'}
      >
        <span className="toggle-icon">{expanded ? '▲' : '▼'}</span>
        <span className="toggle-label">提示词改写</span>
      </button>

      {expanded && (
        <div className="prompt-rewrite-body">
          {/* 媒体类型切换 */}
          <div className="pr-media-type">
            {MEDIA_TYPE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`pr-type-btn ${mediaType === opt.value ? 'active' : ''}`}
                onClick={() => setMediaType(opt.value)}
              >
                <span className="type-icon">{opt.icon}</span>
                <span>{opt.label}</span>
              </button>
            ))}
          </div>

          {/* 风格选择 */}
          <div className="pr-style-section">
            <label className="pr-label">风格模板</label>
            <div className="pr-style-grid">
              {STYLE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={`pr-style-btn ${style === opt.value ? 'active' : ''}`}
                  onClick={() => setStyle(opt.value)}
                >
                  <span className="style-icon">{opt.icon}</span>
                  <span>{opt.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 输入框 */}
          <div className="pr-input-section">
            <label className="pr-label">你的输入</label>
            <textarea
              ref={inputRef}
              className="pr-input"
              placeholder="输入简单描述，如：女孩、赛博朋克城市、海边日落…"
              rows={3}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                // Ctrl/Cmd + Enter 快捷提交
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                  e.preventDefault();
                  handleRewrite();
                }
              }}
            />
            <div className="pr-input-hint">
              输入简短词语或描述，AI 会自动扩写为专业提示词。按 Ctrl+Enter 快速改写。
            </div>
          </div>

          {/* 改写按钮 */}
          <button
            className={`pr-rewrite-btn ${loading ? 'loading' : ''}`}
            onClick={handleRewrite}
            disabled={loading || !inputValue.trim()}
          >
            {loading ? (
              <>
                <span className="btn-spinner" />
                <span>改写中…</span>
              </>
            ) : (
              <>
                <span className="btn-icon">✨</span>
                <span>改写提示词</span>
              </>
            )}
          </button>

          {/* 改写结果 */}
          {result && (
            <div className="pr-result-section">
              <div className="pr-result-header">
                <label className="pr-label">改写结果</label>
                <div className="pr-result-actions">
                  <button
                    className={`pr-copy-btn ${copied ? 'copied' : ''}`}
                    onClick={handleCopy}
                    title="复制到剪贴板"
                  >
                    {copied ? '✓ 已复制' : '📋 复制'}
                  </button>
                  <button className="pr-apply-btn" onClick={handleApply} title="应用到节点">
                    ✓ 应用到节点
                  </button>
                </div>
              </div>
              <div className="pr-result-text">{result}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
