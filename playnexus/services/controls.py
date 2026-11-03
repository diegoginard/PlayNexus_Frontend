"""
Módulo de gestión y configuración de controles y teclado de PlayNexus.
Permite asignar teclas personalizadas para navegación, selección y cierre de emuladores,
guardando la configuración en la base de datos de PlayNexus.
"""

from PySide6.QtCore import Qt

# Identificadores de acciones configurables
ACTION_CLOSE_EMULATOR = "close_emulator"
ACTION_CLOSE_FRONTEND = "close_frontend"
ACTION_NAV_UP = "nav_up"
ACTION_NAV_DOWN = "nav_down"
ACTION_NAV_LETTER_BACK = "nav_letter_back"
ACTION_NAV_LETTER_FWD = "nav_letter_fwd"
ACTION_NAV_STEP5_BACK = "nav_step5_back"
ACTION_NAV_STEP5_FWD = "nav_step5_fwd"
ACTION_SELECT = "select_game"
ACTION_NAV_BACK = "nav_back"
ACTION_MUTE = "mute_video"
ACTION_TOGGLE_FPS = "toggle_fps"

# Compatibilidad con identificadores anteriores
ACTION_NAV_LETTER = ACTION_NAV_LETTER_FWD
ACTION_NAV_STEP5 = ACTION_NAV_STEP5_FWD
ACTION_PAGE_UP = ACTION_NAV_STEP5_BACK
ACTION_PAGE_DOWN = ACTION_NAV_STEP5_FWD

# Metadatos de cada acción (nombre para mostrar, descripción, tecla por defecto y botón mando por defecto)
ACTIONS_INFO = [
    {
        "id": ACTION_NAV_UP,
        "name": "Subir (Ruleta / Lista)",
        "desc": "Sube un elemento en la ruleta de juegos o en las listas",
        "default": "Up",
        "default_pad": "D-Pad Up",
    },
    {
        "id": ACTION_NAV_DOWN,
        "name": "Bajar (Ruleta / Lista)",
        "desc": "Baja un elemento en la ruleta de juegos o en las listas",
        "default": "Down",
        "default_pad": "D-Pad Down",
    },
    {
        "id": ACTION_NAV_LETTER_BACK,
        "name": "Saltar letra hacia atrás",
        "desc": "Salta al primer juego de la letra anterior en orden alfabético",
        "default": "Left",
        "default_pad": "D-Pad Left",
    },
    {
        "id": ACTION_NAV_LETTER_FWD,
        "name": "Saltar letra hacia adelante",
        "desc": "Salta al primer juego de la siguiente letra en orden alfabético",
        "default": "Right",
        "default_pad": "D-Pad Right",
    },
    {
        "id": ACTION_NAV_STEP5_BACK,
        "name": "Saltar de 5 en 5 hacia atrás",
        "desc": "Retrocede rápidamente saltando de 5 en 5 juegos en la lista",
        "default": "PageUp",
        "default_pad": "LB",
    },
    {
        "id": ACTION_NAV_STEP5_FWD,
        "name": "Saltar de 5 en 5 hacia adelante",
        "desc": "Avanza rápidamente saltando de 5 en 5 juegos en la lista",
        "default": "PageDown",
        "default_pad": "RB",
    },
    {
        "id": ACTION_SELECT,
        "name": "Seleccionar / Entrar / Ejecutar",
        "desc": "Ejecuta el juego o entra al sistema o lista seleccionada",
        "default": "Return",
        "default_pad": "A",
    },
    {
        "id": ACTION_NAV_BACK,
        "name": "Volver atrás (Menús / Listas)",
        "desc": "Retrocede al menú anterior o lista de listas en navegación jerárquica",
        "default": "Backspace",
        "default_pad": "B",
    },
    {
        "id": ACTION_CLOSE_FRONTEND,
        "name": "Cerrar frontend (PlayNexus)",
        "desc": "Cierra la ventana del frontend y vuelve al sistema",
        "default": "Escape",
        "default_pad": "",
    },
    {
        "id": ACTION_CLOSE_EMULATOR,
        "name": "Cerrar emulador en ejecución",
        "desc": "Cierra el proceso del emulador activo y restaura el frontend",
        "default": "Escape",
        "default_pad": "Back+Start",
    },
    {
        "id": ACTION_MUTE,
        "name": "Silenciar / Activar audio video",
        "desc": "Alterna el sonido del video snap en el diseño visual",
        "default": "M",
        "default_pad": "Y",
    },
    {
        "id": ACTION_TOGGLE_FPS,
        "name": "Mostrar / Ocultar FPS (Overlay)",
        "desc": "Alterna la visualización del contador de FPS, tiempo de render y resolución en pantalla",
        "default": "F10",
        "default_pad": "R-Thumb",
    },
]

