"""
Menú lateral izquierdo desplegable (estilo YouTube / TecnoService) para el Configurador de PlayNexus.

Características:
- Modo desplegado (~236 px): botón '☰' + logo PlayNexus, encabezados de grupo con línea degradada,
  iconos vectoriales coloreados por categoría + etiqueta de texto, indicador activo lateral y punto luminoso.
- Modo colapsado (~64 px): riel compacto solo de iconos centrados con barra activa lateral y tooltips.
- Animación suave de ancho (180 ms, OutCubic) y API compatible con QTabWidget para integración limpia.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

EXPANDED_WIDTH = 236
COLLAPSED_WIDTH = 64


def _strip_leading_emoji(text: str) -> str:
    """Limpia prefijos de emoji heredados de pestañas antiguas dejando solo el texto legible."""
    s = (text or "").strip()
    if "  " in s:
        left, right = s.split("  ", 1)
        if len(left) <= 3 and right.strip():
            return right.strip()
    if s and ord(s[0]) > 0x2000:
        parts = s.split(" ", 1)
        if len(parts) == 2 and parts[1].strip():
            return parts[1].strip()
    return s


def _draw_nav_icon(painter: QPainter, rect: QRectF, icon_id: str, color: QColor) -> None:
    """Dibuja iconos vectoriales nítidos e independientes de DPI para cada sección del Configurador."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color, 1.75, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    cx = rect.center().x()
    cy = rect.center().y()
    w = rect.width()
    h = rect.height()

    if icon_id == "library":
        # Mando / Gamepad estilizado
        body = QRectF(cx - w * 0.36, cy - h * 0.22, w * 0.72, h * 0.44)
        painter.drawRoundedRect(body, 5.0, 5.0)
        # Cruceta izquierda
        dx = cx - w * 0.17
        painter.drawLine(QPointF(dx - 3.2, cy), QPointF(dx + 3.2, cy))
        painter.drawLine(QPointF(dx, cy - 3.2), QPointF(dx, cy + 3.2))
        # Botones derechos
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx + w * 0.15, cy - 2.2), 1.7, 1.7)
        painter.drawEllipse(QPointF(cx + w * 0.22, cy + 2.2), 1.7, 1.7)

    elif icon_id == "frontend":
        # Pantalla panorámica con triángulo Play
        scr = QRectF(cx - w * 0.36, cy - h * 0.28, w * 0.72, h * 0.46)
        painter.drawRoundedRect(scr, 3.2, 3.2)
        painter.drawLine(QPointF(cx - w * 0.16, cy + h * 0.28), QPointF(cx + w * 0.16, cy + h * 0.28))
        painter.drawLine(QPointF(cx, cy + h * 0.18), QPointF(cx, cy + h * 0.28))
        tri = QPolygonF([
            QPointF(cx - 2.5, cy - h * 0.13),
            QPointF(cx - 2.5, cy + h * 0.03),
            QPointF(cx + 4.2, cy - h * 0.05),
        ])
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(tri)

    elif icon_id == "rom_manager":
        # Maletín / Caja de herramientas multimedia
        box = QRectF(cx - w * 0.34, cy - h * 0.18, w * 0.68, h * 0.46)
        painter.drawRoundedRect(box, 3.2, 3.2)
        handle = QRectF(cx - w * 0.14, cy - h * 0.30, w * 0.28, h * 0.14)
        path = QPainterPath()
        path.moveTo(handle.left(), box.top())
        path.lineTo(handle.left(), handle.top() + 2.0)
        path.quadTo(handle.left(), handle.top(), handle.left() + 2.0, handle.top())
        path.lineTo(handle.right() - 2.0, handle.top())
        path.quadTo(handle.right(), handle.top(), handle.right(), handle.top() + 2.0)
        path.lineTo(handle.right(), box.top())
        painter.drawPath(path)
        painter.drawLine(QPointF(box.left() + 2.0, cy + h * 0.03), QPointF(box.right() - 2.0, cy + h * 0.03))

    elif icon_id == "xml_converter":
        # Rayo eléctrico (conversión ultrarrápida)
        bolt = QPolygonF([
            QPointF(cx + w * 0.06, cy - h * 0.34),
            QPointF(cx - w * 0.22, cy + h * 0.02),
            QPointF(cx - w * 0.01, cy + h * 0.02),
            QPointF(cx - w * 0.08, cy + h * 0.34),
            QPointF(cx + w * 0.22, cy - h * 0.04),
            QPointF(cx + w * 0.01, cy - h * 0.04),
        ])
        fill_c = QColor(color)
        fill_c.setAlpha(60)
        painter.setBrush(fill_c)
        painter.drawPolygon(bolt)

    elif icon_id == "emulators":
        # Palanca Arcade clásica (base + mástil + bola superior)
        base = QRectF(cx - w * 0.32, cy + h * 0.14, w * 0.64, h * 0.16)
        painter.drawRoundedRect(base, 2.5, 2.5)
        painter.drawLine(QPointF(cx, cy - h * 0.10), QPointF(cx, cy + h * 0.14))
        fill_c = QColor(color)
        fill_c.setAlpha(75)
        painter.setBrush(fill_c)
        painter.drawEllipse(QPointF(cx, cy - h * 0.20), w * 0.15, h * 0.15)

    elif icon_id == "layout_studio":
        # Capas / Lienzo de diseño visual
        back = QRectF(cx - w * 0.32, cy - h * 0.28, w * 0.50, h * 0.40)
        front = QRectF(cx - w * 0.14, cy - h * 0.10, w * 0.48, h * 0.40)
        painter.drawRoundedRect(back, 2.8, 2.8)
        fill_c = QColor(color)
        fill_c.setAlpha(50)
        painter.setBrush(fill_c)
        painter.drawRoundedRect(front, 2.8, 2.8)

    else:  # "settings"
        # Engranaje de precisión
        r_outer = min(w, h) * 0.33
        r_inner = min(w, h) * 0.23
        pts: list[QPointF] = []
        teeth = 8
        for i in range(teeth * 2):
            ang = (i * math.pi) / teeth
            rad = r_outer if (i % 2 == 0) else r_inner
            pts.append(QPointF(cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
        painter.drawPolygon(QPolygonF(pts))
        painter.drawEllipse(QPointF(cx, cy), min(w, h) * 0.11, min(w, h) * 0.11)

    painter.restore()


class _HamburgerButton(QPushButton):
    """Botón circular '☰' estilo YouTube / TecnoService para alternar colapsado y desplegado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._hovered = False

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        if self._hovered:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 24))
            p.drawEllipse(QRectF(2, 2, 36, 36))
            bar_color = QColor("#00c6ff")
        else:
            bar_color = QColor(226, 232, 240, 205)

        pen = QPen(bar_color, 2.0, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        for y in (14.0, 20.0, 26.0):
            p.drawLine(QPointF(11.5, y), QPointF(28.5, y))
        p.end()


class _SidebarGroupHeader(QWidget):
    """Encabezado de grupo en mayúsculas con línea degradada derecha (estilo TecnoService)."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text = text.upper()
        self.setFixedHeight(28)

    def set_title(self, text: str) -> None:
        self._text = text.upper()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        f = QFont("Segoe UI", 7)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.1)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 112))

        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(self._text)
        x_text = 16
        y_base = int((self.height() + fm.ascent() - fm.descent()) / 2) + 2
        p.drawText(x_text, y_base, self._text)

        line_x1 = x_text + tw + 10
        line_x2 = self.width() - 14
        if line_x2 > line_x1 + 8:
            line_y = self.height() / 2.0 + 2.0
            grad = QLinearGradient(line_x1, line_y, line_x2, line_y)
            grad.setColorAt(0.0, QColor(255, 255, 255, 42))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(QPen(grad, 1.0))
            p.drawLine(QPointF(line_x1, line_y), QPointF(line_x2, line_y))
        p.end()


