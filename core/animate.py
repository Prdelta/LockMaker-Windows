"""
LockMaker - animación.

Genera fondos animados (GIF / MP4 / WebM) con el overlay encima:
  * entrada: imagen fija, GIF/WebP animado, o un fondo procedural animado
  * efectos en bucle perfecto: Ken Burns (zoom/paneo), punto de la barra en
    movimiento, pulso del título, partículas (bokeh / nieve / lluvia / estrellas)
  * salida: GIF (solo Pillow) y MP4/WebM (si hay ffmpeg en el sistema)

Todo el bucle usa t ∈ [0,1): el último fotograma enlaza con el primero.
"""
from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, asdict

from PIL import Image, ImageDraw, ImageFilter, ImageSequence

from .render import Style, render, _base_cache  # noqa: F401


@dataclass
class Anim:
    seconds: float = 6.0
    fps: int = 15
    kenburns: float = 0.05      # 0 = sin zoom; 0.05 = 5 % de zoom máximo
    bar: bool = True            # punto de la barra recorre la línea
    pulse: float = 0.25         # 0..1 pulso de opacidad/glow del texto
    particles: str = "none"     # none | bokeh | snow | rain | stars
    density: float = 1.0
    out_w: int = 1280           # resolución de salida (más pequeña = GIF más ligero)
    out_h: int = 720
    colors: int = 256           # paleta GIF

    @staticmethod
    def from_dict(d: dict) -> "Anim":
        a = Anim()
        for k, v in (d or {}).items():
            if hasattr(a, k):
                cur = getattr(a, k)
                try:
                    v = (v in (True, "true", 1, "1")) if isinstance(cur, bool) else type(cur)(v)
                except (TypeError, ValueError):
                    continue
                setattr(a, k, v)
        a.fps = max(2, min(30, a.fps))
        a.seconds = max(1.0, min(30.0, a.seconds))
        return a

    def to_dict(self):
        return asdict(self)


# ----------------------------------------------------------------------------
# Entrada
# ----------------------------------------------------------------------------
def load_frames(path: str, max_frames: int = 120):
    """Devuelve (frames RGB, duraciones ms). Para imágenes fijas: 1 frame."""
    im = Image.open(path)
    frames, durs = [], []
    n = getattr(im, "n_frames", 1)
    if n <= 1:
        return [im.convert("RGB")], [0]
    step = max(1, math.ceil(n / max_frames))
    for i, fr in enumerate(ImageSequence.Iterator(im)):
        if i % step:
            continue
        frames.append(fr.convert("RGB"))
        durs.append(int(fr.info.get("duration", 80)) * step)
    return frames, durs


def is_animated(path: str) -> bool:
    try:
        return getattr(Image.open(path), "n_frames", 1) > 1
    except Exception:
        return False


# ----------------------------------------------------------------------------
# Partículas (en bucle: posición = f(t) con envoltura)
# ----------------------------------------------------------------------------
def _particles_layer(kind: str, w: int, h: int, t: float, density: float, seed: int = 7) -> Image.Image:
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    u = h / 1080.0
    if kind == "bokeh":
        n = int(60 * density)
        for i in range(n):
            x0, y0 = rnd.random(), rnd.random()
            r = rnd.uniform(14, 70) * u
            spd = rnd.uniform(0.3, 1.0)
            y = (y0 - t * spd * 0.25) % 1.0
            x = (x0 + math.sin((t + x0) * math.tau) * 0.01) % 1.0
            a = int(90 * (0.5 + 0.5 * math.sin((t * 2 + x0) * math.tau)))
            c = rnd.choice([(255, 255, 255), (170, 190, 255), (255, 200, 240), (160, 240, 255)])
            d.ellipse([x * w - r, y * h - r, x * w + r, y * h + r], fill=c + (a,))
        layer = layer.filter(ImageFilter.GaussianBlur(6 * u))
    elif kind == "snow":
        n = int(220 * density)
        for i in range(n):
            x0, y0 = rnd.random(), rnd.random()
            r = rnd.uniform(1.5, 5) * u
            spd = rnd.uniform(0.5, 1.5)
            y = (y0 + t * spd * 0.3) % 1.0
            x = (x0 + math.sin((t * 3 + y0) * math.tau) * 0.012) % 1.0
            d.ellipse([x * w - r, y * h - r, x * w + r, y * h + r], fill=(255, 255, 255, int(200 * (1.5 - spd / 1.5))))
        layer = layer.filter(ImageFilter.GaussianBlur(1.2 * u))
    elif kind == "rain":
        n = int(260 * density)
        for i in range(n):
            x0, y0 = rnd.random(), rnd.random()
            spd = rnd.uniform(1.0, 2.0)
            ln = rnd.uniform(18, 40) * u
            y = (y0 + t * spd * 0.5) % 1.0
            x = (x0 - t * 0.08 * spd) % 1.0
            d.line([(x * w, y * h), (x * w - ln * 0.18, y * h + ln)], fill=(220, 230, 255, int(110 * spd / 2)), width=max(1, int(1.5 * u)))
    elif kind == "stars":
        n = int(300 * density)
        for i in range(n):
            x0, y0 = rnd.random(), rnd.random() * 0.85
            r = rnd.uniform(0.8, 2.6) * u
            ph = rnd.random()
            a = int(255 * (0.35 + 0.65 * (0.5 + 0.5 * math.sin((t * 2 + ph) * math.tau))))
            d.ellipse([x0 * w - r, y0 * h - r, x0 * w + r, y0 * h + r], fill=(255, 255, 255, a))
    return layer


