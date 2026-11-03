"""
Servicio centralizado de detección y gestión de Mandos y Joysticks para PlayNexus.
Soporta mandos XInput (Xbox 360, Xbox One, Xbox Series, 8BitDo y compatibles) y
mandos DirectInput / Arcade / genéricos USB mediante Windows Multimedia (WinMM).
Permite navegación simultánea con teclado y joystick, y asignación interactiva.
"""

import sys
import time
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QObject, Signal, QThread

from playnexus.services.controls import (
    ACTIONS_INFO, ACTION_NAV_UP, ACTION_NAV_DOWN,
    ACTION_NAV_LETTER_BACK, ACTION_NAV_LETTER_FWD,
    ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD,
    ACTION_NAV_BACK, ACTION_SELECT, ACTION_PAGE_UP, ACTION_PAGE_DOWN,
    ACTION_CLOSE_FRONTEND, ACTION_CLOSE_EMULATOR,
    ACTION_MUTE, ACTION_TOGGLE_FPS, ACTION_TOGGLE_BEZEL, GAMEPAD_ACTION_ALIASES,
    get_gamepad_binding, matches_gamepad_action
)

# Estructuras para XInput
class _XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad", _XINPUT_GAMEPAD),
    ]


# Estructuras para WinMM (DirectInput / Joystick genérico)
class _JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD),
        ("dwYpos", wintypes.DWORD),
        ("dwZpos", wintypes.DWORD),
        ("dwRpos", wintypes.DWORD),
        ("dwUpos", wintypes.DWORD),
        ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD),
        ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("dwReserved2", wintypes.DWORD),
    ]


# Cargar bibliotecas de Windows una sola vez
_XINPUT_DLL = None
_WINMM_DLL = None

if sys.platform == "win32":
    for dll_name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            _XINPUT_DLL = ctypes.windll.LoadLibrary(dll_name)
            break
        except Exception:
            pass

    try:
        _WINMM_DLL = ctypes.windll.winmm
    except Exception:
        pass


def is_gamepad_supported() -> bool:
    """Retorna True si el sistema operativo y las bibliotecas soportan mandos."""
    return _XINPUT_DLL is not None or _WINMM_DLL is not None


_WINMM_CONNECTED_DEVS: list[int] = []
_WINMM_LAST_SCAN: float = 0.0


def poll_raw_gamepad_inputs(force_winmm_rescan: bool = False) -> set[str]:
    """
    Sondea todos los mandos y joysticks conectados y retorna un conjunto
    con los nombres de todas las entradas (botones, crucetas, palancas) activas en este momento.
    Utiliza caché temporal de dispositivos WinMM para no bloquear con esperas I/O de Windows.
    """
    global _WINMM_CONNECTED_DEVS, _WINMM_LAST_SCAN
    inputs: set[str] = set()

    # 1. Sondear XInput (puertos 0 a 3) - consulta rápida (<0.2ms)
    if _XINPUT_DLL is not None:
        for port in range(4):
            xs = _XINPUT_STATE()
            if _XINPUT_DLL.XInputGetState(port, ctypes.byref(xs)) == 0:
                wb = xs.Gamepad.wButtons
                if wb & 0x0001: inputs.add("D-Pad Up")
                if wb & 0x0002: inputs.add("D-Pad Down")
                if wb & 0x0004: inputs.add("D-Pad Left")
                if wb & 0x0008: inputs.add("D-Pad Right")
                if wb & 0x0010: inputs.add("Start")
                if wb & 0x0020: inputs.add("Back")
                if wb & 0x0040: inputs.add("L3")
                if wb & 0x0080: inputs.add("R3")
                if wb & 0x0100: inputs.add("LB")
                if wb & 0x0200: inputs.add("RB")
                if wb & 0x1000: inputs.add("A")
                if wb & 0x2000: inputs.add("B")
                if wb & 0x4000: inputs.add("X")
                if wb & 0x8000: inputs.add("Y")

                # Gatillos analógicos (umbral > 60 de 255)
                if xs.Gamepad.bLeftTrigger > 60: inputs.add("LT")
                if xs.Gamepad.bRightTrigger > 60: inputs.add("RT")

                # Palanca izquierda (umbral > 16000 o < -16000 de 32767)
                if xs.Gamepad.sThumbLY > 16000: inputs.add("L-Stick Up")
                if xs.Gamepad.sThumbLY < -16000: inputs.add("L-Stick Down")
                if xs.Gamepad.sThumbLX < -16000: inputs.add("L-Stick Left")
                if xs.Gamepad.sThumbLX > 16000: inputs.add("L-Stick Right")

    # 2. Si no hubo entradas XInput, consultar mandos DirectInput / Arcade USB mediante WinMM
    if not inputs and _WINMM_DLL is not None:
        try:
            now = time.monotonic()
            # Escanear puertos WinMM cada 3 segundos o si se fuerza explícitamente
            if force_winmm_rescan or (now - _WINMM_LAST_SCAN > 3.0):
                _WINMM_LAST_SCAN = now
                active = []
                max_devs = min(int(_WINMM_DLL.joyGetNumDevs()), 8)
                ji_scan = _JOYINFOEX()
                ji_scan.dwSize = ctypes.sizeof(_JOYINFOEX)
                ji_scan.dwFlags = 0x01  # flag mínimo para probe de presencia
                for dev_id in range(max_devs):
                    if _WINMM_DLL.joyGetPosEx(dev_id, ctypes.byref(ji_scan)) == 0:
                        active.append(dev_id)
                _WINMM_CONNECTED_DEVS = active

            # Solo interrogar dispositivos confirmados como conectados
            if _WINMM_CONNECTED_DEVS:
                ji = _JOYINFOEX()
                ji.dwSize = ctypes.sizeof(_JOYINFOEX)
                ji.dwFlags = 0xFF  # All flags

                for dev_id in _WINMM_CONNECTED_DEVS:
                    if _WINMM_DLL.joyGetPosEx(dev_id, ctypes.byref(ji)) == 0:
                        buttons = ji.dwButtons
                        for b in range(16):
                            if buttons & (1 << b):
                                inputs.add(f"Button {b + 1}")

                        # POV / Cruceta (0 = Arriba, 9000 = Derecha, 18000 = Abajo, 27000 = Izquierda)
                        pov = ji.dwPOV
                        if pov != 65535:
                            if pov == 0 or (31500 <= pov <= 36000) or (0 <= pov <= 4500):
                                inputs.add("D-Pad Up")
                            if 13500 <= pov <= 22500:
                                inputs.add("D-Pad Down")
                            if 22500 <= pov <= 31500:
                                inputs.add("D-Pad Left")
                            if 4500 <= pov <= 13500:
                                inputs.add("D-Pad Right")

                        # Ejes analógicos X e Y (centro ~32767)
                        if ji.dwYpos < 16384: inputs.add("L-Stick Up")
                        if ji.dwYpos > 49152: inputs.add("L-Stick Down")
                        if ji.dwXpos < 16384: inputs.add("L-Stick Left")
                        if ji.dwXpos > 49152: inputs.add("L-Stick Right")

                        if inputs:
                            break
        except Exception:
            pass

    return inputs


