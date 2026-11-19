"""
Pestaña de Configuración del Modo Frontend (Pantalla Completa) para PlayNexus.
Permite configurar:
1. Qué lista o menú de sistemas se mostrará al iniciar el frontend en pantalla completa.
2. El diseño visual del elemento de inicio.
3. Para menús de sistemas (listas de listas), la visualización y asignación del diseño visual
   propio de cada una de sus sub-listas (para que al navegar a ellas se muestre su diseño asignado).
4. Opciones de visualización de pantalla (pantalla completa, resolución, monitor).
5. Lanzamiento directo del Frontend en pantalla completa.
"""

import sys
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QGroupBox, QFrame, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QCheckBox, QLineEdit, QFileDialog,
    QListWidget, QListWidgetItem, QStackedWidget
)
from playnexus.db import Database, APP_DIR
from playnexus.i18n import tr
from playnexus.ui.layouts import get_available_layouts
from playnexus.ui.settings_tab import SCREEN_MODES, RESOLUTIONS_LIST
from playnexus.ui.shaders import (
    EFFECT_PERF_PROFILES,
    SHADER_PRESETS,
    SHADER_TARGETS,
    get_effects_perf_profiles,
    get_shader_presets,
    get_shader_targets,
    normalize_effects_perf,
    normalize_shader_preset,
    normalize_shader_target,
)
from playnexus.ui.gpu_renderer import (
    RENDER_BACKEND_PROFILES,
    get_render_backend_profiles,
    normalize_render_backend,
)
from playnexus.ui.particles import (
    PARTICLE_PRESETS,
    get_particle_presets,
    normalize_particle_preset,
)
from playnexus.ui.table_utils import (
    SortableTableWidgetItem,
    configure_details_table,
    paused_table_sorting,
)


