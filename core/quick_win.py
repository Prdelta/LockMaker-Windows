"""
LockMaker - Ajustes rápidos para Windows 10/11.

Reúne en un solo panel los ajustes de personalización que Windows reparte entre
Configuración, el Panel de control y el registro. Todo es HKCU (tu usuario, sin
administrador) salvo lo marcado con admin=True. Cada cambio se notifica al
sistema con WM_SETTINGCHANGE para que se vea sin reiniciar cuando es posible.
"""
from __future__ import annotations

import ctypes
import os
import subprocess

import winreg

HKCU = winreg.HKEY_CURRENT_USER
HKLM = winreg.HKEY_LOCAL_MACHINE
NOWIN = 0x08000000

PERS = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
ADV = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
DWM = r"Software\Microsoft\Windows\DWM"
ACCENT = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"
CDM = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
DESK = r"Control Panel\Desktop"
ACCESS = r"Software\Microsoft\Accessibility"
SEARCH = r"Software\Microsoft\Windows\CurrentVersion\Search"
CLASSIC_MENU = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"
POLICY_SYS = r"SOFTWARE\Policies\Microsoft\Windows\System"


# ---------------------------------------------------------------- registro
def rget(root, path, name, default=None):
    try:
        with winreg.OpenKeyEx(root, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def rset(root, path, name, value, kind=winreg.REG_DWORD):
    with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
        winreg.SetValueEx(k, name, 0, kind, value)


def rdel(root, path, name):
    try:
        with winreg.OpenKeyEx(root, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass


def key_exists(root, path) -> bool:
    try:
        winreg.CloseKey(winreg.OpenKeyEx(root, path, 0, winreg.KEY_READ))
        return True
    except OSError:
        return False


def broadcast(*areas):
    """Avisa a Windows/Explorer de que cambió la configuración."""
    res = ctypes.c_ulong()
    for a in areas or ("ImmersiveColorSet",):
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, a, 0x0002, 3000, ctypes.byref(res))


def spi(action, uparam, pvparam, flags=0x03):
    return ctypes.windll.user32.SystemParametersInfoW(action, uparam, pvparam, flags)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------------------------------------------------------------- helpers de color
def _hex_to_abgr(hexc: str) -> int:
    h = hexc.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0xFF << 24) | (b << 16) | (g << 8) | r


def _abgr_to_hex(v) -> str:
    if v is None:
        return "#0078d4"
    v = int(v) & 0xFFFFFFFF
    r, g, b = v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"


def _set_accent(hexc: str):
    abgr = _hex_to_abgr(hexc)
    h = hexc.lstrip("#")
    argb = (0xC4 << 24) | int(h, 16)
    rset(HKCU, DESK, "AutoColorization", 0)
    rset(HKCU, DWM, "AccentColor", abgr)
    rset(HKCU, DWM, "ColorizationColor", argb)
    rset(HKCU, DWM, "ColorizationAfterglow", argb)
    rset(HKCU, ACCENT, "AccentColorMenu", abgr)
    rset(HKCU, ACCENT, "StartColorMenu", abgr)
    # paleta de 8 tonos (claro→oscuro) que usan Inicio y la barra de tareas
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    pal = bytearray()
    for f in (1.6, 1.4, 1.2, 1.0, 0.8, 0.6, 0.4, 0.3):
        if f >= 1:
            c = [int(x + (255 - x) * (f - 1) / 0.75) for x in (r, g, b)]
        else:
            c = [int(x * f) for x in (r, g, b)]
        pal += bytes([min(255, c[0]), min(255, c[1]), min(255, c[2]), 0])
    rset(HKCU, ACCENT, "AccentPalette", bytes(pal), winreg.REG_BINARY)
    broadcast("ImmersiveColorSet", "WindowsThemeElement")


# ---------------------------------------------------------------- definición de ajustes
def _dw(root, path, name, on=1, off=0, default=None, areas=("ImmersiveColorSet",)):
    """Interruptor sobre un DWORD."""
    def get():
        v = rget(root, path, name, default)
        return None if v is None else (v == on)

    def set_(val):
        rset(root, path, name, on if val else off)
        broadcast(*areas)
    return get, set_


def _sel(root, path, name, values: dict, default=None, areas=("TraySettings",)):
    """Selector sobre un DWORD: values = {etiqueta_valor: dword}."""
    rev = {v: k for k, v in values.items()}

    def get():
        return rev.get(rget(root, path, name, default))

    def set_(val):
        rset(root, path, name, values[val])
        broadcast(*areas)
    return get, set_