# Mapa de nombres legibles a códigos de teclas virtuales de Windows (VK Codes)
VK_MAP = {
    "Escape": 0x1B,
    "Return": 0x0D,
    "Enter": 0x0D,
    "Space": 0x20,
    "Up": 0x26,
    "Down": 0x28,
    "Left": 0x25,
    "Right": 0x27,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "Home": 0x24,
    "End": 0x23,
    "Tab": 0x09,
    "Backspace": 0x08,
    "Delete": 0x2E,
    "Insert": 0x2D,
    "F1": 0x70,
    "F2": 0x71,
    "F3": 0x72,
    "F4": 0x73,
    "F5": 0x74,
    "F6": 0x75,
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
}

# Mapa exhaustivo de Qt.Key a nombres amigables
QT_TO_NAME = {
    Qt.Key_Escape: "Escape",
    Qt.Key_Return: "Return",
    Qt.Key_Enter: "Return",
    Qt.Key_Space: "Space",
    Qt.Key_Up: "Up",
    Qt.Key_Down: "Down",
    Qt.Key_Left: "Left",
    Qt.Key_Right: "Right",
    Qt.Key_PageUp: "PageUp",
    Qt.Key_PageDown: "PageDown",
    Qt.Key_Home: "Home",
    Qt.Key_End: "End",
    Qt.Key_Tab: "Tab",
    Qt.Key_Backtab: "Tab",
    Qt.Key_Backspace: "Backspace",
    Qt.Key_Delete: "Delete",
    Qt.Key_Insert: "Insert",
    Qt.Key_F1: "F1",
    Qt.Key_F2: "F2",
    Qt.Key_F3: "F3",
    Qt.Key_F4: "F4",
    Qt.Key_F5: "F5",
    Qt.Key_F6: "F6",
    Qt.Key_F7: "F7",
    Qt.Key_F8: "F8",
    Qt.Key_F9: "F9",
    Qt.Key_F10: "F10",
    Qt.Key_F11: "F11",
    Qt.Key_F12: "F12",
}

# Agregar letras A-Z y números 0-9 al diccionario
for _c in range(ord('A'), ord('Z') + 1):
    _ch = chr(_c)
    _qt = getattr(Qt, f"Key_{_ch}", None)
    if _qt is not None:
        QT_TO_NAME[_qt] = _ch
        VK_MAP.setdefault(_ch, _c)

for _n in range(10):
    _ch = str(_n)
    _qt = getattr(Qt, f"Key_{_ch}", None)
    if _qt is not None:
        QT_TO_NAME[_qt] = _ch
        VK_MAP.setdefault(_ch, ord('0') + _n)

# Mapa invertido de nombres a lista de Qt.Key equivalentes
NAME_TO_QT = {}
for _k, _name in QT_TO_NAME.items():
    NAME_TO_QT.setdefault(_name, []).append(_k)
NAME_TO_QT.setdefault("Enter", [Qt.Key_Return, Qt.Key_Enter])

# Alias secundarios por defecto (por conveniencia de teclado)
ACTION_ALIASES = {
    ACTION_NAV_UP: [Qt.Key_Up, Qt.Key_W, Qt.Key_K],
    ACTION_NAV_DOWN: [Qt.Key_Down, Qt.Key_S, Qt.Key_J],
    ACTION_NAV_LETTER_BACK: [Qt.Key_Left, Qt.Key_A],
    ACTION_NAV_LETTER_FWD: [Qt.Key_Right, Qt.Key_D],
    ACTION_NAV_STEP5_BACK: [Qt.Key_PageUp],
    ACTION_NAV_STEP5_FWD: [Qt.Key_PageDown],
    ACTION_NAV_BACK: [Qt.Key_Backspace],
    ACTION_SELECT: [Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space],
    ACTION_CLOSE_FRONTEND: [Qt.Key_Escape],
    ACTION_CLOSE_EMULATOR: [Qt.Key_Escape],
    ACTION_TOGGLE_FPS: [Qt.Key_F10, Qt.Key_F3],
}

