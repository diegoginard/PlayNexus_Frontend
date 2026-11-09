from __future__ import annotations

import os
import ast
import re
import types
import shutil
import datetime
import importlib.util
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QSize
from PySide6.QtGui import QIcon, QFont, QColor, QImage, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QSplitter, QTabWidget, QMessageBox, QInputDialog, QFileDialog, QDialog,
    QDialogButtonBox, QFormLayout, QLineEdit, QListWidget, QListWidgetItem,
    QSlider, QFrame, QSizePolicy
)

from playnexus.services.themes import get_layouts_root, get_all_theme_layouts
from playnexus.ui.layout_studio.models import LayoutProject, LayoutElement, CANONICAL_W, CANONICAL_H
from playnexus.ui.layout_studio.templates import (
    TEMPLATES_LIBRARY, generate_layout_code, create_arcade_cabinet_template
)
from playnexus.ui.layout_studio.canvas import LayoutCanvasWidget
from playnexus.ui.layout_studio.inspector import LayoutInspectorWidget
from playnexus.ui.layout_studio.code_editor import LayoutCodeEditorWidget
from playnexus.ui.layout_studio.runtime_hook import (
    get_trimmed_image_info, should_trim_alpha,
    install_studio_overrides, update_studio_overrides,
    extract_elements_from_theme_instance,
    sync_quiet_studio_instance,
    measure_native_layer_bbox,
)


