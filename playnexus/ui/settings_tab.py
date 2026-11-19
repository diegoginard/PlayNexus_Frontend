"""
Pestaña de Configuración del Sistema para PlayNexus.
Permite configurar:
1. Asignación interactiva de controles y teclas (Cerrar emulador, subir/bajar ruleta, seleccionar, silenciar, etc.).
2. Comportamiento del emulador (silenciar videos al ejecutar, tecla de cierre global, combo de gamepad).
3. Configuración de pantalla y video del Frontend (modo de pantalla, resolución, monitor y escala).
"""

from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QSize
from PySide6.QtGui import QFont, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QCheckBox, QComboBox,
    QSpinBox, QDialog, QMessageBox, QFrame, QScrollArea, QAbstractItemView,
    QListWidget, QListWidgetItem, QStackedWidget
)
from playnexus.i18n import (
    discover_languages,
    get_lang_dir,
    restart_current_application,
    set_language,
    tr,
)
from playnexus.services.controls import (
    ACTIONS_INFO, get_all_bindings, set_binding, reset_default_bindings,
    qt_key_to_name, qt_event_to_shortcut_name,
    get_gamepad_binding, set_gamepad_binding, reset_default_gamepad_bindings
)
from playnexus.services.gamepad import poll_raw_gamepad_inputs
from playnexus.services.emulator_templates import (
    load_emulator_templates, save_emulator_templates, reset_default_templates
)
from playnexus.ui.dialogs import TemplateEditDialog
from playnexus.ui.table_utils import (
    SortableTableWidgetItem,
    configure_details_table,
    paused_table_sorting,
)


def _get_screen_modes() -> list[tuple[str, str]]:
    return [
        (tr("settings.video.mode_fullscreen", "Exclusive Fullscreen"), "fullscreen"),
        (tr("settings.video.mode_borderless", "Borderless Window"), "borderless"),
        (tr("settings.video.mode_windowed", "Standard Windowed Mode"), "windowed"),
    ]


def _get_resolutions_list() -> list[tuple[str, str]]:
    return [
        (tr("settings.video.res_system", "System Resolution (Monitor Native)"), "system"),
        ("3840 x 2160 (4K UHD - 16:9)", "3840x2160"),
        ("2560 x 1440 (2K QHD - 16:9)", "2560x1440"),
        ("1920 x 1080 (Full HD 1080p - 16:9)", "1920x1080"),
        ("1600 x 900 (HD+ - 16:9)", "1600x900"),
        ("1366 x 768 (Laptop HD - 16:9)", "1366x768"),
        ("1360 x 768 (HD Wide - TV / Monitor)", "1360x768"),
        ("1280 x 720 (HD 720p - 16:9)", "1280x720"),
        ("1920 x 1200 (WUXGA - 16:10)", "1920x1200"),
        ("1680 x 1050 (16:10)", "1680x1050"),
        ("1280 x 800 (16:10)", "1280x800"),
        ("1280 x 1024 (SXGA - 5:4)", "1280x1024"),
        ("1024 x 768 (XGA 4:3 CRT / Arcade)", "1024x768"),
        ("800 x 600 (SVGA - 4:3)", "800x600"),
        ("640 x 480 (VGA 4:3 Retro)", "640x480"),
        (tr("settings.video.res_custom", "Custom (define width and height)..."), "custom"),
    ]


def _get_graphics_engines() -> list[tuple[str, str]]:
    return [
        (tr("settings.video.engine_d3d11", "DirectX 11 (Direct3D 11 - Recommended on Windows)"), "d3d11"),
        ("DirectX 12 (Direct3D 12)", "d3d12"),
        (tr("settings.video.engine_opengl", "OpenGL (Cross-platform standard)"), "opengl"),
        (tr("settings.video.engine_vulkan", "Vulkan (High performance)"), "vulkan"),
    ]


SCREEN_MODES = _get_screen_modes()
RESOLUTIONS_LIST = _get_resolutions_list()
GRAPHICS_ENGINES = _get_graphics_engines()


