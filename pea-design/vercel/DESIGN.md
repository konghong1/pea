# Design System Inspired by Vercel (reference)

> Source: awesome-design-md/vercel. Applied to pea **precision** surface (admin/pages).

## 1. Visual Theme
Black-and-white precision. Monochrome, minimal, professional, data-clear. Geist typography. Hairline borders. Subtle stacked shadows (no single heavy drop).

## 2. Color (precision surface)
- ink `#171717` (primary CTA / dark text) · on-primary `#ffffff` · body `#4d4d4d` · mute `#888888`
- hairline `#ebebeb` · hairline-strong `#a1a1a1` · canvas `#ffffff` · canvas-soft `#fafafa` · canvas-soft-2 `#f5f5f5`
- selection `#171717`/`#f2f2f2`. Link `#0070f3` (used sparingly). Brand gradients reserved for hero only.

## 3. Typography (Geist)
- display-xl 48/600/-2.4px · display-lg 32/600 · display-md 24/600 · display-sm 20/600
- body-lg 18/400 · body-md 16/400 · body-sm 14/400/-0.28px · caption 12 · code 13 mono
- Weight cap 600; negative tracking is the brand voice; sentence-case + period.

## 4. Components
- button-primary: bg `#171717`, text `#fff`, radius `pill 100px` (marketing) / `6px` (in-app); for pea in-app use **6px**.
- Secondary: white bg, ink text, hairline border.
- Cards: white bg, radius md 8px / lg 12px, hairline border, subtle stacked shadow. Featured card inverts to ink bg.

## 5. Layout
- 4px base: 4,8,12,16,24,32,40,48,64,96,128,192. Section pad 64–96px; hero 192px. Card pad 16–32px.

## 6. Depth (stacked, subtle)
- L1 inset hairline `0 0 0 1px #00000014` · L2 `0 1px 1px #00000005,0 2px 2px #0000000a` · L3 `0 2px 2px #0000000a,0 8px 8px -8px #0000000a` · L4 `0 8px 16px -4px #0000000a` · L5 modal `0 24px 32px -8px #0000000f`. All + inset hairline.

## 7. Radius
- none 0 · xs 4 · sm 6 (app buttons/inputs) · md 8 (cards) · lg 12 (pricing) · xl 16 · pill-sm 64 · pill 100 · full 9999.

## 8. Agent guide
- "Precision card: white bg, 1px #ebebeb border, radius 8px, shadow L2, ink #171717 text."
- "In-app button: bg #171717, white text, radius 6px, Geist 14/500."
