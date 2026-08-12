# Design System Inspired by Runway (reference)

> Source: awesome-design-md/runwayml. Applied to pea **cinematic** surface (creation/canvas).

## 1. Visual Theme
Cinematic, editorial, film-production-grade. Full-bleed imagery/video is the primary UI. Interface retreats to near-invisibility: minimal borders, **zero shadows**, cool-gray text, dark palette. Single geometric sans for everything.

## 2. Color (cinematic surface)
- Runway Black `#000000` (page bg / max-emphasis text) · Deep Black `#030303` · Dark Surface `#1a1a1a`
- Pure White `#ffffff` (text on dark) · Near White `#fefefe` · Cool Cloud `#e9ecf2` (light bands)
- Cool Slate `#767d88` (secondary text) · Mid Slate `#7d848e` · Muted Gray `#a7a7a7`
- Border Dark `#27272a` (dark hairline) · Cool Silver `#c9ccd1` (light divider)
- **No interface gradients** — color comes only from media.

## 3. Typography
- One family (abcNormal → Inter fallback). Weight 400–600 (450 precision micro-label). 
- Display 48px/-1.2px lh1.0 · Section 40px · Sub 36px · Card title 24px · Body 16px (-0.16px) · Label 14px uppercase +0.35px · Micro 11px.
- Tight line-heights everywhere (1.0–1.3). Negative tracking default.

## 4. Components
- Buttons: small radius 4–8px; **primary CTA = pure-black pill (radius 9999px) with white text** per pea guidance; extremely restrained fills.
- Cards: transparent or `#1a1a1a`; border `1px #27272a`; **zero shadow**; radius 4–8px (16px for alert-style).
- Nav: minimal, transparent over hero; uppercase 14px labels w/ +0.35px tracking.

## 5. Layout
- Base 8px: 4,6,8,12,16,20,24,28,32,48,64,78. Section gaps 48–78px. Max container 1600px (cinema-wide). Hero full-bleed.

## 6. Depth
- **Zero box-shadow.** Depth from dark/light section alternation, photographic DOF, overlay transparency.

## 7. Do / Don't
- Do: let media dominate; single font; uppercase +letter-spacing labels; zero shadow; 4–8px functional radius.
- Don't: add decorative color, heavy borders, shadows, pill radius on functional controls (pill only for hero CTA), bold >600, multi-font.

## 8. Agent guide
- "Cinematic hero: full-bleed #000 bg, 48px Inter 400, lh1.0, -1.2px, white; sub text Cool Slate #767d88 16px."
- "Card: #1a1a1a surface, 1px #27272a border, radius 8px, no shadow."
