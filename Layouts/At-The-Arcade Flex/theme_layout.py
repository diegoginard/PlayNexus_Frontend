"""
=============================================================================
Layout Temático: At-The-Arcade Flex
=============================================================================
Hereda el motor de navegación, sonidos, fuentes, worker y ruleta curva unificada
de 14 nodos desde `CommonThemeLayout`, conservando el mueble arcade interactivo,
marquesina, bezel, video de fondo continuo, video snap CRT y flyer deslizante.
"""
import os
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink

from playnexus.services.media import find_media_file as cached_find_media_file
from playnexus.ui.layouts.theme_base import CommonThemeLayout

LAYOUT_DIR = Path(__file__).resolve().parent
COMMON_DIR = LAYOUT_DIR.parent / "gtc-common"


class ThemeLayout(CommonThemeLayout):
    LAYOUT_NAME = "At-The-Arcade Flex"
    LAYOUT_DESCRIPTION = "Layout arcade fotorrealista con mueble interactivo, video de fondo y ruleta"
    LAYOUT_DIR = LAYOUT_DIR
    COMMON_DIR = COMMON_DIR

    # 1. Requerimientos de medios (Regla 4 y 8)
    MEDIA_REQUIREMENTS = [
        {"key": "video", "label": "Videos", "extensions": [".mp4", ".mkv", ".avi", ".webm"], "required": True},
        {"key": "wheel", "label": "Wheel", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": True},
        {"key": "cabinet", "label": "Cabinets", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
        {"key": "flyer", "label": "Flyers", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
        {"key": "marquee", "label": "Marquees", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
        {"key": "bezel", "label": "Bezels", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
    ]

    # 2. Fuentes tipográficas
    FONT_TITLE_FILE = LAYOUT_DIR / "BebasNeue Bold.otf"
    FONT_COUNTER_FILE = LAYOUT_DIR / "Handel Gothic BT.ttf"
    FONT_MAIN_FILE = FONT_COUNTER_FILE
    FONT_FILES = [FONT_TITLE_FILE, FONT_COUNTER_FILE]

    # 3. Recursos propios y compartidos (gtc-common)
    CABINET_IMAGE = LAYOUT_DIR / "cabinets.png"
    MARQUEE_IMAGE = LAYOUT_DIR / "marquee1.jpg"
    BEZEL_IMAGE = LAYOUT_DIR / "bezels.png"
    POINTER_IMAGE = LAYOUT_DIR / "pointers" / "default.png"
    DEFAULT_WHEEL_IMAGE = LAYOUT_DIR / "wheel.png"
    WHEEL_IMAGE = DEFAULT_WHEEL_IMAGE

    SCANLINES_IMAGE = COMMON_DIR / "art" / "scanlines_1920.png"
    SCRATCHES_IMAGE = COMMON_DIR / "art" / "arcade" / "scratched_cover.png"
    WHEEL_SHADOW_IMAGE = COMMON_DIR / "wheel" / "wheel_shadow.png"
    COMMON_WHEEL_ART = COMMON_DIR / "art" / "wheel_art.png"
    COMMON_FRAME = COMMON_DIR / "art" / "frame.png"
    FALLBACK_BG_IMAGE = COMMON_DIR / "art" / "arcade" / "bkg.jpg"
    BG_VIDEO = COMMON_DIR / "videos" / "bkg_anim.mp4"
    STATIC_VIDEO = COMMON_DIR / "videos" / "static.mp4"
    SOUND_NAV = COMMON_DIR / "sounds" / "joystick.mp3"
    SOUND_SELECT = COMMON_DIR / "sounds" / "Mame_coin.mp3"

    # 4. Geometría virtual del mueble arcade y temporizadores
    CAB_BASE_W = 1300
    CAB_BASE_H = 1080
    CAB_MAX_WIDTH_RATIO = 0.82
    SNAP_LOCAL_RECT = QRect(200, 318, 706, 526)
    MARQUEE_LOCAL_RECT = QRect(138, 0, 832, 227)

    WHEEL_FADEOUT_DELAY_MS = 1400
    FLYER_DELAY_MS = 1500
    VIDEO_DEBOUNCE_MS = 150
    VIDEO_WATCHDOG_MS = 1200

    FOOTER_COUNTER_PREFIX = "ARCADE:"
    COLOR_FOOTER_TITLE = QColor(255, 255, 255)
    COLOR_FOOTER_COUNTER = QColor(245, 185, 35)

    def _init_extra_resources(self):
        self._font_counter = self._font_main
        self._media_cache: dict[Any, dict] = {}
        self._current_marquee_pix: QPixmap | None = None
        self._current_cabinet_pix: QPixmap | None = None
        self._current_bezel_pix: QPixmap | None = None
        self._current_flyer_pix: QPixmap | None = None
        self._pending_video_is_snap = False
        self._is_emulator_running = False

        self._pix_cabinet = self._load_pixmap(self.CABINET_IMAGE)
        self._pix_marquee_default = self._load_pixmap(self.MARQUEE_IMAGE)
        self._current_cabinet_pix = self._pix_cabinet
        self._current_marquee_pix = self._pix_marquee_default
        self._pix_wheel_default = self._load_pixmap(self.DEFAULT_WHEEL_IMAGE)
        self._pix_bg_fallback = self._load_pixmap(self.FALLBACK_BG_IMAGE)

        # Reproductor de video de fondo continuo
        self._bg_video_image: QImage | None = None
        self._bg_player_initialized = False
        self.bg_player: QMediaPlayer | None = None
        self.bg_sink: QVideoSink | None = None

        # Reproductor gameplay en monitor CRT
        self._game_video_image: QImage | None = None
        self._game_player_initialized = False
        self._want_game_video_playing = False
        self.game_player: QMediaPlayer | None = None
        self.game_audio: QAudioOutput | None = None
        self.game_sink: QVideoSink | None = None

        self._video_watchdog_timer = QTimer(self)
        self._video_watchdog_timer.setSingleShot(True)
        self._video_watchdog_timer.setInterval(int(self.VIDEO_WATCHDOG_MS))
        self._video_watchdog_timer.timeout.connect(self._on_game_video_watchdog)

        self._art_debounce_timer = QTimer(self)
        self._art_debounce_timer.setSingleShot(True)
        self._art_debounce_timer.setInterval(100)
        self._art_debounce_timer.timeout.connect(self._on_art_debounce_timeout)

        self._flyer_slide = 1.0
        self._flyer_ready = False
        self._flyer_delay_timer = QTimer(self)
        self._flyer_delay_timer.setSingleShot(True)
        self._flyer_delay_timer.setInterval(int(self.FLYER_DELAY_MS))
        self._flyer_delay_timer.timeout.connect(self._on_flyer_delay_timeout)

        self._flyer_anim_timer = QTimer(self)
        self._flyer_anim_timer.setInterval(16)
        self._flyer_anim_timer.timeout.connect(self._on_flyer_anim_tick)

        self._init_bg_player()

    # -------------------------------------------------------------------------
    # REPRODUCTORES DE VIDEO (FONDO + CRT ARCADE)
    # -------------------------------------------------------------------------
    def _init_bg_player(self):
        if self._bg_player_initialized:
            return
        bg_video_path = Path(self.BG_VIDEO)
        if not bg_video_path.is_file():
            return
        self._bg_player_initialized = True
        self.bg_player = QMediaPlayer(self)
        self.bg_sink = QVideoSink(self)
        self.bg_sink.videoFrameChanged.connect(self._on_bg_frame)
        self.bg_player.setVideoSink(self.bg_sink)
        self.bg_player.setLoops(QMediaPlayer.Infinite)
        self.bg_player.mediaStatusChanged.connect(self._on_bg_media_status_changed)
        self.bg_player.errorOccurred.connect(self._on_bg_player_error)
        self.bg_player.setSource(QUrl.fromLocalFile(str(bg_video_path)))
        self.bg_player.play()

    def _on_bg_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia and self.bg_player and self.isVisible():
            self.bg_player.play()

    def _on_bg_player_error(self, error, error_string=""):
        self._bg_video_image = None

    def _on_bg_frame(self, frame):
        if not frame.isValid():
            return
        img = frame.toImage()
        if not img.isNull():
            self._bg_video_image = img
            self.update()

    def _init_game_player(self):
        if self._game_player_initialized and self.game_player is not None:
            return
        self._game_player_initialized = True
        self.game_player = QMediaPlayer(self)
        self.game_audio = QAudioOutput(self)
        self.game_audio.setVolume(0.0 if self._media_muted else 0.8)
        self.game_sink = QVideoSink(self)
        self.game_sink.videoFrameChanged.connect(self._on_game_frame)
        self.game_player.setVideoSink(self.game_sink)
        self.game_player.setAudioOutput(self.game_audio)
        self.game_player.setLoops(QMediaPlayer.Infinite)
        self.game_player.mediaStatusChanged.connect(self._on_game_media_status_changed)
        self.game_player.errorOccurred.connect(self._on_game_player_error)

    def _apply_game_audio_state(self, active: bool):
        if not self.game_audio:
            return
        muted = bool(self._media_muted or not getattr(self, "_pending_video_is_snap", True) or not active)
        try:
            self.game_audio.setMuted(muted)
            self.game_audio.setVolume(0.0 if muted else 0.8)
        except Exception:
            pass

    def _on_game_media_status_changed(self, status):
        if not self.game_player or self._is_emulator_running:
            return
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferingMedia, QMediaPlayer.BufferedMedia):
            if self._want_game_video_playing and self.isVisible():
                self._apply_game_audio_state(True)
                if self.game_player.playbackState() != QMediaPlayer.PlayingState:
                    self.game_player.play()
            else:
                self._apply_game_audio_state(False)
        elif status == QMediaPlayer.EndOfMedia:
            if self._want_game_video_playing and self.isVisible():
                self.game_player.play()

    def _on_game_player_error(self, error, error_string=""):
        if not self._is_emulator_running:
            self._game_video_image = None

    def _on_game_video_watchdog(self):
        if self._is_emulator_running or not self._want_game_video_playing or not self._pending_video_path or not self.isVisible():
            return
        if not os.path.isfile(self._pending_video_path) or not self.game_player:
            return
        if self.game_player.playbackState() == QMediaPlayer.PlayingState:
            return
        if self._game_video_image is None:
            try:
                src_url = QUrl.fromLocalFile(self._pending_video_path)
                if self.game_player.source() != src_url:
                    self.game_player.setSource(src_url)
                self.game_player.play()
            except Exception:
                pass

    def _on_game_frame(self, frame):
        if frame.isValid() and self.game_player:
            if not self._want_game_video_playing and not self._is_emulator_running:
                return
            if self._pending_video_path and self.game_player.source() != QUrl.fromLocalFile(self._pending_video_path):
                return
            img = frame.toImage()
            if not img.isNull():
                self._game_video_image = img
                self.update()

    # -------------------------------------------------------------------------
    # RESOLUCIÓN DE MEDIOS ARCADE Y FLYER
    # -------------------------------------------------------------------------
    def _find_media_file(self, folder: str | None, stem: str, exts: tuple[str, ...]) -> str | None:
        return cached_find_media_file(folder, stem, exts)

    def _resolve_game_media(self, game_dict: dict) -> dict:
        gid = game_dict.get("id")
        if gid in self._media_cache:
            return self._media_cache[gid]
        stem = Path(game_dict.get("rom_path", "")).stem if game_dict.get("rom_path") else ""
        img_exts = (".png", ".jpg", ".jpeg", ".webp")
        vid_exts = (".mp4", ".mkv", ".avi", ".webm")
        res = {
            "video": self._find_media_file(game_dict.get("video_path"), stem, vid_exts),
            "wheel": self._find_media_file(game_dict.get("wheel_path"), stem, img_exts),
            "cabinet": self._find_media_file(game_dict.get("cabinet_path"), stem, img_exts),
            "flyer": self._find_media_file(game_dict.get("flyer_path"), stem, img_exts),
            "marquee": self._find_media_file(game_dict.get("marquee_path"), stem, img_exts),
            "bezel": self._find_media_file(game_dict.get("bezel_path"), stem, img_exts),
        }
        self._media_cache[gid] = res
        return res

    def _get_cached_art_pixmap(self, path: str | None) -> QPixmap | None:
        if not path:
            return None
        if path in self._art_pix_cache:
            return self._art_pix_cache[path]
        pix = self._load_pixmap(path)
        if len(self._art_pix_cache) >= 120:
            self._art_pix_cache.pop(next(iter(self._art_pix_cache)), None)
        self._art_pix_cache[path] = pix
        return pix

    def _preload_adjacent_art(self, center_idx: int):
        n = len(self.games)
        if n <= 1:
            return
        for off in (-1, 1):
            m = self._resolve_game_media(self.games[(center_idx + off) % n])
            for k in ("cabinet", "marquee"):
                if m.get(k):
                    self._get_cached_art_pixmap(m[k])

    def _reset_flyer_state(self):
        self._flyer_ready = False
        self._flyer_slide = 1.0
        self._current_flyer_pix = None
        if hasattr(self, "_flyer_delay_timer"):
            self._flyer_delay_timer.stop()
        if hasattr(self, "_flyer_anim_timer") and self._flyer_anim_timer.isActive():
            self._flyer_anim_timer.stop()

    def _on_flyer_delay_timeout(self):
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self._reset_flyer_state()
            return
        flyer_file = self.current_media.get("flyer") if self.current_media else None
        self._current_flyer_pix = self._get_cached_art_pixmap(flyer_file) if flyer_file else None
        if self._current_flyer_pix and not self._current_flyer_pix.isNull():
            self._flyer_slide = 1.0
            self._flyer_ready = True
            self._flyer_anim_timer.start()
            self.update()
        else:
            self._flyer_ready = False
            self._current_flyer_pix = None

    def _on_flyer_anim_tick(self):
        if not self._flyer_ready or self._current_flyer_pix is None:
            self._flyer_anim_timer.stop()
            return
        if self._flyer_slide > 0.005:
            self._flyer_slide *= 0.82
            if self._flyer_slide < 0.005:
                self._flyer_slide = 0.0
                self._flyer_anim_timer.stop()
        else:
            self._flyer_slide = 0.0
            self._flyer_anim_timer.stop()
        self.update()

    def _on_art_debounce_timeout(self):
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return
        game = self.games[self.selected_index]
        self.current_game_id = game.get("id")
        self.current_media = self._resolve_game_media(game)
        self._load_current_game_art()
        if self.current_game_id is not None:
            self.game_selected.emit(self.current_game_id)
        self.update()

    def _load_current_game_art(self):
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return
        cab_pix = self._get_cached_art_pixmap(self.current_media.get("cabinet"))
        has_custom_cab = cab_pix is not None
        self._current_cabinet_pix = cab_pix if has_custom_cab else self._pix_cabinet

        marq_pix = self._get_cached_art_pixmap(self.current_media.get("marquee"))
        self._current_marquee_pix = marq_pix if marq_pix is not None else (None if has_custom_cab else self._pix_marquee_default)
        self._current_bezel_pix = self._get_cached_art_pixmap(self.current_media.get("bezel"))
        self.update()

    # -------------------------------------------------------------------------
    # CICLO DE SELECCIÓN Y MEDIOS
    # -------------------------------------------------------------------------
    def set_games(self, games: list[dict]):
        self._media_cache.clear()
        self._reset_flyer_state()
        self._init_bg_player()
        super().set_games(games or [])
        if self.games:
            self._flyer_delay_timer.start(int(self.FLYER_DELAY_MS))

    def _clear_selected_media(self):
        self._current_marquee_pix = self._pix_marquee_default
        self._current_cabinet_pix = self._pix_cabinet
        self._current_bezel_pix = None
        super()._clear_selected_media()

    def _navigate_steps(self, delta_steps: int, fast_repeat: bool = False):
        self._reset_flyer_state()
        if hasattr(self, "_art_debounce_timer"):
            self._art_debounce_timer.stop()
        super()._navigate_steps(delta_steps, fast_repeat=fast_repeat)
        if self.games:
            self._flyer_delay_timer.start(int(self.FLYER_DELAY_MS))

    def _update_current_selection(self, start_video: bool = True):
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self._clear_selected_media()
            return
        super()._update_current_selection()
        game = self.games[self.selected_index]
        self.current_media = self._resolve_game_media(game)
        self._load_current_game_art()
        self._reset_flyer_state()
        self._flyer_delay_timer.start(int(self.FLYER_DELAY_MS))
        if start_video:
            self._start_game_video()
        self.update()

    def _start_game_video(self):
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return
        game = self.games[self.selected_index]
        if not self.current_media or self.current_game_id != game.get("id"):
            self.current_game_id = game.get("id")
            self.current_media = self._resolve_game_media(game)
        video_path = self.current_media.get("video") if self.current_media else None
        if video_path and os.path.isfile(video_path):
            target_video, is_snap = video_path, True
        elif self._static_video_path and os.path.isfile(self._static_video_path):
            target_video, is_snap = self._static_video_path, False
        else:
            target_video, is_snap = None, False

        self._pending_video_path = target_video
        self._pending_video_is_snap = is_snap
        if not self.isVisible():
            return
        if target_video and os.path.isfile(target_video):
            self._init_game_player()
            if self.game_player:
                self._want_game_video_playing = True
                self._apply_game_audio_state(True)
                try:
                    src_url = QUrl.fromLocalFile(target_video)
                    if self.game_player.source() == src_url:
                        self.game_player.setPosition(0)
                    else:
                        self.game_player.setSource(src_url)
                    self.game_player.play()
                    self._video_watchdog_timer.start()
                except Exception:
                    pass
        else:
            self._want_game_video_playing = False
            self._apply_game_audio_state(False)
            if self.game_player:
                try:
                    self.game_player.stop()
                    self.game_player.setSource(QUrl())
                except Exception:
                    pass
            self._game_video_image = None
        self.update()

    def _play_debounced_video(self):
        self._start_game_video()
        self._flyer_delay_timer.start(int(self.FLYER_DELAY_MS))

    def set_media_muted(self, muted: bool):
        super().set_media_muted(muted)
        self._apply_game_audio_state(self._want_game_video_playing)

    def pause_media(self):
        self._is_emulator_running = True
        self._want_game_video_playing = False
        self._art_debounce_timer.stop()
        self._video_watchdog_timer.stop()
        self._commit_timer.stop()
        self._nav_pending_commit = False
        self._key_released_waiting_rest = False
        self._nav_key_pressed = False
        self._apply_game_audio_state(False)
        if self.game_player:
            try:
                self.game_player.pause()
            except Exception:
                pass
        if self.bg_player:
            try:
                self.bg_player.pause()
            except Exception:
                pass
        self.update()

    def resume_media(self):
        self._is_emulator_running = False
        self._want_game_video_playing = True
        self._init_bg_player()
        if self.bg_player and self.bg_player.playbackState() != QMediaPlayer.PlayingState:
            try:
                self.bg_player.play()
            except Exception:
                pass
        if self.game_player and self._pending_video_path and os.path.isfile(self._pending_video_path):
            self._apply_game_audio_state(True)
            try:
                if self.game_player.playbackState() != QMediaPlayer.PlayingState:
                    self.game_player.play()
                self._video_watchdog_timer.start()
            except Exception:
                pass
        elif self.games and 0 <= self.selected_index < len(self.games):
            self._start_game_video()
        self.update()

    def stop_media(self):
        self._is_emulator_running = False
        self._want_game_video_playing = False
        self._reset_flyer_state()
        if hasattr(self, "_art_debounce_timer"):
            self._art_debounce_timer.stop()
        if hasattr(self, "_video_watchdog_timer"):
            self._video_watchdog_timer.stop()
        self._apply_game_audio_state(False)
        if self.game_player and self.game_player.mediaStatus() == QMediaPlayer.BufferedMedia:
            try:
                self.game_player.pause()
            except Exception:
                pass
        self._game_video_image = None
        super().stop_media()

    def showEvent(self, event):
        super().showEvent(event)
        self._reset_flyer_state()
        self._init_bg_player()
        if self.bg_player and self.bg_player.playbackState() != QMediaPlayer.PlayingState:
            self.bg_player.play()
        if self._is_emulator_running:
            return
        if self.games and 0 <= self.selected_index < len(self.games):
            self._update_current_selection(start_video=True)
            self._reset_wheel_fade()
            self._flyer_delay_timer.start(int(self.FLYER_DELAY_MS))
        self.update()

    def hideEvent(self, event):
        self._reset_flyer_state()
        if self.bg_player:
            try:
                self.bg_player.pause()
            except Exception:
                pass
        if self._is_emulator_running:
            self.pause_media()
        else:
            self.stop_media()
        super().hideEvent(event)

    def closeEvent(self, event):
        if self.bg_player:
            try:
                self.bg_player.stop()
                self.bg_player.setSource(QUrl())
            except Exception:
                pass
            self.bg_player = None
            self.bg_sink = None
            self._bg_player_initialized = False
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # GEOMETRÍA DEL MUEBLE, RENDERIZADO Y RATÓN
    # -------------------------------------------------------------------------
    def _get_cab_dimensions(self) -> tuple[int, int]:
        w, h = self.width(), self.height()
        cab_w = int(h * (self.CAB_BASE_W / float(self.CAB_BASE_H)))
        max_cab_w = int(w * float(self.CAB_MAX_WIDTH_RATIO))
        return min(cab_w, max_cab_w), h

    def _draw_flyer(self, painter: QPainter, w: int, h: int):
        if not self._flyer_ready:
            return
        pix = self._current_flyer_pix
        if not pix or pix.isNull():
            return
        target_w = int(w * 0.22 * 1.30)
        target_h = int(h * 0.52 * 1.30)
        target_x = int(w * 0.67) + int(self._flyer_slide * (w * 0.35))
        target_y = int(h * 0.26)
        if target_x >= w:
            return
        pw, ph = pix.width(), pix.height()
        s = min(target_w / pw, target_h / ph) if pw > 0 and ph > 0 else 1.0
        dw, dh = int(pw * s), int(ph * s)
        ax = target_x + (target_w - dw) // 2
        ay = target_y + (target_h - dh) // 2
        painter.drawPixmap(QRect(ax, ay, dw, dh), pix)

    def _draw_footer(self, painter: QPainter, w: int, h: int):
        bar_h = max(26, int(h * 0.042))
        bar_y = h - bar_h
        if not getattr(self, "_skip_footer_bg", False):
            painter.fillRect(QRect(0, bar_y, w, bar_h), QColor(8, 6, 12, 225))
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return
        game = self.games[self.selected_index]
        title = game.get("title") or "Desconocido"
        painter.save()
        f_t = QFont(self._font_title, max(11, int(h * 0.024)), QFont.Bold)
        f_t.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        painter.setFont(f_t)
        painter.setPen(self.COLOR_FOOTER_TITLE)
        painter.drawText(QRect(int(w * 0.04), bar_y, int(w * 0.65), bar_h), Qt.AlignVCenter | Qt.AlignLeft, title.upper())

        counter_text = f"{self.FOOTER_COUNTER_PREFIX} {self.selected_index + 1} / {len(self.games)}"
        painter.setFont(QFont(self._font_main, max(10, int(h * 0.020)), QFont.Bold))
        painter.setPen(self.COLOR_FOOTER_COUNTER)
        painter.drawText(QRect(int(w * 0.70), bar_y, int(w * 0.26), bar_h), Qt.AlignVCenter | Qt.AlignRight, counter_text)
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        try:
            w, h = self.width(), self.height()
            if w <= 0 or h <= 0:
                return

            # 1. Video de fondo o fallback
            if self._bg_video_image and not self._bg_video_image.isNull():
                painter.drawImage(QRect(0, 0, w, h), self._bg_video_image)
            elif self._pix_bg_fallback:
                self._draw_cached_scaled(painter, "arcade_bg", self._pix_bg_fallback, 0, 0, w, h)
            else:
                painter.fillRect(QRect(0, 0, w, h), QColor(10, 8, 16))

            cab_w, cab_h = self._get_cab_dimensions()
            sx_cab = cab_w / float(self.CAB_BASE_W)
            sy_cab = cab_h / float(self.CAB_BASE_H)
            snap_rect = QRect(
                int(self.SNAP_LOCAL_RECT.x() * sx_cab),
                int(self.SNAP_LOCAL_RECT.y() * sy_cab),
                int(self.SNAP_LOCAL_RECT.width() * sx_cab),
                int(self.SNAP_LOCAL_RECT.height() * sy_cab),
            )
            marquee_rect = QRect(
                int(self.MARQUEE_LOCAL_RECT.x() * sx_cab),
                int(self.MARQUEE_LOCAL_RECT.y() * sy_cab),
                int(self.MARQUEE_LOCAL_RECT.width() * sx_cab),
                int(self.MARQUEE_LOCAL_RECT.height() * sy_cab),
            )

            # 2. Monitor CRT, Bezel y vidrio rayado
            painter.fillRect(snap_rect, QColor(0, 0, 0))
            if self._game_video_image and not self._game_video_image.isNull():
                vw, vh = self._game_video_image.width(), self._game_video_image.height()
                s = min(snap_rect.width() / vw, snap_rect.height() / vh) if vw > 0 and vh > 0 else 1.0
                dw, dh = int(vw * s), int(vh * s)
                vx = snap_rect.x() + (snap_rect.width() - dw) // 2
                vy = snap_rect.y() + (snap_rect.height() - dh) // 2
                painter.drawImage(QRect(vx, vy, dw, dh), self._game_video_image)

            if self._current_bezel_pix:
                painter.drawPixmap(snap_rect, self._current_bezel_pix)

            if self._pix_scratches:
                painter.save()
                painter.setOpacity(0.40)
                self._draw_cached_scaled(
                    painter, "scratches", self._pix_scratches,
                    snap_rect.x(), snap_rect.y(), snap_rect.width(), snap_rect.height(),
                )
                painter.restore()

            # 3. Marquesina y Mueble Arcade
            if self._current_marquee_pix:
                self._draw_cached_scaled(
                    painter, "marquee", self._current_marquee_pix,
                    marquee_rect.x(), marquee_rect.y(), marquee_rect.width(), marquee_rect.height(),
                )
                painter.fillRect(marquee_rect, QColor(255, 255, 255, 25))

            pix_cab = self._current_cabinet_pix or self._pix_cabinet
            if pix_cab:
                self._draw_cached_scaled(painter, "cabinet", pix_cab, 0, 0, cab_w, cab_h)

            # 4. Flyer deslizante
            self._draw_flyer(painter, w, h)

            # 5. Ruleta curva unificada y puntero selector (CommonThemeLayout)
            sr = self._get_target_rect()
            if self.games:
                self._draw_wheel_conveyor(painter, sr)
            self._draw_pointer(painter, sr)

            # 6. Barra inferior arcade
            self._draw_footer(painter, w, h)
        finally:
            painter.end()

    def mouseReleaseEvent(self, event):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._mouse_pressed_pos is not None:
            pos = self._mouse_pressed_pos
            self._mouse_pressed_pos = None

            cab_w, cab_h = self._get_cab_dimensions()
            sx_cab = cab_w / float(self.CAB_BASE_W)
            sy_cab = cab_h / float(self.CAB_BASE_H)
            snap_rect = QRect(
                int(self.SNAP_LOCAL_RECT.x() * sx_cab),
                int(self.SNAP_LOCAL_RECT.y() * sy_cab),
                int(self.SNAP_LOCAL_RECT.width() * sx_cab),
                int(self.SNAP_LOCAL_RECT.height() * sy_cab),
            )
            if snap_rect.contains(pos.toPoint()):
                gid = self.get_selected_game_id()
                if gid and self._can_activate_game():
                    self._play_select_sound()
                    self.game_activated.emit(gid)
                event.accept()
                return

            if self.games:
                dy = event.position().y() - pos.y()
                if abs(dy) >= 25:
                    self._navigate_steps(1 if dy > 0 else -1)
                    self._commit_selection()
                    event.accept()
                    return
                hit_off = self._hit_test_wheel_offset(pos.x(), pos.y())
                if hit_off is not None:
                    target_idx = (self.selected_index + hit_off) % len(self.games)
                    if target_idx == self.selected_index:
                        gid = self.get_selected_game_id()
                        if gid and self._can_activate_game():
                            self._play_select_sound()
                            self.game_activated.emit(gid)
                    else:
                        self._navigate_steps(hit_off)
                        self._commit_selection()
                    event.accept()
                    return

            if pos.y() < self.height() * 0.40:
                self._navigate_steps(1)
                self._commit_selection()
            elif pos.y() > self.height() * 0.60:
                self._navigate_steps(-1)
                self._commit_selection()
            else:
                gid = self.get_selected_game_id()
                if gid and self._can_activate_game():
                    self._play_select_sound()
                    self.game_activated.emit(gid)
            event.accept()
            return
        super().mouseReleaseEvent(event)


# --- PLAYNEXUS STUDIO OVERRIDES START ---
STUDIO_ELEMENTS = [
    {'id': 'bg_image', 'name': 'Fondo (gtc-common)', 'type': 'image', 'x': 0.0, 'y': 0.0, 'w': 1920.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 5, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 0.0, 1920.0, 1080.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'video_snap', 'name': 'Pantalla CRT (Video Snap)', 'type': 'video', 'x': 200.0, 'y': 318.0, 'w': 706.0, 'h': 526.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 10, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [200.0, 318.0, 706.0, 526.0], 'media_key': 'video', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'bezel', 'name': 'Bisel de Monitor (Bezel)', 'type': 'image', 'x': 200.0, 'y': 318.0, 'w': 706.0, 'h': 526.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 15, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [200.0, 318.0, 706.0, 526.0], 'media_key': 'bezel', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'scratches', 'name': 'Reflejo Vidrio CRT (gtc-common)', 'type': 'effect', 'x': 200.0, 'y': 318.0, 'w': 706.0, 'h': 526.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 20, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [200.0, 318.0, 706.0, 526.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'marquee', 'name': 'Marquesina (Marquee)', 'type': 'marquee', 'x': 138.0, 'y': 0.0, 'w': 832.0, 'h': 227.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 25, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [138.0, 0.0, 832.0, 227.0], 'media_key': 'marquee', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'cabinet', 'name': 'Mueble Arcade (Cabinet)', 'type': 'cabinet', 'x': 0.0, 'y': 0.0, 'w': 1300.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 30, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 0.0, 1300.0, 1080.0], 'media_key': 'cabinet', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'flyer', 'name': 'Flyer Publicitario', 'type': 'image', 'x': 1286.4, 'y': 280.8, 'w': 549.1, 'h': 730.1, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 35, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1286.4, 280.8, 549.1, 730.1], 'media_key': 'flyer', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'flyer_slide_right', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'wheel_list', 'name': 'Ruleta Curva (Wheel Conveyor)', 'type': 'wheel', 'x': 1200.0, 'y': 0.0, 'w': 720.0, 'h': 1080.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 40, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1200.0, 0.0, 720.0, 1080.0], 'media_key': 'wheel', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'pointer', 'name': 'Puntero de Ruleta', 'type': 'image', 'x': 1772.0, 'y': 428.0, 'w': 140.0, 'h': 256.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 45, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1772.0, 428.0, 140.0, 256.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': 'pointer_pulse', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'footer_frame', 'name': 'Barra Inferior (Footer)', 'type': 'image', 'x': 0.0, 'y': 1035.0, 'w': 1920.0, 'h': 45.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 50, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [0.0, 1035.0, 1920.0, 45.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'title_text', 'name': 'Título del Juego (Footer)', 'type': 'text', 'x': 76.8, 'y': 1035.0, 'w': 1190.4, 'h': 45.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 55, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [76.8, 1035.0, 1190.4, 45.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
    {'id': 'counter_text', 'name': 'Contador de Juegos (Footer)', 'type': 'text', 'x': 1344.0, 'y': 1035.0, 'w': 499.2, 'h': 45.0, 'rotation': 0.0, 'opacity': 1.0, 'z_index': 60, 'visible': True, 'locked': False, 'corner_pins': None, 'orig_rect': [1344.0, 1035.0, 499.2, 45.0], 'media_key': '', 'resource_path': '', 'text_template': '{title}', 'font_file': '', 'font_size': 24, 'text_color': '#ffffff', 'text_align': 'left', 'wheel_orientation': 'vertical', 'wheel_visible_items': 9, 'wheel_item_spacing': 85.0, 'wheel_curvature': 0.0, 'effect_type': '', 'effect_intensity': 0.4, 'effect_param': 4.0, 'anim_type': '', 'anim_delay': 0.0, 'anim_duration': 0.8},
]
try:
    from playnexus.ui.layout_studio.runtime_hook import install_studio_overrides as _install_studio_overrides
    _orig_init = ThemeLayout.__init__
    def _studio_patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        _install_studio_overrides(self, STUDIO_ELEMENTS)
    if not getattr(ThemeLayout.__init__, '_is_studio_patched', False):
        _orig_init = ThemeLayout.__init__
        _studio_patched_init._is_studio_patched = True
        ThemeLayout.__init__ = _studio_patched_init
except Exception:
    pass
# --- PLAYNEXUS STUDIO OVERRIDES END ---
