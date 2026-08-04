import random, math, os

def gen(scheme):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">', '<defs>']
    lines.append('<radialGradient id="bg" cx="50%" cy="50%" r="70%">')
    lines.append(f'<stop offset="0%" stop-color="{scheme["bgc"]}"/>')
    lines.append(f'<stop offset="100%" stop-color="{scheme["bge"]}"/>')
    lines.append('</radialGradient>')
    lines.append('<filter id="g"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    lines.append('<filter id="s"><feGaussianBlur stdDeviation="1.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    lines.append('</defs>')
    lines.append(f'<rect width="512" height="512" rx="48" fill="url(#bg)"/>')
    
    random.seed(2024)
    p = []
    
    # Head - left side
    for _ in range(60):
        a = random.uniform(0, 6.28)
        r = random.uniform(3, 35)
        x = 90 + r * 0.9 * math.cos(a)
        y = 180 + r * 0.8 * math.sin(a)
        sz = random.uniform(2, 7)
        c = random.choice(scheme["colors"])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{c}" opacity="{random.uniform(0.5,1):.2f}" filter="url(#s)"/>')
    
    # Eye
    p.append(f'<circle cx="75" cy="175" r="5" fill="{scheme["ed"]}"/>')
    p.append(f'<circle cx="75" cy="174" r="2.5" fill="{scheme["ec"]}"/>')
    p.append(f'<circle cx="74" cy="173" r="1" fill="white"/>')
    
    # Beak
    for i in range(12):
        t = i / 11
        x = 65 - t * 25
        y = 190 + t * 15
        sz = 4 - t * 2
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{random.choice(scheme["bk"])}" opacity="{random.uniform(0.7,1):.2f}" filter="url(#s)"/>')
    
    # Crown feathers -飘向左上
    for _ in range(40):
        t = random.uniform(0, 1)
        x = 90 - t * 40 + random.uniform(-10, 10)
        y = 150 - t * 50 + random.uniform(-8, 8)
        sz = random.uniform(2, 6) * (1-t*0.5)
        c = random.choice(scheme["cr"])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{c}" opacity="{random.uniform(0.5,0.9):.2f}" filter="url(#s)"/>')
    
    # Body - horizontal ellipse
    for _ in range(100):
        a = random.uniform(0, 6.28)
        r = random.uniform(5, 55)
        x = 180 + r * 1.2 * math.cos(a)
        y = 210 + r * 0.7 * math.sin(a)
        sz = random.uniform(2, 6)
        c = random.choice(scheme["colors"])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{c}" opacity="{random.uniform(0.4,0.9):.2f}" filter="url(#s)"/>')
    
    # Upper wing - up and left
    for _ in range(120):
        a = random.uniform(-3.0, -0.3)
        r = random.uniform(10, 90)
        x = 180 + r * 0.8 * math.cos(a)
        y = 190 + r * 0.5 * math.sin(a)
        sz = random.uniform(2, 7)
        c = random.choice(scheme["wg"])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{c}" opacity="{random.uniform(0.4,0.8):.2f}"/>')
    
    # Lower wing
    for _ in range(80):
        a = random.uniform(0.3, 2.5)
        r = random.uniform(10, 60)
        x = 180 + r * 0.7 * math.cos(a)
        y = 220 + r * 0.4 * math.sin(a)
        sz = random.uniform(2, 5)
        c = random.choice(scheme["wg"])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{c}" opacity="{random.uniform(0.3,0.7):.2f}"/>')
    
    # Tail - flowing right
    for strand in range(12):
        bx = 260 + strand * 8
        for _ in range(30):
            t = random.uniform(0, 1)
            x = bx + t * 120 + random.uniform(-15, 15)
            y = 260 + t * 30 + math.sin(t * 6.28) * 20 + random.uniform(-10, 10)
            sz = random.uniform(2, 8) * (1 - t * 0.6)
            c = random.choice(scheme["tl"])
            p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{c}" opacity="{random.uniform(0.3,0.8):.2f}" filter="url(#s)"/>')
    
    # Fire particles - scattered
    for _ in range(150):
        a = random.uniform(0, 6.28)
        r = random.uniform(80, 220)
        x = 200 + r * 0.9 * math.cos(a)
        y = 230 + r * 0.8 * math.sin(a)
        sz = random.uniform(1, 5)
        c = random.choice(scheme["fl"])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{c}" opacity="{random.uniform(0.1,0.5):.2f}"/>')
    
    # Core highlights
    for _ in range(25):
        x = random.uniform(120, 280)
        y = random.uniform(140, 300)
        sz = random.uniform(4, 12)
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{sz:.1f}" fill="{scheme["hl"]}" filter="url(#g)"/>')
    
    lines.append('<g>')
    lines.extend(p)
    lines.append('</g>')
    lines.append(f'<rect width="512" height="512" rx="48" fill="none" stroke="{scheme["br"]}" stroke-width="2"/>')
    lines.append('</svg>')
    return '\n'.join(lines)

schemes = {
    'flame': {'bgc':'#1a0800','bge':'#050200',
        'colors':['#ff2400','#ff4500','#ff6b35','#ff8c00','#ffa500','#ffd700'],
        'cr':['#ffd700','#ffa500','#ff8c00','#ff6b35'],
        'wg':['#ff4500','#ff6b35','#ff8c00','#ffa500','#ffd700'],
        'tl':['#ff8c00','#ffa500','#ffd700','#ffe066'],
        'fl':['#ff2400','#ff4500','#ff8c00','#ffd700'],
        'bk':['#ff8c00','#ffa500','#ffd700'],
        'ed':'#1a0800','ec':'#ffd700','hl':'#fff4a0','br':'rgba(255,140,0,0.25)'},
    'neon': {'bgc':'#0a001a','bge':'#05000a',
        'colors':['#4c1d95','#5b21b6','#6d28d9','#7c3aed','#8b5cf6','#a78bfa'],
        'cr':['#c084fc','#a78bfa','#8b5cf6','#7c3aed'],
        'wg':['#7c3aed','#8b5cf6','#a78bfa','#c084fc','#e9d5ff'],
        'tl':['#a78bfa','#c084fc','#e9d5ff','#f5f3ff'],
        'fl':['#7c3aed','#8b5cf6','#a78bfa','#c084fc'],
        'bk':['#a78bfa','#c084fc','#e9d5ff'],
        'ed':'#0a001a','ec':'#e9d5ff','hl':'#f5f3ff','br':'rgba(124,58,237,0.25)'},
    'emerald': {'bgc':'#001a0a','bge':'#000a05',
        'colors':['#064e3b','#065f46','#059669','#10b981','#34d399','#6ee7b7'],
        'cr':['#6ee7b7','#34d399','#10b981','#059669'],
        'wg':['#059669','#10b981','#34d399','#6ee7b7','#a7f3d0'],
        'tl':['#34d399','#6ee7b7','#a7f3d0','#d1fae5'],
        'fl':['#10b981','#34d399','#6ee7b7','#a7f3d0'],
        'bk':['#34d399','#6ee7b7','#a7f3d0'],
        'ed':'#001a0a','ec':'#d1fae5','hl':'#ecfdf5','br':'rgba(52,211,153,0.25)'}
}

os.makedirs('D:/workspace/pea/assets/icons', exist_ok=True)
for fname, scheme in [('icon-1-pea-pod.svg', schemes['flame']), ('icon-2-abstract.svg', schemes['neon']), ('icon-3-minimal.svg', schemes['emerald'])]:
    svg = gen(scheme)
    with open(f'D:/workspace/pea/assets/icons/{fname}', 'w', encoding='utf-8') as f:
        f.write(svg)
    circles = svg.count('<circle')
    print(f'{fname}: {len(svg)} bytes, {circles} particles')