# Alias secundarios por defecto para mandos y joysticks
GAMEPAD_ACTION_ALIASES = {
    ACTION_NAV_UP: ["D-Pad Up", "L-Stick Up", "POV Up", "Axis Y-"],
    ACTION_NAV_DOWN: ["D-Pad Down", "L-Stick Down", "POV Down", "Axis Y+"],
    ACTION_NAV_LETTER_BACK: ["D-Pad Left", "L-Stick Left", "POV Left", "Axis X-"],
    ACTION_NAV_LETTER_FWD: ["D-Pad Right", "L-Stick Right", "POV Right", "Axis X+"],
    ACTION_NAV_STEP5_BACK: ["LB", "Button 5"],
    ACTION_NAV_STEP5_FWD: ["RB", "Button 6"],
    ACTION_SELECT: ["A", "Start", "Button 1"],
    ACTION_NAV_BACK: ["B", "Back", "Button 2"],
    ACTION_CLOSE_FRONTEND: ["Back+Start"],
    ACTION_CLOSE_EMULATOR: ["Back+Start"],
    ACTION_MUTE: ["Y", "Button 4"],
    ACTION_TOGGLE_FPS: ["R-Thumb", "Button 10", "R3", "RS"],
}


def key_name_to_vk(key_name: str) -> int:
    """Convierte un nombre de tecla (o shortcut) a su código Virtual Key (VK) de Windows."""
    name = (key_name or "").strip()
    if "+" in name:
        name = name.split("+")[-1].strip()
    if name in VK_MAP:
        return VK_MAP[name]
    if len(name) == 1:
        ch = name.upper()
        if 'A' <= ch <= 'Z' or '0' <= ch <= '9':
            return ord(ch)
    return 0x1B  # Fallback a VK_ESCAPE


def qt_key_to_name(qt_key: int) -> str:
    """Convierte un código Qt.Key a un nombre de tecla legible."""
    if qt_key in QT_TO_NAME:
        return QT_TO_NAME[qt_key]
    if Qt.Key_A <= qt_key <= Qt.Key_Z:
        return chr(qt_key - Qt.Key_A + ord('A'))
    if Qt.Key_0 <= qt_key <= Qt.Key_9:
        return chr(qt_key - Qt.Key_0 + ord('0'))
    return f"Key_{qt_key}"


def qt_event_to_shortcut_name(event) -> str:
    """Construye un nombre amigable para un evento de teclado, incluyendo modificadores."""
    key = event.key()
    modifiers = event.modifiers()

    mod_parts = []
    if modifiers & Qt.ControlModifier:
        mod_parts.append("Ctrl")
    if modifiers & Qt.AltModifier:
        mod_parts.append("Alt")
    if modifiers & Qt.ShiftModifier and key not in (Qt.Key_Shift,):
        # Solo agregar Shift si la tecla no es Shift sola
        mod_parts.append("Shift")
    if modifiers & Qt.MetaModifier:
        mod_parts.append("Win")

    base_name = qt_key_to_name(key)
    if mod_parts and base_name not in ("Control", "Shift", "Alt", "Meta"):
        return f"{'+'.join(mod_parts)}+{base_name}"
    return base_name


def parse_shortcut(shortcut_str: str) -> tuple[list[int], int]:
    """
    Parsea una cadena como 'Ctrl+Q' o 'Escape' y retorna:
    (lista de Qt.Key posibles, máscara de modificadores Qt.KeyboardModifier)
    """
    s = (shortcut_str or "").strip()
    if not s:
        return ([Qt.Key_Escape], 0)

    parts = [p.strip() for p in s.split("+")]
    base_name = parts[-1]
    mod_mask = 0

    for m in parts[:-1]:
        m_lower = m.lower()
        if m_lower == "ctrl":
            mod_mask |= int(getattr(Qt.ControlModifier, "value", Qt.ControlModifier))
        elif m_lower == "alt":
            mod_mask |= int(getattr(Qt.AltModifier, "value", Qt.AltModifier))
        elif m_lower == "shift":
            mod_mask |= int(getattr(Qt.ShiftModifier, "value", Qt.ShiftModifier))
        elif m_lower in ("win", "meta", "cmd"):
            mod_mask |= int(getattr(Qt.MetaModifier, "value", Qt.MetaModifier))

    keys = name_to_qt_keys(base_name)
    return (keys, mod_mask)


