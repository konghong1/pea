import random
import os

def generate_phoenix(color_scheme, name):
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">')
    
    lines.append('<defs>')
    lines.append('<radialGradient id="bg" cx="50%" cy="60%" r="80%">')
    lines.append(f'<stop offset="0%" stop-color="{color_scheme["bg_center"]}"/>')
    lines.append(f'<stop offset="100%" stop-color="{color_scheme["bg_edge"]}"/>')
    lines.append('</radialGradient>')
    lines.append('<filter id="glow" x="-100%" y="-100%" width="300%" height="300%">')
    lines.append('<feGaussianBlur stdDeviation="4" result="b1"/>')
    lines.append('<feGaussianBlur stdDeviation="8" result="b2"/>')
    lines.append('<feMerge><feMergeNode in="b2"/><feMergeNode in="b1"/><feMergeNode in="SourceGraphic"/></feMerge>')
    lines.append('</filter>')
    lines.append('<filter id="softGlow">')
    lines.append('<feGaussianBlur stdDeviation="2" result="b"/>')
    lines.append('<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>')
    lines.append('</filter>')
    lines.append('</defs>')
    
    lines.append(f'<rect width="512" height="512" rx="48" fill="url(#bg)"/>')
    lines.append(f'<ellipse cx="256" cy="280" rx="200" ry="160" fill="{color_scheme["glow"]}"/>')
    
    random.seed(42)
    particles = []
    
    # 头部粒子
    for i in range(50):
        angle = random.uniform(0, 6.28)
        r = random.uniform(5, 28)
        x = int(256 + r * 1.2 * 0.9)
        y = int(100 + r * 0.9)
        size = random.uniform(3, 14)
        opacity = random.uniform(0.5, 1.0)
        color = random.choice(color_scheme["colors"])
        particles.append(f'<circle cx="{x}" cy="{y}" r="{size:.1f}" fill="{color}" opacity="{opacity:.2f}" filter="url(#softGlow)"/>')
    
    # 冠羽
    for i in range(60):
        t = random.uniform(0, 1)
        spread = random.uniform(-35, 35)
        height = random.uniform(25, 70)
        x = int(256 + spread * (1-t) + random.uniform(-12, 12))
        y = int(75 - height)
        size = random.uniform(4, 16)
        opacity = random.uniform(0.6, 1.0)
        color = random.choice(color_scheme["colors"])
        particles.append(f'<circle cx="{x}" cy="{y}" r="{size:.1f}" fill="{color}" opacity="{opacity:.2f}"/>')
    
    # 身体核心
    for i in range(100):
        angle = random.uniform(0, 6.28)
        r = random.uniform(8, 50)
        x = int(256 + r * 1.4 * 0.9)
        y = int(200 + r * 1.0)
        size = random.uniform(4, 18)
        opacity = random.uniform(0.4, 0.9)
        color = random.choice(color_scheme["colors"])
        particles.append(f'<circle cx="{x}" cy="{y}" r="{size:.1f}" fill="{color}" opacity="{opacity:.2f}" filter="url(#softGlow)"/>')
    
    # 左翅膀多层
    for layer in range(6):
        y_off = layer * 30
        for i in range(45):
            angle = random.uniform(2.4, 3.9)
            r = random.uniform(25, 130 - layer*18)
            x = int(210 + r * 0.85 * 0.8)
            y = int(155 - y_off + r * 0.55 * 0.7)
            size = random.uniform(3, 14 - layer)
            opacity = random.uniform(0.3, 0.8)
            color = random.choice(color_scheme["wing_colors"])
            particles.append(f'<circle cx="{x}" cy="{y}" r="{size:.1f}" fill="{color}" opacity="{opacity:.2f}"/>')
    
    # 右翅膀
    for layer in range(6):
        y_off = layer * 30
        for i in range(45):
            angle = random.uniform(-0.4, 1.0)
            r = random.uniform(25, 130 - layer*18)
            x = int(302 + r * 1.15 * 0.85)
            y = int(155 - y_off + r * 0.55 * 0.7)
            size = random.uniform(3, 14 - layer)
            opacity = random.uniform(0.3, 0.8)
            color = random.choice(color_scheme["wing_colors"])
            particles.append(f'<circle cx="{x}" cy="{y}" r="{size:.1f}" fill="{color}" opacity="{opacity:.2f}"/>')
    
    # 长尾粒子群
    for strand in range(9):
        offset = (strand - 4) * 18
        for i in range(35):
            t = i / 34
            base_x = 235 + offset
            base_y = 275 + t * 180
            spread = random.uniform(-25, 25) * (1-t)
            x = int(base_x + spread)
            y = int(base_y)
            size = random.uniform(4, 12 * (1-t*0.6))
            opacity = random.uniform(0.4, 0.9) * (1-t*0.4)
            color = random.choice(color_scheme["tail_colors"])
            particles.append(f'<circle cx="{x}" cy="{y}" r="{size:.1f}" fill="{color}" opacity="{opacity:.2f}" filter="url(#softGlow)"/>')
    
    # 火焰上升粒子
    for i in range(80):
        x = random.uniform(80, 432)
        y = random.uniform(250, 520)
        size = random.uniform(2, 7)
        opacity = random.uniform(0.2, 0.6)
        color = random.choice(color_scheme["flame_colors"])
        particles.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" opacity="{opacity:.2f}"/>')
    
    # 周围氛围粒子
    for i in range(70):
        angle = random.uniform(0, 6.28)
        r = random.uniform(120, 240)
        x = int(256 + r * 0.9)
        y = int(280 + r * 0.8)
        size = random.uniform(1, 5)
        opacity = random.uniform(0.1, 0.4)
        color = random.choice(color_scheme["colors"])
        particles.append(f'<circle cx="{x}" cy="{y}" r="{size:.1f}" fill="{color}" opacity="{opacity:.2f}"/>')
    
    # 核心高光
    for _ in range(20):
        x = random.uniform(220, 292)
        y = random.uniform(130, 240)
        size = random.uniform(8, 18)
        color = color_scheme["highlight"]
        particles.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{size:.1f}" fill="{color}" filter="url(#glow)"/>')
    
    lines.append('<g filter="url(#glow)">')
    lines.extend(particles)
    lines.append('</g>')
    lines.append(f'<rect width="512" height="512" rx="48" fill="none" stroke="{color_scheme["border"]}" stroke-width="2"/>')
    lines.append('</svg>')
    return '\n'.join(lines)

schemes = {
    'flame': {
        'bg_center': '#1a0800', 'bg_edge': '#050200',
        'glow': 'rgba(255,80,0,0.06)',
        'colors': ['#ff2400', '#ff4500', '#ff6b35', '#ff8c00', '#ffa500', '#ffd700', '#ffe066', '#fff8dc'],
        'wing_colors': ['#ff4500', '#ff6b35', '#ff8c00', '#ffa500', '#ffd700'],
        'tail_colors': ['#ff8c00', '#ffa500', '#ffd700', '#ffe066', '#fff8dc'],
        'flame_colors': ['#ff4500', '#ff6b35', '#ff8c00', '#ffd700'],
        'highlight': '#fff4a0', 'border': 'rgba(255,140,0,0.2)'
    },
    'neon': {
        'bg_center': '#0a001a', 'bg_edge': '#05000a',
        'glow': 'rgba(124,58,237,0.06)',
        'colors': ['#4c1d95', '#5b21b6', '#6d28d9', '#7c3aed', '#8b5cf6', '#a78bfa', '#c084fc', '#e9d5ff'],
        'wing_colors': ['#7c3aed', '#8b5cf6', '#a78bfa', '#c084fc', '#e9d5ff'],
        'tail_colors': ['#a78bfa', '#c084fc', '#e9d5ff', '#f5f3ff'],
        'flame_colors': ['#8b5cf6', '#a78bfa', '#c084fc', '#e9d5ff'],
        'highlight': '#f5f3ff', 'border': 'rgba(124,58,237,0.2)'
    },
    'emerald': {
        'bg_center': '#001a0a', 'bg_edge': '#000a05',
        'glow': 'rgba(52,211,153,0.06)',
        'colors': ['#064e3b', '#065f46', '#059669', '#10b981', '#34d399', '#6ee7b7', '#a7f3d0', '#d1fae5'],
        'wing_colors': ['#059669', '#10b981', '#34d399', '#6ee7b7', '#a7f3d0'],
        'tail_colors': ['#34d399', '#6ee7b7', '#a7f3d0', '#d1fae5'],
        'flame_colors': ['#10b981', '#34d399', '#6ee7b7', '#a7f3d0'],
        'highlight': '#ecfdf5', 'border': 'rgba(52,211,153,0.2)'
    }
}

os.makedirs('D:/workspace/pea/assets/icons', exist_ok=True)
for fname, scheme in [('icon-1-pea-pod.svg', schemes['flame']), ('icon-2-abstract.svg', schemes['neon']), ('icon-3-minimal.svg', schemes['emerald'])]:
    svg = generate_phoenix(scheme, fname)
    with open(f'D:/workspace/pea/assets/icons/{fname}', 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'{fname}: {len(svg)} bytes')
