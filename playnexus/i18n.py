"""Motor de internacionalización (i18n) basado en archivos `.txt` planos en `lang/`.

Formato de cada archivo `lang/<codigo>.txt` (codificación UTF-8):
    # Comentarios opcionales con '#'
    _lang_code = en
    _lang_name = English
    app.ready = PlayNexus ready.

Soporta cualquier idioma adicional creando un nuevo `.txt` en la carpeta `lang/`.
Si alguna clave falta en el idioma activo, respalda en `en.txt` y luego en el texto
por defecto pasado a `tr(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

DEFAULT_LANGUAGE_CODE = "en"


def _resolve_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_lang_dir() -> Path:
    """Devuelve la carpeta `lang/` activa junto al ejecutable o raíz del proyecto."""
    primary = _resolve_app_dir() / "lang"
    if primary.is_dir():
        return primary
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "lang"
        if bundled.is_dir():
            return bundled
    return primary


LANG_DIR: Path = get_lang_dir()


@dataclass(frozen=True)
class LanguagePack:
    code: str
    name: str
    path: Path
    strings: dict[str, str]


_INITIALIZED: bool = False
_CURRENT_CODE: str = DEFAULT_LANGUAGE_CODE
_ACTIVE_PACK: dict[str, str] = {}
_FALLBACK_EN: dict[str, str] = {}


def _unescape_value(raw: str) -> str:
    """Convierte secuencias escapadas (`\\n`, `\\t`, `\\r`, `\\\\`) en caracteres reales."""
    if not raw or "\\" not in raw:
        return raw
    out: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == "\\" and i + 1 < n:
            nxt = raw[i + 1]
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "t":
                out.append("\t")
                i += 2
                continue
            if nxt == "r":
                i += 2
                continue
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_lang_file(path: Path) -> LanguagePack:
    """Lee un archivo `.txt` de idioma (`clave = valor`) y extrae sus metadatos."""
    strings: dict[str, str] = {}
    stem_code = path.stem.strip().lower() or DEFAULT_LANGUAGE_CODE
    code = stem_code
    name = path.stem.strip() or stem_code.upper()
    try:
        raw_text = path.read_text(encoding="utf-8-sig", errors="replace")
        for raw_line in raw_text.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, v = raw_line.rstrip("\r\n").split("=", 1)
            key = k.strip().lstrip("\ufeff")
            if not key or key.startswith("#"):
                continue
            raw_val = v[1:] if v.startswith(" ") else v
            val = _unescape_value(raw_val)
            if key == "_lang_code":
                if val.strip():
                    code = val.strip().lower()
                continue
            if key == "_lang_name":
                if val.strip():
                    name = val.strip()
                continue
            strings[key] = val
    except Exception:
        pass
    return LanguagePack(code=code, name=name, path=path, strings=strings)


def discover_languages(lang_dir: Path | None = None) -> list[dict[str, str]]:
    """Lista los idiomas disponibles leyendo dinámicamente todos los `.txt` en `lang/`."""
    folder = lang_dir or get_lang_dir()
    if not folder.is_dir():
        return []

    found: list[LanguagePack] = []
    seen_codes: set[str] = set()
    for txt_path in sorted(folder.glob("*.txt"), key=lambda p: p.name.lower()):
        pack = parse_lang_file(txt_path)
        if pack.code in seen_codes:
            continue
        seen_codes.add(pack.code)
        found.append(pack)

    priority = {"en": 0, "es": 1}
    found.sort(key=lambda p: (priority.get(p.code, 2), p.name.lower(), p.code))
    return [
        {"code": p.code, "name": p.name, "path": str(p.path)}
        for p in found
    ]


def _find_pack_by_code(code: str, lang_dir: Path | None = None) -> LanguagePack | None:
    folder = lang_dir or get_lang_dir()
    if not folder.is_dir():
        return None
    norm = (code or "").strip().lower()
    if not norm:
        return None
    direct = folder / f"{norm}.txt"
    if direct.is_file():
        return parse_lang_file(direct)
    for txt_path in sorted(folder.glob("*.txt"), key=lambda p: p.name.lower()):
        pack = parse_lang_file(txt_path)
        if pack.code == norm or txt_path.stem.strip().lower() == norm:
            return pack
    return None


def _read_setting_from_disk(key: str, default: str = "") -> str:
    settings_path = _resolve_app_dir() / "config" / "settings.txt"
    if not settings_path.is_file():
        return default
    try:
        text = settings_path.read_text(encoding="utf-8-sig", errors="replace")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                val = v.strip()
                return val or default
    except Exception:
        pass
    return default


def set_language(lang_code: str, lang_dir: Path | None = None) -> str:
    """Carga en memoria el paquete de idioma indicado (`en` por defecto si falta)."""
    global _INITIALIZED, _CURRENT_CODE, _ACTIVE_PACK, _FALLBACK_EN

    folder = lang_dir or get_lang_dir()
    en_pack = _find_pack_by_code(DEFAULT_LANGUAGE_CODE, folder)
    _FALLBACK_EN = dict(en_pack.strings) if en_pack else {}

    requested = (lang_code or DEFAULT_LANGUAGE_CODE).strip().lower() or DEFAULT_LANGUAGE_CODE
    active = _find_pack_by_code(requested, folder)
    if active is None and requested != DEFAULT_LANGUAGE_CODE:
        active = en_pack

    if active is not None:
        _CURRENT_CODE = active.code
        _ACTIVE_PACK = dict(active.strings)
    else:
        _CURRENT_CODE = requested
        _ACTIVE_PACK = {}

    _INITIALIZED = True
    return _CURRENT_CODE


def init_i18n(db: Any = None, default_lang: str = DEFAULT_LANGUAGE_CODE) -> str:
    """Inicializa el idioma activo leyendo `app_language` desde `db` o `config/settings.txt`."""
    raw_code = ""
    if db is not None and hasattr(db, "get_setting"):
        try:
            raw_code = str(db.get_setting("app_language", "") or "").strip().lower()
        except Exception:
            raw_code = ""
    if not raw_code:
        raw_code = _read_setting_from_disk("app_language", default_lang).strip().lower()
    return set_language(raw_code or default_lang)


def get_current_language() -> str:
    """Devuelve el código del idioma actualmente activo."""
    if not _INITIALIZED:
        init_i18n()
    return _CURRENT_CODE


def tr(key: str, default: str | None = None, **kwargs: Any) -> str:
    """Traduce `key` usando el idioma activo, respaldo `en.txt` o `default`.

    Si se pasan argumentos nominales (`kwargs`), formatea de manera tolerante
    ante placeholders incompletos en archivos traducidos por usuarios.
    """
    if not _INITIALIZED:
        init_i18n()

    text = _ACTIVE_PACK.get(key)
    if text is None or text == "":
        text = _FALLBACK_EN.get(key)
    if text is None or text == "":
        text = default if default is not None else key

    if kwargs and text:
        try:
            return text.format(**kwargs)
        except Exception:
            if default:
                try:
                    return default.format(**kwargs)
                except Exception:
                    return default
    return text


def restart_current_application(widget: Any = None) -> bool:
    """Relanza el proceso actual de PlayNexus y solicita el cierre limpio de la ventana."""
    import subprocess

    app_dir = _resolve_app_dir()
    try:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, *sys.argv[1:]]
        else:
            argv0 = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
            if argv0 is not None and argv0.name == "__main__.py":
                cmd = [sys.executable, "-m", "playnexus", *sys.argv[1:]]
            elif argv0 is not None and argv0.is_file():
                cmd = [sys.executable, str(argv0), *sys.argv[1:]]
            else:
                cmd = [sys.executable, "-m", "playnexus"]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        subprocess.Popen(cmd, cwd=str(app_dir), creationflags=creationflags)
    except Exception:
        return False

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if widget is not None and hasattr(widget, "window"):
            win = widget.window()
            if win is not None and hasattr(win, "close"):
                QTimer.singleShot(50, win.close)
        if app is not None:
            QTimer.singleShot(150, app.quit)
    except Exception:
        pass
    return True
