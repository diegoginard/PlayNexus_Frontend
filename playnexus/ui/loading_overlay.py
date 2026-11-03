"""
Módulo de Loading Screen Overlay para PlayNexus.
Muestra una pantalla de carga a pantalla completa (TOPMOST) al iniciar un emulador
y al cerrarlo, tapando transiciones de Windows, parpadeos de resolución y carga de ROMs.
"""
from __future__ import annotations
import sys
import ctypes
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap, QGuiApplication, QColor
from PySide6.QtWidgets import QWidget


class LoadingOverlayWindow(QWidget):
    """
    Ventana flotante de cobertura a pantalla completa (TOPMOST)
    que muestra la imagen de carga o despedida con animación suave de fundido de salida (fade-out).
    """
    finished = Signal()

    def __init__(self, image_path: str, target_screen_idx: int = 0, duration: float = 2.0, fade_duration: float = 0.3, parent=None):
        super().__init__(parent)
        self.image_path = str(image_path) if image_path else ""
        self.pixmap = QPixmap(self.image_path) if self.image_path else QPixmap()
        self.duration = max(0.0, float(duration))
        self.fade_duration = max(0.0, float(fade_duration))
        self._opacity = 1.0
        self._fade_timer: QTimer | None = None
        self._fade_start_time: float | None = None
        self._stay_timer: QTimer | None = None

        # Configuración de ventana de pantalla completa por encima de todo
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Asignar a la pantalla correspondiente
        screens = QGuiApplication.screens()
        if 0 <= target_screen_idx < len(screens):
            geo = screens[target_screen_idx].geometry()
            self.setGeometry(geo)
        elif screens:
            self.setGeometry(screens[0].geometry())

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            self._apply_win32_topmost_style()

    def start_display(self):
        """Muestra la ventana y programa la retención y posterior fundido de salida."""
        self._opacity = 1.0
        self.show()
        self.bring_to_top()
        self.update()

        if self.duration <= 0.0:
            self._start_fade_out()
            return

        self._stay_timer = QTimer(self)
        self._stay_timer.setSingleShot(True)
        self._stay_timer.timeout.connect(self._start_fade_out)
        self._stay_timer.start(int(self.duration * 1000))

    def _start_fade_out(self):
        if self._stay_timer and self._stay_timer.isActive():
            self._stay_timer.stop()

        if self.fade_duration <= 0.0:
            self._opacity = 0.0
            self.update()
            self.finished.emit()
            self.close()
            return

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
            if self._fade_timer:
                self._fade_timer.stop()
            self._opacity = 0.0
            self.update()
            self.finished.emit()
            self.close()
        else:
            self._opacity = max(0.0, 1.0 - progress)
            self.update()

    def dismiss_now(self):
        """Cierra inmediatamente la pantalla de carga sin esperar."""
        if self._stay_timer and self._stay_timer.isActive():
            self._stay_timer.stop()
        if self._fade_timer and self._fade_timer.isActive():
            self._fade_timer.stop()
        self.close()
        self.deleteLater()

    def _apply_win32_topmost_style(self):
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
        if self._opacity <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)

        # Si no hay pixmap válido, dibujar fondo negro sólido
        if self.pixmap.isNull():
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            return

        # Dibujar pixmap escalado al tamaño del monitor (aspect ratio preservado o expandido)
        # Modo 'KeepAspectRatioByExpanding' centrado para cubrir la pantalla completa
        scaled = self.pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        painter.drawPixmap(x, y, scaled)