class GamepadPollingThread(QThread):
    """
    Hilo de trabajo dedicado que sondea los mandos y joysticks fuera del hilo GUI,
    eliminando por completo cualquier congelamiento o caída de FPS en el renderizado.
    """
    action_triggered = Signal(str)
    input_detected = Signal(str)

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._running = True
        self._enabled = True
        self._action_bindings: dict[str, str] = {}
        self.refresh_bindings()

        # Estado previo de entradas para lógica de disparo y autorrepetición
        self._prev_inputs: set[str] = set()
        self._held_action: str | None = None
        self._held_ticks = 0

        # Parámetros de repetición (en ticks de ~20ms):
        # 16 ticks = ~320ms de retardo inicial antes de repetir
        # 5 ticks = ~100ms entre repeticiones continuas al mantener presionado
        self.INITIAL_REPEAT_TICKS = 16
        self.CONTINUOUS_REPEAT_TICKS = 5

    def refresh_bindings(self):
        """Precarga en memoria las asignaciones de botones para evitar consultas SQLite en caliente."""
        check_order = [
            ACTION_CLOSE_FRONTEND,
            ACTION_CLOSE_EMULATOR,
            ACTION_NAV_UP,
            ACTION_NAV_DOWN,
            ACTION_NAV_LETTER_BACK,
            ACTION_NAV_LETTER_FWD,
            ACTION_NAV_STEP5_BACK,
            ACTION_NAV_STEP5_FWD,
            ACTION_SELECT,
            ACTION_NAV_BACK,
            ACTION_PAGE_UP,
            ACTION_PAGE_DOWN,
            ACTION_MUTE,
            ACTION_TOGGLE_FPS,
            ACTION_TOGGLE_BEZEL,
        ]
        bindings = {}
        for act in check_order:
            bindings[act] = get_gamepad_binding(self.db, act)
        self._action_bindings = bindings

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled:
            self._prev_inputs.clear()
            self._held_action = None
            self._held_ticks = 0

    def stop(self):
        self._running = False
        self.wait(300)

    def _matches_action(self, pressed_inputs: set[str], action: str) -> bool:
        """Evaluación puramente en memoria de asignaciones y alias."""
        if not pressed_inputs:
            return False
        assigned = self._action_bindings.get(action)
        if not assigned:
            return False

        if "+" in assigned:
            parts = [p.strip() for p in assigned.split("+")]
            if all(p in pressed_inputs for p in parts):
                return True
        elif assigned in pressed_inputs:
            return True

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

    def run(self):
        while self._running:
            if not self._enabled:
                time.sleep(0.040)
                continue

            current_inputs = poll_raw_gamepad_inputs()
            if not current_inputs:
                self._prev_inputs.clear()
                self._held_action = None
                self._held_ticks = 0
                time.sleep(0.020)
                continue

            # Emitir señal de captura en vivo si hay observadores (diálogo de configuración)
            if "Back" in current_inputs and "Start" in current_inputs:
                combo_name = "Back+Start"
            else:
                combo_name = next(iter(current_inputs))
            self.input_detected.emit(combo_name)

            # Comprobar qué acción coincide con las entradas activas
            matched_action = None
            if self._matches_action(current_inputs, ACTION_CLOSE_FRONTEND):
                matched_action = ACTION_CLOSE_FRONTEND
            elif self._matches_action(current_inputs, ACTION_CLOSE_EMULATOR):
                matched_action = ACTION_CLOSE_EMULATOR
            else:
                check_order = [
                    ACTION_NAV_UP,
                    ACTION_NAV_DOWN,
                    ACTION_NAV_LETTER_BACK,
                    ACTION_NAV_LETTER_FWD,
                    ACTION_NAV_STEP5_BACK,
                    ACTION_NAV_STEP5_FWD,
                    ACTION_SELECT,
                    ACTION_NAV_BACK,
                    ACTION_PAGE_UP,
                    ACTION_PAGE_DOWN,
                    ACTION_MUTE,
                    ACTION_TOGGLE_FPS,
                ]
                for act in check_order:
                    if self._matches_action(current_inputs, act):
                        matched_action = act
                        break

            if not matched_action:
                self._held_action = None
                self._held_ticks = 0
                self._prev_inputs = current_inputs
                time.sleep(0.020)
                continue

            # Distinguir entre acciones navegables continuas y acciones de un solo toque
            repeatable_actions = {
                ACTION_NAV_UP, ACTION_NAV_DOWN,
                ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD,
                ACTION_PAGE_UP, ACTION_PAGE_DOWN
            }

            if matched_action in repeatable_actions:
                if matched_action == self._held_action:
                    self._held_ticks += 1
                    if self._held_ticks >= self.INITIAL_REPEAT_TICKS:
                        if (self._held_ticks - self.INITIAL_REPEAT_TICKS) % self.CONTINUOUS_REPEAT_TICKS == 0:
                            self.action_triggered.emit(matched_action)
                else:
                    self._held_action = matched_action
                    self._held_ticks = 0
                    self.action_triggered.emit(matched_action)
            else:
                if matched_action != self._held_action:
                    self._held_action = matched_action
                    self._held_ticks = 0
                    self.action_triggered.emit(matched_action)

            self._prev_inputs = current_inputs
            time.sleep(0.020)