class NewLayoutDialog(QDialog):
    """Diálogo modal para crear un nuevo layout desde una plantilla o en blanco."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo Layout - PlayNexus Studio")
        self.resize(480, 360)
        self.selected_template = "Arcade Cabinet (Clásico)"
        self.layout_name = "Mi Nuevo Layout"

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(self.layout_name)
        form.addRow("Nombre del Layout:", self.name_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("Selecciona una Plantilla Inicial:"))
        self.tpl_list = QListWidget()
        for tpl_name in TEMPLATES_LIBRARY.keys():
            item = QListWidgetItem(f"📐  {tpl_name}")
            item.setData(Qt.UserRole, tpl_name)
            self.tpl_list.addItem(item)
        self.tpl_list.setCurrentRow(0)
        layout.addWidget(self.tpl_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_result(self) -> tuple[str, str]:
        name = self.name_edit.text().strip() or "Nuevo Layout"
        item = self.tpl_list.currentItem()
        tpl = item.data(Qt.UserRole) if item else "Arcade Cabinet (Clásico)"
        return name, tpl


class LayoutStudioWidget(QWidget):
    """
    Pestaña principal de Layout Studio en PlayNexus.
    Permite diseñar visualmente, mover y distorsionar elementos,
    editar código Python en tiempo real y probar layouts antes de producción.
    """
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_project: LayoutProject | None = None
        self.current_list_games: list[dict[str, Any]] = []
        self._is_syncing = False
        self._cached_code: str = ""
        self._pending_code_sync: bool = False

        self._init_ui()
        self._load_lists_and_games()
        self.refresh_layouts_list()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # -------------------------------------------------------------
        # 1. BARRA SUPERIOR DE HERRAMIENTAS (2 FILAS)
        # -------------------------------------------------------------
        # Fila 1: Gestión de Layouts y Herramienta de Edición
        row1_layout = QHBoxLayout()
        row1_layout.setContentsMargins(0, 0, 0, 2)
        row1_layout.setSpacing(10)

        lbl_select = QLabel("🎨 Layout Activo:")
        lbl_select.setStyleSheet("font-weight: bold; color: #cbd5e1;")
        row1_layout.addWidget(lbl_select)

        self.cb_layouts = QComboBox()
        self.cb_layouts.setMinimumWidth(200)
        self.cb_layouts.setMaximumWidth(280)
        self.cb_layouts.setStyleSheet("""
            QComboBox {
                background: #1e293b;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 10px;
            }
        """)
        self.cb_layouts.currentIndexChanged.connect(self._on_layout_combo_changed)
        row1_layout.addWidget(self.cb_layouts)

        self.btn_new = QPushButton("➕ Nuevo Layout")
        self.btn_new.setStyleSheet("""
            QPushButton {
                background: #0284c7;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #0369a1;
            }
        """)
        self.btn_new.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_new.setMinimumWidth(self.btn_new.sizeHint().width() + 14)
        self.btn_new.clicked.connect(self._on_new_layout)
        row1_layout.addWidget(self.btn_new)

        self.btn_save = QPushButton("💾 Guardar Cambios")
        self.btn_save.setToolTip("Guarda los cambios en theme_layout.py generando previamente una copia de seguridad en /backups")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: #16a34a;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #15803d;
            }
        """)
        self.btn_save.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_save.setMinimumWidth(self.btn_save.sizeHint().width() + 14)
        self.btn_save.clicked.connect(self._on_save_layout)
        row1_layout.addWidget(self.btn_save)

        self.btn_save_as = QPushButton("💾 Guardar Como...")
        self.btn_save_as.setStyleSheet("""
            QPushButton {
                background: #334155;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #475569;
            }
        """)
        self.btn_save_as.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_save_as.setMinimumWidth(self.btn_save_as.sizeHint().width() + 14)
        self.btn_save_as.clicked.connect(self._on_save_as_layout)
        row1_layout.addWidget(self.btn_save_as)

        self.btn_reset = QPushButton("🔄 Restablecer Cambios")
        self.btn_reset.setToolTip("Descarta las modificaciones y restablece todos los elementos del layout a su posición, tamaño y forma originales")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background: #be123c;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #e11d48;
            }
        """)
        self.btn_reset.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_reset.setMinimumWidth(self.btn_reset.sizeHint().width() + 14)
        self.btn_reset.clicked.connect(self._on_reset_layout)
        row1_layout.addWidget(self.btn_reset)

        row1_layout.addStretch()

        self.btn_skew_mode = QPushButton("🔮 Deformación 4 Puntos")
        self.btn_skew_mode.setCheckable(True)
        self.btn_skew_mode.setStyleSheet("""
            QPushButton {
                background: #334155;
                color: #e2e8f0;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #475569;
            }
            QPushButton:checked {
                background: #d97706;
                color: #ffffff;
            }
        """)
        self.btn_skew_mode.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_skew_mode.setMinimumWidth(self.btn_skew_mode.sizeHint().width() + 14)
        self.btn_skew_mode.toggled.connect(self._on_skew_mode_toggled)
        row1_layout.addWidget(self.btn_skew_mode)

        main_layout.addLayout(row1_layout)

        # Fila 2: Contexto de Datos (Izquierda) y Prueba en Sandbox con Modo/Resolución (Derecha)
        row2_layout = QHBoxLayout()
        row2_layout.setContentsMargins(0, 2, 0, 2)
        row2_layout.setSpacing(10)

        lbl_list = QLabel("📁 Lista:")
        lbl_list.setStyleSheet("font-weight: bold; color: #cbd5e1;")
        row2_layout.addWidget(lbl_list)

        self.cb_lists = QComboBox()
        self.cb_lists.setMinimumWidth(170)
        self.cb_lists.setMaximumWidth(240)
        self.cb_lists.setStyleSheet("""
            QComboBox {
                background: #1e293b;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 8px;
            }
        """)
        self.cb_lists.currentIndexChanged.connect(self._on_list_combo_changed)
        row2_layout.addWidget(self.cb_lists)

        lbl_game = QLabel("🎮 Juego:")
        lbl_game.setStyleSheet("font-weight: bold; color: #cbd5e1;")
        row2_layout.addWidget(lbl_game)

        self.cb_sample_games = QComboBox()
        self.cb_sample_games.setMinimumWidth(220)
        self.cb_sample_games.setMaximumWidth(320)
        self.cb_sample_games.setEditable(True)
        self.cb_sample_games.setInsertPolicy(QComboBox.NoInsert)
        self.cb_sample_games.setStyleSheet("""
            QComboBox {
                background: #1e293b;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 8px;
            }
        """)
        self.cb_sample_games.currentIndexChanged.connect(self._on_sample_game_changed)
        row2_layout.addWidget(self.cb_sample_games)

        self.lbl_games_count = QLabel("")
        self.lbl_games_count.setStyleSheet("color: #38bdf8; font-size: 8.5pt; font-weight: bold;")
        row2_layout.addWidget(self.lbl_games_count)

        row2_layout.addStretch()

        self.cb_sandbox_mode = QComboBox()
        self.cb_sandbox_mode.setToolTip("Modo de visualización al probar en el Sandbox (Ventana o Pantalla Completa)")
        self.cb_sandbox_mode.setMinimumWidth(155)
        self.cb_sandbox_mode.setStyleSheet("""
            QComboBox {
                background: #1e293b;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
            }
        """)
        self.cb_sandbox_mode.addItem("🪟 Modo Ventana", "windowed")
        self.cb_sandbox_mode.addItem("🖥 Pantalla Completa", "fullscreen")
        self.cb_sandbox_mode.addItem("🔲 Ventana sin Bordes", "borderless")
        self.cb_sandbox_mode.currentIndexChanged.connect(self._on_sandbox_display_changed)
        row2_layout.addWidget(self.cb_sandbox_mode)

        self.cb_sandbox_res = QComboBox()
        self.cb_sandbox_res.setToolTip("Resolución en la que se ejecutará la prueba del Sandbox")
        self.cb_sandbox_res.setMinimumWidth(180)
        self.cb_sandbox_res.setStyleSheet("""
            QComboBox {
                background: #1e293b;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 10px;
            }
        """)
        sandbox_resolutions = [
            ("1280 x 720 (HD 16:9)", "1280x720"),
            ("1920 x 1080 (Full HD 16:9)", "1920x1080"),
            ("1600 x 900 (HD+ 16:9)", "1600x900"),
            ("1366 x 768 (Laptop 16:9)", "1366x768"),
            ("2560 x 1440 (2K QHD 16:9)", "2560x1440"),
            ("3840 x 2160 (4K UHD 16:9)", "3840x2160"),
            ("1920 x 1200 (16:10)", "1920x1200"),
            ("1280 x 800 (16:10)", "1280x800"),
            ("1280 x 1024 (5:4)", "1280x1024"),
            ("1024 x 768 (4:3 CRT/Arcade)", "1024x768"),
            ("800 x 600 (4:3 SVGA)", "800x600"),
            ("640 x 480 (4:3 VGA)", "640x480"),
            ("Nativa del Monitor", "system"),
        ]
        for label, val in sandbox_resolutions:
            self.cb_sandbox_res.addItem(label, val)
        self.cb_sandbox_res.currentIndexChanged.connect(self._on_sandbox_display_changed)
        row2_layout.addWidget(self.cb_sandbox_res)

        self.btn_test = QPushButton("▶ Probar en Sandbox")
        self.btn_test.setToolTip("Abre una previsualización interactiva con las modificaciones actuales del layout (Esc para cerrar, F11 para alternar pantalla completa)")
        self.btn_test.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8b5cf6, stop:1 #6d28d9);
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #7c3aed;
            }
        """)
        self.btn_test.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_test.setMinimumWidth(self.btn_test.sizeHint().width() + 16)
        self.btn_test.clicked.connect(self._on_test_layout)
        row2_layout.addWidget(self.btn_test)

        main_layout.addLayout(row2_layout)

        # -------------------------------------------------------------
        # 2. ÁREA CENTRAL SPLITTER (CANVAS + TIMELINE A LA IZQUIERDA, EDITOR/INSPECTOR A LA DERECHA)
        # -------------------------------------------------------------
        self.splitter = QSplitter(Qt.Horizontal)

        # Contenedor central: Canvas + Barra de Línea Temporal de Animación
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(6)

        # Lienzo Interactivo
        self.canvas = LayoutCanvasWidget(self)
        self.canvas.element_selected.connect(self._on_canvas_element_selected)
        self.canvas.element_dragging.connect(self._on_canvas_element_dragging)
        self.canvas.element_modified.connect(self._on_canvas_element_modified)
        canvas_layout.addWidget(self.canvas, 1)

        # Barra de Línea Temporal de Animación (Animation Timeline Bar)
        # Oculta por defecto; solo aparece si el elemento seleccionado tiene animación
        self.timeline_bar = QFrame()
        self.timeline_bar.setVisible(False)
        self.timeline_bar.setStyleSheet("""
            QFrame {
                background: #090d16;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 4px 10px;
            }
        """)
        timeline_layout = QHBoxLayout(self.timeline_bar)
        timeline_layout.setContentsMargins(4, 2, 4, 2)
        timeline_layout.setSpacing(8)

        lbl_tl_title = QLabel("⏱ Animación:")
        lbl_tl_title.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 8.5pt;")
        timeline_layout.addWidget(lbl_tl_title)

        self.btn_tl_reset = QPushButton("🔄 0.0s")
        self.btn_tl_reset.setToolTip("Reiniciar animación al inicio (0.0s)")
        self.btn_tl_reset.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #94a3b8; border: 1px solid #334155;
                border-radius: 4px; padding: 3px 8px; font-weight: bold; font-size: 8pt;
            }
            QPushButton:hover { background: #334155; color: #f8fafc; }
        """)
        self.btn_tl_reset.clicked.connect(self._on_timeline_reset)
        timeline_layout.addWidget(self.btn_tl_reset)

        self.btn_tl_step_back = QPushButton("⏪ -0.1s")
        self.btn_tl_step_back.setToolTip("Retroceder 100 milisegundos")
        self.btn_tl_step_back.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #cbd5e1; border: 1px solid #334155;
                border-radius: 4px; padding: 3px 8px; font-size: 8pt;
            }
            QPushButton:hover { background: #334155; color: #38bdf8; }
        """)
        self.btn_tl_step_back.clicked.connect(lambda: self._on_timeline_step(-0.1))
        timeline_layout.addWidget(self.btn_tl_step_back)

        self.btn_tl_play = QPushButton("▶ Play")
        self.btn_tl_play.setToolTip("Reproducir / Pausar ciclo de animación (60 FPS)")
        self.btn_tl_play.setStyleSheet("""
            QPushButton {
                background: #0284c7; color: #ffffff; border: 1px solid #0ea5e9;
                border-radius: 4px; padding: 3px 12px; font-weight: bold; font-size: 8.5pt;
            }
            QPushButton:hover { background: #0ea5e9; }
        """)
        self.btn_tl_play.clicked.connect(self._toggle_timeline_play)
        timeline_layout.addWidget(self.btn_tl_play)

        self.btn_tl_step_fwd = QPushButton("⏩ +0.1s")
        self.btn_tl_step_fwd.setToolTip("Adelantar 100 milisegundos")
        self.btn_tl_step_fwd.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #cbd5e1; border: 1px solid #334155;
                border-radius: 4px; padding: 3px 8px; font-size: 8pt;
            }
            QPushButton:hover { background: #334155; color: #38bdf8; }
        """)
        self.btn_tl_step_fwd.clicked.connect(lambda: self._on_timeline_step(0.1))
        timeline_layout.addWidget(self.btn_tl_step_fwd)

        # Scrubber Slider (0.0s a 5.0s, resolución de 10ms = 500 pasos)
        self.slider_timeline = QSlider(Qt.Horizontal)
        self.slider_timeline.setRange(0, 500)
        self.slider_timeline.setValue(0)
        self.slider_timeline.setToolTip("Arrastrar para posicionar la animación en cualquier momento (0.00s a 5.00s)")
        self.slider_timeline.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #1e293b;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #f8fafc;
                border: 2px solid #0ea5e9;
                width: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #38bdf8;
                border: 2px solid #ffffff;
            }
        """)
        self.slider_timeline.valueChanged.connect(self._on_timeline_slider_changed)
        timeline_layout.addWidget(self.slider_timeline, 1)

        self.lbl_timeline_time = QLabel("0.00s / 5.00s")
        self.lbl_timeline_time.setMinimumWidth(85)
        self.lbl_timeline_time.setAlignment(Qt.AlignCenter)
        self.lbl_timeline_time.setStyleSheet("color: #38bdf8; font-family: monospace; font-weight: bold; font-size: 8.5pt;")
        timeline_layout.addWidget(self.lbl_timeline_time)

        canvas_layout.addWidget(self.timeline_bar, 0)
        self.splitter.addWidget(canvas_container)

        # Timer para reproducción continua a 60 FPS
        self._timeline_timer = QTimer(self)
        self._timeline_timer.setInterval(16)
        self._timeline_timer.timeout.connect(self._on_timeline_tick)
        self._timeline_playing = False

        # Pestañas derechas: Inspector y Editor de Código
        self.side_tabs = QTabWidget()
        self.side_tabs.setMinimumWidth(380)
        self.side_tabs.currentChanged.connect(self._on_side_tab_changed)

        self.inspector = LayoutInspectorWidget(self)
        self.inspector.element_selected.connect(self.canvas.select_element)
        self.inspector.element_selected.connect(self._update_timeline_visibility)
        self.inspector.element_modified.connect(self._on_inspector_element_modified)
        self.inspector.element_added.connect(self._on_inspector_element_added)
        self.inspector.element_removed.connect(self._on_inspector_element_removed)
        self.inspector.layer_order_changed.connect(self._on_layer_order_changed)
        self.inspector.layer_visibility_changed.connect(self._on_layer_visibility_changed)
        self.inspector.skew_mode_toggled.connect(self.canvas.set_skew_mode)
        self.side_tabs.addTab(self.inspector, "🎨  Inspector Visual")

        self.code_editor = LayoutCodeEditorWidget(self)
        self.code_editor.code_applied.connect(self._on_code_hot_reloaded)
        self.side_tabs.addTab(self.code_editor, "💻  Código Python")

        self.splitter.addWidget(self.side_tabs)
        self.splitter.setSizes([750, 450])

        main_layout.addWidget(self.splitter)

    # -------------------------------------------------------------
    # CONTROL DE LÍNEA TEMPORAL DE ANIMACIÓN
    # -------------------------------------------------------------
    def _toggle_timeline_play(self):
        """Alterna entre reproducir y pausar la animación del layout a 60 FPS."""
        self._timeline_playing = not self._timeline_playing
        if self._timeline_playing:
            self.btn_tl_play.setText("⏸ Pausa")
            self.btn_tl_play.setStyleSheet("""
                QPushButton {
                    background: #f59e0b; color: #000000; border: 1px solid #fbbf24;
                    border-radius: 4px; padding: 3px 12px; font-weight: bold; font-size: 8.5pt;
                }
                QPushButton:hover { background: #fbbf24; }
            """)
            if self.slider_timeline.value() >= 500:
                self.slider_timeline.setValue(0)
            self._timeline_timer.start()
        else:
            self._timeline_timer.stop()
            self.btn_tl_play.setText("▶ Play")
            self.btn_tl_play.setStyleSheet("""
                QPushButton {
                    background: #0284c7; color: #ffffff; border: 1px solid #0ea5e9;
                    border-radius: 4px; padding: 3px 12px; font-weight: bold; font-size: 8.5pt;
                }
                QPushButton:hover { background: #0ea5e9; }
            """)

    def _on_timeline_reset(self):
        """Reinicia la línea temporal a 0.0s."""
        self.slider_timeline.setValue(0)

    def _on_timeline_step(self, delta_s: float):
        """Avanza o retrocede la línea temporal en pasos de delta_s segundos."""
        steps = int(delta_s * 100)
        new_val = max(0, min(500, self.slider_timeline.value() + steps))
        self.slider_timeline.setValue(new_val)

    def _on_timeline_tick(self):
        """Tic del temporizador a 60 FPS para avanzar el slider de la línea temporal."""
        val = self.slider_timeline.value()
        if val >= 500:
            # Al llegar a 5.00s, reiniciar automáticamente al inicio (ciclo continuo)
            self.slider_timeline.setValue(0)
        else:
            # Cada tic de 16ms equivale a 1.6 centésimas de segundo (aprox 2 pasos)
            self.slider_timeline.setValue(min(500, val + 2))

    def _on_timeline_slider_changed(self, value: int):
        """Controlador del cambio en el slider de tiempo (0 a 500 = 0.00s a 5.00s)."""
        seconds = value / 100.0
        self.lbl_timeline_time.setText(f"{seconds:.2f}s / 5.00s")
        self.canvas.apply_animation_time(seconds)

    # -------------------------------------------------------------
    # GESTIÓN DE LISTAS Y JUEGOS DE MUESTRA
    # -------------------------------------------------------------
    def _load_lists_and_games(self):
        """Carga las listas creadas por el usuario en la base de datos y sus juegos."""
        self.cb_lists.blockSignals(True)
        self.cb_lists.clear()

        lists = []
        if self.db:
            try:
                lists = self.db.get_lists(with_counts=True)
            except Exception:
                pass
        self._all_db_lists = [dict(l) for l in lists] if lists else []

        if lists:
            for l in lists:
                count = l.get("game_count", 0)
                name = l.get("name", "Lista")
                self.cb_lists.addItem(f"📁 {name} ({count})", l.get("id"))
        else:
            self.cb_lists.addItem("📁 Lista Predeterminada (Ejemplo)", None)

        self.cb_lists.blockSignals(False)

        if self.cb_lists.count() > 0:
            self.cb_lists.setCurrentIndex(0)
            self._on_list_combo_changed(0)

    def _on_list_combo_changed(self, index: int):
        """Actualiza el listado de juegos cuando el usuario cambia de lista."""
        # Limpiar caché de pixmaps y cuadros de video del canvas al cambiar de lista
        self.canvas._pixmap_cache.clear()
        if hasattr(self.canvas, "_video_frame_cache"):
            self.canvas._video_frame_cache.clear()
        self.canvas._video_frame_pix = None

        list_id = self.cb_lists.itemData(index)
        self.current_list_games = []

        if self.db and list_id:
            try:
                self.current_list_games = self.db.get_games(list_id)
            except Exception:
                pass

        self.cb_sample_games.blockSignals(True)
        self.cb_sample_games.clear()

        if self.current_list_games:
            for g in self.current_list_games:
                title = g.get("title", "Sin Título")
                year = g.get("year", "")
                display = f"{title} ({year})" if year else title
                self.cb_sample_games.addItem(display, g)
            self.lbl_games_count.setText(f"✓ {len(self.current_list_games)} juegos disponibles")
        else:
            mock = {
                "id": 9999,
                "title": "Street Fighter II: The World Warrior",
                "year": "1991",
                "manufacturer": "Capcom",
                "genre": "Fighting",
            }
            self.current_list_games = [mock]
            self.cb_sample_games.addItem("Street Fighter II (Ejemplo)", mock)
            self.lbl_games_count.setText("(1 juego de ejemplo)")

        # Configurar búsqueda interactiva / auto-completado
        completer = self.cb_sample_games.completer()
        if completer:
            completer.setFilterMode(Qt.MatchContains)

        self.cb_sample_games.blockSignals(False)

        # Sincronizar la colección de juegos con el lienzo para poblar la ruleta de ruedas
        if hasattr(self.canvas, "set_sample_games_list"):
            self.canvas.set_sample_games_list(self.current_list_games)

        if self.cb_sample_games.count() > 0:
            self.cb_sample_games.setCurrentIndex(0)
            self._on_sample_game_changed(0)

    def _on_sample_game_changed(self, index: int):
        game = self.cb_sample_games.itemData(index)
        if game:
            if self.canvas.layout_instance is not None:
                sync_quiet_studio_instance(self.canvas.layout_instance, self.current_list_games, game)
            self.canvas.set_sample_game(game)
            self.canvas.update()

    def _instantiate_quiet_theme(self, name: str, folder: str, code: str):
        """
        Compila e instancia la clase real ThemeLayout de theme_layout.py en memoria
        con todos sus temporizadores y reproductores detenidos (0% CPU en reposo).
        """
        if not folder or not code:
            return None
        try:
            clean_code = re.sub(
                r"\n*# --- PLAYNEXUS STUDIO OVERRIDES START ---.*?# --- PLAYNEXUS STUDIO OVERRIDES END ---\n?",
                "\n",
                code,
                flags=re.DOTALL,
            )
            py_path = str((Path(folder) / "theme_layout.py").resolve())
            code_obj = compile(clean_code, py_path, "exec")
            mod = types.ModuleType(f"studio_live_{name}")
            mod.__file__ = py_path
            exec(code_obj, mod.__dict__)
            layout_cls = getattr(mod, "ThemeLayout", None)
            if layout_cls is None:
                return None
            inst = layout_cls(name, None)
            selected_game = self.cb_sample_games.currentData()
            sync_quiet_studio_instance(inst, self.current_list_games, selected_game)
            return inst
        except Exception as err:
            print(f"[LayoutStudio] Error instanciando ThemeLayout de '{name}': {err}")
            return None

    # -------------------------------------------------------------------------
    # CARGA Y GESTIÓN DE LAYOUTS
    # -------------------------------------------------------------------------
    def refresh_layouts_list(self):
        """Recarga la lista de layouts disponibles en la carpeta Layouts/."""
        self.cb_layouts.blockSignals(True)
        self.cb_layouts.clear()

        layouts_root = get_layouts_root()
        themes = get_all_theme_layouts(force_reload=True)

        for name in sorted(themes.keys()):
            self.cb_layouts.addItem(name, themes[name]["folder"])

        self.cb_layouts.blockSignals(False)

        if self.cb_layouts.count() > 0:
            self.cb_layouts.setCurrentIndex(0)
            self._load_selected_layout()

    def _on_layout_combo_changed(self, index: int):
        if index >= 0:
            self._load_selected_layout()

    def _auto_select_list_for_layout(self, layout_name: str):
        """Selecciona automáticamente en cb_lists la lista asociada al layout elegido."""
        db_lists = getattr(self, "_all_db_lists", None)
        if not db_lists or not layout_name:
            return
        cur_list_id = self.cb_lists.currentData()
        norm_layout = re.sub(r"[^a-z0-9]+", "", layout_name.lower())

        # Si la lista actual ya usa este layout y tiene juegos, mantenerla
        for l in db_lists:
            if l.get("id") == cur_list_id and (l.get("game_count", 0) or 0) > 0:
                if (l.get("layout") or "").strip().lower() == layout_name.strip().lower():
                    return

        # Buscar la mejor lista que use este layout (priorizando las que tienen juegos y flyers si es arcade)
        candidates = []
        for l in db_lists:
            gcount = int(l.get("game_count", 0) or 0)
            if gcount <= 0 and (l.get("list_type") != "menu"):
                continue
            l_layout = (l.get("layout") or "").strip()
            l_name = (l.get("name") or "").strip()
            norm_lname = re.sub(r"[^a-z0-9]+", "", l_name.lower())
            if l_layout.lower() == layout_name.strip().lower() or norm_lname == norm_layout:
                has_flyer = 1 if (l.get("flyer_path") or "").strip() else 0
                candidates.append((has_flyer, gcount, l.get("id")))

        if candidates:
            candidates.sort(reverse=True)
            best_list_id = candidates[0][2]
            idx = self.cb_lists.findData(best_list_id)
            if idx >= 0 and idx != self.cb_lists.currentIndex():
                self.cb_lists.setCurrentIndex(idx)

    def _load_selected_layout(self):
        """Carga el layout seleccionado leyendo directamente su theme_layout.py."""
        folder = self.cb_layouts.currentData()
        name = self.cb_layouts.currentText()
        if not folder or not os.path.isdir(folder):
            return

        # Sincronizar automáticamente la lista de juegos asociada a este layout
        self._auto_select_list_for_layout(name)

        py_file = Path(folder) / "theme_layout.py"
        code_content = ""
        if py_file.is_file():
            try:
                code_content = py_file.read_text(encoding="utf-8")
            except Exception:
                pass

        # Instanciar el ThemeLayout real y extraer sus capas directamente desde paintEvent
        inst = self._instantiate_quiet_theme(name, folder, code_content)
        project = self._parse_or_create_project(name, folder, code_content, inst=inst)
        self.current_project = project

        self.canvas.set_project(project)
        self.canvas.set_layout_instance(inst)
        self.inspector.set_project(project)

        active_code = code_content if code_content else generate_layout_code(project)
        self._cached_code = active_code
        self._pending_code_sync = False
        self.code_editor.set_code(active_code)

        # Actualizar los datos de muestra del lienzo
        self._update_live_layout_engine(code_content, existing_inst=inst)

    def _update_live_layout_engine(self, code_override: str | None = None, existing_inst=None):
        """Sincroniza la instancia real de ThemeLayout con la lista y el juego de muestra activos."""
        if not self.current_project:
            return
        already_synced = existing_inst is not None
        if existing_inst is None and code_override and self.current_project.folder_path:
            existing_inst = self._instantiate_quiet_theme(
                self.current_project.name,
                self.current_project.folder_path,
                code_override,
            )
            self.canvas.set_layout_instance(existing_inst)
            already_synced = True

        if hasattr(self.canvas, "set_sample_games_list"):
            self.canvas.set_sample_games_list(self.current_list_games)
        selected_game = self.cb_sample_games.currentData()
        if selected_game:
            if self.canvas.layout_instance is not None and not already_synced:
                sync_quiet_studio_instance(self.canvas.layout_instance, self.current_list_games, selected_game)
            self.canvas.set_sample_game(selected_game)
        self.canvas.update()

    def _parse_or_create_project(self, name: str, folder: str, code: str, inst=None) -> LayoutProject:
        """
        Construye el LayoutProject directamente desde la instancia real de ThemeLayout
        y el AST de su paintEvent en theme_layout.py (o desde STUDIO_ELEMENTS si fue guardado).
        """
        proj = LayoutProject(name=name, folder_path=folder)
        if inst is None and folder and code:
            inst = self._instantiate_quiet_theme(name, folder, code)

        # Buscar si el archivo ya contiene STUDIO_ELEMENTS = [...] o ELEMENTS = [...]
        elements_found: list[LayoutElement] = []
        if code and ("STUDIO_ELEMENTS = [" in code or "ELEMENTS = [" in code):
            target_var = "STUDIO_ELEMENTS" if "STUDIO_ELEMENTS = [" in code else "ELEMENTS"
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == target_var:
                                if isinstance(node.value, ast.List):
                                    for elem_node in node.value.elts:
                                        elem_dict = ast.literal_eval(elem_node)
                                        elem = LayoutElement.from_dict(elem_dict)
                                        if elem.orig_rect is None and inst is not None:
                                            elem.orig_rect = measure_native_layer_bbox(inst, elem.id)
                                        elements_found.append(elem)
            except Exception:
                pass

        if elements_found:
            proj.elements = elements_found
        elif inst is not None:
            proj.elements = extract_elements_from_theme_instance(inst, code)
        else:
            default_proj = create_arcade_cabinet_template(proj.name)
            proj.elements = default_proj.elements
            proj.media_requirements = default_proj.media_requirements

        if inst is not None and hasattr(inst, "MEDIA_REQUIREMENTS"):
            try:
                proj.media_requirements = dict(getattr(inst, "MEDIA_REQUIREMENTS") or {})
            except Exception:
                pass

        return proj

    # -------------------------------------------------------------------------
    # SINCRONIZACIÓN BIDIRECCIONAL
    # -------------------------------------------------------------------------
    def _on_canvas_element_selected(self, elem_id: str):
        self.inspector.select_element(elem_id)
        self._update_timeline_visibility(elem_id)

    def _update_timeline_visibility(self, elem_id: str):
        """
        Muestra u oculta la barra de tiempo de animación.
        Solo es visible si el elemento seleccionado tiene o admite cinemática (flyer, cart, boxart, logo, avatar, pointer).
        """
        elem = self.current_project.get_element(elem_id) if (self.current_project and elem_id) else None
        has_anim = elem.has_animation() if elem else False

        if hasattr(self, "timeline_bar"):
            self.timeline_bar.setVisible(has_anim)
            if getattr(self, "_timeline_playing", False):
                self._toggle_timeline_play()
            if hasattr(self, "slider_timeline"):
                self.slider_timeline.blockSignals(True)
                self.slider_timeline.setValue(0)
                self.slider_timeline.blockSignals(False)
            if hasattr(self, "lbl_timeline_time"):
                self.lbl_timeline_time.setText("0.00s / 5.00s")

        # Al seleccionar el elemento, mostrarlo en su posición de reposo (listo para mover/redimensionar)
        # La animación solo se aplica cuando el usuario mueve la línea de tiempo o pulsa Play
        self.canvas._is_previewing_anim = False
        self.canvas.update()

    def _on_canvas_element_dragging(self, elem_id: str):
        """Maneja el arrastre en tiempo real con latencia 0 ms sin tocar el editor de código."""
        self._apply_element_to_live_instance(elem_id)
        if hasattr(self.inspector, "update_geometry_fields"):
            self.inspector.update_geometry_fields(elem_id)

    def _on_canvas_element_modified(self, elem_id: str):
        self.inspector.select_element(elem_id)
        self._apply_element_to_live_instance(elem_id)
        self._sync_project_to_code()

    def _on_layer_visibility_changed(self, elem_id: str, is_visible: bool):
        """Refresca el lienzo y el Sandbox cuando se activa u oculta el ojo de una capa."""
        self._apply_element_to_live_instance(elem_id)
        self.canvas.update()
        self._sync_project_to_code()

    def _on_side_tab_changed(self, index: int):
        """Si el usuario abre la pestaña de código, vuelca cualquier sincronización pendiente."""
        if index == 1 and getattr(self, "_pending_code_sync", False):
            self._pending_code_sync = False
            self.code_editor.set_code(self._cached_code)

    def _on_inspector_element_modified(self, elem_id: str):
        self._apply_element_to_live_instance(elem_id)
        self.canvas.update()
        self._sync_project_to_code()

    def _apply_element_to_live_instance(self, elem_id: str):
        if not self.current_project:
            return
        # Si hay una ventana de Sandbox abierta, actualizar sus overrides en tiempo real
        test_widget = getattr(self, "_test_layout_widget", None)
        if test_widget is not None:
            try:
                update_studio_overrides(test_widget, self.current_project.elements)
            except Exception:
                pass
        self.canvas.update()

    def _on_inspector_element_added(self, elem_id: str):
        self.canvas.select_element(elem_id)
        self._apply_element_to_live_instance(elem_id)
        self._sync_project_to_code()

    def _on_inspector_element_removed(self, elem_id: str):
        self.canvas.select_element(None)
        self._apply_element_to_live_instance("")
        self._sync_project_to_code()

    def _on_layer_order_changed(self):
        self._apply_element_to_live_instance("")
        self.canvas.update()
        self._sync_project_to_code()

    def _on_skew_mode_toggled(self, checked: bool):
        self.canvas.set_skew_mode(checked)

    def _sync_project_to_code(self):
        """Actualiza el código Python cuando ocurren cambios visuales."""
        if self._is_syncing or not self.current_project:
            return
        self._is_syncing = True

        current_code = self._cached_code or self.code_editor.get_code()
        # Si el layout usa la lista ELEMENTS = [...] (plantillas generadas por Studio)
        if "ELEMENTS = [" in current_code and "STUDIO_ELEMENTS = [" not in current_code:
            elements_code = []
            for elem in sorted(self.current_project.elements, key=lambda e: e.z_index):
                if not elem.visible:
                    continue
                elements_code.append(f"        {elem.to_dict()!r},")
            new_elements_block = "ELEMENTS = [\n" + "\n".join(elements_code) + "\n    ]"
            new_code = re.sub(r"ELEMENTS\s*=\s*\[.*?\]", new_elements_block, current_code, flags=re.DOTALL)
        else:
            # Layout de producción existente: mantener constantes intactas y persistir STUDIO_ELEMENTS
            # para evitar doble reescalado o doble desplazamiento al aplicar los overrides.
            new_code = current_code

            # Persistir STUDIO_ELEMENTS y el hook de runtime al final del módulo
            studio_lines = [f"    {elem.to_dict()!r}," for elem in sorted(self.current_project.elements, key=lambda e: e.z_index)]
            studio_block = (
                "# --- PLAYNEXUS STUDIO OVERRIDES START ---\n"
                "STUDIO_ELEMENTS = [\n" + "\n".join(studio_lines) + "\n]\n"
                "try:\n"
                "    from playnexus.ui.layout_studio.runtime_hook import install_studio_overrides as _install_studio_overrides\n"
                "    _orig_init = ThemeLayout.__init__\n"
                "    def _studio_patched_init(self, *args, **kwargs):\n"
                "        _orig_init(self, *args, **kwargs)\n"
                "        _install_studio_overrides(self, STUDIO_ELEMENTS)\n"
                "    if not getattr(ThemeLayout.__init__, '_is_studio_patched', False):\n"
                "        _orig_init = ThemeLayout.__init__\n"
                "        _studio_patched_init._is_studio_patched = True\n"
                "        ThemeLayout.__init__ = _studio_patched_init\n"
                "except Exception:\n"
                "    pass\n"
                "# --- PLAYNEXUS STUDIO OVERRIDES END ---\n"
            )
            if "# --- PLAYNEXUS STUDIO OVERRIDES START ---" in new_code:
                new_code = re.sub(
                    r"# --- PLAYNEXUS STUDIO OVERRIDES START ---.*?# --- PLAYNEXUS STUDIO OVERRIDES END ---\n?",
                    studio_block,
                    new_code,
                    flags=re.DOTALL,
                )
            else:
                new_code = new_code.rstrip() + "\n\n" + studio_block

        self._cached_code = new_code
        if self.side_tabs.currentIndex() == 1:
            self.code_editor.set_code(new_code)
            self._pending_code_sync = False
        else:
            self._pending_code_sync = True

        self._is_syncing = False

    def _on_code_hot_reloaded(self, code: str):
        """Aplica los cambios del editor de código al lienzo en caliente."""
        if not self.current_project:
            return
        inst = self._instantiate_quiet_theme(
            self.current_project.name,
            self.current_project.folder_path,
            code,
        )
        new_project = self._parse_or_create_project(
            self.current_project.name,
            self.current_project.folder_path,
            code,
            inst=inst,
        )
        self.current_project = new_project
        self.canvas.set_project(new_project)
        self.canvas.set_layout_instance(inst)
        self.inspector.set_project(new_project)
        self._update_live_layout_engine(code, existing_inst=inst)
        QMessageBox.information(self, "Hot Reload", "¡Layout recargado con éxito desde el código!")

    # -------------------------------------------------------------------------
    # ACCIONES: NUEVO, GUARDAR, PROBAR
    # -------------------------------------------------------------------------
    def _on_new_layout(self):
        dlg = NewLayoutDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        name, tpl_name = dlg.get_result()
        creator = TEMPLATES_LIBRARY.get(tpl_name, create_arcade_cabinet_template)
        new_proj = creator(name)

        layouts_root = get_layouts_root()
        target_dir = layouts_root / name
        target_dir.mkdir(parents=True, exist_ok=True)
        new_proj.folder_path = str(target_dir)

        # Generar theme_layout.py inicial
        py_file = target_dir / "theme_layout.py"
        code = generate_layout_code(new_proj)
        py_file.write_text(code, encoding="utf-8")

        self.refresh_layouts_list()

        # Seleccionar el recién creado
        idx = self.cb_layouts.findText(name)
        if idx >= 0:
            self.cb_layouts.setCurrentIndex(idx)

        QMessageBox.information(self, "Nuevo Layout Creado", f"Se creó exitosamente el layout '{name}'.")

    def _on_save_layout(self):
        """Guarda los cambios en theme_layout.py generando previamente una copia de seguridad en /backups."""
        if not self.current_project or not self.current_project.folder_path:
            return

        if getattr(self, "_pending_code_sync", False):
            self._pending_code_sync = False
            self.code_editor.set_code(self._cached_code)

        # Validar sintaxis antes de guardar
        if not self.code_editor._validate_syntax():
            res = QMessageBox.warning(
                self,
                "Error de Sintaxis",
                "El código contiene errores de sintaxis Python.\n¿Deseas guardarlo de todos modos?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return

        target_dir = Path(self.current_project.folder_path)
        target_dir.mkdir(parents=True, exist_ok=True)

        py_file = target_dir / "theme_layout.py"
        backup_path: Path | None = None

        if py_file.is_file():
            # Crear directorio de copias de seguridad
            backup_dir = target_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"theme_layout_backup_{timestamp}.py"
            try:
                shutil.copy2(py_file, backup_file)
                backup_path = backup_file
            except Exception as e:
                print(f"[LayoutStudio] Error al crear backup: {e}")

        code = self.code_editor.get_code()
        py_file.write_text(code, encoding="utf-8")

        get_all_theme_layouts(force_reload=True)

        msg = f"✓ Se guardaron los cambios de '{self.current_project.name}' exitosamente."
        if backup_path:
            msg += f"\n\n📁 Copia de seguridad generada en:\nbackups/{backup_path.name}"
        QMessageBox.information(self, "Layout Guardado", msg)

    def _on_save_as_layout(self):
        """Guarda una copia del layout con un nuevo nombre."""
        name, ok = QInputDialog.getText(self, "Guardar Como", "Nombre del nuevo layout:")
        if not ok or not name.strip():
            return
        name = name.strip()

        layouts_root = get_layouts_root()
        target_dir = layouts_root / name
        target_dir.mkdir(parents=True, exist_ok=True)

        py_file = target_dir / "theme_layout.py"
        code = self.code_editor.get_code()
        py_file.write_text(code, encoding="utf-8")

        self.refresh_layouts_list()
        idx = self.cb_layouts.findText(name)
        if idx >= 0:
            self.cb_layouts.setCurrentIndex(idx)

        QMessageBox.information(self, "Layout Guardado", f"Se creó una copia como '{name}'.")

    def _on_reset_layout(self):
        """Restablece todos los elementos del layout a su posición, tamaño, forma y visibilidad originales."""
        if not self.current_project or not self.current_project.folder_path:
            return

        folder = Path(self.current_project.folder_path)
        name = self.current_project.name
        py_file = folder / "theme_layout.py"
        backup_dir = folder / "backups"

        # Buscar la copia de seguridad original más antigua si existe
        backups = sorted(backup_dir.glob("theme_layout_backup_*.py")) if backup_dir.is_dir() else []

        # Leer código base limpio (desde el primer backup original o limpiando el bloque STUDIO_ELEMENTS)
        base_code = ""
        if backups:
            try:
                base_code = backups[0].read_text(encoding="utf-8")
            except Exception:
                pass

        if not base_code and py_file.is_file():
            try:
                base_code = py_file.read_text(encoding="utf-8")
            except Exception:
                pass

        # Eliminar cualquier bloque de overrides previo para forzar la geometría original de fábrica
        clean_code = re.sub(
            r"\n*# --- PLAYNEXUS STUDIO OVERRIDES START ---.*?# --- PLAYNEXUS STUDIO OVERRIDES END ---\n?",
            "\n",
            base_code,
            flags=re.DOTALL,
        )

        # Reconstruir proyecto con sus valores originales leyendo directamente theme_layout.py
        inst = self._instantiate_quiet_theme(name, str(folder), clean_code)
        reset_proj = self._parse_or_create_project(name, str(folder), clean_code, inst=inst)

        self.current_project = reset_proj
        self._cached_code = clean_code if clean_code else generate_layout_code(reset_proj)
        self._pending_code_sync = False

        # Desactivar modo deformación 4 puntos si estaba activo
        if self.btn_skew_mode.isChecked():
            self.btn_skew_mode.setChecked(False)
        self.canvas.set_skew_mode(False)
        self.canvas._is_previewing_anim = False

        # Actualizar Canvas, Inspector y Editor de Código
        self.canvas.set_project(reset_proj)
        self.canvas.set_layout_instance(inst)
        self.inspector.set_project(reset_proj)
        self.code_editor.set_code(self._cached_code)
        self._update_live_layout_engine(clean_code, existing_inst=inst)
        self._update_timeline_visibility("")

        # Si hay una ventana de Sandbox abierta, sincronizarla en tiempo real con el estado restablecido
        test_widget = getattr(self, "_test_layout_widget", None)
        if test_widget is not None:
            try:
                update_studio_overrides(test_widget, self.current_project.elements)
            except Exception:
                pass

        self.canvas.update()

    def _get_sandbox_display_config(self) -> tuple[str, int, int, str]:
        """Retorna (mode, target_w, target_h, res_val) seleccionados para el Sandbox."""
        mode = self.cb_sandbox_mode.currentData() or "windowed"
        res_val = self.cb_sandbox_res.currentData() or "1280x720"
        screen = QApplication.primaryScreen()
        scr_geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)

        target_w, target_h = 1280, 720
        if res_val == "system":
            target_w, target_h = scr_geo.width(), scr_geo.height()
        elif "x" in res_val:
            try:
                parts = res_val.lower().split("x")
                target_w, target_h = int(parts[0].strip()), int(parts[1].strip())
            except Exception:
                target_w, target_h = 1280, 720
        return mode, target_w, target_h, res_val

    def _apply_sandbox_window_geometry(self, test_win, layout_widget):
        """Aplica en vivo el modo de visualización (ventana / sin bordes / pantalla completa) y resolución al Sandbox."""
        if test_win is None or layout_widget is None:
            return
        mode, target_w, target_h, res_val = self._get_sandbox_display_config()
        screen = test_win.screen() or QApplication.primaryScreen()
        scr_geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        avail_geo = screen.availableGeometry() if screen else scr_geo

        test_win.setWindowTitle(
            f"Sandbox Preview: {self.current_project.name} — {target_w}x{target_h} "
            f"({'Pantalla Completa' if mode == 'fullscreen' else 'Sin Bordes' if mode == 'borderless' else 'Ventana'}) [Esc: Salir | F11: Pantalla Completa]"
        )

        container_layout = test_win.centralWidget().layout() if test_win.centralWidget() else None

        if mode == "fullscreen":
            test_win.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
            test_win.setGeometry(scr_geo)
            if res_val == "system" or (target_w == scr_geo.width() and target_h == scr_geo.height()):
                layout_widget.setMinimumSize(0, 0)
                layout_widget.setMaximumSize(16777215, 16777215)
                if container_layout is not None:
                    container_layout.setAlignment(layout_widget, Qt.Alignment())
            else:
                # Si la resolución elegida supera el tamaño físico del monitor, ajustar manteniendo proporción exacta
                fit_w, fit_h = target_w, target_h
                if fit_w > scr_geo.width() or fit_h > scr_geo.height():
                    scale = min(scr_geo.width() / float(fit_w), scr_geo.height() / float(fit_h))
                    fit_w = max(1, round(fit_w * scale))
                    fit_h = max(1, round(fit_h * scale))
                layout_widget.setFixedSize(fit_w, fit_h)
                if container_layout is not None:
                    container_layout.setAlignment(layout_widget, Qt.AlignCenter)
            test_win.showFullScreen()
        elif mode == "borderless":
            layout_widget.setMinimumSize(0, 0)
            layout_widget.setMaximumSize(16777215, 16777215)
            if container_layout is not None:
                container_layout.setAlignment(layout_widget, Qt.Alignment())
            test_win.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
            test_win.showNormal()
            cx = scr_geo.x() + (scr_geo.width() - target_w) // 2
            cy = scr_geo.y() + (scr_geo.height() - target_h) // 2
            test_win.setGeometry(cx, cy, target_w, target_h)
            test_win.show()
        else:
            layout_widget.setMinimumSize(0, 0)
            layout_widget.setMaximumSize(16777215, 16777215)
            if container_layout is not None:
                container_layout.setAlignment(layout_widget, Qt.Alignment())
            test_win.setWindowFlags(Qt.Window)
            test_win.showNormal()
            test_win.resize(target_w, target_h)
            cx = avail_geo.x() + max(0, (avail_geo.width() - target_w) // 2)
            cy = avail_geo.y() + max(0, (avail_geo.height() - target_h) // 2)
            try:
                test_win.move(cx, cy)
            except Exception:
                pass
            test_win.show()

        test_win.raise_()
        test_win.activateWindow()
        layout_widget.setFocus()
        layout_widget.update()

    def _on_sandbox_display_changed(self, _index: int = 0):
        """Si la ventana de Sandbox está abierta, actualiza su resolución o modo de pantalla al instante."""
        test_win = getattr(self, "_test_win", None)
        layout_widget = getattr(self, "_test_layout_widget", None)
        if test_win is not None and layout_widget is not None:
            self._apply_sandbox_window_geometry(test_win, layout_widget)

    def _on_test_layout(self):
        """Abre una ventana de prueba interactiva para probar el layout con las modificaciones en vivo."""
        if not self.current_project:
            return
        try:
            from PySide6.QtWidgets import QMainWindow

            # Cerrar ventana de prueba previa si estuviera abierta
            prev_win = getattr(self, "_test_win", None)
            if prev_win is not None:
                try:
                    prev_win.close()
                    prev_win.deleteLater()
                except Exception:
                    pass
                self._test_win = None
                self._test_layout_widget = None

            folder = Path(self.current_project.folder_path) if self.current_project.folder_path else None
            if not folder or not folder.is_dir():
                QMessageBox.warning(self, "Previsualización", "La carpeta del layout no existe en disco.")
                return

            # Sincronizar y obtener código limpio para la instancia del Sandbox
            self._sync_project_to_code()
            if getattr(self, "_pending_code_sync", False):
                self._pending_code_sync = False
                self.code_editor.set_code(self._cached_code)
            current_code = self._cached_code or self.code_editor.get_code()
            clean_sandbox_code = re.sub(
                r"\n*# --- PLAYNEXUS STUDIO OVERRIDES START ---.*?# --- PLAYNEXUS STUDIO OVERRIDES END ---\n?",
                "\n",
                current_code,
                flags=re.DOTALL,
            )

            # Compilación instantánea en memoria RAM sin escritura a disco (evita bloqueos de I/O y antivirus)
            code_obj = compile(clean_sandbox_code, f"<sandbox_{self.current_project.name}>", "exec")
            mod = types.ModuleType("sandbox_preview_module")
            mod.__file__ = str((folder / "theme_layout.py").resolve())
            exec(code_obj, mod.__dict__)
            layout_cls = getattr(mod, "ThemeLayout")

            test_win = QMainWindow(self)
            test_win.setAttribute(Qt.WA_DeleteOnClose, True)
            test_win.setStyleSheet("QMainWindow { background: #000000; }")

            # Suspender temporalmente animaciones del editor para que el sandbox tenga 100% CPU
            if hasattr(self, "_timeline_timer") and self._timeline_timer.isActive():
                self._toggle_timeline_play()

            # Contenedor central con centrado automático cuando se usa resolución fija en pantalla completa
            container = QWidget(test_win)
            container.setStyleSheet("background: #000000;")
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)

            layout_widget = layout_cls(self.current_project.name, container)
            install_studio_overrides(layout_widget, self.current_project.elements)
            self._test_layout_widget = layout_widget
            container_layout.addWidget(layout_widget, 1)

            if hasattr(layout_widget, "back_requested"):
                try:
                    layout_widget.back_requested.connect(test_win.close)
                except Exception:
                    pass

            # Atajos para salir (Esc) y alternar Ventana / Pantalla Completa (F11)
            esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), test_win)
            esc_shortcut.activated.connect(test_win.close)

            def _toggle_sandbox_fullscreen():
                cur_mode = self.cb_sandbox_mode.currentData()
                next_mode = "windowed" if cur_mode == "fullscreen" else "fullscreen"
                idx = self.cb_sandbox_mode.findData(next_mode)
                if idx >= 0:
                    self.cb_sandbox_mode.setCurrentIndex(idx)

            f11_shortcut = QShortcut(QKeySequence(Qt.Key_F11), test_win)
            f11_shortcut.activated.connect(_toggle_sandbox_fullscreen)

            # Optimizar catálogo de prueba a una muestra ágil (hasta 40 títulos) con el juego seleccionado en índice 0
            all_games = list(self.current_list_games or [])
            selected_game = self.cb_sample_games.currentData()
            initial_id = selected_game.get("id") if selected_game else None

            if not all_games:
                games = [
                    {"id": 1, "title": "Street Fighter II", "year": "1991", "manufacturer": "Capcom"},
                    {"id": 2, "title": "Mortal Kombat", "year": "1992", "manufacturer": "Midway"},
                    {"id": 3, "title": "Pac-Man", "year": "1980", "manufacturer": "Namco"},
                ]
            else:
                if initial_id is not None:
                    sel_idx = next((i for i, g in enumerate(all_games) if g.get("id") == initial_id), 0)
                    if sel_idx > 0:
                        all_games = all_games[sel_idx:] + all_games[:sel_idx]
                games = all_games[:40]

            test_win.setCentralWidget(container)
            self._test_win = test_win  # Prevenir recolección de basura
            self._apply_sandbox_window_geometry(test_win, layout_widget)

            layout_widget.set_games(games)
            # Reutilizar logos wheel ya cargados en el Studio para arranque instantáneo
            if self.canvas.layout_instance and hasattr(self.canvas.layout_instance, "_wheel_pixmaps"):
                if hasattr(layout_widget, "_wheel_pixmaps"):
                    layout_widget._wheel_pixmaps.update(self.canvas.layout_instance._wheel_pixmaps)
            layout_widget.update()

            # Limpieza estricta e inmediata de hilos y reproductores al cerrar la ventana de prueba
            def _cleanup():
                if getattr(self, "_test_layout_widget", None) is layout_widget:
                    self._test_layout_widget = None
                if getattr(self, "_test_win", None) is test_win:
                    self._test_win = None
                if layout_widget:
                    try:
                        if hasattr(layout_widget, "stop_media"):
                            layout_widget.stop_media()
                        if hasattr(layout_widget, "_wheel_worker") and layout_widget._wheel_worker:
                            layout_widget._wheel_worker.stop()
                            layout_widget._wheel_worker.wait(300)
                        if hasattr(layout_widget, "cleanup"):
                            layout_widget.cleanup()
                        layout_widget.deleteLater()
                    except Exception as err:
                        print(f"[Sandbox] Error liberando recursos: {err}")

            test_win.destroyed.connect(_cleanup)
            layout_widget.setFocus()
        except Exception as e:
            QMessageBox.critical(self, "Error al Iniciar Previsualización", f"Error cargando el layout modificado:\n{e}")

    def closeEvent(self, event):
        """Asegura la liberación de los motores y recursos en vivo del layout."""
        if hasattr(self, "_timeline_timer") and self._timeline_timer.isActive():
            self._timeline_timer.stop()
        if hasattr(self, "canvas") and hasattr(self.canvas, "cleanup"):
            self.canvas.cleanup()
        super().closeEvent(event)

