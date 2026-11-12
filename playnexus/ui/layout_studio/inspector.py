from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QGroupBox, QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox,
    QSlider, QCheckBox, QScrollArea, QFrame, QMenu, QColorDialog
)

from playnexus.ui.layout_studio.models import LayoutElement, LayoutProject, CANONICAL_W, CANONICAL_H


class LayoutInspectorWidget(QWidget):
    """
    Panel lateral de inspección de capas, transformación geométrica,
    deformación de perspectiva y propiedades de medios.
    """
    element_modified = Signal(str)      # elem_id
    element_selected = Signal(str)      # elem_id
    element_added = Signal(str)         # elem_id
    element_removed = Signal(str)       # elem_id
    layer_order_changed = Signal()
    layer_visibility_changed = Signal(str, bool)  # elem_id, is_visible
    skew_mode_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: LayoutProject | None = None
        self.current_elem_id: str | None = None
        self._updating_ui = False

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(8)

        # -------------------------------------------------------------
        # 1. GESTOR DE CAPAS Y ELEMENTOS (ESTILO PHOTOSHOP)
        # -------------------------------------------------------------
        layers_box = QGroupBox("📑  Capas del Layout (Estilo Photoshop)")
        layers_box.setStyleSheet("QGroupBox { font-weight: bold; color: #cbd5e1; }")
        l_layout = QVBoxLayout(layers_box)
        l_layout.setContentsMargins(6, 12, 6, 6)
        l_layout.setSpacing(6)

        self.layer_list = QListWidget()
        self.layer_list.setStyleSheet("""
            QListWidget {
                background-color: #0b0f19;
                border: 1px solid #1e293b;
                border-radius: 6px;
                color: #e2e8f0;
                padding: 4px;
                font-size: 9pt;
            }
            QListWidget::item {
                padding: 6px 8px;
                margin-bottom: 2px;
                border-radius: 4px;
                border-left: 3px solid transparent;
            }
            QListWidget::item:hover {
                background-color: #1e293b;
            }
            QListWidget::item:selected {
                background-color: #1e3a8a;
                color: #ffffff;
                font-weight: bold;
                border-left: 3px solid #38bdf8;
            }
        """)
        self.layer_list.currentItemChanged.connect(self._on_layer_selection_changed)
        self.layer_list.itemDoubleClicked.connect(lambda item: self._on_toggle_visibility())
        l_layout.addWidget(self.layer_list)

        # Barra de botones de capas estilo Photoshop
        layer_btn_bar = QHBoxLayout()
        layer_btn_bar.setSpacing(4)

        self.btn_toggle_vis = QPushButton("👁 Visible")
        self.btn_toggle_vis.setToolTip("Ocultar o mostrar capa en el lienzo (Doble clic en la lista)")
        self.btn_toggle_vis.setStyleSheet("background: #334155; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
        self.btn_toggle_vis.clicked.connect(self._on_toggle_visibility)
        layer_btn_bar.addWidget(self.btn_toggle_vis)

        self.btn_add_elem = QPushButton("➕ Agregar")
        self.btn_add_elem.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
        self.btn_add_elem.clicked.connect(self._show_add_menu)
        layer_btn_bar.addWidget(self.btn_add_elem)

        self.btn_up_elem = QPushButton("▲")
        self.btn_up_elem.setToolTip("Subir capa (Z-Index +1)")
        self.btn_up_elem.setStyleSheet("background: #1e293b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
        self.btn_up_elem.clicked.connect(self._on_move_up)
        layer_btn_bar.addWidget(self.btn_up_elem)

        self.btn_down_elem = QPushButton("▼")
        self.btn_down_elem.setToolTip("Bajar capa (Z-Index -1)")
        self.btn_down_elem.setStyleSheet("background: #1e293b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
        self.btn_down_elem.clicked.connect(self._on_move_down)
        layer_btn_bar.addWidget(self.btn_down_elem)

        self.btn_del_elem = QPushButton("🗑")
        self.btn_del_elem.setToolTip("Eliminar elemento seleccionado")
        self.btn_del_elem.setStyleSheet("background: #dc2626; color: white; padding: 4px 8px; border-radius: 4px;")
        self.btn_del_elem.clicked.connect(self._on_delete_element)
        layer_btn_bar.addWidget(self.btn_del_elem)

        l_layout.addLayout(layer_btn_bar)
        main_layout.addWidget(layers_box)

        # -------------------------------------------------------------
        # 2. ÁREA DE PROPIEDADES EN SCROLL
        # -------------------------------------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        prop_container = QWidget()
        self.prop_layout = QVBoxLayout(prop_container)
        self.prop_layout.setContentsMargins(0, 0, 0, 0)
        self.prop_layout.setSpacing(8)

        # --- A. Transformación Básica ---
        geom_box = QGroupBox("📐  Geometría Canónica (1920 x 1080)")
        geom_box.setStyleSheet("QGroupBox { font-weight: bold; color: #cbd5e1; }")
        g_layout = QVBoxLayout(geom_box)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("X:"))
        self.sp_x = QDoubleSpinBox()
        self.sp_x.setRange(-2000, 4000)
        self.sp_x.valueChanged.connect(self._on_geometry_changed)
        row1.addWidget(self.sp_x)

        row1.addWidget(QLabel("Y:"))
        self.sp_y = QDoubleSpinBox()
        self.sp_y.setRange(-2000, 4000)
        self.sp_y.valueChanged.connect(self._on_geometry_changed)
        row1.addWidget(self.sp_y)
        g_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Ancho:"))
        self.sp_w = QDoubleSpinBox()
        self.sp_w.setRange(10, 4000)
        self.sp_w.valueChanged.connect(self._on_geometry_changed)
        row2.addWidget(self.sp_w)

        row2.addWidget(QLabel("Alto:"))
        self.sp_h = QDoubleSpinBox()
        self.sp_h.setRange(10, 4000)
        self.sp_h.valueChanged.connect(self._on_geometry_changed)
        row2.addWidget(self.sp_h)
        g_layout.addLayout(row2)

        # Opacidad
        row_op = QHBoxLayout()
        row_op.addWidget(QLabel("Opacidad:"))
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.valueChanged.connect(self._on_opacity_changed)
        row_op.addWidget(self.slider_opacity)
        self.lbl_opacity = QLabel("100%")
        row_op.addWidget(self.lbl_opacity)
        g_layout.addLayout(row_op)

        self.prop_layout.addWidget(geom_box)

        # --- B. Deformación de Perspectiva (Corner Pinning 4 Puntos) ---
        skew_box = QGroupBox("🔮  Deformación 4 Puntos (Perspectiva CRT)")
        skew_box.setStyleSheet("QGroupBox { font-weight: bold; color: #f59e0b; }")
        sk_layout = QVBoxLayout(skew_box)

        self.chk_skew_active = QCheckBox("Activar Deformación de Cuadrilátero")
        self.chk_skew_active.setStyleSheet("color: #fbbf24; font-weight: bold;")
        self.chk_skew_active.toggled.connect(self._on_skew_toggled)
        sk_layout.addWidget(self.chk_skew_active)

        self.btn_reset_pins = QPushButton("Restablecer a Rectángulo")
        self.btn_reset_pins.clicked.connect(self._on_reset_pins)
        sk_layout.addWidget(self.btn_reset_pins)

        self.lbl_skew_info = QLabel("Arrastra los 4 vértices circulares en el lienzo para ajustar el video o imagen al bisel del monitor.")
        self.lbl_skew_info.setWordWrap(True)
        self.lbl_skew_info.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        sk_layout.addWidget(self.lbl_skew_info)

        self.prop_layout.addWidget(skew_box)

        # --- B2. Animación del Elemento ---
        anim_box = QGroupBox("🎬  Animación Cinemática")
        anim_box.setStyleSheet("QGroupBox { font-weight: bold; color: #38bdf8; }")
        an_layout = QVBoxLayout(anim_box)

        an_layout.addWidget(QLabel("Tipo de Animación:"))
        self.cb_anim_type = QComboBox()
        self._anim_options = [
            ("Sin Animación", "none"),
            ("Deslizar desde Derecha (Flyer)", "flyer_slide_right"),
            ("Caída / Inserción Vertical (Cartucho)", "cart_drop"),
            ("Entrada Lateral con Fundido (Boxart)", "boxart_slide_fade"),
            ("Caída Superior con Rebote (Logo)", "logo_bounce"),
            ("Flotación Continua (Avatar / Nave)", "avatar_float"),
            ("Pulso Horizontal (Puntero)", "pointer_pulse"),
            ("Giro Continuo 360° (Disco / CD)", "disc_spin"),
        ]
        for label, key in self._anim_options:
            self.cb_anim_type.addItem(label, key)
        self.cb_anim_type.currentIndexChanged.connect(self._on_anim_type_changed)
        an_layout.addWidget(self.cb_anim_type)

        lbl_anim_hint = QLabel("Cuando el elemento tiene una animación activa, aparece la Línea de Tiempo debajo del lienzo para adelantar, retroceder o reproducir su movimiento.")
        lbl_anim_hint.setWordWrap(True)
        lbl_anim_hint.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        an_layout.addWidget(lbl_anim_hint)

        self.prop_layout.addWidget(anim_box)

        # --- C. Parámetros Específicos por Tipo ---
        self.spec_box = QGroupBox("⚙  Configuración Específica")
        self.spec_box.setStyleSheet("QGroupBox { font-weight: bold; color: #cbd5e1; }")
        self.spec_layout = QVBoxLayout(self.spec_box)
        self.prop_layout.addWidget(self.spec_box)

        self.prop_layout.addStretch()
        scroll.setWidget(prop_container)
        main_layout.addWidget(scroll)

    def set_project(self, project: LayoutProject | None):
        """Asigna el proyecto y regenera la lista de capas."""
        self.project = project
        self.refresh_layers()

    def refresh_layers(self):
        """Actualiza la lista visual de capas en orden de Z-Index descendente (estilo Photoshop)."""
        self._updating_ui = True
        self.layer_list.clear()
        if not self.project:
            self._updating_ui = False
            return

        sorted_elems = sorted(self.project.elements, key=lambda e: e.z_index, reverse=True)
        for elem in sorted_elems:
            type_icons = {
                "video": "🎬",
                "image": "🖼",
                "marquee": "💡",
                "wheel": "🎡",
                "cabinet": "🕹",
                "text": "🔤",
                "effect": "✨",
                "pointer": "🎯",
            }
            icon = type_icons.get(elem.type, "▫")
            eye = "👁" if elem.visible else "🚫"
            item = QListWidgetItem(f" {eye}  {icon}  {elem.name}  [Z:{elem.z_index}]")
            item.setData(Qt.UserRole, elem.id)
            if not elem.visible:
                item.setForeground(QColor("#64748b"))
            self.layer_list.addItem(item)
            if elem.id == self.current_elem_id:
                self.layer_list.setCurrentItem(item)

        self._updating_ui = False

    def _on_toggle_visibility(self):
        """Alterna la visibilidad (ojo) del elemento seleccionado."""
        if not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            elem.visible = not elem.visible
            self.refresh_layers()
            self.layer_visibility_changed.emit(elem.id, elem.visible)
            self.element_modified.emit(elem.id)

    def select_element(self, elem_id: str | None):
        """Selecciona un elemento y sincroniza los campos de inspección."""
        self.current_elem_id = elem_id
        if not self._updating_ui:
            for i in range(self.layer_list.count()):
                item = self.layer_list.item(i)
                if item.data(Qt.UserRole) == elem_id:
                    self.layer_list.setCurrentItem(item)
                    break
        self._load_element_data()

    def update_geometry_fields(self, elem_id: str):
        """Actualiza quirúrgicamente solo los campos numéricos de geometría sin reconstruir widgets."""
        if not self.project or not elem_id or self.current_elem_id != elem_id:
            return
        elem = self.project.get_element(elem_id)
        if not elem:
            return

        self._updating_ui = True
        try:
            self.sp_x.setValue(elem.x)
            self.sp_y.setValue(elem.y)
            self.sp_w.setValue(elem.w)
            self.sp_h.setValue(elem.h)
        finally:
            self._updating_ui = False

    def _load_element_data(self):
        """Carga las propiedades del elemento seleccionado en los controles."""
        if not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if not elem:
            return

        self._updating_ui = True

        self.sp_x.setValue(elem.x)
        self.sp_y.setValue(elem.y)
        self.sp_w.setValue(elem.w)
        self.sp_h.setValue(elem.h)

        op_int = int(elem.opacity * 100)
        self.slider_opacity.setValue(op_int)
        self.lbl_opacity.setText(f"{op_int}%")

        has_skew = (elem.corner_pins is not None and len(elem.corner_pins) == 4)
        self.chk_skew_active.setChecked(has_skew)

        # Sincronizar tipo de animación
        elem.has_animation()
        anim_key = elem.anim_type if elem.anim_type else "none"
        idx_anim = self.cb_anim_type.findData(anim_key)
        self.cb_anim_type.setCurrentIndex(idx_anim if idx_anim >= 0 else 0)

        # Limpiar controles específicos
        while self.spec_layout.count() > 0:
            child = self.spec_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Construir controles específicos según tipo
        if elem.type == "video":
            lbl = QLabel(f"Medio Vinculado: Video Snap ('{elem.media_key or 'video'}')")
            lbl.setStyleSheet("color: #38bdf8;")
            self.spec_layout.addWidget(lbl)

        elif elem.type == "text":
            self.spec_layout.addWidget(QLabel("Plantilla de Texto:"))
            txt_edit = QLineEdit(elem.text_template)
            txt_edit.textChanged.connect(lambda t: self._update_elem_attr("text_template", t))
            self.spec_layout.addWidget(txt_edit)

            self.spec_layout.addWidget(QLabel("Tamaño de Fuente:"))
            sp_font = QSpinBox()
            sp_font.setRange(8, 120)
            sp_font.setValue(elem.font_size)
            sp_font.valueChanged.connect(lambda v: self._update_elem_attr("font_size", v))
            self.spec_layout.addWidget(sp_font)

        elif elem.type == "wheel":
            self.spec_layout.addWidget(QLabel("Elementos Visibles en Ruleta:"))
            sp_items = QSpinBox()
            sp_items.setRange(3, 21)
            sp_items.setSingleStep(2)
            sp_items.setValue(elem.wheel_visible_items)
            sp_items.valueChanged.connect(lambda v: self._update_elem_attr("wheel_visible_items", v))
            self.spec_layout.addWidget(sp_items)

        elif elem.type == "effect":
            self.spec_layout.addWidget(QLabel("Tipo de Efecto:"))
            cb_eff = QComboBox()
            cb_eff.addItems(["scanlines", "vignette"])
            cb_eff.setCurrentText(elem.effect_type)
            cb_eff.currentTextChanged.connect(lambda t: self._update_elem_attr("effect_type", t))
            self.spec_layout.addWidget(cb_eff)

        self._updating_ui = False

    def _update_elem_attr(self, attr_name: str, value: Any):
        if self._updating_ui or not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            setattr(elem, attr_name, value)
            self.element_modified.emit(elem.id)

    def _on_geometry_changed(self):
        if self._updating_ui or not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            elem.x = self.sp_x.value()
            elem.y = self.sp_y.value()
            elem.w = self.sp_w.value()
            elem.h = self.sp_h.value()
            self.element_modified.emit(elem.id)

    def _on_opacity_changed(self, val: int):
        if self._updating_ui or not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            elem.opacity = val / 100.0
            self.lbl_opacity.setText(f"{val}%")
            self.element_modified.emit(elem.id)

    def _on_skew_toggled(self, checked: bool):
        if self._updating_ui or not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            if checked and not elem.corner_pins:
                elem.init_corner_pins()
            elif not checked:
                elem.reset_corner_pins()
            self.skew_mode_toggled.emit(checked)
            self.element_modified.emit(elem.id)

    def _on_anim_type_changed(self, index: int):
        if self._updating_ui or not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            anim_key = self.cb_anim_type.itemData(index) or "none"
            elem.anim_type = str(anim_key)
            self.element_modified.emit(elem.id)
            self.element_selected.emit(elem.id)

    def _on_reset_pins(self):
        if not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem and elem.corner_pins:
            elem.init_corner_pins()
            self.element_modified.emit(elem.id)

    def _on_layer_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        if not current:
            return
        elem_id = current.data(Qt.UserRole)
        self.select_element(elem_id)
        self.element_selected.emit(elem_id or "")

    def _show_add_menu(self):
        """Menú emergente para agregar nuevas capas visuales."""
        if not self.project:
            return
        menu = QMenu(self)
        menu.addAction("▶  Video Snap (CRT / Monitor)").triggered.connect(lambda: self._add_element_type("video"))
        menu.addAction("🖼  Imagen / Arte / Bezel").triggered.connect(lambda: self._add_element_type("image"))
        menu.addAction("💡  Marquee Superior").triggered.connect(lambda: self._add_element_type("marquee"))
        menu.addAction("🎡  Ruleta de Juegos (Wheel)").triggered.connect(lambda: self._add_element_type("wheel"))
        menu.addAction("🔤  Texto Dinámico").triggered.connect(lambda: self._add_element_type("text"))
        menu.addAction("✨  Scanlines CRT").triggered.connect(lambda: self._add_element_type("scanlines"))
        menu.addAction("🌑  Viñeta Perimetral").triggered.connect(lambda: self._add_element_type("vignette"))
        menu.exec(self.btn_add_elem.mapToGlobal(self.btn_add_elem.rect().bottomLeft()))

    def _add_element_type(self, kind: str):
        if not self.project:
            return
        new_elem = LayoutElement()
        if kind == "video":
            new_elem.name = "Pantalla Video Snap"
            new_elem.type = "video"
            new_elem.w, new_elem.h = 640, 480
            new_elem.media_key = "video"
        elif kind == "image":
            new_elem.name = "Arte / Bezel"
            new_elem.type = "image"
            new_elem.w, new_elem.h = 500, 500
        elif kind == "marquee":
            new_elem.name = "Marquee"
            new_elem.type = "marquee"
            new_elem.w, new_elem.h = 600, 180
            new_elem.media_key = "marquee"
        elif kind == "wheel":
            new_elem.name = "Ruleta de Logos"
            new_elem.type = "wheel"
            new_elem.w, new_elem.h = 450, 900
            new_elem.media_key = "wheel"
        elif kind == "text":
            new_elem.name = "Título del Juego"
            new_elem.type = "text"
            new_elem.text_template = "{title}"
            new_elem.w, new_elem.h = 600, 50
        elif kind == "scanlines":
            new_elem.name = "Scanlines CRT"
            new_elem.type = "effect"
            new_elem.effect_type = "scanlines"
            new_elem.w, new_elem.h = CANONICAL_W, CANONICAL_H
            new_elem.x, new_elem.y = 0, 0
        elif kind == "vignette":
            new_elem.name = "Viñeta Sombra"
            new_elem.type = "effect"
            new_elem.effect_type = "vignette"
            new_elem.w, new_elem.h = CANONICAL_W, CANONICAL_H
            new_elem.x, new_elem.y = 0, 0

        self.project.add_element(new_elem)
        self.refresh_layers()
        self.select_element(new_elem.id)
        self.element_added.emit(new_elem.id)

    def _on_delete_element(self):
        if not self.project or not self.current_elem_id:
            return
        eid = self.current_elem_id
        if self.project.remove_element(eid):
            self.current_elem_id = None
            self.refresh_layers()
            self.element_removed.emit(eid)

    def _on_move_up(self):
        """Sube la capa seleccionada en la pila Z."""
        if not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            elem.z_index += 15
            self.refresh_layers()
            self.layer_order_changed.emit()

    def _on_move_down(self):
        """Baja la capa seleccionada en la pila Z."""
        if not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            elem.z_index = max(elem.z_index - 15, 1)
            self.refresh_layers()
            self.layer_order_changed.emit()