# ----------------------------------------------------------------------------
# Fondos animados procedurales (sin imagen de entrada)
# ----------------------------------------------------------------------------
def procedural_frames(name: str, w: int, h: int, n: int):
    """Genera n fotogramas RGB en bucle. name: aurora | mesh | waves"""
    frames = []
    for i in range(n):
        t = i / n
        if name == "aurora":
            im = Image.new("RGB", (w, h), (8, 6, 26))
            blobs = [((0.25 + 0.08 * math.sin(t * math.tau)), 0.35, 0.55, (60, 20, 140)),
                     ((0.75 + 0.06 * math.cos(t * math.tau)), 0.3, 0.5, (10, 90, 160)),
                     (0.55, (0.85 + 0.05 * math.sin(t * math.tau * 2)), 0.5, (0, 120, 110))]
            for cx, cy, r, c in blobs:
                im = _blob(im, w * cx, h * cy, h * r, c)
        elif name == "mesh":
            im = Image.new("RGB", (w, h), (10, 10, 22))
            for k, (cx, cy, r, c) in enumerate([(0.15, 0.2, 0.6, (120, 40, 200)), (0.85, 0.25, 0.55, (0, 110, 230)),
                                                 (0.5, 0.8, 0.6, (230, 60, 120)), (0.9, 0.9, 0.4, (0, 200, 170))]):
                dx = 0.07 * math.sin((t + k * 0.25) * math.tau)
                dy = 0.05 * math.cos((t + k * 0.25) * math.tau)
                im = _blob(im, w * (cx + dx), h * (cy + dy), h * r, c)
        else:  # waves
            im = Image.new("RGB", (w, h), (18, 12, 40))
            d = ImageDraw.Draw(im)
            cols = [(45, 25, 80), (80, 40, 120), (130, 60, 150), (200, 90, 150)]
            for k, c in enumerate(cols):
                pts = [(x, h * (0.45 + 0.13 * k) + math.sin(x / (w / 7) + k * 1.7 + t * math.tau * (1 + k % 2)) * h * 0.05)
                       for x in range(0, w + 40, 40)] + [(w, h), (0, h)]
                d.polygon(pts, fill=c)
        frames.append(im)
    return frames


def _blob(base, cx, cy, r, color, alpha=0.8):
    from PIL import ImageChops
    layer = Image.new("RGB", base.size, (0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.55))
    return ImageChops.add(base, layer.point(lambda p: int(p * alpha)))


PROCEDURAL = {"Aurora animada": "aurora", "Mesh animado": "mesh", "Olas animadas": "waves"}


# ----------------------------------------------------------------------------
# Render de la animación
# ----------------------------------------------------------------------------
def _kenburns(img: Image.Image, t: float, amount: float, w: int, h: int) -> Image.Image:
    """Zoom/paneo suave en ida y vuelta (bucle perfecto)."""
    k = 0.5 - 0.5 * math.cos(t * math.tau)          # 0→1→0
    z = 1.0 + amount * k
    iw, ih = img.size
    cw, ch = iw / z, ih / z
    cx = iw / 2 + (iw - cw) / 2 * 0.6 * math.sin(t * math.tau)
    cy = ih / 2 + (ih - ch) / 2 * 0.3 * math.cos(t * math.tau)
    box = (int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2))
    return img.crop(box)


