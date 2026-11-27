import sys
import os
import time
import random
from collections import deque
import subprocess
from pathlib import Path
import playnexus
from PySide6.QtCore import Qt, QPoint, QSize, QTimer, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QMessageBox, QStackedWidget, QGraphicsOpacityEffect
)
from playnexus.db import Database
from playnexus.i18n import tr
from playnexus.services.library import enrich_game_dict
from playnexus.services.launcher import launch_game
from playnexus.services.controls import (
    ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_NAV_LETTER, ACTION_NAV_STEP5,
    ACTION_NAV_LETTER_BACK, ACTION_NAV_LETTER_FWD,
    ACTION_NAV_STEP5_BACK, ACTION_NAV_STEP5_FWD,
    ACTION_NAV_BACK, ACTION_SELECT, ACTION_PAGE_UP, ACTION_PAGE_DOWN,
    ACTION_CLOSE_FRONTEND,
    ACTION_MUTE, ACTION_TOGGLE_FPS, ACTION_TOGGLE_FAVORITE, ACTION_FRONTEND_MENU,
    matches_action, get_binding
)
from playnexus.services.gamepad import get_gamepad_manager
from playnexus.ui.frontend_quick_menu import (
    FrontendQuickMenuOverlay, QuickSearchOverlay,
    filter_and_sort_runtime_games, execute_system_power_action,
)
from playnexus.ui.gpu_renderer import (
    is_gpu_rendering_permitted,
    normalize_render_backend,
)
from playnexus.ui.layout_studio.runtime_hook import (
    apply_render_backend_to_layout,
    update_studio_effects,
)
from playnexus.ui.layouts import LAYOUT_REGISTRY, get_available_layouts, create_layout, resolve_theme_name
from playnexus.ui.shaders import (
    install_layout_runtime_fx_hook,
    resolve_widget_effect_settings,
    SHADER_LABELS,
    get_shader_label,
    normalize_shader_preset,
    normalize_shader_target,
    normalize_effects_perf,
)
from playnexus.ui.particles import (
    RetroEffectOverlayWidget,
    PARTICLE_LABELS,
    get_particle_label,
    normalize_particle_preset,
)

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
        self._all_list_games = []
        self._last_loaded_list_id = None
        self._runtime_filter_mode = "all"
        self._runtime_sort_mode = "title"
        self._quick_menu_overlay = None
        self._quick_search_overlay = None
        self._manual_viewer_overlay = None
        self._transition_overlay = None
        self._transition_anim = None
        self._roulette_timer = QTimer(self)
        self._roulette_timer.setSingleShot(True)
        self._roulette_timer.timeout.connect(self._on_roulette_tick)
        self._roulette_steps = []
        self._roulette_winner_id = None
        self._roulette_winner_idx = 0
        self._roulette_active = False
        self.requested_return_to_configurator = False
        self.active_layouts = {}
        self.navigation_history = []

        self.setWindowTitle(tr("player.window_title", "PlayNexus — Frontend"))
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet(PLAYER_STYLESHEET)

        root_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
        icon_path = root_dir / "app_icon.ico"
        if not icon_path.exists():
            icon_path = root_dir / "PlayNexus_icon.png"
        if not icon_path.exists():
            icon_path = root_dir / "PlayNexus_Logo.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Gestor de mandos y joysticks en tiempo real
        self.gamepad_manager = get_gamepad_manager(self.db)
        self.gamepad_manager.action_triggered.connect(self._on_gamepad_action)
        self.gamepad_manager.trigger_pressed.connect(self._on_gamepad_trigger)

        self._build_ui()
        self._setup_shortcuts()
        self.load_startup_list()
        try:
            from playnexus.services.audio_guard import ensure_audio_guard_installed
            ensure_audio_guard_installed(self)
        except Exception:
            pass

    def _build_ui(self):
        self.layout_stack = QStackedWidget()
        self.layout_stack.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(self.layout_stack)

        # Capa transparente de partículas ambientales y shaders post-proceso globales
        self._retro_overlay = RetroEffectOverlayWidget(self)
        self._retro_overlay.hide()

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
        self.fps_label.setText(tr("player.fps_placeholder", "FPS: --"))
        self.fps_label.adjustSize()
        show_fps_cfg = self.db.get_setting("video_show_fps", "false").lower() in ("true", "1", "yes")
        self.fps_label.setVisible(show_fps_cfg)

        # Timer para actualizar lectura de FPS cada 250ms
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(250)
        self._fps_timer.timeout.connect(self._update_fps_display)
        self._fps_timer.start()

        # Salvapantallas (Screensaver)
        self._screensaver_widget = None
        self._screensaver_timer = QTimer(self)
        self._screensaver_timer.setSingleShot(True)
        self._screensaver_timer.timeout.connect(self._trigger_screensaver)
        self._restart_screensaver_timer()

        # Instalar eventFilter en la propia ventana para captura global de inactividad
        self.installEventFilter(self)
        self.layout_stack.installEventFilter(self)

    def _setup_shortcuts(self):
        # F11 para alternar pantalla completa
        QShortcut(QKeySequence(Qt.Key_F11), self, self.toggle_fullscreen)
        # Atajo dinámico para alternar FPS (por defecto F10) y alias secundario F3
        fps_key_str = get_binding(self.db, ACTION_TOGGLE_FPS) or "F10"
        self._fps_shortcut = QShortcut(QKeySequence(fps_key_str), self, self.toggle_fps_counter)
        if fps_key_str.strip().upper() != "F3":
            self._fps_shortcut_alt = QShortcut(QKeySequence(Qt.Key_F3), self, self.toggle_fps_counter)

        # Notificación flotante (toast) discreta para acciones rápidas como Favoritos
        self.toast_label = QLabel(self)
        self.toast_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.toast_label.setAlignment(Qt.AlignCenter)
        self.toast_label.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast_label.hide)

        try:
            from playnexus.services.emulator_manager import EMULATOR_MANAGER
            EMULATOR_MANAGER.telemetry_updated.connect(self._on_telemetry_updated)
        except Exception:
            pass

    def focusNextPrevChild(self, next: bool) -> bool:
        """Evita que la tecla Tab robe el foco del Frontend al asignarse al Menú Rápido."""
        return False

    def eventFilter(self, watched, event):
        # Reiniciar contador de inactividad ante cualquier interacción de usuario
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            if not self._is_screensaver_active():
                self._restart_screensaver_timer()

        if event.type() == QEvent.KeyPress and not self._is_screensaver_active():
            from playnexus.services.emulator_manager import EMULATOR_MANAGER
            if not EMULATOR_MANAGER.is_launching_or_running():
                overlay = self._active_overlay()
                if overlay is not None and watched is not overlay and not overlay.isAncestorOf(watched):
                    overlay.keyPressEvent(event)
                    return True
                if overlay is None and matches_action(event, ACTION_FRONTEND_MENU, self.db):
                    self.open_quick_menu()
                    event.accept()
                    return True
                if overlay is None and matches_action(event, ACTION_CLOSE_FRONTEND, self.db):
                    if not event.isAutoRepeat():
                        if self._roulette_active:
                            self._stop_random_roulette(commit=False)
                        self.prompt_exit_confirmation()
                    event.accept()
                    return True

        if event.type() == QEvent.Paint:
            self._record_fps_tick()
        return super().eventFilter(watched, event)

    def _record_fps_tick(self):
        now = time.perf_counter()
        self._frame_times.append(now)
        while self._frame_times and (now - self._frame_times[0]) > 1.0:
            self._frame_times.popleft()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_retro_overlay") and self._retro_overlay:
            self._retro_overlay.setGeometry(self.rect())
        self._reposition_fps_label()
        if hasattr(self, "toast_label") and self.toast_label and self.toast_label.isVisible():
            x = max(20, (self.width() - self.toast_label.width()) // 2)
            self.toast_label.move(x, 24)
            self.toast_label.raise_()
        if hasattr(self, "_screensaver_widget") and self._screensaver_widget:
            self._screensaver_widget.setGeometry(self.rect())
            self._screensaver_widget.raise_()
        if hasattr(self, "_quick_menu_overlay") and self._quick_menu_overlay and self._quick_menu_overlay.isVisible():
            self._quick_menu_overlay.setGeometry(self.rect())
            self._quick_menu_overlay.raise_()
        if hasattr(self, "_quick_search_overlay") and self._quick_search_overlay and self._quick_search_overlay.isVisible():
            self._quick_search_overlay.setGeometry(self.rect())
            self._quick_search_overlay.raise_()
        if hasattr(self, "_manual_viewer_overlay") and self._manual_viewer_overlay and self._manual_viewer_overlay.isVisible():
            self._manual_viewer_overlay.setGeometry(self.rect())
            self._manual_viewer_overlay.raise_()
        if hasattr(self, "_transition_overlay") and self._transition_overlay and self._transition_overlay.isVisible():
            self._transition_overlay.setGeometry(self.layout_stack.geometry())

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
        self.fps_label.setText(
            tr(
                "player.fps_readout",
                "{fps} FPS ({ms} ms) • {driver} • {w}x{h}",
                fps=f"{fps:.1f}",
                ms=f"{frame_ms:.1f}",
                driver=driver,
                w=self.width(),
                h=self.height(),
            )
        )
        self.fps_label.adjustSize()
        self._reposition_fps_label()

    def _active_overlay(self):
        """Retorna el overlay arcade actualmente visible (ManualViewer, QuickSearch o QuickMenu)."""
        if self._manual_viewer_overlay and self._manual_viewer_overlay.isVisible():
            return self._manual_viewer_overlay
        if self._quick_search_overlay and self._quick_search_overlay.isVisible():
            return self._quick_search_overlay
        if self._quick_menu_overlay and self._quick_menu_overlay.isVisible():
            return self._quick_menu_overlay
        return None

    def open_quick_menu(self):
        """Abre el Menú Rápido Arcade superpuesto sin pausar el video actual."""
        if self._is_screensaver_active():
            return
        if self._quick_search_overlay and self._quick_search_overlay.isVisible():
            self.close_quick_search()
        if self._quick_menu_overlay is None:
            self._quick_menu_overlay = FrontendQuickMenuOverlay(self.db, self)
            self._quick_menu_overlay.close_requested.connect(self.close_quick_menu)
            self._quick_menu_overlay.toggle_favorite_requested.connect(self.toggle_current_favorite)
            self._quick_menu_overlay.random_game_requested.connect(self.start_random_roulette)
            self._quick_menu_overlay.search_requested.connect(self.open_quick_search)
            self._quick_menu_overlay.open_manual_requested.connect(self.open_manual_viewer)
            self._quick_menu_overlay.filter_sort_changed.connect(self._on_runtime_filter_sort_changed)
            self._quick_menu_overlay.layout_selected.connect(self._on_quick_layout_selected)
            self._quick_menu_overlay.shader_preset_changed.connect(self._on_quick_shader_changed)
            self._quick_menu_overlay.particle_preset_changed.connect(self._on_quick_particle_changed)
            self._quick_menu_overlay.system_action_requested.connect(self._on_system_action_requested)

        list_row = self.db.get_list(self.current_list_id) if self.current_list_id else None
        list_name = (list_row.get("name") if list_row else "") or "Frontend"
        cur_game = next((g for g in self.games_cache if g.get("id") == self.current_game_id), None)
        full_game = (self.db.get_game(self.current_game_id) if self.current_game_id else None) or cur_game
        from playnexus.services.media import resolve_game_manual_pdf
        is_menu = self._is_menu_list(self.current_list_id)
        manual_pdf = resolve_game_manual_pdf(full_game, list_row=list_row) if (full_game and not is_menu) else ""
        active_layout_name = (list_row.get("layout") if list_row else "") or "Wheel"
        avail_layouts = get_available_layouts(for_frontend=True)
        sh_cfg = normalize_shader_preset(self.db.get_setting("frontend_shader_preset", "layout"), allow_layout=True)
        pt_cfg = normalize_particle_preset(self.db.get_setting("frontend_particle_preset", "layout"), allow_layout=True)

        self._quick_menu_overlay.open_with_context(
            list_name=list_name,
            is_menu_list=is_menu,
            current_game=full_game,
            filter_mode=self._runtime_filter_mode,
            sort_mode=self._runtime_sort_mode,
            active_layout_name=active_layout_name,
            available_layouts=avail_layouts,
            shader_preset=sh_cfg,
            particle_preset=pt_cfg,
            manual_path=manual_pdf,
        )
        self._quick_menu_overlay.setGeometry(self.rect())
        self._quick_menu_overlay.show()
        self._quick_menu_overlay.raise_()
        self._quick_menu_overlay.setFocus()

    def close_quick_menu(self):
        if self._quick_menu_overlay:
            self._quick_menu_overlay.hide()
        cur = self.layout_stack.currentWidget()
        if cur:
            cur.setFocus()

    def open_manual_viewer(self):
        """Abre el visor de manuales PDF superpuesto sin pausar el video de fondo."""
        if self._is_screensaver_active() or self._is_menu_list(self.current_list_id):
            return
        if not self.current_game_id:
            return
        list_row = self.db.get_list(self.current_list_id) if self.current_list_id else None
        cur_game = next((g for g in self.games_cache if g.get("id") == self.current_game_id), None)
        full_game = self.db.get_game(self.current_game_id) or cur_game
        if not full_game:
            return

        from playnexus.services.media import resolve_game_manual_pdf
        pdf = resolve_game_manual_pdf(full_game, list_row=list_row)
        if not pdf:
            self._show_toast(tr("player.toast_no_manual", "This game does not have an assigned PDF manual."))
            return

        if self._quick_menu_overlay and self._quick_menu_overlay.isVisible():
            self._quick_menu_overlay.hide()
        if self._quick_search_overlay and self._quick_search_overlay.isVisible():
            self._quick_search_overlay.hide()

        if self._manual_viewer_overlay is None:
            from playnexus.ui.manual_viewer import ManualViewerOverlay
            self._manual_viewer_overlay = ManualViewerOverlay(self.db, self)
            self._manual_viewer_overlay.close_requested.connect(self.close_manual_viewer)

        self._manual_viewer_overlay.open_manual(pdf, game_title=full_game.get("title", ""))

    def close_manual_viewer(self):
        if self._manual_viewer_overlay:
            self._manual_viewer_overlay.hide()
        cur = self.layout_stack.currentWidget()
        if cur:
            cur.setFocus()

    def open_quick_search(self):
        """Abre el buscador rápido con teclado en pantalla sobre la lista activa."""
        if self._is_screensaver_active():
            return
        if self._quick_menu_overlay and self._quick_menu_overlay.isVisible():
            self._quick_menu_overlay.hide()
        if self._quick_search_overlay is None:
            self._quick_search_overlay = QuickSearchOverlay(self.db, self)
            self._quick_search_overlay.close_requested.connect(self.close_quick_search)
            self._quick_search_overlay.game_selected_requested.connect(self._on_quick_search_selected)

        pool = self._all_list_games or self.games_cache
        self._quick_search_overlay.open_with_games(pool)
        self._quick_search_overlay.setGeometry(self.rect())
        self._quick_search_overlay.show()
        self._quick_search_overlay.raise_()
        self._quick_search_overlay.setFocus()

    def close_quick_search(self):
        if self._quick_search_overlay:
            self._quick_search_overlay.hide()
        cur = self.layout_stack.currentWidget()
        if cur:
            cur.setFocus()

    def _on_quick_search_selected(self, game_id: int):
        """Salta al juego encontrado en Búsqueda Rápida y confirma sus medios."""
        if not any(g.get("id") == game_id for g in self.games_cache) and self._runtime_filter_mode != "all":
            self._runtime_filter_mode = "all"
            self._apply_runtime_filter_and_sort(restore_game_id=game_id)
            return
        cur = self.layout_stack.currentWidget()
        if cur:
            cur.select_game_by_id(game_id)
            if hasattr(cur, "_commit_selection"):
                cur._commit_selection()
        self._on_game_selected(game_id)
        item = next((g for g in self.games_cache if g.get("id") == game_id), None)
        if item:
            self._show_toast(f"🔍 {item.get('title', '')}", "#a5b4fc")

    def _on_runtime_filter_sort_changed(self, filter_mode: str, sort_mode: str):
        self._runtime_filter_mode = filter_mode
        self._runtime_sort_mode = sort_mode
        self._apply_runtime_filter_and_sort()

    def _on_quick_layout_selected(self, layout_name: str):
        if not self.current_list_id or not layout_name:
            return
        self.db.update_list(self.current_list_id, layout=layout_name)
        keep_gid = self.current_game_id
        self.select_list(self.current_list_id, push_history=False, restore_game_id=keep_gid)
        self._show_toast(tr("player.toast_layout", "🎨 Layout: {name}", name=layout_name), "#a78bfa")

    def _on_quick_shader_changed(self, shader_preset: str):
        norm = normalize_shader_preset(shader_preset, allow_layout=True)
        self.db.set_setting("frontend_shader_preset", norm)
        self._sync_visual_effects()
        lbl = tr("qmenu.from_layout", "From Layout") if norm == "layout" else get_shader_label(norm)
        self._show_toast(tr("player.toast_shader", "📺 Shader: {label}", label=lbl), "#38bdf8")

    def _on_quick_particle_changed(self, particle_preset: str):
        norm = normalize_particle_preset(particle_preset, allow_layout=True)
        self.db.set_setting("frontend_particle_preset", norm)
        self._sync_visual_effects()
        lbl = tr("qmenu.from_layout", "From Layout") if norm == "layout" else get_particle_label(norm)
        self._show_toast(tr("player.toast_particles", "✨ Particles: {label}", label=lbl), "#c084fc")

    def _sync_visual_effects(self):
        """Sincroniza shader GPU/software, backend gráfico y partículas activas en el layout y overlay."""
        user_sh = normalize_shader_preset(self.db.get_setting("frontend_shader_preset", "layout"), allow_layout=True)
        raw_tg = self.db.get_setting("frontend_shader_target", "layout").strip().lower()
        user_tg = "layout" if raw_tg in ("", "layout", "auto") else normalize_shader_target(raw_tg)
        user_pt = normalize_particle_preset(self.db.get_setting("frontend_particle_preset", "layout"), allow_layout=True)
        user_perf = normalize_effects_perf(self.db.get_setting("frontend_effects_perf", "high"))
        user_rb = normalize_render_backend(self.db.get_setting("frontend_render_backend", "auto"))

        cur = self.layout_stack.currentWidget() if hasattr(self, "layout_stack") else None
        cur_gpu_active = False
        if cur is not None:
            cur._pn_shader_override = user_sh
            cur._pn_shader_target_override = user_tg
            cur._pn_particle_override = user_pt
            cur._pn_effects_perf = user_perf
            apply_render_backend_to_layout(cur, user_rb)

            vp = getattr(cur, "_gpu_viewport", None)
            cur_gpu_active = (
                vp is not None
                and not getattr(vp, "_fallback_triggered", True)
                and is_gpu_rendering_permitted(user_rb)
            )
            cur._pn_external_overlay = not cur_gpu_active
            if hasattr(cur, "_studio_override_installed") and cur._studio_override_installed:
                update_studio_effects(cur)
            sh_eff, tg_eff, pt_eff, perf_eff = resolve_widget_effect_settings(cur)
            cur.update()
        else:
            sh_eff = "none" if user_sh == "layout" else user_sh
            tg_eff = "tv_rect" if user_tg == "layout" else user_tg
            pt_eff = "none" if user_pt == "layout" else user_pt
            perf_eff = user_perf

        if hasattr(self, "_retro_overlay") and self._retro_overlay is not None:
            if cur_gpu_active:
                self._retro_overlay.configure(
                    shader_preset="none",
                    shader_target="tv_rect",
                    particle_preset="none",
                    perf_profile=perf_eff,
                )
            else:
                self._retro_overlay.configure(
                    shader_preset=sh_eff,
                    shader_target=tg_eff,
                    particle_preset=pt_eff,
                    perf_profile=perf_eff,
                )
            if hasattr(self, "fps_label") and self.fps_label and self.fps_label.isVisible():
                self.fps_label.raise_()
            if hasattr(self, "toast_label") and self.toast_label and self.toast_label.isVisible():
                self.toast_label.raise_()
            active_ov = self._active_overlay() if hasattr(self, "_active_overlay") else None
            if active_ov is not None:
                active_ov.raise_()

    def _on_system_action_requested(self, action: str):
        if action == "return_configurator":
            self.requested_return_to_configurator = True
            self._confirmed_exit = True
            self.close()
        elif action == "exit_frontend":
            self._confirmed_exit = True
            self.close()
        elif action in ("restart_pc", "shutdown_pc"):
            try:
                execute_system_power_action(action)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    tr("player.power_error_title", "Power error"),
                    tr("player.power_error_msg", "Could not execute system action:\n{error}", error=e),
                )

    def start_random_roulette(self):
        """
        Ruleta aleatoria animada con desaceleración visual respetando Commit-on-Release:
        avanza pasos de rueda sin cargar artes ni pausar el video previo hasta detenerse en el ganador.
        """
        pool = self.games_cache
        n = len(pool)
        if n <= 0:
            return
        if n == 1:
            gid = pool[0].get("id")
            if gid:
                self._show_toast(
                    f"🎲 {pool[0].get('title') or tr('player.game_fallback', 'Game')}",
                    "#fbbf24",
                )
            return

        cur_idx = 0
        for idx, g in enumerate(pool):
            if g.get("id") == self.current_game_id:
                cur_idx = idx
                break

        cand_indices = [i for i in range(n) if i != cur_idx]
        winner_idx = random.choice(cand_indices)
        winner = pool[winner_idx]
        self._roulette_winner_id = winner.get("id")
        self._roulette_winner_idx = winner_idx

        total_dist = (winner_idx - cur_idx) % n
        while total_dist < 14:
            total_dist += n

        delays = [36, 38, 42, 46, 52, 60, 70, 84, 100, 118, 140, 168, 200, 240]
        num_ticks = len(delays)
        steps_list: list[tuple[int, int]] = []
        tail_ticks = min(6, total_dist)
        head_ticks = num_ticks - tail_ticks
        remaining = total_dist - tail_ticks

        for t_idx in range(num_ticks):
            if t_idx < head_ticks and head_ticks > 0:
                left = head_ticks - t_idx
                step = remaining // left
                remaining -= step
            else:
                step = 1
            if step > 0 or t_idx == num_ticks - 1:
                steps_list.append((step, delays[t_idx]))

        self._roulette_steps = steps_list
        self._roulette_active = True
        self._show_toast(
            tr("player.toast_roulette_spinning", "🎲 Spinning random wheel…"),
            "#fbbf24",
            duration_ms=2600,
        )
        self._on_roulette_tick()

    def _stop_random_roulette(self, commit: bool = False):
        self._roulette_active = False
        if self._roulette_timer.isActive():
            self._roulette_timer.stop()
        self._roulette_steps = []
        if commit and self._roulette_winner_id is not None:
            cur = self.layout_stack.currentWidget()
            winner_gid = self._roulette_winner_id
            if cur:
                if hasattr(cur, "_commit_timer"):
                    try:
                        cur._commit_timer.stop()
                    except Exception:
                        pass
                cur.select_game_by_id(winner_gid)
                if hasattr(cur, "_commit_selection"):
                    cur._commit_selection()
            self._on_game_selected(winner_gid)

    def _on_roulette_tick(self):
        if not self._roulette_active or not self._roulette_steps:
            self._roulette_active = False
            return

        step, delay_ms = self._roulette_steps.pop(0)
        cur = self.layout_stack.currentWidget()
        is_last = (len(self._roulette_steps) == 0)

        if cur and step > 0:
            if hasattr(cur, "_navigate_steps"):
                # ThemeLayout: avanza visualmente la ruleta sin pausar video ni disparar carga de artes
                cur._navigate_steps(step)
            elif hasattr(cur, "wheel_list") and hasattr(cur.wheel_list, "setCurrentRow"):
                total = cur.wheel_list.count()
                if total > 0:
                    nxt = (cur.wheel_list.currentRow() + step) % total
                    if is_last:
                        cur.wheel_list.setCurrentRow(nxt)
                    else:
                        cur.wheel_list.blockSignals(True)
                        cur.wheel_list.setCurrentRow(nxt)
                        cur.wheel_list.blockSignals(False)
            elif hasattr(cur, "table") and hasattr(cur.table, "selectRow"):
                total = cur.table.rowCount()
                if total > 0:
                    nxt = (cur.table.currentRow() + step) % total
                    if is_last:
                        cur.table.selectRow(nxt)
                    else:
                        cur.table.blockSignals(True)
                        cur.table.selectRow(nxt)
                        cur.table.blockSignals(False)
            elif hasattr(cur, "selected_index") and hasattr(cur, "games") and cur.games:
                cur.selected_index = (cur.selected_index + step) % len(cur.games)
                cur.update()

        if is_last:
            self._roulette_active = False
            winner_gid = self._roulette_winner_id
            winner = next((g for g in self.games_cache if g.get("id") == winner_gid), None)
            if cur and winner_gid is not None:
                if hasattr(cur, "_commit_timer"):
                    try:
                        cur._commit_timer.stop()
                    except Exception:
                        pass
                if hasattr(cur, "_commit_selection"):
                    cur._commit_selection()
                else:
                    cur.select_game_by_id(winner_gid)
            if winner_gid is not None:
                self._on_game_selected(winner_gid)
            if winner:
                self._show_toast(
                    tr(
                        "player.toast_roulette_winner",
                        "🎲 Picked: {title}!",
                        title=winner.get("title") or tr("player.game_fallback", "Game"),
                    ),
                    "#4ade80",
                    duration_ms=2600,
                )
        else:
            self._roulette_timer.start(delay_ms)

    def _show_toast(self, message: str, accent: str = "#fbbf24", duration_ms: int = 2100):
        """Muestra una insignia flotante discreta sin interrumpir video ni ruleta."""
        if not hasattr(self, "toast_label") or not self.toast_label:
            return
        self.toast_label.setStyleSheet(f"""
            background-color: rgba(12, 14, 22, 0.90);
            color: {accent};
            font-family: 'Segoe UI', sans-serif;
            font-size: 15px;
            font-weight: 700;
            padding: 9px 18px;
            border-radius: 10px;
            border: 1px solid {accent};
        """)
        self.toast_label.setText(message)
        self.toast_label.adjustSize()
        x = max(20, (self.width() - self.toast_label.width()) // 2)
        y = 24
        self.toast_label.move(x, y)
        self.toast_label.show()
        self.toast_label.raise_()
        if hasattr(self, "_toast_timer"):
            self._toast_timer.start(duration_ms)

    def _on_telemetry_updated(self, game_id: int):
        """Refresca en RAM la telemetría de un juego tras iniciar o cerrar sesión."""
        if not self.db or not self.games_cache:
            return
        row = self.db.get_game(game_id)
        if not row:
            return
        for item in self.games_cache:
            if item.get("id") == game_id:
                item["play_count"] = row.get("play_count", 0)
                item["play_time_seconds"] = row.get("play_time_seconds", 0)
                item["last_played"] = row.get("last_played", "")
                item["is_favorite"] = row.get("is_favorite", 0)
                break

    def toggle_current_favorite(self):
        """Alterna favorito del juego seleccionado sin pausar videos ni reiniciar la ruleta."""
        cur = self.layout_stack.currentWidget() if hasattr(self, "layout_stack") else None
        gid = self.current_game_id
        if not gid and cur and hasattr(cur, "get_selected_game_id"):
            gid = cur.get_selected_game_id()
        if not gid:
            return

        selected_item = next((g for g in self.games_cache if g.get("id") == gid), None)
        if selected_item and selected_item.get("is_menu_target"):
            self._show_toast(
                tr("player.toast_favorites_only_in_list", "★ Favorites are available inside a game list"),
                "#94a3b8",
            )
            return

        new_state = self.db.toggle_game_favorite(gid)
        if new_state is None:
            return

        title = (selected_item.get("title") if selected_item else None) or tr("player.game_fallback", "Game")
        if selected_item is not None:
            selected_item["is_favorite"] = 1 if new_state else 0

        if new_state:
            self._show_toast(tr("player.toast_fav_added", "⭐ Added to Favorites: {title}", title=title), "#fbbf24")
        else:
            self._show_toast(tr("player.toast_fav_removed", "☆ Removed from Favorites: {title}", title=title), "#cbd5e1")

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
        if hasattr(self, "_screensaver_timer"):
            self._screensaver_timer.stop()
        if hasattr(self, "_retro_overlay") and self._retro_overlay is not None:
            self._retro_overlay.stop()
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
        self._restart_screensaver_timer()
        self._sync_visual_effects()
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
        self._stop_random_roulette(commit=False)
        if hasattr(self, "_retro_overlay") and self._retro_overlay is not None:
            self._retro_overlay.stop()
        if getattr(self, "_transition_anim", None) and self._transition_anim.state():
            self._transition_anim.stop()
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
        """Retrocede en el historial de navegación (listas de listas o menús)."""
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

        # Intercepción del Salvapantallas
        if self._is_screensaver_active():
            if matches_action(event, ACTION_SELECT, self.db):
                gid = self._screensaver_widget.get_currently_displayed_game_id()
                self._dismiss_screensaver()
                if gid:
                    self.select_game_by_id(gid)
            else:
                self._dismiss_screensaver()
            event.accept()
            return

        self._restart_screensaver_timer()

        overlay = self._active_overlay()
        if overlay is not None:
            overlay.keyPressEvent(event)
            event.accept()
            return

        if self._roulette_active and not event.isAutoRepeat():
            self._stop_random_roulette(commit=False)

        if matches_action(event, ACTION_FRONTEND_MENU, self.db):
            self.open_quick_menu()
            event.accept()
            return

        if matches_action(event, ACTION_TOGGLE_FAVORITE, self.db):
            self.toggle_current_favorite()
            event.accept()
            return

        if matches_action(event, ACTION_TOGGLE_FPS, self.db):
            self.toggle_fps_counter()
            event.accept()
            return
        elif matches_action(event, ACTION_CLOSE_FRONTEND, self.db):
            self.prompt_exit_confirmation()
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_BACK, self.db):
            self.go_back()
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

        if self._is_screensaver_active():
            self._dismiss_screensaver()
            event.accept()
            return

        self._restart_screensaver_timer()
        cur = self.layout_stack.currentWidget()
        if cur and hasattr(cur, "wheelEvent"):
            cur.wheelEvent(event)
            if event.isAccepted():
                return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if self._is_screensaver_active():
            self._dismiss_screensaver()
            event.accept()
            return

        self._restart_screensaver_timer()
        cur = self.layout_stack.currentWidget()
        if cur:
            cur.setFocus()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_screensaver_active():
            pos = event.pos()
            last = getattr(self, "_last_mouse_pos", None)
            self._last_mouse_pos = pos
            if last and (abs(pos.x() - last.x()) > 6 or abs(pos.y() - last.y()) > 6):
                self._dismiss_screensaver()
                event.accept()
                return
        else:
            self._restart_screensaver_timer()
        super().mouseMoveEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            cur = self.layout_stack.currentWidget()
            if cur:
                cur.setFocus()
        elif event.type() == QEvent.Type.WindowStateChange:
            old_state = event.oldState()
            if self.isMinimized():
                self.stop_all_active_media()
            elif (old_state & Qt.WindowMinimized) and not self.isMinimized():
                cur = self.layout_stack.currentWidget()
                if cur:
                    if hasattr(cur, "resume_media") and callable(cur.resume_media):
                        cur.resume_media()
                    elif hasattr(cur, "_update_current_selection") and callable(cur._update_current_selection):
                        cur._update_current_selection()
        super().changeEvent(event)

    def _on_gamepad_trigger(self, trigger_name: str):
        """Despacha gatillos/bumpers (LT/RT/LB/RB) hacia el visor de manuales si está visible."""
        overlay = self._active_overlay()
        if overlay is not None and hasattr(overlay, "handle_trigger"):
            if self.isVisible() and not self.isMinimized():
                overlay.handle_trigger(trigger_name)

    def _on_gamepad_action(self, action_id: str):
        """Procesa acciones provenientes de cualquier mando/joystick conectado."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            return

        if self._is_screensaver_active():
            if action_id == ACTION_SELECT:
                gid = self._screensaver_widget.get_currently_displayed_game_id()
                self._dismiss_screensaver()
                if gid:
                    self.select_game_by_id(gid)
            else:
                self._dismiss_screensaver()
            return

        self._restart_screensaver_timer()

        if not self.isActiveWindow():
            if self.isVisible() and not self.isMinimized():
                self.activateWindow()
                self.raise_()
            else:
                return

        overlay = self._active_overlay()
        if overlay is not None:
            overlay.handle_action(action_id)
            return

        if self._roulette_active:
            self._stop_random_roulette(commit=False)

        if action_id == ACTION_FRONTEND_MENU:
            self.open_quick_menu()
            return

        if action_id == ACTION_TOGGLE_FAVORITE:
            self.toggle_current_favorite()
            return

        if action_id == ACTION_TOGGLE_FPS:
            self.toggle_fps_counter()
            return
        elif action_id == ACTION_CLOSE_FRONTEND:
            self.prompt_exit_confirmation()
            return
        elif action_id == ACTION_NAV_BACK:
            self.go_back()
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
                tr(
                    "player.no_lists_placeholder",
                    "No lists have been created in PlayNexus.<br><br>"
                    "Open the Configurator to create lists and add games.",
                )
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
        user_rb = normalize_render_backend(self.db.get_setting("frontend_render_backend", "auto"))
        vp = getattr(inst, "_gpu_viewport", None)
        has_gpu = vp is not None and not getattr(vp, "_fallback_triggered", True) and is_gpu_rendering_permitted(user_rb)
        inst._pn_external_overlay = not has_gpu
        apply_render_backend_to_layout(inst, user_rb)
        if vp is not None:
            vp.set_on_frame_rendered(self._record_fps_tick)
        install_layout_runtime_fx_hook(inst)
        inst.game_selected.connect(self._on_game_selected)
        inst.game_activated.connect(self._on_game_activated)
        if hasattr(inst, "nav_back_requested"):
            inst.nav_back_requested.connect(self.go_back)
        inst.installEventFilter(self)
        for child in inst.findChildren(QWidget):
            child.installEventFilter(self)
        self.active_layouts[layout_name] = inst
        self.layout_stack.addWidget(inst)
        return inst

    def select_list(self, list_id: int, push_history: bool = True, restore_game_id: int | None = None):
        """
        Selecciona una lista o menú y carga su layout específico asignado.
        Si proviene de un menú (lista de listas), este método carga el layout propio de la sub-lista.
        """
        prev_list_id = self.current_list_id
        if push_history and self.current_list_id and self.current_list_id != list_id:
            self.navigation_history.append((self.current_list_id, self.current_game_id))

        self.current_list_id = list_id

        row = self.db.get_list(list_id)
        if not row:
            return

        if row.get("list_type") == "filtered":
            try:
                from playnexus.services.library import sync_filtered_list_games
                sync_filtered_list_games(self.db, list_id)
            except Exception:
                pass

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
        self._stop_random_roulette(commit=False)
        prev_widget = self.layout_stack.currentWidget()
        prev_pixmap = None
        if prev_widget is not None and prev_widget.isVisible() and self.isVisible():
            trans_mode = self.db.get_setting("frontend_view_transition", "fade").strip().lower()
            if trans_mode != "instant":
                try:
                    prev_pixmap = prev_widget.grab()
                except Exception:
                    prev_pixmap = None

        self.stop_all_active_media()

        inst = self._get_or_create_layout(target_layout)
        self.layout_stack.setCurrentWidget(inst)
        inst.setFocus()

        self.current_game_id = None
        self.load_games(restore_game_id=restore_game_id)
        self._sync_visual_effects()

        if prev_pixmap is not None and not prev_pixmap.isNull() and (prev_widget is not inst or prev_list_id != list_id):
            self._start_view_transition(prev_pixmap)

    def _start_view_transition(self, snapshot_pixmap):
        """Aplica un crossfade suave de 220 ms usando la captura de la vista previa."""
        try:
            if self._transition_anim and self._transition_anim.state():
                self._transition_anim.stop()
            if self._transition_overlay is None:
                self._transition_overlay = QLabel(self)
                self._transition_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                self._transition_overlay.setScaledContents(True)
            self._transition_overlay.setPixmap(snapshot_pixmap)
            self._transition_overlay.setGeometry(self.layout_stack.geometry())

            eff = QGraphicsOpacityEffect(self._transition_overlay)
            eff.setOpacity(1.0)
            self._transition_overlay.setGraphicsEffect(eff)
            self._transition_overlay.show()
            self._transition_overlay.raise_()

            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(220)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)

            def _cleanup_trans():
                if self._transition_overlay:
                    self._transition_overlay.hide()
                    self._transition_overlay.setGraphicsEffect(None)

            anim.finished.connect(_cleanup_trans)
            self._transition_anim = anim
            anim.start()
        except Exception:
            if self._transition_overlay:
                self._transition_overlay.hide()

    def load_games(self, restore_game_id: int | None = None):
        if not self.current_list_id:
            self._all_list_games = []
            self.games_cache = []
            return

        row = self.db.get_list(self.current_list_id)
        if not row:
            return

        if self._last_loaded_list_id != self.current_list_id:
            self._last_loaded_list_id = self.current_list_id
            self._runtime_filter_mode = "all"
            self._runtime_sort_mode = str(row.get("sort_mode") or "title")

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
                    "effective_name": tr("player.menu_game_count", "{count} games", count=g_count),
                    "source": "menu",
                    "icon_path": t_dict.get("icon_path", ""),
                })
            self._all_list_games = items
            self.games_cache = items
            current_layout = self.layout_stack.currentWidget()
            if current_layout:
                current_layout.set_games(self.games_cache)
                target_select_id = None
                if restore_game_id and any(item["id"] == restore_game_id for item in self.games_cache):
                    target_select_id = restore_game_id
                elif self.games_cache:
                    target_select_id = self.games_cache[0]["id"]

                if target_select_id and current_layout.get_selected_game_id() != target_select_id:
                    current_layout.select_game_by_id(target_select_id)
                if target_select_id:
                    self._on_game_selected(target_select_id)
            return

        rows = self.db.get_games(self.current_list_id, search_term="", enriched=True)
        self._all_list_games = [enrich_game_dict(r) for r in rows]
        self._apply_runtime_filter_and_sort(restore_game_id=restore_game_id)

    def _apply_runtime_filter_and_sort(self, restore_game_id: int | None = None):
        """Aplica el filtro y orden en caliente sobre `_all_list_games` y actualiza la vista."""
        filtered = filter_and_sort_runtime_games(
            self._all_list_games, self._runtime_filter_mode, self._runtime_sort_mode
        )
        if not filtered and self._all_list_games and self._runtime_filter_mode != "all":
            self._show_toast(
                tr("player.toast_filter_fallback", "⚠ No games match the filter; showing all"),
                "#f59e0b",
            )
            self._runtime_filter_mode = "all"
            filtered = filter_and_sort_runtime_games(
                self._all_list_games, self._runtime_filter_mode, self._runtime_sort_mode
            )

        self.games_cache = filtered
        current_layout = self.layout_stack.currentWidget()
        if current_layout:
            current_layout.set_games(self.games_cache)
            target_select_id = None
            keep_id = restore_game_id or self.current_game_id
            if keep_id and any(item["id"] == keep_id for item in self.games_cache):
                target_select_id = keep_id
            elif self.games_cache:
                target_select_id = self.games_cache[0]["id"]

            if target_select_id and current_layout.get_selected_game_id() != target_select_id:
                current_layout.select_game_by_id(target_select_id)
            if target_select_id:
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
            QMessageBox.critical(self, tr("player.launch_error_title", "Could not launch game"), str(e))

    def _is_screensaver_active(self) -> bool:
        """Indica si el widget del salvapantallas está actualmente activo y visible."""
        return bool(hasattr(self, "_screensaver_widget") and self._screensaver_widget and self._screensaver_widget.isVisible())

    def _is_menu_list(self, list_id: int | None) -> bool:
        """Determina si la lista indicada es un menú de sistemas (lista de listas)."""
        if not list_id:
            return False
        row = self.db.get_list(list_id)
        return bool(row and "list_type" in row.keys() and row["list_type"] == "menu")

    def _restart_screensaver_timer(self):
        """Reinicia el temporizador de inactividad según los minutos configurados."""
        if not hasattr(self, "_screensaver_timer"):
            return
        ss_enabled = self.db.get_setting("screensaver_enabled", "true").lower() in ("true", "1", "yes")
        if not ss_enabled:
            self._screensaver_timer.stop()
            return

        try:
            timeout_min = int(self.db.get_setting("screensaver_timeout", "3") or "3")
        except (ValueError, TypeError):
            timeout_min = 3
        timeout_ms = max(5000, timeout_min * 60 * 1000)
        self._screensaver_timer.start(timeout_ms)

    def _trigger_screensaver(self):
        """Activa el salvapantallas tras cumplirse el tiempo de inactividad."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            self._restart_screensaver_timer()
            return

        if not self.isVisible() or self.isMinimized() or self._is_screensaver_active():
            return

        # Pausar reproducción del layout activo
        self.pause_active_media()

        from playnexus.ui.screensaver import ScreensaverWidget
        pool = self.games_cache if (self.games_cache and not self._is_menu_list(self.current_list_id)) else None
        self._screensaver_widget = ScreensaverWidget(self.db, games=pool, parent=self)
        self._screensaver_widget.setGeometry(self.rect())
        self._screensaver_widget.game_selected_request.connect(self._on_screensaver_select)
        self._screensaver_widget.dismiss_requested.connect(self._dismiss_screensaver)
        self._screensaver_widget.show()
        self._screensaver_widget.raise_()
        self._screensaver_widget.setFocus()
        self._screensaver_widget.start()

    def _dismiss_screensaver(self):
        """Cierra el salvapantallas y devuelve el control al layout activo."""
        if hasattr(self, "_screensaver_widget") and self._screensaver_widget:
            self._screensaver_widget.stop_all()
            self._screensaver_widget.hide()
            self._screensaver_widget.deleteLater()
            self._screensaver_widget = None

        cur = self.layout_stack.currentWidget()
        if cur:
            cur.setFocus()
        self.resume_active_media()
        self._restart_screensaver_timer()

    def _on_screensaver_select(self, game_id: int):
        """Salta y selecciona directamente el juego exhibido en el salvapantallas."""
        self._dismiss_screensaver()
        if game_id:
            self.select_game_by_id(game_id)

    def select_game_by_id(self, game_id: int):
        """Selecciona el juego indicado por ID en la lista activa o navega a su lista si es externa."""
        if not game_id:
            return
        cur = self.layout_stack.currentWidget()
        in_current = any(g.get("id") == game_id for g in self.games_cache)
        if in_current and cur:
            if hasattr(cur, "select_game_by_id"):
                cur.select_game_by_id(game_id)
            self._on_game_selected(game_id)
        else:
            g_row = self.db.get_game(game_id)
            if g_row and g_row.get("list_id"):
                self.select_list(int(g_row["list_id"]), push_history=True, restore_game_id=game_id)

    def prompt_exit_confirmation(self):
        """Muestra una ventana modal de confirmación con estilo arcade antes de cerrar el frontend."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            return
        from playnexus.ui.exit_confirm_dialog import ExitConfirmDialog
        dlg = ExitConfirmDialog(self, db=self.db)
        if dlg.exec():
            self._confirmed_exit = True
            self.close()

    def closeEvent(self, event):
        """Detiene cualquier reproducción activa y el hilo de mandos antes de cerrar la ventana."""
        if not getattr(self, "_confirmed_exit", False):
            from playnexus.services.emulator_manager import EMULATOR_MANAGER
            if not EMULATOR_MANAGER.is_launching_or_running():
                from playnexus.ui.exit_confirm_dialog import ExitConfirmDialog
                dlg = ExitConfirmDialog(self, db=self.db)
                if not dlg.exec():
                    event.ignore()
                    return
        self._confirmed_exit = True
        try:
            self.setUpdatesEnabled(False)
            if sys.platform == "win32" and self.isVisible() and self.testAttribute(Qt.WA_WState_Created):
                import ctypes
                ctypes.windll.user32.ShowWindow(int(self.winId()), 0)  # SW_HIDE inmediato en DWM
            self.hide()
        except Exception:
            pass
        self.stop_all_active_media()
        for inst in list(getattr(self, "active_layouts", {}).values()):
            try:
                if hasattr(inst, "cleanup"):
                    inst.cleanup()
            except Exception:
                pass
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
        from playnexus.i18n import init_i18n
        db = Database()
        init_i18n(db)
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
    if getattr(window, "requested_return_to_configurator", False):
        try:
            import subprocess
            from pathlib import Path
            from playnexus.services.launcher import build_clean_child_env
            child_env = build_clean_child_env()
            popen_kw: dict = {"env": child_env, "close_fds": True}
            if os.name == "nt":
                popen_kw["creationflags"] = (
                    getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            if getattr(sys, "frozen", False):
                cfg_exe = Path(sys.executable).resolve().parent / "PlayNexus_Config.exe"
                if cfg_exe.exists():
                    subprocess.Popen([str(cfg_exe)], cwd=str(cfg_exe.parent), **popen_kw)
            else:
                entry_cfg = Path(__file__).resolve().parents[2] / "entry_config.py"
                if entry_cfg.exists():
                    subprocess.Popen([sys.executable, str(entry_cfg)], cwd=str(entry_cfg.parent), **popen_kw)
        except Exception:
            pass
    os._exit(code)
