from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QGroupBox, QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox,
    QSlider, QCheckBox, QScrollArea, QFrame, QMenu, QColorDialog
)

from playnexus.i18n import tr
from playnexus.services.library import humanize_column_label
from playnexus.ui.layout_studio.models import LayoutElement, LayoutProject, CANONICAL_W, CANONICAL_H
from playnexus.ui.shaders import (
    SHADER_PRESETS,
    SHADER_TARGETS,
    normalize_shader_preset,
    normalize_shader_target,
)
from playnexus.ui.particles import PARTICLE_PRESETS, normalize_particle_preset

_SHADER_PRESET_I18N: dict[str, tuple[str, str]] = {
    "none": ("studio.shader_preset.none", "No Shader (Native)"),
    "crt_aperture": ("studio.shader_preset.crt_aperture", "CRT Aperture (Curvature + Trinitron + Scanlines)"),
    "crt_bloom": ("studio.shader_preset.crt_bloom", "CRT Bloom (Warm Phosphor Halo + CRT)"),
    "lcd_handheld": ("studio.shader_preset.lcd_handheld", "LCD Handheld (Portable Subpixel Matrix)"),
    "vhs_arcade": ("studio.shader_preset.vhs_arcade", "VHS / Analog Arcade (Aberration + Noise)"),
}

_SHADER_TARGET_I18N: dict[str, tuple[str, str]] = {
    "tv_rect": ("studio.shader_target.tv_rect", "Screen / Video Only (TV_RECT)"),
    "global": ("studio.shader_target.global", "Global Screen Post-Process"),
}

_PARTICLE_PRESET_I18N: dict[str, tuple[str, str]] = {
    "none": ("studio.particle_preset.none", "No Particles"),
    "arcade_sparks": ("studio.particle_preset.arcade_sparks", "Arcade Sparks (Luminous Rise)"),
    "neon_dust": ("studio.particle_preset.neon_dust", "Neon Dust (Ambient Float)"),
    "snow_drift": ("studio.particle_preset.snow_drift", "Snow / Sparkles (Soft Fall)"),
    "starfield_parallax": ("studio.particle_preset.starfield_parallax", "Parallax Starfield"),
}