class _SidebarNavButton(QPushButton):
    """Ítem de navegación lateral con modo expandido (icono + texto) y modo riel (solo icono)."""

    def __init__(
        self,
        label: str,
        icon_id: str,
        accent_hex: str,
        parent=None,
    ):
        super().__init__(parent)
        self._label = _strip_leading_emoji(label)
        self._icon_id = icon_id
        self._accent = QColor(accent_hex)
        self._active = False
        self._expanded = True
        self._hovered = False

        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._sync_tooltip()

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self.update()

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded != expanded:
            self._expanded = expanded
            self._sync_tooltip()
            self.update()

    def set_label(self, label: str) -> None:
        self._label = _strip_leading_emoji(label)
        self._sync_tooltip()
        self.update()

    def _sync_tooltip(self) -> None:
        self.setToolTip("" if self._expanded else self._label)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        pill = QRectF(8.0, 2.0, max(24.0, w - 16.0), h - 4.0)
        active_cyan = QColor("#00c6ff")

        # 1. Fondo y borde de la píldora
        if self._active:
            grad = QLinearGradient(pill.left(), pill.top(), pill.right(), pill.top())
            grad.setColorAt(0.0, QColor(0, 198, 255, 56))
            grad.setColorAt(1.0, QColor(93, 72, 217, 24))
            p.setBrush(grad)
            p.setPen(QPen(QColor(0, 198, 255, 96), 1.0))
            p.drawRoundedRect(pill, 10.0, 10.0)

            # Barra lateral brillante izquierda ("Acá estás parado" estilo TecnoService)
            glow_bar = QRectF(0.0, h * 0.22, 4.0, h * 0.56)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 198, 255, 70))
            p.drawRoundedRect(glow_bar.adjusted(0.0, -2.0, 3.0, 2.0), 3.0, 3.0)
            p.setBrush(active_cyan)
            p.drawRoundedRect(glow_bar, 2.0, 2.0)
        elif self._hovered:
            p.setBrush(QColor(255, 255, 255, 19))
            p.setPen(QPen(QColor(255, 255, 255, 24), 1.0))
            p.drawRoundedRect(pill, 10.0, 10.0)

        # 2. Cajita redondeada del icono (30 x 30)
        icon_size = 30.0
        icon_y = (h - icon_size) / 2.0
        if self._expanded and w > 96.0:
            icon_x = pill.left() + 9.0
        else:
            icon_x = (w - icon_size) / 2.0
        icon_box = QRectF(icon_x, icon_y, icon_size, icon_size)

        p.setPen(Qt.NoPen)
        if self._active:
            p.setBrush(QColor(0, 198, 255, 58))
            icon_color = active_cyan
        elif self._hovered:
            p.setBrush(QColor(255, 255, 255, 30))
            icon_color = self._accent.lighter(118)
        else:
            p.setBrush(QColor(255, 255, 255, 11))
            icon_color = self._accent
        p.drawRoundedRect(icon_box, 8.0, 8.0)

        _draw_nav_icon(p, icon_box.adjusted(3.0, 3.0, -3.0, -3.0), self._icon_id, icon_color)

        # 3. Etiqueta de texto y punto luminoso derecho (solo cuando hay ancho desplegado)
        if self._expanded and w > 110.0:
            text_left = icon_box.right() + 11.0
            dot_space = 18.0 if self._active else 8.0
            text_right = pill.right() - dot_space
            if text_right > text_left + 12.0:
                font = QFont("Segoe UI", 9)
                font.setWeight(QFont.Bold if self._active else QFont.Medium)
                p.setFont(font)
                if self._active or self._hovered:
                    p.setPen(QColor("#ffffff"))
                else:
                    p.setPen(QColor(226, 232, 240, 190))

                avail_w = int(text_right - text_left)
                elided = p.fontMetrics().elidedText(self._label, Qt.ElideRight, avail_w)
                p.drawText(
                    QRectF(text_left, 0.0, avail_w, h),
                    Qt.AlignVCenter | Qt.AlignLeft,
                    elided,
                )

            if self._active:
                dot_c = QPointF(pill.right() - 11.0, h / 2.0)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 198, 255, 80))
                p.drawEllipse(dot_c, 5.5, 5.5)
                p.setBrush(active_cyan)
                p.drawEllipse(dot_c, 3.3, 3.3)

        p.end()


