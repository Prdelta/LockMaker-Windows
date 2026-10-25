"""
LockMaker - motor de renderizado.

Compone una imagen de fondo con un overlay tipo "reproductor":
    S A T U R D A Y
    05 APRIL, 2025.
       - 13:27 -
    00:00 •───────────── -00:00
         ◁◁   ▷   ▷▷

Todo se dibuja con Pillow (la única dependencia externa). Sin tipografías
del sistema: se usan las fuentes OFL incluidas en /fonts.
"""
from __future__ import annotations

import datetime as _dt
import io
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "fonts")

FONTS = {
    "light": os.path.join(FONT_DIR, "Poppins-Light.ttf"),
    "regular": os.path.join(FONT_DIR, "Poppins-Regular.ttf"),
    "medium": os.path.join(FONT_DIR, "Poppins-Medium.ttf"),
}

DAYS = {
    "en": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"],
    "es": ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"],
}
MONTHS = {
    "en": ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
           "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"],
    "es": ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
           "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"],
}


@dataclass
class Style:
    """Todos los parámetros del overlay. Serializable a JSON (presets)."""
    # Lienzo
    width: int = 1920
    height: int = 1080
    fit: str = "cover"            # cover | contain | stretch
    bg_color: str = "#0b0b14"     # relleno cuando fit=contain
    blur: float = 0.0             # desenfoque del fondo (px, escala 1080p)
    dim: float = 0.0              # oscurecer fondo 0..1
    vignette: float = 0.0         # viñeta 0..1

    # Posición y escala del bloque (porcentaje del lienzo)
    x: float = 52.0               # centro horizontal del bloque
    y: float = 9.0                # borde superior del bloque
    scale: float = 1.0            # multiplicador general
    width_pct: float = 20.0       # ancho de la barra de progreso (% del lienzo)

    # Textos
    title: str = "auto"           # "auto" => día de la semana; o texto fijo
    date: str = "auto"            # "auto" => fecha actual; o texto fijo
    time: str = "auto"            # "auto" => hora actual; o texto fijo (ej. 13:27)
    lang: str = "en"              # en | es   (para auto)
    date_format: str = "{d:02d} {M}, {Y}."   # {d} {M} {Y} {m} {D}
    time_format: str = "- {H}:{i} -"         # {H} {i} {s} {h} {p}
    uppercase: bool = True

    # Tipografía
    font_title: str = "light"
    title_size: float = 1.0       # multiplicadores finos por elemento
    title_spacing: float = 0.55   # tracking del título (fracción del tamaño)
    date_spacing: float = 0.14
    time_spacing: float = 0.04

    # Colores / efectos
    color: str = "#ffffff"
    opacity: float = 1.0
    shadow: float = 0.35          # intensidad de sombra suave 0..1
    glow: float = 0.0             # resplandor 0..1

    # Elementos visibles
    show_title: bool = True
    show_date: bool = True
    show_time: bool = True
    show_bar: bool = True
    show_controls: bool = True
    bar_left: str = "00:00"
    bar_right: str = "-00:00"
    bar_progress: float = 0.0     # 0..1 posición del punto

    @staticmethod
    def from_dict(d: dict) -> "Style":
        s = Style()
        for k, v in (d or {}).items():
            if hasattr(s, k):
                cur = getattr(s, k)
                try:
                    if isinstance(cur, bool):
                        v = v in (True, "true", "True", 1, "1", "on")
                    elif isinstance(cur, int) and not isinstance(cur, bool):
                        v = int(float(v))
                    elif isinstance(cur, float):
                        v = float(v)
                    elif isinstance(cur, str):
                        v = str(v)
                except (TypeError, ValueError):
                    continue
                setattr(s, k, v)
        return s

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------
_font_cache: dict = {}


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key not in _font_cache:
        path = FONTS.get(kind, FONTS["light"])
        _font_cache[key] = ImageFont.truetype(path, max(4, int(size)))
    return _font_cache[key]


def _hex(c: str, alpha: float = 1.0):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (r, g, b, int(255 * max(0.0, min(1.0, alpha))))


def _text_width(font, text: str, spacing: float) -> float:
    if not text:
        return 0.0
    w = sum(font.getlength(ch) for ch in text)
    return w + spacing * (len(text) - 1)


def _draw_spaced(draw: ImageDraw.ImageDraw, cx: float, y: float, text: str,
                 font, spacing: float, fill):
    """Dibuja texto centrado en cx con tracking personalizado."""
    total = _text_width(font, text, spacing)
    x = cx - total / 2
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + spacing
    return total