def _animations():
    def get():
        b = ctypes.c_int()
        spi(0x1042, 0, ctypes.byref(b), 0)  # SPI_GETCLIENTAREAANIMATION
        return bool(b.value)

    def set_(val):
        spi(0x1043, 0, ctypes.c_void_p(1 if val else 0))  # SPI_SETCLIENTAREAANIMATION
        rset(HKCU, DESK + r"\WindowMetrics", "MinAnimate", "1" if val else "0", winreg.REG_SZ)
        broadcast("WindowMetrics")
    return get, set_


def _text_scale():
    def get():
        return rget(HKCU, ACCESS, "TextScaleFactor", 100)

    def set_(val):
        rset(HKCU, ACCESS, "TextScaleFactor", max(100, min(225, int(val))))
        broadcast("ImmersiveColorSet", "WindowMetrics")
    return get, set_


def _cursor_size():
    def get():
        return rget(HKCU, ACCESS, "CursorSize", 1)

    def set_(val):
        n = max(1, min(15, int(val)))
        rset(HKCU, ACCESS, "CursorSize", n)
        rset(HKCU, r"Control Panel\Cursors", "CursorBaseSize", 32 + (n - 1) * 16)
        spi(0x0057, 0, None)  # SPI_SETCURSORS: recarga cursores
    return get, set_


def _accent():
    return (lambda: _abgr_to_hex(rget(HKCU, DWM, "AccentColor"))), _set_accent


def _accent_auto():
    def get():
        return rget(HKCU, DESK, "AutoColorization", 0) == 1

    def set_(val):
        rset(HKCU, DESK, "AutoColorization", 1 if val else 0)
        broadcast("ImmersiveColorSet")
    return get, set_


def _classic_menu():
    def get():
        return key_exists(HKCU, CLASSIC_MENU + r"\InprocServer32")

    def set_(val):
        if val:
            rset(HKCU, CLASSIC_MENU + r"\InprocServer32", "", "", winreg.REG_SZ)
        else:
            for p in (CLASSIC_MENU + r"\InprocServer32", CLASSIC_MENU):
                try:
                    winreg.DeleteKey(HKCU, p)
                except OSError:
                    pass
    return get, set_


def _spotlight():
    def get():
        return rget(HKCU, CDM, "RotatingLockScreenEnabled", 1) == 1

    def set_(val):
        rset(HKCU, CDM, "RotatingLockScreenEnabled", 1 if val else 0)
    return get, set_


def _lock_tips():
    def get():
        return rget(HKCU, CDM, "SubscribedContent-338387Enabled", 1) == 1

    def set_(val):
        v = 1 if val else 0
        rset(HKCU, CDM, "SubscribedContent-338387Enabled", v)
        rset(HKCU, CDM, "RotatingLockScreenOverlayEnabled", v)
    return get, set_


def _logon_blur():
    def get():
        return rget(HKLM, POLICY_SYS, "DisableAcrylicBackgroundOnLogon", 0) != 1

    def set_(val):
        if not is_admin():
            raise PermissionError("Requiere administrador: abre LockMaker con 'Ejecutar como administrador'.")
        if val:
            rdel(HKLM, POLICY_SYS, "DisableAcrylicBackgroundOnLogon")
        else:
            rset(HKLM, POLICY_SYS, "DisableAcrylicBackgroundOnLogon", 1)
    return get, set_


LIGHT_DARK = {"Claro": 1, "Oscuro": 0}

