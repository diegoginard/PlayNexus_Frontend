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

SCREEN_MODES = [
    ("Pantalla completa exclusiva (Fullscreen)", "fullscreen"),
    ("Ventana sin bordes (Borderless Window)", "borderless"),
    ("Modo ventana estándar", "windowed")
]

RESOLUTIONS_LIST = [
    ("Resolución del sistema (Nativa del monitor)", "system"),
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
    ("Personalizada (definir ancho y alto)...", "custom"),
]

GRAPHICS_ENGINES = [
    ("DirectX 11 (Direct3D 11 - Recomendado en Windows)", "d3d11"),
    ("DirectX 12 (Direct3D 12)", "d3d12"),
    ("OpenGL (Estándar multiplataforma)", "opengl"),
    ("Vulkan (Alto rendimiento)", "vulkan"),
]


class KeyCaptureDialog(QDialog):
    """
    Diálogo modal interactivo para capturar una tecla o combinación presionada por el usuario.
    """
    def __init__(self, action_name: str, parent=None):
        super().__init__(parent)
        self.action_name = action_name
        self.captured_key_name: str | None = None

        self.setWindowTitle("Asignar tecla o atajo")
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

        lbl_title = QLabel("Asignando tecla para:")
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
        self.status_label = QLabel("Presioná una tecla en el teclado...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #e2e8f0; font-size: 11pt; font-weight: bold;")
        kb_layout.addWidget(self.status_label)
        layout.addWidget(self.key_box)

        hint = QLabel("Presioná cualquier tecla o atajo (ej: Escape, Espacio, Enter, Flechas, Letras, Ctrl+Q, Alt+F4...)")
        hint.setStyleSheet("color: #718096; font-size: 8.5pt;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        btn_cancel = QPushButton("Cancelar")
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
        self.status_label.setText(f"✓ Tecla asignada: {name}")
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
                self.status_label.setText("Presioná una tecla en el teclado...")
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

        self.setWindowTitle("Asignar botón de mando / joystick")
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

        lbl_title = QLabel("Asignando botón de mando para:")
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
        self.status_label = QLabel("Presioná un botón, cruceta o palanca en el mando...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #e2e8f0; font-size: 11pt; font-weight: bold;")
        kb_layout.addWidget(self.status_label)
        layout.addWidget(self.key_box)

        hint = QLabel("Soporta mandos Xbox, PlayStation, 8BitDo y genéricos USB (A, B, X, Y, LB, RB, D-Pad, etc.)")
        hint.setStyleSheet("color: #718096; font-size: 8.5pt;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        btn_cancel = QPushButton("Cancelar")
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
        self.status_label.setText(f"✓ Botón capturado: {btn_name}")
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

        title = QLabel("⚙ Configuración del Sistema")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        h_layout.addWidget(title)

        desc = QLabel(
            "Administrá los controles de teclado y joystick, el comportamiento al ejecutar emuladores, "
            "la pantalla y video del frontend, y las plantillas rápidas de emulación."
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
            ("⌨️🎮  Configuración de teclas y mando", "Asignación de teclas y botones de joystick"),
            ("🕹️  Comportamiento de emuladores", "Opciones de audio, salida y bezel overlay"),
            ("🖥️  Pantalla y video del frontend", "Modo de pantalla, resolución, monitor y FPS"),
            ("🧩  Plantilla rápida para emuladores", "Gestión de plantillas y presets de emuladores"),
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

        grp_controls = QGroupBox("🎮 Configuración de Teclas y Mando")
        v_controls = QVBoxLayout(grp_controls)
        v_controls.setSpacing(12)

        lbl_c_info = QLabel(
            "Configurá las teclas del teclado y los botones de mandos / joysticks para cada acción. "
            "Ambos métodos de control funcionan de manera simultánea en todo momento en PlayNexus."
        )
        lbl_c_info.setStyleSheet("color: #a0aec0; font-size: 9.5pt;")
        lbl_c_info.setWordWrap(True)
        v_controls.addWidget(lbl_c_info)

        self.controls_table = QTableWidget()
        self.controls_table.setColumnCount(4)
        self.controls_table.setHorizontalHeaderLabels([
            "Acción", "Descripción", "Tecla (Teclado)", "Mando / Joystick"
        ])
        self.controls_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.controls_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.controls_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.controls_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.controls_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.controls_table.verticalHeader().setVisible(False)
        self.controls_table.verticalHeader().setDefaultSectionSize(36)
        v_controls.addWidget(self.controls_table)

        row_c_btns = QHBoxLayout()
        btn_reset_keys = QPushButton("↺ Restablecer controles predeterminados (Teclado y Mandos)")
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

        grp_emu = QGroupBox("🕹 Comportamiento de Emuladores")
        v_emu = QVBoxLayout(grp_emu)
        v_emu.setSpacing(14)

        self.chk_mute_video = QCheckBox("Silenciar audio de los videos snaps automáticamente al ejecutar un emulador")
        self.chk_mute_video.setStyleSheet("font-weight: 500; font-size: 10pt;")
        v_emu.addWidget(self.chk_mute_video)

        lbl_mute_hint = QLabel("Al salir del emulador, el sonido del video snap en el diseño visual se reanuda de inmediato.")
        lbl_mute_hint.setStyleSheet("color: #718096; font-size: 9pt; margin-left: 24px;")
        lbl_mute_hint.setWordWrap(True)
        v_emu.addWidget(lbl_mute_hint)

        self.chk_global_exit = QCheckBox("Permitir cerrar el emulador en ejecución con la tecla asignada (ej: Escape)")
        self.chk_global_exit.setStyleSheet("font-weight: 500; font-size: 10pt;")
        v_emu.addWidget(self.chk_global_exit)

        lbl_exit_hint = QLabel("Monitorea globalmente en Windows la tecla configurada y cierra el emulador de forma limpia al presionarla.")
        lbl_exit_hint.setStyleSheet("color: #718096; font-size: 9pt; margin-left: 24px;")
        lbl_exit_hint.setWordWrap(True)
        v_emu.addWidget(lbl_exit_hint)

        self.chk_gamepad_exit = QCheckBox("Permitir cerrar el emulador con combo de control / gamepad (Back + Start)")
        self.chk_gamepad_exit.setStyleSheet("font-weight: 500; font-size: 10pt;")
        v_emu.addWidget(self.chk_gamepad_exit)

        self.chk_bezel_overlay = QCheckBox("Activar Bezels superpuestos (Overlay en primer plano sobre el emulador)")
        self.chk_bezel_overlay.setStyleSheet("font-weight: 500; font-size: 10pt;")
        v_emu.addWidget(self.chk_bezel_overlay)

        lbl_bezel_hint = QLabel(
            "Superpone el marco decorativo (bezel) específico de la ROM o el genérico por encima del emulador. "
            "Podés ocultar o restaurar el bezel en cualquier momento durante la emulación usando la tecla o botón asignado "
            "en la tabla de controles (por defecto F11 o L-Thumb) para acceder libremente a menús y opciones del emulador."
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

        grp_video = QGroupBox("🖥 Pantalla y Video del Frontend")
        v_video = QVBoxLayout(grp_video)
        v_video.setSpacing(14)

        row_v1 = QHBoxLayout()
        row_v1.setSpacing(16)

        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Modo de pantalla:"))
        self.mode_combo = QComboBox()
        for label, val in SCREEN_MODES:
            self.mode_combo.addItem(label, val)
        col1.addWidget(self.mode_combo)
        row_v1.addLayout(col1, 1)

        col2 = QVBoxLayout()
        col2.addWidget(QLabel("Resolución:"))
        self.res_combo = QComboBox()
        for label, val in RESOLUTIONS_LIST:
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
        col_cw.addWidget(QLabel("📐 Ancho personalizado (px):"))
        self.spin_custom_w = QSpinBox()
        self.spin_custom_w.setRange(320, 7680)
        self.spin_custom_w.setSingleStep(10)
        self.spin_custom_w.setSuffix(" px")
        self.spin_custom_w.setValue(1920)
        col_cw.addWidget(self.spin_custom_w)
        row_custom.addLayout(col_cw, 1)

        col_ch = QVBoxLayout()
        col_ch.addWidget(QLabel("Alto personalizado (px):"))
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
        col3.addWidget(QLabel("Motor gráfico / API de video:"))
        self.driver_combo = QComboBox()
        for label, val in GRAPHICS_ENGINES:
            self.driver_combo.addItem(label, val)
        col3.addWidget(self.driver_combo)
        row_v2.addLayout(col3, 1)

        col4 = QVBoxLayout()
        col4.addWidget(QLabel("Monitor de destino:"))
        self.screen_combo = QComboBox()
        screens = QGuiApplication.screens()
        primary = QGuiApplication.primaryScreen()
        for idx, scr in enumerate(screens):
            geo = scr.geometry()
            tag = " [Principal]" if scr == primary else ""
            self.screen_combo.addItem(f"Monitor {idx + 1}: {geo.width()}x{geo.height()} ({scr.name()}){tag}", idx)
        self.screen_combo.currentIndexChanged.connect(self._on_screen_changed)
        col4.addWidget(self.screen_combo)
        row_v2.addLayout(col4, 1)

        v_video.addLayout(row_v2)

        lbl_driver_hint = QLabel("💡 <i>Nota: El cambio de motor gráfico (DirectX 11, DirectX 12, OpenGL o Vulkan) se aplicará la próxima vez que inicies PlayNexus.</i>")
        lbl_driver_hint.setStyleSheet("color: #9aa5b8; font-size: 8.5pt;")
        lbl_driver_hint.setWordWrap(True)
        v_video.addWidget(lbl_driver_hint)

        self.chk_show_fps = QCheckBox("Mostrar contador de FPS y rendimiento en el frontend (Overlay)")
        self.chk_show_fps.setStyleSheet("font-weight: 500; font-size: 10pt; margin-top: 6px;")
        v_video.addWidget(self.chk_show_fps)

        lbl_fps_hint = QLabel(
            "Muestra en tiempo real los fotogramas por segundo (FPS), tiempo de render, resolución y motor gráfico. "
            "Podés activarlo/desactivarlo aquí o en cualquier momento mediante la tecla o botón asignado en la tabla de controles."
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

        grp_templates = QGroupBox("🧩 Plantilla Rápida para Emuladores")
        v_templates = QVBoxLayout(grp_templates)
        v_templates.setSpacing(12)

        lbl_tmpl_desc = QLabel(
            "Administrá las plantillas que aparecen en el menú desplegable «Plantilla rápida» al dar de alta o configurar emuladores. "
            "Podés crear tus propios presets con ejecutables, argumentos y plataformas habituales."
        )
        lbl_tmpl_desc.setStyleSheet("color: #a0aec0; font-size: 9.5pt;")
        lbl_tmpl_desc.setWordWrap(True)
        v_templates.addWidget(lbl_tmpl_desc)

        self.templates_table = QTableWidget()
        self.templates_table.setColumnCount(9)
        self.templates_table.setHorizontalHeaderLabels([
            "Nombre", "Ejecutable", "Argumentos", "Plataforma", "Retardo", "Fade", "Carga (In)", "Cierre (Out)", "Descripción"
        ])
        self.templates_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.templates_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.templates_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.templates_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.templates_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.templates_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.templates_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.templates_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.templates_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)
        self.templates_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.templates_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.templates_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.templates_table.setMinimumHeight(240)
        self.templates_table.doubleClicked.connect(self._edit_selected_template)
        v_templates.addWidget(self.templates_table)

        row_t_btns = QHBoxLayout()
        btn_add_tmpl = QPushButton("➕ Agregar plantilla…")
        btn_add_tmpl.clicked.connect(self._add_template)
        row_t_btns.addWidget(btn_add_tmpl)

        btn_edit_tmpl = QPushButton("✏ Editar plantilla…")
        btn_edit_tmpl.clicked.connect(self._edit_selected_template)
        row_t_btns.addWidget(btn_edit_tmpl)

        btn_del_tmpl = QPushButton("🗑 Eliminar plantilla")
        btn_del_tmpl.clicked.connect(self._delete_selected_template)
        row_t_btns.addWidget(btn_del_tmpl)

        row_t_btns.addStretch()

        btn_reset_tmpl = QPushButton("↺ Restaurar plantillas predeterminadas")
        btn_reset_tmpl.clicked.connect(self._reset_templates)
        row_t_btns.addWidget(btn_reset_tmpl)

        v_templates.addLayout(row_t_btns)

        page_tmpl_layout.addWidget(grp_templates)
        page_tmpl_layout.addStretch(1)
        self.stacked_widget.addWidget(_make_tab_scroll(page_tmpl_container))

        # Seleccionar la primera pestaña lateral por defecto
        self.sidebar.setCurrentRow(0)
        body_layout.addWidget(self.stacked_widget, 1)
        outer_layout.addLayout(body_layout, 1)

        # -------------------------------------------------------------
        # Barra inferior fija de guardado para todas las secciones
        # -------------------------------------------------------------
        save_bar = QHBoxLayout()
        save_bar.addStretch(1)

        self.save_btn = QPushButton("💾 Guardar Configuración del Sistema")
        self.save_btn.setObjectName("primary")
        self.save_btn.setMinimumHeight(42)
        self.save_btn.setMinimumWidth(280)
        self.save_btn.clicked.connect(self.save_all)
        save_bar.addWidget(self.save_btn)

        outer_layout.addLayout(save_bar)

        self.refresh_controls_table()
        self.refresh_templates_table()
        self.load_settings()

        self.refresh_controls_table()
        self.refresh_templates_table()
        self.load_settings()

    def refresh_controls_table(self):
        """Llena la tabla compacta de asignación de teclas y mandos."""
        bindings = get_all_bindings(self.db)
        self.controls_table.setRowCount(len(bindings))

        for row, info in enumerate(bindings):
            item_name = QTableWidgetItem(info["name"])
            item_name.setFont(QFont("Segoe UI", 9, QFont.Bold))
            item_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.controls_table.setItem(row, 0, item_name)

            item_desc = QTableWidgetItem(info["desc"])
            item_desc.setForeground(Qt.gray)
            item_desc.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.controls_table.setItem(row, 1, item_desc)

            # Teclado (Botón interactivo que muestra la tecla y abre captura al hacer clic)
            key_text = info['key'] if info['key'] else "Sin asignar"
            btn_key = QPushButton(f"⌨  {key_text}")
            btn_key.setCursor(Qt.PointingHandCursor)
            btn_key.setToolTip("Hacé clic para cambiar la tecla asignada")
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

            # Mando / Joystick (Botón interactivo que muestra el control y abre captura al hacer clic)
            pad_text = info['pad'] if info['pad'] else "Sin asignar"
            btn_pad = QPushButton(f"🎮  {pad_text}")
            btn_pad.setCursor(Qt.PointingHandCursor)
            btn_pad.setToolTip("Hacé clic para cambiar el botón o combo de mando asignado")
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
            "Restablecer controles",
            "¿Deseás restablecer todas las teclas y botones de mandos a sus valores predeterminados?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res == QMessageBox.Yes:
            reset_default_bindings(self.db)
            reset_default_gamepad_bindings(self.db)
            self.refresh_controls_table()
            self.settings_saved.emit()

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
            text = f"Resolución del sistema ({geo.width()} x {geo.height()} @ {rate}Hz — {scr.name()})"
        else:
            text = "Resolución del sistema (Nativa del monitor)"

        if self.res_combo.count() > 0 and self.res_combo.itemData(0) == "system":
            self.res_combo.setItemText(0, text)

    def refresh_templates_table(self):
        """Llena la tabla de plantillas de emuladores desde el archivo de texto plano."""
        templates = load_emulator_templates()
        self.templates_table.setRowCount(len(templates))
        for row, t in enumerate(templates):
            item_name = QTableWidgetItem(t.get("name", ""))
            item_name.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.templates_table.setItem(row, 0, item_name)

            self.templates_table.setItem(row, 1, QTableWidgetItem(t.get("executable", "")))
            self.templates_table.setItem(row, 2, QTableWidgetItem(t.get("arguments", "")))
            self.templates_table.setItem(row, 3, QTableWidgetItem(t.get("platform", "") or "—"))

            d_raw = t.get("bezel_delay", "0.0")
            f_raw = t.get("bezel_fade", "0.3")
            load_raw = t.get("loading_time", "1.5")
            exit_load_raw = t.get("exit_loading_time", "1.0")
            try:
                d_str = f"{float(d_raw):.1f} s"
            except Exception:
                d_str = "0.0 s"
            try:
                f_str = f"{float(f_raw):.1f} s"
            except Exception:
                f_str = "0.3 s"
            try:
                load_str = f"{float(load_raw):.1f} s"
            except Exception:
                load_str = "1.5 s"
            try:
                exit_load_str = f"{float(exit_load_raw):.1f} s"
            except Exception:
                exit_load_str = "1.0 s"

            item_d = QTableWidgetItem(d_str)
            item_d.setTextAlignment(Qt.AlignCenter)
            self.templates_table.setItem(row, 4, item_d)

            item_f = QTableWidgetItem(f_str)
            item_f.setTextAlignment(Qt.AlignCenter)
            self.templates_table.setItem(row, 5, item_f)

            item_load = QTableWidgetItem(load_str)
            item_load.setTextAlignment(Qt.AlignCenter)
            self.templates_table.setItem(row, 6, item_load)

            item_exit_load = QTableWidgetItem(exit_load_str)
            item_exit_load.setTextAlignment(Qt.AlignCenter)
            self.templates_table.setItem(row, 7, item_exit_load)

            item_desc = QTableWidgetItem(t.get("description", ""))
            item_desc.setForeground(Qt.gray)
            self.templates_table.setItem(row, 8, item_desc)

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
                "Plantilla agregada",
                f"La plantilla '{new_tmpl['name']}' fue guardada con éxito.\nYa está disponible en la lista de 'Plantilla rápida' al registrar o editar emuladores."
            )

    def _edit_selected_template(self):
        selected = self.templates_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Seleccionar", "Por favor seleccioná una plantilla de la tabla para editar.")
            return
        row_idx = selected[0].row()
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
            QMessageBox.information(self, "Seleccionar", "Por favor seleccioná una plantilla de la tabla para eliminar.")
            return
        row_idx = selected[0].row()
        templates = load_emulator_templates()
        if 0 <= row_idx < len(templates):
            target_name = templates[row_idx].get("name", "")
            confirm = QMessageBox.question(
                self,
                "Confirmar eliminación",
                f"¿Deseás eliminar la plantilla '{target_name}'?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                templates.pop(row_idx)
                save_emulator_templates(templates)
                self.refresh_templates_table()

    def _reset_templates(self):
        confirm = QMessageBox.question(
            self,
            "Restaurar plantillas",
            "¿Deseás restaurar todas las plantillas rápidas a los valores predeterminados oficiales?\n\n(Nota: Tus emuladores ya registrados en la biblioteca no se modificarán).",
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

        self._update_system_res_label()
        self.refresh_templates_table()

    def save_all(self):
        """Guarda todas las configuraciones en la base de datos."""
        if not self.db:
            return

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

        self.settings_saved.emit()
        QMessageBox.information(
            self,
            "Configuración guardada",
            "La configuración del sistema, controles y video fue guardada exitosamente.\n\n"
            "Si cambiaste el motor gráfico, este se aplicará la próxima vez que inicies PlayNexus."
        )
