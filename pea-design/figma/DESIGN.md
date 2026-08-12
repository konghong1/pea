# Design System Inspired by Figma (reference)

> Source: awesome-design-md/figma. Applied to pea **figma** surface (creation/canvas, light alternative to Runway).
> 互补于 cinematic/Runway —— 同一「创作端」，亮色分支。

## 1. Visual Theme

Confident black-and-white editorial frame interrupted by oversized, hand-cut pastel color blocks. Marketing canvas is rigorously monochrome — pure white surfaces, pure black ink, pill-shaped CTAs — while story sections drop the page into saturated lime / lavender / cream / mint / pink panels that read like sticky notes on a clean desk. Technical AND joyful.

## 2. Color (figma surface)

### Monochrome chrome (every CTA, headline, body line)
- **Black** `#000000` (primary, headlines, ink)
- **White** `#ffffff` (canvas, on-primary text)
- **Hairline** `#e6e6e6` (1px borders on cards/inputs)
- **Hairline Soft** `#f1f1f1` (subtler dividers)
- **Surface Soft** `#f7f7f5` (off-white tiles, icon-button bg)

### Pastel color blocks (signature storytelling device — 全宽圆角面板)
- **Block Lime** `#dceeb1` · **Block Lilac** `#c5b0f4` · **Block Cream** `#f4ecd6`
- **Block Mint** `#c8e6cd` · **Block Pink** `#efd4d4` · **Block Coral** `#f3c9b6`
- **Block Navy** `#1f1d3d` (the only dark color block)

### Accent
- **Magenta Promo** `#ff3d8b` (single-shot pink CTA, use sparingly)
- **Success** `#1ea64a` (glyph only, never surface)

### 落到 pea 令牌
- `--pea-bg-deep: #ffffff` · `--pea-bg-surface: #ffffff` · `--pea-bg-elevated: #f7f7f5`
- `--pea-border: #e6e6e6` · `--pea-border-strong: #cfcfcf`
- `--pea-text-primary: #000000` · `--pea-text-secondary: #4d4d4d` · `--pea-text-muted: #8a8a8a`
- `--pea-brand / --pea-accent: #000000`（黑墨主操作）
- `--pea-purple: #8b5cf6`（AI 信号，全表面统一）

## 3. Typography

- **figmaSans** (proprietary variable) → fallback **Inter**（figmaSans 的开源替身，variable weights 320/330/340/480/540/700 匹配 figmaSans 的细粒度 weight 轴）。
- **figmaMono** → fallback **Geist Mono** / **JetBrains Mono**（仅用于 eyebrows / captions，全大写 + 正字距）。
- 字号节奏：Display 86/64 · Headline 26 · Body 18/20 · Caption 12 mono uppercase。
- **层级靠字重，不靠字号**：20px body 320 与 20px link 480 并排，靠 weight 表达强调。
- 显示字号负字距（-1.72px @ 86px → -0.26px @ 26px）；正文近零。
- 显示行高紧凑 1.0–1.10；正文 1.40–1.45。
- **mono 永远是分类标签，不是正文**。

## 4. Components

- **Buttons**：所有文字 CTA = pill（`rounded.pill: 50px`），无方角。`button-primary` = 纯黑底白字 + `0 1px 2px rgba(0,0,0,0.18)` 微影；`button-secondary` = 白底黑字 pill（无边框，靠阴影对比）。Icon button = `rounded.full: 9999px` 圆形 40px（`surface-soft` 背景）。
- **Cards**：白底 + `1px hairline` 描边（**不靠阴影做层级**），`rounded.lg: 24px`。极少数 floating 元素才用 `0 4px 16px rgba(0,0,0,0.06)` 软影。
- **Forms**：白底 + hairline 边框 + `rounded.md: 8px`；focus 用 ring，不改 fill。
- **Color-block sections**：全宽 + `rounded.lg: 24px` 圆角 + 48px 内边距；每个 viewport 只允许出现一个色块，色块之间回到白底。
- **Pricing-tab-selected** = 与 button-primary 同一黑色表面（"选中态 = 主操作"）。
- **不要灰色文字**；body 永远 `#000` 320–340 weight，靠 weight 表达层级，不靠 opacity。

## 5. Layout

- Base 8px：4 / 8 / 12 / 16 / 24 / 32 / 48 / 96。
- Card 内边距 24px；color-block 内边距 48px；按钮 padding `8px 18px 10px`（**不对称纵向**，光学居中文字）。
- Section 间距 96px。
- Max content width ~1280px。
- Color-block 突破栏栅：跨满内容宽度，圆角 24px，内部只放单栏编辑式 headline + body。

## 6. Depth

| 层级 | 处理 | 用途 |
|---|---|---|
| 0 (flat) | 无阴影无边框 | color-block、footer、hero |
| 1 (hairline) | `1px hairline` | pricing card / form input |
| 2 (soft) | `0 4px 16px rgba(0,0,0,0.06)` | floating template / dropdown |
| 3 (modal) | 更深阴影 + 60% 黑 scrim | lightbox / video overlay |

**核心：色块即层级。** 大多数 SaaS 用阴影白卡强调；Figma 用饱和背景面板强调。所以白卡几乎不带阴影，反而让真正悬浮的元素（template card）显得"例外"。

## 7. 落到 pea figma surface 的实现摘要

- 画布容器加 `data-surface="figma"` 切换令牌。
- 节点卡：`--pea-node-bg: #ffffff` + `1px #e6e6e6` hairline + `0 8px 28px rgba(0,0,0,0.08)` 软影 + `rounded.lg: 24px`。
- 主 CTA：`.pea-btn--primary` 黑药丸白字 + `0 1px 2px rgba(0,0,0,0.18)`。
- 连线：`--pea-edge-idle: rgba(0,0,0,0.18)`（深墨，非青）。
- 字体：Inter 主导（`--pea-font-sans: 'Inter', 'Geist', ...`）。

## 8. Do / Don't

**Do**
- 主操作只用纯黑/纯白；`--pea-purple` 留给 AI 信号，不要给 figma 加新彩。
- 写故事面板时选**一个** color-block，让它全宽 + 24px 圆角 + 48px 内边距。
- 字号层级走 weight（320→480→700），不靠透明度。
- mono 只用于 eyebrows/captions，全大写 + 正字距。
- 所有文字 CTA = pill；所有 icon button = 圆。
- 每个色块之间回到白底，让每个色块读起来"刻意"。

**Don't**
- 不要灰色正文（不要 `#888` body）—— Figma 没有 mid-gray text role。
- 不要给 color-block 加阴影。
- 不要在 `{colors.block-*}` 之外引入新彩。
- 同一 viewport 不要叠两个色块。
- 不要方角 CTA（方按钮 = 另一个品牌）。
- 不要用 figmaMono 写正文段。
- 不要把"选中态 tab"换成彩色填充 —— 选中 = 主操作 = 黑。

## 9. Agent guide

- "Figma 创作端：纯白画布 `#ffffff`，纯黑墨 `#000000`，hairline `#e6e6e6`，圆角 24px，软投影 `0 8px 28px rgba(0,0,0,0.08)`，Inter 字体。"
- "Node card: `#ffffff` 表面 + `1px #e6e6e6` 边 + `0 8px 28px rgba(0,0,0,0.08)` 阴影 + `rounded.lg 24px`。"
- "Primary CTA: 纯黑药丸白字 + `0 1px 2px rgba(0,0,0,0.18)` 微影，padding 10px 20px。"
- "Color block: 全宽 + 24px 圆角 + 48px 内边距，仅在讲故事时使用，且每屏一个。"