class GamepadManager(QObject):
    """
    Monitor en segundo plano que gestiona los mandos y joysticks conectados
    mediante un hilo dedicado (QThread) y despacha señales seguras a través
    de eventos Qt sin afectar la tasa de cuadros (FPS) del hilo principal de la interfaz.
    """
    action_triggered = Signal(str)  # Id de la acción disparada (ej: 'nav_up', 'select_game', etc.)
    input_detected = Signal(str)    # Nombre del botón/combinación para diálogos de captura

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._worker = GamepadPollingThread(db=db)
        self._worker.action_triggered.connect(self.action_triggered.emit)
        self._worker.input_detected.connect(self.input_detected.emit)

        # Iniciar sondeo si hay soporte
        if is_gamepad_supported():
            self._worker.start()

    def set_enabled(self, enabled: bool):
        self._worker.set_enabled(enabled)

    def start(self):
        if is_gamepad_supported() and not self._worker.isRunning():
            self._worker.start()

    def stop(self):
        if self._worker.isRunning():
            self._worker.stop()

    def refresh_bindings(self):
        self._worker.db = self.db
        self._worker.refresh_bindings()


_GLOBAL_GAMEPAD_MANAGER: GamepadManager | None = None

def get_gamepad_manager(db=None) -> GamepadManager:
    """Retorna la instancia global del gestor de mandos."""
    global _GLOBAL_GAMEPAD_MANAGER
    if _GLOBAL_GAMEPAD_MANAGER is None:
        _GLOBAL_GAMEPAD_MANAGER = GamepadManager(db=db)
    elif db is not None and _GLOBAL_GAMEPAD_MANAGER.db != db:
        _GLOBAL_GAMEPAD_MANAGER.db = db
        _GLOBAL_GAMEPAD_MANAGER.refresh_bindings()
    return _GLOBAL_GAMEPAD_MANAGER
