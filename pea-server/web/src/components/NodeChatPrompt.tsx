import { useEffect, useRef, useState } from 'react';
import { useViewport } from 'reactflow';
import { useCanvas } from '../store/canvas';
import { useAgent } from '../store/agent';
import { toast } from '../store/toast';
import { listAvailableModels, estimateCost, acceptGenerationJob } from '../api/catalog';
import type { AvailableModel, PricingRule } from '../api/catalog';

interface KindCfg {
  label: string;
  placeholder: string;
  modelIcon: string;
}

/**
 * 节点下方全宽输入栏（对齐截图3/4/5/6）。
 * 选中单个节点时在节点正下方浮现与节点同宽的输入栏。
 *
 * 定位策略（关键修复 2026-07-24）：
 *  - 不再用 document.querySelector 实时查询节点 DOM（React 重渲期间会返回 null → 输入栏闪退）。
 *  - 改为基于节点 DOM getBoundingClientRect + rAF 循环，确定性计算 fixed 视口坐标。
 *
 * 生成接入（2026-07-25）：
 *  - 按节点 kind 动态加载 /models/available，模型名/参数均动态，不再硬编码。
 *  - 参数 UI 由所选模型的 pricing.tiers 驱动（每个维度一个下拉），实时调用 /models/estimate 预估 Tapies。
 *  - 提交真实 POST /generation/jobs（带 model + params + 幂等键）；通过 WS
 *    job.updated 事件 + canvas.jobNodeMap 把 resultUrl 异步回填到触发节点。
 */
const KIND_CFG: Record<string, KindCfg> = {
  text: { label: '文本', placeholder: '描述任何你想要生成的内容', modelIcon: '✦' },
  image: { label: '图片', placeholder: '描述任何你想要生成的内容', modelIcon: '📊' },
  video: { label: '视频', placeholder: '描述你想生成的内容，或输入 /@ 唤出素材库与快捷操作', modelIcon: '📊' },
  audio: { label: '音频', placeholder: '描述你想要生成的任何内容', modelIcon: '🌊' },
  generate: { label: '生成', placeholder: '描述你想生成的内容', modelIcon: '✦' },
};

