"""
Gestor y monitor de procesos de emuladores para RetroShelf.
Funcionalidades clave:
1. Silencia el audio de los videos mientras el emulador está ejecutándose y lo reactiva al salir.
2. Monitorea globalmente la tecla configurada (ej: Escape) y/o combo de mando (Back + Start)
   para permitir cerrar el emulador al instante, restaurando el foco en RetroShelf.
"""

import sys
import time
import ctypes
import subprocess
from PySide6.QtCore import QObject, QTimer, Signal
from retroshelf.services.controls import get_binding, key_name_to_vk, ACTION_CLOSE_EMULATOR

# Estructuras para XInput (mando de juegos en Windows)
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


class EmulatorManager(QObject):
    """
    Monitor singleton de emuladores en ejecución.
    Supervisa el ciclo de vida del emulador, gestiona el silenciamiento
    de medios y la interceptación de la tecla global de salida.
    """
    emulator_started = Signal(str)      # Emite el nombre o título del emulador/juego
    emulator_finished = Signal(int)     # Emite el código de retorno al salir

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_proc: subprocess.Popen | None = None
        self._last_launch_time: float = 0.0
        self.active_layout = None
        self.parent_window = None
        self.db = None
        self.exit_vk = 0x1B  # VK_ESCAPE por defecto
        self.mute_on_run = True
        self.global_exit_enabled = True
        self.gamepad_exit_enabled = True

        self._timer = QTimer(self)
        self._timer.setInterval(50)  # Chequeo a 20 Hz (muy bajo impacto en CPU)
        self._timer.timeout.connect(self._on_check_tick)

        # Cargar DLL de XInput si está disponible
        self._xinput = None
        if sys.platform == "win32":
            for dll in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
                try:
                    self._xinput = ctypes.windll.LoadLibrary(dll)
                    break
                except Exception:
                    pass

    # Ventana (segundos) durante la cual se ignoran nuevos lanzamientos tras iniciar uno
    LAUNCH_GUARD_SECONDS = 2.5

    def is_running(self) -> bool:
        """Retorna True si hay un emulador actualmente en ejecución activa.
        No modifica 'active_proc': su limpieza la realiza '_on_process_ended'
        para no saltear la reanudación de medios y la restauración del foco."""
        proc = self.active_proc
        return proc is not None and proc.poll() is None

    def is_launching_or_running(self) -> bool:
        """Retorna True si un emulador está corriendo o en proceso inmediato de iniciarse."""
        if self.is_running():
            return True
        last = self._last_launch_time
        return bool(last) and (time.perf_counter() - last < self.LAUNCH_GUARD_SECONDS)

    def mark_launching(self):
        """Registra el instante de inicio para evitar ráfagas o dobles instancias."""
        self._last_launch_time = time.perf_counter()

    def clear_launching(self):
        """Libera el bloqueo de lanzamiento (ej: si el inicio falló antes de crear el proceso)."""
        self._last_launch_time = 0.0

    def start_monitoring(self, proc: subprocess.Popen, game_title: str, layout, db, parent_window=None):
        """
        Inicia la supervisión del proceso de emulador recién ejecutado.
        """
        self.active_proc = proc
        self.active_layout = layout
        self.parent_window = parent_window
        self.db = db

        # Leer configuración de la base de datos
        self.exit_key_name = get_binding(db, ACTION_CLOSE_EMULATOR)
        self.exit_vk = key_name_to_vk(self.exit_key_name)

        self.mute_on_run = (db.get_setting("emulator_mute_video", "true").lower() == "true") if db else True
        self.global_exit_enabled = (db.get_setting("emulator_global_exit", "true").lower() == "true") if db else True
        self.gamepad_exit_enabled = (db.get_setting("emulator_gamepad_exit", "true").lower() == "true") if db else True

        # 1. Pausar video y silenciar audio del layout mientras el emulador se ejecuta
        if self.active_layout:
            try:
                if hasattr(self.active_layout, "pause_media"):
                    self.active_layout.pause_media()
                elif self.mute_on_run:
                    if hasattr(self.active_layout, "set_media_muted"):
                        self.active_layout.set_media_muted(True)
                    elif hasattr(self.active_layout, "audio_output") and self.active_layout.audio_output:
                        self.active_layout.audio_output.setMuted(True)
            except Exception:
                pass

        self._timer.start()
        self.emulator_started.emit(game_title)

    def _on_check_tick(self):
        proc = self.active_proc
        if not proc:
            self._timer.stop()
            return

        # 1. Verificar si el proceso terminó por su cuenta
        ret = proc.poll()
        if ret is not None:
            self._on_process_ended(ret)
            return

        # 2. Verificar tecla global de salida en Windows
        if self.global_exit_enabled and sys.platform == "win32":
            try:
                # GetAsyncKeyState retorna < 0 (bit 15 en 1) si la tecla está presionada
                state = ctypes.windll.user32.GetAsyncKeyState(self.exit_vk)
                if state & 0x8000:
                    # Si el atajo requiere modificadores (Ctrl, Alt, Shift), comprobar que coincidan
                    parts = [p.strip().lower() for p in (self.exit_key_name or "").split("+")]
                    req_ctrl = "ctrl" in parts[:-1]
                    req_alt = "alt" in parts[:-1]
                    req_shift = "shift" in parts[:-1]

                    ctrl_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)
                    alt_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000)
                    shift_pressed = bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)

                    if (req_ctrl == ctrl_pressed) and (req_alt == alt_pressed) and (req_shift == shift_pressed):
                        self.terminate_active_emulator()
                        return
            except Exception:
                pass

        # 3. Verificar combo de salida en mando (Back + Start)
        if self.gamepad_exit_enabled and self._xinput:
            try:
                for port in range(4):
                    x_state = _XINPUT_STATE()
                    if self._xinput.XInputGetState(port, ctypes.byref(x_state)) == 0:
                        buttons = x_state.Gamepad.wButtons
                        # Back (0x0020) + Start (0x0010) = 0x0030
                        if (buttons & 0x0030) == 0x0030:
                            self.terminate_active_emulator()
                            return
            except Exception:
                pass

    def terminate_active_emulator(self):
        """Fuerza el cierre inmediato y limpio del proceso del emulador y sus subprocesos."""
        proc = self.active_proc
        if not proc:
            return

        try:
            if sys.platform == "win32":
                # taskkill /F /T termina el proceso y todo su árbol de subprocesos
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    creationflags=0x08000000  # CREATE_NO_WINDOW
                )
            else:
                proc.terminate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _on_process_ended(self, return_code: int):
        self._timer.stop()
        self.active_proc = None
        self.clear_launching()

        # 1. Reanudar video y audio en el layout activo y liberar bloqueos de clic
        if self.active_layout:
            try:
                if hasattr(self.active_layout, "_last_activate_time"):
                    self.active_layout._last_activate_time = 0.0
                if hasattr(self.active_layout, "releaseMouse"):
                    self.active_layout.releaseMouse()
                if hasattr(self.active_layout, "resume_media"):
                    self.active_layout.resume_media()
                elif hasattr(self.active_layout, "set_media_muted"):
                    self.active_layout.set_media_muted(False)
                elif hasattr(self.active_layout, "audio_output") and self.active_layout.audio_output:
                    self.active_layout.audio_output.setMuted(False)
            except Exception:
                pass

        # 2. Restaurar ventana y traer RetroShelf al primer plano
        if self.parent_window:
            try:
                if hasattr(self.parent_window, "_last_activation_time"):
                    self.parent_window._last_activation_time = 0.0
                if hasattr(self.parent_window, "releaseMouse"):
                    self.parent_window.releaseMouse()
                if hasattr(self.parent_window, "resume_active_media"):
                    self.parent_window.resume_active_media()
                self.parent_window.show()
                self.parent_window.raise_()
                self.parent_window.activateWindow()
            except Exception:
                pass

        # 3. En Windows: asegurar liberación de captura nativa y forzar primer plano
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.ReleaseCapture()
                if self.parent_window:
                    hwnd = int(self.parent_window.winId())
                    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                    ctypes.windll.user32.AllowSetForegroundWindow(-1)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    ctypes.windll.user32.BringWindowToTop(hwnd)
            except Exception:
                pass

        # 4. Asignar foco explícito al layout activo (inmediato y con retardo seguro)
        target_layout = self.active_layout
        if not target_layout and self.parent_window and hasattr(self.parent_window, "layout_stack"):
            target_layout = self.parent_window.layout_stack.currentWidget()
        if target_layout:
            try:
                target_layout.setFocus()
            except Exception:
                pass

        if self.parent_window and hasattr(self.parent_window, "layout_stack"):
            from PySide6.QtCore import QTimer
            def _ensure_layout_focus():
                if self.parent_window and hasattr(self.parent_window, "layout_stack"):
                    cur = self.parent_window.layout_stack.currentWidget()
                    if cur:
                        cur.setFocus()
            QTimer.singleShot(60, _ensure_layout_focus)

        self.emulator_finished.emit(return_code)


# Instancia global compartida
EMULATOR_MANAGER = EmulatorManager()
