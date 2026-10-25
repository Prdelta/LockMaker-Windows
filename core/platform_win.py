"""
LockMaker - aplicador para Windows 10/11.

- Fondo de escritorio : SystemParametersInfoW (sin admin, instantáneo).
- Pantalla de bloqueo : PersonalizationCSP (HKLM) -> requiere administrador.
                        Es el mismo mecanismo que usa Intune/MDM; funciona en
                        Home y Pro y NO bloquea el panel de Configuración.
- Pantalla de inicio  : en Windows 11 la pantalla de inicio de sesión muestra
                        la misma imagen de bloqueo. Se desactiva además el
                        "fondo borroso" (DisableAcrylicBackgroundOnLogon) para
                        que la imagen se vea nítida.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys

SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

STORE_DIR = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "LockMaker")
USER_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "LockMaker")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(args: list[str]) -> bool:
    """Vuelve a lanzar el proceso actual con UAC. Devuelve True si se lanzó."""
    try:
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in args)
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return int(r) > 32
    except Exception:
        return False


def _reg_set(root, key, name, value, kind="REG_SZ"):
    import winreg  # noqa
    hroot = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}[root]
    with winreg.CreateKeyEx(hroot, key, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
        if kind == "REG_DWORD":
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))
        else:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, str(value))


def _reg_delete(root, key, name):
    import winreg
    hroot = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}[root]
    try:
        with winreg.OpenKeyEx(hroot, key, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


def _store(src: str, name: str, system: bool) -> str:
    """Copia la imagen a una ruta estable y legible por SYSTEM/LogonUI."""
    d = STORE_DIR if system else USER_DIR
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, name)
    # Cambiar de nombre en cada aplicación evita que LogonUI use caché antigua
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    return dst


def set_wallpaper(path: str) -> str:
    dst = _store(path, "wallpaper.png", system=False)
    # Ajuste "Rellenar" (fill) para que no se deforme
    try:
        _reg_set("HKCU", r"Control Panel\Desktop", "WallpaperStyle", "10")
        _reg_set("HKCU", r"Control Panel\Desktop", "TileWallpaper", "0")
    except Exception:
        pass
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, dst, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    if not ok:
        raise OSError("SystemParametersInfoW falló")
    return dst


def set_lockscreen(path: str, also_logon: bool = True) -> str:
    """Requiere administrador. Usa PersonalizationCSP (método oficial MDM)."""
    if not is_admin():
        raise PermissionError("Se necesitan permisos de administrador para la pantalla de bloqueo.")
    dst = _store(path, "lockscreen.png", system=True)
    csp = r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
    _reg_set("HKLM", csp, "LockScreenImagePath", dst)
    _reg_set("HKLM", csp, "LockScreenImageUrl", dst)
    _reg_set("HKLM", csp, "LockScreenImageStatus", 1, "REG_DWORD")
    # Quitar "Contenido destacado de Windows" en el usuario actual para que
    # no sustituya la imagen con fotos de Bing.
    try:
        cdm = r"SOFTWARE\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
        _reg_set("HKCU", cdm, "RotatingLockScreenEnabled", 0, "REG_DWORD")
        _reg_set("HKCU", cdm, "RotatingLockScreenOverlayEnabled", 0, "REG_DWORD")
        _reg_set("HKCU", cdm, "SubscribedContent-338387Enabled", 0, "REG_DWORD")
    except Exception:
        pass
    if also_logon:
        # Pantalla de inicio de sesión nítida (sin desenfoque acrílico)
        _reg_set("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\System",
                 "DisableAcrylicBackgroundOnLogon", 1, "REG_DWORD")
    return dst


def restore_lockscreen() -> None:
    if not is_admin():
        raise PermissionError("Se necesitan permisos de administrador.")
    csp = r"SOFTWARE\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
    for n in ("LockScreenImagePath", "LockScreenImageUrl", "LockScreenImageStatus"):
        _reg_delete("HKLM", csp, n)
    _reg_delete("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\System",
                "DisableAcrylicBackgroundOnLogon")


# ---------------------------------------------------------------------------
# Fondo animado (GIF/MP4) mediante Lively Wallpaper (libre, gratuito)
# ---------------------------------------------------------------------------
LIVELY_URL = "https://github.com/rocksdanister/lively/releases"


def _livelycu() -> str | None:
    cands = [shutil.which("livelycu"), shutil.which("livelycu.exe"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "livelycu.exe"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Lively Wallpaper", "livelycu.exe"),
             os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Lively Wallpaper", "livelycu.exe"),
             os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Lively Wallpaper", "livelycu.exe")]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def set_live_wallpaper(path: str, persist: bool = False) -> str:
    """Reproduce el GIF/MP4 como fondo con Lively Wallpaper."""
    cu = _livelycu()
    if not cu:
        raise OSError("Lively Wallpaper no está instalado. Es libre y gratuito: " + LIVELY_URL +
                      " (o Microsoft Store). Tras instalarlo vuelve a pulsar; también puedes arrastrar el archivo a Lively.")
    dst = _store(path, "live" + os.path.splitext(path)[1], system=False)
    r = subprocess.run([cu, "setwp", "--file", dst], capture_output=True, text=True, creationflags=0x08000000)
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout).strip() or "livelycu devolvió error")
    return dst


def stop_live_wallpaper() -> None:
    cu = _livelycu()
    if cu:
        subprocess.run([cu, "closewp", "--monitor", "-1"], capture_output=True, text=True, creationflags=0x08000000)


# ---------------------------------------------------------------------------
# Actualización automática (fecha/hora "auto") con el Programador de tareas
# ---------------------------------------------------------------------------
TASK_NAME = "LockMaker AutoRefresh"


TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>LockMaker: re-renderiza y aplica la imagen (fecha/hora auto)</Description></RegistrationInfo>
  <Triggers>
    <TimeTrigger><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled>
      <Repetition><Interval>PT{minutes}M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition></TimeTrigger>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
    <SessionStateChangeTrigger><Enabled>true</Enabled><StateChange>SessionUnlock</StateChange></SessionStateChangeTrigger>
    <SessionStateChangeTrigger><Enabled>true</Enabled><StateChange>SessionLock</StateChange></SessionStateChangeTrigger>
    <SessionStateChangeTrigger><Enabled>true</Enabled><StateChange>ConsoleConnect</StateChange></SessionStateChangeTrigger>
    <EventTrigger><Enabled>true</Enabled><Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="System"&gt;&lt;Select Path="System"&gt;*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription></EventTrigger>
  </Triggers>
  <Principals><Principal id="Author">{principal}</Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>{cmd}</Command><Arguments>{args}</Arguments></Exec></Actions>
</Task>
"""


