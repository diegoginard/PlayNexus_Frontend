"""
Módulo de Splash Screen con Video para PlayNexus Frontend.
Muestra un video de introducción a pantalla completa al arrancar el Frontend.
Permite omitir el video al instante mediante cualquier tecla, botón de gamepad o clic de ratón.
"""
from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent.parent


def resolve_splash_video(db=None, custom_path: str | None = None) -> Path | None:
    """
    Resuelve la ruta absoluta al video de splash screen.
    Prioridades:
    1. custom_path (si se especifica explícitamente).
    2. frontend_splash_video en la base de datos de settings.
    3. Primer archivo de video (.mp4, .mkv, .avi, .webm) encontrado en la carpeta splash/.
    """
    # 1. Ruta personalizada explícita
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return p.resolve()
        cand = APP_DIR / custom_path
        if cand.is_file():
            return cand.resolve()

    # 2. Configuración guardada en DB
    if db:
        try:
            saved = db.get_setting("frontend_splash_video", "").strip()
            if saved:
                p = Path(saved)
                if p.is_file():
                    return p.resolve()
                cand = APP_DIR / saved
                if cand.is_file():
                    return cand.resolve()
        except Exception:
            pass

    # 3. Búsqueda automática en carpeta splash/ de la raíz
    splash_dir = APP_DIR / "splash"
    if splash_dir.is_dir():
        for ext in (".mp4", ".mkv", ".avi", ".webm", ".mov", ".wmv"):
            candidates = sorted(splash_dir.glob(f"*{ext}"))
            if candidates:
                return candidates[0].resolve()

    return None


class VideoSplashScreen(QWidget):
    """
    Ventana flotante a pantalla completa que reproduce el video de splash/intro.
    Emite la señal `finished` al finalizar la reproducción o cuando el usuario
    presiona cualquier tecla, botón del gamepad o hace clic con el ratón.
    """
    finished = Signal()

    def __init__(self, video_path: str | Path, target_geo=None, db=None, parent=None):
        super().__init__(parent)
        self.video_path = Path(video_path).resolve()
        self.db = db
        self._is_finishing = False

        self.setWindowTitle("PlayNexus — Intro")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setStyleSheet("background-color: #000000;")

        if target_geo:
            self.setGeometry(target_geo)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setStyleSheet("background-color: #000000;")
        layout.addWidget(self.video_widget)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(1.0)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_player_error)

        # Conectar gamepad si está disponible
        self._gamepad_manager = None
        try:
            from playnexus.services.gamepad import get_gamepad_manager
            self._gamepad_manager = get_gamepad_manager(self.db)
            self._gamepad_manager.action_triggered.connect(self._on_gamepad_trigger)
        except Exception:
            pass

    def start_playback(self):
        """Inicia la reproducción del video."""
        if not self.video_path.is_file():
            self._finish()
            return
        self.player.setSource(QUrl.fromLocalFile(str(self.video_path)))
        self.player.play()

    def _on_media_status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
            self._finish()

    def _on_player_error(self, error, error_string=""):
        self._finish()

    def _on_gamepad_trigger(self, action_id: str):
        self._finish()

    def keyPressEvent(self, event):
        event.accept()
        self._finish()

    def mousePressEvent(self, event):
        event.accept()
        self._finish()

    def _finish(self):
        """Detiene la reproducción y notifica el cierre una sola vez."""
        if self._is_finishing:
            return
        self._is_finishing = True

        if self._gamepad_manager:
            try:
                self._gamepad_manager.action_triggered.disconnect(self._on_gamepad_trigger)
            except Exception:
                pass

        try:
            if self.player:
                self.player.stop()
        except Exception:
            pass

        self.finished.emit()
        self.close()
        self.deleteLater()

