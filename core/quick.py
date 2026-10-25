"""
Ajustes rápidos: capa común Windows/Linux.

- list_settings(): ajustes disponibles con su valor ACTUAL leído del sistema.
- set_setting(id, valor): aplica; antes guarda el valor original (1ª vez) para
  poder restaurarlo con restore_all(). Nada se aplica sin que el usuario lo pida.
"""
from __future__ import annotations

import json
import os
import sys

_impl = None
try:
    if sys.platform.startswith("win"):
        from . import quick_win as _impl  # noqa: F401
    elif sys.platform.startswith("linux"):
        from . import quick_linux as _impl  # noqa: F401
except ImportError:
    _impl = None

SNAP_FILE = None  # lo fija lockmaker.py (carpeta de datos del usuario)


def _items():
    """Devuelve (dict id->item normalizado, links, actions, entorno)."""
    if _impl is None:
        return {}, [], [], sys.platform
    if sys.platform.startswith("win"):
        items = {}
        for iid, group, label, kind, (get, set_), extra in _impl.ITEMS:
            items[iid] = {"avail": lambda: True, "get": get, "set": set_, "type": kind,
                          "label": label, "group": group, "extra": extra}
        links = [{"label": l, "target": t} for l, t in _impl.LINKS]
        actions = [{"id": a, "label": l, "note": n} for a, l, n in _impl.ACTIONS]
        return items, links, actions, "Windows"
    items, links, kind = _impl.build()
    links = [{"label": l, "target": f"{tool}:{page}"} for tool, l, page in links]
    return items, links, [], kind


def _load_snap() -> dict:
    try:
        with open(SNAP_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, TypeError, json.JSONDecodeError):
        return {}


def _save_snap(d: dict):
    if not SNAP_FILE:
        return
    os.makedirs(os.path.dirname(SNAP_FILE), exist_ok=True)
    with open(SNAP_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def list_settings() -> dict:
    from concurrent.futures import ThreadPoolExecutor
    items, links, actions, env = _items()
    snap = _load_snap()

    def read(it):
        try:
            return (True, it["get"]()) if it["avail"]() else (False, None)
        except Exception:  # noqa: BLE001  (ajuste que no existe en esta versión)
            return False, None
    with ThreadPoolExecutor(max_workers=8) as ex:
        values = dict(zip(items.keys(), ex.map(read, items.values())))
    out = []
    for iid, it in items.items():
        ok, val = values[iid]
        if not ok:
            continue
        if val is None and it["type"] != "toggle":
            continue
        ex = dict(it["extra"])
        if it["type"] == "select":
            opts = [str(o) for o in ex.get("options", [])]
            if not opts:
                continue
            if val is not None and str(val) not in opts:
                opts = [str(val)] + opts
            ex["options"] = opts
        out.append({"id": iid, "group": it["group"], "label": it["label"], "type": it["type"],
                    "value": val, "changed": iid in snap, **ex})
    return {"env": env, "items": out, "links": links, "actions": actions, "changed": len(snap)}


def set_setting(iid: str, value) -> dict:
    items, *_ = _items()
    it = items.get(iid)
    if not it:
        raise KeyError("ajuste desconocido: " + iid)
    snap = _load_snap()
    if iid not in snap:
        try:
            snap[iid] = it["get"]()
        except Exception:  # noqa: BLE001
            snap[iid] = None
    it["set"](value)
    # si volvió al valor original, ya no cuenta como cambio
    try:
        now = it["get"]()
    except Exception:  # noqa: BLE001
        now = value
    if snap.get(iid) == now:
        snap.pop(iid, None)
    _save_snap(snap)
    return {"id": iid, "value": now, "changed": iid in snap,
            "restart_explorer": bool(it["extra"].get("restart_explorer"))}


def restore_all() -> dict:
    items, *_ = _items()
    snap = _load_snap()
    done, errors = [], {}
    for iid, old in list(snap.items()):
        it = items.get(iid)
        if it is None or old is None:
            snap.pop(iid, None)
            continue
        try:
            it["set"](old)
            done.append(iid)
            snap.pop(iid, None)
        except Exception as e:  # noqa: BLE001
            errors[iid] = str(e)
    _save_snap(snap)
    return {"restored": done, "errors": errors}


def open_link(target: str):
    _impl.open_link(target)


def run_action(aid: str) -> str:
    return _impl.run_action(aid)
