"""
=============================================================================
Clases Base Compartidas para Layouts Temáticos de PlayNexus
=============================================================================
Centraliza la arquitectura común de los layouts bajo `Layouts/`:
- `CommonThemeLayout`: Motor compartido de fuentes, sonidos, video snap,
  worker de precarga de wheels, navegación con Commit on Release (Regla 5),
  atajos configurables (`matches_action`), ruleta conveyor curva unificada
  de 14 nodos compatible con OpenGL/GPU (Regla 9 y 10), puntero y barra inferior.
- `ConsoleThemeLayout`: Especialización declarativa para layouts de consola
  (TV CRT, consola/tapa/joystick, avatar flotante, logo con rebote, cartucho
  deslizante o disco CD giratorio, boxart con anclaje inferior/central y Z-order
  configurable mediante `LAYER_ORDER`).
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QPoint, QRect, QSize, QTimer, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect, QVideoSink

from playnexus.services.controls import (
    ACTION_MUTE,
    ACTION_NAV_BACK,
    ACTION_NAV_DOWN,
    ACTION_NAV_LETTER,
    ACTION_NAV_LETTER_BACK,
    ACTION_NAV_LETTER_FWD,
    ACTION_NAV_STEP5,
    ACTION_NAV_STEP5_BACK,
    ACTION_NAV_STEP5_FWD,
    ACTION_NAV_UP,
    ACTION_PAGE_DOWN,
    ACTION_PAGE_UP,
    ACTION_SELECT,
    matches_action,
)
from playnexus.services.media import resolve_game_media
from playnexus.ui.cover_utils import load_cover
from playnexus.ui.layouts.base import BaseLayout, WheelPreloadWorker

_LOADED_FONT_CACHE: dict[str, str] = {}


class CommonThemeLayout(BaseLayout):
    """Base común para todos los layouts temáticos con ruleta curva unificada."""

    LAYOUT_NAME = "Theme"
    LAYOUT_DESCRIPTION = ""

    CANONICAL_W = 1920
    CANONICAL_H = 1080

    # 1. Requerimientos explícitos de medios (Regla 4 y 8: cada subclase declara los suyos)
    MEDIA_REQUIREMENTS: list[dict[str, Any]] = []

    # 2. Fuentes tipográficas
    FONT_TITLE_FILE: str | Path | None = None
    FONT_MAIN_FILE: str | Path | None = None
    FONT_COUNTER_FILE: str | Path | None = None
    FONT_FILES: list[str | Path | None] = []

    # 3. Recursos compartidos (gtc-common) y puntero/sombra
    WHEEL_SHADOW_IMAGE: str | Path | None = None
    COMMON_WHEEL_ART: str | Path | None = None
    COMMON_FRAME: str | Path | None = None
    STATIC_VIDEO: str | Path | None = None
    SOUND_NAV: str | Path | None = None
    SOUND_SELECT: str | Path | None = None
    SCANLINES_IMAGE: str | Path | None = None
    SCRATCHES_IMAGE: str | Path | None = None
    WHEEL_IMAGE: str | Path | None = None
    WHEEL_ART_IMAGE: str | Path | None = None
    POINTER_IMAGE: str | Path | None = None

    # 4. Métricas unificadas de la ruleta curva (14 nodos interpolados a 60 FPS)
    CONVEYOR_X = [0.89, 0.85, 0.83, 0.80, 0.77, 0.74, 0.71, 0.625, 0.71, 0.74, 0.77, 0.80, 0.83, 0.89]
    CONVEYOR_Y = [-0.34, -0.22, -0.105, 0.00, 0.105, 0.215, 0.325, 0.421, 0.59, 0.70, 0.81, 0.915, 0.99, 1.12]
    CONVEYOR_W = [0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.30, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18]
    CONVEYOR_H = [0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.186, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
    CONVEYOR_R = [35.0, 30.0, 25.0, 20.0, 15.0, 10.0, 5.0, 0.0, -10.0, -15.0, -20.0, -25.0, -30.0, -35.0]
    CONVEYOR_A = [0, 20, 35, 60, 90, 125, 160, 255, 160, 125, 90, 60, 35, 0]

    # Estilo unificado de tarjetas de texto de respaldo en la ruleta
    WHEEL_CARD_SELECTED_BG = (220, 50, 40, 215)
    WHEEL_CARD_BG = (22, 26, 40, 185)
    WHEEL_CARD_SELECTED_BORDER = (255, 255, 255, 230)
    WHEEL_CARD_BORDER = (75, 85, 115, 130)
    WHEEL_FADEOUT_DELAY_MS: int | None = None

    # Puntero e intervalos estándar
    POINTER_REST_X_RATIO = 0.905
    POINTER_PULSE_X_RATIO = 0.880
    NAV_COMMIT_DEBOUNCE_MS = 180
    VIDEO_DEBOUNCE_MS = 100
    VIDEO_AUDIO_VOLUME = 0.8

    # Métricas y estilo configurables de la barra inferior
    BOTTOM_BAR_H_RATIO = 0.075
    BOTTOM_TITLE_X_RATIO = 0.08
    BOTTOM_TITLE_W_RATIO = 0.62
    BOTTOM_COUNTER_X_RATIO = 0.70
    BOTTOM_COUNTER_W_RATIO = 0.26
    BOTTOM_BAR_BG_COLOR = (8, 10, 20, 235)
    BOTTOM_COUNTER_COLOR = (245, 185, 35)
    BOTTOM_COUNTER_PREFIX = "GAME"
    BOTTOM_UPPERCASE_TITLE = False
    BOTTOM_INCLUDE_YEAR_MANU = True
    BOTTOM_USE_FRAME = True
    BOTTOM_LETTER_SPACING = 0.0

    def __init__(self, theme_name: str | None = None, parent=None):
        """Inicializa estado base, worker de ruedas, sonidos, fuentes y temporizadores."""
        if theme_name is not None and not isinstance(theme_name, str):
            parent = theme_name
            theme_name = None
        resolved_name = theme_name or getattr(self, "LAYOUT_NAME", "Theme")
        super().__init__(parent=parent, theme_name=resolved_name)

        self.theme_name = resolved_name
        self.layout_dir = self._resolve_layout_dir()
        self.common_dir = self._resolve_common_dir()

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.selected_index = 0
        self.current_media: dict[str, Any] = {}
        self._wheel_pixmaps: dict[Any, QPixmap] = {}
        self._art_pix_cache: dict[str, QPixmap | None] = {}
        self._scaled_layer_cache: dict[str, tuple[tuple[int, int, int], QPixmap]] = {}
        self._pending_video_path: str | None = None
        self._pending_video_play_on_show = False

        # Hilo de precarga asíncrona de logotipos de ruleta
        self._wheel_worker = WheelPreloadWorker(self)
        self._wheel_worker.wheel_loaded.connect(self._on_wheel_image_loaded)
        self._wheel_worker.start()

        # Reproductor de video snap (inicialización perezosa)
        self._player_initialized = False
        self.player: QMediaPlayer | None = None
        self.audio_output: QAudioOutput | None = None
        self.video_sink: QVideoSink | None = None
        self._want_video_playing = False
        self._media_muted = False
        self.db = None
        self._current_video_image: QImage | None = None

        # Sonidos de navegación y selección
        self._sound_effect = QSoundEffect(self)
        self._sound_effect.setVolume(0.4)
        nav_snd = self._resolve_existing_path(self.SOUND_NAV, self.common_dir / "sounds" / "joystick.mp3")
        if nav_snd:
            self._sound_effect.setSource(QUrl.fromLocalFile(nav_snd))

        self._select_sound_effect = QSoundEffect(self)
        self._select_sound_effect.setVolume(0.5)
        sel_snd = self._resolve_existing_path(self.SOUND_SELECT, self.common_dir / "sounds" / "Mame_coin.mp3")
        if sel_snd:
            self._select_sound_effect.setSource(QUrl.fromLocalFile(sel_snd))

        # Recursos compartidos y puntero/sombra de ruleta
        self._pix_scanlines = None
        self._pix_scratches = self._load_pixmap(self._resolve_existing_path(self.SCRATCHES_IMAGE))
        self._pix_wheel_art = self._load_pixmap(
            self._resolve_existing_path(self.WHEEL_ART_IMAGE, self.COMMON_WHEEL_ART)
        )
        self._pix_frame = self._load_pixmap(self._resolve_existing_path(self.COMMON_FRAME))
        static_vid = self._resolve_existing_path(self.STATIC_VIDEO)
        self._static_video_path = static_vid
        self._pix_wheel_shadow = self._load_pixmap(self._resolve_existing_path(self.WHEEL_SHADOW_IMAGE))
        self._pix_wheel = self._load_pixmap(self._resolve_existing_path(self.WHEEL_IMAGE))

        ptr_path = self._resolve_existing_path(self.POINTER_IMAGE)
        if not ptr_path:
            ptr_path = self._resolve_file("pointers/default.png")
        self._pix_pointer = self._load_pixmap(ptr_path)

        # Estado del puntero
        self._pointer_rest_x_ratio = float(self.POINTER_REST_X_RATIO)
        self._pointer_pulse_x_ratio = float(self.POINTER_PULSE_X_RATIO)
        self._pointer_current_x_ratio = self._pointer_rest_x_ratio
        self._pointer_anim_tick = 0
        self._pointer_anim_timer = QTimer(self)
        self._pointer_anim_timer.timeout.connect(self._on_pointer_tick)
        if self._pix_pointer:
            self._pointer_anim_timer.start(16)

        # Tipografías
        self._font_title = "sans-serif"
        self._font_main = "sans-serif"
        self._font_bebas = "sans-serif"
        self._font_handel = "sans-serif"
        self._font_slapstick = "sans-serif"
        self._load_theme_fonts()

        # Animación de giro continuo y desvanecimiento opcional de ruleta
        self._wheel_spin_offset = 0.0
        self._wheel_spin_timer = QTimer(self)
        self._wheel_spin_timer.setTimerType(Qt.PreciseTimer)
        self._wheel_spin_timer.timeout.connect(self._on_wheel_spin_tick)

        self._wheel_alpha = 255.0
        self._wheel_target_alpha = 255.0
        self._wheel_fade_timer: QTimer | None = None
        self._wheel_fadeout_delay_timer: QTimer | None = None
        if self.WHEEL_FADEOUT_DELAY_MS:
            self._wheel_fade_timer = QTimer(self)
            self._wheel_fade_timer.timeout.connect(self._on_wheel_fade_tick)
            self._wheel_fadeout_delay_timer = QTimer(self)
            self._wheel_fadeout_delay_timer.setSingleShot(True)
            self._wheel_fadeout_delay_timer.timeout.connect(self._start_wheel_fadeout)

        # Confirmación de selección diferida al soltar tecla o reposo (Regla 5)
        self._nav_pending_commit = False
        self._nav_key_pressed = False
        self._key_released_waiting_rest = False
        self._mouse_pressed_pos: Any = None
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(int(self.NAV_COMMIT_DEBOUNCE_MS))
        self._commit_timer.timeout.connect(self._commit_selection)

        self._init_extra_resources()

    def _init_extra_resources(self):
        """Hook para que subclases carguen recursos e inicialicen animaciones propias."""

    # -------------------------------------------------------------------------
    # RESOLUCIÓN DE RUTAS Y FUENTES
    # -------------------------------------------------------------------------
    @classmethod
    def _resolve_layout_dir(cls) -> Path:
        ld = getattr(cls, "LAYOUT_DIR", None)
        if isinstance(ld, Path):
            return ld
        mod = sys.modules.get(cls.__module__)
        mod_dict = getattr(mod, "__dict__", {}) if mod else {}
        if isinstance(mod_dict.get("LAYOUT_DIR"), Path):
            return mod_dict["LAYOUT_DIR"]
        mod_file = getattr(mod, "__file__", None)
        if mod_file:
            return Path(mod_file).resolve().parent
        return Path.cwd()

    @classmethod
    def _resolve_common_dir(cls) -> Path:
        cd = getattr(cls, "COMMON_DIR", None)
        if isinstance(cd, Path):
            return cd
        return cls._resolve_layout_dir().parent / "gtc-common"

    @classmethod
    def _resolve_file(cls, rel_path: str | Path | None) -> str | None:
        """Resuelve una ruta relativa dentro de la carpeta propia del layout."""
        if not rel_path:
            return None
        layout_dir = cls._resolve_layout_dir()
        rel_str = str(rel_path).strip()
        if not rel_str:
            return None
        p = Path(rel_str)
        if p.is_absolute() and p.is_file():
            return str(p)
        for cand in (layout_dir / p, layout_dir / p.name, layout_dir / "pointers" / p.name):
            if cand.is_file():
                return str(cand)
        return None

    def _resolve_existing_path(self, *candidates: str | Path | None) -> str | None:
        """Retorna la primera ruta existente (archivo válido, nunca directorio)."""
        for cand in candidates:
            if cand is None:
                continue
            s = str(cand).strip()
            if not s or s == str(self.layout_dir):
                continue
            p = Path(s)
            if p.is_file():
                return str(p)
        return None

    def _load_pixmap(self, path: str | Path | None) -> QPixmap | None:
        """Carga un QPixmap con caché global verificando que la ruta sea un archivo."""
        resolved = self._resolve_existing_path(path)
        return super()._load_pixmap(resolved) if resolved else None

    def _load_font_family(self, font_spec: str | Path | None) -> str:
        """Registra una fuente local o de `gtc-common/fonts` y retorna su familia."""
        if not font_spec:
            return "sans-serif"
        spec_str = str(font_spec).strip()
        if not spec_str:
            return "sans-serif"
        p = Path(spec_str)
        candidates: list[Path] = []
        if p.is_absolute():
            candidates.append(p)
        candidates.extend([
            self.layout_dir / p,
            self.layout_dir / p.name,
            self.common_dir / "fonts" / p.name,
        ])
        for font_path in candidates:
            if not font_path.is_file():
                continue
            cache_key = os.path.normcase(os.path.abspath(str(font_path)))
            if cache_key in _LOADED_FONT_CACHE:
                return _LOADED_FONT_CACHE[cache_key]
            fid = QFontDatabase.addApplicationFont(str(font_path))
            if fid != -1:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    _LOADED_FONT_CACHE[cache_key] = families[0]
                    return families[0]
        return "sans-serif"

    def _load_theme_fonts(self):
        """Carga las fuentes declaradas en la cabecera del layout."""
        title_spec = getattr(self, "FONT_TITLE_FILE", None)
        main_spec = getattr(self, "FONT_MAIN_FILE", None) or getattr(self, "FONT_COUNTER_FILE", None)
        self._font_title = self._load_font_family(title_spec)
        self._font_main = self._load_font_family(main_spec)
        self._font_bebas = self._font_title
        self._font_handel = self._font_main
        self._font_slapstick = self._font_title

    # -------------------------------------------------------------------------
    # SONIDO Y AUDIO
    # -------------------------------------------------------------------------
    def _play_wheel_sound(self):
        """Reproduce el sonido de navegación al mover la ruleta."""
        if getattr(self, "_media_muted", False):
            return
        try:
            if self._sound_effect.source().isValid():
                self._sound_effect.play()
        except Exception:
            pass

    _play_nav_sound = _play_wheel_sound

    def _play_select_sound(self):
        """Reproduce el sonido característico al lanzar o confirmar un juego."""
        if getattr(self, "_media_muted", False):
            return
        try:
            if self._select_sound_effect.source().isValid():
                self._select_sound_effect.play()
        except Exception:
            pass

    def _apply_audio_state(self, active: bool):
        """Aplica estado de silencio/volumen al `QAudioOutput` principal."""
        if not self.audio_output:
            return
        muted = bool(self._media_muted) or (not active)
        try:
            self.audio_output.setMuted(muted)
            self.audio_output.setVolume(0.0 if muted else float(self.VIDEO_AUDIO_VOLUME))
        except Exception:
            pass

    def set_media_muted(self, muted: bool):
        """Silencia o reactiva el audio del video y de los efectos del layout."""
        self._media_muted = bool(muted)
        for eff_name, vol in (("_sound_effect", 0.4), ("_select_sound_effect", 0.5)):
            eff = getattr(self, eff_name, None)
            if eff:
                try:
                    eff.setMuted(self._media_muted)
                    eff.setVolume(0.0 if self._media_muted else vol)
                except Exception:
                    pass
        self._apply_audio_state(active=self._want_video_playing)

    def set_muted(self, muted: bool):
        self.set_media_muted(muted)

    def is_muted(self) -> bool:
        return bool(self._media_muted)

    # -------------------------------------------------------------------------
    # REPRODUCTOR DE VIDEO SNAP
    # -------------------------------------------------------------------------
    def _ensure_player_initialized(self):
        """Inicializa perezosamente el `QMediaPlayer` y temporizadores de video."""
        if self._player_initialized:
            return
        self._player_initialized = True
        self._want_video_playing = False
        self._video_debounce_timer = QTimer(self)
        self._video_debounce_timer.setSingleShot(True)
        self._video_debounce_timer.setInterval(int(self.VIDEO_DEBOUNCE_MS))
        self._video_debounce_timer.timeout.connect(self._play_debounced_video)

        self._video_watchdog_timer = QTimer(self)
        self._video_watchdog_timer.setSingleShot(True)
        self._video_watchdog_timer.setInterval(1200)
        self._video_watchdog_timer.timeout.connect(self._on_video_watchdog)

        self.player = QMediaPlayer(self)
        self.player.setLoops(QMediaPlayer.Infinite)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self._apply_audio_state(active=False)

        self.video_sink = QVideoSink(self)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_player_error)

    def _on_video_frame_changed(self, frame):
        """Convierte el frame en modo software y solicita repintado."""
        if frame.isValid() and self._want_video_playing and self.player:
            p_path = self._pending_video_path
            if p_path and self.player.source() != QUrl.fromLocalFile(p_path):
                return
            img = frame.toImage()
            if not img.isNull():
                self._current_video_image = img
                self.update()

    def _on_media_status_changed(self, status):
        """Garantiza reproducción continua y bucle infinito al cargar el medio."""
        if not self.player:
            return
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferingMedia, QMediaPlayer.BufferedMedia):
            if self._want_video_playing and self.isVisible():
                self._apply_audio_state(active=True)
                if self.player.playbackState() != QMediaPlayer.PlayingState:
                    self.player.play()
            else:
                self._apply_audio_state(active=False)
        elif status == QMediaPlayer.EndOfMedia:
            if self._want_video_playing and self.isVisible():
                self.player.setPosition(0)
                self.player.play()

    def _on_player_error(self, error, error_string=""):
        self._current_video_image = None

    def _on_video_watchdog(self):
        """Reintenta reproducción si el video quedó atascado tras cambiar de juego."""
        if not self._want_video_playing or not self._pending_video_path or not self.isVisible():
            return
        if not os.path.isfile(self._pending_video_path) or not self.player:
            return
        if self.player.mediaStatus() == QMediaPlayer.LoadingMedia:
            return
        if self._current_video_image is None or self.player.playbackState() != QMediaPlayer.PlayingState:
            try:
                src_url = QUrl.fromLocalFile(self._pending_video_path)
                if self.player.source() != src_url:
                    self.player.setSource(src_url)
                self.player.play()
            except Exception:
                pass

    def _queue_video_playback(self, video_to_play: str | None):
        """Programa la reproducción diferida de un video o detiene el actual si no hay fuente."""
        self._ensure_player_initialized()
        self._pending_video_path = video_to_play
        if not video_to_play:
            self._want_video_playing = False
            self._apply_audio_state(active=False)
            if self.player:
                self.player.stop()
            self._current_video_image = None
            self.update()
            return
        self._video_debounce_timer.start(int(self.VIDEO_DEBOUNCE_MS))

    def _play_debounced_video(self):
        """Inicia la reproducción del video confirmado sin disparar recargas redundantes de arte."""
        if not self.isVisible():
            self._pending_video_play_on_show = True
            return
        self._pending_video_play_on_show = False
        video_to_play = self._pending_video_path
        if video_to_play and os.path.isfile(video_to_play):
            self._want_video_playing = True
            self._apply_audio_state(active=True)
            source_url = QUrl.fromLocalFile(video_to_play)
            try:
                if self.player and self.player.source() == source_url:
                    if self.player.playbackState() != QMediaPlayer.PlayingState:
                        self.player.play()
                elif self.player:
                    self.player.setSource(source_url)
                    self.player.play()
                if hasattr(self, "_video_watchdog_timer"):
                    self._video_watchdog_timer.start()
            except Exception:
                pass
        else:
            self._want_video_playing = False
            self._apply_audio_state(active=False)
            if self.player:
                try:
                    self.player.stop()
                    self.player.setSource(QUrl())
                except Exception:
                    pass
            self._current_video_image = None
            self.update()

    def pause_media(self):
        """Pausa temporalmente el video (ej. mientras corre un emulador o al ocultarse)."""
        if self.player:
            try:
                self.player.pause()
            except Exception:
                pass
        self._apply_audio_state(active=False)

    def resume_media(self):
        """Reanuda el video si había reproducción pendiente o activa."""
        if self._pending_video_play_on_show and self._pending_video_path:
            self._play_debounced_video()
            return
        if self._want_video_playing and self.player and self.isVisible():
            self._apply_audio_state(active=True)
            try:
                if self.player.playbackState() != QMediaPlayer.PlayingState:
                    self.player.play()
            except Exception:
                pass

    def stop_media(self):
        """Detiene el reproductor y todos los temporizadores de confirmación."""
        self._want_video_playing = False
        self._pending_video_path = None
        self._pending_video_play_on_show = False
        self._nav_pending_commit = False
        self._nav_key_pressed = False
        self._key_released_waiting_rest = False
        for tname in ("_commit_timer", "_video_debounce_timer", "_video_watchdog_timer"):
            tmr = getattr(self, tname, None)
            if tmr:
                tmr.stop()
        self._apply_audio_state(active=False)
        if self.player:
            try:
                self.player.stop()
                self.player.setSource(QUrl())
            except Exception:
                pass
        self._current_video_image = None
        self.update()

    # -------------------------------------------------------------------------
    # GESTIÓN DE JUEGOS, WHEELS Y NAVEGACIÓN (REGLAS 5 Y 10)
    # -------------------------------------------------------------------------
    def set_db(self, db):
        self.db = db
        if self.games and 0 <= self.selected_index < len(self.games):
            self._update_current_selection()

    def set_games(self, games: list):
        """Carga la lista de juegos, reinicia el enfoque y dispara precarga de wheels."""
        self.games = [dict(g) if hasattr(g, "keys") else g for g in games]
        self.selected_index = 0
        self._wheel_spin_offset = 0.0
        self._wheel_pixmaps.clear()
        if self._wheel_worker:
            self._wheel_worker.clear()
        if self.games:
            self._update_current_selection()
            self._on_games_loaded()
            self._preload_around(0)
            self._reset_wheel_fade()
        else:
            self._clear_selected_media()
        self.update()

    def _on_games_loaded(self):
        """Hook ejecutado una vez al cargar una nueva lista de juegos."""

    def _clear_selected_media(self):
        self.current_media = {}
        self.stop_media()

    def render_games(self):
        self.update()

    def select_game_by_id(self, game_id: int):
        """Selecciona un juego concreto por su ID."""
        for i, g in enumerate(self.games):
            if g.get("id") == game_id:
                if self.selected_index != i:
                    self.selected_index = i
                    self._update_current_selection()
                    self._preload_around(i)
                    self._reset_wheel_fade()
                    self.update()
                break

    def get_selected_game_id(self) -> int | None:
        if self.games and 0 <= self.selected_index < len(self.games):
            return self.games[self.selected_index].get("id")
        return None

    def _update_current_selection(self):
        """Debe ser implementado o extendido por subclases para cargar medios del ítem activo."""
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self._clear_selected_media()
            return
        game = self.games[self.selected_index]
        gid = game.get("id")
        self.current_game_id = gid
        if gid is not None:
            self.game_selected.emit(gid)

    def _on_wheel_image_loaded(self, gid: int, img: QImage):
        if not img.isNull():
            self._wheel_pixmaps[gid] = QPixmap.fromImage(img)
            if len(self._wheel_pixmaps) > 600:
                for old_gid in list(self._wheel_pixmaps.keys()):
                    if not self._is_game_visible_in_wheel(old_gid):
                        del self._wheel_pixmaps[old_gid]
                        break
            if self._is_game_visible_in_wheel(gid):
                self.update()

    def _is_game_visible_in_wheel(self, game_id: int) -> bool:
        if not self.games:
            return False
        n = len(self.games)
        for offset in (-6, 6, -5, 5, -4, 4, -3, 3, -2, 2, -1, 1, 0):
            if self.games[(self.selected_index + offset) % n].get("id") == game_id:
                return True
        return False

    def _preload_around(self, center_idx: int):
        """Encola precarga de logotipos cercanos alrededor de `center_idx`."""
        if not self.games or not self._wheel_worker:
            return
        n = len(self.games)
        window = [
            self.games[(center_idx + i) % n]
            for i in range(-4, 12)
            if self.games[(center_idx + i) % n].get("id") not in self._wheel_pixmaps
        ]
        if window:
            self._wheel_worker.queue_games(window)
        self._preload_adjacent_art(center_idx)

    def _preload_adjacent_art(self, center_idx: int):
        """Hook opcional para precargar artes vecinos al índice actual."""

    def _preload_direction(self, steps: int):
        """Encola precarga predictiva de logotipos en la dirección de desplazamiento."""
        if not self.games or not self._wheel_worker:
            return
        n = len(self.games)
        direction = 1 if steps > 0 else -1
        count = 30 if abs(steps) <= 1 else 50
        window = [
            self.games[(self.selected_index + (i * direction)) % n]
            for i in range(1, count + 1)
            if self.games[(self.selected_index + (i * direction)) % n].get("id") not in self._wheel_pixmaps
        ]
        if window:
            self._wheel_worker.queue_games(window, priority=True)

    def _get_game_wheel_pixmap(self, game: dict) -> QPixmap | None:
        gid = game.get("id")
        if gid in self._wheel_pixmaps:
            return self._wheel_pixmaps[gid]
        if self._wheel_worker:
            self._wheel_worker.queue_game(game, priority=True)
        return None

    def _reset_wheel_fade(self):
        """Restaura opacidad total de ruleta y reprograma fadeout si está habilitado."""
        if not self.WHEEL_FADEOUT_DELAY_MS:
            return
        self._wheel_alpha = 255.0
        self._wheel_target_alpha = 255.0
        if self._wheel_fade_timer and self._wheel_fade_timer.isActive():
            self._wheel_fade_timer.stop()
        if self._wheel_fadeout_delay_timer:
            self._wheel_fadeout_delay_timer.start(int(self.WHEEL_FADEOUT_DELAY_MS))

    def _start_wheel_fadeout(self):
        self._wheel_target_alpha = 0.0
        if self._wheel_fade_timer and not self._wheel_fade_timer.isActive():
            self._wheel_fade_timer.start(16)

    def _on_wheel_fade_tick(self):
        diff = self._wheel_target_alpha - self._wheel_alpha
        if abs(diff) > 1.0:
            self._wheel_alpha += diff * 0.12
            self.update()
        else:
            self._wheel_alpha = self._wheel_target_alpha
            if self._wheel_fade_timer:
                self._wheel_fade_timer.stop()
            self.update()

    def _navigate_steps(self, delta_steps: int, fast_repeat: bool = False):
        """Desplaza la ruleta N posiciones diferiendo la carga de medios al soltar (Regla 5)."""
        n = len(self.games)
        if n == 0 or delta_steps == 0:
            return

        self._preload_direction(delta_steps)
        self.selected_index = (self.selected_index + delta_steps) % n
        self._wheel_spin_offset += float(delta_steps)
        self._wheel_spin_offset = max(-5.0, min(5.0, self._wheel_spin_offset))
        self._pointer_current_x_ratio = self._pointer_pulse_x_ratio
        self._reset_wheel_fade()
        self._play_wheel_sound()

        # Mantener reproducción fluida del video anterior hasta confirmar selección
        if hasattr(self, "_video_debounce_timer"):
            self._video_debounce_timer.stop()
        if hasattr(self, "_video_watchdog_timer"):
            self._video_watchdog_timer.stop()
        self._nav_pending_commit = True
        self._key_released_waiting_rest = False
        self._commit_timer.start(int(self.NAV_COMMIT_DEBOUNCE_MS))

        if not self._wheel_spin_timer.isActive():
            self._wheel_spin_timer.start(16)
        self.update()

    def _commit_selection(self):
        """Aplica la selección y carga artes/video únicamente cuando terminó el desplazamiento."""
        if not self._nav_pending_commit:
            return
        if self._nav_key_pressed:
            return
        if abs(self._wheel_spin_offset) >= 0.05:
            self._key_released_waiting_rest = True
            return
        self._nav_pending_commit = False
        self._key_released_waiting_rest = False
        self._commit_timer.stop()
        self._update_current_selection()

    def _on_wheel_spin_tick(self):
        """Suaviza el giro continuo de la ruleta a 60 FPS."""
        self._wheel_spin_offset *= 0.72
        if abs(self._wheel_spin_offset) < 0.015:
            self._wheel_spin_offset = 0.0
            self._wheel_spin_timer.stop()
            if self._key_released_waiting_rest and self._nav_pending_commit:
                self._commit_selection()
        self.update()

    def _on_pointer_tick(self):
        self._pointer_anim_tick += 1
        diff = self._pointer_rest_x_ratio - self._pointer_current_x_ratio
        if abs(diff) > 0.0005:
            self._pointer_current_x_ratio += diff * 0.20
        else:
            self._pointer_current_x_ratio = self._pointer_rest_x_ratio
        if self._pix_pointer:
            self.update()

    def _jump_letter(self, forward: bool):
        """Salta a la letra alfabética siguiente o anterior sin doble recarga de medios."""
        prev_idx = self.selected_index
        if forward:
            super().jump_to_next_letter()
        else:
            super().jump_to_prev_letter()
        self._nav_pending_commit = False
        self._nav_key_pressed = False
        self._key_released_waiting_rest = False
        self._wheel_spin_offset = 0.0
        self._commit_timer.stop()
        if self.selected_index != prev_idx:
            self._reset_wheel_fade()
            self._preload_around(self.selected_index)
            self.update()

    def jump_to_next_letter(self):
        self._jump_letter(True)

    def jump_to_prev_letter(self):
        self._jump_letter(False)

    # -------------------------------------------------------------------------
    # RENDERIZADO COMPARTIDO (RULETA UNIFICADA, PUNTERO Y BARRA INFERIOR)
    # -------------------------------------------------------------------------
    def _get_target_rect(self) -> QRect:
        """Retorna el rectángulo 16:9 centrado dentro del widget (letterbox/pillarbox)."""
        w, h = self.width(), self.height()
        target_ar = self.CANONICAL_W / float(self.CANONICAL_H)
        curr_ar = w / float(h) if h > 0 else target_ar
        if curr_ar > target_ar:
            sh = h
            sw = int(h * target_ar)
            return QRect((w - sw) // 2, 0, sw, sh)
        sw = w
        sh = int(w / target_ar)
        return QRect(0, (h - sh) // 2, sw, sh)

    def _draw_cached_scaled(
        self,
        painter: QPainter,
        cache_key: str,
        pix: QPixmap | None,
        x: int,
        y: int,
        w: int,
        h: int,
    ):
        """Dibuja un pixmap estático pre-escalado cacheando la textura por tamaño."""
        if not pix or pix.isNull() or w <= 0 or h <= 0:
            return
        entry = self._scaled_layer_cache.get(cache_key)
        spec = (id(pix), w, h)
        if entry is None or entry[0] != spec:
            scaled = pix.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self._scaled_layer_cache[cache_key] = (spec, scaled)
        else:
            scaled = entry[1]
        painter.drawPixmap(x, y, scaled)

    def _draw_wheel_shadow_layer(self, painter: QPainter, sr: QRect):
        """Dibuja la sombra trasera de la ruleta desde `gtc-common`."""
        if not self._pix_wheel_shadow:
            return
        if self.WHEEL_FADEOUT_DELAY_MS and self._wheel_alpha <= 2.0:
            return
        painter.save()
        if self.WHEEL_FADEOUT_DELAY_MS:
            painter.setOpacity(painter.opacity() * (self._wheel_alpha / 255.0))
        self._draw_cached_scaled(
            painter, "wheel_shadow", self._pix_wheel_shadow, sr.x(), sr.y(), sr.width(), sr.height()
        )
        painter.restore()

    def _draw_wheel_conveyor(self, painter: QPainter, sr: QRect):
        """Ruleta curva unificada de 14 nodos interpolados a 60 FPS (Reglas 9 y 10)."""
        n_games = len(self.games)
        if n_games == 0:
            return
        fade_factor = (self._wheel_alpha / 255.0) if self.WHEEL_FADEOUT_DELAY_MS else 1.0
        if fade_factor <= 0.01:
            return

        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        outer_op = max(0.0, min(1.0, float(painter.opacity()))) * fade_factor
        draw_offsets = (-6, 6, -5, 5, -4, 4, -3, 3, -2, 2, -1, 1, 0)

        for offset in draw_offsets:
            game = self.games[(self.selected_index + offset) % n_games]
            pos = (7.0 - offset) - self._wheel_spin_offset
            if pos < 0.0 or pos >= 13.0:
                continue

            i0 = int(math.floor(pos))
            i1 = min(i0 + 1, 13)
            p = pos - i0

            rx = self.CONVEYOR_X[i0] + p * (self.CONVEYOR_X[i1] - self.CONVEYOR_X[i0])
            ry = self.CONVEYOR_Y[i0] + p * (self.CONVEYOR_Y[i1] - self.CONVEYOR_Y[i0])
            rw = self.CONVEYOR_W[i0] + p * (self.CONVEYOR_W[i1] - self.CONVEYOR_W[i0])
            rh = self.CONVEYOR_H[i0] + p * (self.CONVEYOR_H[i1] - self.CONVEYOR_H[i0])
            angle = self.CONVEYOR_R[i0] + p * (self.CONVEYOR_R[i1] - self.CONVEYOR_R[i0])
            alpha = int(self.CONVEYOR_A[i0] + p * (self.CONVEYOR_A[i1] - self.CONVEYOR_A[i0]))
            if alpha <= 0:
                continue

            is_selected = abs(pos - 7.0) < 0.5
            item_w = int(sw * rw)
            item_h = int(sh * rh)
            item_cx = sx + int(sw * rx) + item_w // 2
            item_cy = sy + int(sh * ry) + item_h // 2

            painter.save()
            try:
                painter.translate(item_cx, item_cy)
                if angle != 0:
                    painter.rotate(angle)
                painter.setOpacity(outer_op * min(1.0, max(0.0, alpha / 255.0)))

                wheel_pix = self._get_game_wheel_pixmap(game)
                if wheel_pix and not wheel_pix.isNull():
                    pw, ph = wheel_pix.width(), wheel_pix.height()
                    max_w = max(1, item_w - 12)
                    max_h = max(1, item_h - 8)
                    s = min(max_w / pw, max_h / ph) if pw > 0 and ph > 0 else 1.0
                    dw = max(1, int(pw * s))
                    dh = max(1, int(ph * s))
                    painter.drawPixmap(QRect(-dw // 2, -dh // 2, dw, dh), wheel_pix)
                else:
                    rect = QRect(-item_w // 2, -item_h // 2, item_w, item_h)
                    card_path = QPainterPath()
                    card_path.addRoundedRect(rect, 8, 8)
                    bg_col = QColor(*(self.WHEEL_CARD_SELECTED_BG if is_selected else self.WHEEL_CARD_BG))
                    border_col = QColor(*(self.WHEEL_CARD_SELECTED_BORDER if is_selected else self.WHEEL_CARD_BORDER))
                    painter.fillPath(card_path, bg_col)
                    painter.setPen(QPen(border_col, 2 if is_selected else 1))
                    painter.drawPath(card_path)

                    title = game.get("title") or "Juego"
                    painter.setPen(QColor(255, 255, 255))
                    f_size = max(11, int(item_h * 0.30))
                    painter.setFont(QFont(self._font_main, f_size, QFont.Bold))
                    painter.drawText(rect.adjusted(8, 4, -8, -4), Qt.AlignCenter | Qt.TextWordWrap, title)
            finally:
                painter.restore()

    def _draw_pointer(self, painter: QPainter, sr: QRect):
        """Dibuja el puntero selector alineado al slot central de la ruleta."""
        if not self._pix_pointer or not self.games:
            return
        fade_factor = (self._wheel_alpha / 255.0) if self.WHEEL_FADEOUT_DELAY_MS else 1.0
        if fade_factor <= 0.01:
            return
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        ptr_size = int(sh * 0.24)
        slot_center_y_ratio = self.CONVEYOR_Y[7] + (self.CONVEYOR_H[7] / 2.0)
        ptr_y = sy + int(sh * slot_center_y_ratio) - (ptr_size // 2)

        visible_w = int(ptr_size * 0.56)
        edge_margin = max(4, int(sw * 0.003))
        base_x = sx + sw - edge_margin - visible_w
        pulse_offset = int(sw * (self._pointer_rest_x_ratio - self._pointer_current_x_ratio))
        idle_osc = int(sw * (math.sin(self._pointer_anim_tick * (8.0 / 60.0)) * 0.009375))
        ptr_x = base_x - pulse_offset + idle_osc

        painter.save()
        painter.setOpacity(painter.opacity() * fade_factor)
        painter.drawPixmap(ptr_x, ptr_y, ptr_size, ptr_size, self._pix_pointer)
        painter.restore()

    def _draw_bottom_bar(self, painter: QPainter, sr: QRect):
        """Dibuja la barra inferior de metadatos respetando `_skip_footer_bg` para GPU/Studio."""
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        bar_h = max(32, int(round(sh * float(self.BOTTOM_BAR_H_RATIO))))
        bar_y = sy + sh - bar_h

        if not getattr(self, "_skip_footer_bg", False):
            if self.BOTTOM_USE_FRAME and self._pix_frame:
                self._draw_cached_scaled(painter, "bottom_frame", self._pix_frame, sx, bar_y, sw, bar_h)
            else:
                painter.fillRect(QRect(sx, bar_y, sw, bar_h), QColor(*self.BOTTOM_BAR_BG_COLOR))

        if not self.games or not (0 <= self.selected_index < len(self.games)):
            return

        game = self.games[self.selected_index]
        title = game.get("title") or self.theme_name
        if self.BOTTOM_INCLUDE_YEAR_MANU:
            parts = [p for p in (game.get("title", ""), game.get("year", ""), game.get("manufacturer", "")) if p]
            if parts:
                title = " - ".join(parts)
        if self.BOTTOM_UPPERCASE_TITLE:
            title = title.upper()

        painter.save()
        painter.setPen(QColor(255, 255, 255))
        f_title = QFont(self._font_title, max(10, int(bar_h * 0.40)), QFont.Bold)
        if self.BOTTOM_LETTER_SPACING:
            f_title.setLetterSpacing(QFont.AbsoluteSpacing, float(self.BOTTOM_LETTER_SPACING))
        painter.setFont(f_title)
        title_rect = QRect(
            sx + int(sw * float(self.BOTTOM_TITLE_X_RATIO)),
            bar_y,
            int(sw * float(self.BOTTOM_TITLE_W_RATIO)),
            bar_h,
        )
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, title)

        prefix = f"{self.BOTTOM_COUNTER_PREFIX}: " if self.BOTTOM_COUNTER_PREFIX else ""
        counter_text = f"{prefix}{self.selected_index + 1} / {len(self.games)}"
        painter.setPen(QColor(*self.BOTTOM_COUNTER_COLOR))
        painter.setFont(QFont(self._font_main, max(9, int(bar_h * 0.35)), QFont.Bold))
        counter_rect = QRect(
            sx + int(sw * float(self.BOTTOM_COUNTER_X_RATIO)),
            bar_y,
            int(sw * float(self.BOTTOM_COUNTER_W_RATIO)),
            bar_h,
        )
        painter.drawText(counter_rect, Qt.AlignVCenter | Qt.AlignRight, counter_text)
        painter.restore()

    # -------------------------------------------------------------------------
    # EVENTOS DE TECLADO, RATÓN Y CICLO DE VIDA
    # -------------------------------------------------------------------------
    def keyPressEvent(self, event):
        """Maneja navegación y acciones respetando `matches_action` y Commit on Release."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return

        fast = event.isAutoRepeat()
        db = getattr(self, "db", None)
        if matches_action(event, ACTION_NAV_UP, db):
            self._nav_key_pressed = True
            self._navigate_steps(-1, fast_repeat=fast)
            event.accept()
        elif matches_action(event, ACTION_NAV_DOWN, db):
            self._nav_key_pressed = True
            self._navigate_steps(1, fast_repeat=fast)
            event.accept()
        elif matches_action(event, ACTION_SELECT, db):
            if fast:
                event.accept()
                return
            gid = self.get_selected_game_id()
            if gid and self._can_activate_game():
                self._play_select_sound()
                self.game_activated.emit(gid)
            event.accept()
        elif matches_action(event, ACTION_NAV_LETTER_BACK, db):
            if fast:
                event.accept()
                return
            self.jump_to_prev_letter()
            event.accept()
        elif matches_action(event, ACTION_NAV_LETTER_FWD, db) or matches_action(event, ACTION_NAV_LETTER, db):
            if fast:
                event.accept()
                return
            self.jump_to_next_letter()
            event.accept()
        elif matches_action(event, ACTION_NAV_STEP5_BACK, db) or matches_action(event, ACTION_PAGE_UP, db):
            self._nav_key_pressed = True
            self._navigate_steps(-5, fast_repeat=fast)
            event.accept()
        elif (
            matches_action(event, ACTION_NAV_STEP5_FWD, db)
            or matches_action(event, ACTION_NAV_STEP5, db)
            or matches_action(event, ACTION_PAGE_DOWN, db)
        ):
            self._nav_key_pressed = True
            self._navigate_steps(5, fast_repeat=fast)
            event.accept()
        elif matches_action(event, ACTION_NAV_BACK, db):
            self.nav_back_requested.emit()
            event.accept()
        elif matches_action(event, ACTION_MUTE, db):
            self.set_media_muted(not self._media_muted)
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Confirma la selección pendiente únicamente al soltar la tecla (Regla 5)."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if not event.isAutoRepeat():
            self._nav_key_pressed = False
            if self._nav_pending_commit:
                if abs(self._wheel_spin_offset) < 0.05:
                    self._commit_selection()
                else:
                    self._key_released_waiting_rest = True
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        """Guarda posición de inicio sin alterar ruleta ni selección hasta el release."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        self.setFocus()
        if event.button() == Qt.LeftButton:
            self._mouse_pressed_pos = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def _hit_test_wheel_offset(self, mx: float, my: float) -> int | None:
        """Retorna el offset de slot bajo `(mx, my)` dentro de la ruleta curva."""
        sr = self._get_target_rect()
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        for offset in range(-6, 7):
            pos_idx = (7.0 - offset) - self._wheel_spin_offset
            if 0.0 <= pos_idx < 13.0:
                i0 = int(math.floor(pos_idx))
                i1 = min(i0 + 1, 13)
                p = pos_idx - i0
                rx = self.CONVEYOR_X[i0] + p * (self.CONVEYOR_X[i1] - self.CONVEYOR_X[i0])
                ry = self.CONVEYOR_Y[i0] + p * (self.CONVEYOR_Y[i1] - self.CONVEYOR_Y[i0])
                rw = self.CONVEYOR_W[i0] + p * (self.CONVEYOR_W[i1] - self.CONVEYOR_W[i0])
                rh = self.CONVEYOR_H[i0] + p * (self.CONVEYOR_H[i1] - self.CONVEYOR_H[i0])
                hit_rect = QRect(sx + int(sw * rx), sy + int(sh * ry), int(sw * rw), int(sh * rh))
                if hit_rect.contains(int(mx), int(my)):
                    return offset
        return None

    def mouseReleaseEvent(self, event):
        """Ejecuta navegación o activación en la ruleta exclusivamente al soltar clic."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._mouse_pressed_pos is not None:
            pos = self._mouse_pressed_pos
            self._mouse_pressed_pos = None
            if self.games:
                dy = event.position().y() - pos.y()
                if abs(dy) >= 25:
                    # Arrastre hacia abajo avanza (+1), hacia arriba retrocede (-1) (Regla 10)
                    self._navigate_steps(1 if dy > 0 else -1)
                    self._commit_selection()
                    event.accept()
                    return
                hit_off = self._hit_test_wheel_offset(pos.x(), pos.y())
                if hit_off is not None:
                    n_games = len(self.games)
                    target_idx = (self.selected_index + hit_off) % n_games
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
        super().mouseReleaseEvent(event)
        event.accept()

    def wheelEvent(self, event):
        """Rueda abajo avanza al siguiente (+1), rueda arriba retrocede (-1) (Regla 10)."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._navigate_steps(-1)
        elif delta < 0:
            self._navigate_steps(1)
        event.accept()

    def _pause_ambient_timers(self):
        if self._pointer_anim_timer.isActive():
            self._pointer_anim_timer.stop()

    def _resume_ambient_timers(self):
        if self._pix_pointer and not self._pointer_anim_timer.isActive():
            self._pointer_anim_timer.start(16)

    def hideEvent(self, event):
        self._pause_ambient_timers()
        self.pause_media()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._resume_ambient_timers()
        self.resume_media()

    def clear(self):
        self._wheel_spin_offset = 0.0
        if self._wheel_spin_timer.isActive():
            self._wheel_spin_timer.stop()
        self.stop_media()
        super().clear()
        self._wheel_pixmaps.clear()
        if self._wheel_worker:
            self._wheel_worker.clear()

    def closeEvent(self, event):
        self.stop_media()
        self._pause_ambient_timers()
        if self._wheel_worker:
            self._wheel_worker.stop()
            self._wheel_worker.wait(1000)
        if event is not None:
            super().closeEvent(event)


class ConsoleThemeLayout(CommonThemeLayout):
    """Base declarativa para los layouts de consola con CRT, arte físico, boxart y ruleta."""

    DEFAULT_LAYER_ORDER = (
        "bg_image",
        "video_snap",
        "scanlines_crt",
        "scratches",
        "tv_bezel",
        "avatar",
        "logo",
        "console",
        "cartart",
        "console_cover",
        "joystick",
        "boxart",
        "wheel_shadow",
        "wheel_list",
        "pointer",
        "footer_frame",
    )
    LAYER_ORDER = DEFAULT_LAYER_ORDER

    # Recursos propios locales del layout (Regla 8)
    BKG_IMAGE: str | Path | None = None
    TV_IMAGE: str | Path | None = None
    CONSOLE_IMAGE: str | Path | None = None
    CONSOLE_COVER_IMAGE: str | Path | None = None
    JOYSTICK_IMAGE: str | Path | None = None
    AVATAR_IMAGE: str | Path | None = None
    LOGO_IMAGE: str | Path | None = None
    CARTART_IMAGE: str | Path | None = None
    DISCART_IMAGE: str | Path | None = None
    BOXART_IMAGE: str | Path | None = None

    # Geometría CRT / video y capas
    TV_RECT = (0.044, 0.240, 0.315, 0.425)
    SCANLINES_AUTO_LOAD = False
    SCANLINES_OPACITY = 0.40
    SCRATCHES_OPACITY = 0.40

    # Cartucho / disco físico
    CART_RECT: tuple[float, float, float, float] = (0.428, 0.540, 0.121, 0.250)
    DISC_RECT: tuple[float, float, float, float] | None = None
    IS_CD = False
    CART_START_X: float | None = None
    CART_END_X: float | None = None
    CART_START_Y: float | None = None
    CART_END_Y: float | None = None
    DISC_END_Y: float | None = None
    CART_DURATION = 700
    DISC_FADE_ON_ENTER = True
    CD_SPIN_SPEED = 1.152

    # Carátula (Boxart)
    BOXART_X = 0.015
    BOXART_Y = 0.530
    BOXART_W = 0.240
    BOXART_H = 0.380
    BOXART_ANCHOR = "bottom"
    BOXART_BOTTOM_Y = 0.928
    BOXART_START_X: float | None = None
    BOXART_END_X: float | None = None
    BOXART_START_Y: float | None = None
    BOXART_END_Y: float | None = None
    BOXART_SLIDE_OFFSET_X: float | None = None
    BOXART_DURATION = 400
    BOXART_PLACEHOLDER = True

    # Avatar, consola y logotipo
    AVATAR_SCALE = 1.0
    AVATAR_X = 0.0
    AVATAR_Y = 0.0
    AVATAR_Y_ADJUST = 0
    CONSOLE_SCALE = 1.0
    LOGO_SCALE = 1.0

    def _init_extra_resources(self):
        """Carga sprites de consola y configura temporizadores de cinemática."""
        self._current_box_pixmap: QPixmap | None = None
        self._current_cart_pixmap: QPixmap | None = None
        self._current_disc_pixmap: QPixmap | None = None
        self._pending_box_file: str | None = None
        self._pending_cart_file: str | None = None
        self._pending_disc_file: str | None = None

        self._pix_bkg = self._load_pixmap(self._resolve_existing_path(self.BKG_IMAGE))
        self._pix_tv = self._load_pixmap(self._resolve_existing_path(self.TV_IMAGE))
        self._pix_console = self._load_pixmap(self._resolve_existing_path(self.CONSOLE_IMAGE))
        self._pix_console_cover = self._load_pixmap(self._resolve_existing_path(self.CONSOLE_COVER_IMAGE))
        self._pix_joystick = self._load_pixmap(self._resolve_existing_path(self.JOYSTICK_IMAGE))
        self._pix_avatar = self._load_pixmap(self._resolve_existing_path(self.AVATAR_IMAGE))
        self._pix_logo = self._load_pixmap(self._resolve_existing_path(self.LOGO_IMAGE))

        disc_path = self._resolve_existing_path(self.DISCART_IMAGE)
        cart_path = self._resolve_existing_path(self.CARTART_IMAGE, self.DISCART_IMAGE)
        self._pix_discart_frame = self._load_pixmap(disc_path or (cart_path if self.IS_CD else None))
        self._pix_cartart_frame = self._load_pixmap(cart_path) if not self.IS_CD else self._pix_discart_frame
        self._pix_boxart_frame = self._load_pixmap(self._resolve_existing_path(self.BOXART_IMAGE))

        # Avatar sinusoidal
        self._avatar_anim_time = 0.0
        self._avatar_offset_x = 0.0
        self._avatar_offset_y = 0.0
        self._avatar_bounce_timer = QTimer(self)
        self._avatar_bounce_timer.timeout.connect(self._on_avatar_bounce_tick)
        if self._pix_avatar:
            self._avatar_bounce_timer.start(20)

        # Métricas de cartucho / disco sincronizadas con `runtime_hook.py`
        geom = self._get_cart_rect()
        self._cart_end_x_ratio = float(self.CART_END_X if self.CART_END_X is not None else geom[0])
        self._cart_start_x_ratio = float(self.CART_START_X if self.CART_START_X is not None else self._cart_end_x_ratio)
        default_end_y = self.DISC_END_Y if (self.IS_CD and self.DISC_END_Y is not None) else (
            self.CART_END_Y if self.CART_END_Y is not None else geom[1]
        )
        self._cart_end_y_ratio = float(default_end_y)
        self._cart_start_y_ratio = float(
            self.CART_START_Y if self.CART_START_Y is not None else (1.15 if self.IS_CD else -0.45)
        )
        self._cart_current_x_ratio = self._cart_end_x_ratio
        self._cart_current_y_ratio = self._cart_end_y_ratio
        self._disc_end_x_ratio = self._cart_end_x_ratio
        self._disc_end_y_ratio = self._cart_end_y_ratio
        self._disc_current_y_ratio = self._cart_end_y_ratio

        self._cart_anim_elapsed = 0
        self._cart_anim_duration = int(self.CART_DURATION)
        self._cart_anim_timer = QTimer(self)
        self._cart_anim_timer.timeout.connect(self._on_cart_anim_tick)
        self._disc_anim_timer = self._cart_anim_timer
        self._disc_anim_elapsed = 0
        self._disc_anim_duration = self._cart_anim_duration

        self._cd_rotation_angle = 0.0
        self._cd_spin_timer = QTimer(self)
        self._cd_spin_timer.timeout.connect(self._on_cd_spin_tick)
        if self.IS_CD:
            self._cd_spin_timer.start(16)

        # Logo elástico
        self._logo_anim_elapsed = 0
        self._logo_anim_duration = 1200
        self._logo_current_y_offset_ratio = 0.0
        self._logo_anim_timer = QTimer(self)
        self._logo_anim_timer.timeout.connect(self._on_logo_anim_tick)

        # Boxart deslizante / fade
        self._boxart_anim_elapsed = 0
        self._boxart_anim_duration = int(self.BOXART_DURATION)
        default_y = self.BOXART_BOTTOM_Y if self.BOXART_ANCHOR == "bottom" else self.BOXART_Y
        self._boxart_end_x_ratio = float(self.BOXART_END_X if self.BOXART_END_X is not None else self.BOXART_X)
        self._boxart_start_x_ratio = float(self.BOXART_START_X if self.BOXART_START_X is not None else self._boxart_end_x_ratio)
        self._boxart_end_y_ratio = float(self.BOXART_END_Y if self.BOXART_END_Y is not None else default_y)
        self._boxart_start_y_ratio = float(self.BOXART_START_Y if self.BOXART_START_Y is not None else self._boxart_end_y_ratio)
        self._boxart_current_x_ratio = self._boxart_end_x_ratio
        self._boxart_current_y_ratio = self._boxart_end_y_ratio
        self._boxart_current_x_offset_ratio = 0.0
        self._boxart_alpha = 1.0
        self._boxart_anim_timer = QTimer(self)
        self._boxart_anim_timer.timeout.connect(self._on_boxart_anim_tick)

        self._paint_dispatch: dict[str, Callable[[QPainter, QRect], None]] = {
            "bg_image": self._layer_bg,
            "video_snap": self._layer_video,
            "scanlines_crt": self._layer_scanlines,
            "scratches": self._layer_scratches,
            "tv_bezel": self._layer_tv,
            "avatar": self._draw_avatar,
            "logo": self._draw_logo,
            "console": self._layer_console,
            "cartart": self._draw_cart_or_disc,
            "console_cover": self._layer_console_cover,
            "joystick": self._layer_joystick,
            "boxart": self._draw_boxart,
            "wheel_shadow": self._draw_wheel_shadow_layer,
            "wheel_list": self._draw_wheel_conveyor,
            "pointer": self._draw_pointer,
            "footer_frame": self._draw_bottom_bar,
        }

    def _get_cart_rect(self) -> tuple[float, float, float, float]:
        if self.IS_CD and self.DISC_RECT is not None:
            return self.DISC_RECT
        return self.CART_RECT or self.DISC_RECT or (0.428, 0.540, 0.121, 0.250)

    def _get_tv_rect(self, sr: QRect) -> QRect:
        vx, vy, vw, vh = self.TV_RECT
        return QRect(
            sr.x() + int(sr.width() * vx),
            sr.y() + int(sr.height() * vy),
            int(sr.width() * vw),
            int(sr.height() * vh),
        )

    # -------------------------------------------------------------------------
    # CARGA DE ARTES DEL JUEGO Y ANIMACIONES
    # -------------------------------------------------------------------------
    def _on_games_loaded(self):
        self._start_logo_animation()

    def _clear_selected_media(self):
        self._current_box_pixmap = None
        self._current_cart_pixmap = None
        self._current_disc_pixmap = None
        self._pending_box_file = None
        self._pending_cart_file = None
        self._pending_disc_file = None
        super()._clear_selected_media()

    def select_game_by_id(self, game_id: int):
        prev_idx = self.selected_index
        super().select_game_by_id(game_id)
        if self.selected_index != prev_idx:
            self._start_cart_animation()
            self._start_boxart_animation()

    def _preload_adjacent_art(self, center_idx: int):
        n = len(self.games)
        if n <= 1:
            return
        for off in (-1, 1):
            gm = self.games[(center_idx + off) % n]
            gmedia = resolve_game_media(gm)
            for key in ("boxart", "cartart", "discart"):
                path = gmedia.get(key)
                if path and path not in self._art_pix_cache and os.path.isfile(path):
                    p = QPixmap(path)
                    if not p.isNull():
                        self._art_pix_cache[path] = p

    def _update_current_selection(self):
        if not self.games or not (0 <= self.selected_index < len(self.games)):
            self._clear_selected_media()
            return
        super()._update_current_selection()
        game = self.games[self.selected_index]
        self.current_media = resolve_game_media(game)

        box_file = self.current_media.get("boxart") or game.get("cover_path") or game.get("boxart_path")
        self._pending_box_file = box_file if (box_file and os.path.isfile(box_file)) else None

        if self.IS_CD:
            phys_file = (
                self.current_media.get("discart")
                or self.current_media.get("cartart")
                or game.get("discart_path")
                or game.get("cartart_path")
            )
            self._pending_disc_file = phys_file if (phys_file and os.path.isfile(phys_file)) else None
            self._pending_cart_file = self._pending_disc_file
        else:
            phys_file = (
                self.current_media.get("cartart")
                or self.current_media.get("discart")
                or game.get("cartart_path")
                or game.get("discart_path")
            )
            self._pending_cart_file = phys_file if (phys_file and os.path.isfile(phys_file)) else None
            self._pending_disc_file = None

        self._load_pending_art()
        self._start_cart_animation()
        self._start_boxart_animation()

        snap_video = self.current_media.get("snap")
        video_to_play = None
        if snap_video and os.path.isfile(snap_video):
            video_to_play = snap_video
        elif self._static_video_path and os.path.isfile(self._static_video_path):
            video_to_play = self._static_video_path
        self._queue_video_playback(video_to_play)

    def _load_pending_art(self):
        """Carga en RAM la carátula y cartucho/disco del juego activo."""
        if len(self._art_pix_cache) > 100:
            self._art_pix_cache.clear()

        b_file = self._pending_box_file
        if b_file and os.path.isfile(b_file):
            if b_file not in self._art_pix_cache:
                p = QPixmap(b_file)
                self._art_pix_cache[b_file] = p if not p.isNull() else None
            self._current_box_pixmap = self._art_pix_cache.get(b_file)
        elif self.BOXART_PLACEHOLDER:
            game = self.games[self.selected_index] if (self.games and 0 <= self.selected_index < len(self.games)) else {}
            title = game.get("title") or game.get("rom_name") or ""
            pkey = f"__placeholder_{title}"
            if pkey not in self._art_pix_cache:
                self._art_pix_cache[pkey] = load_cover(None, title, QSize(400, 400))
            self._current_box_pixmap = self._art_pix_cache.get(pkey)
        else:
            self._current_box_pixmap = None

        c_file = self._pending_disc_file if self.IS_CD else self._pending_cart_file
        if c_file and os.path.isfile(c_file):
            if c_file not in self._art_pix_cache:
                p = QPixmap(c_file)
                self._art_pix_cache[c_file] = p if not p.isNull() else None
            loaded = self._art_pix_cache.get(c_file)
            self._current_cart_pixmap = loaded
            self._current_disc_pixmap = loaded if self.IS_CD else None
        else:
            self._current_cart_pixmap = None
            self._current_disc_pixmap = None

    def _start_cart_animation(self):
        self._cart_anim_elapsed = 0
        self._disc_anim_elapsed = 0
        self._cart_current_x_ratio = self._cart_start_x_ratio
        self._cart_current_y_ratio = self._cart_start_y_ratio
        self._disc_current_y_ratio = self._cart_start_y_ratio
        self._cart_anim_timer.start(16)

    def _on_cart_anim_tick(self):
        self._cart_anim_elapsed += 16
        self._disc_anim_elapsed = self._cart_anim_elapsed
        t = min(self._cart_anim_elapsed / max(1, self._cart_anim_duration), 1.0)
        ease = 1.0 - (1.0 - t) ** 3
        self._cart_current_x_ratio = (
            self._cart_start_x_ratio + (self._cart_end_x_ratio - self._cart_start_x_ratio) * ease
        )
        cur_y = self._cart_start_y_ratio + (self._cart_end_y_ratio - self._cart_start_y_ratio) * ease
        self._cart_current_y_ratio = cur_y
        self._disc_current_y_ratio = cur_y
        if t >= 1.0:
            self._cart_anim_timer.stop()
            self._cart_current_x_ratio = self._cart_end_x_ratio
            self._cart_current_y_ratio = self._cart_end_y_ratio
            self._disc_current_y_ratio = self._cart_end_y_ratio
        self.update()

    def _on_cd_spin_tick(self):
        self._cd_rotation_angle = (self._cd_rotation_angle + float(self.CD_SPIN_SPEED)) % 360.0
        if self.games and self._disc_current_y_ratio <= 1.05:
            self.update()

    def _start_logo_animation(self):
        self._logo_anim_elapsed = 0
        self._logo_current_y_offset_ratio = -0.50
        if self._pix_logo:
            self._logo_anim_timer.start(16)

    def _on_logo_anim_tick(self):
        self._logo_anim_elapsed += 16
        t = min(self._logo_anim_elapsed / max(1, self._logo_anim_duration), 1.0)
        p = 0.3
        s = p / 4.0
        if t <= 0.0:
            ease = 0.0
        elif t >= 1.0:
            ease = 1.0
        else:
            ease = math.pow(2.0, -10.0 * t) * math.sin((t - s) * (2.0 * math.pi) / p) + 1.0
        self._logo_current_y_offset_ratio = -0.50 * (1.0 - ease)
        if t >= 1.0:
            self._logo_anim_timer.stop()
            self._logo_current_y_offset_ratio = 0.0
        self.update()

    def _start_boxart_animation(self):
        self._boxart_anim_elapsed = 0
        self._boxart_current_x_ratio = self._boxart_start_x_ratio
        self._boxart_current_y_ratio = self._boxart_start_y_ratio
        self._boxart_current_x_offset_ratio = float(self.BOXART_SLIDE_OFFSET_X or 0.0)
        self._boxart_alpha = 0.0
        self._boxart_anim_timer.start(16)

    def _on_boxart_anim_tick(self):
        self._boxart_anim_elapsed += 16
        t = min(self._boxart_anim_elapsed / max(1, self._boxart_anim_duration), 1.0)
        ease = 1.0 - (1.0 - t) ** 3
        self._boxart_current_x_ratio = (
            self._boxart_start_x_ratio + (self._boxart_end_x_ratio - self._boxart_start_x_ratio) * ease
        )
        self._boxart_current_y_ratio = (
            self._boxart_start_y_ratio + (self._boxart_end_y_ratio - self._boxart_start_y_ratio) * ease
        )
        if self.BOXART_SLIDE_OFFSET_X is not None:
            self._boxart_current_x_offset_ratio = float(self.BOXART_SLIDE_OFFSET_X) * (1.0 - ease)
        else:
            self._boxart_current_x_offset_ratio = 0.0
        self._boxart_alpha = min(1.0, max(0.0, ease * 1.35))
        if t >= 1.0:
            self._boxart_anim_timer.stop()
            self._boxart_current_x_ratio = self._boxart_end_x_ratio
            self._boxart_current_y_ratio = self._boxart_end_y_ratio
            self._boxart_current_x_offset_ratio = 0.0
            self._boxart_alpha = 1.0
        self.update()

    def _on_avatar_bounce_tick(self):
        self._avatar_anim_time += 0.04
        t = self._avatar_anim_time
        self._avatar_offset_x = math.sin(t * 0.9) * 8.0
        self._avatar_offset_y = (math.sin(t * 1.8) * 12.0) + (math.cos(t * 0.45) * 5.0)
        if self._pix_avatar:
            self.update()

    def _pause_ambient_timers(self):
        super()._pause_ambient_timers()
        for tmr in (self._avatar_bounce_timer, self._cd_spin_timer):
            if tmr.isActive():
                tmr.stop()

    def _resume_ambient_timers(self):
        super()._resume_ambient_timers()
        if self._pix_avatar and not self._avatar_bounce_timer.isActive():
            self._avatar_bounce_timer.start(20)
        if self.IS_CD and not self._cd_spin_timer.isActive():
            self._cd_spin_timer.start(16)

    def showEvent(self, event):
        super().showEvent(event)
        self._start_logo_animation()

    # -------------------------------------------------------------------------
    # RENDERIZADO DE CAPAS
    # -------------------------------------------------------------------------
    def _layer_bg(self, painter: QPainter, sr: QRect):
        self._draw_cached_scaled(painter, "bkg", self._pix_bkg, sr.x(), sr.y(), sr.width(), sr.height())

    def _layer_video(self, painter: QPainter, sr: QRect):
        tv_rect = self._get_tv_rect(sr)
        if self._current_video_image and not self._current_video_image.isNull():
            painter.drawImage(tv_rect, self._current_video_image)
        else:
            painter.fillRect(tv_rect, QColor(10, 10, 15))

    def _layer_scanlines(self, painter: QPainter, sr: QRect):
        if not self._pix_scanlines and getattr(self, "SCANLINES_AUTO_LOAD", False):
            self._pix_scanlines = self._load_pixmap(self._resolve_existing_path(self.SCANLINES_IMAGE))
        if not self._pix_scanlines:
            return
        tv_rect = self._get_tv_rect(sr)
        painter.save()
        painter.setOpacity(float(self.SCANLINES_OPACITY))
        painter.drawPixmap(tv_rect, self._pix_scanlines)
        painter.restore()

    def _layer_scratches(self, painter: QPainter, sr: QRect):
        if not self._pix_scratches:
            return
        tv_rect = self._get_tv_rect(sr)
        painter.save()
        painter.setOpacity(float(self.SCRATCHES_OPACITY))
        self._draw_cached_scaled(
            painter, "scratches", self._pix_scratches, tv_rect.x(), tv_rect.y(), tv_rect.width(), tv_rect.height()
        )
        painter.restore()

    def _layer_tv(self, painter: QPainter, sr: QRect):
        self._draw_cached_scaled(painter, "tv", self._pix_tv, sr.x(), sr.y(), sr.width(), sr.height())

    def _draw_console_layer(self, painter: QPainter, cache_key: str, pix: QPixmap | None, sr: QRect):
        if not pix:
            return
        scale = float(self.CONSOLE_SCALE)
        cw = int(sr.width() * scale)
        ch = int(sr.height() * scale)
        cx = sr.x()
        cy = sr.y() + (sr.height() - ch)
        self._draw_cached_scaled(painter, cache_key, pix, cx, cy, cw, ch)

    def _layer_console(self, painter: QPainter, sr: QRect):
        self._draw_console_layer(painter, "console", self._pix_console, sr)

    def _layer_console_cover(self, painter: QPainter, sr: QRect):
        self._draw_console_layer(painter, "console_cover", self._pix_console_cover, sr)

    def _layer_joystick(self, painter: QPainter, sr: QRect):
        self._draw_console_layer(painter, "joystick", self._pix_joystick, sr)

    def _draw_avatar(self, painter: QPainter, sr: QRect):
        avatar_pix = self._pix_avatar
        if not avatar_pix:
            return
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        scale = float(self.AVATAR_SCALE)
        rx = sw / float(self.CANONICAL_W)
        ry = sh / float(self.CANONICAL_H)
        anim_x = int(self._avatar_offset_x * rx)
        anim_y = int((self._avatar_offset_y + float(self.AVATAR_Y_ADJUST)) * ry)
        if avatar_pix.width() >= 1200:
            draw_x = sx + int(float(self.AVATAR_X) * sw) + anim_x
            draw_y = sy + int(float(self.AVATAR_Y) * sh) + anim_y
            painter.drawPixmap(draw_x, draw_y, int(sw * scale), int(sh * scale), avatar_pix)
        else:
            draw_x = sx + int((0.68 + float(self.AVATAR_X)) * sw) + anim_x
            draw_y = sy + int((0.08 + float(self.AVATAR_Y)) * sh) + anim_y
            painter.drawPixmap(draw_x, draw_y, int(0.25 * sw * scale), int(0.50 * sh * scale), avatar_pix)

    def _draw_logo(self, painter: QPainter, sr: QRect):
        if not self._pix_logo:
            return
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        scale = float(self.LOGO_SCALE)
        if self._pix_logo.width() >= 1200:
            logo_y = sy + int(sh * self._logo_current_y_offset_ratio)
            painter.drawPixmap(sx, logo_y, int(sw * scale), int(sh * scale), self._pix_logo)
        else:
            lx = sx + int(0.04 * sw)
            ly = sy + int((0.02 + self._logo_current_y_offset_ratio) * sh)
            painter.drawPixmap(lx, ly, int(0.35 * sw * scale), int(0.18 * sh * scale), self._pix_logo)

    def _draw_cart_or_disc(self, painter: QPainter, sr: QRect):
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        _, _, cw, ch = self._get_cart_rect()
        item_w = int(sw * cw)
        item_h = int(sh * ch)
        item_x = sx + int(sw * self._cart_current_x_ratio)
        item_y = sy + int(sh * self._cart_current_y_ratio)

        if self.IS_CD:
            has_pending = bool(self._pending_disc_file or self._pending_cart_file)
            pix = (self._current_disc_pixmap or self._current_cart_pixmap) if has_pending else (
                self._pix_discart_frame or self._pix_cartart_frame
            )
            if not pix or pix.isNull():
                return
            side = min(item_w, item_h)
            cx = item_x + item_w // 2
            cy = item_y + item_h // 2
            painter.save()
            if self.DISC_FADE_ON_ENTER and self._cart_anim_timer.isActive() and self._cart_anim_duration > 0:
                painter.setOpacity(min(1.0, max(0.0, self._cart_anim_elapsed / (self._cart_anim_duration * 0.6))))
            painter.translate(cx, cy)
            painter.rotate(self._cd_rotation_angle)
            painter.drawPixmap(QRect(-side // 2, -side // 2, side, side), pix)
            painter.restore()
            return

        pix = self._current_cart_pixmap if self._pending_cart_file else self._pix_cartart_frame
        if pix and not pix.isNull():
            pw, ph = pix.width(), pix.height()
            s = min(item_w / pw, item_h / ph) if pw > 0 and ph > 0 else 1.0
            dw = int(pw * s)
            dh = int(ph * s)
            draw_x = item_x + (item_w - dw) // 2
            draw_y = item_y + (item_h - dh) // 2
            painter.drawPixmap(QRect(draw_x, draw_y, dw, dh), pix)

    def _draw_boxart(self, painter: QPainter, sr: QRect):
        box_pix = self._current_box_pixmap if self._pending_box_file else (self._pix_boxart_frame or self._current_box_pixmap)
        if not box_pix or box_pix.isNull():
            return
        sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
        box_w = int(sw * float(self.BOXART_W))
        box_h = int(sh * float(self.BOXART_H))
        pw, ph = box_pix.width(), box_pix.height()
        s = min(box_w / pw, box_h / ph) if pw > 0 and ph > 0 else 1.0
        dw = int(pw * s)
        dh = int(ph * s)

        box_x = sx + int(sw * (self._boxart_current_x_ratio + self._boxart_current_x_offset_ratio))
        draw_x = box_x + (box_w - dw) // 2
        if self.BOXART_ANCHOR == "bottom":
            draw_y = (sy + int(sh * self._boxart_current_y_ratio)) - dh
        else:
            box_y = sy + int(sh * self._boxart_current_y_ratio)
            draw_y = box_y + (box_h - dh) // 2

        painter.save()
        painter.setOpacity(self._boxart_alpha)
        painter.drawPixmap(QRect(draw_x, draw_y, dw, dh), box_pix)
        painter.restore()

    def paintEvent(self, event):
        """Renderiza las capas declaradas en `LAYER_ORDER` dentro del marco 16:9."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        try:
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            sr = self._get_target_rect()
            for layer_id in self.LAYER_ORDER:
                fn = self._paint_dispatch.get(layer_id)
                if fn is not None:
                    fn(painter, sr)
        finally:
            painter.end()