class KeyCaptureDialog(QDialog):
    """
    Diálogo modal interactivo para capturar una tecla o combinación presionada por el usuario.
    """
    def __init__(self, action_name: str, parent=None):
        super().__init__(parent)
        self.action_name = action_name
        self.captured_key_name: str | None = None

        self.setWindowTitle(tr("settings.key_dlg.title", "Assign Key or Shortcut"))
        self.setFixedSize(460, 240)
        self.setModal(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1d27;
                border: 2px solid #5d48d9;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        lbl_title = QLabel(tr("settings.key_dlg.assigning_for", "Assigning key for:"))
        lbl_title.setStyleSheet("color: #9aa5b8; font-size: 10pt;")
        layout.addWidget(lbl_title)

        lbl_action = QLabel(f"<b>{action_name}</b>")
        lbl_action.setStyleSheet("color: #ffffff; font-size: 13pt;")
        layout.addWidget(lbl_action)

        self.key_box = QFrame()
        self.key_box.setStyleSheet("""
            QFrame {
                background-color: #242938;
                border: 2px dashed #7866ed;
                border-radius: 8px;
                padding: 14px;
            }
        """)
        kb_layout = QVBoxLayout(self.key_box)
        self.status_label = QLabel(tr("settings.key_dlg.prompt", "Press a key on the keyboard..."))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #e2e8f0; font-size: 11pt; font-weight: bold;")
        kb_layout.addWidget(self.status_label)
        layout.addWidget(self.key_box)

        hint = QLabel(tr("settings.key_dlg.hint", "Press any key or shortcut (e.g., Escape, Space, Enter, Arrows, Letters, Ctrl+Q, Alt+F4...)"))
        hint.setStyleSheet("color: #718096; font-size: 8.5pt;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        btn_cancel = QPushButton(tr("common.cancel", "Cancel"))
        btn_cancel.setFocusPolicy(Qt.NoFocus)
        btn_cancel.clicked.connect(self._safe_reject)
        layout.addWidget(btn_cancel)

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()
        self.activateWindow()
        try:
            self.grabKeyboard()
        except Exception:
            pass

    def hideEvent(self, event):
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        super().hideEvent(event)

    def _safe_reject(self):
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self.reject()

    def event(self, event):
        # Interceptar pulsaciones de tecla y ShortcutOverride antes de que Qt las consuma
        if event.type() == QEvent.ShortcutOverride:
            event.accept()
            return True
        if event.type() == QEvent.KeyPress:
            self.keyPressEvent(event)
            return True
        if event.type() == QEvent.KeyRelease:
            self.keyReleaseEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        # Si solo se presionó una tecla modificadora sola (Ctrl, Alt, Shift, Meta)
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            mod_names = []
            if (modifiers & Qt.ControlModifier) or key == Qt.Key_Control:
                mod_names.append("Ctrl")
            if (modifiers & Qt.AltModifier) or key == Qt.Key_Alt:
                mod_names.append("Alt")
            if (modifiers & Qt.ShiftModifier) or key == Qt.Key_Shift:
                mod_names.append("Shift")
            if (modifiers & Qt.MetaModifier) or key == Qt.Key_Meta:
                mod_names.append("Win")
            self.status_label.setText(f"{' + '.join(mod_names)} + ...")
            self.status_label.setStyleSheet("color: #93c5fd; font-size: 11pt; font-weight: bold;")
            event.accept()
            return

        name = qt_event_to_shortcut_name(event)
        self.captured_key_name = name
        self.status_label.setText(tr("settings.key_dlg.assigned", "✓ Key assigned: {name}", name=name))
        self.status_label.setStyleSheet("color: #4ade80; font-size: 12pt; font-weight: bold;")
        event.accept()

        try:
            self.releaseKeyboard()
        except Exception:
            pass
        QTimer.singleShot(160, self.accept)

    def keyReleaseEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            modifiers = event.modifiers()
            mod_names = []
            if modifiers & Qt.ControlModifier:
                mod_names.append("Ctrl")
            if modifiers & Qt.AltModifier:
                mod_names.append("Alt")
            if modifiers & Qt.ShiftModifier:
                mod_names.append("Shift")
            if modifiers & Qt.MetaModifier:
                mod_names.append("Win")
            if mod_names:
                self.status_label.setText(f"{' + '.join(mod_names)} + ...")
                self.status_label.setStyleSheet("color: #93c5fd; font-size: 11pt; font-weight: bold;")
            else:
                self.status_label.setText(tr("settings.key_dlg.prompt", "Press a key on the keyboard..."))
                self.status_label.setStyleSheet("color: #e2e8f0; font-size: 11pt; font-weight: bold;")
            event.accept()
            return
        super().keyReleaseEvent(event)


class GamepadCaptureDialog(QDialog):
    """
    Diálogo modal interactivo para capturar un botón o combinación de mando / joystick.
    """
    def __init__(self, action_name: str, parent=None):
        super().__init__(parent)
        self.action_name = action_name
        self.captured_button_name: str | None = None

        self.setWindowTitle(tr("settings.pad_dlg.title", "Assign Controller / Gamepad Button"))
        self.setFixedSize(460, 240)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1d27;
                border: 2px solid #5d48d9;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        lbl_title = QLabel(tr("settings.pad_dlg.assigning_for", "Assigning controller button for:"))
        lbl_title.setStyleSheet("color: #9aa5b8; font-size: 10pt;")
        layout.addWidget(lbl_title)

        lbl_action = QLabel(f"<b>{action_name}</b>")
        lbl_action.setStyleSheet("color: #ffffff; font-size: 13pt;")
        layout.addWidget(lbl_action)

        self.key_box = QFrame()
        self.key_box.setStyleSheet("""
            QFrame {
                background-color: #242938;
                border: 2px dashed #7866ed;
                border-radius: 8px;
                padding: 14px;
            }
        """)
        kb_layout = QVBoxLayout(self.key_box)
        self.status_label = QLabel(tr("settings.pad_dlg.prompt", "Press a button, D-pad, or stick on the controller..."))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #e2e8f0; font-size: 11pt; font-weight: bold;")
        kb_layout.addWidget(self.status_label)
        layout.addWidget(self.key_box)

        hint = QLabel(tr("settings.pad_dlg.hint", "Supports Xbox, PlayStation, 8BitDo and generic USB controllers (A, B, X, Y, LB, RB, D-Pad, etc.)"))
        hint.setStyleSheet("color: #718096; font-size: 8.5pt;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        btn_cancel = QPushButton(tr("common.cancel", "Cancel"))
        btn_cancel.clicked.connect(self._safe_reject)
        layout.addWidget(btn_cancel)

        # Temporizador de sondeo de mandos en tiempo real
        self._timer = QTimer(self)
        self._timer.setInterval(28)
        self._timer.timeout.connect(self._poll_inputs)
        self._timer.start()

    def _poll_inputs(self):
        inputs = poll_raw_gamepad_inputs()
        if not inputs:
            return

        if "Back" in inputs and "Start" in inputs:
            btn_name = "Back+Start"
        elif "Back" in inputs and len(inputs) > 1:
            others = [x for x in inputs if x != "Back"]
            btn_name = f"Back+{others[0]}"
        elif "Start" in inputs and len(inputs) > 1:
            others = [x for x in inputs if x != "Start"]
            btn_name = f"Start+{others[0]}"
        else:
            btn_name = next(iter(inputs))

        self.captured_button_name = btn_name
        self._timer.stop()
        self.status_label.setText(tr("settings.pad_dlg.captured", "✓ Button captured: {btn}", btn=btn_name))
        self.status_label.setStyleSheet("color: #4ade80; font-size: 12pt; font-weight: bold;")
        QTimer.singleShot(180, self.accept)

    def _safe_reject(self):
        if self._timer.isActive():
            self._timer.stop()
        self.reject()

    def closeEvent(self, event):
        if self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)


class SystemSettingsWidget(QWidget):
    """
    Panel integrado de Configuración del Sistema para PlayNexus.
    """
    settings_saved = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(18, 16, 18, 16)
        outer_layout.setSpacing(14)

        # Encabezado principal superior
        header_card = QFrame()
        header_card.setStyleSheet("background-color: #1b1e2a; border: 1px solid #2a3143; border-radius: 8px; padding: 12px;")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(14, 10, 14, 10)
        h_layout.setSpacing(4)

        title = QLabel(tr("settings.header.title", "⚙ System Settings"))
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        h_layout.addWidget(title)

        desc = QLabel(
            tr(
                "settings.header.desc",
                "Manage keyboard and controller controls, emulator launch behavior, "
                "frontend display and video, quick emulator templates, and interface language."
            )
        )
        desc.setStyleSheet("color: #9aa5b8; font-size: 9.5pt;")
        desc.setWordWrap(True)
        h_layout.addWidget(desc)
        outer_layout.addWidget(header_card)

        # Cuerpo central: Barra de pestañas lateral a la izquierda y páginas a la derecha
        body_layout = QHBoxLayout()
        body_layout.setSpacing(16)

        # -------------------------------------------------------------
        # Barra lateral de navegación (Sidebar Tabs) a la izquierda
        # -------------------------------------------------------------
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("settings_sidebar")
        self.sidebar.setFixedWidth(275)
        self.sidebar.setFocusPolicy(Qt.NoFocus)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.sidebar.setStyleSheet("""
            QListWidget#settings_sidebar {
                background-color: #161822;
                border: 1px solid #2a3143;
                border-radius: 8px;
                padding: 6px;
                outline: none;
            }
            QListWidget#settings_sidebar::item {
                color: #a0aec0;
                padding: 12px 14px;
                border-radius: 6px;
                font-size: 10pt;
                font-weight: 500;
                margin-bottom: 4px;
            }
            QListWidget#settings_sidebar::item:hover {
                background-color: #222638;
                color: #ffffff;
            }
            QListWidget#settings_sidebar::item:selected {
                background-color: #5d48d9;
                color: #ffffff;
                font-weight: bold;
            }
        """)

        sidebar_items = [
            (
                tr("settings.tab.controls", "⌨️🎮  Controls & Gamepad"),
                tr("settings.tab.controls_tip", "Keyboard key and controller button bindings"),
            ),
            (
                tr("settings.tab.emulators", "🕹️  Emulator Behavior"),
                tr("settings.tab.emulators_tip", "Audio, exit shortcut, and bezel overlay options"),
            ),
            (
                tr("settings.tab.video", "🖥️  Frontend Display & Video"),
                tr("settings.tab.video_tip", "Screen mode, resolution, monitor, and FPS overlay"),
            ),
            (
                tr("settings.tab.templates", "🧩  Quick Emulator Templates"),
                tr("settings.tab.templates_tip", "Manage quick emulator presets and templates"),
            ),
            (
                tr("settings.tab.language", "🌐  Language / Idioma"),
                tr("settings.tab.language_tip", "Interface language selection (lang/*.txt)"),
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

        # Helper para crear scroll area homogéneo para cada sub-pestaña
        def _make_tab_scroll(inner_widget: QWidget) -> QScrollArea:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setStyleSheet("QScrollArea { border: 1px solid #2a3143; border-radius: 8px; background-color: #161822; }")
            sa.setWidget(inner_widget)
            return sa

        # -------------------------------------------------------------
        # Pestaña 1: Configuración de teclas y mando
        # -------------------------------------------------------------
        page_controls_container = QWidget()
        page_controls_layout = QVBoxLayout(page_controls_container)
        page_controls_layout.setContentsMargins(20, 18, 20, 18)
        page_controls_layout.setSpacing(14)

        grp_controls = QGroupBox(tr("settings.controls.group", "🎮 Controls & Gamepad Configuration"))
        v_controls = QVBoxLayout(grp_controls)
        v_controls.setSpacing(12)

        lbl_c_info = QLabel(
            tr(
                "settings.controls.info",
                "Configure keyboard keys and controller/gamepad buttons for each action. "
                "Both input methods work simultaneously at all times in PlayNexus."
            )
        )
        lbl_c_info.setStyleSheet("color: #a0aec0; font-size: 9.5pt;")
        lbl_c_info.setWordWrap(True)
        v_controls.addWidget(lbl_c_info)

        self.controls_table = QTableWidget()
        self.controls_table.setColumnCount(4)
        self.controls_table.setHorizontalHeaderLabels([
            tr("settings.controls.col_action", "Action"),
            tr("settings.controls.col_desc", "Description"),
            tr("settings.controls.col_key", "Key (Keyboard)"),
            tr("settings.controls.col_pad", "Controller / Gamepad"),
        ])
        configure_details_table(
            self.controls_table,
            col_widths=(190, 320, 170, 170),
            hide_vertical_header=True,
        )
        self.controls_table.verticalHeader().setDefaultSectionSize(36)
        v_controls.addWidget(self.controls_table)

        row_c_btns = QHBoxLayout()
        btn_reset_keys = QPushButton(tr("settings.controls.reset_btn", "↺ Reset default controls (Keyboard & Controllers)"))
        btn_reset_keys.clicked.connect(self._reset_controls_defaults)
        row_c_btns.addWidget(btn_reset_keys)
        row_c_btns.addStretch(1)
        v_controls.addLayout(row_c_btns)

        page_controls_layout.addWidget(grp_controls)
        page_controls_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_controls_container))

        # -------------------------------------------------------------
        # Pestaña 2: Comportamiento de emuladores
        # -------------------------------------------------------------
        page_emu_container = QWidget()
        page_emu_layout = QVBoxLayout(page_emu_container)
        page_emu_layout.setContentsMargins(20, 18, 20, 18)
        page_emu_layout.setSpacing(14)

        grp_emu = QGroupBox(tr("settings.emu.group", "🕹 Emulator Behavior"))
        v_emu = QVBoxLayout(grp_emu)
        v_emu.setSpacing(14)

        self.chk_mute_video = QCheckBox(
            tr("settings.emu.mute_video", "Automatically mute video snap audio when launching an emulator")
        )
        self.chk_mute_video.setStyleSheet("font-weight: 500; font-size: 10pt;")
        v_emu.addWidget(self.chk_mute_video)

        lbl_mute_hint = QLabel(
            tr("settings.emu.mute_hint", "When exiting the emulator, video snap sound in the layout resumes immediately.")
        )
        lbl_mute_hint.setStyleSheet("color: #718096; font-size: 9pt; margin-left: 24px;")
        lbl_mute_hint.setWordWrap(True)
        v_emu.addWidget(lbl_mute_hint)

        self.chk_global_exit = QCheckBox(
            tr("settings.emu.global_exit", "Allow closing the running emulator using the assigned key (e.g., Escape)")
        )
        self.chk_global_exit.setStyleSheet("font-weight: 500; font-size: 10pt;")
        v_emu.addWidget(self.chk_global_exit)

        lbl_exit_hint = QLabel(
            tr("settings.emu.exit_hint", "Globally monitors the configured key on Windows and cleanly closes the emulator when pressed.")
        )
        lbl_exit_hint.setStyleSheet("color: #718096; font-size: 9pt; margin-left: 24px;")
        lbl_exit_hint.setWordWrap(True)
        v_emu.addWidget(lbl_exit_hint)

        self.chk_gamepad_exit = QCheckBox(
            tr("settings.emu.gamepad_exit", "Allow closing the emulator with controller / gamepad combo (Back + Start)")
        )
        self.chk_gamepad_exit.setStyleSheet("font-weight: 500; font-size: 10pt;")
        v_emu.addWidget(self.chk_gamepad_exit)

        self.chk_bezel_overlay = QCheckBox(
            tr("settings.emu.bezel_overlay", "Enable Bezel Overlays (Foreground overlay above the emulator)")
        )
        self.chk_bezel_overlay.setStyleSheet("font-weight: 500; font-size: 10pt;")
        v_emu.addWidget(self.chk_bezel_overlay)

        lbl_bezel_hint = QLabel(
            tr(
                "settings.emu.bezel_hint",
                "Overlays the ROM-specific or generic decorative bezel frame on top of the emulator. "
                "You can hide or restore the bezel anytime during emulation using the assigned key or controller button "
                "in the controls table (default F11 or L-Thumb) to freely access emulator menus and options."
            )
        )
        lbl_bezel_hint.setStyleSheet("color: #718096; font-size: 9pt; margin-left: 24px;")
        lbl_bezel_hint.setWordWrap(True)
        v_emu.addWidget(lbl_bezel_hint)

        page_emu_layout.addWidget(grp_emu)
        page_emu_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_emu_container))

        # -------------------------------------------------------------
        # Pestaña 3: Pantalla y video del frontend
        # -------------------------------------------------------------
        page_video_container = QWidget()
        page_video_layout = QVBoxLayout(page_video_container)
        page_video_layout.setContentsMargins(20, 18, 20, 18)
        page_video_layout.setSpacing(14)

        grp_video = QGroupBox(tr("settings.video.group", "🖥 Frontend Display & Video"))
        v_video = QVBoxLayout(grp_video)
        v_video.setSpacing(14)

        row_v1 = QHBoxLayout()
        row_v1.setSpacing(16)

        col1 = QVBoxLayout()
        col1.addWidget(QLabel(tr("settings.video.screen_mode", "Display mode:")))
        self.mode_combo = QComboBox()
        for label, val in _get_screen_modes():
            self.mode_combo.addItem(label, val)
        col1.addWidget(self.mode_combo)
        row_v1.addLayout(col1, 1)

        col2 = QVBoxLayout()
        col2.addWidget(QLabel(tr("settings.video.resolution", "Resolution:")))
        self.res_combo = QComboBox()
        for label, val in _get_resolutions_list():
            self.res_combo.addItem(label, val)
        self.res_combo.currentIndexChanged.connect(self._on_res_changed)
        col2.addWidget(self.res_combo)
        row_v1.addLayout(col2, 1)

        v_video.addLayout(row_v1)

        # Fila de resolución personalizada (se muestra únicamente al seleccionar 'Personalizada...')
        self.custom_res_container = QWidget()
        row_custom = QHBoxLayout(self.custom_res_container)
        row_custom.setContentsMargins(0, 0, 0, 0)
        row_custom.setSpacing(16)

        col_cw = QVBoxLayout()
        col_cw.addWidget(QLabel(tr("settings.video.custom_w", "📐 Custom width (px):")))
        self.spin_custom_w = QSpinBox()
        self.spin_custom_w.setRange(320, 7680)
        self.spin_custom_w.setSingleStep(10)
        self.spin_custom_w.setSuffix(" px")
        self.spin_custom_w.setValue(1920)
        col_cw.addWidget(self.spin_custom_w)
        row_custom.addLayout(col_cw, 1)

        col_ch = QVBoxLayout()
        col_ch.addWidget(QLabel(tr("settings.video.custom_h", "Custom height (px):")))
        self.spin_custom_h = QSpinBox()
        self.spin_custom_h.setRange(240, 4320)
        self.spin_custom_h.setSingleStep(10)
        self.spin_custom_h.setSuffix(" px")
        self.spin_custom_h.setValue(1080)
        col_ch.addWidget(self.spin_custom_h)
        row_custom.addLayout(col_ch, 1)

        v_video.addWidget(self.custom_res_container)
        self.custom_res_container.setVisible(False)

        row_v2 = QHBoxLayout()
        row_v2.setSpacing(16)

        col3 = QVBoxLayout()
        col3.addWidget(QLabel(tr("settings.video.driver", "Graphics engine / Video API:")))
        self.driver_combo = QComboBox()
        for label, val in _get_graphics_engines():
            self.driver_combo.addItem(label, val)
        col3.addWidget(self.driver_combo)
        row_v2.addLayout(col3, 1)

        col4 = QVBoxLayout()
        col4.addWidget(QLabel(tr("settings.video.monitor", "Target monitor:")))
        self.screen_combo = QComboBox()
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        primary_tag = tr("settings.video.monitor_primary", " [Primary]")
        for idx, scr in enumerate(screens):
            geo = scr.geometry()
            tag = primary_tag if scr == primary else ""
            self.screen_combo.addItem(
                tr(
                    "settings.video.monitor_item",
                    "Monitor {num}: {w}x{h} ({name}){tag}",
                    num=idx + 1, w=geo.width(), h=geo.height(), name=scr.name(), tag=tag,
                ),
                idx,
            )
        self.screen_combo.currentIndexChanged.connect(self._on_screen_changed)
        col4.addWidget(self.screen_combo)
        row_v2.addLayout(col4, 1)

        v_video.addLayout(row_v2)

        lbl_driver_hint = QLabel(
            tr(
                "settings.video.driver_hint",
                "💡 <i>Note: Changes to the graphics engine (DirectX 11, DirectX 12, OpenGL, or Vulkan) will apply the next time you start PlayNexus.</i>"
            )
        )
        lbl_driver_hint.setStyleSheet("color: #9aa5b8; font-size: 8.5pt;")
        lbl_driver_hint.setWordWrap(True)
        v_video.addWidget(lbl_driver_hint)

        self.chk_show_fps = QCheckBox(tr("settings.video.show_fps", "Show FPS and performance counter on frontend (Overlay)"))
        self.chk_show_fps.setStyleSheet("font-weight: 500; font-size: 10pt; margin-top: 6px;")
        v_video.addWidget(self.chk_show_fps)

        lbl_fps_hint = QLabel(
            tr(
                "settings.video.fps_hint",
                "Displays real-time frames per second (FPS), render time, resolution, and graphics engine. "
                "You can toggle it here or anytime using the assigned key or button in the controls table."
            )
        )
        lbl_fps_hint.setStyleSheet("color: #718096; font-size: 8.5pt; margin-left: 24px;")
        lbl_fps_hint.setWordWrap(True)
        v_video.addWidget(lbl_fps_hint)

        page_video_layout.addWidget(grp_video)
        page_video_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_video_container))

        # -------------------------------------------------------------
        # Pestaña 4: Plantilla rápida para emuladores
        # -------------------------------------------------------------
        page_tmpl_container = QWidget()
        page_tmpl_layout = QVBoxLayout(page_tmpl_container)
        page_tmpl_layout.setContentsMargins(20, 18, 20, 18)
        page_tmpl_layout.setSpacing(14)

        grp_templates = QGroupBox(tr("settings.tmpl.group", "🧩 Quick Emulator Templates"))
        v_templates = QVBoxLayout(grp_templates)
        v_templates.setSpacing(12)

        lbl_tmpl_desc = QLabel(
            tr(
                "settings.tmpl.desc",
                "Manage the templates shown in the «Quick Template» dropdown when adding or editing emulators. "
                "You can create your own presets with common executables, arguments, and platforms."
            )
        )
        lbl_tmpl_desc.setStyleSheet("color: #a0aec0; font-size: 9.5pt;")
        lbl_tmpl_desc.setWordWrap(True)
        v_templates.addWidget(lbl_tmpl_desc)

        self.templates_table = QTableWidget()
        self.templates_table.setColumnCount(9)
        self.templates_table.setHorizontalHeaderLabels([
            tr("settings.tmpl.col_name", "Name"),
            tr("settings.tmpl.col_exec", "Executable"),
            tr("settings.tmpl.col_args", "Arguments"),
            tr("settings.tmpl.col_platform", "Platform"),
            tr("settings.tmpl.col_delay", "Delay"),
            tr("settings.tmpl.col_fade", "Fade"),
            tr("settings.tmpl.col_load_in", "Load (In)"),
            tr("settings.tmpl.col_load_out", "Exit (Out)"),
            tr("settings.tmpl.col_desc", "Description"),
        ])
        configure_details_table(
            self.templates_table,
            col_widths=(160, 140, 180, 130, 80, 80, 90, 90, 200),
        )
        self.templates_table.setMinimumHeight(240)
        self.templates_table.doubleClicked.connect(self._edit_selected_template)
        v_templates.addWidget(self.templates_table)

        row_t_btns = QHBoxLayout()
        btn_add_tmpl = QPushButton(tr("settings.tmpl.add_btn", "➕ Add template…"))
        btn_add_tmpl.clicked.connect(self._add_template)
        row_t_btns.addWidget(btn_add_tmpl)

        btn_edit_tmpl = QPushButton(tr("settings.tmpl.edit_btn", "✏ Edit template…"))
        btn_edit_tmpl.clicked.connect(self._edit_selected_template)
        row_t_btns.addWidget(btn_edit_tmpl)

        btn_del_tmpl = QPushButton(tr("settings.tmpl.del_btn", "🗑 Delete template"))
        btn_del_tmpl.clicked.connect(self._delete_selected_template)
        row_t_btns.addWidget(btn_del_tmpl)

        row_t_btns.addStretch()

        btn_reset_tmpl = QPushButton(tr("settings.tmpl.reset_btn", "↺ Restore default templates"))
        btn_reset_tmpl.clicked.connect(self._reset_templates)
        row_t_btns.addWidget(btn_reset_tmpl)

        v_templates.addLayout(row_t_btns)

        page_tmpl_layout.addWidget(grp_templates)
        page_tmpl_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_tmpl_container))

        # -------------------------------------------------------------
        # Pestaña 5: Idioma / Language (archivos .txt en carpeta lang/)
        # -------------------------------------------------------------
        page_lang_container = QWidget()
        page_lang_layout = QVBoxLayout(page_lang_container)
        page_lang_layout.setContentsMargins(20, 18, 20, 18)
        page_lang_layout.setSpacing(14)

        grp_lang = QGroupBox(tr("settings.lang.group", "🌐 Interface Language"))
        v_lang = QVBoxLayout(grp_lang)
        v_lang.setSpacing(12)

        lbl_lang_desc = QLabel(
            tr(
                "settings.lang.desc",
                "Select the application language. PlayNexus automatically loads all .txt language files placed in the 'lang/' folder."
            )
        )
        lbl_lang_desc.setStyleSheet("color: #a0aec0; font-size: 9.5pt;")
        lbl_lang_desc.setWordWrap(True)
        v_lang.addWidget(lbl_lang_desc)

        row_lang = QHBoxLayout()
        row_lang.setSpacing(12)
        row_lang.addWidget(QLabel(tr("settings.lang.label", "Active language:")))

        self.lang_combo = QComboBox()
        self.lang_combo.setMinimumWidth(260)
        row_lang.addWidget(self.lang_combo, 1)

        btn_reload_langs = QPushButton(tr("settings.lang.reload_btn", "🔄 Reload languages"))
        btn_reload_langs.clicked.connect(lambda: self._refresh_languages_combo(keep_selection=True))
        row_lang.addWidget(btn_reload_langs)
        v_lang.addLayout(row_lang)

        lbl_lang_hint = QLabel(
            tr(
                "settings.lang.hint",
                "💡 To add a new language, copy 'lang/en.txt' as 'lang/<code>.txt' (UTF-8), set '_lang_code' and '_lang_name', translate the values, and click Reload languages.\nFolder: {folder}",
                folder=str(get_lang_dir()),
            )
        )
        lbl_lang_hint.setStyleSheet("color: #9aa5b8; font-size: 8.5pt;")
        lbl_lang_hint.setWordWrap(True)
        lbl_lang_hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v_lang.addWidget(lbl_lang_hint)

        page_lang_layout.addWidget(grp_lang)
        page_lang_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_lang_container))
        self._refresh_languages_combo(keep_selection=False)

        # Seleccionar la primera pestaña lateral por defecto
        self.sidebar.setCurrentRow(0)
        body_layout.addWidget(self.stacked_widget, 1)
        outer_layout.addLayout(body_layout, 1)

        # -------------------------------------------------------------
        # Barra inferior fija de guardado para todas las secciones
        # -------------------------------------------------------------
        save_bar = QHBoxLayout()
        save_bar.addStretch(1)

        self.save_btn = QPushButton(tr("settings.save_btn", "💾 Save System Settings"))
        self.save_btn.setObjectName("primary")
        self.save_btn.setMinimumHeight(42)
        self.save_btn.setMinimumWidth(280)
        self.save_btn.clicked.connect(self.save_all)
        save_bar.addWidget(self.save_btn)

        outer_layout.addLayout(save_bar)

        self.refresh_controls_table()
        self.refresh_templates_table()
        self.load_settings()

    def refresh_controls_table(self):
        """Llena la tabla compacta de asignación de teclas y mandos."""
        bindings = get_all_bindings(self.db)
        with paused_table_sorting(self.controls_table, reenable=True):
            self.controls_table.clearContents()
            self.controls_table.setRowCount(len(bindings))

            for row, info in enumerate(bindings):
                item_name = SortableTableWidgetItem(info["name"])
                item_name.setFont(QFont("Segoe UI", 9, QFont.Bold))
                item_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.controls_table.setItem(row, 0, item_name)

                item_desc = SortableTableWidgetItem(info["desc"])
                item_desc.setForeground(Qt.gray)
                item_desc.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.controls_table.setItem(row, 1, item_desc)

                # Teclado (Botón interactivo + ítem subyacente para ordenar por tecla)
                unassigned_txt = tr("settings.controls.unassigned", "Unassigned")
                key_text = info["key"] if info["key"] else unassigned_txt
                key_sort_item = SortableTableWidgetItem(key_text)
                key_sort_item.setForeground(Qt.transparent)
                key_sort_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.controls_table.setItem(row, 2, key_sort_item)
                btn_key = QPushButton(f"⌨  {key_text}")
                btn_key.setCursor(Qt.PointingHandCursor)
                btn_key.setToolTip(tr("settings.controls.key_tip", "Click to change the assigned key"))
                btn_key.setStyleSheet("""
                    QPushButton {
                        background-color: #242938;
                        color: #a5b4fc;
                        border: 1px solid #4f46e5;
                        border-radius: 6px;
                        padding: 4px 14px;
                        font-weight: bold;
                        font-size: 9pt;
                    }
                    QPushButton:hover {
                        background-color: #3730a3;
                        color: #ffffff;
                        border-color: #6366f1;
                    }
                """)
                btn_key.clicked.connect(lambda checked=False, i=info: self._prompt_key_change(i["id"], i["name"]))
                self.controls_table.setCellWidget(row, 2, btn_key)

                # Mando / Joystick (Botón interactivo + ítem subyacente para ordenar por mando)
                pad_text = info["pad"] if info["pad"] else unassigned_txt
                pad_sort_item = SortableTableWidgetItem(pad_text)
                pad_sort_item.setForeground(Qt.transparent)
                pad_sort_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.controls_table.setItem(row, 3, pad_sort_item)
                btn_pad = QPushButton(f"🎮  {pad_text}")
                btn_pad.setCursor(Qt.PointingHandCursor)
                btn_pad.setToolTip(tr("settings.controls.pad_tip", "Click to change the assigned controller button or combo"))
                btn_pad.setStyleSheet("""
                    QPushButton {
                        background-color: #242938;
                        color: #38bdf8;
                        border: 1px solid #0284c7;
                        border-radius: 6px;
                        padding: 4px 14px;
                        font-weight: bold;
                        font-size: 9pt;
                    }
                    QPushButton:hover {
                        background-color: #0369a1;
                        color: #ffffff;
                        border-color: #38bdf8;
                    }
                """)
                btn_pad.clicked.connect(lambda checked=False, i=info: self._prompt_gamepad_change(i["id"], i["name"]))
                self.controls_table.setCellWidget(row, 3, btn_pad)

        # Ajustar altura de la tabla para que quepan todas las filas sin scrollbar interno vertical
        header_h = self.controls_table.horizontalHeader().height() or 28
        row_h = self.controls_table.verticalHeader().defaultSectionSize() or 36
        total_h = header_h + (len(bindings) * row_h) + 6
        self.controls_table.setFixedHeight(total_h)

    def _prompt_key_change(self, action_id: str, action_name: str):
        dialog = KeyCaptureDialog(action_name, self)
        if dialog.exec() and dialog.captured_key_name:
            new_key = dialog.captured_key_name
            set_binding(self.db, action_id, new_key)
            self.refresh_controls_table()
            self.settings_saved.emit()

    def _prompt_gamepad_change(self, action_id: str, action_name: str):
        dialog = GamepadCaptureDialog(action_name, self)
        if dialog.exec() and dialog.captured_button_name:
            new_pad = dialog.captured_button_name
            set_gamepad_binding(self.db, action_id, new_pad)
            self.refresh_controls_table()
            self.settings_saved.emit()

    def _reset_controls_defaults(self):
        res = QMessageBox.question(
            self,
            tr("settings.controls.reset_title", "Reset Controls"),
            tr("settings.controls.reset_msg", "Do you want to reset all keyboard and controller bindings to their default values?"),
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            reset_default_bindings(self.db)
            reset_default_gamepad_bindings(self.db)
            self.refresh_controls_table()
            self.settings_saved.emit()

    def _refresh_languages_combo(self, keep_selection: bool = True):
        """Recarga la lista de idiomas disponibles escaneando los `.txt` en `lang/`."""
        if not hasattr(self, "lang_combo"):
            return
        prev_code = str(self.lang_combo.currentData() or "").strip().lower() if keep_selection else ""
        if not prev_code and self.db:
            prev_code = str(self.db.get_setting("app_language", "en") or "en").strip().lower()
        self.lang_combo.blockSignals(True)
        self.lang_combo.clear()
        langs = discover_languages()
        if not langs:
            self.lang_combo.addItem("English (en)", "en")
        else:
            for item in langs:
                self.lang_combo.addItem(f"{item['name']} ({item['code']})", item["code"])
        idx = self.lang_combo.findData(prev_code or "en")
        if idx == -1 and self.lang_combo.count() > 0:
            idx = 0
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.blockSignals(False)

    def _on_res_changed(self):
        is_custom = (self.res_combo.currentData() == "custom")
        self.custom_res_container.setVisible(is_custom)

    def _on_screen_changed(self):
        self._update_system_res_label()

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
                "settings.video.res_system_detected",
                "System Resolution ({w} x {h} @ {rate}Hz — {name})",
                w=geo.width(), h=geo.height(), rate=rate, name=scr.name(),
            )
        else:
            text = tr("settings.video.res_system", "System Resolution (Monitor Native)")

        if self.res_combo.count() > 0 and self.res_combo.itemData(0) == "system":
            self.res_combo.setItemText(0, text)

    def refresh_templates_table(self):
        """Llena la tabla de plantillas de emuladores desde el archivo de texto plano."""
        templates = load_emulator_templates()
        with paused_table_sorting(self.templates_table, reenable=True):
            self.templates_table.setRowCount(len(templates))
            for row, t in enumerate(templates):
                item_name = SortableTableWidgetItem(t.get("name", ""))
                item_name.setFont(QFont("Segoe UI", 9, QFont.Bold))
                item_name.setData(Qt.UserRole, row)
                self.templates_table.setItem(row, 0, item_name)

                self.templates_table.setItem(row, 1, SortableTableWidgetItem(t.get("executable", "")))
                self.templates_table.setItem(row, 2, SortableTableWidgetItem(t.get("arguments", "")))
                self.templates_table.setItem(row, 3, SortableTableWidgetItem(t.get("platform", "") or "—"))

                d_raw = t.get("bezel_delay", "0.0")
                f_raw = t.get("bezel_fade", "0.3")
                load_raw = t.get("loading_time", "1.5")
                exit_load_raw = t.get("exit_loading_time", "1.0")
                try:
                    d_val = float(d_raw)
                    d_str = f"{d_val:.1f} s"
                except Exception:
                    d_val = 0.0
                    d_str = "0.0 s"
                try:
                    f_val = float(f_raw)
                    f_str = f"{f_val:.1f} s"
                except Exception:
                    f_val = 0.3
                    f_str = "0.3 s"
                try:
                    load_val = float(load_raw)
                    load_str = f"{load_val:.1f} s"
                except Exception:
                    load_val = 1.5
                    load_str = "1.5 s"
                try:
                    exit_load_val = float(exit_load_raw)
                    exit_load_str = f"{exit_load_val:.1f} s"
                except Exception:
                    exit_load_val = 1.0
                    exit_load_str = "1.0 s"

                item_d = SortableTableWidgetItem(d_str, sort_key=d_val)
                item_d.setTextAlignment(Qt.AlignCenter)
                self.templates_table.setItem(row, 4, item_d)

                item_f = SortableTableWidgetItem(f_str, sort_key=f_val)
                item_f.setTextAlignment(Qt.AlignCenter)
                self.templates_table.setItem(row, 5, item_f)

                item_load = SortableTableWidgetItem(load_str, sort_key=load_val)
                item_load.setTextAlignment(Qt.AlignCenter)
                self.templates_table.setItem(row, 6, item_load)

                item_exit_load = SortableTableWidgetItem(exit_load_str, sort_key=exit_load_val)
                item_exit_load.setTextAlignment(Qt.AlignCenter)
                self.templates_table.setItem(row, 7, item_exit_load)

                item_desc = SortableTableWidgetItem(t.get("description", ""))
                item_desc.setForeground(Qt.gray)
                self.templates_table.setItem(row, 8, item_desc)

    def _selected_template_index(self, visual_row: int) -> int:
        it = self.templates_table.item(visual_row, 0)
        raw_idx = it.data(Qt.UserRole) if it is not None else None
        return int(raw_idx) if raw_idx is not None else visual_row

    def _add_template(self):
        dialog = TemplateEditDialog(self)
        if dialog.exec():
            new_tmpl = dialog.values()
            templates = load_emulator_templates()
            templates.append(new_tmpl)
            save_emulator_templates(templates)
            self.refresh_templates_table()
            QMessageBox.information(
                self,
                tr("settings.tmpl.added_title", "Template Added"),
                tr(
                    "settings.tmpl.added_msg",
                    "The template '{name}' was saved successfully.\nIt is now available in the 'Quick Template' dropdown when adding or editing emulators.",
                    name=new_tmpl["name"],
                ),
            )

    def _edit_selected_template(self):
        selected = self.templates_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(
                self,
                tr("common.select", "Select"),
                tr("settings.tmpl.select_edit_msg", "Please select a template from the table to edit."),
            )
            return
        row_idx = self._selected_template_index(selected[0].row())
        templates = load_emulator_templates()
        if 0 <= row_idx < len(templates):
            curr = templates[row_idx]
            dialog = TemplateEditDialog(self, existing=curr)
            if dialog.exec():
                updated = dialog.values()
                templates[row_idx] = updated
                save_emulator_templates(templates)
                self.refresh_templates_table()

    def _delete_selected_template(self):
        selected = self.templates_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(
                self,
                tr("common.select", "Select"),
                tr("settings.tmpl.select_del_msg", "Please select a template from the table to delete."),
            )
            return
        row_idx = self._selected_template_index(selected[0].row())
        templates = load_emulator_templates()
        if 0 <= row_idx < len(templates):
            target_name = templates[row_idx].get("name", "")
            confirm = QMessageBox.question(
                self,
                tr("common.confirm_delete", "Confirm Deletion"),
                tr("settings.tmpl.delete_confirm", "Do you want to delete the template '{name}'?", name=target_name),
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                templates.pop(row_idx)
                save_emulator_templates(templates)
                self.refresh_templates_table()

    def _reset_templates(self):
        confirm = QMessageBox.question(
            self,
            tr("settings.tmpl.reset_title", "Restore Templates"),
            tr(
                "settings.tmpl.reset_msg",
                "Do you want to restore all quick templates to the official defaults?\n\n(Note: Emulators already registered in your library will not be modified)."
            ),
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            reset_default_templates()
            self.refresh_templates_table()

    def load_settings(self):
        """Carga las opciones de emuladores y pantalla desde la base de datos."""
        if not self.db:
            return

        # Emulador
        self.chk_mute_video.setChecked(self.db.get_setting("emulator_mute_video", "true").lower() == "true")
        self.chk_global_exit.setChecked(self.db.get_setting("emulator_global_exit", "true").lower() == "true")
        self.chk_gamepad_exit.setChecked(self.db.get_setting("emulator_gamepad_exit", "true").lower() == "true")
        self.chk_bezel_overlay.setChecked(self.db.get_setting("emulator_bezel_overlay", "true").lower() == "true")

        # Video
        mode = self.db.get_setting("video_mode", "fullscreen")
        idx_mode = self.mode_combo.findData(mode)
        if idx_mode != -1:
            self.mode_combo.setCurrentIndex(idx_mode)

        res = self.db.get_setting("video_resolution", "system")
        if res == "native":
            res = "system"
        idx_res = self.res_combo.findData(res)
        if idx_res != -1:
            self.res_combo.setCurrentIndex(idx_res)
        else:
            idx_cust = self.res_combo.findData("custom")
            if idx_cust != -1:
                self.res_combo.setCurrentIndex(idx_cust)

        try:
            custom_w = int(self.db.get_setting("video_custom_width", "1920") or "1920")
            custom_h = int(self.db.get_setting("video_custom_height", "1080") or "1080")
        except (ValueError, TypeError):
            custom_w, custom_h = 1920, 1080
        self.spin_custom_w.setValue(custom_w)
        self.spin_custom_h.setValue(custom_h)
        self.custom_res_container.setVisible(self.res_combo.currentData() == "custom")

        driver = self.db.get_setting("video_driver", "d3d11")
        idx_driver = self.driver_combo.findData(driver)
        if idx_driver != -1:
            self.driver_combo.setCurrentIndex(idx_driver)

        target_screen = int(self.db.get_setting("video_monitor", self.db.get_setting("target_screen", "0") or "0") or "0")
        if 0 <= target_screen < self.screen_combo.count():
            self.screen_combo.setCurrentIndex(target_screen)

        self.chk_show_fps.setChecked(self.db.get_setting("video_show_fps", "false").lower() == "true")

        # Idioma
        self._refresh_languages_combo(keep_selection=False)
        lang_code = (self.db.get_setting("app_language", "en") or "en").strip().lower()
        idx_lang = self.lang_combo.findData(lang_code)
        if idx_lang != -1:
            self.lang_combo.setCurrentIndex(idx_lang)

        self._update_system_res_label()
        self.refresh_templates_table()

    def save_all(self):
        """Guarda todas las configuraciones en la base de datos."""
        if not self.db:
            return

        prev_lang = (self.db.get_setting("app_language", "en") or "en").strip().lower()

        # Emulador
        self.db.set_setting("emulator_mute_video", "true" if self.chk_mute_video.isChecked() else "false")
        self.db.set_setting("emulator_global_exit", "true" if self.chk_global_exit.isChecked() else "false")
        self.db.set_setting("emulator_gamepad_exit", "true" if self.chk_gamepad_exit.isChecked() else "false")
        self.db.set_setting("emulator_bezel_overlay", "true" if self.chk_bezel_overlay.isChecked() else "false")

        # Video
        mode = self.mode_combo.currentData()
        self.db.set_setting("video_mode", mode)

        res = self.res_combo.currentData()
        self.db.set_setting("video_resolution", res)
        self.db.set_setting("video_custom_width", str(self.spin_custom_w.value()))
        self.db.set_setting("video_custom_height", str(self.spin_custom_h.value()))

        driver = self.driver_combo.currentData()
        self.db.set_setting("video_driver", driver)

        target_screen = self.screen_combo.currentData()
        mon_str = str(target_screen if target_screen is not None else 0)
        self.db.set_setting("video_monitor", mon_str)
        self.db.set_setting("target_screen", mon_str)

        self.db.set_setting("video_show_fps", "true" if self.chk_show_fps.isChecked() else "false")

        # Idioma
        new_lang = str(self.lang_combo.currentData() or "en").strip().lower()
        self.db.set_setting("app_language", new_lang)
        set_language(new_lang)

        self.settings_saved.emit()

        if new_lang != prev_lang:
            ans = QMessageBox.question(
                self,
                tr("settings.lang.restart_title", "Language Updated"),
                tr(
                    "settings.lang.restart_msg",
                    "The configuration and language were saved successfully.\n\n"
                    "Do you want to restart PlayNexus now to apply the new language across the entire interface?"
                ),
                QMessageBox.Yes | QMessageBox.No,
            )
            if ans == QMessageBox.Yes:
                restart_current_application(self)
                return

        QMessageBox.information(
            self,
            tr("settings.saved_title", "Settings Saved"),
            tr(
                "settings.saved_msg",
                "System, controls, and video settings were saved successfully.\n\n"
                "If you changed the graphics engine, it will take effect the next time you start PlayNexus."
            ),
        )
