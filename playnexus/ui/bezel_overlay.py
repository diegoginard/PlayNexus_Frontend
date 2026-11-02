"""
Módulo de Bezel Overlay en primer plano para PlayNexus.
Muestra una ventana transparente con el bezel por encima de la ventana del emulador
utilizando la API Win32 para que sea completamente 'click-through' (no capture clics ni foco).
"""
import sys
import ctypes
from pathlib import Path
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPixmap, QGuiApplication, QColor
from PySide6.QtWidgets import QWidget


class BezelOverlayWindow(QWidget):
    """
    Ventana flotante transparente que se dibuja en el plano más alto (TOPMOST)
    delante del emulador en ejecución.
    """
    def __init__(self, bezel_path: str, target_screen_idx: int = 0, parent=None):
        super().__init__(parent)
        self.bezel_path = str(bezel_path)
        self.bezel_pixmap = QPixmap(self.bezel_path)

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

    def _apply_win32_click_through(self):
        """
        Aplica los estilos extendidos de Win32:
        - WS_EX_TRANSPARENT (0x00000020): El mouse y los clics traspasan la ventana hacia el emulador.
        - WS_EX_LAYERED (0x00080000): Soporte para composición de transparencia en Windows.
        - WS_EX_NOACTIVATE (0x08000000): Nunca roba el foco de la ventana activa al mostrarse.
        - HWND_TOPMOST (-1): Permanece siempre en primer plano cubriendo los marcos del monitor.
        """
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            WS_EX_NOACTIVATE = 0x08000000

            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE)

            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        except Exception:
            pass

    def bring_to_top(self):
        """Reafirma la posición TOPMOST si el emulador cambió de modo de pantalla."""
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                HWND_TOPMOST = -1
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            except Exception:
                pass

    def paintEvent(self, event):
        if self.bezel_pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.bezel_pixmap)