def build_frames(src_frames, src_durs, style: dict, anim: Anim, progress=None):
    """Devuelve (frames RGB, duración ms por frame)."""
    st = Style.from_dict(style)
    st.width, st.height = anim.out_w, anim.out_h
    n = max(2, int(anim.seconds * anim.fps))
    dur = int(1000 / anim.fps)
    animated_src = len(src_frames) > 1
    if animated_src:
        total = sum(src_durs) or len(src_frames) * 80
        # recorre el GIF de entrada completo en los n frames (bucle natural)
        n = max(n, len(src_frames))
    out = []
    base_style = Style.from_dict(style)
    for i in range(n):
        t = i / n
        if animated_src:
            # fotograma de origen proporcional al tiempo
            idx = int(t * len(src_frames)) % len(src_frames)
            bg = src_frames[idx]
        else:
            bg = src_frames[0]
        if anim.kenburns > 0:
            bg = _kenburns(bg, t, anim.kenburns, anim.out_w, anim.out_h)
        s = Style.from_dict(base_style.to_dict())
        s.width, s.height = anim.out_w, anim.out_h
        if anim.bar:
            s.bar_progress = t
        if anim.pulse > 0:
            k = 0.5 + 0.5 * math.sin(t * math.tau * 2)
            s.opacity = max(0.2, min(1.0, s.opacity * (1 - anim.pulse * 0.35 * (1 - k))))
            s.glow = min(1.0, s.glow + anim.pulse * 0.4 * k)
        fr = render(bg, s)
        if anim.particles != "none":
            layer = _particles_layer(anim.particles, anim.out_w, anim.out_h, t, anim.density)
            if anim.particles in ("bokeh", "stars"):
                # mezcla aditiva: las luces brillan en vez de verse grises
                from PIL import ImageChops
                rgb = Image.new("RGB", layer.size, (0, 0, 0))
                rgb.paste(layer.convert("RGB"), mask=layer.getchannel("A"))
                fr = ImageChops.add(fr, rgb)
            else:
                fr = Image.alpha_composite(fr.convert("RGBA"), layer).convert("RGB")
        out.append(fr)
        if progress:
            progress(i + 1, n)
        if len(_base_cache) > 2:   # evita que la caché de fondos crezca con los crops
            _base_cache.clear()
    return out, [dur] * n


# ----------------------------------------------------------------------------
# Salida
# ----------------------------------------------------------------------------
def save_gif(frames, durs, path: str, colors: int = 256):
    # paleta global calculada sobre varios fotogramas (evita parpadeo de colores)
    w, h = frames[0].size
    picks = [frames[int(i * (len(frames) - 1) / 3)] for i in range(4)]
    sheet = Image.new("RGB", (w * 2, h * 2))
    for i, f in enumerate(picks):
        sheet.paste(f, ((i % 2) * w, (i // 2) * h))
    pal = sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(colors=colors, palette=pal, dither=Image.Dither.FLOYDSTEINBERG) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=durs, loop=0, optimize=True, disposal=0)
    return path


def ffmpeg_path():
    return shutil.which("ffmpeg")


def save_video(frames, fps: int, path: str, fmt: str = "mp4"):
    """MP4 (H.264) o WebM (VP9) con ffmpeg. Devuelve None si no hay ffmpeg."""
    ff = ffmpeg_path()
    if not ff:
        return None
    tmp = tempfile.mkdtemp(prefix="lockmaker_")
    try:
        for i, f in enumerate(frames):
            f.save(os.path.join(tmp, f"f{i:05d}.png"), compress_level=1)
        w, h = frames[0].size
        w, h = w - w % 2, h - h % 2
        vf = f"scale={w}:{h}"
        if fmt == "webm":
            codec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-pix_fmt", "yuv420p"]
        else:
            codec = ["-c:v", "libx264", "-crf", "22", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        cmd = [ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(tmp, "f%05d.png"),
               "-vf", vf, *codec, "-an", path]
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise OSError(r.stderr.strip()[:300])
        return path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