ITEMS = [
    # id, grupo, etiqueta, tipo, (get,set), extra
    ("theme_apps", "Tema y color", "Modo de las aplicaciones", "select", _sel(HKCU, PERS, "AppsUseLightTheme", LIGHT_DARK, 1, ("ImmersiveColorSet",)), {"options": list(LIGHT_DARK)}),
    ("theme_system", "Tema y color", "Modo de Windows (barra, Inicio)", "select", _sel(HKCU, PERS, "SystemUsesLightTheme", LIGHT_DARK, 1, ("ImmersiveColorSet",)), {"options": list(LIGHT_DARK)}),
    ("transparency", "Tema y color", "Efectos de transparencia", "toggle", _dw(HKCU, PERS, "EnableTransparency", default=1), {}),
    ("accent_auto", "Tema y color", "Color de énfasis automático (del fondo)", "toggle", _accent_auto(), {}),
    ("accent", "Tema y color", "Color de énfasis", "color", _accent(), {"note": "Inicio/barra pueden tardar unos segundos o pedir reiniciar el Explorador."}),
    ("accent_taskbar", "Tema y color", "Énfasis en Inicio y barra de tareas", "toggle", _dw(HKCU, PERS, "ColorPrevalence", default=0), {"note": "Solo con modo de Windows oscuro."}),
    ("accent_titlebar", "Tema y color", "Énfasis en barras de título", "toggle", _dw(HKCU, DWM, "ColorPrevalence", default=0), {}),

    ("taskbar_align", "Barra de tareas", "Alineación", "select", _sel(HKCU, ADV, "TaskbarAl", {"Izquierda": 0, "Centro": 1}, 1), {"options": ["Izquierda", "Centro"]}),
    ("taskbar_search", "Barra de tareas", "Búsqueda", "select", _sel(HKCU, SEARCH, "SearchboxTaskbarMode", {"Oculta": 0, "Icono": 1, "Cuadro": 2, "Icono y etiqueta": 3}, 1), {"options": ["Oculta", "Icono", "Cuadro", "Icono y etiqueta"]}),
    ("taskbar_taskview", "Barra de tareas", "Botón Vista de tareas", "toggle", _dw(HKCU, ADV, "ShowTaskViewButton", default=1, areas=("TraySettings",)), {}),
    ("taskbar_widgets", "Barra de tareas", "Widgets", "toggle", _dw(HKCU, ADV, "TaskbarDa", default=1, areas=("TraySettings",)), {"note": "Algunas versiones lo protegen; si falla usa Configuración."}),
    ("clock_seconds", "Barra de tareas", "Segundos en el reloj", "toggle", _dw(HKCU, ADV, "ShowSecondsInSystemClock", default=0, areas=("TraySettings",)), {"note": "Windows 11 23H2 o posterior."}),

    ("start_recent", "Inicio y Explorador", "Mostrar archivos recientes en Inicio", "toggle", _dw(HKCU, ADV, "Start_TrackDocs", default=1, areas=("TraySettings",)), {}),
    ("file_ext", "Inicio y Explorador", "Mostrar extensiones de archivo", "toggle", _dw(HKCU, ADV, "HideFileExt", on=0, off=1, default=1, areas=("ShellState",)), {}),
    ("hidden_files", "Inicio y Explorador", "Mostrar archivos ocultos", "toggle", _dw(HKCU, ADV, "Hidden", on=1, off=2, default=2, areas=("ShellState",)), {}),
    ("explorer_open", "Inicio y Explorador", "El Explorador abre en", "select", _sel(HKCU, ADV, "LaunchTo", {"Inicio": 2, "Este equipo": 1, "Descargas": 3}, 2), {"options": ["Inicio", "Este equipo", "Descargas"]}),
    ("classic_menu", "Inicio y Explorador", "Menú contextual clásico (Win 10)", "toggle", _classic_menu(), {"note": "Se ve tras reiniciar el Explorador.", "restart_explorer": True}),

    ("lock_spotlight", "Pantalla de bloqueo", "Windows destacado (fotos de Bing)", "toggle", _spotlight(), {"note": "Desactívalo para usar tu propia imagen."}),
    ("lock_tips", "Pantalla de bloqueo", "Datos curiosos y sugerencias", "toggle", _lock_tips(), {}),
    ("logon_blur", "Pantalla de bloqueo", "Desenfoque en inicio de sesión", "toggle", _logon_blur(), {"admin": True}),

    ("animations", "Efectos y accesibilidad", "Animaciones de Windows", "toggle", _animations(), {}),
    ("text_scale", "Efectos y accesibilidad", "Tamaño del texto (%)", "slider", _text_scale(), {"min": 100, "max": 225, "step": 5, "note": "Algunas apps lo aplican al reabrirlas."}),
    ("cursor_size", "Efectos y accesibilidad", "Tamaño del puntero", "slider", _cursor_size(), {"min": 1, "max": 15, "step": 1}),
]

LINKS = [
    ("Fondo", "ms-settings:personalization-background"),
    ("Colores", "ms-settings:personalization-colors"),
    ("Temas", "ms-settings:themes"),
    ("Pantalla de bloqueo", "ms-settings:lockscreen"),
    ("Inicio", "ms-settings:personalization-start"),
    ("Barra de tareas", "ms-settings:taskbar"),
    ("Fuentes", "ms-settings:fonts"),
    ("Luz nocturna", "ms-settings:nightlight"),
    ("Pantalla", "ms-settings:display"),
    ("Puntero del mouse", "ms-settings:easeofaccess-mousepointer"),
    ("Efectos visuales", "ms-settings:easeofaccess-visualeffects"),
    ("Fecha y hora", "ms-settings:dateandtime"),
]

ACTIONS = [
    ("restart_explorer", "Reiniciar Explorador", "Aplica cambios de barra de tareas y menú contextual."),
]


def run_action(aid: str) -> str:
    if aid == "restart_explorer":
        subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True, creationflags=NOWIN)
        subprocess.Popen(["explorer.exe"], creationflags=NOWIN)
        return "Explorador reiniciado."
    raise ValueError("acción desconocida")


def open_link(target: str) -> None:
    if not target.startswith("ms-settings:"):
        raise ValueError("enlace no permitido")
    os.startfile(target)  # noqa: S606


def environment() -> str:
    return "Windows"
