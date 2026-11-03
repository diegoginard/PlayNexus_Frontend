import os
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QUrl, QRect, QPoint, QTimer, QModelIndex, QEvent
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPixmap, QIcon, QBrush, QPen
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QFrame, QSplitter, QStyleOptionViewItem, QStyledItemDelegate,
    QStackedWidget, QStyle
)

from playnexus.ui.layouts.base import BaseLayout, WheelPreloadWorker
from playnexus.services.media import resolve_game_media, find_media_file, IMAGE_EXTS
from playnexus.ui.cover_utils import load_cover
from playnexus.services.controls import (
    matches_action, ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_SELECT, ACTION_MUTE, ACTION_NAV_BACK,
    ACTION_NAV_LETTER, ACTION_NAV_STEP5, ACTION_PAGE_UP, ACTION_PAGE_DOWN,
    ACTION_NAV_LETTER_FWD, ACTION_NAV_LETTER_BACK,
    ACTION_NAV_STEP5_FWD, ACTION_NAV_STEP5_BACK
)


class WheelItemDelegate(QStyledItemDelegate):
    """
    Delegado que dibuja cada elemento de la Rueda (Wheel).
    Muestra el logo transparente (.png) de Wheel del juego, o un banner estilizado si no existe logo.
    """
    def __init__(self, parent=None, wheel_worker=None):
        super().__init__(parent)
        self._wheel_worker = wheel_worker
        self._wheel_cache = {}  # game_id -> QPixmap or None
        self._scaled_cache = {} # (game_id, is_selected, max_w, max_h) -> QPixmap

    def invalidate_cache(self):
        self._wheel_cache.clear()
        self._scaled_cache.clear()

    def sizeHint(self, option, index):
        return QSize(260, 70)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.setRenderHint(QPainter.TextAntialiasing)

            rect = option.rect
            is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
            is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

            # Opacidad: el seleccionado 100% visible, los que están arriba y abajo con mayor transparencia
            opacity = 1.0 if is_selected else (0.75 if is_hover else 0.55)
            painter.setOpacity(opacity)

            game = index.data(Qt.UserRole + 10)
            if not game:
                return

            game_id = game.get("id", 0)
            title = game.get("title", "")

            # Coordenadas ajustadas para efecto de tarjeta en la rueda
            pad_x = 6 if is_selected else 16
            pad_y = 2 if is_selected else 5
            card_rect = QRect(rect.x() + pad_x, rect.y() + pad_y, rect.width() - pad_x * 2, rect.height() - pad_y * 2)

            # Fondo del ítem
            path = QPainterPath()
            path.addRoundedRect(card_rect.x(), card_rect.y(), card_rect.width(), card_rect.height(), 10, 10)

            if is_selected:
                bg_color = QColor("#2d225a")
                border_color = QColor("#8c7ae6")
                border_width = 2.0
            elif is_hover:
                bg_color = QColor("#1e2438")
                border_color = QColor("#48547a")
                border_width = 1.0
            else:
                bg_color = QColor(21, 24, 36, 180)
                border_color = QColor(38, 43, 60, 180)
                border_width = 1.0

            painter.fillPath(path, QBrush(bg_color))
            painter.setPen(QPen(border_color, border_width))
            painter.drawPath(path)

            # Obtener o encolar imagen de Wheel Logo sin bloquear jamás el hilo de la UI
            if game_id not in self._wheel_cache:
                if self._wheel_worker:
                    self._wheel_worker.queue_game(game, priority=True)
                self._wheel_cache[game_id] = None

            wheel_pix = self._wheel_cache.get(game_id)

            if wheel_pix and not wheel_pix.isNull():
                # Dibujar el logo wheel centrado manteniendo proporción (+20% si está seleccionado)
                if is_selected:
                    max_w = int((card_rect.width() - 16) * 1.20)
                    max_h = int((card_rect.height() - 8) * 1.20)
                else:
                    max_w = card_rect.width() - 24
                    max_h = card_rect.height() - 16

                cache_key = (game_id, is_selected, max_w, max_h)
                scaled = self._scaled_cache.get(cache_key)
                if not scaled or scaled.isNull():
                    scaled = wheel_pix.scaled(QSize(max_w, max_h), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    if len(self._scaled_cache) > 400:
                        self._scaled_cache.clear()
                    self._scaled_cache[cache_key] = scaled

                draw_x = card_rect.x() + (card_rect.width() - scaled.width()) // 2
                draw_y = card_rect.y() + (card_rect.height() - scaled.height()) // 2
                painter.drawPixmap(draw_x, draw_y, scaled)
            else:
                # Texto estilizado si no hay logo de wheel
                font = QFont("Segoe UI", 12 if is_selected else 10, QFont.Bold)
                painter.setFont(font)
                painter.setPen(QColor("#ffffff" if is_selected else "#b8c2d6"))
                text_rect = QRect(card_rect.x() + 12, card_rect.y(), card_rect.width() - 24, card_rect.height())
                painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, title)
        finally:
            painter.restore()


