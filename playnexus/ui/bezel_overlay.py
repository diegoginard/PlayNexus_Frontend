"""
Módulo de Bezel Overlay en primer plano para PlayNexus.
Muestra una ventana transparente con el bezel por encima de la ventana del emulador
utilizando la API Win32 para que sea completamente 'click-through' (no capture clics ni foco)
con soporte de animación de fundido suave (fade-in) configurable.
"""
import sys
import ctypes
if sys.platform == "win32":
    import ctypes.wintypes
import time
from pathlib import Path
from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap, QGuiApplication, QColor
from PySide6.QtWidgets import QWidget


class BezelOverlayWindow(QWidget):
    """
    Ventana flotante transparente que se dibuja en el plano más alto (TOPMOST)
    delante del emulador en ejecución con animación de fundido (fade-in) configurable.
    """
    fade_finished = Signal()

    def __init__(self, bezel_path: str, target_screen_idx: int = 0, fade_duration: float = 0.3, parent=None):
        super().__init__(parent)
        self.bezel_path = str(bezel_path)
        self.bezel_pixmap = QPixmap(self.bezel_path)
        self.fade_duration = max(0.0, float(fade_duration))
        self._opacity = 0.0 if self.fade_duration > 0.0 else 1.0
        self._fade_timer: QTimer | None = None
        self._fade_start_time: float | None = None

        # Configuración de ventana flotante sin bordes y sin captura de foco
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        # Ubicar en la pantalla seleccionada
        screens = QGuiApplication.screens()
        if 0 <= target_screen_idx < len(screens):
            geo = screens[target_screen_idx].geometry()
            self.setGeometry(geo)
        elif screens:
            self.setGeometry(screens[0].geometry())

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            self._apply_win32_click_through()

    def start_fade(self):
        """Inicia la animación de fundido suave (fade-in) desde 0.0 hasta 1.0 de opacidad."""
        if self.fade_duration <= 0.0:
            self._opacity = 1.0
            self.update()
            self.fade_finished.emit()
            return

        self._opacity = 0.0
        self.update()
        self._fade_start_time = time.perf_counter()
        if not self._fade_timer:
            self._fade_timer = QTimer(self)
            self._fade_timer.setInterval(16)  # ~60 fps
            self._fade_timer.timeout.connect(self._on_fade_step)
        self._fade_timer.start()

    def _on_fade_step(self):
        if self._fade_start_time is None:
            return
        elapsed = time.perf_counter() - self._fade_start_time
        progress = elapsed / self.fade_duration
        if progress >= 1.0:
            self._opacity = 1.0
            if self._fade_timer:
                self._fade_timer.stop()
            self.update()
            self.fade_finished.emit()
        else:
            self._opacity = progress
            self.update()

    def stop_fade(self):
        """Detiene cualquier temporizador de fade activo."""
        if self._fade_timer and self._fade_timer.isActive():
            self._fade_timer.stop()

    def _apply_win32_click_through(self):
        """
        Aplica los estilos extendidos de Win32:
        - WS_EX_TRANSPARENT (0x00000020): El mouse y los clics traspasan la ventana hacia el emulador.
        - WS_EX_NOACTIVATE (0x08000000): Nunca roba el foco de la ventana activa al mostrarse.
        - HWND_TOPMOST (-1): Permanece siempre en primer plano cubriendo los marcos del monitor.
        """
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_NOACTIVATE = 0x08000000

            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)

            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        except Exception:
            pass

    def attach_to_target_hwnd(self, emu_hwnd: int):
        """
        Asocia esta ventana como Owned Window de la ventana del emulador en Win32.
        En Windows, una Owned Window (GWLP_HWNDPARENT) siempre se dibuja por encima
        de su ventana propietaria, impidiendo que el emulador la tape al tomar foco.
        """
        if sys.platform == "win32" and emu_hwnd:
            try:
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                GWLP_HWNDPARENT = -8
                try:
                    user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, emu_hwnd)
                except AttributeError:
                    user32.SetWindowLongW(hwnd, GWLP_HWNDPARENT, emu_hwnd)
                self.bring_to_top()
            except Exception:
                pass

    def bring_to_top(self):
        """Reafirma la posición TOPMOST sin activar la ventana ni robar el foco del emulador."""
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                HWND_TOPMOST = -1
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
            except Exception:
                pass

    def nativeEvent(self, eventType, message):
        """Previene la captura de clics y garantiza que la ventana nunca se active por mouse."""
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            # WM_MOUSEACTIVATE = 0x0021 -> MA_NOACTIVATE (3): No activar nunca por clic
            if msg.message == 0x0021:
                return True, 3
            # WM_NCHITTEST = 0x0084 -> HTTRANSPARENT (-1): Traspasar cualquier hit-test al emulador
            if msg.message == 0x0084:
                return True, -1
        return super().nativeEvent(eventType, message)

    def paintEvent(self, event):
        if self.bezel_pixmap.isNull() or self._opacity <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(self.rect(), self.bezel_pixmap)
