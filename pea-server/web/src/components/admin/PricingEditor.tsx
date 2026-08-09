import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  AutoComplete,
  Button,
  Collapse,
  Divider,
  Empty,
  InputNumber,
  Segmented,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
  theme,
} from 'antd';
import {
  DeleteOutlined,
  PlusOutlined,
  ThunderboltOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import type { PricingRule } from '../../api/catalog';
import { adminPreviewCost, type CostPreview } from '../../api/admin';
import {
  DIM_LABELS,
  MAX_DIMS,
  MAX_TIERS_PER_DIM,
  defaultPreviewParams,
  isSafeDimName,
  nextUid,
  toWire,
  validateForm,
  type DimRow,
  type PricingFormValue,
} from './pricingForm';

const { Text } = Typography;

/** 参数名输入的候选项 —— 打字即提示, 免去背参数名。 */
const DIM_SUGGESTIONS = Object.keys(DIM_LABELS).filter((k) => k !== 'n');

/**
 * 模型定价可视化编辑器。
 *
 * 取代原先"手写 pricing_json 文本域"的方案: 运营/产品同学用输入框就能配价,
 * 且同一份配置同时产出 params_schema (用户能选什么) 与 pricing.tiers (每个选项多少钱),
 * 两者不可能再对不上。
 *
 * 价格永远由服务端算 —— 右侧试算面板走 /admin/models/preview-cost, 与真实扣费同一段引擎,
 * 前端一行价格计算逻辑都没有, 从设计上杜绝"预览价 ≠ 实扣价"。
 */
export default function PricingEditor({
  value,
  onChange,
}: {
  value: PricingFormValue;
  onChange: (v: PricingFormValue) => void;
}) {
  const { token } = theme.useToken();
  const [picks, setPicks] = useState<Record<string, string>>(() => defaultPreviewParams(value));
  const [preview, setPreview] = useState<CostPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const wire = useMemo(() => toWire(value), [value]);
  const errors = useMemo(() => validateForm(value), [value]);

  const patch = useCallback(
    (partial: Partial<PricingFormValue>) => onChange({ ...value, ...partial }),
    [value, onChange],
  );

  const patchDim = useCallback(
    (uid: string, partial: Partial<DimRow>) =>
      patch({ dims: value.dims.map((d) => (d.uid === uid ? { ...d, ...partial } : d)) }),
    [patch, value.dims],
  );

  /* ── 试算: 防抖 260ms, 避免每次敲键盘都打一次后端 ────────────────── */
  const seqRef = useRef(0);
  useEffect(() => {
    if (errors.length) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    const seq = ++seqRef.current;
    const timer = window.setTimeout(() => {
      setPreviewing(true);
      adminPreviewCost(wire.pricing, picks)
        .then((r) => {
          if (seq !== seqRef.current) return; // 丢弃过期响应, 防止乱序覆盖
          setPreview(r);
          setPreviewError(null);
        })
        .catch((e: any) => {
          if (seq !== seqRef.current) return;
          setPreview(null);
          setPreviewError(e?.response?.data?.message ?? '试算失败');
        })
        .finally(() => {
          if (seq === seqRef.current) setPreviewing(false);
        });
    }, 260);
    return () => window.clearTimeout(timer);
  }, [wire, picks, errors.length]);

  /* 维度/档位增删后, 让试算选项跟着回到有效值, 否则会一直算着一个已删掉的档。 */
  useEffect(() => {
    setPicks((prev) => {
      const next: Record<string, string> = {};
      let changed = false;
      for (const dim of value.dims) {
        const key = dim.key.trim();
        if (!isSafeDimName(key) || !dim.tiers.length) continue;
        const options = dim.tiers.map((t) => String(t.value ?? '').trim()).filter(Boolean);
        if (!options.length) continue;
        const cur = prev[key];
        next[key] = cur && options.includes(cur) ? cur : options[0];
        if (next[key] !== cur) changed = true;
      }
      if (value.multiplierEnabled) {
        const mKey = value.multiplierKey.trim();
        const opts = value.multiplierOptions.map((v) => String(v ?? '').trim()).filter(Boolean);
        if (isSafeDimName(mKey) && opts.length) {
          const cur = prev[mKey];
          next[mKey] = cur && opts.includes(cur) ? cur : opts[0];
          if (next[mKey] !== cur) changed = true;
        }
      }
      if (!changed && Object.keys(next).length === Object.keys(prev).length) return prev;
      return next;
    });
  }, [value.dims, value.multiplierEnabled, value.multiplierKey, value.multiplierOptions]);

  const addDim = () => {
    if (value.dims.length >= MAX_DIMS) return;
    patch({
      dims: [
        ...value.dims,
        { uid: nextUid('d'), key: '', tiers: [{ uid: nextUid('t'), value: '', delta: 0 }] },
      ],
    });
  };

  const cardStyle: React.CSSProperties = {
    background: token.colorBgContainer,
    border: `1px solid ${token.colorBorderSecondary}`,
    borderRadius: token.borderRadiusLG,
    padding: '12px 14px',
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ width: 3, height: 14, borderRadius: 2, background: token.colorPrimary }} />
        <Text strong style={{ fontSize: 14 }}>
          参数与计价
        </Text>
        <Tooltip title="这里配置的每个参数维度，既决定用户在生成面板能选什么，也决定选中后加多少钱。保存后同时写入 pricing_json 与 params_schema_json。">
          <InfoCircleOutlined style={{ color: token.colorTextTertiary }} />
        </Tooltip>
        <span style={{ flex: 1 }} />
        <Tag color="blue" style={{ marginInlineEnd: 0 }}>
          服务端权威计算
        </Tag>
      </div>

      {errors.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 10 }}
          message={errors[0]}
          description={
            errors.length > 1 ? <Text type="secondary">另有 {errors.length - 1} 项待修正</Text> : undefined
          }
        />
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.5fr) minmax(220px, 1fr)',
          gap: 12,
          alignItems: 'start',
        }}
      >
        {/* ─────────── 左：配置区 ─────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ ...cardStyle, display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500 }}>基础价</div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                未命中任何档位时的兜底价
              </Text>
            </div>
            <InputNumber
              min={0}
              max={1_000_000}
              precision={0}
              value={value.base}
              onChange={(v) => patch({ base: Number(v ?? 0) })}
              addonBefore="💎"
              style={{ width: 148 }}
            />
          </div>

          {value.dims.map((dim, idx) => (
            <DimCard
              key={dim.uid}
              dim={dim}
              index={idx}
              cardStyle={cardStyle}
              onPatch={(p) => patchDim(dim.uid, p)}
              onRemove={() => patch({ dims: value.dims.filter((d) => d.uid !== dim.uid) })}
            />
          ))}

          <div style={{ ...cardStyle, display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <Switch
              checked={value.multiplierEnabled}
              onChange={(v) => patch({ multiplierEnabled: v })}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 2 }}>
                数量倍率
                <Tooltip title="按张数/条数整体乘倍：最终价 =（基础价 + 各档加价）× 数量。为防止刷单，服务端把倍率钳制在 8 以内。">
                  <InfoCircleOutlined
                    style={{ color: token.colorTextTertiary, marginLeft: 6, fontSize: 12 }}
                  />
                </Tooltip>
              </div>
              {value.multiplierEnabled ? (
                <Space size={8} wrap style={{ marginTop: 6 }}>
                  <AutoComplete
                    value={value.multiplierKey}
                    onChange={(v) => patch({ multiplierKey: v ?? '' })}
                    options={[{ value: 'n' }, { value: 'count' }, { value: 'num_images' }]}
                    placeholder="参数名"
                    style={{ width: 130 }}
                  />
                  <Select
                    mode="tags"
                    value={value.multiplierOptions}
                    onChange={(v) => patch({ multiplierOptions: v })}
                    placeholder="可选数量，回车添加"
                    style={{ minWidth: 200 }}
                    tokenSeparators={[',', ' ']}
                  />
                </Space>
              ) : (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  关闭后，一次请求只按单份计费
                </Text>
              )}
            </div>
          </div>

          <Button
            type="dashed"
            block
            icon={<PlusOutlined />}
            onClick={addDim}
            disabled={value.dims.length >= MAX_DIMS}
          >
            添加参数维度
            {value.dims.length >= MAX_DIMS ? `（已达上限 ${MAX_DIMS}）` : ''}
          </Button>
        </div>

        {/* ─────────── 右：试算区 ─────────── */}
        <div
          style={{
            background: token.colorFillQuaternary,
            borderRadius: token.borderRadiusLG,
            padding: 14,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <ThunderboltOutlined style={{ color: token.colorPrimary }} />
            <Text strong style={{ fontSize: 13 }}>
              实时试算
            </Text>
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            调后端计价引擎，所见即用户所付
          </Text>

          <div style={{ marginTop: 12 }}>
            {value.dims.filter((d) => isSafeDimName(d.key.trim()) && d.tiers.length).length === 0 &&
            !value.multiplierEnabled ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={<Text type="secondary" style={{ fontSize: 12 }}>暂无参数维度</Text>}
                style={{ margin: '8px 0' }}
              />
            ) : null}

            {value.dims.map((dim) => {
              const key = dim.key.trim();
              const options = dim.tiers.map((t) => String(t.value ?? '').trim()).filter(Boolean);
              if (!isSafeDimName(key) || !options.length) return null;
              return (
                <div key={dim.uid} style={{ marginBottom: 10 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {key}
                    {DIM_LABELS[key] ? ` · ${DIM_LABELS[key]}` : ''}
                  </Text>
                  <Segmented
                    block
                    size="small"
                    style={{ marginTop: 4 }}
                    value={picks[key] ?? options[0]}
                    options={options}
                    onChange={(v) => setPicks((p) => ({ ...p, [key]: String(v) }))}
                  />
                </div>
              );
            })}

            {value.multiplierEnabled && isSafeDimName(value.multiplierKey.trim()) && (
              <div style={{ marginBottom: 10 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {value.multiplierKey.trim()} · 数量
                </Text>
                <Segmented
                  block
                  size="small"
                  style={{ marginTop: 4 }}
                  value={picks[value.multiplierKey.trim()] ?? value.multiplierOptions[0]}
                  options={value.multiplierOptions.map((v) => String(v ?? '').trim()).filter(Boolean)}
                  onChange={(v) => setPicks((p) => ({ ...p, [value.multiplierKey.trim()]: String(v) }))}
                />
              </div>
            )}
          </div>

          <div
            style={{
              background: token.colorBgContainer,
              borderRadius: token.borderRadius,
              padding: 12,
              marginTop: 4,
              opacity: previewing ? 0.6 : 1,
              transition: 'opacity .18s ease',
            }}
          >
            <Text type="secondary" style={{ fontSize: 12 }}>
              本次消耗
            </Text>
            <div
              style={{
                fontSize: 26,
                fontWeight: 600,
                lineHeight: 1.3,
                color: errors.length || previewError ? token.colorTextQuaternary : token.colorPrimary,
              }}
            >
              {errors.length ? '—' : previewError ? '!' : (preview?.cost ?? '—')}
              {!errors.length && !previewError && preview && (
                <span style={{ fontSize: 12, fontWeight: 400, marginLeft: 4, color: token.colorTextTertiary }}>
                  Tapies
                </span>
              )}
            </div>

            {previewError && (
              <Text type="danger" style={{ fontSize: 12 }}>
                {previewError}
              </Text>
            )}

            {!errors.length && !previewError && preview && (
              <>
                <Divider style={{ margin: '9px 0' }} />
                <BreakdownRow label="基础价" value={`${preview.base}`} />
                {preview.items.map((it) => (
                  <BreakdownRow
                    key={`${it.dim}=${it.value}`}
                    label={`${it.dim} = ${it.value}`}
                    value={it.hit ? `${it.delta >= 0 ? '+' : ''}${it.delta}` : '未命中'}
                    muted={!it.hit}
                  />
                ))}
                {preview.multiplierParam && (
                  <BreakdownRow
                    label={`× ${preview.multiplierParam} = ${picks[preview.multiplierParam] ?? 1}`}
                    value={`×${preview.multiplier}`}
                  />
                )}
                <Divider style={{ margin: '9px 0' }} />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  （{preview.base}
                  {preview.items
                    .filter((i) => i.hit && i.delta !== 0)
                    .map((i) => ` ${i.delta >= 0 ? '+' : '-'} ${Math.abs(i.delta)}`)
                    .join('')}
                  ）× {preview.multiplier} = {preview.cost}
                </Text>
              </>
            )}
          </div>
        </div>
      </div>

      <Collapse
        ghost
        size="small"
        style={{ marginTop: 6 }}
        items={[
          {
            key: 'json',
            label: (
              <Text type="secondary" style={{ fontSize: 12 }}>
                查看生成的 JSON（只读，供工程师核对）
              </Text>
            ),
            children: (
              <pre
                style={{
                  margin: 0,
                  padding: 10,
                  borderRadius: token.borderRadius,
                  background: token.colorFillQuaternary,
                  fontSize: 11,
                  lineHeight: 1.6,
                  maxHeight: 220,
                  overflow: 'auto',
                }}
              >
{`// pricing_json
${JSON.stringify(wire.pricing, null, 2)}

// params_schema_json
${JSON.stringify(wire.paramsSchema, null, 2)}`}
              </pre>
            ),
          },
        ]}
      />
    </div>
  );
}

function BreakdownRow({
  label,
  value,
  muted,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 3 }}>
      <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
        {label}
      </Text>
      <Text type={muted ? 'secondary' : undefined} style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
        {value}
      </Text>
    </div>
  );
}

function DimCard({
  dim,
  index,
  cardStyle,
  onPatch,
  onRemove,
}: {
  dim: DimRow;
  index: number;
  cardStyle: React.CSSProperties;
  onPatch: (p: Partial<DimRow>) => void;
  onRemove: () => void;
}) {
  const { token } = theme.useToken();
  const key = dim.key.trim();
  const keyInvalid = !!key && !isSafeDimName(key);

  const patchTier = (uid: string, p: Partial<{ value: string; delta: number }>) =>
    onPatch({ tiers: dim.tiers.map((t) => (t.uid === uid ? { ...t, ...p } : t)) });

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <AutoComplete
          value={dim.key}
          onChange={(v) => onPatch({ key: v ?? '' })}
          options={DIM_SUGGESTIONS.map((k) => ({
            value: k,
            label: `${k}${DIM_LABELS[k] ? ` · ${DIM_LABELS[k]}` : ''}`,
          }))}
          placeholder={`参数名，如 size（第 ${index + 1} 个维度）`}
          status={keyInvalid ? 'error' : undefined}
          style={{ width: 200 }}
        />
        {DIM_LABELS[key] && <Tag color="blue">{DIM_LABELS[key]}</Tag>}
        {keyInvalid && (
          <Text type="danger" style={{ fontSize: 12 }}>
            仅限字母/数字/下划线
          </Text>
        )}
        <span style={{ flex: 1 }} />
        <Text type="secondary" style={{ fontSize: 12 }}>
          {dim.tiers.length} 个档位
        </Text>
        <Tooltip title="删除该参数维度">
          <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={onRemove} />
        </Tooltip>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {dim.tiers.map((t) => (
          <div key={t.uid} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <AutoComplete
              value={t.value}
              onChange={(v) => patchTier(t.uid, { value: v ?? '' })}
              options={SUGGESTED_VALUES[key]?.map((v) => ({ value: v })) ?? []}
              placeholder="档位值，如 4K"
              style={{ flex: 1 }}
            />
            <InputNumber
              value={t.delta}
              onChange={(v) => patchTier(t.uid, { delta: Number(v ?? 0) })}
              precision={0}
              prefix="+"
              placeholder="加价"
              style={{ width: 116 }}
            />
            <Button
              size="small"
              type="text"
              icon={<DeleteOutlined />}
              onClick={() => onPatch({ tiers: dim.tiers.filter((x) => x.uid !== t.uid) })}
            />
          </div>
        ))}
      </div>

      <Button
        type="link"
        size="small"
        icon={<PlusOutlined />}
        style={{ paddingInline: 0, marginTop: 6, color: token.colorPrimary }}
        disabled={dim.tiers.length >= MAX_TIERS_PER_DIM}
        onClick={() =>
          onPatch({ tiers: [...dim.tiers, { uid: nextUid('t'), value: '', delta: 0 }] })
        }
      >
        添加档位
      </Button>
    </div>
  );
}

/** 常见维度的档位候选值, 减少手打错字 (如 4k / 4K 拼错就永远命不中)。 */
const SUGGESTED_VALUES: Record<string, string[]> = {
  size: ['1K', '2K', '4K', '720P', '1080P'],
  resolution: ['1K', '2K', '4K'],
  duration: ['5', '6', '10', '15', '30'],
  quality: ['standard', 'high', 'ultra'],
  ratio: ['1:1', '16:9', '9:16', '4:3'],
};

export type { PricingRule };