class WheelLayout(BaseLayout):
    """
    Layout Arcade Wheel con Video Snaps en vivo, Boxart y Wheel Logos.
    Estilo clásico de gabinetes arcade y frontends profesionales (Attract-Mode / BigBox).
    El reproductor de video se inicializa de forma diferida (lazy) para evitar crashes
    en Windows al mostrar QVideoWidget antes de que el event loop esté activo.
    """
    LAYOUT_NAME = "Wheel"
    LAYOUT_DESCRIPTION = "Modo Arcade con Rueda de Logos (Wheel), Video Snaps en vivo y Box Art"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.current_media = {}
        self._player_initialized = False  # Flag: media player aún no creado
        self.player = None
        self.audio_output = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(12)

        # -------------------------------------------------------------
        # PANEL IZQUIERDO: Video Snap, Box Art y Datos del Juego
        # -------------------------------------------------------------
        left_panel = QFrame()
        left_panel.setStyleSheet("""
            QFrame {
                background-color: #141722;
                border-radius: 12px;
                border: 1px solid #23283b;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        # 1. Contenedor de Video Snap — usa QStackedWidget para evitar crash con QVideoWidget vacío
        self.video_container = QFrame()
        self.video_container.setStyleSheet("""
            QFrame {
                background-color: #000000;
                border: 2px solid #363e59;
                border-radius: 10px;
            }
        """)
        self.video_container.setMinimumHeight(240)
        video_box_layout = QVBoxLayout(self.video_container)
        video_box_layout.setContentsMargins(0, 0, 0, 0)

        # Stack: página 0 = placeholder, página 1 = video widget (se agrega lazy)
        self._video_stack = QStackedWidget()
        video_box_layout.addWidget(self._video_stack)

        # Placeholder inicial (siempre seguro de mostrar)
        self.no_video_label = QLabel("🎬 Sin video snap disponible")
        self.no_video_label.setAlignment(Qt.AlignCenter)
        self.no_video_label.setStyleSheet("color: #616e87; font-size: 11pt; background: #0c0e14;")
        self._video_stack.addWidget(self.no_video_label)  # índice 0

        # video_widget se agrega en _init_player() una vez la ventana es visible
        self.video_widget = None

        left_layout.addWidget(self.video_container, 3)

        # Barra de control de audio del video snap
        video_bar = QHBoxLayout()
        self.mute_btn = QPushButton("🔊 Silenciar video")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFocusPolicy(Qt.NoFocus)
        self.mute_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e2333;
                border: 1px solid #2d344d;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 9pt;
                color: #a2b0cb;
            }
            QPushButton:hover { background-color: #293046; color: #ffffff; }
            QPushButton:checked { background-color: #44243b; color: #fca5a5; border-color: #632d4b; }
        """)
        self.mute_btn.clicked.connect(self._toggle_mute)
        video_bar.addWidget(self.mute_btn)
        video_bar.addStretch()
        left_layout.addLayout(video_bar)

        # 2. Fila inferior: Boxart a la izquierda, detalles a la derecha
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        # Imagen de Box Art
        self.boxart_label = QLabel()
        self.boxart_label.setFixedSize(140, 160)
        self.boxart_label.setAlignment(Qt.AlignCenter)
        self.boxart_label.setStyleSheet("""
            QLabel {
                background-color: #1a1e2c;
                border: 1px solid #2d344d;
                border-radius: 8px;
            }
        """)
        bottom_row.addWidget(self.boxart_label, 0, Qt.AlignTop)

        # Datos técnicos y Wheel Logo grande
        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)

        self.wheel_logo_label = QLabel()
        self.wheel_logo_label.setFixedHeight(50)
        self.wheel_logo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        info_layout.addWidget(self.wheel_logo_label)

        self.title_label = QLabel("Seleccioná un juego")
        self.title_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.title_label.setStyleSheet("color: #f1f3f9;")
        self.title_label.setWordWrap(True)
        info_layout.addWidget(self.title_label)

        self.meta_label = QLabel("—")
        self.meta_label.setStyleSheet("color: #8c9bb3; font-size: 9pt;")
        info_layout.addWidget(self.meta_label)
        info_layout.addStretch()
        bottom_row.addLayout(info_layout, 1)

        left_layout.addLayout(bottom_row, 2)
        main_layout.addWidget(left_panel, 6)

        # -------------------------------------------------------------
        # PANEL DERECHO: The Wheel (Rueda de Logos y Juegos)
        # -------------------------------------------------------------
        right_panel = QFrame()
        right_panel.setStyleSheet("""
            QFrame {
                background-color: #12151f;
                border-radius: 12px;
                border: 1px solid #23283b;
            }
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 12, 8, 8)
        right_layout.setSpacing(8)

        wheel_header = QLabel("RUEDA DE JUEGOS")
        wheel_header.setStyleSheet("font-weight: bold; color: #8e9bb0; letter-spacing: 1.5px; font-size: 9pt; padding-left: 6px;")
        right_layout.addWidget(wheel_header)

        self.wheel_list = QListWidget()
        self.wheel_list.setFocusPolicy(Qt.StrongFocus)
        self.wheel_list.installEventFilter(self)
        self.wheel_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                border: none;
                background: transparent;
            }
        """)
        self.wheel_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.wheel_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Worker en segundo plano para pre-carga asíncrona de logotipos de rueda
        self._wheel_worker = WheelPreloadWorker(self, max_w=360, max_h=120)
        self._wheel_worker.wheel_loaded.connect(self._on_wheel_image_loaded)
        self._wheel_worker.start()

        self.delegate = WheelItemDelegate(self, wheel_worker=self._wheel_worker)
        self.wheel_list.setItemDelegate(self.delegate)

        self.wheel_list.currentItemChanged.connect(self._on_wheel_item_changed)
        self.wheel_list.itemDoubleClicked.connect(self._on_wheel_double_clicked)
        self.wheel_list.itemActivated.connect(self._on_wheel_double_clicked)
        self.wheel_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.wheel_list.customContextMenuRequested.connect(self._on_context_menu)

        right_layout.addWidget(self.wheel_list, 1)
        main_layout.addWidget(right_panel, 4)

        # Timer para debounce de video al desplazarse rápidamente por la rueda
        self._want_video_playing = False
        self.video_timer = QTimer(self)
        self.video_timer.setSingleShot(True)
        self.video_timer.setInterval(160)
        self.video_timer.timeout.connect(self._start_video)

        # Timer para diferir la carga en disco de artes pesadas (boxart/video) durante el scroll rápido
        self._art_timer = QTimer(self)
        self._art_timer.setSingleShot(True)
        self._art_timer.setInterval(120)
        self._art_timer.timeout.connect(self._load_pending_art)
        self._pending_art_game = None

        self._video_watchdog_timer = QTimer(self)
        self._video_watchdog_timer.setSingleShot(True)
        self._video_watchdog_timer.setInterval(1200)
        self._video_watchdog_timer.timeout.connect(self._on_video_watchdog)

        # Timer para inicialización diferida del reproductor de video
        self._init_timer = QTimer(self)
        self._init_timer.setSingleShot(True)
        self._init_timer.setInterval(500)  # 500ms después de mostrar la ventana
        self._init_timer.timeout.connect(self._init_player)

    def showEvent(self, event):
        """Dispara la inicialización del reproductor de video una vez que la ventana es visible."""
        super().showEvent(event)
        if not self._player_initialized:
            self._init_timer.start()

    def _init_player(self):
        """Inicializa QMediaPlayer y QVideoWidget de forma diferida (segura en Windows)."""
        if self._player_initialized:
            return
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget

            self.video_widget = QVideoWidget()
            self.video_widget.setFocusPolicy(Qt.NoFocus)
            self.video_widget.setStyleSheet("background-color: #000000;")
            self._video_stack.addWidget(self.video_widget)  # índice 1

            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.audio_output.setVolume(0.35)
            self.player.setAudioOutput(self.audio_output)
            self.player.setVideoOutput(self.video_widget)
            self.player.setLoops(QMediaPlayer.Infinite)
            self.player.mediaStatusChanged.connect(self._on_media_status_changed)
            self.player.errorOccurred.connect(self._on_player_error)

            self._player_initialized = True

            # Si ya hay un juego seleccionado, reproducir su video ahora
            if self.current_media.get("video"):
                self._start_video()

        except Exception as e:
            # Si falla (driver incompatible), seguimos sin video — no crashea la app
            print(f"[WheelLayout] No se pudo inicializar el reproductor de video: {e}")
            self._player_initialized = True  # Marcar como "intentado" para no reintentar

    def _on_media_status_changed(self, status):
        if not self.player:
            return
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferingMedia, QMediaPlayer.BufferedMedia):
                if self._want_video_playing and self.isVisible():
                    if self.audio_output:
                        is_m = getattr(self, "_media_muted", False)
                        self.audio_output.setMuted(is_m)
                        self.audio_output.setVolume(0.0 if is_m else 0.35)
                    if self.player.playbackState() != QMediaPlayer.PlayingState:
                        self.player.play()
                else:
                    if self.audio_output:
                        self.audio_output.setMuted(True)
                        self.audio_output.setVolume(0.0)
                    if status == QMediaPlayer.BufferedMedia:
                        self.player.pause()
            elif status == QMediaPlayer.EndOfMedia:
                if self._want_video_playing and self.isVisible():
                    self.player.setPosition(0)
                    self.player.play()
        except Exception:
            pass

    def _on_video_watchdog(self):
        if not self._want_video_playing or not self.player or not self.isVisible():
            return
        video_file = self.current_media.get("video")
        if video_file and os.path.isfile(video_file):
            try:
                from PySide6.QtMultimedia import QMediaPlayer
                if self.player.mediaStatus() in (QMediaPlayer.LoadingMedia, QMediaPlayer.BufferingMedia) and self.player.playbackState() == QMediaPlayer.PlayingState:
                    return
                src_url = QUrl.fromLocalFile(video_file)
                if self.player.source() != src_url:
                    self.player.setSource(src_url)
                if self.player.playbackState() != QMediaPlayer.PlayingState:
                    self.player.play()
            except Exception:
                pass

    def _on_player_error(self, error, error_string=""):
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self._video_stack.setCurrentIndex(0)

    def set_games(self, games: list):
        self.games = [dict(g) if hasattr(g, "keys") else g for g in games]
        matching_ids = {g.get("id") for g in self.games}
        if not self.current_game_id or self.current_game_id not in matching_ids:
            self.current_game_id = self.games[0].get("id") if self.games else None
        self.render_games()

    def _on_wheel_image_loaded(self, gid: int, img):
        if not img.isNull():
            pix = QPixmap.fromImage(img)
            self.delegate._wheel_cache[gid] = pix
            if self.isVisible():
                self.wheel_list.viewport().update()

    def _preload_around(self, center_row: int):
        if not self.games or not hasattr(self, "_wheel_worker") or not self._wheel_worker:
            return
        n = len(self.games)
        window = [
            self.games[i] for i in range(max(0, center_row - 10), min(n, center_row + 35))
            if self.games[i].get("id") not in self.delegate._wheel_cache
        ]
        if window:
            self._wheel_worker.queue_games(window)

    def _preload_direction(self, direction: int):
        if not self.games or not hasattr(self, "_wheel_worker") or not self._wheel_worker:
            return
        curr = self.wheel_list.currentRow()
        n = len(self.games)
        count = 30
        window = [
            self.games[curr + (i * direction)]
            for i in range(1, count + 1)
            if 0 <= curr + (i * direction) < n and self.games[curr + (i * direction)].get("id") not in self.delegate._wheel_cache
        ]
        if window:
            self._wheel_worker.queue_games(window, priority=True)

    def render_games(self):
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        if hasattr(self, "video_timer"):
            self.video_timer.stop()

        self.delegate.invalidate_cache()
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.clear()
        self._preload_around(0)
        self.wheel_list.blockSignals(True)
        self.wheel_list.setUpdatesEnabled(False)
        self.wheel_list.clear()

        target_item = None
        for g in self.games:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, g.get("id"))
            item.setData(Qt.UserRole + 10, g)
            self.wheel_list.addItem(item)
            if self.current_game_id and g.get("id") == self.current_game_id:
                target_item = item

        if not target_item and self.wheel_list.count() > 0:
            target_item = self.wheel_list.item(0)
            self.current_game_id = target_item.data(Qt.UserRole)

        if target_item:
            self.wheel_list.setCurrentItem(target_item)
            self.wheel_list.setUpdatesEnabled(True)
            self.wheel_list.blockSignals(False)
            self._update_game_display(target_item.data(Qt.UserRole + 10))
        else:
            self.wheel_list.setUpdatesEnabled(True)
            self.wheel_list.blockSignals(False)
            self.current_game_id = None
            self._clear_game_display()

    def select_game_by_id(self, game_id: int):
        curr = self.wheel_list.currentItem()
        if curr and curr.data(Qt.UserRole) == game_id and self.current_game_id == game_id:
            return
        self.current_game_id = game_id
        target_item = None
        for i in range(self.wheel_list.count()):
            item = self.wheel_list.item(i)
            if item and item.data(Qt.UserRole) == game_id:
                target_item = item
                break

        if not target_item and self.wheel_list.count() > 0:
            target_item = self.wheel_list.item(0)
            self.current_game_id = target_item.data(Qt.UserRole)

        if target_item:
            self.wheel_list.blockSignals(True)
            self.wheel_list.setCurrentItem(target_item)
            self.wheel_list.blockSignals(False)
            self._preload_around(self.wheel_list.row(target_item))
            self._update_game_display(target_item.data(Qt.UserRole + 10))
        else:
            self._clear_game_display()

    def _clear_game_display(self):
        self.title_label.setText("No hay elementos")
        self.meta_label.setText("—")
        self.boxart_label.clear()
        self.boxart_label.setVisible(False)
        self.wheel_logo_label.clear()
        self.wheel_logo_label.setVisible(False)
        self.current_media = {}
        if self.player:
            try:
                self.player.stop()
                self.player.setSource(QUrl())
            except Exception:
                pass
        self._video_stack.setCurrentIndex(0)

    def _on_wheel_item_changed(self, current, previous):
        if not current:
            return
        game = current.data(Qt.UserRole + 10)
        if game:
            row = self.wheel_list.row(current)
            if previous:
                diff = row - self.wheel_list.row(previous)
                if diff != 0:
                    self._preload_direction(1 if diff > 0 else -1)
            self._preload_around(row)
            self.current_game_id = game.get("id")
            self.game_selected.emit(self.current_game_id)
            self._update_game_display(game)

    def _update_game_display(self, game: dict):
        if not game:
            self._clear_game_display()
            return

        title = game.get("title", "")
        self.title_label.setText(title)

        emu = game.get("effective_name", "Sin emulador")
        plat = game.get("platform") or "Retro"
        filename = os.path.basename(game.get("rom_path", ""))
        if game.get("is_menu_target"):
            self.meta_label.setText(f"Sistema: <b>{plat}</b>   |   Contenido: <b>{emu}</b>")
        else:
            xml_bits = []
            if game.get("year"):
                xml_bits.append(f"<b>{game['year']}</b>")
            if game.get("manufacturer"):
                xml_bits.append(f"<b>{game['manufacturer']}</b>")
            if game.get("genre"):
                xml_bits.append(f"{game['genre']}")
            if game.get("players"):
                xml_bits.append(f"👥 {game['players']}")
            xml_line = f"<br>{'   ·   '.join(xml_bits)}" if xml_bits else ""
            self.meta_label.setText(
                f"Plataforma: <b>{plat}</b>   |   Emulador: <b>{emu}</b>{xml_line}"
                f"<br>Archivo: <span style='color:#6d7b93;'>{filename}</span>"
            )

        # Detener video previo y diferir la lectura en disco de artes pesadas (boxart/logo/video)
        self._want_video_playing = False
        if hasattr(self, "_video_watchdog_timer"):
            self._video_watchdog_timer.stop()
        if self.audio_output:
            try:
                self.audio_output.setMuted(True)
                self.audio_output.setVolume(0.0)
            except Exception:
                pass
        if self.player:
            try:
                self.player.pause()
            except Exception:
                pass
        if hasattr(self, "video_timer"):
            self.video_timer.stop()

        self._pending_art_game = game
        if hasattr(self, "_art_timer"):
            self._art_timer.start(120)

    def _load_pending_art(self):
        game = getattr(self, "_pending_art_game", None)
        if not game:
            return

        title = game.get("title", "")

        # Resolver medios (boxart, wheel, video)
        rom_path = game.get("rom_path", "")
        self.current_media = resolve_game_media(rom_path, game)

        # 1. Box Art
        box_file = self.current_media.get("boxart")
        if box_file and os.path.isfile(box_file):
            pix = QPixmap(box_file).scaled(
                self.boxart_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.boxart_label.setPixmap(pix)
            self.boxart_label.setVisible(True)
        else:
            if game.get("is_menu_target"):
                self.boxart_label.clear()
                self.boxart_label.setVisible(False)
            else:
                cover_pix = load_cover(game.get("cover_path"), title, self.boxart_label.size())
                self.boxart_label.setPixmap(cover_pix)
                self.boxart_label.setVisible(True)

        # 2. Wheel Logo grande
        wheel_file = self.current_media.get("wheel")
        if wheel_file and os.path.isfile(wheel_file):
            w_pix = QPixmap(wheel_file).scaled(QSize(220, 50), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.wheel_logo_label.setPixmap(w_pix)
            self.wheel_logo_label.setVisible(True)
        else:
            self.wheel_logo_label.clear()
            self.wheel_logo_label.setVisible(False)

        # 3. Video Snap — solo si el player ya fue inicializado
        video_file = self.current_media.get("video")
        if video_file and os.path.isfile(video_file):
            if self._player_initialized and self.player:
                self.video_timer.start()
            else:
                self._video_stack.setCurrentIndex(0)
        else:
            self._video_stack.setCurrentIndex(0)
            if self.player:
                try:
                    self.player.stop()
                    self.player.setSource(QUrl())
                except Exception:
                    pass

    def _start_video(self):
        if not self.isVisible() or not self._player_initialized or not self.player:
            return
        video_file = self.current_media.get("video")
        if video_file and os.path.isfile(video_file):
            self._want_video_playing = True
            self._video_stack.setCurrentIndex(1)
            try:
                if self.audio_output:
                    is_m = getattr(self, "_media_muted", False)
                    self.audio_output.setMuted(is_m)
                    self.audio_output.setVolume(0.0 if is_m else 0.35)
                src_url = QUrl.fromLocalFile(video_file)
                if self.player.source() == src_url:
                    self.player.setPosition(0)
                else:
                    self.player.setSource(src_url)
                self.player.play()
                self._video_watchdog_timer.start()
            except Exception as e:
                print(f"[WheelLayout] Error al reproducir video: {e}")

    def _toggle_mute(self):
        is_muted = self.mute_btn.isChecked()
        self.set_media_muted(is_muted)
        if hasattr(self, "wheel_list") and self.wheel_list:
            self.wheel_list.setFocus()
        else:
            self.setFocus()

    def eventFilter(self, watched, event):
        if watched == getattr(self, "wheel_list", None) and event.type() == QEvent.KeyPress:
            self.keyPressEvent(event)
            if event.isAccepted():
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if hasattr(self, "wheel_list") and self.wheel_list:
            self.wheel_list.setFocus()
        else:
            self.setFocus()

    def _on_wheel_double_clicked(self, item):
        if item:
            game_id = item.data(Qt.UserRole)
            if game_id and self._can_activate_game():
                self.current_game_id = game_id
                self.game_activated.emit(game_id)

    def _on_play_clicked(self):
        if self.current_game_id and self._can_activate_game():
            self.game_activated.emit(self.current_game_id)

    def _on_context_menu(self, pos: QPoint):
        item = self.wheel_list.itemAt(pos)
        if item:
            game_id = item.data(Qt.UserRole)
            global_pos = self.wheel_list.mapToGlobal(pos)
            self.context_menu_requested.emit(game_id, global_pos)

    def keyPressEvent(self, event):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if matches_action(event, ACTION_SELECT, getattr(self, "db", None)):
            if event.isAutoRepeat():
                event.accept()
                return
            if self.current_game_id and self._can_activate_game():
                self.game_activated.emit(self.current_game_id)
                event.accept()
                return
        elif matches_action(event, ACTION_NAV_UP, getattr(self, "db", None)):
            self._preload_direction(-1)
            row = max(0, self.wheel_list.currentRow() - 1)
            self.wheel_list.setCurrentRow(row)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_DOWN, getattr(self, "db", None)):
            self._preload_direction(1)
            row = min(self.wheel_list.count() - 1, self.wheel_list.currentRow() + 1)
            self.wheel_list.setCurrentRow(row)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_LETTER_BACK, getattr(self, "db", None)):
            self.jump_to_prev_letter()
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_LETTER_FWD, getattr(self, "db", None)) or matches_action(event, ACTION_NAV_LETTER, getattr(self, "db", None)):
            self.jump_to_next_letter()
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_STEP5_BACK, getattr(self, "db", None)) or matches_action(event, ACTION_PAGE_UP, getattr(self, "db", None)):
            self.navigate_steps(-5)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_STEP5_FWD, getattr(self, "db", None)) or matches_action(event, ACTION_NAV_STEP5, getattr(self, "db", None)) or matches_action(event, ACTION_PAGE_DOWN, getattr(self, "db", None)):
            self.navigate_steps(5)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_BACK, getattr(self, "db", None)):
            self.nav_back_requested.emit()
            event.accept()
            return
        elif matches_action(event, ACTION_MUTE, getattr(self, "db", None)):
            self.set_media_muted(not getattr(self, "_media_muted", False))
            event.accept()
            return
        super().keyPressEvent(event)

    def set_media_muted(self, muted: bool):
        """Silencia o reactiva el sonido del reproductor de video."""
        self._media_muted = muted
        if self.audio_output:
            try:
                self.audio_output.setMuted(muted)
                self.audio_output.setVolume(0.0 if muted else 0.35)
            except Exception:
                pass
        if hasattr(self, "sound_effect") and self.sound_effect:
            try:
                self.sound_effect.setMuted(muted)
            except Exception:
                pass
        if hasattr(self, "select_effect") and self.select_effect:
            try:
                self.select_effect.setMuted(muted)
            except Exception:
                pass
        if hasattr(self, "mute_btn") and self.mute_btn:
            try:
                self.mute_btn.blockSignals(True)
                self.mute_btn.setChecked(muted)
                self.mute_btn.setText("🔇 Silenciado" if muted else "🔊 Silenciar video")
                self.mute_btn.blockSignals(False)
            except Exception:
                pass
        # Garantizar que el foco permanezca en la rueda de juegos para responder al teclado
        if hasattr(self, "wheel_list") and self.wheel_list:
            self.wheel_list.setFocus()

    def stop_media(self):
        """Detiene el reproductor de video al cambiar de layout."""
        if hasattr(self, "video_timer"):
            self.video_timer.stop()
        if hasattr(self, "audio_output") and self.audio_output:
            try:
                self.audio_output.setMuted(True)
                self.audio_output.setVolume(0.0)
            except Exception:
                pass
        if self.player:
            try:
                self.player.stop()
                self.player.setSource(QUrl())
            except Exception:
                pass
        self._video_stack.setCurrentIndex(0)

    def hideEvent(self, event):
        # Detener video al salir o cambiar de pestaña para liberar recursos
        self.stop_media()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.stop_media()
        if hasattr(self, "_wheel_worker") and self._wheel_worker:
            self._wheel_worker.stop()
        if event is not None:
            super().closeEvent(event)