def name_to_qt_keys(key_name: str) -> list[int]:
    """Convierte un nombre de tecla a los códigos Qt.Key equivalentes."""
    name = (key_name or "").strip()
    if "+" in name:
        name = name.split("+")[-1].strip()
    if name in NAME_TO_QT:
        return NAME_TO_QT[name]
    if len(name) == 1:
        ch = name.upper()
        if 'A' <= ch <= 'Z':
            return [Qt.Key_A + (ord(ch) - ord('A'))]
        if '0' <= ch <= '9':
            return [Qt.Key_0 + (ord(ch) - ord('0'))]
    return [Qt.Key_Escape]


def get_binding(db, action: str) -> str:
    """Obtiene el nombre de la tecla configurada para una acción, o su valor predeterminado."""
    default = "Escape"
    for info in ACTIONS_INFO:
        if info["id"] == action:
            default = info["default"]
            break
    if db is None:
        try:
            from playnexus.db import Database
            db = Database()
        except Exception:
            return default

    # Compatibilidad con acciones redirigidas o alias anteriores
    val = db.get_setting(f"control_{action}", None)
    if val is not None and str(val).strip():
        return str(val).strip()

    # Compatibilidad con claves históricas en la base de datos
    if action == ACTION_NAV_LETTER_BACK:
        old = db.get_setting("control_nav_letter", None)
        if old:
            return str(old).strip()
    elif action == ACTION_NAV_STEP5_BACK:
        old = db.get_setting("control_page_up", None)
        if old:
            return str(old).strip()
    elif action == ACTION_NAV_STEP5_FWD:
        old = db.get_setting("control_page_down", None)
        if old:
            return str(old).strip()
    elif action == "page_up":
        return get_binding(db, ACTION_NAV_STEP5_BACK)
    elif action == "page_down":
        return get_binding(db, ACTION_NAV_STEP5_FWD)
    elif action == "nav_letter":
        return get_binding(db, ACTION_NAV_LETTER_FWD)
    elif action == "nav_step5":
        return get_binding(db, ACTION_NAV_STEP5_FWD)

    return default


def set_binding(db, action: str, key_name: str):
    """Guarda una asignación de tecla en la base de datos."""
    if db:
        db.set_setting(f"control_{action}", key_name.strip())


def reset_default_bindings(db):
    """Restablece todas las teclas y mandos a sus valores predeterminados."""
    if db:
        for info in ACTIONS_INFO:
            db.set_setting(f"control_{info['id']}", info["default"])
            db.set_setting(f"gamepad_{info['id']}", info.get("default_pad", ""))


def get_gamepad_binding(db, action: str) -> str:
    """Obtiene el botón de joystick configurado para una acción, o su valor predeterminado."""
    default = ""
    for info in ACTIONS_INFO:
        if info["id"] == action:
            default = info.get("default_pad", "")
            break
    if db is None:
        try:
            from playnexus.db import Database
            db = Database()
        except Exception:
            return default

    val = db.get_setting(f"gamepad_{action}", None)
    if val is not None:
        return str(val).strip()

    if action == ACTION_NAV_LETTER_BACK:
        old = db.get_setting("gamepad_nav_letter", None)
        if old is not None and str(old).strip():
            return str(old).strip()
    elif action == ACTION_NAV_STEP5_BACK:
        old = db.get_setting("gamepad_page_up", None)
        if old is not None and str(old).strip():
            return str(old).strip()
    elif action == ACTION_NAV_STEP5_FWD:
        old = db.get_setting("gamepad_page_down", None)
        if old is not None and str(old).strip():
            return str(old).strip()
    elif action == "page_up":
        return get_gamepad_binding(db, ACTION_NAV_STEP5_BACK)
    elif action == "page_down":
        return get_gamepad_binding(db, ACTION_NAV_STEP5_FWD)
    elif action == "nav_letter":
        return get_gamepad_binding(db, ACTION_NAV_LETTER_FWD)
    elif action == "nav_step5":
        return get_gamepad_binding(db, ACTION_NAV_STEP5_FWD)

    return default