/** 节点 kind → 生成类型（后端仅支持 image/video/text；audio 暂未接入生成）。 */
const GEN_TYPE: Record<string, 'image' | 'video' | 'text' | null> = {
  text: 'text',
  image: 'image',
  video: 'video',
  generate: 'image',
  audio: null,
};

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

  // ── 生成态（模型/参数/预估）──
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [modelId, setModelId] = useState('');
  const [tierVals, setTierVals] = useState<Record<string, string>>({});
  const [count, setCount] = useState(1);
  const [est, setEst] = useState<{ cost: number; allowed: boolean; minPlanLevel: number } | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);

  const kind = sel?.data.kind ?? 'text';
  const genType = GEN_TYPE[kind] ?? null;
  const selectedModel = models.find((m) => m.id === modelId) ?? null;
  const tiers = (selectedModel?.pricing as PricingRule | null)?.tiers ?? {};
  const dimKeys = Object.keys(tiers);
  const multiplier = (selectedModel?.pricing as PricingRule | null)?.multiplier ?? null;
  const params: Record<string, unknown> = { ...tierVals };
  if (multiplier) params[multiplier] = count;

  // ── WS 监听：job.updated → 通过 jobNodeMap 回填结果（仅挂载一次）──
  useEffect(() => {
    const onEvent = (e: Event) => {
      const ev = (e as CustomEvent).detail;
      if (!ev || ev.kind !== 'job.updated') return;
      const nodeId = useCanvas.getState().jobNodeMap[ev.jobId];
      if (!nodeId) return;
      if (ev.status === 'done') {
        useCanvas.getState().applyJobResult(ev.jobId, {
          generating: false,
          resultUrl: ev.resultUrl ?? undefined,
        });
        useCanvas.getState().removeJob(ev.jobId);
        toast.success('生成完成');
      } else if (ev.status === 'failed' || ev.status === 'refunded') {
        useCanvas.getState().applyJobResult(ev.jobId, { generating: false });
        useCanvas.getState().removeJob(ev.jobId);
        toast.error(ev.error || '生成失败，已退款');
      }
    };
    window.addEventListener('pea:event', onEvent);
    return () => window.removeEventListener('pea:event', onEvent);
  }, []);

  // ── 节点切换：恢复该节点的草稿（优先）/已保存 prompt，否则清空 ──
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

  // ── 加载可用模型 + 依据节点已存 meta 还原模型/参数选择 ──
  useEffect(() => {
    if (!single || !genType) {
      setModels([]);
      setModelId('');
      setPickerOpen(false);
      return;
    }
    let cancelled = false;
    setModels([]);
    setModelId('');
    listAvailableModels(genType)
      .then((list) => {
        if (cancelled) return;
        setModels(list);
        const node = useCanvas.getState().nodes.find((n) => n.id === single);
        const meta = ((node?.data.meta ?? {}) as Record<string, unknown>) || {};
        const pick =
          list.find((m) => m.id === meta.modelId) ??
          list.find((m) => m.isDefault) ??
          list[0];
        setModelId(pick?.id ?? '');
        // 初始化参数：默认取各 tier 维度第一项；若节点已存 genParams 则还原
        const t = (pick?.pricing as PricingRule | null)?.tiers ?? {};
        const init: Record<string, string> = {};
        Object.keys(t).forEach((d) => {
          init[d] = String(Object.keys(t[d] ?? {})[0] ?? '');
        });
        const gp = (meta.genParams ?? {}) as Record<string, unknown>;
        Object.keys(t).forEach((d) => {
          if (gp[d] !== undefined) init[d] = String(gp[d]);
        });
        setTierVals(init);
        const mult = (pick?.pricing as PricingRule | null)?.multiplier ?? null;
        setCount(mult && gp[mult] != null ? Number(gp[mult]) || 1 : 1);
      })
      .catch(() => {
        if (!cancelled) {
          setModels([]);
          setModelId('');
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [genType, single]);

  // ── 实时预估 Tapies（按当前模型 + 参数）──
  useEffect(() => {
    if (!modelId) {
      setEst(null);
      return;
    }
    let cancelled = false;
    const key = JSON.stringify(params);
    const t = setTimeout(() => {
      estimateCost(modelId, params)
        .then((r) => {
          if (!cancelled) setEst({ cost: r.cost, allowed: r.allowed, minPlanLevel: r.minPlanLevel });
        })
        .catch(() => {
          if (!cancelled) setEst(null);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, JSON.stringify(params)]);

  // ── 关闭模型选择浮层（点击外部 / Esc）──
  useEffect(() => {
    if (!pickerOpen) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (pickerRef.current?.contains(t) || chipRef.current?.contains(t)) return;
      setPickerOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPickerOpen(false);
    };
    window.addEventListener('mousedown', onDoc);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDoc);
      window.removeEventListener('keydown', onKey);
    };
  }, [pickerOpen]);

  // ── 确定性定位：基于节点真实 DOM 底边 + rAF 循环跟随 ──
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
        const centerX = r.left + r.width / 2;
        const width = Math.max(360, Math.round(r.width));
        return { left: Math.round(centerX - width / 2), top: Math.round(r.bottom + 16), width };
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

    const initial = compute();
    if (initial) setRect(initial);
    rafRef.current = requestAnimationFrame(loop);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [sel, single, viewport.x, viewport.y, viewport.zoom, sel?.position.x, sel?.position.y, sel?.width, sel?.height]);

  if (!sel || !rect || !single) return null;
  const cfg = KIND_CFG[kind] ?? KIND_CFG.text;

  const onModelChange = (v: string) => {
    setModelId(v);
    const m = models.find((x) => x.id === v);
    const t = (m?.pricing as PricingRule | null)?.tiers ?? {};
    const init: Record<string, string> = {};
    Object.keys(t).forEach((d) => {
      init[d] = String(Object.keys(t[d] ?? {})[0] ?? '');
    });
    setTierVals(init);
    setCount(1);
  };
  const onTierChange = (dim: string, v: string) =>
    setTierVals((s) => ({ ...s, [dim]: v }));
  const onCountChange = (v: number) =>
    setCount(Number.isFinite(v) && v >= 1 ? Math.min(8, Math.floor(v)) : 1);

  const submit = async () => {
    const t = text.trim();
    if (!t || submitting) return;
    if (!genType) {
      toast.info('音频生成即将开放，敬请期待');
      return;
    }
    if (!modelId || !selectedModel) {
      toast.error('暂无可用模型，请联系管理员配置');
      return;
    }
    if (est && !est.allowed) {
      toast.error(`该模型需要更高套餐（权益等级 ≥ ${est.minPlanLevel}）`);
      return;
    }
    // 写入节点 prompt，并记忆所选模型/参数（随画布保存）
    update(single, {
      prompt: t,
      meta: { ...(sel.data.meta ?? {}), modelId, genParams: params },
    });
    push('user', `[${sel.data.label || cfg.label}] ${t}`);
    setSubmitting(true);
    try {
      const res = await acceptGenerationJob({
        type: genType,
        prompt: t,
        model: modelId,
        params,
        priority: 'normal',
        idempotencyKey: `gen-${single}-${Date.now()}`,
      });
      useCanvas.getState().registerJob(res.jobId, single);
      update(single, { generating: true });
      toast.success('已受理，生成中…');
      draftRef.current[single] = '';
      setText('');
      // 提交后保持输入栏打开，方便连续输入
      setTimeout(() => inputRef.current?.focus(), 0);
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '受理失败，请重试');
    } finally {
      setSubmitting(false);
    }
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

  const costLabel =
    est == null ? '…' : est.allowed ? String(est.cost) : `需 Lv.${est.minPlanLevel}`;

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
          {genType ? (
            <button
              ref={chipRef}
              type="button"
              className="node-input-model"
              title={selectedModel?.displayName ?? '选择模型'}
              aria-label="选择模型"
              aria-haspopup="dialog"
              aria-expanded={pickerOpen}
              onClick={() => setPickerOpen((v) => !v)}
            >
              <span className="node-input-model-icon" aria-hidden>
                {cfg.modelIcon}
              </span>
              <span>{selectedModel?.displayName ?? (models.length ? '选择模型' : '无可用模型')}</span>
            </button>
          ) : (
            <span className="node-input-model" title="音频生成即将开放">
              <span className="node-input-model-icon" aria-hidden>
                {cfg.modelIcon}
              </span>
              <span>音频生成即将开放</span>
            </span>
          )}
          {dimKeys.map((d) => (
            <span key={d} className="node-input-param" title={d}>
              <span className="node-input-param-icon" aria-hidden>
                ⚙
              </span>
              <span>{tierVals[d] ?? '—'}</span>
            </span>
          ))}
          {multiplier && (
            <span className="node-input-param" title={multiplier}>
              <span className="node-input-param-icon" aria-hidden>
                ×
              </span>
              <span>{count}</span>
            </span>
          )}
        </div>
        <div className="node-input-status-right">
          <button type="button" className="node-input-icon-btn" title="语音输入" aria-label="语音">
            🎤
          </button>
          {kind !== 'audio' && (
            <span className="node-input-icon-btn" title="1× 倍速">
              1×
            </span>
          )}
          <span className="node-input-tapies" title="本次预计消耗 Tapies">
            <span className="node-input-tapies-icon" aria-hidden>
              💎
            </span>
            <span>{costLabel}</span>
          </span>
          <button
            type="button"
            className="node-input-send node-chat-prompt-send"
            title="发送 (Enter)"
            aria-label="发送"
            disabled={!text.trim() || submitting || (!!genType && !modelId)}
            onMouseDown={(e) => e.preventDefault()}
            onClick={submit}
          >
            ↑
          </button>
        </div>
      </div>

      {pickerOpen && genType && (
        <div
          ref={pickerRef}
          className="node-model-picker"
          style={{
            position: 'fixed',
            left: rect.left,
            top: rect.top - 8,
            width: rect.width,
            transform: 'translateY(-100%)',
          }}
          role="dialog"
          aria-label="模型与参数"
        >
          <div className="node-model-picker-title">生成设置</div>
          <label className="node-model-picker-label">模型</label>
          <select
            className="node-model-picker-select"
            value={modelId}
            onChange={(e) => onModelChange(e.target.value)}
          >
            {models.length === 0 && <option value="">（无可用模型）</option>}
            {models.map((m) => (
              <option key={m.id} value={m.id} disabled={!m.allowed}>
                {m.displayName}
                {m.allowed ? '' : ' · 需 Lv.' + m.minPlanLevel}
                {m.isDefault ? ' · 默认' : ''}
              </option>
            ))}
          </select>

          {dimKeys.map((d) => (
            <div key={d} className="node-model-picker-row">
              <label className="node-model-picker-label">{d}</label>
              <select
                className="node-model-picker-select"
                value={tierVals[d] ?? ''}
                onChange={(e) => onTierChange(d, e.target.value)}
              >
                {Object.keys(tiers[d] ?? {}).map((k) => (
                  <option key={k} value={k}>
                    {k}
                    {(tiers[d] as Record<string, number>)[k] ? `（+${tiers[d][k]}）` : ''}
                  </option>
                ))}
              </select>
            </div>
          ))}

          {multiplier && (
            <div className="node-model-picker-row">
              <label className="node-model-picker-label">{multiplier}</label>
              <input
                className="node-model-picker-select"
                type="number"
                min={1}
                max={8}
                value={count}
                onChange={(e) => onCountChange(Number(e.target.value))}
              />
            </div>
          )}

          <div className="node-model-picker-est">
            预计消耗 <b>💎 {est ? est.cost : '…'}</b> Tapies
            {est && !est.allowed && (
              <span className="node-model-picker-warn"> · 需套餐等级 ≥ {est.minPlanLevel}</span>
            )}
          </div>
          <button
            type="button"
            className="node-model-picker-close"
            onClick={() => setPickerOpen(false)}
          >
            完成
          </button>
        </div>
      )}
    </div>
  );
}