def _fit_background(img: Image.Image, w: int, h: int, mode: str, bg) -> Image.Image:
    img = img.convert("RGB")
    iw, ih = img.size
    if mode == "stretch":
        return img.resize((w, h), Image.LANCZOS)
    ratio = max(w / iw, h / ih) if mode == "cover" else min(w / iw, h / ih)
    nw, nh = max(1, round(iw * ratio)), max(1, round(ih * ratio))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), bg[:3])
    canvas.paste(img, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def _auto_texts(st: Style, now: Optional[_dt.datetime] = None):
    now = now or _dt.datetime.now()
    lang = st.lang if st.lang in DAYS else "en"
    title = st.title
    if title.strip().lower() == "auto":
        title = DAYS[lang][now.weekday()]
    date = st.date
    if date.strip().lower() == "auto":
        try:
            date = st.date_format.format(
                d=now.day, m=now.month, Y=now.year, y=now.year % 100,
                M=MONTHS[lang][now.month - 1], D=DAYS[lang][now.weekday()],
            )
        except (KeyError, ValueError, IndexError):
            date = f"{now.day:02d} {MONTHS[lang][now.month - 1]}, {now.year}."
    time = st.time
    if time.strip().lower() == "auto":
        h12 = now.hour % 12 or 12
        try:
            time = st.time_format.format(
                H=f"{now.hour:02d}", i=f"{now.minute:02d}", s=f"{now.second:02d}",
                h=f"{h12:02d}", p="PM" if now.hour >= 12 else "AM",
            )
        except (KeyError, ValueError):
            time = f"- {now.hour:02d}:{now.minute:02d} -"
    if st.uppercase:
        title, date = title.upper(), date.upper()
    return title, date, time


# ----------------------------------------------------------------------------
# render principal
# ----------------------------------------------------------------------------
_base_cache: dict = {}   # (id(bg), W, H, fit, bg_color, blur, dim, vignette) -> RGBA


def _prepare_base(background: Image.Image, st: Style) -> Image.Image:
    """Fondo ajustado + blur/dim/viñeta. Se cachea: al editar solo el texto no se recalcula."""
    W, H = int(st.width), int(st.height)
    key = (id(background), W, H, st.fit, st.bg_color, round(st.blur, 2), round(st.dim, 3), round(st.vignette, 3))
    hit = _base_cache.get(key)
    if hit is not None:
        return hit
    base = _fit_background(background, W, H, st.fit, _hex(st.bg_color))
    if st.blur > 0:
        base = base.filter(ImageFilter.GaussianBlur(st.blur * (H / 1080.0)))
    if st.dim > 0:
        base = Image.blend(base, Image.new("RGB", (W, H), (0, 0, 0)), min(1.0, st.dim))
    if st.vignette > 0:
        small = Image.new("L", (64, 36), 0)
        md = ImageDraw.Draw(small)
        md.ellipse([-12, -10, 76, 46], fill=255)
        mask = small.filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
        mask = mask.point(lambda p: int((255 - p) * min(1.0, st.vignette)))
        base.paste(Image.new("RGB", (W, H), (0, 0, 0)), mask=mask)
    base = base.convert("RGBA")
    if len(_base_cache) >= 6:          # pequeño LRU: evita acumular memoria
        _base_cache.pop(next(iter(_base_cache)))
    _base_cache[key] = base
    return base


def render(background: Image.Image, st: Style, now: Optional[_dt.datetime] = None) -> Image.Image:
    W, H = int(st.width), int(st.height)
    u = (H / 1080.0) * st.scale     # escala relativa a 1080p (presets iguales en 4K)
    base = _prepare_base(background, st).copy()

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    col = _hex(st.color, st.opacity)

    title, date, time = _auto_texts(st, now)

    cx = W * st.x / 100.0
    y = H * st.y / 100.0

    # --- Título ---------------------------------------------------------
    if st.show_title and title:
        size = int(62 * u * st.title_size)
        f = _font(st.font_title, size)
        _draw_spaced(draw, cx, y, title, f, size * st.title_spacing, col)
        y += size * 1.35

    # --- Fecha ----------------------------------------------------------
    if st.show_date and date:
        size = int(21 * u)
        f = _font("regular", size)
        _draw_spaced(draw, cx, y, date, f, size * st.date_spacing, col)
        y += size * 2.2

    # --- Hora -----------------------------------------------------------
    if st.show_time and time:
        size = int(24 * u)
        f = _font("regular", size)
        _draw_spaced(draw, cx, y, time, f, size * st.time_spacing, col)
        y += size * 2.6

    # --- Barra de progreso --------------------------------------------------
    bar_w = W * st.width_pct / 100.0
    if st.show_bar:
        size = int(13 * u)
        f = _font("medium", size)
        lw = _text_width(f, st.bar_left, size * 0.12)
        rw = _text_width(f, st.bar_right, size * 0.12)
        gap = 14 * u
        line_x0 = cx - bar_w / 2 + lw + gap
        line_x1 = cx + bar_w / 2 - rw - gap
        ly = y + size * 0.55
        _draw_spaced(draw, cx - bar_w / 2 + lw / 2, y, st.bar_left, f, size * 0.12, col)
        _draw_spaced(draw, cx + bar_w / 2 - rw / 2, y, st.bar_right, f, size * 0.12, col)
        thin = _hex(st.color, st.opacity * 0.55)
        draw.line([(line_x0, ly), (line_x1, ly)], fill=thin, width=max(1, int(1.6 * u)))
        px = line_x0 + (line_x1 - line_x0) * max(0.0, min(1.0, st.bar_progress))
        r = 4.2 * u
        draw.ellipse([px - r, ly - r, px + r, ly + r], fill=col)
        y += size * 4.4

    # --- Controles ◁◁ ▷ ▷▷ --------------------------------------------------
    if st.show_controls:
        h = 17 * u            # altura de los triángulos
        tw = h * 0.95         # ancho triángulo
        stroke = max(1, int(1.8 * u))
        gap_ctrl = 32 * u
        cy = y + h / 2

        def tri(x0, direction):
            # triángulo con contorno (outline) centrado verticalmente en cy
            if direction > 0:
                pts = [(x0, cy - h / 2), (x0 + tw, cy), (x0, cy + h / 2)]
            else:
                pts = [(x0 + tw, cy - h / 2), (x0, cy), (x0 + tw, cy + h / 2)]
            draw.polygon(pts, outline=col, width=stroke)

        # play centrado
        tri(cx - tw / 2, +1)
        # rewind (dos triángulos solapados)
        ov = tw * 0.42
        x_rw = cx - tw / 2 - gap_ctrl - (2 * tw - ov)
        tri(x_rw, -1)
        tri(x_rw + tw - ov, -1)
        # forward
        x_ff = cx + tw / 2 + gap_ctrl
        tri(x_ff, +1)
        tri(x_ff + tw - ov, +1)

    # --- Sombra / glow ------------------------------------------------------
    if st.shadow > 0 or st.glow > 0:
        alpha = layer.getchannel("A")
        if st.shadow > 0:
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sh.putalpha(alpha.point(lambda p: int(p * st.shadow)))
            sh = sh.filter(ImageFilter.GaussianBlur(6 * u))
            base = Image.alpha_composite(base, sh)
        if st.glow > 0:
            gl = Image.new("RGBA", (W, H), col[:3] + (0,))
            gl.putalpha(alpha.point(lambda p: int(p * st.glow)))
            gl = gl.filter(ImageFilter.GaussianBlur(10 * u))
            base = Image.alpha_composite(base, gl)

    out = Image.alpha_composite(base, layer)
    return out.convert("RGB")


def render_to_bytes(background: Image.Image, st: Style, fmt: str = "PNG",
                    quality: int = 92, now: Optional[_dt.datetime] = None) -> bytes:
    img = render(background, st, now)
    buf = io.BytesIO()
    if fmt.upper() in ("JPG", "JPEG"):
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    else:
        img.save(buf, "PNG", compress_level=3)
    return buf.getvalue()


_small_cache: dict = {}


def _small_bg(background: Image.Image, w: int, h: int) -> Image.Image:
    bw, bh = background.size
    k = max(1.0, min(bw / (w * 1.2), bh / (h * 1.2)))
    if k <= 1.05:
        return background
    key = (id(background), int(bw / k), int(bh / k))
    if key not in _small_cache:
        _small_cache.clear()
        _small_cache[key] = background.resize((int(bw / k), int(bh / k)), Image.BILINEAR)
    return _small_cache[key]


def preview(background: Image.Image, st: Style, max_w: int = 960) -> bytes:
    """Render reducido para la vista previa del editor (rápido)."""
    s = Style.from_dict(st.to_dict())
    ratio = min(1.0, max_w / float(s.width))
    s.width = max(16, int(s.width * ratio))
    s.height = max(9, int(s.height * ratio))
    # downscale el fondo antes de renderizar para ahorrar CPU
    background = _small_bg(background, s.width, s.height)
    img = render(background, s)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()