def set_gamepad_binding(db, action: str, pad_btn: str):
    """Guarda una asignación de botón de mando en la base de datos."""
    if db:
        db.set_setting(f"gamepad_{action}", pad_btn.strip())
        try:
            from playnexus.services.gamepad import get_gamepad_manager
            get_gamepad_manager(db).refresh_bindings()
        except Exception:
            pass


def reset_default_gamepad_bindings(db):
    """Restablece todos los botones de joystick a sus valores predeterminados."""
    if db:
        for info in ACTIONS_INFO:
            db.set_setting(f"gamepad_{info['id']}", info.get("default_pad", ""))
        try:
            from playnexus.services.gamepad import get_gamepad_manager
            get_gamepad_manager(db).refresh_bindings()
        except Exception:
            pass


def get_all_bindings(db=None) -> list[dict]:
    """Retorna una lista con la información completa, tecla actual y botón de joystick de cada acción."""
    result = []
    for info in ACTIONS_INFO:
        current_key = get_binding(db, info["id"])
        current_pad = get_gamepad_binding(db, info["id"])
        result.append({
            "id": info["id"],
            "name": info["name"],
            "desc": info["desc"],
            "key": current_key,
            "default": info["default"],
            "pad": current_pad,
            "default_pad": info.get("default_pad", "A"),
        })
    return result


def matches_action(event_or_key, action: str, db=None) -> bool:
    """
    Verifica si una tecla o evento QKeyEvent coincide con la acción asignada,
    soportando modificadores (ej: Ctrl+Q) y alias secundarios por defecto.
    Acepta tanto un objeto QKeyEvent como un entero Qt.Key.
    """
    if hasattr(event_or_key, "key"):
        ev_key = event_or_key.key()
        mods = event_or_key.modifiers()
        ev_mods = int(getattr(mods, "value", mods))
    else:
        ev_key = int(event_or_key)
        ev_mods = 0

    assigned = get_binding(db, action)
    target_keys, req_mods = parse_shortcut(assigned)

    ctrl_val = int(getattr(Qt.ControlModifier, "value", Qt.ControlModifier))
    alt_val = int(getattr(Qt.AltModifier, "value", Qt.AltModifier))
    ctrl_alt = ctrl_val | alt_val

    # Si se especificaron modificadores requeridos (ej: Ctrl+Q, Alt+F4)
    if req_mods != 0:
        if ev_key in target_keys and (ev_mods & req_mods) == req_mods:
            return True
    else:
        # Si la acción asignada no requiere modificadores, ignorar si Ctrl o Alt están activos
        if ev_mods & ctrl_alt:
            return False
        if ev_key in target_keys:
            return True

    # Si la acción está en su valor predeterminado, admitir también alias secundarios estándar
    default = next((info["default"] for info in ACTIONS_INFO if info["id"] == action), "")
    if assigned == default and action in ACTION_ALIASES:
        if ev_key in ACTION_ALIASES[action] and not (ev_mods & ctrl_alt):
            return True

    return False


def matches_gamepad_action(pressed_inputs: set[str], action: str, db=None) -> bool:
    """
    Verifica si el conjunto de entradas activas de joystick coincide con la acción asignada,
    soportando combinaciones compuestas (ej: Back+Start) y alias secundarios por defecto.
    """
    if not pressed_inputs:
        return False

    assigned = get_gamepad_binding(db, action)
    if not assigned or assigned in ("Sin asignar", "-"):
        return False

    # Si es una combinación compuesta por '+' (ej: Back+Start)
    if "+" in assigned:
        parts = [p.strip() for p in assigned.split("+")]
        if all(p in pressed_inputs for p in parts):
            return True
    else:
        if assigned in pressed_inputs:
            return True

    # Si está en el valor predeterminado, admitir alias secundarios estándar
    default_pad = next((info.get("default_pad", "") for info in ACTIONS_INFO if info["id"] == action), "")
    if assigned == default_pad and action in GAMEPAD_ACTION_ALIASES:
        for alias in GAMEPAD_ACTION_ALIASES[action]:
            if "+" in alias:
                parts = [p.strip() for p in alias.split("+")]
                if all(p in pressed_inputs for p in parts):
                    return True
            elif alias in pressed_inputs:
                return True

    return False