def install_autorefresh(script: str, preset: str, every_minutes: int = 1, targets: str = "wallpaper") -> str:
    """Crea la tarea programada que re-renderiza y aplica la imagen.

    Se dispara: cada N minutos, al iniciar sesión, al bloquear/desbloquear, al
    conectar la consola y al despertar del reposo. Para 'lock'/'login' corre como
    SYSTEM (puede escribir HKLM); para 'wallpaper' como el usuario actual.
    """
    import datetime as _dt
    from xml.sax.saxutils import escape
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    args = f'"{script}" apply --preset "{preset}" --targets {targets} --quiet'
    every_minutes = max(1, int(every_minutes))
    if any(t in targets for t in ("lock", "login")):
        principal = "<UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel>"
    else:
        user = os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get("USERNAME", "")
        principal = f"<UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel>"
    xml = TASK_XML.format(start=_dt.datetime.now().strftime("%Y-%m-%dT%H:%M:00"), minutes=every_minutes,
                          principal=principal, cmd=escape(pyw), args=escape(args))
    xml_path = os.path.join(USER_DIR, "task.xml")
    os.makedirs(USER_DIR, exist_ok=True)
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)
    r = subprocess.run(["schtasks", "/Create", "/F", "/TN", TASK_NAME, "/XML", xml_path],
                       capture_output=True, text=True, creationflags=0x08000000)
    if r.returncode != 0:
        raise OSError(r.stderr.strip() or r.stdout.strip())
    # primera ejecución inmediata
    subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, creationflags=0x08000000)
    return TASK_NAME + " (cada %d min + inicio de sesión + bloquear/desbloquear + reposo)" % every_minutes


def uninstall_autorefresh() -> None:
    subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
                   capture_output=True, text=True, creationflags=0x08000000)


def info() -> dict:
    return {
        "os": "windows",
        "admin": is_admin(),
        "store": STORE_DIR,
        "capabilities": {
            "wallpaper": True,
            "lock": True,
            "login": True,
            "live": True,
            "live_player": "Lively Wallpaper" + ("" if _livelycu() else " (no instalado)"),
            "needs_admin": ["lock", "login"],
        },
        "notes": [
            "Pantalla de bloqueo e inicio requieren ejecutar como administrador (se pedirá UAC).",
            "La imagen de inicio de sesión en Windows 11 es la misma que la de bloqueo.",
        ],
    }
