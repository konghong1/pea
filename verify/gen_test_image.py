import zlib, struct

def make_png(path, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter type 0 (None)
        for x in range(w):
            t = y / h
            r = int(31 + (139 - 31) * t)
            g = int(162 + (92 - 162) * t)
            b = int(220 + (246 - 220) * t)
            raw += bytes((r, g, b))
    comp = zlib.compress(bytes(raw), 9)
    def chunk(typ, data):
        return struct.pack('>I', len(data)) + typ + data + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', comp)
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)
    print('wrote', path, w, 'x', h)

make_png(r'D:/workspace/pea/pea-server/web/public/e2e-test.png', 400, 300)
