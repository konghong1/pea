import re

P = 'D:/workspace/ai-agent/pea-canvas-v10.html'
with open(P, 'r', encoding='utf-8') as f:
    c = f.read()

# ---- 1) rewrite the FIRST :root block with REAL pea tokens ----
new_root = """:root {
  --bg-deep:      #0a0a0a;
  --bg-surface:   #0f0f0f;
  --bg-panel:     #1f1f1f;
  --bg-elevated:  #262626;
  --bg-hover:     #2b2b2b;
  --border:       rgba(255,255,255,.10);
  --border-focus: rgba(255,255,255,.15);
  --text-primary: #f5f5f5;
  --text-secondary:#d4d4d8;
  --text-muted:   #7a7a7a;
  --accent:       #1fa2dc;
  --accent-hover: #90c4e5;
  --accent-glow:  rgba(31,162,220,.18);
  --success:      #34d399;
  --warning:      #fbbf24;
  --danger:       #f87171;
  --radius-sm:    8px;
  --radius-md:    12px;
  --radius-lg:    16px;
  --radius-xl:    24px;
  --radius-pill:  999px;
  --shadow-sm:    0 2px 4px rgba(0,0,0,.10);
  --shadow-md:    0 2px 4px rgba(0,0,0,.10),0 2px 8px rgba(0,0,0,.12);
  --font:         -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans CJK SC",sans-serif;
}"""
c = re.sub(r':root \{[^}]*\}', new_root, c, count=1)
print('root replaced:', ':root {' in c[:400])

# ---- 2) global brand-color literal unification to cyan ----
c = c.replace('#4a90ff', '#1fa2dc')
c = c.replace('#6aa3ff', '#90c4e5')
c = c.replace('rgba(74,144,255', 'rgba(31,162,220')

# ---- 3) send button -> solid cyan (was purple gradient) ----
c = c.replace(
    'background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-size:15px;',
    'background:#1fa2dc;color:#fff;font-size:15px;')
# keep avatar gradient purple (semantic) — leave other #6366f1/#8b5cf6 as-is

# ---- 4) purple glows -> cyan glows (workspace / node) ----
c = c.replace('rgba(99,102,241', 'rgba(31,162,220')

# ---- 5) add-pal bottom bar background -> real popover tone ----
c = c.replace('rgba(30,32,38,.85)', 'rgba(38,38,38,.96)')
c = c.replace('rgba(30,32,38,.95)', 'rgba(38,38,38,.96)')

# ---- 6) heavy purple/black shadows -> subtle (match real shadow-md) ----
c = c.replace('0 20px 60px rgba(0,0,0,.6)', '0 12px 40px rgba(0,0,0,.5)')
c = c.replace('0 24px 64px rgba(0,0,0,.70)', '0 16px 48px rgba(0,0,0,.55)')
c = c.replace('0 12px 32px rgba(0,0,0,.60)', '0 8px 28px rgba(0,0,0,.5)')
c = c.replace('0 20px 55px', '0 12px 40px')
c = c.replace('0 8px 24px rgba(0,0,0,.5)', '0 4px 16px rgba(0,0,0,.45)')
# workspace sh-* helpers
c = c.replace('--sh-3: 0 12px 32px rgba(0,0,0,.60);', '--sh-3: 0 8px 28px rgba(0,0,0,.5);')
c = c.replace('--sh-modal: 0 24px 64px rgba(0,0,0,.70);', '--sh-modal: 0 16px 48px rgba(0,0,0,.55);')
c = c.replace('--sh-2: 0 4px 12px rgba(0,0,0,.50);', '--sh-2: 0 2px 8px rgba(0,0,0,.35);')
c = c.replace('--sh-1: 0 1px 2px rgba(0,0,0,.40);', '--sh-1: 0 2px 4px rgba(0,0,0,.25);')

with open(P, 'w', encoding='utf-8') as f:
    f.write(c)

# ---- verify ----
leftover_purple_brand = c.count('#6366f1') + c.count('rgba(99,102,241')
print('purple-brand refs left (expect avatar/node-type only):', leftover_purple_brand)
print('#1fa2dc count:', c.count('#1fa2dc'))
print('heavy shadow 0 20px 60px left:', c.count('0 20px 60px'))
print('done')