class FrontendSettingsWidget(QWidget):
    """
    Panel de configuración del Frontend para pantalla completa.
    """
    layout_changed = Signal(int, str)  # (list_id, layout_name)
    launch_requested = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._updating = False

        self._build_ui()
        self.refresh_data()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(18, 16, 18, 16)
        outer_layout.setSpacing(14)

        # -------------------------------------------------------------
        # 1. ENCABEZADO SUPERIOR
        # -------------------------------------------------------------
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #1b1e2a; border: 1px solid #2a3143; border-radius: 8px; padding: 12px;")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(14, 10, 14, 10)
        h_layout.setSpacing(4)

        title = QLabel(tr("frontend.header_title", "📺  Frontend Mode Settings (Fullscreen)"))
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        h_layout.addWidget(title)

        desc = QLabel(
            tr(
                "frontend.header_desc",
                "Configure the frontend startup item, system menu visual layouts, "
                "target screen and monitor, splash video, and interactive screensaver.",
            )
        )
        desc.setStyleSheet("color: #9aa5b8; font-size: 9.5pt;")
        desc.setWordWrap(True)
        h_layout.addWidget(desc)
        outer_layout.addWidget(header_card)

        # -------------------------------------------------------------
        # CUERPO CENTRAL: Pestañas laterales a la izquierda y páginas a la derecha
        # -------------------------------------------------------------
        body_layout = QHBoxLayout()
        body_layout.setSpacing(16)

        # Barra lateral de pestañas (Sidebar)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("frontend_sidebar")
        self.sidebar.setFixedWidth(275)
        self.sidebar.setFocusPolicy(Qt.NoFocus)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sidebar.setStyleSheet("""
            QListWidget#frontend_sidebar {
                background-color: #161822;
                border: 1px solid #2a3143;
                border-radius: 8px;
                padding: 6px;
                outline: none;
            }
            QListWidget#frontend_sidebar::item {
                color: #a0aec0;
                padding: 12px 14px;
                border-radius: 6px;
                font-size: 10pt;
                font-weight: 500;
                margin-bottom: 4px;
            }
            QListWidget#frontend_sidebar::item:hover {
                background-color: #222638;
                color: #ffffff;
            }
            QListWidget#frontend_sidebar::item:selected {
                background-color: #5d48d9;
                color: #ffffff;
                font-weight: bold;
            }
        """)

        sidebar_items = [
            (
                tr("frontend.tab_startup", "🚀  Startup Item"),
                tr("frontend.tab_startup_tip", "Main list or menu and startup layout"),
            ),
            (
                tr("frontend.tab_menus", "🧭  System Menus & Layouts"),
                tr("frontend.tab_menus_tip", "Individual visual layouts for sub-lists"),
            ),
            (
                tr("frontend.tab_video", "🖥️  Screen & Monitor"),
                tr("frontend.tab_video_tip", "Display mode, monitor, and resolution"),
            ),
            (
                tr("frontend.tab_splash", "🎬  Splash Screen"),
                tr("frontend.tab_splash_tip", "Intro video when starting the Frontend"),
            ),
            (
                tr("frontend.tab_screensaver", "💤  Screensaver"),
                tr("frontend.tab_screensaver_tip", "Timeouts, video visual modes, and sound"),
            ),
        ]

        for item_text, item_tip in sidebar_items:
            item = QListWidgetItem(item_text)
            item.setToolTip(item_tip)
            item.setSizeHint(QSize(255, 48))
            self.sidebar.addItem(item)

        body_layout.addWidget(self.sidebar)

        # Contenedor apilado (QStackedWidget) a la derecha
        self.stacked_widget = QStackedWidget()
        self.sidebar.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

        def _make_tab_scroll(inner_widget: QWidget) -> QScrollArea:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setStyleSheet("QScrollArea { border: 1px solid #2a3143; border-radius: 8px; background-color: #161822; }")
            sa.setWidget(inner_widget)
            return sa

        # -------------------------------------------------------------
        # PESTAÑA 1: Elemento de Inicio
        # -------------------------------------------------------------
        page_start_container = QWidget()
        page_start_layout = QVBoxLayout(page_start_container)
        page_start_layout.setContentsMargins(20, 18, 20, 18)
        page_start_layout.setSpacing(14)

        grp_startup = QGroupBox(tr("frontend.grp_startup", "🚀 Frontend Startup Item"))
        v_startup = QVBoxLayout(grp_startup)
        v_startup.setSpacing(14)

        row_start = QHBoxLayout()
        row_start.setSpacing(14)

        col_list = QVBoxLayout()
        col_list.addWidget(QLabel(tr("frontend.startup_list_label", "<b>Main list or menu shown at startup:</b>")))
        self.startup_combo = QComboBox()
        self.startup_combo.setMinimumHeight(34)
        self.startup_combo.currentIndexChanged.connect(self._on_startup_list_changed)
        col_list.addWidget(self.startup_combo)
        row_start.addLayout(col_list, 2)

        col_layout = QVBoxLayout()
        col_layout.addWidget(QLabel(tr("frontend.startup_layout_label", "<b>Startup visual layout:</b>")))
        self.startup_layout_combo = QComboBox()
        self.startup_layout_combo.setMinimumHeight(34)
        self.startup_layout_combo.addItems(get_available_layouts(for_frontend=True))
        self.startup_layout_combo.currentTextChanged.connect(self._on_startup_layout_changed)
        col_layout.addWidget(self.startup_layout_combo)
        row_start.addLayout(col_layout, 1)

        v_startup.addLayout(row_start)

        self.startup_info_label = QLabel("")
        self.startup_info_label.setStyleSheet("color: #7b88a3; font-size: 9pt;")
        self.startup_info_label.setWordWrap(True)
        v_startup.addWidget(self.startup_info_label)

        page_start_layout.addWidget(grp_startup)
        page_start_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_start_container))

        # -------------------------------------------------------------
        # PESTAÑA 2: Menús de Sistemas y Diseños
        # -------------------------------------------------------------
        page_menu_container = QWidget()
        page_menu_layout = QVBoxLayout(page_menu_container)
        page_menu_layout.setContentsMargins(20, 18, 20, 18)
        page_menu_layout.setSpacing(14)

        self.grp_menu_systems = QGroupBox(
            tr("frontend.grp_menu_systems", "🧭 Visual Layouts for System Menus (Lists of lists)")
        )
        v_menu = QVBoxLayout(self.grp_menu_systems)
        v_menu.setSpacing(14)

        # Explicación del funcionamiento
        notice_box = QFrame()
        notice_box.setStyleSheet("background-color: #171b26; border-left: 4px solid #5d48d9; border-radius: 6px; padding: 10px;")
        n_layout = QVBoxLayout(notice_box)
        n_layout.setContentsMargins(6, 6, 6, 6)
        notice_text = QLabel(
            tr(
                "frontend.menu_notice_html",
                "<b>💡 Menu navigation behavior:</b><br>"
                "When starting the frontend with a System Menu, it will first display the menu layout (e.g., console wheel). "
                "When you press Enter / Select on any system, the Frontend will automatically load "
                "<b>the visual layout assigned to that specific list</b> (even if it wasn't selected as the main startup list). "
                "When you press Back (Escape / Backspace / Gamepad B), it will instantly return to the system menu.",
            )
        )
        notice_text.setStyleSheet("color: #c4cde0; font-size: 9pt;")
        notice_text.setWordWrap(True)
        n_layout.addWidget(notice_text)
        v_menu.addWidget(notice_box)

        # Selector del menú a inspeccionar/configurar
        row_menu_sel = QHBoxLayout()
        row_menu_sel.addWidget(QLabel(tr("frontend.menu_selector_label", "<b>System Menu to configure:</b>")))
        self.menu_selector_combo = QComboBox()
        self.menu_selector_combo.setMinimumHeight(32)
        self.menu_selector_combo.currentIndexChanged.connect(self._on_menu_selector_changed)
        row_menu_sel.addWidget(self.menu_selector_combo, 1)
        row_menu_sel.addStretch(1)
        v_menu.addLayout(row_menu_sel)

        # Tabla de sistemas vinculados al menú
        self.sublists_table = QTableWidget()
        self.sublists_table.setColumnCount(5)
        self.sublists_table.setHorizontalHeaderLabels([
            tr("frontend.col_system_list", "System / List"),
            tr("frontend.col_platform", "Platform"),
            tr("frontend.col_games", "Games"),
            tr("frontend.col_visual_layout", "Visual Layout for this System"),
            tr("frontend.col_emulator", "Emulator"),
        ])
        configure_details_table(
            self.sublists_table,
            col_widths=(220, 150, 95, 220, 160),
            alternating_rows=True,
        )
        self.sublists_table.setMinimumHeight(240)
        v_menu.addWidget(self.sublists_table)

        self.empty_menu_label = QLabel(
            tr("frontend.empty_menu_initial", "This menu currently has no linked systems.")
        )
        self.empty_menu_label.setAlignment(Qt.AlignCenter)
        self.empty_menu_label.setStyleSheet("color: #8b97ac; font-style: italic; padding: 20px;")
        self.empty_menu_label.setVisible(False)
        v_menu.addWidget(self.empty_menu_label)

        page_menu_layout.addWidget(self.grp_menu_systems)
        page_menu_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_menu_container))

        # -------------------------------------------------------------
        # PESTAÑA 3: Pantalla y Monitor
        # -------------------------------------------------------------
        page_video_container = QWidget()
        page_video_layout = QVBoxLayout(page_video_container)
        page_video_layout.setContentsMargins(20, 18, 20, 18)
        page_video_layout.setSpacing(14)

        grp_video = QGroupBox(tr("frontend.grp_video", "🖥 Frontend Screen & Monitor"))
        v_video = QVBoxLayout(grp_video)
        v_video.setSpacing(14)

        row_v = QHBoxLayout()
        row_v.setSpacing(16)

        col_m = QVBoxLayout()
        col_m.addWidget(QLabel(tr("frontend.screen_mode_label", "Screen mode:")))
        self.mode_combo = QComboBox()
        for label, val in SCREEN_MODES:
            self.mode_combo.addItem(label, val)
        self.mode_combo.currentIndexChanged.connect(self._save_video_settings)
        col_m.addWidget(self.mode_combo)
        row_v.addLayout(col_m, 1)

        col_scr = QVBoxLayout()
        col_scr.addWidget(QLabel(tr("frontend.target_monitor_label", "Target monitor:")))
        self.screen_combo = QComboBox()
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        for idx, scr in enumerate(screens):
            geo = scr.geometry()
            tag = tr("frontend.monitor_primary_tag", " [Primary]") if scr == primary else ""
            self.screen_combo.addItem(
                tr(
                    "frontend.monitor_item",
                    "Monitor {index}: {width}x{height}{tag}",
                    index=idx + 1,
                    width=geo.width(),
                    height=geo.height(),
                    tag=tag,
                ),
                idx,
            )
        self.screen_combo.currentIndexChanged.connect(self._on_screen_changed)
        col_scr.addWidget(self.screen_combo)
        row_v.addLayout(col_scr, 1)

        col_res = QVBoxLayout()
        col_res.addWidget(QLabel(tr("frontend.resolution_label", "Resolution:")))
        self.res_combo = QComboBox()
        for label, val in RESOLUTIONS_LIST:
            self.res_combo.addItem(label, val)
        self.res_combo.currentIndexChanged.connect(self._on_res_changed)
        col_res.addWidget(self.res_combo)
        row_v.addLayout(col_res, 1)

        v_video.addLayout(row_v)

        # Fila de resolución personalizada (se muestra únicamente al seleccionar 'Personalizada...')
        self.custom_res_container = QWidget()
        row_custom = QHBoxLayout(self.custom_res_container)
        row_custom.setContentsMargins(0, 0, 0, 0)
        row_custom.setSpacing(16)

        col_cw = QVBoxLayout()
        col_cw.addWidget(QLabel(tr("frontend.custom_width_label", "📐 Custom width (px):")))
        self.spin_custom_w = QSpinBox()
        self.spin_custom_w.setRange(320, 7680)
        self.spin_custom_w.setSingleStep(10)
        self.spin_custom_w.setSuffix(" px")
        self.spin_custom_w.setValue(1920)
        self.spin_custom_w.valueChanged.connect(self._save_video_settings)
        col_cw.addWidget(self.spin_custom_w)
        row_custom.addLayout(col_cw, 1)

        col_ch = QVBoxLayout()
        col_ch.addWidget(QLabel(tr("frontend.custom_height_label", "Custom height (px):")))
        self.spin_custom_h = QSpinBox()
        self.spin_custom_h.setRange(240, 4320)
        self.spin_custom_h.setSingleStep(10)
        self.spin_custom_h.setSuffix(" px")
        self.spin_custom_h.setValue(1080)
        self.spin_custom_h.valueChanged.connect(self._save_video_settings)
        col_ch.addWidget(self.spin_custom_h)
        row_custom.addLayout(col_ch, 1)

        v_video.addWidget(self.custom_res_container)
        self.custom_res_container.setVisible(False)

        # Fila de transición entre vistas (Menú <-> Lista)
        row_trans = QHBoxLayout()
        row_trans.setSpacing(12)
        row_trans.addWidget(QLabel(tr("frontend.view_transition_label", "View transition (Menus / Lists):")))
        self.transition_combo = QComboBox()
        self.transition_combo.addItem(
            tr("frontend.transition_fade", "Smooth transition (Crossfade 220 ms) — Recommended"),
            "fade",
        )
        self.transition_combo.addItem(tr("frontend.transition_instant", "Instant (No animation)"), "instant")
        self.transition_combo.currentIndexChanged.connect(self._save_video_settings)
        row_trans.addWidget(self.transition_combo, 1)
        row_trans.addStretch(1)
        v_video.addLayout(row_trans)

        # Sub-bloque Fase 4: Motor de Shaders GPU y Partículas Dinámicas
        sep_fx = QFrame()
        sep_fx.setFrameShape(QFrame.HLine)
        sep_fx.setStyleSheet("color: #cbd5e1; margin-top: 6px; margin-bottom: 4px;")
        v_video.addWidget(sep_fx)

        lbl_fx_hdr = QLabel(tr("frontend.gpu_fx_header", "✨ <b>GPU Visual Engine (Retro Shaders & Dynamic Particles)</b>"))
        lbl_fx_hdr.setStyleSheet("color: #38bdf8; font-size: 10pt;")
        v_video.addWidget(lbl_fx_hdr)

        row_fx1 = QHBoxLayout()
        row_fx1.setSpacing(12)

        col_sh = QVBoxLayout()
        col_sh.addWidget(QLabel(tr("frontend.shader_preset_label", "<b>Retro Shader:</b>")))
        self.shader_preset_combo = QComboBox()
        self.shader_preset_combo.addItem(
            tr("frontend.shader_follow_layout", "Follow Layout settings (Recommended)"),
            "layout",
        )
        for key, label in get_shader_presets():
            self.shader_preset_combo.addItem(label, key)
        self.shader_preset_combo.currentIndexChanged.connect(self._save_video_settings)
        col_sh.addWidget(self.shader_preset_combo)
        row_fx1.addLayout(col_sh, 1)

        col_tg = QVBoxLayout()
        col_tg.addWidget(QLabel(tr("frontend.shader_target_label", "<b>Shader Target:</b>")))
        self.shader_target_combo = QComboBox()
        self.shader_target_combo.addItem(tr("frontend.target_follow_layout", "Follow Layout target"), "layout")
        for key, label in get_shader_targets():
            self.shader_target_combo.addItem(label, key)
        self.shader_target_combo.currentIndexChanged.connect(self._save_video_settings)
        col_tg.addWidget(self.shader_target_combo)
        row_fx1.addLayout(col_tg, 1)

        v_video.addLayout(row_fx1)

        row_fx2 = QHBoxLayout()
        row_fx2.setSpacing(12)

        col_pt = QVBoxLayout()
        col_pt.addWidget(QLabel(tr("frontend.particles_label", "<b>Ambient Particles:</b>")))
        self.particle_preset_combo = QComboBox()
        self.particle_preset_combo.addItem(tr("frontend.particles_follow_layout", "Follow Layout particles"), "layout")
        for key, label in get_particle_presets():
            self.particle_preset_combo.addItem(label, key)
        self.particle_preset_combo.currentIndexChanged.connect(self._save_video_settings)
        col_pt.addWidget(self.particle_preset_combo)
        row_fx2.addLayout(col_pt, 1)

        col_perf = QVBoxLayout()
        col_perf.addWidget(QLabel(tr("frontend.effects_perf_label", "<b>GPU/CPU Performance Profile:</b>")))
        self.effects_perf_combo = QComboBox()
        for key, label in get_effects_perf_profiles():
            self.effects_perf_combo.addItem(label, key)
        self.effects_perf_combo.currentIndexChanged.connect(self._save_video_settings)
        col_perf.addWidget(self.effects_perf_combo)
        row_fx2.addLayout(col_perf, 1)

        v_video.addLayout(row_fx2)

        row_fx3 = QHBoxLayout()
        row_fx3.setSpacing(12)
        col_rb = QVBoxLayout()
        col_rb.addWidget(QLabel(tr("frontend.render_backend_label", "<b>Frontend Render Engine:</b>")))
        self.render_backend_combo = QComboBox()
        self.render_backend_combo.setToolTip(
            tr(
                "frontend.render_backend_tip",
                "Accelerates themes, video snaps, retro shaders, warps, and 2x2 collage directly on OpenGL GPU "
                "(with automatic CPU fallback if OpenGL is unavailable).",
            )
        )
        for key, label in get_render_backend_profiles():
            self.render_backend_combo.addItem(label, key)
        self.render_backend_combo.currentIndexChanged.connect(self._save_video_settings)
        col_rb.addWidget(self.render_backend_combo)
        row_fx3.addLayout(col_rb, 1)
        row_fx3.addStretch(1)
        v_video.addLayout(row_fx3)

        page_video_layout.addWidget(grp_video)
        page_video_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_video_container))

        # -------------------------------------------------------------
        # PESTAÑA 4: Pantalla de Bienvenida (Splash Screen de Video)
        # -------------------------------------------------------------
        page_splash_container = QWidget()
        page_splash_layout = QVBoxLayout(page_splash_container)
        page_splash_layout.setContentsMargins(20, 18, 20, 18)
        page_splash_layout.setSpacing(14)

        grp_splash = QGroupBox(tr("frontend.grp_splash", "🎬 Splash Screen (Video Intro)"))
        v_splash = QVBoxLayout(grp_splash)
        v_splash.setSpacing(12)

        self.chk_splash = QCheckBox(tr("frontend.chk_splash", "Play intro video when starting the Frontend"))
        self.chk_splash.setStyleSheet("font-weight: 500; font-size: 10pt;")
        self.chk_splash.toggled.connect(self._on_splash_toggled)
        v_splash.addWidget(self.chk_splash)

        self.splash_container = QWidget()
        v_splash_box = QVBoxLayout(self.splash_container)
        v_splash_box.setContentsMargins(0, 0, 0, 0)
        v_splash_box.setSpacing(8)

        v_splash_box.addWidget(QLabel(tr("frontend.splash_path_label", "<b>Video file path (.mp4, .mkv, .webm, etc.):</b>")))

        row_splash_path = QHBoxLayout()
        self.splash_path_edit = QLineEdit()
        self.splash_path_edit.setPlaceholderText(tr("frontend.splash_path_placeholder", "Ex: splash/splash-1920x1080.mp4"))
        self.splash_path_edit.textChanged.connect(self._save_splash_settings)
        row_splash_path.addWidget(self.splash_path_edit, 1)

        btn_browse_splash = QPushButton(tr("frontend.browse_btn", "Browse…"))
        btn_browse_splash.clicked.connect(self._browse_splash_video)
        row_splash_path.addWidget(btn_browse_splash)

        btn_test_splash = QPushButton(tr("frontend.test_video_btn", "▶ Test video"))
        btn_test_splash.clicked.connect(self._test_splash_video)
        row_splash_path.addWidget(btn_test_splash)

        v_splash_box.addLayout(row_splash_path)

        lbl_splash_hint = QLabel(
            tr(
                "frontend.splash_hint",
                "💡 <i>The video will play fullscreen when starting the Frontend before entering the library. "
                "Any key, gamepad button, or mouse click will skip it immediately to enter directly.</i>",
            )
        )
        lbl_splash_hint.setStyleSheet("color: #718096; font-size: 8.5pt;")
        lbl_splash_hint.setWordWrap(True)
        v_splash_box.addWidget(lbl_splash_hint)

        v_splash.addWidget(self.splash_container)
        self.splash_container.setVisible(False)

        page_splash_layout.addWidget(grp_splash)
        page_splash_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_splash_container))

        # -------------------------------------------------------------
        # PESTAÑA 5: Salvapantallas (Screensaver)
        # -------------------------------------------------------------
        page_ss_container = QWidget()
        page_ss_layout = QVBoxLayout(page_ss_container)
        page_ss_layout.setContentsMargins(20, 18, 20, 18)
        page_ss_layout.setSpacing(14)

        grp_screensaver = QGroupBox(tr("frontend.grp_screensaver", "💤 Screensaver"))
        v_ss = QVBoxLayout(grp_screensaver)
        v_ss.setSpacing(14)

        self.chk_screensaver = QCheckBox(tr("frontend.chk_screensaver", "Enable screensaver after inactivity"))
        self.chk_screensaver.setStyleSheet("font-weight: 500; font-size: 10pt;")
        self.chk_screensaver.toggled.connect(self._on_screensaver_toggled)
        v_ss.addWidget(self.chk_screensaver)

        self.screensaver_container = QWidget()
        v_ss_box = QVBoxLayout(self.screensaver_container)
        v_ss_box.setContentsMargins(0, 0, 0, 0)
        v_ss_box.setSpacing(14)

        # Fila 1: Tiempo de inactividad y Arte superpuesto
        row_ss_1 = QHBoxLayout()
        row_ss_1.setSpacing(16)

        col_time = QVBoxLayout()
        col_time.addWidget(QLabel(tr("frontend.ss_timeout_label", "<b>Inactivity timeout to activate:</b>")))
        self.spin_ss_timeout = QSpinBox()
        self.spin_ss_timeout.setRange(1, 120)
        self.spin_ss_timeout.setValue(3)
        self.spin_ss_timeout.setSuffix(tr("frontend.minutes_suffix", " minutes"))
        self.spin_ss_timeout.setMinimumHeight(32)
        self.spin_ss_timeout.valueChanged.connect(self._save_screensaver_settings)
        col_time.addWidget(self.spin_ss_timeout)
        row_ss_1.addLayout(col_time, 1)

        col_art = QVBoxLayout()
        col_art.addWidget(QLabel(tr("frontend.ss_overlay_label", "<b>Overlay artwork:</b>")))
        self.combo_ss_overlay = QComboBox()
        self.combo_ss_overlay.setMinimumHeight(32)
        self.combo_ss_overlay.addItem(tr("frontend.ss_overlay_wheel", "Game Wheel / Logo"), "wheel")
        self.combo_ss_overlay.addItem(tr("frontend.ss_overlay_flyer", "Promotional flyer"), "flyer")
        self.combo_ss_overlay.addItem(tr("frontend.ss_overlay_marquee", "Marquee"), "marquee")
        self.combo_ss_overlay.addItem(tr("frontend.ss_overlay_none", "None (video / image only)"), "none")
        self.combo_ss_overlay.currentIndexChanged.connect(self._save_screensaver_settings)
        col_art.addWidget(self.combo_ss_overlay)
        row_ss_1.addLayout(col_art, 1)

        col_blank = QVBoxLayout()
        col_blank.addWidget(QLabel(tr("frontend.ss_blank_label", "<b>Deep power-off (Black screen):</b>")))
        self.spin_ss_blank = QSpinBox()
        self.spin_ss_blank.setRange(0, 360)
        self.spin_ss_blank.setValue(60)
        self.spin_ss_blank.setSpecialValueText(tr("frontend.disabled_value", "Disabled"))
        self.spin_ss_blank.setSuffix(tr("frontend.minutes_suffix", " minutes"))
        self.spin_ss_blank.setMinimumHeight(32)
        self.spin_ss_blank.valueChanged.connect(self._save_screensaver_settings)
        col_blank.addWidget(self.spin_ss_blank)
        row_ss_1.addLayout(col_blank, 1)

        v_ss_box.addLayout(row_ss_1)

        # Fila 2: Modos visuales activos
        v_ss_box.addWidget(QLabel(tr("frontend.ss_modes_label", "<b>Allowed visual modes (weighted random rotation):</b>")))
        row_modes = QHBoxLayout()
        row_modes.setSpacing(16)

        self.chk_ss_basic = QCheckBox(tr("frontend.ss_mode_basic", "Single video (Basic Movie)"))
        self.chk_ss_basic.toggled.connect(self._save_screensaver_settings)
        row_modes.addWidget(self.chk_ss_basic)

        self.chk_ss_movie_collage = QCheckBox(tr("frontend.ss_mode_movie_collage", "2x2 video collage"))
        self.chk_ss_movie_collage.toggled.connect(self._save_screensaver_settings)
        row_modes.addWidget(self.chk_ss_movie_collage)

        self.chk_ss_image_collage = QCheckBox(tr("frontend.ss_mode_image_collage", "4x4 image collage (100ms)"))
        self.chk_ss_image_collage.toggled.connect(self._save_screensaver_settings)
        row_modes.addWidget(self.chk_ss_image_collage)

        self.chk_ss_rgb = QCheckBox(tr("frontend.ss_mode_rgb", "Animated RGB effect"))
        self.chk_ss_rgb.toggled.connect(self._save_screensaver_settings)
        row_modes.addWidget(self.chk_ss_rgb)
        row_modes.addStretch(1)

        v_ss_box.addLayout(row_modes)

        # Fila 3: Opciones multimedia y botón de prueba
        row_ss_extra = QHBoxLayout()
        row_ss_extra.setSpacing(16)

        self.chk_ss_sound = QCheckBox(tr("frontend.ss_sound", "Play video sound"))
        self.chk_ss_sound.toggled.connect(self._save_screensaver_settings)
        row_ss_extra.addWidget(self.chk_ss_sound)

        self.chk_ss_preserve_ar = QCheckBox(tr("frontend.ss_preserve_ar", "Preserve original aspect ratio (no stretching)"))
        self.chk_ss_preserve_ar.toggled.connect(self._save_screensaver_settings)
        row_ss_extra.addWidget(self.chk_ss_preserve_ar)
        row_ss_extra.addStretch(1)

        self.btn_test_screensaver = QPushButton(tr("frontend.test_screensaver_btn", "▶ Test screensaver"))
        self.btn_test_screensaver.setMinimumHeight(32)
        self.btn_test_screensaver.clicked.connect(self._test_screensaver)
        row_ss_extra.addWidget(self.btn_test_screensaver)

        v_ss_box.addLayout(row_ss_extra)

        lbl_ss_hint = QLabel(
            tr(
                "frontend.ss_hint",
                "💡 <i>Pressing any key, moving the mouse, or touching the gamepad immediately resumes the frontend. "
                "If you press the SELECT action (Enter or Gamepad A), it will jump straight to the game currently shown.</i>",
            )
        )
        lbl_ss_hint.setStyleSheet("color: #718096; font-size: 8.5pt;")
        lbl_ss_hint.setWordWrap(True)
        v_ss_box.addWidget(lbl_ss_hint)

        v_ss.addWidget(self.screensaver_container)
        self.screensaver_container.setVisible(False)

        page_ss_layout.addWidget(grp_screensaver)
        page_ss_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_ss_container))

        # Seleccionar la primera pestaña lateral por defecto
        self.sidebar.setCurrentRow(0)
        body_layout.addWidget(self.stacked_widget, 1)
        outer_layout.addLayout(body_layout, 1)

        # -------------------------------------------------------------
        # BOTÓN DE INICIO DEL FRONTEND (FIJO EN LA PARTE INFERIOR)
        # -------------------------------------------------------------
        btn_bar = QHBoxLayout()
        btn_bar.addStretch(1)

        self.btn_launch = QPushButton(tr("frontend.launch_btn", "▶  LAUNCH FRONTEND IN FULLSCREEN"))
        self.btn_launch.setObjectName("primary")
        self.btn_launch.setMinimumHeight(48)
        self.btn_launch.setMinimumWidth(380)
        self.btn_launch.setStyleSheet("""
            QPushButton#primary {
                background-color: #5d48d9;
                color: #ffffff;
                font-weight: bold;
                font-size: 11pt;
                border-radius: 8px;
                padding: 10px 24px;
            }
            QPushButton#primary:hover {
                background-color: #6d58ea;
            }
        """)
        self.btn_launch.clicked.connect(self._on_launch_clicked)
        btn_bar.addWidget(self.btn_launch)
        btn_bar.addStretch(1)

        outer_layout.addLayout(btn_bar)

    # -----------------------------------------------------------------
    # CARGA Y ACTUALIZACIÓN DE DATOS
    # -----------------------------------------------------------------
    def refresh_data(self):
        """Actualiza todas las listas, menús y configuraciones desde la base de datos."""
        self._updating = True
        try:
            lists = self.db.get_lists(with_counts=True)

            # 1. Selector de inicio
            self.startup_combo.clear()
            saved_startup = self.db.get_setting("frontend_startup_list", "")
            target_idx = 0

            for idx, r in enumerate(lists):
                lid = r["id"]
                name = r["name"]
                is_menu = (r["list_type"] == "menu") if "list_type" in r.keys() else False
                is_filtered = (r["list_type"] == "filtered") if "list_type" in r.keys() else False

                no_plat = tr("frontend.no_platform", "No platform")
                if is_menu:
                    sub_count = len(self.db.get_menu_items(lid))
                    text = tr(
                        "frontend.startup_item_menu",
                        "🧭 [System Menu]  {name}  ({count} linked systems)",
                        name=name,
                        count=sub_count,
                    )
                elif is_filtered:
                    g_count = r.get("game_count", 0)
                    plat = r.get("platform") or no_plat
                    text = tr(
                        "frontend.startup_item_filtered",
                        "⚡ [Filtered List]  {name}  ({count} games) — {platform}",
                        name=name,
                        count=g_count,
                        platform=plat,
                    )
                else:
                    g_count = r.get("game_count", 0)
                    plat = r.get("platform") or no_plat
                    text = tr(
                        "frontend.startup_item_list",
                        "🎮 [Game List]  {name}  ({count} games) — {platform}",
                        name=name,
                        count=g_count,
                        platform=plat,
                    )

                self.startup_combo.addItem(text, lid)
                if str(lid) == str(saved_startup):
                    target_idx = idx

            if self.startup_combo.count() > 0:
                self.startup_combo.setCurrentIndex(target_idx)

            # 2. Selector de menús
            self.menu_selector_combo.clear()
            menu_lists = [r for r in lists if ("list_type" in r.keys() and r["list_type"] == "menu")]

            for m in menu_lists:
                sub_count = len(self.db.get_menu_items(m["id"]))
                self.menu_selector_combo.addItem(
                    tr(
                        "frontend.menu_selector_item",
                        "🧭 {name} ({count} systems)",
                        name=m["name"],
                        count=sub_count,
                    ),
                    m["id"],
                )

            if not menu_lists:
                self.menu_selector_combo.addItem(
                    tr("frontend.no_menus_created", "No system menus created"),
                    None,
                )
                self.menu_selector_combo.setEnabled(False)
            else:
                self.menu_selector_combo.setEnabled(True)

            # 3. Cargar video settings
            curr_mode = self.db.get_setting("video_mode", "fullscreen")
            idx_mode = self.mode_combo.findData(curr_mode)
            if idx_mode >= 0:
                self.mode_combo.setCurrentIndex(idx_mode)

            try:
                mon_idx = int(self.db.get_setting("video_monitor", "0"))
            except (ValueError, TypeError):
                mon_idx = 0
            if 0 <= mon_idx < self.screen_combo.count():
                self.screen_combo.setCurrentIndex(mon_idx)

            curr_res = self.db.get_setting("video_resolution", "system")
            if curr_res == "native":
                curr_res = "system"
            idx_res = self.res_combo.findData(curr_res)
            if idx_res >= 0:
                self.res_combo.setCurrentIndex(idx_res)
            else:
                idx_cust = self.res_combo.findData("custom")
                if idx_cust >= 0:
                    self.res_combo.setCurrentIndex(idx_cust)

            try:
                custom_w = int(self.db.get_setting("video_custom_width", "1920") or "1920")
                custom_h = int(self.db.get_setting("video_custom_height", "1080") or "1080")
            except (ValueError, TypeError):
                custom_w, custom_h = 1920, 1080
            self.spin_custom_w.setValue(custom_w)
            self.spin_custom_h.setValue(custom_h)
            self.custom_res_container.setVisible(self.res_combo.currentData() == "custom")
            self._update_system_res_label()

            trans_mode = self.db.get_setting("frontend_view_transition", "fade").strip().lower()
            idx_tr = self.transition_combo.findData(trans_mode)
            if idx_tr >= 0:
                self.transition_combo.setCurrentIndex(idx_tr)

            if hasattr(self, "shader_preset_combo"):
                sh_val = normalize_shader_preset(self.db.get_setting("frontend_shader_preset", "layout"), allow_layout=True)
                idx_sh = self.shader_preset_combo.findData(sh_val)
                if idx_sh >= 0:
                    self.shader_preset_combo.setCurrentIndex(idx_sh)

                raw_tg = self.db.get_setting("frontend_shader_target", "layout").strip().lower()
                tg_val = "layout" if raw_tg in ("", "layout", "auto") else normalize_shader_target(raw_tg)
                idx_tg = self.shader_target_combo.findData(tg_val)
                if idx_tg >= 0:
                    self.shader_target_combo.setCurrentIndex(idx_tg)

                pt_val = normalize_particle_preset(self.db.get_setting("frontend_particle_preset", "layout"), allow_layout=True)
                idx_pt = self.particle_preset_combo.findData(pt_val)
                if idx_pt >= 0:
                    self.particle_preset_combo.setCurrentIndex(idx_pt)

                perf_val = normalize_effects_perf(self.db.get_setting("frontend_effects_perf", "high"))
                idx_pf = self.effects_perf_combo.findData(perf_val)
                if idx_pf >= 0:
                    self.effects_perf_combo.setCurrentIndex(idx_pf)
                self.shader_target_combo.setEnabled(perf_val != "off" and sh_val != "none")

            if hasattr(self, "render_backend_combo"):
                rb_val = normalize_render_backend(self.db.get_setting("frontend_render_backend", "auto"))
                idx_rb = self.render_backend_combo.findData(rb_val)
                if idx_rb >= 0:
                    self.render_backend_combo.setCurrentIndex(idx_rb)

            # 4. Cargar configuración de Splash Screen
            splash_en = self.db.get_setting("frontend_splash_enabled", "false").strip().lower() in ("true", "1", "yes")
            self.chk_splash.setChecked(splash_en)
            self.splash_container.setVisible(splash_en)

            saved_splash = self.db.get_setting("frontend_splash_video", "").strip()
            if not saved_splash:
                from playnexus.ui.splash_screen import resolve_splash_video
                auto_vid = resolve_splash_video(self.db)
                if auto_vid:
                    try:
                        saved_splash = str(auto_vid.relative_to(APP_DIR)).replace("\\", "/")
                    except ValueError:
                        saved_splash = str(auto_vid).replace("\\", "/")
            self.splash_path_edit.setText(saved_splash)

            # 5. Cargar configuración de Salvapantallas (Screensaver)
            ss_en = self.db.get_setting("screensaver_enabled", "true").strip().lower() in ("true", "1", "yes")
            self.chk_screensaver.setChecked(ss_en)
            self.screensaver_container.setVisible(ss_en)

            try:
                ss_timeout = int(self.db.get_setting("screensaver_timeout", "3") or "3")
            except (ValueError, TypeError):
                ss_timeout = 3
            self.spin_ss_timeout.setValue(ss_timeout)

            overlay_val = self.db.get_setting("screensaver_overlay_art", "wheel")
            idx_ov = self.combo_ss_overlay.findData(overlay_val)
            if idx_ov >= 0:
                self.combo_ss_overlay.setCurrentIndex(idx_ov)

            try:
                blank_time = int(self.db.get_setting("screensaver_blank_time", "60") or "60")
            except (ValueError, TypeError):
                blank_time = 60
            self.spin_ss_blank.setValue(blank_time)

            self.chk_ss_basic.setChecked(self.db.get_setting("screensaver_mode_basic_movie", "true").strip().lower() in ("true", "1", "yes"))
            self.chk_ss_movie_collage.setChecked(self.db.get_setting("screensaver_mode_movie_collage", "true").strip().lower() in ("true", "1", "yes"))
            self.chk_ss_image_collage.setChecked(self.db.get_setting("screensaver_mode_image_collage", "true").strip().lower() in ("true", "1", "yes"))
            self.chk_ss_rgb.setChecked(self.db.get_setting("screensaver_mode_rgb_movie", "true").strip().lower() in ("true", "1", "yes"))

            self.chk_ss_sound.setChecked(self.db.get_setting("screensaver_sound", "true").strip().lower() in ("true", "1", "yes"))
            self.chk_ss_preserve_ar.setChecked(self.db.get_setting("screensaver_preserve_ar", "false").strip().lower() in ("true", "1", "yes"))

        finally:
            self._updating = False

        self._sync_startup_item_details()
        self._refresh_sublists_table()

    def _on_startup_list_changed(self, index: int):
        if self._updating:
            return
        lid = self.startup_combo.currentData()
        if lid is not None:
            self.db.set_setting("frontend_startup_list", str(lid))

        self._sync_startup_item_details()

        # Si el inicio seleccionado es un menú, sincronizar el selector de menú
        row = self.db.get_list(lid)
        if row and ("list_type" in row.keys() and row["list_type"] == "menu"):
            idx = self.menu_selector_combo.findData(lid)
            if idx >= 0 and self.menu_selector_combo.currentIndex() != idx:
                self._updating = True
                self.menu_selector_combo.setCurrentIndex(idx)
                self._updating = False
                self._refresh_sublists_table()

    def _sync_startup_item_details(self):
        lid = self.startup_combo.currentData()
        if lid is None:
            self.startup_info_label.setText(tr("frontend.no_list_selected", "No list selected."))
            return

        row = self.db.get_list(lid)
        if not row:
            return

        # Sincronizar combo de layout del inicio (Detalles no se permite en frontend)
        curr_layout = row["layout"] or "Wheel"
        if curr_layout == "Detalles":
            curr_layout = "Wheel"
        self.startup_layout_combo.blockSignals(True)
        idx = self.startup_layout_combo.findText(curr_layout)
        if idx >= 0:
            self.startup_layout_combo.setCurrentIndex(idx)
        else:
            self.startup_layout_combo.setCurrentText(curr_layout)
        self.startup_layout_combo.blockSignals(False)

        is_menu = (row["list_type"] == "menu") if "list_type" in row.keys() else False
        if is_menu:
            sub_items = self.db.get_menu_items(lid)
            self.startup_info_label.setText(
                tr(
                    "frontend.startup_info_menu",
                    "🧭 <b>System Menu:</b> This item contains <b>{count}</b> linked systems. "
                    "When starting the frontend it will show the <i>{layout}</i> layout, and upon entering any of its systems "
                    "it will show the layout configured below in the systems table.",
                    count=len(sub_items),
                    layout=curr_layout,
                )
            )
        else:
            g_count = self.db.count_games(lid)
            self.startup_info_label.setText(
                tr(
                    "frontend.startup_info_list",
                    "🎮 <b>Game List:</b> Contains <b>{count}</b> games. "
                    "When starting the frontend it will directly show this list with the <i>{layout}</i> layout.",
                    count=g_count,
                    layout=curr_layout,
                )
            )

    def _on_startup_layout_changed(self, new_layout: str):
        if self._updating:
            return
        lid = self.startup_combo.currentData()
        if lid is not None and new_layout:
            self.db.update_list(lid, layout=new_layout)
            self.layout_changed.emit(lid, new_layout)
            self._sync_startup_item_details()

    def _on_menu_selector_changed(self, index: int):
        if self._updating:
            return
        self._refresh_sublists_table()

    def _refresh_sublists_table(self):
        """Llena la tabla de sub-listas para el menú actualmente seleccionado."""
        menu_id = self.menu_selector_combo.currentData()
        if menu_id is None:
            self.sublists_table.setRowCount(0)
            self.sublists_table.setVisible(False)
            self.empty_menu_label.setText(
                tr("frontend.empty_menu_none_selected", "No System Menu selected.")
            )
            self.empty_menu_label.setVisible(True)
            return

        sub_items = self.db.get_menu_items(menu_id)
        if not sub_items:
            self.sublists_table.setRowCount(0)
            self.sublists_table.setVisible(False)
            self.empty_menu_label.setText(
                tr(
                    "frontend.empty_menu_no_linked",
                    "This menu currently has no linked systems. You can add them by editing the menu in the Library.",
                )
            )
            self.empty_menu_label.setVisible(True)
            return

        self.empty_menu_label.setVisible(False)
        self.sublists_table.setVisible(True)
        available_layouts = get_available_layouts(for_frontend=True)

        with paused_table_sorting(self.sublists_table, reenable=True):
            self.sublists_table.clearContents()
            self.sublists_table.setRowCount(len(sub_items))

            for row_idx, item in enumerate(sub_items):
                item_id = item["id"]
                name = item["name"]
                platform = item.get("platform") or "—"
                game_count = self.db.count_games(item_id)
                current_layout = item.get("layout") or "Wheel"
                if current_layout == "Detalles":
                    current_layout = "Wheel"

                # 0. Nombre
                name_item = SortableTableWidgetItem(f"🎮  {name}", sort_key=name.lower())
                name_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.sublists_table.setItem(row_idx, 0, name_item)

                # 1. Plataforma
                plat_item = SortableTableWidgetItem(platform)
                plat_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.sublists_table.setItem(row_idx, 1, plat_item)

                # 2. Juegos
                count_item = SortableTableWidgetItem(
                    tr("frontend.table_game_count", "{count} games", count=game_count),
                    sort_key=int(game_count),
                )
                count_item.setTextAlignment(Qt.AlignCenter)
                count_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.sublists_table.setItem(row_idx, 2, count_item)

                # 3. Combo de diseño visual (ítem subyacente para ordenación por diseño)
                lay_sort_item = SortableTableWidgetItem(current_layout)
                lay_sort_item.setForeground(Qt.transparent)
                lay_sort_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.sublists_table.setItem(row_idx, 3, lay_sort_item)

                layout_combo = QComboBox()
                layout_combo.addItems(available_layouts)
                idx_lay = layout_combo.findText(current_layout)
                if idx_lay >= 0:
                    layout_combo.setCurrentIndex(idx_lay)
                else:
                    layout_combo.setCurrentText(current_layout)

                # Conectar guardado inmediato al cambiar
                layout_combo.currentTextChanged.connect(
                    lambda new_l, sid=item_id: self._on_sublist_layout_changed(sid, new_l)
                )
                self.sublists_table.setCellWidget(row_idx, 3, layout_combo)

                # 4. Emulador
                emu_id = item.get("default_emulator_id")
                emu_name = tr("frontend.no_emulator", "No emulator")
                if emu_id:
                    emu_data = self.db.get_emulator(emu_id)
                    if emu_data:
                        emu_name = emu_data.get("name") or tr("frontend.assigned_emulator", "Assigned")
                emu_item = SortableTableWidgetItem(emu_name)
                emu_item.setForeground(Qt.gray)
                emu_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.sublists_table.setItem(row_idx, 4, emu_item)

    def _on_sublist_layout_changed(self, sub_list_id: int, new_layout: str):
        if self._updating or not new_layout:
            return
        self.db.update_list(sub_list_id, layout=new_layout)
        self.layout_changed.emit(sub_list_id, new_layout)

    def _on_res_changed(self):
        is_custom = (self.res_combo.currentData() == "custom")
        self.custom_res_container.setVisible(is_custom)
        self._save_video_settings()

    def _on_screen_changed(self):
        self._update_system_res_label()
        self._save_video_settings()

    def _update_system_res_label(self):
        screens = QGuiApplication.screens()
        mon_idx = self.screen_combo.currentData()
        if screens and isinstance(mon_idx, int) and 0 <= mon_idx < len(screens):
            scr = screens[mon_idx]
        else:
            scr = QGuiApplication.primaryScreen()

        if scr:
            geo = scr.geometry()
            rate = int(round(scr.refreshRate())) if scr.refreshRate() > 0 else 60
            text = tr(
                "frontend.res_system_detail",
                "System resolution ({width} x {height} @ {rate}Hz — {name})",
                width=geo.width(),
                height=geo.height(),
                rate=rate,
                name=scr.name(),
            )
        else:
            text = tr("frontend.res_system_native", "System resolution (Native monitor)")

        if self.res_combo.count() > 0 and self.res_combo.itemData(0) == "system":
            self.res_combo.setItemText(0, text)

    def _save_video_settings(self):
        if self._updating:
            return
        mode = self.mode_combo.currentData()
        mon = self.screen_combo.currentData()
        res = self.res_combo.currentData()

        if mode is not None:
            self.db.set_setting("video_mode", str(mode))
        if mon is not None:
            self.db.set_setting("video_monitor", str(mon))
            self.db.set_setting("target_screen", str(mon))
        if res is not None:
            self.db.set_setting("video_resolution", str(res))
        if hasattr(self, "spin_custom_w") and hasattr(self, "spin_custom_h"):
            self.db.set_setting("video_custom_width", str(self.spin_custom_w.value()))
            self.db.set_setting("video_custom_height", str(self.spin_custom_h.value()))
        if hasattr(self, "transition_combo"):
            self.db.set_setting("frontend_view_transition", str(self.transition_combo.currentData() or "fade"))
        if hasattr(self, "shader_preset_combo"):
            sh_sel = str(self.shader_preset_combo.currentData() or "layout")
            tg_sel = str(self.shader_target_combo.currentData() or "layout")
            pt_sel = str(self.particle_preset_combo.currentData() or "layout")
            pf_sel = str(self.effects_perf_combo.currentData() or "high")
            self.db.set_setting("frontend_shader_preset", sh_sel)
            self.db.set_setting("frontend_shader_target", tg_sel)
            self.db.set_setting("frontend_particle_preset", pt_sel)
            self.db.set_setting("frontend_effects_perf", pf_sel)
            self.shader_target_combo.setEnabled(pf_sel != "off" and sh_sel != "none")
        if hasattr(self, "render_backend_combo"):
            rb_sel = normalize_render_backend(self.render_backend_combo.currentData())
            self.db.set_setting("frontend_render_backend", rb_sel)

    def _on_splash_toggled(self, checked: bool):
        self.splash_container.setVisible(checked)
        if checked and not self.splash_path_edit.text().strip():
            from playnexus.ui.splash_screen import resolve_splash_video
            auto_vid = resolve_splash_video(self.db)
            if auto_vid:
                try:
                    rel = str(auto_vid.relative_to(APP_DIR)).replace("\\", "/")
                except ValueError:
                    rel = str(auto_vid).replace("\\", "/")
                self.splash_path_edit.setText(rel)
        self._save_splash_settings()

    def _save_splash_settings(self):
        if self._updating:
            return
        enabled = self.chk_splash.isChecked()
        video_path = self.splash_path_edit.text().strip()
        self.db.set_setting("frontend_splash_enabled", "true" if enabled else "false")
        self.db.set_setting("frontend_splash_video", video_path)

    def _browse_splash_video(self):
        splash_dir = APP_DIR / "splash"
        start_dir = str(splash_dir if splash_dir.is_dir() else APP_DIR)
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("frontend.browse_splash_title", "Select splash video"),
            start_dir,
            tr(
                "frontend.browse_splash_filter",
                "Video files (*.mp4 *.mkv *.avi *.webm *.mov *.wmv);;All files (*.*)",
            ),
        )
        if path:
            p = Path(path)
            try:
                rel = p.relative_to(APP_DIR)
                self.splash_path_edit.setText(str(rel).replace("\\", "/"))
            except ValueError:
                self.splash_path_edit.setText(str(p).replace("\\", "/"))

    def _test_splash_video(self):
        path = self.splash_path_edit.text().strip()
        from playnexus.ui.splash_screen import resolve_splash_video, VideoSplashScreen
        video_file = resolve_splash_video(self.db, path)
        if not video_file or not video_file.is_file():
            QMessageBox.warning(
                self,
                tr("frontend.video_not_found_title", "Video not found"),
                tr("frontend.video_not_found_msg", "No video file was found at the specified path."),
            )
            return
        geo = None
        mon_idx = self.screen_combo.currentData()
        screens = QGuiApplication.screens()
        if screens and isinstance(mon_idx, int) and 0 <= mon_idx < len(screens):
            geo = screens[mon_idx].geometry()
        elif screens:
            geo = screens[0].geometry()

        self._test_splash = VideoSplashScreen(video_file, target_geo=geo, db=self.db)
        self._test_splash.showFullScreen()
        self._test_splash.raise_()
        self._test_splash.activateWindow()
        self._test_splash.start_playback()

    def _on_screensaver_toggled(self, checked: bool):
        self.screensaver_container.setVisible(checked)
        self._save_screensaver_settings()

    def _save_screensaver_settings(self):
        if self._updating:
            return
        self.db.set_setting("screensaver_enabled", "true" if self.chk_screensaver.isChecked() else "false")
        self.db.set_setting("screensaver_timeout", str(self.spin_ss_timeout.value()))
        self.db.set_setting("screensaver_overlay_art", str(self.combo_ss_overlay.currentData()))
        self.db.set_setting("screensaver_blank_time", str(self.spin_ss_blank.value()))
        self.db.set_setting("screensaver_mode_basic_movie", "true" if self.chk_ss_basic.isChecked() else "false")
        self.db.set_setting("screensaver_mode_movie_collage", "true" if self.chk_ss_movie_collage.isChecked() else "false")
        self.db.set_setting("screensaver_mode_image_collage", "true" if self.chk_ss_image_collage.isChecked() else "false")
        self.db.set_setting("screensaver_mode_rgb_movie", "true" if self.chk_ss_rgb.isChecked() else "false")
        self.db.set_setting("screensaver_sound", "true" if self.chk_ss_sound.isChecked() else "false")
        self.db.set_setting("screensaver_preserve_ar", "true" if self.chk_ss_preserve_ar.isChecked() else "false")

    def _test_screensaver(self):
        self._save_screensaver_settings()
        from playnexus.ui.screensaver import ScreensaverWidget
        geo = None
        mon_idx = self.screen_combo.currentData()
        screens = QGuiApplication.screens()
        if screens and isinstance(mon_idx, int) and 0 <= mon_idx < len(screens):
            geo = screens[mon_idx].geometry()
        elif screens:
            geo = screens[0].geometry()

        self._test_ss = ScreensaverWidget(self.db)
        if geo:
            self._test_ss.setGeometry(geo)
        self._test_ss.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self._test_ss.dismiss_requested.connect(self._close_test_screensaver)
        self._test_ss.game_selected_request.connect(lambda gid: self._close_test_screensaver())
        self._test_ss.showFullScreen()
        self._test_ss.raise_()
        self._test_ss.activateWindow()
        self._test_ss.start()

    def _close_test_screensaver(self):
        if hasattr(self, "_test_ss") and self._test_ss:
            self._test_ss.stop_all()
            self._test_ss.close()
            self._test_ss = None

    def _on_launch_clicked(self):
        self._save_video_settings()
        self._save_splash_settings()
        self._save_screensaver_settings()
        self.launch_requested.emit()

