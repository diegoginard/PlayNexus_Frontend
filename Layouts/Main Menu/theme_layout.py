"""
=============================================================================
Layout Temático: Main Menu (Selector de Sistemas)
=============================================================================
"""
import os
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QUrl
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap

from playnexus.services.media import resolve_game_media
from playnexus.ui.layouts.theme_base import CommonThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(CommonThemeLayout):
    LAYOUT_NAME = "Main Menu"
    LAYOUT_DESCRIPTION = (
        "Menú principal de selección de sistemas con video de fondo a pantalla completa y ruleta de wheels curva"
    )
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
        {
            "key": "video",
            "label": "Videos de Fondo / Temas",
            "extensions": [".mp4", ".mkv", ".avi", ".webm"],
            "required": True,
        },
        {
            "key": "wheel",
            "label": "Logos Wheel",
            "extensions": [".png", ".webp"],
            "required": True,
        },
        {
            "key": "boxart",
            "label": "Artwork / Imagen decorativa",
            "extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "required": False,
        },
    ]

    # 2. Fuentes tipográficas
    FONT_FILE = COMMON_DIR / "fonts" / "Handel Gothic BT.ttf"
    FONT_TITLE_FILE = FONT_FILE
    FONT_MAIN_FILE = COMMON_DIR / "fonts" / "BebasNeue Bold.otf"
    FONT_BEBAS = FONT_MAIN_FILE
    FONT_FILES = [FONT_TITLE_FILE, FONT_MAIN_FILE]

    # 3. Recursos propios y compartidos (gtc-common)
    WHEEL_ART_IMAGE = LAYOUT_DIR / "wheel_art.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers" / "default.png"

    WHEEL_IMAGE = COMMON_DIR / "wheel" / "wheel.png"
    WHEEL_SHADOW_IMAGE = COMMON_DIR / "wheel" / "wheel_shadow.png"
    COMMON_WHEEL_ART = COMMON_DIR / "art" / "wheel_art.png"
    COMMON_FRAME = COMMON_DIR / "art" / "frame.png"
    SCANLINES_IMAGE = COMMON_DIR / "art" / "scanlines_1920.png"
    SCRATCHES_IMAGE = COMMON_DIR / "art" / "arcade" / "scratched_cover.png"
    STATIC_VIDEO = COMMON_DIR / "videos" / "static.mp4"
    SOUND_NAV = COMMON_DIR / "sounds" / "joystick.mp3"
    SOUND_SELECT = COMMON_DIR / "sounds" / "hs_click.mp3"

    # 4. Geometría de barra inferior (ruleta unificada heredada de CommonThemeLayout)
    BOTTOM_BAR_H_RATIO = 0.052
    BOTTOM_TITLE_X_RATIO = 0.03
    BOTTOM_TITLE_W_RATIO = 0.58
    BOTTOM_COUNTER_X_RATIO = 0.62
    BOTTOM_COUNTER_W_RATIO = 0.35
    VIDEO_DEBOUNCE_MS = 180

    def _init_extra_resources(self):
        self._current_artwork_pixmap: QPixmap | None = None
        self._video_frame_painting = False

    def _clear_selected_media(self):
        self._current_artwork_pixmap = None
        super()._clear_selected_media()

    def _update_current_selection(self):
        """Actualiza artwork de respaldo y video de fondo del sistema enfocado."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self._clear_selected_media()
            return

        super()._update_current_selection()
        game = self.games[self.selected_index]
        self.current_media = resolve_game_media(game)

        art_file = self.current_media.get("boxart") or self.current_media.get("snap") or self.current_media.get("flyer")
        if art_file and os.path.isfile(art_file):
            if art_file not in self._art_pix_cache:
                pix = QPixmap(art_file)
                self._art_pix_cache[art_file] = pix if not pix.isNull() else None
            self._current_artwork_pixmap = self._art_pix_cache.get(art_file)
        else:
            self._current_artwork_pixmap = None

        snap_video = (
            self.current_media.get("video")
            or self.current_media.get("snap")
            or game.get("video")
            or game.get("snap")
        )
        video_to_play = snap_video if (snap_video and os.path.isfile(snap_video)) else None
        self._ensure_player_initialized()
        self._pending_video_path = video_to_play
        self._play_debounced_video()

    def _draw_bottom_bar(self, painter: QPainter, sr: QRect):
        """Renderiza la barra inferior del Menú Principal con el sistema activo y su contador."""
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        bar_h = max(32, int(round(sh * self.BOTTOM_BAR_H_RATIO)))
        bar_y = sy + sh - bar_h

        if not getattr(self, "_skip_footer_bg", False):
            painter.fillRect(QRect(sx, bar_y, sw, bar_h), QColor(0, 0, 0, 160))

        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return

        game = self.games[self.selected_index]
        title = (game.get("title") or "").upper()
        eff_name = game.get("effective_name") or ""
        pad_x = max(4, int(round(sw * 0.004)))

        painter.save()
        painter.setFont(QFont(self._font_title, max(11, int(sh * 0.022)), QFont.Bold))
        painter.setPen(QColor(255, 255, 255))
        title_x = sx + int(round(sw * self.BOTTOM_TITLE_X_RATIO))
        title_w = int(round(sw * self.BOTTOM_TITLE_W_RATIO))
        title_rect = QRect(title_x + pad_x, bar_y, max(1, title_w - 2 * pad_x), bar_h)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, title)

        counter_text = (
            f"{eff_name.upper()}  |  SISTEMA {self.selected_index + 1} / {len(self.games)}"
            if eff_name
            else f"SISTEMA {self.selected_index + 1} / {len(self.games)}"
        )
        painter.setFont(QFont(self._font_main, max(11, int(sh * 0.022)), QFont.Bold))
        painter.setPen(QColor(245, 185, 35))
        counter_x = sx + int(round(sw * self.BOTTOM_COUNTER_X_RATIO))
        counter_w = int(round(sw * self.BOTTOM_COUNTER_W_RATIO))
        counter_rect = QRect(counter_x + pad_x, bar_y, max(1, counter_w - 2 * pad_x), bar_h)
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter_text)
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0))

            sr = self._get_target_rect()
            sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()

            # Video de fondo o Artwork de respaldo
            if self._current_video_image and not self._current_video_image.isNull():
                vw, vh = self._current_video_image.width(), self._current_video_image.height()
                if vw > 0 and vh > 0 and sw > 0 and sh > 0 and abs((vw / float(vh)) - (sw / float(sh))) >= 0.15:
                    scale = min(sw / float(vw), sh / float(vh))
                    dw, dh = int(vw * scale), int(vh * scale)
                    painter.drawImage(QRect(sx + (sw - dw) // 2, sy + (sh - dh) // 2, dw, dh), self._current_video_image)
                else:
                    painter.drawImage(sr, self._current_video_image)
            elif self._current_artwork_pixmap and not self._current_artwork_pixmap.isNull():
                pw, ph = self._current_artwork_pixmap.width(), self._current_artwork_pixmap.height()
                if pw > 0 and ph > 0:
                    scale = max(sw / float(pw), sh / float(ph))
                    dw, dh = int(pw * scale), int(ph * scale)
                    painter.drawPixmap(QRect(sx + (sw - dw) // 2, sy + (sh - dh) // 2, dw, dh), self._current_artwork_pixmap)

            # Sombra de ruleta
            if self._pix_wheel_shadow:
                self._draw_wheel_shadow_layer(painter, sr)
            else:
                gradient = QLinearGradient(sx + int(sw * 0.50), 0, sx + sw, 0)
                gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
                gradient.setColorAt(0.4, QColor(0, 0, 0, 80))
                gradient.setColorAt(1.0, QColor(0, 0, 0, 210))
                painter.fillRect(QRect(sx + int(sw * 0.50), sy, int(sw * 0.50), sh), gradient)
                if self._pix_wheel_art and not self._pix_wheel_art.isNull():
                    painter.drawPixmap(QRect(sx + int(sw * 0.65), sy, int(sw * 0.36), sh), self._pix_wheel_art)

            # Ruleta unificada, puntero y barra inferior
            if self.games:
                self._draw_wheel_conveyor(painter, sr)
            self._draw_pointer(painter, sr)
            self._draw_bottom_bar(painter, sr)
        finally:
            self._video_frame_painting = False
            painter.end()