class CollapsibleSidebar(QFrame):
    """Panel lateral izquierdo colapsable con cabecera de marca, grupos y pie de versión."""

    page_selected = Signal(int)
    toggled_expanded = Signal(bool)

    def __init__(
        self,
        logo_path: Path | None = None,
        version_text: str = "",
        toggle_tooltip: str = "Toggle navigation menu",
        expanded: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._expanded = bool(expanded)
        self._version_full = version_text.strip()
        self._version_short = self._version_full.split(" ")[0] if self._version_full else ""
        self._buttons: list[_SidebarNavButton] = []
        self._headers: list[_SidebarGroupHeader] = []
        self._last_top_group = ""
        self._last_bottom_group = ""

        self.setObjectName("pnSidebar")
        self.setStyleSheet(
            "QFrame#pnSidebar {"
            "  background-color: #0e121b;"
            "  border-right: 1px solid #22293c;"
            "}"
        )

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._apply_width)

        root_vbox = QVBoxLayout(self)
        root_vbox.setContentsMargins(0, 8, 0, 8)
        root_vbox.setSpacing(4)

        # Cabecera: Botón Hamburguesa '☰' + Logo PlayNexus
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(12, 2, 10, 4)
        brand_row.setSpacing(8)

        self.toggle_btn = _HamburgerButton(self)
        self.toggle_btn.setToolTip(toggle_tooltip)
        self.toggle_btn.clicked.connect(self.toggle_expanded)
        brand_row.addWidget(self.toggle_btn, 0, Qt.AlignVCenter)

        self.logo_lbl = QLabel()
        self.logo_lbl.setStyleSheet("background: transparent; border: none;")
        self._has_logo = False
        if logo_path and logo_path.is_file():
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                scaled = pix.scaled(QSize(156, 38), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.logo_lbl.setPixmap(scaled)
                self._has_logo = True
        if not self._has_logo:
            self.logo_lbl.setText("PlayNexus")
            self.logo_lbl.setStyleSheet(
                "color: #f1f5f9; font-size: 12pt; font-weight: 800; letter-spacing: 0.5px; background: transparent;"
            )
        brand_row.addWidget(self.logo_lbl, 1, Qt.AlignVCenter | Qt.AlignLeft)
        root_vbox.addLayout(brand_row)

        top_sep = QFrame()
        top_sep.setFixedHeight(1)
        top_sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.07); border: none; margin: 2px 10px;")
        root_vbox.addWidget(top_sep)

        # Área desplazable para los ítems superiores (por si la ventana se achica verticalmente)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        scroll_body = QWidget()
        scroll_body.setStyleSheet("background: transparent;")
        self._nav_vbox = QVBoxLayout(scroll_body)
        self._nav_vbox.setContentsMargins(0, 2, 0, 4)
        self._nav_vbox.setSpacing(2)

        self._top_items_vbox = QVBoxLayout()
        self._top_items_vbox.setContentsMargins(0, 0, 0, 0)
        self._top_items_vbox.setSpacing(2)
        self._nav_vbox.addLayout(self._top_items_vbox)
        self._nav_vbox.addStretch(1)

        self._bottom_items_vbox = QVBoxLayout()
        self._bottom_items_vbox.setContentsMargins(0, 0, 0, 0)
        self._bottom_items_vbox.setSpacing(2)
        self._nav_vbox.addLayout(self._bottom_items_vbox)

        scroll.setWidget(scroll_body)
        root_vbox.addWidget(scroll, 1)

        # Pie de versión
        bot_sep = QFrame()
        bot_sep.setFixedHeight(1)
        bot_sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.07); border: none; margin: 2px 10px;")
        root_vbox.addWidget(bot_sep)

        self.version_lbl = QLabel()
        self.version_lbl.setAlignment(Qt.AlignCenter)
        self.version_lbl.setStyleSheet(
            "color: #a78bfa; font-weight: 700; font-size: 8.5pt; padding: 3px 6px; background: transparent;"
        )
        root_vbox.addWidget(self.version_lbl)

        self._sync_expanded_visuals(animate=False)

    def _apply_width(self, val) -> None:
        w = int(val)
        self.setFixedWidth(w)

    def _sync_expanded_visuals(self, animate: bool) -> None:
        target_w = EXPANDED_WIDTH if self._expanded else COLLAPSED_WIDTH
        self.logo_lbl.setVisible(self._expanded)
        for hdr in self._headers:
            hdr.setVisible(self._expanded)
        for btn in self._buttons:
            btn.set_expanded(self._expanded)

        if self._expanded:
            self.version_lbl.setText(self._version_full)
            self.version_lbl.setToolTip("")
        else:
            self.version_lbl.setText(self._version_short)
            self.version_lbl.setToolTip(self._version_full)

        self._anim.stop()
        if animate:
            self._anim.setStartValue(self.width())
            self._anim.setEndValue(target_w)
            self._anim.start()
        else:
            self.setFixedWidth(target_w)

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        expanded_b = bool(expanded)
        if self._expanded == expanded_b:
            return
        self._expanded = expanded_b
        self._sync_expanded_visuals(animate=animate)
        self.toggled_expanded.emit(self._expanded)

    def toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded, animate=True)

    def add_nav_item(
        self,
        label: str,
        icon_id: str,
        accent_hex: str,
        group_title: str = "",
        bottom: bool = False,
    ) -> int:
        target_layout = self._bottom_items_vbox if bottom else self._top_items_vbox
        last_grp = self._last_bottom_group if bottom else self._last_top_group

        if group_title and group_title != last_grp:
            hdr = _SidebarGroupHeader(group_title, self)
            hdr.setVisible(self._expanded)
            target_layout.addWidget(hdr)
            self._headers.append(hdr)
            if bottom:
                self._last_bottom_group = group_title
            else:
                self._last_top_group = group_title

        idx = len(self._buttons)
        btn = _SidebarNavButton(label=label, icon_id=icon_id, accent_hex=accent_hex, parent=self)
        btn.set_expanded(self._expanded)
        if idx == 0:
            btn.set_active(True)
        btn.clicked.connect(lambda _checked=False, i=idx: self.page_selected.emit(i))
        target_layout.addWidget(btn)
        self._buttons.append(btn)
        return idx

    def set_active_index(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.set_active(i == index)


class SidebarShellWidget(QWidget):
    """
    Contenedor central [CollapsibleSidebar | QStackedWidget] con interfaz compatible
    con QTabWidget (currentIndex, setCurrentIndex, setCurrentWidget, widget, currentChanged).
    """

    currentChanged = Signal(int)
    toggled_expanded = Signal(bool)

    def __init__(
        self,
        logo_path: Path | None = None,
        version_text: str = "",
        toggle_tooltip: str = "Toggle navigation menu",
        expanded: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)

        self.sidebar = CollapsibleSidebar(
            logo_path=logo_path,
            version_text=version_text,
            toggle_tooltip=toggle_tooltip,
            expanded=expanded,
            parent=self,
        )
        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("QStackedWidget { background-color: #15171e; border: none; }")

        hbox.addWidget(self.sidebar)
        hbox.addWidget(self.stack, 1)

        self.sidebar.page_selected.connect(self.setCurrentIndex)
        self.sidebar.toggled_expanded.connect(self.toggled_expanded.emit)
        self.stack.currentChanged.connect(self._on_stack_changed)

    def add_page(
        self,
        widget: QWidget,
        label: str,
        *,
        icon_id: str,
        accent_hex: str = "#38bdf8",
        group_title: str = "",
        bottom: bool = False,
    ) -> int:
        idx = self.stack.addWidget(widget)
        self.sidebar.add_nav_item(
            label=label,
            icon_id=icon_id,
            accent_hex=accent_hex,
            group_title=group_title,
            bottom=bottom,
        )
        self.sidebar.set_active_index(self.stack.currentIndex())
        return idx

    def _on_stack_changed(self, index: int) -> None:
        self.sidebar.set_active_index(index)
        self.currentChanged.emit(index)

    def currentIndex(self) -> int:
        return self.stack.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            self.sidebar.set_active_index(index)

    def currentWidget(self) -> QWidget | None:
        return self.stack.currentWidget()

    def setCurrentWidget(self, widget: QWidget) -> None:
        idx = self.stack.indexOf(widget)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def widget(self, index: int) -> QWidget | None:
        return self.stack.widget(index)

    def count(self) -> int:
        return self.stack.count()

    def indexOf(self, widget: QWidget) -> int:
        return self.stack.indexOf(widget)

    def is_expanded(self) -> bool:
        return self.sidebar.is_expanded()

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        self.sidebar.set_expanded(expanded, animate=animate)
