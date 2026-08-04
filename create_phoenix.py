import random, math, os

def generate_anime_phoenix(scheme):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">', '<defs>']
    lines.append('<radialGradient id="bg" cx="50%" cy="55%" r="85%">')
    lines.append(f'<stop offset="0%" stop-color="{scheme["bg_center"]}"/>')
    lines.append(f'<stop offset="100%" stop-color="{scheme["bg_edge"]}"/>')
    lines.append('</radialGradient>')
    lines.append('<filter id="glow1" x="-150%" y="-150%" width="400%" height="400%">')
    lines.append('<feGaussianBlur stdDeviation="3" result="b1"/>')
    lines.append('<feGaussianBlur stdDeviation="6" result="b2"/>')
    lines.append('<feGaussianBlur stdDeviation="12" result="b3"/>')
    lines.append('<feMerge><feMergeNode in="b3"/><feMergeNode in="b2"/><feMergeNode in="b1"/><feMergeNode in="SourceGraphic"/></feMerge>')
    lines.append('</filter>')
    lines.append('<filter id="glow2"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    lines.append('<filter id="glow3"><feGaussianBlur stdDeviation="1" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    lines.append('</defs>')
    lines.append(f'<rect width="512" height="512" rx="48" fill="url(#bg)"/>')
    lines.append(f'<ellipse cx="256" cy="260" rx="160" ry="140" fill="{scheme["halo"]}"/>')
    
    random.seed(42)
    p = []
    
    # 头部轮廓
    for angle in range(0, 360, 5):
        rad = angle * 3.14159 / 180
        r = 22 + random.uniform(-3, 3)
        x = 256 + r * 1.1 * 0.9
        y = 90 + r * 0.9
        size = random.uniform(4, 8)
        color = random.choice(scheme['head_colors'])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{random.uniform(0.8,1):.2f}" filter="url(#glow2)"/>')
    
    # 头部内部
    for _ in range(30):
        angle = random.uniform(0, 6.28)
        r = random.uniform(0, 18)
        x = 256 + r * 0.9 * math.cos(angle)
        y = 90 + r * 0.8 * math.sin(angle)
        size = random.uniform(3, 6)
        color = random.choice(scheme['colors'])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{random.uniform(0.5,0.9):.2f}" filter="url(#glow3)"/>')
    
    # 眼睛 - 动漫风格
    p.append(f'<ellipse cx="242" cy="88" rx="6" ry="8" fill="{scheme["eye_dark"]}" filter="url(#glow2)"/>')
    p.append(f'<ellipse cx="242" cy="87" rx="4" ry="5" fill="{scheme["eye_color"]}"/>')
    p.append(f'<circle cx="240" cy="85" r="2" fill="white"/>')
    p.append(f'<ellipse cx="270" cy="88" rx="6" ry="8" fill="{scheme["eye_dark"]}" filter="url(#glow2)"/>')
    p.append(f'<ellipse cx="270" cy="87" rx="4" ry="5" fill="{scheme["eye_color"]}"/>')
    p.append(f'<circle cx="268" cy="85" r="2" fill="white"/>')
    
    # 喙
    for i in range(15):
        t = i / 14
        x = 256 + (t - 0.5) * 12
        y = 100 + t * 18
        size = 3 + (1-t) * 3
        color = random.choice(scheme['beak_colors'])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{random.uniform(0.7,1):.2f}" filter="url(#glow3)"/>')
    
    # 冠羽
    for feather in range(5):
        fx = 256 + (feather - 2) * 18
        for i in range(25):
            t = i / 24
            x = fx + random.uniform(-8, 8) + math.sin(t * 6.28) * 5
            y = 70 - t * 50
            size = (1-t) * 8 + random.uniform(1, 4)
            color = random.choice(scheme['crown_colors'])
            p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{(1-t*0.5):.2f}" filter="url(#glow2)"/>')
    
    # 身体轮廓
    for angle in range(0, 360, 8):
        rad = angle * 3.14159 / 180
        rx, ry = 38, 55
        x = 256 + rx * 0.9 * math.cos(rad)
        y = 170 + ry * 0.9 * math.sin(rad)
        size = random.uniform(5, 10)
        color = random.choice(scheme['body_colors'])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{random.uniform(0.7,1):.2f}" filter="url(#glow2)"/>')
    
    # 身体内部
    for _ in range(50):
        angle = random.uniform(0, 6.28)
        r = random.uniform(0, 35)
        x = 256 + r * 0.9 * math.cos(angle)
        y = 170 + r * 0.85 * math.sin(angle)
        size = random.uniform(3, 8)
        color = random.choice(scheme['colors'])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{random.uniform(0.4,0.8):.2f}" filter="url(#glow3)"/>')
    
    # 左翅膀
    for layer in range(8):
        for idx in range(12):
            fx = 210 - idx * 12
            fy = 140 + layer * 8
            for i in range(20):
                t = i / 19
                x = fx - t * 35 + random.uniform(-5, 5)
                y = fy + t * 20
                size = (1-t) * 6 + random.uniform(1, 3)
                color = random.choice(scheme['wing_colors'])
                p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{(0.9-t*0.4):.2f}" filter="url(#glow2)"/>')
    
    # 右翅膀
    for layer in range(8):
        for idx in range(12):
            fx = 302 + idx * 12
            fy = 140 + layer * 8
            for i in range(20):
                t = i / 19
                x = fx + t * 35 + random.uniform(-5, 5)
                y = fy + t * 20
                size = (1-t) * 6 + random.uniform(1, 3)
                color = random.choice(scheme['wing_colors'])
                p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{(0.9-t*0.4):.2f}" filter="url(#glow2)"/>')
    
    # 长尾
    for tail in range(7):
        tx = 235 + tail * 10
        for i in range(35):
            t = i / 34
            wave = math.sin(t * 6.28) * 15 * (1-t)
            x = tx + wave + random.uniform(-5, 5)
            y = 240 + t * 180
            size = (1-t*0.7) * 7 + random.uniform(1, 4)
            color = random.choice(scheme['tail_colors'])
            p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{(1-t*0.5):.2f}" filter="url(#glow2)"/>')
    
    # 火焰粒子
    for _ in range(100):
        angle = random.uniform(0, 6.28)
        r = random.uniform(80, 200)
        x = 256 + r * 0.9 * math.cos(angle)
        y = 260 + r * 0.8 * math.sin(angle)
        size = random.uniform(2, 8)
        color = random.choice(scheme['flame_colors'])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{random.uniform(0.2,0.6):.2f}" filter="url(#glow3)"/>')
    
    for _ in range(60):
        x = random.uniform(180, 332)
        y = random.uniform(350, 520)
        size = random.uniform(2, 6)
        color = random.choice(scheme['flame_colors'])
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{random.uniform(0.3,0.7):.2f}"/>')
    
    # 核心光芒
    for _ in range(30):
        angle = random.uniform(0, 6.28)
        r = random.uniform(0, 50)
        x = 256 + r * 0.9 * math.cos(angle)
        y = 180 + r * 0.8 * math.sin(angle)
        size = random.uniform(4, 12)
        p.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{scheme["highlight"]}" filter="url(#glow1)"/>')
    
    lines.append('<g filter="url(#glow1)">')
    lines.extend(p)
    lines.append('</g>')
    lines.append(f'<rect width="512" height="512" rx="48" fill="none" stroke="{scheme["border"]}" stroke-width="2" filter="url(#glow2)"/>')
    lines.append('</svg>')
    return '\n'.join(lines)

schemes = {
    'flame': {'bg_center':'#1a0500','bg_edge':'#050200','halo':'rgba(255,60,0,0.08)','halo_inner':'rgba(255,150,0,0.05)',
        'colors':['#ff2400','#ff4500','#ff6b35','#ff8c00','#ffa500','#ffd700'],
        'head_colors':['#ff4500','#ff6b35','#ff8c00','#ffd700'],
        'crown_colors':['#ffd700','#ffa500','#ff8c00','#ff6b35'],
        'body_colors':['#ff4500','#ff6b35','#ff8c00','#ffd700'],
        'wing_colors':['#ff4500','#ff6b35','#ff8c00','#ffa500','#ffd700'],
        'tail_colors':['#ff8c00','#ffa500','#ffd700','#ffe066','#fff8dc'],
        'flame_colors':['#ff2400','#ff4500','#ff6b35','#ff8c00','#ffd700'],
        'beak_colors':['#ff8c00','#ffa500','#ffd700'],
        'eye_dark':'#1a0500','eye_color':'#ffd700',
        'highlight':'#fff4a0','border':'rgba(255,120,0,0.3)'},
    'neon': {'bg_center':'#0a001a','bg_edge':'#05000a','halo':'rgba(124,58,237,0.08)','halo_inner':'rgba(167,139,250,0.05)',
        'colors':['#4c1d95','#5b21b6','#6d28d9','#7c3aed','#8b5cf6','#a78bfa'],
        'head_colors':['#7c3aed','#8b5cf6','#a78bfa','#c084fc'],
        'crown_colors':['#c084fc','#a78bfa','#8b5cf6','#7c3aed'],
        'body_colors':['#7c3aed','#8b5cf6','#a78bfa','#c084fc'],
        'wing_colors':['#7c3aed','#8b5cf6','#a78bfa','#c084fc','#e9d5ff'],
        'tail_colors':['#a78bfa','#c084fc','#e9d5ff','#f5f3ff'],
        'flame_colors':['#7c3aed','#8b5cf6','#a78bfa','#c084fc','#e9d5ff'],
        'beak_colors':['#a78bfa','#c084fc','#e9d5ff'],
        'eye_dark':'#0a001a','eye_color':'#e9d5ff',
        'highlight':'#f5f3ff','border':'rgba(124,58,237,0.3)'},
    'emerald': {'bg_center':'#001a0a','bg_edge':'#000a05','halo':'rgba(52,211,153,0.08)','halo_inner':'rgba(110,231,183,0.05)',
        'colors':['#064e3b','#065f46','#059669','#10b981','#34d399','#6ee7b7'],
        'head_colors':['#059669','#10b981','#34d399','#6ee7b7'],
        'crown_colors':['#6ee7b7','#34d399','#10b981','#059669'],
        'body_colors':['#059669','#10b981','#34d399','#6ee7b7'],
        'wing_colors':['#059669','#10b981','#34d399','#6ee7b7','#a7f3d0'],
        'tail_colors':['#34d399','#6ee7b7','#a7f3d0','#d1fae5'],
        'flame_colors':['#059669','#10b981','#34d399','#6ee7b7','#a7f3d0'],
        'beak_colors':['#34d399','#6ee7b7','#a7f3d0'],
        'eye_dark':'#001a0a','eye_color':'#d1fae5',
        'highlight':'#ecfdf5','border':'rgba(52,211,153,0.3)'}
}

os.makedirs('D:/workspace/pea/assets/icons', exist_ok=True)
for fname, scheme in [('icon-1-pea-pod.svg', schemes['flame']), ('icon-2-abstract.svg', schemes['neon']), ('icon-3-minimal.svg', schemes['emerald'])]:
    svg = generate_anime_phoenix(scheme)
    with open(f'D:/workspace/pea/assets/icons/{fname}', 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'{fname}: {len(svg)} bytes')