_EFFECT_TYPE_OPTIONS: list[tuple[str, str, str]] = [
    ("scanlines", "studio.effect_type.scanlines", "Scanlines"),
    ("vignette", "studio.effect_type.vignette", "Vignette"),
    ("crt_aperture", "studio.effect_type.crt_aperture", "CRT Aperture"),
    ("crt_bloom", "studio.effect_type.crt_bloom", "CRT Bloom"),
    ("lcd_handheld", "studio.effect_type.lcd_handheld", "LCD Handheld"),
    ("vhs_arcade", "studio.effect_type.vhs_arcade", "VHS / Analog Arcade"),
]


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
    project_effects_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: LayoutProject | None = None
        self.current_elem_id: str | None = None
        self._updating_ui = False
        self._extra_template_vars: list[str] = []
        self._txt_var_combo: QComboBox | None = None

        self._init_ui()

    def set_available_custom_vars(self, vars_list: list[str]):
        cleaned = [str(v).strip() for v in (vars_list or []) if str(v).strip()]
        self._extra_template_vars = list(dict.fromkeys(cleaned))
        if self._txt_var_combo is not None:
            try:
                self._populate_var_combo(self._txt_var_combo)
            except RuntimeError:
                self._txt_var_combo = None

    def _populate_var_combo(self, combo: QComboBox):
        with QSignalBlocker(combo):
            combo.clear()
            combo.addItem(tr("studio.inspector.insert_var_placeholder", "＋ Insert variable…"), "")
            std_vars = [
                ("{title}", f"{{title}} — {tr('layout.col_title', 'Title')}"),
                ("{rom_name}", f"{{rom_name}} — {tr('layout.col_rom_file', 'ROM / File')}"),
                ("{year}", f"{{year}} — {tr('layout.col_year', 'Year')}"),
                ("{manufacturer}", f"{{manufacturer}} — {tr('layout.col_manufacturer', 'Manufacturer')}"),
                ("{genre}", f"{{genre}} — {tr('layout.col_genre', 'Genre')}"),
                ("{players}", f"{{players}} — {tr('layout.col_players', 'Players')}"),
                ("{bios}", f"{{bios}} — {tr('layout.col_bios', 'BIOS')}"),
                ("{sourcefile}", f"{{sourcefile}} — {tr('layout.col_sourcefile', 'Sourcefile')}"),
                ("{cloneof}", f"{{cloneof}} — {tr('layout.col_cloneof', 'Clone of')}"),
                ("{index}/{total}", "{index}/{total}"),
            ]
            for token, label in std_vars:
                combo.addItem(label, token)
            for v in self._extra_template_vars:
                tok = f"{{{v}}}"
                combo.addItem(f"✨ {tok} — {humanize_column_label(v)}", tok)
            combo.setCurrentIndex(0)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(8)

        # -------------------------------------------------------------
        # 1. GESTOR DE CAPAS Y ELEMENTOS (ESTILO PHOTOSHOP)
        # -------------------------------------------------------------
        layers_box = QGroupBox(tr("studio.inspector.layers_group", "📑  Layout Layers (Photoshop Style)"))
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

        self.btn_toggle_vis = QPushButton(tr("studio.inspector.btn_visible", "👁 Visible"))
        self.btn_toggle_vis.setToolTip(
            tr("studio.inspector.btn_visible_tip", "Hide or show layer on canvas (Double-click in list)")
        )
        self.btn_toggle_vis.setStyleSheet("background: #334155; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
        self.btn_toggle_vis.clicked.connect(self._on_toggle_visibility)
        layer_btn_bar.addWidget(self.btn_toggle_vis)

        self.btn_add_elem = QPushButton(tr("studio.inspector.btn_add", "➕ Add"))
        self.btn_add_elem.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
        self.btn_add_elem.clicked.connect(self._show_add_menu)
        layer_btn_bar.addWidget(self.btn_add_elem)

        self.btn_up_elem = QPushButton("▲")
        self.btn_up_elem.setToolTip(tr("studio.inspector.btn_up_tip", "Move layer up (Z-Index +1)"))
        self.btn_up_elem.setStyleSheet("background: #1e293b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
        self.btn_up_elem.clicked.connect(self._on_move_up)
        layer_btn_bar.addWidget(self.btn_up_elem)

        self.btn_down_elem = QPushButton("▼")
        self.btn_down_elem.setToolTip(tr("studio.inspector.btn_down_tip", "Move layer down (Z-Index -1)"))
        self.btn_down_elem.setStyleSheet("background: #1e293b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
        self.btn_down_elem.clicked.connect(self._on_move_down)
        layer_btn_bar.addWidget(self.btn_down_elem)

        self.btn_del_elem = QPushButton("🗑")
        self.btn_del_elem.setToolTip(tr("studio.inspector.btn_del_tip", "Delete selected element"))
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
        geom_box = QGroupBox(tr("studio.inspector.geom_group", "📐  Canonical Geometry (1920 x 1080)"))
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
        row2.addWidget(QLabel(tr("studio.inspector.width", "Width:")))
        self.sp_w = QDoubleSpinBox()
        self.sp_w.setRange(10, 4000)
        self.sp_w.valueChanged.connect(self._on_geometry_changed)
        row2.addWidget(self.sp_w)

        row2.addWidget(QLabel(tr("studio.inspector.height", "Height:")))
        self.sp_h = QDoubleSpinBox()
        self.sp_h.setRange(10, 4000)
        self.sp_h.valueChanged.connect(self._on_geometry_changed)
        row2.addWidget(self.sp_h)
        g_layout.addLayout(row2)

        # Opacidad
        row_op = QHBoxLayout()
        row_op.addWidget(QLabel(tr("studio.inspector.opacity", "Opacity:")))
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
        skew_box = QGroupBox(tr("studio.inspector.skew_group", "🔮  4-Point Warp (CRT Perspective)"))
        skew_box.setStyleSheet("QGroupBox { font-weight: bold; color: #f59e0b; }")
        sk_layout = QVBoxLayout(skew_box)

        self.chk_skew_active = QCheckBox(tr("studio.inspector.skew_enable", "Enable Quad Corner Warp"))
        self.chk_skew_active.setStyleSheet("color: #fbbf24; font-weight: bold;")
        self.chk_skew_active.toggled.connect(self._on_skew_toggled)
        sk_layout.addWidget(self.chk_skew_active)

        self.btn_reset_pins = QPushButton(tr("studio.inspector.skew_reset", "Reset to Rectangle"))
        self.btn_reset_pins.clicked.connect(self._on_reset_pins)
        sk_layout.addWidget(self.btn_reset_pins)

        self.lbl_skew_info = QLabel(
            tr(
                "studio.inspector.skew_info",
                "Drag the 4 circular corner vertices on the canvas to fit the video or image to the monitor bezel.",
            )
        )
        self.lbl_skew_info.setWordWrap(True)
        self.lbl_skew_info.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        sk_layout.addWidget(self.lbl_skew_info)

        self.prop_layout.addWidget(skew_box)

        # --- B2. Animación del Elemento ---
        anim_box = QGroupBox(tr("studio.inspector.anim_group", "🎬  Cinematic Animation"))
        anim_box.setStyleSheet("QGroupBox { font-weight: bold; color: #38bdf8; }")
        an_layout = QVBoxLayout(anim_box)

        an_layout.addWidget(QLabel(tr("studio.inspector.anim_entry_label", "Entry Transition:")))
        self.cb_anim_entry = QComboBox()
        self._anim_entry_options = [
            (tr("studio.inspector.anim_entry.none", "No Entry"), "none"),
            (tr("studio.inspector.anim_entry.disc_rise", "Rise from Bottom & Park (CD / Disc)"), "disc_rise"),
            (tr("studio.inspector.anim_entry.cart_drop", "Vertical Drop / Insert (Cartridge)"), "cart_drop"),
            (tr("studio.inspector.anim_entry.boxart_slide_fade", "Side Slide with Fade (Boxart)"), "boxart_slide_fade"),
            (tr("studio.inspector.anim_entry.flyer_slide_right", "Slide from Right (Flyer)"), "flyer_slide_right"),
            (tr("studio.inspector.anim_entry.logo_bounce", "Top Drop with Bounce (Logo)"), "logo_bounce"),
        ]
        for label, key in self._anim_entry_options:
            self.cb_anim_entry.addItem(label, key)
        self.cb_anim_entry.currentIndexChanged.connect(self._on_anim_type_changed)
        an_layout.addWidget(self.cb_anim_entry)

        an_layout.addWidget(QLabel(tr("studio.inspector.anim_loop_label", "Continuous Effect (Loop):")))
        self.cb_anim_loop = QComboBox()
        self._anim_loop_options = [
            (tr("studio.inspector.anim_loop.none", "No Continuous Loop"), "none"),
            (tr("studio.inspector.anim_loop.disc_spin", "Continuous 360° Spin (Disc / CD)"), "disc_spin"),
            (tr("studio.inspector.anim_loop.avatar_float", "Continuous Float (Avatar / Ship)"), "avatar_float"),
            (tr("studio.inspector.anim_loop.pointer_pulse", "Horizontal Pulse (Pointer)"), "pointer_pulse"),
        ]
        for label, key in self._anim_loop_options:
            self.cb_anim_loop.addItem(label, key)
        self.cb_anim_loop.currentIndexChanged.connect(self._on_anim_type_changed)
        an_layout.addWidget(self.cb_anim_loop)

        # Alias de compatibilidad hacia cb_anim_entry
        self.cb_anim_type = self.cb_anim_entry

        lbl_anim_hint = QLabel(
            tr(
                "studio.inspector.anim_hint",
                "When the element has an active animation, the Timeline appears below the canvas to scrub forward, backward, or play its motion.",
            )
        )
        lbl_anim_hint.setWordWrap(True)
        lbl_anim_hint.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        an_layout.addWidget(lbl_anim_hint)

        self.prop_layout.addWidget(anim_box)

        # --- C. Parámetros Específicos por Tipo ---
        self.spec_box = QGroupBox(tr("studio.inspector.spec_group", "⚙  Specific Settings"))
        self.spec_box.setStyleSheet("QGroupBox { font-weight: bold; color: #cbd5e1; }")
        self.spec_layout = QVBoxLayout(self.spec_box)
        self.prop_layout.addWidget(self.spec_box)

        # --- D. Efectos Globales del Layout (Shaders GPU y Partículas) ---
        self.fx_box = QGroupBox(tr("studio.inspector.fx_group", "✨  Layout GPU Shaders & Particles"))
        self.fx_box.setStyleSheet("QGroupBox { font-weight: bold; color: #c4b5fd; }")
        fx_layout = QVBoxLayout(self.fx_box)

        fx_layout.addWidget(QLabel(tr("studio.inspector.shader_label", "Retro Shader (GPU GLSL / Fallback):")))
        self.cb_project_shader = QComboBox()
        for key, label in SHADER_PRESETS:
            i18n_pair = _SHADER_PRESET_I18N.get(key)
            disp = tr(i18n_pair[0], i18n_pair[1]) if i18n_pair else label
            self.cb_project_shader.addItem(disp, key)
        self.cb_project_shader.currentIndexChanged.connect(self._on_project_effects_changed)
        fx_layout.addWidget(self.cb_project_shader)

        fx_layout.addWidget(QLabel(tr("studio.inspector.shader_target_label", "Shader Target:")))
        self.cb_project_shader_target = QComboBox()
        for key, label in SHADER_TARGETS:
            i18n_pair = _SHADER_TARGET_I18N.get(key)
            disp = tr(i18n_pair[0], i18n_pair[1]) if i18n_pair else label
            self.cb_project_shader_target.addItem(disp, key)
        self.cb_project_shader_target.currentIndexChanged.connect(self._on_project_effects_changed)
        fx_layout.addWidget(self.cb_project_shader_target)

        fx_layout.addWidget(QLabel(tr("studio.inspector.particle_label", "Ambient Particles:")))
        self.cb_project_particle = QComboBox()
        for key, label in PARTICLE_PRESETS:
            i18n_pair = _PARTICLE_PRESET_I18N.get(key)
            disp = tr(i18n_pair[0], i18n_pair[1]) if i18n_pair else label
            self.cb_project_particle.addItem(disp, key)
        self.cb_project_particle.currentIndexChanged.connect(self._on_project_effects_changed)
        fx_layout.addWidget(self.cb_project_particle)

        self.prop_layout.addWidget(self.fx_box)

        self.prop_layout.addStretch()
        scroll.setWidget(prop_container)
        main_layout.addWidget(scroll)

    def set_project(self, project: LayoutProject | None):
        """Asigna el proyecto y regenera la lista de capas."""
        self.project = project
        self._sync_project_effects_ui()
        self.refresh_layers()

    def _sync_project_effects_ui(self):
        self._updating_ui = True
        try:
            sh = normalize_shader_preset(getattr(self.project, "shader_preset", "none"))
            tg = normalize_shader_target(getattr(self.project, "shader_target", "tv_rect"))
            pt = normalize_particle_preset(getattr(self.project, "particle_preset", "none"))
            for cb, val in (
                (self.cb_project_shader, sh),
                (self.cb_project_shader_target, tg),
                (self.cb_project_particle, pt),
            ):
                idx = cb.findData(val)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
            self.cb_project_shader_target.setEnabled(sh != "none")
        finally:
            self._updating_ui = False

    def _on_project_effects_changed(self):
        if self._updating_ui or not self.project:
            return
        sh = str(self.cb_project_shader.currentData() or "none")
        tg = str(self.cb_project_shader_target.currentData() or "tv_rect")
        pt = str(self.cb_project_particle.currentData() or "none")
        self.project.shader_preset = sh
        self.project.shader_target = tg
        self.project.particle_preset = pt
        self.cb_project_shader_target.setEnabled(sh != "none")
        self.project_effects_changed.emit()

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

        # Sincronizar tipos de animación (Entrada y Bucle continuo)
        elem.has_animation()
        raw_anim = elem.anim_type if elem.anim_type else "none"
        tokens = [a.strip() for a in raw_anim.replace("+", ",").split(",") if a.strip()]

        entry_tokens = {"disc_rise", "cart_drop", "boxart_slide_fade", "flyer_slide_right", "logo_bounce"}
        loop_tokens = {"disc_spin", "avatar_float", "pointer_pulse"}

        active_entry = "none"
        active_loop = "none"
        for tok in tokens:
            if tok in entry_tokens:
                active_entry = tok
            elif tok in loop_tokens:
                active_loop = tok

        idx_entry = self.cb_anim_entry.findData(active_entry)
        self.cb_anim_entry.setCurrentIndex(idx_entry if idx_entry >= 0 else 0)

        idx_loop = self.cb_anim_loop.findData(active_loop)
        self.cb_anim_loop.setCurrentIndex(idx_loop if idx_loop >= 0 else 0)

        # Limpiar controles específicos
        while self.spec_layout.count() > 0:
            child = self.spec_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Construir controles específicos según tipo
        if elem.type == "video":
            lbl = QLabel(
                tr(
                    "studio.inspector.linked_video",
                    "Linked Media: Video Snap ('{media_key}')",
                    media_key=elem.media_key or "video",
                )
            )
            lbl.setStyleSheet("color: #38bdf8;")
            self.spec_layout.addWidget(lbl)

        elif elem.type == "text":
            self.spec_layout.addWidget(QLabel(tr("studio.inspector.text_template", "Text Template:")))
            txt_edit = QLineEdit(elem.text_template)
            txt_edit.textChanged.connect(lambda t: self._update_elem_attr("text_template", t))
            self.spec_layout.addWidget(txt_edit)

            var_combo = QComboBox()
            self._txt_var_combo = var_combo
            self._populate_var_combo(var_combo)

            def _on_insert_var(idx: int):
                if idx <= 0:
                    return
                token = str(var_combo.itemData(idx) or "")
                with QSignalBlocker(var_combo):
                    var_combo.setCurrentIndex(0)
                if token:
                    txt_edit.setFocus()
                    txt_edit.insert(token)

            var_combo.activated.connect(_on_insert_var)
            self.spec_layout.addWidget(var_combo)

            self.spec_layout.addWidget(QLabel(tr("studio.inspector.font_size", "Font Size:")))
            sp_font = QSpinBox()
            sp_font.setRange(8, 120)
            sp_font.setValue(elem.font_size)
            sp_font.valueChanged.connect(lambda v: self._update_elem_attr("font_size", v))
            self.spec_layout.addWidget(sp_font)

        elif elem.type == "wheel":
            self.spec_layout.addWidget(QLabel(tr("studio.inspector.wheel_visible_items", "Visible Wheel Items:")))
            sp_items = QSpinBox()
            sp_items.setRange(3, 21)
            sp_items.setSingleStep(2)
            sp_items.setValue(elem.wheel_visible_items)
            sp_items.valueChanged.connect(lambda v: self._update_elem_attr("wheel_visible_items", v))
            self.spec_layout.addWidget(sp_items)

        elif elem.type == "effect":
            self.spec_layout.addWidget(QLabel(tr("studio.inspector.effect_type", "Effect Type:")))
            cb_eff = QComboBox()
            for eff_key, i18n_key, fallback_en in _EFFECT_TYPE_OPTIONS:
                cb_eff.addItem(tr(i18n_key, fallback_en), eff_key)
            idx_eff = cb_eff.findData(elem.effect_type)
            if idx_eff >= 0:
                cb_eff.setCurrentIndex(idx_eff)
            elif elem.effect_type:
                cb_eff.addItem(elem.effect_type, elem.effect_type)
                cb_eff.setCurrentIndex(cb_eff.count() - 1)
            cb_eff.currentIndexChanged.connect(
                lambda _i, c=cb_eff: self._update_elem_attr("effect_type", c.currentData())
            )
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

    def _on_anim_type_changed(self, index: int = 0):
        if self._updating_ui or not self.project or not self.current_elem_id:
            return
        elem = self.project.get_element(self.current_elem_id)
        if elem:
            entry = self.cb_anim_entry.currentData() or "none"
            loop = self.cb_anim_loop.currentData() or "none"
            parts = [p for p in (entry, loop) if p and p != "none"]
            elem.anim_type = ",".join(parts) if parts else "none"
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
        menu.addAction(
            tr("studio.inspector.add_menu.video", "▶  Video Snap (CRT / Monitor)")
        ).triggered.connect(lambda: self._add_element_type("video"))
        menu.addAction(
            tr("studio.inspector.add_menu.image", "🖼  Image / Artwork / Bezel")
        ).triggered.connect(lambda: self._add_element_type("image"))
        menu.addAction(
            tr("studio.inspector.add_menu.marquee", "💡  Top Marquee")
        ).triggered.connect(lambda: self._add_element_type("marquee"))
        menu.addAction(
            tr("studio.inspector.add_menu.wheel", "🎡  Game Wheel")
        ).triggered.connect(lambda: self._add_element_type("wheel"))
        menu.addAction(
            tr("studio.inspector.add_menu.text", "🔤  Dynamic Text")
        ).triggered.connect(lambda: self._add_element_type("text"))
        menu.addAction(
            tr("studio.inspector.add_menu.scanlines", "✨  CRT Scanlines")
        ).triggered.connect(lambda: self._add_element_type("scanlines"))
        menu.addAction(
            tr("studio.inspector.add_menu.vignette", "🌑  Perimeter Vignette")
        ).triggered.connect(lambda: self._add_element_type("vignette"))
        menu.exec(self.btn_add_elem.mapToGlobal(self.btn_add_elem.rect().bottomLeft()))

    def _add_element_type(self, kind: str):
        if not self.project:
            return
        new_elem = LayoutElement()
        if kind == "video":
            new_elem.name = tr("studio.elem.video_snap_screen", "Video Snap Screen")
            new_elem.type = "video"
            new_elem.w, new_elem.h = 640, 480
            new_elem.media_key = "video"
        elif kind == "image":
            new_elem.name = tr("studio.elem.art_bezel", "Artwork / Bezel")
            new_elem.type = "image"
            new_elem.w, new_elem.h = 500, 500
        elif kind == "marquee":
            new_elem.name = tr("studio.media.marquee", "Marquee")
            new_elem.type = "marquee"
            new_elem.w, new_elem.h = 600, 180
            new_elem.media_key = "marquee"
        elif kind == "wheel":
            new_elem.name = tr("studio.elem.logo_wheel", "Logo Wheel")
            new_elem.type = "wheel"
            new_elem.w, new_elem.h = 450, 900
            new_elem.media_key = "wheel"
        elif kind == "text":
            new_elem.name = tr("studio.elem.game_title", "Game Title")
            new_elem.type = "text"
            new_elem.text_template = "{title}"
            new_elem.w, new_elem.h = 600, 50
        elif kind == "scanlines":
            new_elem.name = tr("studio.elem.crt_scanlines", "CRT Scanlines")
            new_elem.type = "effect"
            new_elem.effect_type = "scanlines"
            new_elem.w, new_elem.h = CANONICAL_W, CANONICAL_H
            new_elem.x, new_elem.y = 0, 0
        elif kind == "vignette":
            new_elem.name = tr("studio.elem.vignette_shadow", "Shadow Vignette")
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

