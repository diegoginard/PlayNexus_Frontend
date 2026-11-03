import sys
import os
import time
from collections import deque
import subprocess
from pathlib import Path
import playnexus
from PySide6.QtCore import Qt, QPoint, QSize, QTimer, QEvent
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QMessageBox, QStackedWidget
)
from playnexus.db import Database
from playnexus.services.library import enrich_game_dict
from playnexus.services.launcher import launch_game
from playnexus.services.controls import (
    ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_NAV_LETTER, ACTION_NAV_STEP5,
    ACTION_NAV_LETTER_BACK, ACTION_NAV_LETTER_FWD,
    ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD,
    ACTION_NAV_BACK, ACTION_SELECT, ACTION_PAGE_UP, ACTION_PAGE_DOWN,
    ACTION_CLOSE_FRONTEND, ACTION_CLOSE_EMULATOR,
    ACTION_MUTE, ACTION_TOGGLE_FPS, matches_action,
    get_binding
)
from playnexus.services.gamepad import get_gamepad_manager
from playnexus.ui.layouts import LAYOUT_REGISTRY, get_available_layouts, create_layout, resolve_theme_name

PLAYER_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #000000;
    color: #e6e9f2;
}
QStackedWidget {
    background-color: #000000;
    border: none;
    margin: 0px;
    padding: 0px;
}
"""


class PlayerWindow(QMainWindow):
    """
    Ventana del Frontend / Reproductor a Pantalla Completa.
    Muestra exclusivamente los diseños visuales (layouts) en pantalla completa,
    sin barras, botones ni elementos ajenos a la experiencia de juego.
    Toda la configuración se realiza desde el Configurador principal (MainWindow).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = Database()
        self.current_list_id = None
        self.current_game_id = None
        self.games_cache = []
        self.active_layouts = {}
        self.navigation_history = []

        self.setWindowTitle("PlayNexus — Frontend")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet(PLAYER_STYLESHEET)

        root_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
        logo_path = root_dir / "PlayNexus_Logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        # Gestor de mandos y joysticks en tiempo real
        self.gamepad_manager = get_gamepad_manager(self.db)
        self.gamepad_manager.action_triggered.connect(self._on_gamepad_action)

        self._build_ui()
        self._setup_shortcuts()
        self.load_startup_list()

    def _build_ui(self):
        self.layout_stack = QStackedWidget()
        self.layout_stack.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(self.layout_stack)

        # Contador de FPS en tiempo real (Overlay flotante con estilo Arcade)
        self._frame_times = deque()
        self.fps_label = QLabel(self)
        self.fps_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.fps_label.setStyleSheet("""
            background-color: rgba(12, 14, 20, 0.88);
            color: #00ff88;
            font-family: 'Consolas', 'Segoe UI', monospace;
            font-size: 13px;
            font-weight: bold;
            padding: 5px 12px;
            border-radius: 8px;
            border: 1px solid rgba(0, 255, 136, 0.5);
        """)
        self.fps_label.setText("FPS: --")
        self.fps_label.adjustSize()
        show_fps_cfg = self.db.get_setting("video_show_fps", "false").lower() in ("true", "1", "yes")
        self.fps_label.setVisible(show_fps_cfg)

        # Timer para actualizar lectura de FPS cada 250ms
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(250)
        self._fps_timer.timeout.connect(self._update_fps_display)
        self._fps_timer.start()

    def _setup_shortcuts(self):
        # F11 para alternar pantalla completa
        QShortcut(QKeySequence(Qt.Key_F11), self, self.toggle_fullscreen)
        # Atajo dinámico para alternar FPS (por defecto F10) y alias secundario F3
        fps_key_str = get_binding(self.db, ACTION_TOGGLE_FPS) or "F10"
        self._fps_shortcut = QShortcut(QKeySequence(fps_key_str), self, self.toggle_fps_counter)
        if fps_key_str.strip().upper() != "F3":
            self._fps_shortcut_alt = QShortcut(QKeySequence(Qt.Key_F3), self, self.toggle_fps_counter)
        # Escape y Backspace para retroceder / salir
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.go_back)
        QShortcut(QKeySequence(Qt.Key_Backspace), self, self.go_back)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Paint:
            now = time.perf_counter()
            self._frame_times.append(now)
            while self._frame_times and (now - self._frame_times[0]) > 1.0:
                self._frame_times.popleft()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_fps_label()

    def _reposition_fps_label(self):
        if hasattr(self, "fps_label") and self.fps_label:
            self.fps_label.move(self.width() - self.fps_label.width() - 20, 20)
            self.fps_label.raise_()

    def _update_fps_display(self):
        if not hasattr(self, "fps_label") or not self.fps_label or self.fps_label.isHidden():
            return
        now = time.perf_counter()
        while self._frame_times and (now - self._frame_times[0]) > 1.0:
            self._frame_times.popleft()
        count = len(self._frame_times)
        if count >= 2:
            dt = self._frame_times[-1] - self._frame_times[0]
            fps = (count - 1) / dt if dt > 0 else 0.0
            frame_ms = (dt / (count - 1)) * 1000.0
        elif count == 1:
            fps = 60.0
            frame_ms = 16.6
        else:
            fps = 0.0
            frame_ms = 0.0

        if fps >= 55.0:
            color = "#00ff88"
        elif fps >= 30.0:
            color = "#ffcc00"
        else:
            color = "#ff4444"

        driver = os.environ.get("QT_RHI_BACKEND", "").upper() or self.db.get_setting("video_driver", "D3D11").upper()
        if not driver:
            driver = "GPU"

        if getattr(self, "_last_fps_color", None) != color:
            self.fps_label.setStyleSheet(f"""
                background-color: rgba(12, 14, 20, 0.88);
                color: {color};
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 13px;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 8px;
                border: 1px solid {color}88;
            """)
            self._last_fps_color = color
        self.fps_label.setText(f"{fps:.1f} FPS ({frame_ms:.1f} ms) • {driver} • {self.width()}x{self.height()}")
        self.fps_label.adjustSize()
        self._reposition_fps_label()

    def toggle_fps_counter(self):
        """Muestra u oculta el contador de FPS en pantalla y persiste la preferencia."""
        if hasattr(self, "fps_label") and self.fps_label:
            new_vis = self.fps_label.isHidden()
            self.fps_label.setVisible(new_vis)
            if new_vis:
                self._update_fps_display()
            try:
                self.db.set_setting("video_show_fps", "true" if new_vis else "false")
            except Exception:
                pass

    def pause_active_media(self):
        """Pausa la reproducción en el layout activo al iniciar un emulador (sin destruir el video)."""
        active_layout = self.layout_stack.currentWidget()
        if active_layout:
            if hasattr(active_layout, "pause_media") and callable(active_layout.pause_media):
                try:
                    active_layout.pause_media()
                except Exception:
                    pass
            elif hasattr(active_layout, "set_media_muted") and callable(active_layout.set_media_muted):
                try:
                    active_layout.set_media_muted(True)
                except Exception:
                    pass

    def resume_active_media(self):
        """Reanuda la reproducción en el layout activo al cerrar el emulador."""
        active_layout = self.layout_stack.currentWidget()
        if active_layout:
            if hasattr(active_layout, "resume_media") and callable(active_layout.resume_media):
                try:
                    active_layout.resume_media()
                except Exception:
                    pass
            elif hasattr(active_layout, "set_media_muted") and callable(active_layout.set_media_muted):
                try:
                    active_layout.set_media_muted(False)
                except Exception:
                    pass

    def stop_all_active_media(self):
        """Detiene completamente cualquier reproducción activa en TODOS los layouts para evitar audio residual."""
        for inst in list(self.active_layouts.values()):
            if hasattr(inst, "stop_media") and callable(inst.stop_media):
                try:
                    inst.stop_media()
                except Exception:
                    pass
            for audio_attr in ("audio_output", "game_audio"):
                if hasattr(inst, audio_attr):
                    ao = getattr(inst, audio_attr)
                    if ao:
                        try:
                            ao.setMuted(True)
                            ao.setVolume(0.0)
                        except Exception:
                            pass
            for player_attr in ("player", "game_player"):
                if hasattr(inst, player_attr):
                    p = getattr(inst, player_attr)
                    if p:
                        try:
                            p.stop()
                            from PySide6.QtCore import QUrl
                            p.setSource(QUrl())
                        except Exception:
                            pass

    def go_back(self):
        """Retrocede en el historial de navegación (listas de listas o menús). Si está en la raíz, no sale del sistema."""
        if not self.navigation_history:
            return

        # Detener inmediatamente el audio y video de TODOS los layouts antes de retroceder
        self.stop_all_active_media()

        prev_entry = self.navigation_history.pop()
        prev_lid = None
        prev_gid = None
        if isinstance(prev_entry, (tuple, list)):
            prev_lid = prev_entry[0]
            if len(prev_entry) > 1:
                prev_gid = prev_entry[1]
        elif isinstance(prev_entry, dict):
            prev_lid = prev_entry.get("list_id") or prev_entry.get("id")
            prev_gid = prev_entry.get("selected_game_id")
        elif isinstance(prev_entry, int):
            prev_lid = prev_entry

        if prev_lid:
            self.select_list(int(prev_lid), push_history=False, restore_game_id=prev_gid)

    def keyPressEvent(self, event):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if matches_action(event, ACTION_TOGGLE_FPS, self.db):
            self.toggle_fps_counter()
            event.accept()
            return
        elif matches_action(event, ACTION_CLOSE_FRONTEND, self.db):
            self.close()
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_BACK, self.db):
            if self.navigation_history:
                self.go_back()
                event.accept()
                return
            # Si estamos en la raíz y la tecla coincide específicamente con cerrar frontend o emulador
            if matches_action(event, ACTION_CLOSE_FRONTEND, self.db) or matches_action(event, ACTION_CLOSE_EMULATOR, self.db):
                self.close()
                event.accept()
                return
            # Si es la tecla/botón asignado para volver atrás, no salir del frontend
            event.accept()
            return
        elif matches_action(event, ACTION_CLOSE_EMULATOR, self.db):
            self.close()
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_LETTER_BACK, self.db):
            cur = self.layout_stack.currentWidget()
            if cur and hasattr(cur, "jump_to_prev_letter"):
                cur.jump_to_prev_letter()
                event.accept()
                return
        elif matches_action(event, ACTION_NAV_LETTER_FWD, self.db) or matches_action(event, ACTION_NAV_LETTER, self.db):
            cur = self.layout_stack.currentWidget()
            if cur and hasattr(cur, "jump_to_next_letter"):
                cur.jump_to_next_letter()
                event.accept()
                return
        elif matches_action(event, ACTION_NAV_STEP5_BACK, self.db) or matches_action(event, ACTION_PAGE_UP, self.db):
            cur = self.layout_stack.currentWidget()
            if cur and hasattr(cur, "navigate_steps"):
                cur.navigate_steps(-5)
                event.accept()
                return
        elif matches_action(event, ACTION_NAV_STEP5_FWD, self.db) or matches_action(event, ACTION_NAV_STEP5, self.db) or matches_action(event, ACTION_PAGE_DOWN, self.db):
            cur = self.layout_stack.currentWidget()
            if cur and hasattr(cur, "navigate_steps"):
                cur.navigate_steps(5)
                event.accept()
                return

        # Reenviar teclas no consumidas al layout activo (ej: flechas arriba/abajo, Enter, etc.)
        cur = self.layout_stack.currentWidget()
        if cur and hasattr(cur, "keyPressEvent"):
            cur.keyPressEvent(event)
            if event.isAccepted():
                return

        super().keyPressEvent(event)

    def wheelEvent(self, event):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        cur = self.layout_stack.currentWidget()
        if cur and hasattr(cur, "wheelEvent"):
            cur.wheelEvent(event)
            if event.isAccepted():
                return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        cur = self.layout_stack.currentWidget()
        if cur:
            cur.setFocus()
        super().mousePressEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            cur = self.layout_stack.currentWidget()
            if cur:
                cur.setFocus()
        super().changeEvent(event)

    def _on_gamepad_action(self, action_id: str):
        """Procesa acciones provenientes de cualquier mando/joystick conectado."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            return

        if not self.isActiveWindow():
            if self.isVisible() and not self.isMinimized():
                self.activateWindow()
                self.raise_()
            else:
                return

        if action_id == ACTION_TOGGLE_FPS:
            self.toggle_fps_counter()
            return
        elif action_id == ACTION_CLOSE_FRONTEND:
            self.close()
            return
        elif action_id == ACTION_NAV_BACK:
            if self.navigation_history:
                self.go_back()
            return
        elif action_id == ACTION_CLOSE_EMULATOR:
            self.close()
            return

        current_layout = self.layout_stack.currentWidget()
        if not current_layout:
            return

        if action_id == ACTION_NAV_UP:
            if hasattr(current_layout, "_navigate_steps"):
                current_layout._navigate_steps(-1)
            elif hasattr(current_layout, "wheel_list"):
                row = max(0, current_layout.wheel_list.currentRow() - 1)
                current_layout.wheel_list.setCurrentRow(row)
            elif hasattr(current_layout, "table"):
                row = max(0, current_layout.table.currentRow() - 1)
                current_layout.table.selectRow(row)

        elif action_id == ACTION_NAV_DOWN:
            if hasattr(current_layout, "_navigate_steps"):
                current_layout._navigate_steps(1)
            elif hasattr(current_layout, "wheel_list"):
                row = min(current_layout.wheel_list.count() - 1, current_layout.wheel_list.currentRow() + 1)
                current_layout.wheel_list.setCurrentRow(row)
            elif hasattr(current_layout, "table"):
                row = min(current_layout.table.rowCount() - 1, current_layout.table.currentRow() + 1)
                current_layout.table.selectRow(row)

        elif action_id == ACTION_NAV_LETTER_BACK:
            if hasattr(current_layout, "jump_to_prev_letter"):
                current_layout.jump_to_prev_letter()

        elif action_id in (ACTION_NAV_LETTER_FWD, ACTION_NAV_LETTER):
            if hasattr(current_layout, "jump_to_next_letter"):
                current_layout.jump_to_next_letter()

        elif action_id in (ACTION_NAV_STEP5_BACK, ACTION_PAGE_UP):
            if hasattr(current_layout, "navigate_steps"):
                current_layout.navigate_steps(-5)
            elif hasattr(current_layout, "_navigate_steps"):
                current_layout._navigate_steps(-5)
            elif hasattr(current_layout, "wheel_list"):
                row = max(0, current_layout.wheel_list.currentRow() - 5)
                current_layout.wheel_list.setCurrentRow(row)
            elif hasattr(current_layout, "table"):
                row = max(0, current_layout.table.currentRow() - 5)
                current_layout.table.selectRow(row)

        elif action_id in (ACTION_NAV_STEP5_FWD, ACTION_NAV_STEP5, ACTION_PAGE_DOWN):
            if hasattr(current_layout, "navigate_steps"):
                current_layout.navigate_steps(5)
            elif hasattr(current_layout, "_navigate_steps"):
                current_layout._navigate_steps(5)
            elif hasattr(current_layout, "wheel_list"):
                row = min(current_layout.wheel_list.count() - 1, current_layout.wheel_list.currentRow() + 5)
                current_layout.wheel_list.setCurrentRow(row)
            elif hasattr(current_layout, "table"):
                row = min(current_layout.table.rowCount() - 1, current_layout.table.currentRow() + 5)
                current_layout.table.selectRow(row)

        elif action_id == ACTION_SELECT:
            if hasattr(current_layout, "get_selected_game_id"):
                gid = current_layout.get_selected_game_id()
                if gid:
                    if hasattr(current_layout, "_play_select_sound"):
                        current_layout._play_select_sound()
                    self._on_game_activated(gid)
            elif self.current_game_id:
                self._on_game_activated(self.current_game_id)

        elif action_id == ACTION_MUTE:
            if hasattr(current_layout, "set_muted"):
                current_layout.set_muted(not current_layout.is_muted())
            elif hasattr(current_layout, "set_media_muted"):
                current_layout.set_media_muted(not getattr(current_layout, "_media_muted", False))

    def apply_video_settings(self):
        """Pre-calcula la configuración de video para aplicarla al iniciar."""
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()

        try:
            mon_val = self.db.get_setting("video_monitor", self.db.get_setting("target_screen", "0") or "0")
            mon_idx = int(mon_val or "0")
        except (ValueError, TypeError):
            mon_idx = 0

        target_screen = screens[mon_idx] if (screens and 0 <= mon_idx < len(screens)) else primary
        geo = target_screen.geometry() if target_screen else None

        mode = self.db.get_setting("video_mode", "fullscreen")
        res_key = self.db.get_setting("video_resolution", "system")

        if res_key == "custom":
            try:
                w = int(self.db.get_setting("video_custom_width", "1920") or "1920")
                h = int(self.db.get_setting("video_custom_height", "1080") or "1080")
            except (ValueError, TypeError):
                w, h = 1920, 1080
        elif res_key in ("system", "native") or "x" not in str(res_key):
            if geo:
                w = geo.width()
                h = geo.height()
            else:
                w, h = 1920, 1080
        else:
            try:
                parts = str(res_key).split("x")
                w, h = int(parts[0]), int(parts[1])
            except Exception:
                w, h = 1920, 1080

        self._pending_mode = mode
        self._pending_geo = geo
        self._pending_w = w
        self._pending_h = h
        self.configured_window_size = QSize(w, h)

    def _apply_show(self):
        """Aplica la configuración de visualización y reproduce splash screen si está habilitado."""
        splash_enabled = (self.db.get_setting("frontend_splash_enabled", "false").strip().lower() in ("true", "1", "yes"))
        if splash_enabled and not getattr(self, "_splash_played", False):
            from playnexus.ui.splash_screen import resolve_splash_video, VideoSplashScreen
            video_file = resolve_splash_video(self.db)
            if video_file and video_file.is_file():
                self._splash_played = True
                geo = getattr(self, "_pending_geo", None)
                if not geo:
                    try:
                        mon_idx = int(self.db.get_setting("video_monitor", "0"))
                    except Exception:
                        mon_idx = 0
                    screens = QGuiApplication.screens()
                    if 0 <= mon_idx < len(screens):
                        geo = screens[mon_idx].geometry()
                    elif screens:
                        geo = screens[0].geometry()

                self.splash_screen = VideoSplashScreen(video_file, target_geo=geo, db=self.db)
                self.splash_screen.finished.connect(self._on_splash_finished)
                self.splash_screen.showFullScreen()
                self.splash_screen.raise_()
                self.splash_screen.activateWindow()
                self.splash_screen.start_playback()
                return

        self._apply_show_direct()

    def _on_splash_finished(self):
        """Se ejecuta tras concluir o saltar el video de splash screen."""
        self._apply_show_direct()

    def _apply_show_direct(self):
        """Aplica la configuración de visualización a pantalla completa."""
        mode = getattr(self, "_pending_mode", "fullscreen")
        geo = getattr(self, "_pending_geo", None)
        w = getattr(self, "_pending_w", 1920)
        h = getattr(self, "_pending_h", 1080)
        res_key = self.db.get_setting("video_resolution", "system")

        if mode == "windowed":
            self.showNormal()
            self.resize(w, h)
            if geo:
                cx = geo.x() + (geo.width() - w) // 2
                cy = geo.y() + (geo.height() - h) // 2
                try:
                    self.move(max(geo.x(), cx), max(geo.y(), cy))
                except Exception:
                    pass
            self.raise_()
            self.activateWindow()
        elif mode == "borderless":
            # Pantalla completa sin bordes (Borderless)
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
            if geo and (res_key in ("system", "native") or (w == geo.width() and h == geo.height())):
                self.setGeometry(geo)
            elif geo:
                cx = geo.x() + (geo.width() - w) // 2
                cy = geo.y() + (geo.height() - h) // 2
                self.setGeometry(cx, cy, w, h)
            else:
                self.resize(w, h)
            self.show()
            self.raise_()
            self.activateWindow()
        else:
            # Pantalla completa tradicional
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
            if geo:
                self.setGeometry(geo)
            self.showFullScreen()
            self.raise_()
            self.activateWindow()

        self.resume_active_media()
        cur = self.layout_stack.currentWidget()
        if cur:
            cur.setFocus()
            if hasattr(cur, "wheel_list") and cur.wheel_list:
                cur.wheel_list.setFocus()
            # Asegurar que el video del tema / snap comience de inmediato al mostrarse el frontend
            QTimer.singleShot(60, lambda: self._ensure_current_layout_media_playing(cur))

    def _ensure_current_layout_media_playing(self, layout):
        """Garantiza la reproducción de video en el layout visible una vez desplegada la ventana."""
        if not layout:
            return
        if hasattr(layout, "_play_debounced_video") and callable(layout._play_debounced_video):
            try:
                layout._play_debounced_video()
            except Exception:
                pass
        elif hasattr(layout, "_update_current_selection") and callable(layout._update_current_selection):
            try:
                layout._update_current_selection()
            except Exception:
                pass
        elif hasattr(layout, "resume_media") and callable(layout.resume_media):
            try:
                layout.resume_media()
            except Exception:
                pass

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            if hasattr(self, "configured_window_size") and self.configured_window_size.isValid():
                self.resize(self.configured_window_size)
        else:
            self.showFullScreen()

    def load_startup_list(self):
        """Carga la lista o menú configurado como inicio del frontend."""
        rows = self.db.get_lists(with_counts=True)
        if not rows:
            self._show_empty_placeholder(
                "No hay listas creadas en PlayNexus.<br><br>"
                "Abrí el Configurador para crear listas y añadir juegos."
            )
            return

        saved_startup = self.db.get_setting("frontend_startup_list", "")
        target_id = None
        if saved_startup:
            try:
                sid = int(saved_startup)
                if any(r["id"] == sid for r in rows):
                    target_id = sid
            except (ValueError, TypeError):
                pass

        if target_id is None:
            target_id = rows[0]["id"]

        self.select_list(target_id, push_history=False)

    def _show_empty_placeholder(self, message: str):
        placeholder = QWidget()
        v = QVBoxLayout(placeholder)
        v.setAlignment(Qt.AlignCenter)
        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #a3b1c6; font-size: 14pt; line-height: 1.6;")
        v.addWidget(lbl)
        self.layout_stack.addWidget(placeholder)
        self.layout_stack.setCurrentWidget(placeholder)

    def _get_or_create_layout(self, layout_name: str):
        """Obtiene una instancia del layout o la crea dinámicamente si es un tema de sistema."""
        if layout_name in self.active_layouts:
            return self.active_layouts[layout_name]

        inst = create_layout(layout_name)
        inst.db = self.db
        inst.game_selected.connect(self._on_game_selected)
        inst.game_activated.connect(self._on_game_activated)
        if hasattr(inst, "nav_back_requested"):
            inst.nav_back_requested.connect(self.go_back)
        inst.installEventFilter(self)
        self.active_layouts[layout_name] = inst
        self.layout_stack.addWidget(inst)
        return inst

    def select_list(self, list_id: int, push_history: bool = True, restore_game_id: int | None = None):
        """
        Selecciona una lista o menú y carga su layout específico asignado.
        Si proviene de un menú (lista de listas), este método carga el layout propio de la sub-lista.
        """
        if push_history and self.current_list_id and self.current_list_id != list_id:
            self.navigation_history.append((self.current_list_id, self.current_game_id))

        self.current_list_id = list_id

        row = self.db.get_list(list_id)
        if not row:
            return

        # Aplicar el layout asignado a esta lista o buscar si coincide con un tema
        chosen_layout = row["layout"] or ""
        platform_name = row["platform"] or ""
        list_name = row["name"] or ""

        available = get_available_layouts(for_frontend=True)

        if chosen_layout in available and chosen_layout != "Detalles":
            target_layout = chosen_layout
        elif resolve_theme_name(chosen_layout):
            target_layout = resolve_theme_name(chosen_layout)
        elif platform_name in available and platform_name != "Detalles":
            target_layout = platform_name
        elif resolve_theme_name(platform_name):
            target_layout = resolve_theme_name(platform_name)
        elif list_name in available and list_name != "Detalles":
            target_layout = list_name
        elif resolve_theme_name(list_name):
            target_layout = resolve_theme_name(list_name)
        else:
            target_layout = "Wheel"

        # Detener multimedia de todos los layouts antes de cambiar para evitar audio residual
        self.stop_all_active_media()

        inst = self._get_or_create_layout(target_layout)
        self.layout_stack.setCurrentWidget(inst)
        inst.setFocus()

        self.current_game_id = None
        self.load_games(restore_game_id=restore_game_id)

    def load_games(self, restore_game_id: int | None = None):
        if not self.current_list_id:
            self.games_cache = []
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        if "list_type" in row.keys() and row["list_type"] == "menu":
            menu_media_path = row["media_path"] if "media_path" in row.keys() else ""
            menu_boxart_path = row["boxart_path"] if "boxart_path" in row.keys() else ""
            menu_flyer_path = row.get("flyer_path", "")
            menu_wheel_path = row["wheel_path"] if "wheel_path" in row.keys() else ""
            menu_video_path = row["video_path"] if "video_path" in row.keys() else ""
            menu_cartart_path = row["cartart_path"] if "cartart_path" in row.keys() else ""
            menu_cabinet_path = row.get("cabinet_path", "")
            menu_marquee_path = row.get("marquee_path", "")
            menu_bezel_path = row.get("bezel_path", "")

            targets = self.db.get_menu_items(self.current_list_id)
            items = []
            for t in targets:
                t_dict = dict(t)
                title = t_dict["name"]
                platform = t_dict["platform"] or title
                g_count = self.db.count_games(t_dict["id"])
                items.append({
                    "id": t_dict["id"],
                    "target_list_id": t_dict["id"],
                    "is_menu_target": True,
                    "title": title,
                    "rom_path": "",
                    "list_id": self.current_list_id,
                    "platform": platform,
                    "media_path": menu_media_path,
                    "boxart_path": menu_boxart_path,
                    "flyer_path": menu_flyer_path,
                    "wheel_path": menu_wheel_path,
                    "video_path": menu_video_path,
                    "cartart_path": menu_cartart_path,
                    "cabinet_path": menu_cabinet_path,
                    "marquee_path": menu_marquee_path,
                    "bezel_path": menu_bezel_path,
                    "menu_media_path": menu_media_path,
                    "menu_wheel_path": menu_wheel_path,
                    "menu_video_path": menu_video_path,
                    "menu_boxart_path": menu_boxart_path,
                    "menu_cartart_path": menu_cartart_path,
                    "effective_name": f"{g_count} juegos",
                    "source": "menu",
                    "icon_path": t_dict.get("icon_path", ""),
                })
            self.games_cache = items
            current_layout = self.layout_stack.currentWidget()
            if current_layout:
                current_layout.set_games(self.games_cache)
                target_select_id = None
                if restore_game_id and any(item["id"] == restore_game_id for item in self.games_cache):
                    target_select_id = restore_game_id
                elif self.games_cache:
                    target_select_id = self.games_cache[0]["id"]

                if target_select_id:
                    current_layout.select_game_by_id(target_select_id)
                    self._on_game_selected(target_select_id)
            return

        rows = self.db.get_games(self.current_list_id, search_term="", enriched=True)
        self.games_cache = [enrich_game_dict(r) for r in rows]

        current_layout = self.layout_stack.currentWidget()
        if current_layout:
            current_layout.set_games(self.games_cache)
            target_select_id = None
            if restore_game_id and any(item["id"] == restore_game_id for item in self.games_cache):
                target_select_id = restore_game_id
            elif self.games_cache:
                target_select_id = self.games_cache[0]["id"]

            if target_select_id:
                current_layout.select_game_by_id(target_select_id)
                self._on_game_selected(target_select_id)

    def _on_game_selected(self, game_id: int):
        self.current_game_id = game_id

    def _on_game_activated(self, game_id: int):
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            return

        # Anti doble activación (doble clic, mando o teclado): se aplica ANTES de distinguir
        # entre menú y juego para que un doble clic sobre un sistema no abra la lista y
        # acto seguido ejecute el juego seleccionado en ella.
        now = time.perf_counter()
        last = getattr(self, "_last_activation_time", 0.0)
        window = max(0.6, QApplication.doubleClickInterval() / 1000.0 + 0.2)
        if last and (now - last < window):
            return
        self._last_activation_time = now

        self.current_game_id = game_id
        game = next((g for g in self.games_cache if g["id"] == game_id), None)
        if game and game.get("is_menu_target"):
            self.stop_all_active_media()
            target_id = game["target_list_id"]
            self.navigation_history.append((self.current_list_id, self.current_game_id))
            self.select_list(target_id, push_history=False)
            return

        db_game = self.db.get_game(game_id)
        if not db_game:
            return

        try:
            self.pause_active_media()
            from PySide6.QtCore import QEventLoop
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            active_layout = self.layout_stack.currentWidget()
            result = launch_game(self.db, db_game, layout=active_layout, parent_window=self)
            if not result or result[0] is None:
                # El lanzamiento fue descartado (ya había uno en curso): no dejar el video en pausa
                self._last_activation_time = 0.0
                self.resume_active_media()
        except Exception as e:
            self._last_activation_time = 0.0
            self.resume_active_media()
            QMessageBox.critical(self, "No se pudo iniciar el juego", str(e))

    def closeEvent(self, event):
        """Detiene cualquier reproducción activa y el hilo de mandos antes de cerrar la ventana."""
        self.stop_all_active_media()
        if hasattr(self, "splash_screen") and self.splash_screen:
            try:
                self.splash_screen.close()
                self.splash_screen.deleteLater()
            except Exception:
                pass
            self.splash_screen = None
        if hasattr(self, "gamepad_manager") and self.gamepad_manager:
            self.gamepad_manager.stop()
        super().closeEvent(event)


def run_player():
    import os
    from PySide6.QtCore import QTimer
    try:
        from playnexus.db import Database
        db = Database()
        driver = db.get_setting("video_driver", "d3d11")
        if driver:
            os.environ["QSG_RHI_BACKEND"] = driver
            os.environ["QT_RHI_BACKEND"] = driver
    except Exception:
        pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("PlayNexus Player")
    window = PlayerWindow()
    window.apply_video_settings()
    QTimer.singleShot(0, window._apply_show)
    code = app.exec()
    os._exit(code)
