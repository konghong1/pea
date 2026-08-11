import { useEffect, useRef, useState } from 'react';
import { estimateCost, listAvailableModels } from '../api/catalog';
import type { AvailableModel } from '../api/catalog';
import { useCanvas } from '../store/canvas';
import { toast } from '../store/toast';

export interface AngleCubeParams {
  rotation: number;
  tilt: number;
  zoom: number;
  wideAngle: boolean;
  modelId: string;
}

interface Props {
  nodeId: string;
  url: string;
  onClose: () => void;
  onConfirm: (params: AngleCubeParams) => void;
}

/**
 * 角度魔方面板 — 内嵌模式（渲染到节点编辑锚点内，替代 NodeChatPrompt 输入框）。
 *
 * 关键行为：
 * - 不再使用 createPortal→body，而是作为普通子组件渲染到 .pea-node-editor-anchor 内；
 * - 只有点击右上角 × 按钮才关闭（不响应点击外部关闭）；
 * - Escape 键仍可关闭。
 */
export default function AngleCubeOverlay({ nodeId, url, onClose, onConfirm }: Props) {
  const node = useCanvas((s) => s.nodes.find((n) => n.id === nodeId));
  const metaModelId = (node?.data.meta?.modelId as string) || '';

  const [rotation, setRotation] = useState(-30);
  const [tilt, setTilt] = useState(23);
  const [zoom, setZoom] = useState(0);
  const [wideAngle, setWideAngle] = useState(false);

  const [model, setModel] = useState<AvailableModel | null>(null);
  const [est, setEst] = useState<{ cost: number; allowed: boolean; minPlanLevel: number } | null>(null);
  const [loading, setLoading] = useState(false);

  const panelRef = useRef<HTMLDivElement>(null);

  // 仅 Escape 关闭，不监听外部点击（用户必须点 × 才退出角度魔方模式）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  // 加载可用模型 + 估算消耗
  useEffect(() => {
    let cancelled = false;
    listAvailableModels('image')
      .then((list) => {
        if (cancelled) return;
        const pick =
          list.find((m) => m.id === metaModelId) ||
          list.find((m) => m.isDefault) ||
          list[0] ||
          null;
        setModel(pick);
        if (pick) {
          estimateCost(pick.id, { n: 1 })
            .then((r) => {
              if (cancelled) setEst({ cost: r.cost, allowed: r.allowed, minPlanLevel: r.minPlanLevel });
            })
            .catch(() => {
              if (cancelled) setEst(null);
            });
        }
      })
      .catch(() => {
        if (cancelled) setModel(null);
      });
    return () => {
      cancelled = true;
    };
  }, [metaModelId]);

  const reset = () => {
    setRotation(-30);
    setTilt(23);
    setZoom(0);
    setWideAngle(false);
  };

  const canSend = Boolean(model && est?.allowed);

  const handleSend = () => {
    if (!model || !est?.allowed) return;
    setLoading(true);
    onConfirm({ rotation, tilt, zoom, wideAngle, modelId: model.id });
  };

  if (typeof document === 'undefined') return null;

  return (
    <div
      ref={panelRef}
      className="pea-angle-cube-panel"
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      onWheel={(e) => e.stopPropagation()}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
    >
      <div className="pea-angle-cube-header">
        <span className="pea-angle-cube-title">拖拽方块调整角度</span>
        <button
          type="button"
          className="pea-angle-cube-close"
          onClick={onClose}
          aria-label="关闭"
          title="关闭"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M18 6L6 18" />
            <path d="M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="pea-angle-cube-body">
        <div className="pea-angle-cube-preview">
          <div
            className="pea-angle-cube-preview-stage"
            style={{ perspective: '800px' }}
          >
            {(() => {
              /* 等比缩放基础尺寸（不用 CSS scale，避免 translateZ 被同比例放大导致透视变形）
               * 对标参考图：
               *   zoom=0  → 图2 小立方体，约 72px（占 220px 框的 ~33%）
               *   zoom=10 → 图1 大立方体，投影~200px（占框 ~91%，接近填满但不溢出）
               * 立方体固定旋转态(rotation=-30/tilt=23)，旋转后投影≈正方面的1.37倍 */
              const baseSize = 66;
              const maxSize = 112; // zoom=10 正方面112px × 1.37 ≈ 153px 投影（占220px预览框约70%，对标参考图）
              const cubeSize = Math.round(baseSize + (maxSize - baseSize) * (zoom / 10));
              const halfZ = Math.round(cubeSize / 2);
              return (
              <div
                className="pea-angle-cube-preview-cube"
                style={{
                  transform: `rotateX(${tilt}deg) rotateY(${-rotation}deg)`,
                  '--cube-size': `${cubeSize}px`,
                  '--cube-half-z': `${halfZ}px`,
                } as React.CSSProperties}
              >
              {/* 正面 — 贴图 */}
              <div className="pea-cube-face pea-cube-front">
                <img src={url} alt="角度预览" draggable={false} />
              </div>
              {/* 背面 */}
              <div className="pea-cube-face pea-cube-back" />
              {/* 右侧 */}
              <div className="pea-cube-face pea-cube-right" />
              {/* 左侧 */}
              <div className="pea-cube-face pea-cube-left" />
              {/* 顶面 */}
              <div className="pea-cube-face pea-cube-top" />
              {/* 底面 */}
              <div className="pea-cube-face pea-cube-bottom" />
            </div>
              );
            })()}
          </div>
        </div>

        <div className="pea-angle-cube-controls">
          <SliderRow
            label="旋转"
            value={rotation}
            min={-90}
            max={90}
            step={1}
            suffix="°"
            onChange={setRotation}
          />
          <SliderRow
            label="倾斜"
            value={tilt}
            min={-45}
            max={45}
            step={1}
            suffix="°"
            onChange={setTilt}
          />
          <SliderRow
            label="缩放"
            value={zoom}
            min={0}
            max={10}
            step={1}
            suffix=""
            onChange={setZoom}
          />
          <div className="pea-angle-cube-row">
            <span className="pea-angle-cube-label">广角镜头</span>
            <span />
            <button
              type="button"
              role="switch"
              aria-checked={wideAngle}
              className={`pea-angle-cube-toggle ${wideAngle ? 'on' : ''}`}
              onClick={() => setWideAngle((v) => !v)}
            >
              <span className="pea-angle-cube-toggle-knob" />
            </button>
          </div>
        </div>
      </div>

      <div className="pea-angle-cube-footer">
        {/* 重置 */}
        <button type="button" className="pea-angle-cube-reset-foot" onClick={reset} title="重置角度">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
            <path d="M3 3v5h5" />
          </svg>
          重置
        </button>

        {/* 参数胶囊：齿轮图标 + 消耗数字 + 圆形发送按钮（合并消除间距） */}
        <div className="pea-angle-cube-send-pill">
          <span className="pea-angle-cube-cost" title="固定消耗当前模型 1 张图">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.6">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            {est ? Math.round(est.cost) : '—'}
          </span>
          <button
            type="button"
            className="pea-angle-cube-send"
            onClick={handleSend}
            disabled={!canSend || loading}
            aria-label="发送生成"
            title={est?.allowed ? '发送生成' : '当前模型不可用'}
          >
            {loading ? (
              <span className="pea-angle-cube-send-spinner" />
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 19V5" />
                <path d="M5 12l7-7 7 7" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix: string;
  onChange: (v: number) => void;
}) {
  const fmt = `${value > 0 && suffix ? '+' : ''}${value}${suffix}`;
  // 当前值在 range 中的位置百分比（0~100）
  const progress = ((value - min) / (max - min)) * 100;
  // 以中心点(0值=50%)为原点，向当前值方向填充：
  //   正值：中心(50%) → 进度位置（向右亮）
  //   负值：进度位置 → 中心(50%)（向左亮）
  //   零值：from==to 无填充
  const fromPct = value >= 0 ? 50 : progress;
  const toPct = value >= 0 ? progress : 50;
  return (
    <div className="pea-angle-cube-row">
      <span className="pea-angle-cube-label">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="pea-angle-cube-slider"
        style={{ '--from': `${fromPct}%`, '--to': `${toPct}%` } as React.CSSProperties}
        onPointerDown={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      />
      <span className="pea-angle-cube-value">{fmt}</span>
    </div>
  );
}
