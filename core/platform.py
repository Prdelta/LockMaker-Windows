"""Selecciona el aplicador según el sistema operativo."""
import sys

impl = None
try:
    if sys.platform.startswith("win"):
        from . import platform_win as impl  # noqa: F401
    elif sys.platform.startswith("linux"):
        from . import platform_linux as impl  # noqa: F401
except ImportError:
    impl = None


def available() -> bool:
    return impl is not None


def info() -> dict:
    if impl is None:
        return {"os": sys.platform, "admin": False, "capabilities": {}, "notes": ["SO no soportado"]}
    return impl.info()


def apply(path: str, targets: list[str]) -> dict:
    """Aplica la imagen ya renderizada a cada objetivo. Devuelve {target: mensaje|error}."""
    out = {}
    if impl is None:
        return {t: "ERROR: sistema no soportado" for t in targets}
    for t in targets:
        try:
            if t == "wallpaper":
                out[t] = impl.set_wallpaper(path)
            elif t == "lock":
                out[t] = impl.set_lockscreen(path)
            elif t == "login":
                if hasattr(impl, "set_login"):
                    out[t] = impl.set_login(path)
                else:  # Windows: inicio == bloqueo
                    out[t] = impl.set_lockscreen(path, also_logon=True)
            else:
                out[t] = f"ERROR: objetivo desconocido '{t}'"
        except Exception as e:  # noqa: BLE001
            out[t] = f"ERROR: {e}"
    return out


def install_autorefresh(script: str, preset: str, every_minutes: int, targets: str) -> str:
    return impl.install_autorefresh(script, preset, every_minutes, targets)


def uninstall_autorefresh() -> None:
    impl.uninstall_autorefresh()


def is_admin() -> bool:
    return bool(impl and impl.info().get("admin"))


def set_live_wallpaper(path: str, persist: bool = False) -> str:
    return impl.set_live_wallpaper(path, persist)


def stop_live_wallpaper() -> None:
    impl.stop_live_wallpaper()
