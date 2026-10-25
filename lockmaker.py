#!/usr/bin/env python3
"""
LockMaker — personalizador de pantalla de bloqueo / inicio / escritorio
para Windows 11 y Linux.

  python lockmaker.py                      → abre el editor (navegador local)
  python lockmaker.py apply --preset P     → re-renderiza y aplica (uso por tareas programadas)
  python lockmaker.py render --image I --out O [--preset P]
  python lockmaker.py autorefresh --preset P --every 1 --targets wallpaper,lock
  python lockmaker.py autorefresh --remove
  python lockmaker.py restore              → (Windows) quita la política de bloqueo

Dependencia única: Pillow  (pip install pillow)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import os
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

try:
    from PIL import Image
except ImportError:  # instalación automática amable
    print("Pillow no está instalado. Instalando...")
    import subprocess
    subprocess.call([sys.executable, "-m", "pip", "install", "--user", "pillow"])
    from PIL import Image  # noqa

from core import platform as plat
from core.render import Style, render, preview, render_to_bytes
from core import animate as anim_mod
from core import quick

UI_DIR = os.path.join(ROOT, "ui")
WALL_DIR = os.path.join(ROOT, "wallpapers")
PRESET_DIR = os.path.join(ROOT, "presets")

if sys.platform.startswith("win"):
    DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "LockMaker")
else:
    DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "lockmaker")
os.makedirs(DATA_DIR, exist_ok=True)
USER_PRESETS = os.path.join(DATA_DIR, "presets")
os.makedirs(USER_PRESETS, exist_ok=True)
CURRENT_PRESET = os.path.join(USER_PRESETS, "current.json")
quick.SNAP_FILE = os.path.join(DATA_DIR, "ajustes_originales.json")


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------
def load_preset(path_or_name: str) -> dict:
    p = path_or_name
    if not os.path.isfile(p):
        for d in (USER_PRESETS, PRESET_DIR):
            cand = os.path.join(d, p if p.endswith(".json") else p + ".json")
            if os.path.isfile(cand):
                p = cand
                break
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_preset(name: str, style: dict, image: str | None) -> str:
    name = "".join(c for c in name if c.isalnum() or c in "-_ ").strip() or "preset"
    path = os.path.join(USER_PRESETS, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"style": style, "image": image}, f, indent=2, ensure_ascii=False)
    return path


def list_presets() -> list[dict]:
    out = []
    for d, kind in ((PRESET_DIR, "builtin"), (USER_PRESETS, "user")):
        if not os.path.isdir(d):
            continue
        for n in sorted(os.listdir(d)):
            if n.endswith(".json"):
                out.append({"name": n[:-5], "kind": kind, "path": os.path.join(d, n)})
    return out


# ---------------------------------------------------------------------------
# Galería de wallpapers (cualquier imagen en wallpapers/, miniaturas en wallpapers/thumbs)
# ---------------------------------------------------------------------------
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")


def list_wallpapers() -> list[dict]:
    if not os.path.isdir(WALL_DIR):
        return []
    tdir = os.path.join(WALL_DIR, "thumbs")
    os.makedirs(tdir, exist_ok=True)
    out = []
    for n in sorted(os.listdir(WALL_DIR)):
        if not n.lower().endswith(IMG_EXT):
            continue
        thumb = os.path.join(tdir, os.path.splitext(n)[0] + ".jpg")
        if not os.path.isfile(thumb):
            try:
                im = Image.open(os.path.join(WALL_DIR, n)).convert("RGB")
                im.thumbnail((480, 480))
                im.save(thumb, "JPEG", quality=78)
            except Exception:
                continue
        out.append({"file": n, "name": os.path.splitext(n)[0], "thumb": "/wallpapers/thumbs/" + os.path.basename(thumb),
                    "builtin": n[:2].isdigit(), "animated": n.lower().endswith((".gif", ".webp")) and anim_mod.is_animated(os.path.join(WALL_DIR, n))})
    return out


# ---------------------------------------------------------------------------
# Render + apply (compartido por CLI y servidor)
# ---------------------------------------------------------------------------
def do_apply(style: dict, image_path: str, targets: list[str], quiet: bool = False) -> dict:
    st = Style.from_dict(style)
    bg = Image.open(image_path)
    out = os.path.join(DATA_DIR, "render.png")
    render(bg, st).save(out, "PNG", optimize=False, compress_level=3)
    res = plat.apply(out, targets)
    if not quiet:
        for k, v in res.items():
            print(f"[{k}] {v}")
    return res


# ---------------------------------------------------------------------------
# Servidor del editor
# ---------------------------------------------------------------------------
class AnimJob:
    running = False
    done = 0
    total = 0
    result: str | None = None
    error: str | None = None
    fmt = "gif"


class State:
    image: Image.Image | None = None
    image_path: str | None = None
    image_name: str = ""
    lock = threading.Lock()


MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript", ".css": "text/css",
        ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".ttf": "font/ttf",
        ".json": "application/json"}


class Handler(BaseHTTPRequestHandler):
    server_version = "LockMaker/1.0"

    def log_message(self, *a):  # silencio
        pass

    # ---- helpers ------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    # ---- GET ---------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/quick":
            return self._json(quick.list_settings())
        if u.path == "/api/info":
            i = plat.info()
            i["has_image"] = State.image is not None
            i["image_name"] = State.image_name
            i["image_size"] = list(State.image.size) if State.image else None
            i["image_animated"] = bool(State.image_path and anim_mod.is_animated(State.image_path))
            i["ffmpeg"] = bool(anim_mod.ffmpeg_path())
            i["procedural"] = list(anim_mod.PROCEDURAL.keys())
            i["presets"] = list_presets()
            i["data_dir"] = DATA_DIR
            try:
                i["current"] = load_preset(CURRENT_PRESET)
            except Exception:
                i["current"] = None
            return self._json(i)
        if u.path == "/api/preset":
            name = parse_qs(u.query).get("name", [""])[0]
            try:
                pr = load_preset(name)
                if pr.get("image") and os.path.isfile(pr["image"]):
                    self._set_image(Image.open(pr["image"]), pr["image"], os.path.basename(pr["image"]))
                return self._json(pr)
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        if u.path == "/api/export":
            return self._export(parse_qs(u.query))
        if u.path == "/api/wallpapers":
            return self._json(list_wallpapers())
        if u.path == "/api/animate/status":
            return self._json({"running": AnimJob.running, "done": AnimJob.done, "total": AnimJob.total,
                               "result": os.path.basename(AnimJob.result) if AnimJob.result else None,
                               "size": os.path.getsize(AnimJob.result) if AnimJob.result and os.path.isfile(AnimJob.result) else 0,
                               "fmt": AnimJob.fmt, "error": AnimJob.error})
        if u.path == "/api/animate/file":
            if not AnimJob.result or not os.path.isfile(AnimJob.result):
                return self._send(404, b"no file", "text/plain")
            q = parse_qs(u.query)
            with open(AnimJob.result, "rb") as f:
                data = f.read()
            ctype = {"gif": "image/gif", "mp4": "video/mp4", "webm": "video/webm"}[AnimJob.fmt]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            if q.get("download"):
                self.send_header("Content-Disposition", f'attachment; filename="lockmaker-animado.{AnimJob.fmt}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(data)
        # archivos estáticos
        path = "/index.html" if u.path == "/" else unquote(u.path)
        fp = os.path.normpath(os.path.join(UI_DIR, path.lstrip("/")))
        if path.startswith("/fonts/") or path.startswith("/wallpapers/"):
            fp = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if not fp.startswith(ROOT) or not os.path.isfile(fp):
            return self._send(404, b"not found", "text/plain")
        with open(fp, "rb") as f:
            self._send(200, f.read(), MIME.get(os.path.splitext(fp)[1], "application/octet-stream"))

    def _set_image(self, img: Image.Image, path: str, name: str):
        with State.lock:
            State.image = img.convert("RGB")
            State.image_path = path
            State.image_name = name

    def _export(self, q):
        if State.image is None:
            return self._json({"error": "no image"}, 400)
        try:
            style = json.loads(q.get("style", ["{}"])[0])
        except json.JSONDecodeError:
            style = {}
        fmt = q.get("fmt", ["png"])[0]
        data = render_to_bytes(State.image, Style.from_dict(style), fmt)
        self.send_response(200)
        self.send_header("Content-Type", "image/png" if fmt == "png" else "image/jpeg")
        self.send_header("Content-Disposition", f'attachment; filename="lockmaker.{fmt}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- POST --------------------------------------------------------
    def do_POST(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/image":
                return self._upload()
            data = json.loads(self._body() or b"{}")
            if u.path == "/api/preview":
                return self._preview(data)
            if u.path == "/api/apply":
                return self._apply(data)
            if u.path == "/api/wallpaper/use":
                fname = os.path.basename(str(data.get("file", "")))
                fp = os.path.join(WALL_DIR, fname)
                if not fname or not os.path.isfile(fp):
                    return self._json({"error": "wallpaper no encontrado"}, 404)
                img = Image.open(fp)
                img.load()
                self._set_image(img, fp, fname)
                return self._json({"ok": True, "size": list(img.size), "name": fname})
            if u.path == "/api/animate":
                return self._animate(data)
            if u.path == "/api/quick/set":
                try:
                    return self._json({"ok": True, **quick.set_setting(str(data.get("id")), data.get("value"))})
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 400)
            if u.path == "/api/quick/restore":
                return self._json({"ok": True, **quick.restore_all()})
            if u.path == "/api/quick/open":
                try:
                    quick.open_link(str(data.get("target", "")))
                    return self._json({"ok": True})
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 400)
            if u.path == "/api/quick/action":
                try:
                    return self._json({"ok": True, "msg": quick.run_action(str(data.get("id", "")))})
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 400)
            if u.path == "/api/live/apply":
                if not AnimJob.result or not os.path.isfile(AnimJob.result):
                    return self._json({"error": "Genera primero la animación."}, 400)
                try:
                    return self._json({"ok": True, "msg": "Fondo animado aplicado: " + plat.set_live_wallpaper(AnimJob.result, bool(data.get("persist")))})
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 400)
            if u.path == "/api/live/stop":
                plat.stop_live_wallpaper()
                return self._json({"ok": True, "msg": "Fondo animado detenido."})
            if u.path == "/api/wallpaper/url":
                return self._from_url(str(data.get("url", "")).strip())
            if u.path == "/api/wallpaper/delete":
                fname = os.path.basename(str(data.get("file", "")))
                fp = os.path.join(WALL_DIR, fname)
                if fname and os.path.isfile(fp) and not fname[:2].isdigit():   # los incluidos no se borran
                    os.remove(fp)
                    try:
                        os.remove(os.path.join(WALL_DIR, "thumbs", os.path.splitext(fname)[0] + ".jpg"))
                    except OSError:
                        pass
                return self._json({"ok": True, "wallpapers": list_wallpapers()})
            if u.path == "/api/preset/save":
                p = save_preset(data.get("name", "preset"), data.get("style", {}), State.image_path)
                return self._json({"ok": True, "path": p, "presets": list_presets()})
            if u.path == "/api/autorefresh":
                return self._autorefresh(data)
            if u.path == "/api/elevate":
                return self._elevate(data)
            if u.path == "/api/quit":
                self._json({"ok": True})
                threading.Timer(0.3, self.server.shutdown).start()
                return
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)

    def _upload(self):
        name = self.headers.get("X-Filename", "image.png")
        raw = self._body()
        img = Image.open(io.BytesIO(raw))
        img.load()
        ext = os.path.splitext(name)[1].lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
            ext = ".png"
        dst = os.path.join(DATA_DIR, "source" + ext)
        with open(dst, "wb") as f:
            f.write(raw)
        self._set_image(img, dst, name)
        self._json({"ok": True, "size": list(img.size), "name": name})

    def _from_url(self, url: str):
        """Descarga una imagen por URL (en el PC del usuario) a wallpapers/ y la deja seleccionada."""
        import urllib.request
        if not url.startswith(("http://", "https://")):
            return self._json({"error": "URL no válida"}, 400)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LockMaker"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(60 * 1024 * 1024)
        img = Image.open(io.BytesIO(raw))
        img.load()
        ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(img.format or "", ".jpg")
        base = os.path.splitext(os.path.basename(urlparse(url).path))[0] or "descarga"
        base = "".join(c for c in base if c.isalnum() or c in "-_ ")[:40] or "descarga"
        os.makedirs(WALL_DIR, exist_ok=True)
        fname, n = base + ext, 1
        while os.path.exists(os.path.join(WALL_DIR, fname)):
            n += 1
            fname = f"{base}-{n}{ext}"
        with open(os.path.join(WALL_DIR, fname), "wb") as f:
            f.write(raw)
        self._set_image(img, os.path.join(WALL_DIR, fname), fname)
        self._json({"ok": True, "size": list(img.size), "name": fname, "wallpapers": list_wallpapers()})

    def _animate(self, data):
        if AnimJob.running:
            return self._json({"error": "Ya hay una animación en curso."}, 409)
        a = anim_mod.Anim.from_dict(data.get("anim", {}))
        fmt = data.get("fmt", "gif")
        if fmt not in ("gif", "mp4", "webm"):
            fmt = "gif"
        if fmt != "gif" and not anim_mod.ffmpeg_path():
            return self._json({"error": "MP4/WebM necesitan ffmpeg instalado (https://ffmpeg.org). Usa GIF o instala ffmpeg."}, 400)
        source = data.get("source", "current")
        style = data.get("style", {})
        if source.startswith("proc:"):
            name = anim_mod.PROCEDURAL.get(source[5:])
            if not name:
                return self._json({"error": "fondo procedural desconocido"}, 400)
            src_frames, src_durs = anim_mod.procedural_frames(name, a.out_w, a.out_h, max(12, int(a.seconds * a.fps))), None
            src_durs = [int(1000 / a.fps)] * len(src_frames)
        else:
            if State.image_path is None:
                return self._json({"error": "Carga una imagen primero."}, 400)
            src_frames, src_durs = anim_mod.load_frames(State.image_path)
        AnimJob.running, AnimJob.done, AnimJob.total, AnimJob.result, AnimJob.error, AnimJob.fmt = True, 0, 0, None, None, fmt
        out = os.path.join(DATA_DIR, "animado." + fmt)

        def work():
            try:
                def prog(i, n):
                    AnimJob.done, AnimJob.total = i, n + 1
                frames, durs = anim_mod.build_frames(src_frames, src_durs, style, a, prog)
                if fmt == "gif":
                    anim_mod.save_gif(frames, durs, out, a.colors)
                else:
                    anim_mod.save_video(frames, a.fps, out, fmt)
                AnimJob.result = out
            except Exception as e:  # noqa: BLE001
                AnimJob.error = str(e)
            finally:
                AnimJob.running = False
                AnimJob.done = AnimJob.total
        threading.Thread(target=work, daemon=True).start()
        self._json({"ok": True})

    def _preview(self, data):
        if State.image is None:
            return self._json({"error": "no image"}, 400)
        st = Style.from_dict(data.get("style", {}))
        jpg = preview(State.image, st, int(data.get("max_w", 960)))
        self._send(200, jpg, "image/jpeg")

    def _apply(self, data):
        if State.image is None:
            return self._json({"error": "Carga una imagen primero."}, 400)
        style = data.get("style", {})
        targets = [t for t in data.get("targets", []) if t in ("wallpaper", "lock", "login")]
        if not targets:
            return self._json({"error": "Elige al menos un objetivo."}, 400)
        # guarda siempre el preset actual (lo usa la tarea de auto-refresco y la elevación)
        with open(CURRENT_PRESET, "w", encoding="utf-8") as f:
            json.dump({"style": style, "image": State.image_path}, f, indent=2, ensure_ascii=False)
        needs = set(plat.info().get("capabilities", {}).get("needs_admin", []))
        if sys.platform.startswith("win") and (needs & set(targets)) and not plat.is_admin():
            # aplicar lo que no necesita admin, y pedir elevación para el resto
            res = do_apply(style, State.image_path, [t for t in targets if t not in needs], quiet=True)
            return self._json({"ok": True, "need_admin": sorted(needs & set(targets)), "results": res})
        res = do_apply(style, State.image_path, targets, quiet=True)
        self._json({"ok": all(not str(v).startswith("ERROR") for v in res.values()), "results": res})

    def _elevate(self, data):
        targets = ",".join(data.get("targets", ["lock", "login"]))
        ok = plat.impl.relaunch_as_admin([os.path.abspath(__file__), "apply", "--preset", CURRENT_PRESET,
                                          "--targets", targets, "--quiet"])
        self._json({"ok": ok})

    def _autorefresh(self, data):
        if data.get("remove"):
            plat.uninstall_autorefresh()
            return self._json({"ok": True, "msg": "Auto-actualización eliminada."})
        if State.image_path is None:
            return self._json({"error": "Carga una imagen primero."}, 400)
        with open(CURRENT_PRESET, "w", encoding="utf-8") as f:
            json.dump({"style": data.get("style", {}), "image": State.image_path}, f, indent=2)
        targets = ",".join(t for t in data.get("targets", ["wallpaper"]) if t in ("wallpaper", "lock", "login"))
        every = int(data.get("every", 1))
        if sys.platform.startswith("win") and any(t in targets for t in ("lock", "login")) and not plat.is_admin():
            ok = plat.impl.relaunch_as_admin([os.path.abspath(__file__), "autorefresh", "--preset", CURRENT_PRESET,
                                              "--every", str(every), "--targets", targets])
            return self._json({"ok": ok, "msg": "Se pidió permiso de administrador para crear la tarea."})
        name = plat.install_autorefresh(os.path.abspath(__file__), CURRENT_PRESET, every, targets)
        self._json({"ok": True, "msg": f"Auto-actualización activa ({name}) cada {every} min → {targets}"})


def open_window(url: str):
    """Abre el panel como ventana de aplicación (sin pestañas ni barra de direcciones) si hay
    Edge/Chrome/Chromium; si no, en el navegador normal."""
    import shutil
    import subprocess
    cands = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("PROGRAMFILES", ""), os.environ.get("LOCALAPPDATA", "")):
            cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    else:
        cands = [shutil.which(n) for n in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
                                            "brave-browser", "microsoft-edge")]
    for exe in cands:
        if exe and os.path.isfile(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1280,820"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return
            except OSError:
                pass
    webbrowser.open(url)


def serve(port: int = 0, open_browser: bool = True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"LockMaker editor: {url}   (Ctrl+C para salir)")
    if open_browser:
        threading.Timer(0.4, lambda: open_window(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="lockmaker", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="abre el editor web local (por defecto)")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--no-browser", action="store_true")

    a = sub.add_parser("apply", help="renderiza y aplica un preset")
    a.add_argument("--preset", required=True)
    a.add_argument("--image", help="sobrescribe la imagen del preset")
    a.add_argument("--targets", default="wallpaper", help="wallpaper,lock,login")
    a.add_argument("--set", action="append", default=[], metavar="clave=valor", help="sobrescribe un ajuste: --set title=HOY --set time=auto")
    a.add_argument("--quiet", action="store_true")

    r = sub.add_parser("render", help="renderiza a un archivo sin aplicar")
    r.add_argument("--image", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--preset")
    r.add_argument("--set", action="append", default=[], metavar="clave=valor", help="ej. --set title=LUNES --set y=12")

    t = sub.add_parser("autorefresh", help="instala/elimina la tarea de actualización automática")
    t.add_argument("--preset")
    t.add_argument("--every", type=int, default=1, help="minutos")
    t.add_argument("--targets", default="wallpaper")
    t.add_argument("--remove", action="store_true")

    an = sub.add_parser("animate", help="genera un fondo animado (GIF/MP4/WebM) con el overlay")
    an.add_argument("--image", help="imagen fija o GIF animado de origen")
    an.add_argument("--proc", choices=list(anim_mod.PROCEDURAL.keys()), help="fondo procedural en vez de imagen")
    an.add_argument("--out", required=True, help="salida .gif / .mp4 / .webm")
    an.add_argument("--preset")
    an.add_argument("--seconds", type=float, default=6)
    an.add_argument("--fps", type=int, default=15)
    an.add_argument("--size", default="1280x720")
    an.add_argument("--particles", default="none", choices=["none", "bokeh", "snow", "rain", "stars"])
    an.add_argument("--kenburns", type=float, default=0.05)
    an.add_argument("--pulse", type=float, default=0.25)
    an.add_argument("--apply", action="store_true", help="aplicarlo como fondo animado (Lively / mpvpaper)")
    an.add_argument("--persist", action="store_true", help="(Linux) volver a lanzarlo al iniciar sesión")
    an.add_argument("--set", action="append", default=[], metavar="clave=valor")

    sub.add_parser("live-stop", help="detiene el fondo animado")
    sub.add_parser("restore", help="(Windows) quita la configuración de bloqueo")
    sub.add_parser("info", help="muestra lo detectado en este sistema")

    args = ap.parse_args(argv)
    cmd = args.cmd or "serve"

    if cmd == "serve":
        return serve(getattr(args, "port", 0), not getattr(args, "no_browser", False))

    if cmd == "info":
        print(json.dumps(plat.info(), indent=2, ensure_ascii=False))
        return

    if cmd == "apply":
        pr = load_preset(args.preset)
        image = args.image or pr.get("image")
        if not image or not os.path.isfile(image):
            sys.exit("Imagen no encontrada: %s" % image)
        style = pr.get("style", {})
        for kv in args.set:
            k, _, v = kv.partition("=")
            style[k] = v
        res = do_apply(style, image, args.targets.split(","), args.quiet)
        bad = [k for k, v in res.items() if str(v).startswith("ERROR")]
        sys.exit(1 if bad else 0)

    if cmd == "render":
        style = load_preset(args.preset).get("style", {}) if args.preset else {}
        for kv in args.set:
            k, _, v = kv.partition("=")
            style[k] = v
        st = Style.from_dict(style)
        img = render(Image.open(args.image), st, _dt.datetime.now())
        img.save(args.out)
        print("OK", args.out, img.size)
        return

    if cmd == "animate":
        style = load_preset(args.preset).get("style", {}) if args.preset else {}
        for kv in args.set:
            k, _, v = kv.partition("=")
            style[k] = v
        w, h = map(int, args.size.lower().split("x"))
        a = anim_mod.Anim(seconds=args.seconds, fps=args.fps, out_w=w, out_h=h, particles=args.particles,
                          kenburns=args.kenburns, pulse=args.pulse)
        if args.proc:
            fr = anim_mod.procedural_frames(anim_mod.PROCEDURAL[args.proc], w, h, max(12, int(a.seconds * a.fps)))
            du = [int(1000 / a.fps)] * len(fr)
        elif args.image:
            fr, du = anim_mod.load_frames(args.image)
        else:
            sys.exit("Indica --image o --proc")
        frames, durs = anim_mod.build_frames(fr, du, style, a, lambda i, n: print(f"\r  {i}/{n}", end="", flush=True))
        print()
        fmt = os.path.splitext(args.out)[1].lstrip(".").lower() or "gif"
        if fmt == "gif":
            anim_mod.save_gif(frames, durs, args.out)
        elif anim_mod.save_video(frames, a.fps, args.out, fmt) is None:
            sys.exit("ffmpeg no encontrado: instala ffmpeg o exporta a .gif")
        print("OK", args.out, f"{os.path.getsize(args.out) / 1048576:.1f} MB")
        if args.apply:
            print(plat.set_live_wallpaper(args.out, args.persist))
        return

    if cmd == "live-stop":
        plat.stop_live_wallpaper()
        print("Fondo animado detenido.")
        return

    if cmd == "autorefresh":
        if args.remove:
            plat.uninstall_autorefresh()
            print("Tarea eliminada.")
            return
        preset = args.preset or CURRENT_PRESET
        print(plat.install_autorefresh(os.path.abspath(__file__), os.path.abspath(preset), args.every, args.targets))
        return

    if cmd == "restore":
        if sys.platform.startswith("win"):
            if not plat.is_admin():
                plat.impl.relaunch_as_admin([os.path.abspath(__file__), "restore"])
                return
            plat.impl.restore_lockscreen()
            print("Configuración de bloqueo restaurada.")
        else:
            print("En Linux basta con elegir otra imagen en la configuración del escritorio.")


if __name__ == "__main__":
    main()
