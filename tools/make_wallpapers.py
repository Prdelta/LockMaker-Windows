#!/usr/bin/env python3
"""
Genera los wallpapers incluidos (originales, procedurales, sin derechos de terceros).
Ejecuta:  python tools/make_wallpapers.py [--size 2560x1440]
Salida:   wallpapers/*.jpg  y  wallpapers/thumbs/*.jpg
"""
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "wallpapers")
THUMBS = os.path.join(OUT, "thumbs")
W, H = 2560, 1440
if len(sys.argv) > 2 and sys.argv[1] == "--size":
    W, H = map(int, sys.argv[2].lower().split("x"))


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(stops, w=W, h=H, angle=0):
    """Degradado lineal con paradas [(pos, color)], generado a baja resolución y escalado."""
    sw, sh = 32, 256
    im = Image.new("RGB", (sw, sh))
    px = im.load()
    for y in range(sh):
        t = y / (sh - 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                c = lerp(c0, c1, (t - p0) / max(1e-6, p1 - p0))
                break
        for x in range(sw):
            px[x, y] = c
    if angle:
        # cuadrado mayor que la diagonal, rotar y recortar el centro (sin esquinas negras)
        D = int(math.hypot(w, h)) + 4
        im = im.resize((D, D), Image.BILINEAR).rotate(angle, resample=Image.BILINEAR, expand=False)
        im = im.crop(((D - w) // 2, (D - h) // 2, (D - w) // 2 + w, (D - h) // 2 + h))
    else:
        im = im.resize((w, h), Image.BILINEAR)
    return im


def blob(base, cx, cy, r, color, alpha=0.9):
    layer = Image.new("RGB", base.size, (0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.55))
    return ImageChops.add(base, layer.point(lambda p: int(p * alpha)))


def noise_clouds(w, h, seed, scale=6, octaves=4):
    """Nubes suaves: ruido a muy baja resolución (celdas grandes) escalado con bicúbico."""
    random.seed(seed)
    acc = Image.new("L", (w, h), 0)
    amp = 128
    for o in range(octaves):
        cells = scale * (2 ** o)                  # nº de celdas por ancho
        n = Image.effect_noise((max(2, cells), max(2, cells * h // w)), 80)
        n = n.filter(ImageFilter.GaussianBlur(0.6)).resize((w, h), Image.BICUBIC)
        acc = ImageChops.add(acc, n.point(lambda p, a=amp: int(p * a / 255)))
        amp //= 2
    return acc.filter(ImageFilter.GaussianBlur(3))


def colorize(mask, dark, light):
    r = mask.point(lambda p: int(dark[0] + (light[0] - dark[0]) * p / 255))
    g = mask.point(lambda p: int(dark[1] + (light[1] - dark[1]) * p / 255))
    b = mask.point(lambda p: int(dark[2] + (light[2] - dark[2]) * p / 255))
    return Image.merge("RGB", (r, g, b))


# ------------------------------------------------------------------ diseños
def aurora():
    im = vgrad([(0, (8, 6, 24)), (0.5, (16, 10, 48)), (1, (6, 4, 18))])
    im = blob(im, W * 0.25, H * 0.35, H * 0.55, (60, 20, 140), 0.8)
    im = blob(im, W * 0.75, H * 0.30, H * 0.5, (10, 90, 160), 0.8)
    im = blob(im, W * 0.55, H * 0.85, H * 0.5, (0, 120, 110), 0.6)
    return im


def nebula():
    m = noise_clouds(W, H, seed=7, scale=3)
    im = colorize(m, (6, 4, 20), (120, 60, 170))
    m2 = noise_clouds(W, H, seed=21, scale=2).point(lambda p: max(0, p - 110) * 2)
    im = ImageChops.add(im, colorize(m2, (0, 0, 0), (20, 110, 200)).point(lambda p: int(p * 0.7)))
    # estrellas
    d = ImageDraw.Draw(im)
    random.seed(3)
    for _ in range(900):
        x, y = random.randrange(W), random.randrange(H)
        s = random.choice([1, 1, 1, 2, 2, 3])
        c = random.randrange(150, 255)
        d.ellipse([x, y, x + s, y + s], fill=(c, c, 255))
    return im


def dunes():
    im = vgrad([(0, (18, 12, 40)), (1, (70, 30, 90))])
    d = ImageDraw.Draw(im)
    cols = [(45, 25, 80), (80, 40, 120), (130, 60, 150), (200, 90, 150)]
    for i, c in enumerate(cols):
        pts = []
        for x in range(0, W + 40, 40):
            y = H * (0.45 + 0.13 * i) + math.sin(x / (380 + 90 * i) + i * 1.7) * 70 + math.sin(x / 130 + i) * 20
            pts.append((x, y))
        pts += [(W, H), (0, H)]
        d.polygon(pts, fill=c)
    return im.filter(ImageFilter.GaussianBlur(0.7))


def geometric():
    im = vgrad([(0, (12, 14, 22)), (1, (22, 26, 40))])
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    random.seed(11)
    for i in range(14):
        x = random.uniform(-0.2, 1.0) * W
        w = random.uniform(0.12, 0.35) * W
        a = random.randrange(10, 40)
        c = random.choice([(90, 120, 255, a), (120, 90, 255, a), (60, 200, 220, a)])
        d.polygon([(x, 0), (x + w, 0), (x + w - H * 0.6, H), (x - H * 0.6, H)], fill=c)
    im = Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")
    return blob(im, W * 0.7, H * 0.25, H * 0.45, (40, 60, 160), 0.5)


def midnight():
    im = vgrad([(0, (3, 6, 28)), (0.7, (10, 22, 70)), (1, (30, 60, 110))])
    d = ImageDraw.Draw(im)
    random.seed(5)
    for _ in range(1400):
        x, y = random.randrange(W), random.randrange(int(H * 0.8))
        s = random.choice([1, 1, 1, 2, 2, 3])
        c = random.randrange(120, 255)
        d.ellipse([x, y, x + s, y + s], fill=(c, c, min(255, c + 30)))
    # montañas
    ld = ImageDraw.Draw(im)
    for i, c in enumerate([(14, 24, 60), (8, 14, 40), (4, 8, 26)]):
        pts = [(x, H * (0.68 + 0.08 * i) + math.sin(x / (300 - 60 * i) + i) * 60 + math.sin(x / 90) * 15)
               for x in range(0, W + 20, 20)] + [(W, H), (0, H)]
        ld.polygon(pts, fill=c)
    return blob(im, W * 0.5, H * 0.72, H * 0.5, (20, 40, 110), 0.5)


def sunset():
    im = vgrad([(0, (40, 10, 70)), (0.45, (190, 60, 110)), (0.7, (255, 140, 90)), (1, (60, 20, 60))])
    im = blob(im, W * 0.5, H * 0.66, H * 0.22, (255, 200, 120), 0.9)
    d = ImageDraw.Draw(im)
    d.rectangle([0, H * 0.7, W, H], fill=(28, 10, 40))
    for i in range(12):
        y = H * 0.7 + i * (H * 0.3 / 12)
        d.rectangle([0, y, W, y + 2], fill=lerp((120, 50, 90), (28, 10, 40), i / 12))
    return im.filter(ImageFilter.GaussianBlur(0.6))


def mesh():
    im = vgrad([(0, (10, 10, 22)), (1, (14, 12, 30))])
    for cx, cy, r, c in [(0.15, 0.2, 0.6, (120, 40, 200)), (0.85, 0.25, 0.55, (0, 110, 230)),
                         (0.5, 0.8, 0.6, (230, 60, 120)), (0.9, 0.9, 0.4, (0, 200, 170))]:
        im = blob(im, W * cx, H * cy, H * r, c, 0.75)
    return im


def mono_grid():
    im = vgrad([(0, (16, 16, 18)), (1, (24, 24, 28))])
    d = ImageDraw.Draw(im)
    step = 96
    for x in range(0, W, step):
        d.line([(x, 0), (x, H)], fill=(34, 34, 40), width=1)
    for y in range(0, H, step):
        d.line([(0, y), (W, y)], fill=(34, 34, 40), width=1)
    return blob(im, W * 0.5, H * 0.45, H * 0.6, (70, 70, 90), 0.5)


def ocean():
    im = vgrad([(0, (0, 40, 70)), (0.6, (0, 90, 120)), (1, (0, 20, 40))])
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    random.seed(9)
    for i in range(9):
        x = random.uniform(0.2, 0.8) * W
        w = random.uniform(40, 140)
        d.polygon([(x, 0), (x + w, 0), (x + w + 500, H), (x - 100, H)], fill=(40, 90, 110))
    layer = layer.filter(ImageFilter.GaussianBlur(60))
    im = ImageChops.add(im, layer.point(lambda p: p // 2))
    return blob(im, W * 0.5, -H * 0.2, H * 0.7, (90, 180, 200), 0.5)


def forest_fog():
    im = vgrad([(0, (200, 210, 215)), (1, (120, 135, 140))])
    ld = ImageDraw.Draw(im)
    random.seed(4)
    cols = [(150, 165, 170), (110, 128, 135), (70, 90, 100), (35, 50, 60)]
    for i, c in enumerate(cols):
        pts = []
        x = 0
        while x < W + 40:
            peak = H * (0.45 + 0.13 * i) + random.uniform(-80, 80) - math.sin(x / 500 + i) * 60
            pts.append((x, peak))
            x += random.uniform(25, 60)
        pts += [(W, H), (0, H)]
        ld.polygon(pts, fill=c)
    fog = vgrad([(0, (0, 0, 0)), (0.55, (0, 0, 0)), (1, (160, 170, 175))])
    return ImageChops.add(im, fog.point(lambda p: p // 2))


def ember():
    im = vgrad([(0, (10, 6, 6)), (1, (40, 12, 8))])
    m = noise_clouds(W, H, seed=33, scale=3).point(lambda p: max(0, p - 120) * 2)
    im = ImageChops.add(im, colorize(m, (0, 0, 0), (255, 110, 30)).point(lambda p: int(p * 0.8)))
    return blob(im, W * 0.5, H * 1.05, H * 0.6, (255, 90, 20), 0.5)


def sakura():
    im = vgrad([(0, (255, 200, 215)), (0.5, (250, 170, 200)), (1, (120, 60, 110))])
    im = blob(im, W * 0.3, H * 0.3, H * 0.5, (255, 240, 245), 0.4)
    d = ImageDraw.Draw(im)
    random.seed(8)
    for _ in range(260):
        x, y = random.randrange(W), random.randrange(H)
        r = random.randrange(3, 14)
        c = random.choice([(255, 215, 230), (250, 185, 210), (230, 140, 180)])
        d.ellipse([x, y, x + r, y + r * 0.7], fill=c)
    return im.filter(ImageFilter.GaussianBlur(0.8))


DESIGNS = {
    "01 Aurora": aurora, "02 Nebulosa": nebula, "03 Dunas": dunes, "04 Geometrico": geometric,
    "05 Medianoche": midnight, "06 Atardecer": sunset, "07 Mesh": mesh, "08 Grid mono": mono_grid,
    "09 Oceano": ocean, "10 Niebla": forest_fog, "11 Brasa": ember, "12 Sakura": sakura,
}


def main():
    os.makedirs(THUMBS, exist_ok=True)
    for name, fn in DESIGNS.items():
        im = fn().convert("RGB")
        im = Image.blend(im, ImageChops.overlay(im, Image.effect_noise(im.size, 5).convert("RGB")), 0.25)  # grano fino
        im.save(os.path.join(OUT, name + ".jpg"), "JPEG", quality=86, optimize=True, progressive=True)
        im.resize((480, 270), Image.LANCZOS).save(os.path.join(THUMBS, name + ".jpg"), "JPEG", quality=78)
        print("ok", name, os.path.getsize(os.path.join(OUT, name + ".jpg")) // 1024, "KB")




# ------------------------------------------------------------------ serie "Iris" (paleta de la referencia)
def iris_blue():
    """Iris cristalino azul: anillos radiales, facetas y brillo, como el ojo de la referencia."""
    im = vgrad([(0, (20, 18, 60)), (1, (6, 6, 24))])
    cx, cy, R = W * 0.62, H * 0.5, H * 0.62
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    random.seed(12)
    # rayos radiales
    for i in range(520):
        a = random.uniform(0, math.tau)
        r0, r1 = R * random.uniform(0.28, 0.5), R * random.uniform(0.6, 1.05)
        c = random.choice([(40, 80, 255), (90, 140, 255), (20, 200, 220), (150, 170, 255), (255, 255, 255)])
        w = random.randrange(2, 9)
        d.line([(cx + math.cos(a) * r0, cy + math.sin(a) * r0), (cx + math.cos(a) * r1, cy + math.sin(a) * r1)], fill=c, width=w)
    layer = layer.filter(ImageFilter.GaussianBlur(4))
    # facetas (polígonos translúcidos)
    fac = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fac)
    for i in range(70):
        a = random.uniform(0, math.tau)
        r = R * random.uniform(0.35, 0.95)
        px, py = cx + math.cos(a) * r, cy + math.sin(a) * r
        s = random.uniform(40, 160)
        pts = [(px + math.cos(a + k) * s * random.uniform(0.4, 1), py + math.sin(a + k) * s * random.uniform(0.4, 1))
               for k in (0, 1.2, 2.5, 4.1, 5.3)]
        fd.polygon(pts, fill=random.choice([(120, 200, 255, 40), (40, 90, 255, 55), (60, 230, 230, 35), (255, 255, 255, 25)]))
    fac = fac.filter(ImageFilter.GaussianBlur(3))
    im = ImageChops.add(im, layer.point(lambda p: int(p * 0.85)))
    im = Image.alpha_composite(im.convert("RGBA"), fac).convert("RGB")
    # pupila y anillo
    d = ImageDraw.Draw(im)
    pup = Image.new("L", (W, H), 0)
    ImageDraw.Draw(pup).ellipse([cx - R * 0.27, cy - R * 0.27, cx + R * 0.27, cy + R * 0.27], fill=255)
    pup = pup.filter(ImageFilter.GaussianBlur(10))
    im.paste(Image.new("RGB", (W, H), (6, 6, 34)), mask=pup)
    d.ellipse([cx - R * 0.27, cy - R * 0.27, cx + R * 0.27, cy + R * 0.27], outline=(90, 140, 255), width=4)
    im = im.filter(ImageFilter.GaussianBlur(0.8))
    im = blob(im, cx - R * 0.12, cy - R * 0.14, R * 0.09, (255, 255, 255), 0.9)   # reflejo
    im = blob(im, cx, cy, R * 0.9, (30, 60, 200), 0.35)
    return im


def bokeh_violet():
    im = vgrad([(0, (40, 20, 90)), (0.5, (70, 40, 160)), (1, (20, 60, 140))], angle=20)
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    random.seed(19)
    for _ in range(90):
        x, y = random.randrange(W), random.randrange(H)
        r = random.uniform(18, 120)
        c = random.choice([(120, 140, 255), (200, 120, 255), (80, 220, 255), (255, 255, 255)])
        a = random.uniform(0.15, 0.6)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(int(v * a) for v in c))
    layer = layer.filter(ImageFilter.GaussianBlur(9))
    return ImageChops.add(im, layer)


def crystal_shards():
    im = vgrad([(0, (8, 10, 40)), (1, (30, 20, 80))], angle=35)
    fac = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fac)
    random.seed(23)
    for _ in range(160):
        x, y = random.uniform(-0.1, 1.1) * W, random.uniform(-0.1, 1.1) * H
        L, a = random.uniform(120, 520), random.uniform(-0.9, -0.4)
        w = random.uniform(10, 60)
        pts = [(x, y), (x + math.cos(a) * L, y + math.sin(a) * L),
               (x + math.cos(a) * L + math.cos(a + 1.57) * w, y + math.sin(a) * L + math.sin(a + 1.57) * w),
               (x + math.cos(a + 1.57) * w, y + math.sin(a + 1.57) * w)]
        fd.polygon(pts, fill=random.choice([(90, 160, 255, 60), (40, 230, 230, 45), (170, 120, 255, 55), (255, 255, 255, 30)]))
    im = Image.alpha_composite(im.convert("RGBA"), fac).convert("RGB")
    return blob(im, W * 0.7, H * 0.4, H * 0.5, (40, 120, 255), 0.45)


def strands():
    """Mechones fluidos azul/violeta (como el cabello de la referencia)."""
    im = vgrad([(0, (60, 40, 140)), (0.5, (40, 60, 200)), (1, (10, 20, 70))], angle=-25)
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    random.seed(31)
    for i in range(70):
        x0, y0 = random.uniform(-0.2, 1.2) * W, random.uniform(-0.3, 0.2) * H
        pts, x, y = [], x0, y0
        dx, dy = random.uniform(-0.6, 0.6), 1.0
        for k in range(40):
            pts.append((x, y))
            dx += random.uniform(-0.08, 0.08) + math.sin(k / 6 + i) * 0.03
            x += dx * 40
            y += dy * 40
        c = random.choice([(90, 100, 255), (150, 110, 255), (30, 60, 200), (200, 220, 255), (60, 200, 240)])
        d.line(pts, fill=tuple(int(v * random.uniform(0.25, 0.7)) for v in c), width=random.randrange(14, 70), joint="curve")
    layer = layer.filter(ImageFilter.GaussianBlur(14))
    im = ImageChops.add(im, layer)
    return blob(im, W * 0.75, H * 0.35, H * 0.4, (120, 200, 255), 0.35)


DESIGNS.update({"13 Iris azul": iris_blue, "14 Bokeh violeta": bokeh_violet,
                "15 Cristales": crystal_shards, "16 Mechones": strands})

if __name__ == "__main__":
    main()
