"""
Visor integrado de Manuales PDF para PlayNexus (Biblioteca, Rom Manager y Frontend Arcade).
Utiliza `PySide6.QtPdf.QPdfDocument` sin bloquear archivos en Windows (carga en memoria vía QBuffer)
y provee un respaldo limpio para abrir en el lector PDF del sistema operativo si QtPdf falta.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from playnexus.i18n import tr
from playnexus.services.controls import (
    ACTION_CLOSE_FRONTEND,
    ACTION_FRONTEND_MENU,
    ACTION_NAV_BACK,
    ACTION_NAV_DOWN,
    ACTION_NAV_LETTER,
    ACTION_NAV_LETTER_BACK,
    ACTION_NAV_LETTER_FWD,
    ACTION_NAV_STEP5,
    ACTION_NAV_STEP5_BACK,
    ACTION_NAV_STEP5_FWD,
    ACTION_NAV_UP,
    ACTION_PAGE_DOWN,
    ACTION_PAGE_UP,
    ACTION_SELECT,
    matches_action,
)
from playnexus.ui.frontend_quick_menu import _BaseBackdropOverlay


def is_qtpdf_available() -> bool:
    try:
        from PySide6.QtPdf import QPdfDocument  # noqa: F401
        return True
    except ImportError:
        return False


def _open_pdf_document_in_memory(raw_bytes: bytes, parent=None):
    """Carga un PDF desde bytes en RAM vía QBuffer para evitar bloqueos de archivo."""
    from PySide6.QtPdf import QPdfDocument

    ba = QByteArray(raw_bytes)
    buf = QBuffer(ba)
    if not buf.open(QIODevice.OpenModeFlag.ReadOnly):
        raise IOError(tr("manual.qbuffer_error", "Could not open QBuffer for the PDF."))

    doc = QPdfDocument(parent)
    doc.load(buf)
    err = doc.error()
    if (
        doc.status() == QPdfDocument.Status.Error
        or err != QPdfDocument.Error.None_
        or doc.pageCount() <= 0
    ):
        doc.close()
        buf.close()
        raise ValueError(tr("manual.invalid_pdf_error", "Invalid or empty PDF (status: {status}).", status=err))
    return doc, buf, ba


def render_pdf_first_page_pixmap(pdf_path: str | Path, target_size: QSize) -> tuple[QPixmap, int]:
    """
    Renderiza la primera página de un PDF en memoria sin bloquear el archivo en disco.
    Retorna `(QPixmap, total_pages)` (QPixmap nulo y 0 páginas si QtPdf no está o el archivo es inválido).
    """
    p = Path(pdf_path)
    if not p.is_file() or not is_qtpdf_available():
        return QPixmap(), 0
    doc = buf = _ba = None
    try:
        doc, buf, _ba = _open_pdf_document_in_memory(p.read_bytes())
        pages = int(doc.pageCount())
        pt = doc.pagePointSize(0)
        pw = max(1.0, float(pt.width()))
        ph = max(1.0, float(pt.height()))
        tw = max(64, int(target_size.width()))
        th = max(64, int(target_size.height()))
        scale = min(tw / pw, th / ph)
        render_sz = QSize(max(16, int(round(pw * scale))), max(16, int(round(ph * scale))))
        img = doc.render(0, render_sz)
        pix = QPixmap.fromImage(img) if not img.isNull() else QPixmap()
        return pix, pages
    except Exception:
        return QPixmap(), 0
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
        if buf is not None:
            try:
                buf.close()
            except Exception:
                pass


class ManualViewerCoreWidget(QWidget):
    """Widget reutilizable con renderizado PDF paginado, zoom, scroll y soporte de teclado/mando."""

    close_requested = Signal()
    pdf_path_changed = Signal(str)

    def __init__(
        self,
        db=None,
        arcade_style: bool = False,
        on_change_pdf: Callable[[], str | None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self._arcade_style = arcade_style
        self._on_change_pdf = on_change_pdf

        self._pdf_path = ""
        self._game_title = ""
        self._doc = None
        self._doc_buf: QBuffer | None = None
        self._doc_ba: QByteArray | None = None
        self._page_count = 0
        self._current_page = 0
        self._fit_mode = "width"  # "width" | "page" | "custom"
        self._zoom_factor = 1.0
        self._page_cache: OrderedDict[tuple[int, int, int, float], QPixmap] = OrderedDict()

        self._build_ui()

    def _build_ui(self):
        self.setFocusPolicy(Qt.StrongFocus)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Barra superior
        top_bar = QFrame()
        top_bar.setStyleSheet(
            "QFrame { background-color: rgba(18, 22, 34, 0.96); border: 1px solid #303952; border-radius: 10px; }"
            "QPushButton { background-color: #232a3e; color: #f1f5f9; border: 1px solid #394463; "
            "border-radius: 6px; padding: 6px 11px; font-weight: 600; }"
            "QPushButton:hover { background-color: #343f5e; border-color: #7c3aed; }"
            "QPushButton:disabled { color: #64748b; background-color: #171c29; border-color: #252c3d; }"
        )
        tb_lay = QHBoxLayout(top_bar)
        tb_lay.setContentsMargins(12, 8, 12, 8)
        tb_lay.setSpacing(8)

        self.title_lbl = QLabel(tr("manual.default_title", "📖 Game Manual"))
        self.title_lbl.setStyleSheet("color: #f8fafc; font-size: 12pt; font-weight: 700; border: none; background: transparent;")
        tb_lay.addWidget(self.title_lbl, 1)

        self.btn_prev = QPushButton(tr("manual.prev_btn", "◀ Previous"))
        self.btn_prev.setFocusPolicy(Qt.NoFocus)
        self.btn_prev.clicked.connect(self.prev_page)
        tb_lay.addWidget(self.btn_prev)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setFixedWidth(64)
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.setStyleSheet(
            "QSpinBox { background-color: #0f131f; color: #e2e8f0; border: 1px solid #3b4668; border-radius: 5px; padding: 4px; }"
        )
        self.page_spin.valueChanged.connect(self._on_spin_changed)
        tb_lay.addWidget(self.page_spin)

        self.page_total_lbl = QLabel("/ 0")
        self.page_total_lbl.setStyleSheet("color: #94a3b8; font-weight: 600; border: none; background: transparent;")
        tb_lay.addWidget(self.page_total_lbl)

        self.btn_next = QPushButton(tr("manual.next_btn", "Next ▶"))
        self.btn_next.setFocusPolicy(Qt.NoFocus)
        self.btn_next.clicked.connect(self.next_page)
        tb_lay.addWidget(self.btn_next)

        tb_lay.addSpacing(8)

        self.btn_zoom_out = QPushButton("🔍−")
        self.btn_zoom_out.setToolTip(tr("manual.zoom_out_tip", "Zoom out (-)"))
        self.btn_zoom_out.setFocusPolicy(Qt.NoFocus)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        tb_lay.addWidget(self.btn_zoom_out)

        self.btn_fit_width = QPushButton(tr("manual.fit_width_btn", "↔ Width"))
        self.btn_fit_width.setToolTip(tr("manual.fit_width_tip", "Fit to visible width (W)"))
        self.btn_fit_width.setFocusPolicy(Qt.NoFocus)
        self.btn_fit_width.clicked.connect(lambda: self.set_fit_mode("width"))
        tb_lay.addWidget(self.btn_fit_width)

        self.btn_fit_page = QPushButton(tr("manual.fit_page_btn", "⛶ Page"))
        self.btn_fit_page.setToolTip(tr("manual.fit_page_tip", "Fit full page on screen (P)"))
        self.btn_fit_page.setFocusPolicy(Qt.NoFocus)
        self.btn_fit_page.clicked.connect(lambda: self.set_fit_mode("page"))
        tb_lay.addWidget(self.btn_fit_page)

        self.btn_zoom_in = QPushButton("🔍+")
        self.btn_zoom_in.setToolTip(tr("manual.zoom_in_tip", "Zoom in (+)"))
        self.btn_zoom_in.setFocusPolicy(Qt.NoFocus)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        tb_lay.addWidget(self.btn_zoom_in)

        self.zoom_lbl = QLabel(tr("manual.fit_width_label", "Width"))
        self.zoom_lbl.setStyleSheet("color: #a5b4fc; font-weight: 700; min-width: 56px; border: none; background: transparent;")
        self.zoom_lbl.setAlignment(Qt.AlignCenter)
        tb_lay.addWidget(self.zoom_lbl)

        if self._on_change_pdf is not None:
            self.btn_change_pdf = QPushButton(tr("manual.change_pdf_btn", "📂 Change PDF…"))
            self.btn_change_pdf.setFocusPolicy(Qt.NoFocus)
            self.btn_change_pdf.clicked.connect(self._handle_change_pdf_clicked)
            tb_lay.addWidget(self.btn_change_pdf)

        self.btn_open_ext = QPushButton(tr("manual.open_ext_btn", "↗ External"))
        self.btn_open_ext.setToolTip(tr("manual.open_ext_tip", "Open PDF file with the system default viewer"))
        self.btn_open_ext.setFocusPolicy(Qt.NoFocus)
        self.btn_open_ext.clicked.connect(self.open_in_external_viewer)
        tb_lay.addWidget(self.btn_open_ext)

        self.btn_close = QPushButton(tr("manual.close_btn", "✕ Close"))
        self.btn_close.setFocusPolicy(Qt.NoFocus)
        self.btn_close.setStyleSheet(
            "QPushButton { background-color: #4c1d2e; border-color: #be123c; color: #ffe4e6; border-radius: 6px; padding: 6px 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #9f1239; }"
        )
        self.btn_close.clicked.connect(self.close_requested.emit)
        tb_lay.addWidget(self.btn_close)

        root.addWidget(top_bar)

        # Área de contenido PDF
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background-color: #0b0e17; border: 1px solid #262e45; border-radius: 10px; }"
        )
        self.page_label = QLabel(tr("manual.loading_msg", "Loading PDF manual…"))
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setStyleSheet("background-color: #0b0e17; color: #cbd5e1;")
        self.scroll_area.setWidget(self.page_label)
        root.addWidget(self.scroll_area, 1)

        # Banner de respaldo si falta QtPdf o falla la carga
        self.fallback_box = QFrame()
        self.fallback_box.setVisible(False)
        self.fallback_box.setStyleSheet(
            "QFrame { background-color: #141926; border: 1px solid #394463; border-radius: 10px; }"
        )
        fb_lay = QVBoxLayout(self.fallback_box)
        fb_lay.setAlignment(Qt.AlignCenter)
        fb_lay.setSpacing(12)
        self.fallback_lbl = QLabel()
        self.fallback_lbl.setWordWrap(True)
        self.fallback_lbl.setAlignment(Qt.AlignCenter)
        self.fallback_lbl.setStyleSheet("color: #e2e8f0; font-size: 11pt; border: none;")
        fb_lay.addWidget(self.fallback_lbl)

        self.btn_fallback_ext = QPushButton(tr("manual.open_system_pdf_btn", "📖 Open manual in system PDF viewer"))
        self.btn_fallback_ext.setFixedHeight(40)
        self.btn_fallback_ext.clicked.connect(self.open_in_external_viewer)
        fb_lay.addWidget(self.btn_fallback_ext, 0, Qt.AlignCenter)
        root.addWidget(self.fallback_box, 1)

        # Pie con ayuda de teclado y gamepad
        self.hint_lbl = QLabel(
            tr(
                "manual.shortcuts_hint",
                "Shortcuts: ◀ / ▶ or LB / RB / LT / RT to turn page · ▲ / ▼ to scroll · + / - Zoom · W / P Fit · Esc / Back Close",
            )
        )
        self.hint_lbl.setAlignment(Qt.AlignCenter)
        self.hint_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt; padding: 2px;")
        root.addWidget(self.hint_lbl)

    def _close_document(self):
        self._page_cache.clear()
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None
        if self._doc_buf is not None:
            try:
                self._doc_buf.close()
            except Exception:
                pass
            self._doc_buf = None
        self._doc_ba = None
        self._page_count = 0
        self._current_page = 0

    def closeEvent(self, event):
        self._close_document()
        super().closeEvent(event)

    def load_manual(self, pdf_path: str | Path, game_title: str = "") -> bool:
        """Carga un PDF en el visor (usando QBuffer en RAM para no bloquear el archivo)."""
        self._close_document()
        self._pdf_path = str(pdf_path or "").strip()
        self._game_title = str(game_title or "").strip()

        p = Path(self._pdf_path) if self._pdf_path else None
        fname = p.name if p else tr("manual.no_manual_name", "No manual")
        prefix = f"📖 {self._game_title} — {fname}" if self._game_title else f"📖 {fname}"
        self.title_lbl.setText(prefix)

        if not p or not p.is_file():
            self._show_fallback(
                tr(
                    "manual.not_found_msg",
                    "No valid PDF manual file was found for this game.\n"
                    "You can assign it from the game details, in 'Media Folders', or from the Rom Manager.",
                )
            )
            self._sync_nav_controls()
            return False

        if not is_qtpdf_available():
            self._show_fallback(
                tr(
                    "manual.qtpdf_missing_msg",
                    "The optional module <b>PySide6.QtPdf</b> is not available in this environment.\n\n"
                    "Found file: <b>{filename}</b>\n"
                    "Use the button below to open the manual in Windows' default PDF reader.",
                    filename=p.name,
                )
            )
            self._sync_nav_controls()
            return False

        try:
            doc, buf, ba = _open_pdf_document_in_memory(p.read_bytes(), parent=self)
            self._doc_ba = ba
            self._doc_buf = buf
            self._doc = doc
            self._page_count = int(doc.pageCount())
            self._current_page = 0
            self.fallback_box.setVisible(False)
            self.scroll_area.setVisible(True)
            self._sync_nav_controls()
            self._render_current_page()
            return True
        except Exception as exc:
            self._close_document()
            self._show_fallback(
                tr(
                    "manual.render_error_msg",
                    "Could not render the PDF internally:\n{error}\n\n"
                    "You can try opening it with the operating system's PDF reader.",
                    error=exc,
                )
            )
            self._sync_nav_controls()
            return False

    def _show_fallback(self, text: str):
        self.scroll_area.setVisible(False)
        self.fallback_lbl.setText(text)
        self.fallback_box.setVisible(True)

    def _sync_nav_controls(self):
        has_pages = self._page_count > 0
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, self._page_count))
        self.page_spin.setValue(self._current_page + 1 if has_pages else 1)
        self.page_spin.setEnabled(has_pages)
        self.page_spin.blockSignals(False)

        self.page_total_lbl.setText(f"/ {self._page_count}")
        self.btn_prev.setEnabled(has_pages and self._current_page > 0)
        self.btn_next.setEnabled(has_pages and self._current_page < (self._page_count - 1))
        self.btn_zoom_in.setEnabled(has_pages)
        self.btn_zoom_out.setEnabled(has_pages)
        self.btn_fit_width.setEnabled(has_pages)
        self.btn_fit_page.setEnabled(has_pages)
        self.btn_open_ext.setEnabled(bool(self._pdf_path and Path(self._pdf_path).is_file()))

        if self._fit_mode == "width":
            self.zoom_lbl.setText(tr("manual.fit_width_label", "Width"))
        elif self._fit_mode == "page":
            self.zoom_lbl.setText(tr("manual.fit_page_label", "Page"))
        else:
            self.zoom_lbl.setText(f"{int(round(self._zoom_factor * 100))}%")

    def _compute_target_pixel_size(self, page_index: int) -> QSize:
        assert self._doc is not None
        pt = self._doc.pagePointSize(page_index)
        pw = max(100.0, float(pt.width()))
        ph = max(100.0, float(pt.height()))

        vp = self.scroll_area.viewport().size()
        vw = max(320, vp.width() - 28)
        vh = max(240, vp.height() - 24)

        if self._fit_mode == "width":
            scale = vw / pw
        elif self._fit_mode == "page":
            scale = min(vw / pw, vh / ph)
        else:
            scale = (vw / pw) * self._zoom_factor

        scale = max(0.25, min(6.0, scale))
        return QSize(max(64, int(round(pw * scale))), max(64, int(round(ph * scale))))

    def _render_current_page(self):
        if self._doc is None or self._page_count <= 0:
            return
        idx = max(0, min(self._page_count - 1, self._current_page))
        self._current_page = idx

        logical_sz = self._compute_target_pixel_size(idx)
        try:
            dpr = max(1.0, float(self.devicePixelRatioF()))
        except Exception:
            dpr = 1.0

        cache_key = (idx, logical_sz.width(), logical_sz.height(), round(dpr, 2))
        pix = self._page_cache.get(cache_key)
        if pix is None:
            render_sz = QSize(
                max(64, int(round(logical_sz.width() * dpr))),
                max(64, int(round(logical_sz.height() * dpr))),
            )
            img = self._doc.render(idx, render_sz)
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                pix.setDevicePixelRatio(dpr)
            else:
                pix = QPixmap()
            if not pix.isNull():
                self._page_cache[cache_key] = pix
                while len(self._page_cache) > 12:
                    self._page_cache.popitem(last=False)

        self.page_label.setPixmap(pix)
        self.page_label.resize(logical_sz)
        self.scroll_area.verticalScrollBar().setValue(0)
        self._sync_nav_controls()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._doc is not None and self._page_count > 0:
            self._render_current_page()

    def _on_spin_changed(self, value: int):
        self.go_to_page(value - 1)

    def go_to_page(self, page_index: int):
        if self._page_count <= 0:
            return
        target = max(0, min(self._page_count - 1, int(page_index)))
        if target != self._current_page:
            self._current_page = target
            self._render_current_page()

    def next_page(self):
        if self._current_page < (self._page_count - 1):
            self.go_to_page(self._current_page + 1)

    def prev_page(self):
        if self._current_page > 0:
            self.go_to_page(self._current_page - 1)

    def set_fit_mode(self, mode: str):
        self._fit_mode = mode if mode in ("width", "page", "custom") else "width"
        if self._fit_mode != "custom":
            self._zoom_factor = 1.0
        self._render_current_page()

    def zoom_in(self):
        self._fit_mode = "custom"
        self._zoom_factor = min(3.0, round(self._zoom_factor + 0.2, 2))
        self._render_current_page()

    def zoom_out(self):
        self._fit_mode = "custom"
        self._zoom_factor = max(0.5, round(self._zoom_factor - 0.2, 2))
        self._render_current_page()

    def open_in_external_viewer(self):
        if self._pdf_path and Path(self._pdf_path).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._pdf_path).resolve())))

    def _handle_change_pdf_clicked(self):
        if not self._on_change_pdf:
            return
        new_path = self._on_change_pdf()
        if new_path:
            self.pdf_path_changed.emit(new_path)
            self.load_manual(new_path, game_title=self._game_title)

    # ------------------------------------------------------------------
    # NAVEGACIÓN POR TECLADO Y MANDO
    # ------------------------------------------------------------------
    def handle_trigger(self, trigger_name: str) -> bool:
        trig = str(trigger_name or "").strip().upper()
        if trig in ("LT", "LB"):
            self.prev_page()
            return True
        if trig in ("RT", "RB"):
            self.next_page()
            return True
        return False

    def handle_action(self, action_id: str) -> bool:
        if action_id in (ACTION_NAV_BACK, ACTION_CLOSE_FRONTEND, ACTION_FRONTEND_MENU):
            self.close_requested.emit()
            return True
        if action_id in (ACTION_NAV_LETTER_BACK, ACTION_NAV_STEP5_BACK, ACTION_PAGE_UP):
            self.prev_page()
            return True
        if action_id in (ACTION_NAV_LETTER_FWD, ACTION_NAV_LETTER, ACTION_NAV_STEP5_FWD, ACTION_NAV_STEP5, ACTION_PAGE_DOWN):
            self.next_page()
            return True
        if action_id == ACTION_NAV_UP:
            sb = self.scroll_area.verticalScrollBar()
            if sb.value() > sb.minimum():
                sb.setValue(max(sb.minimum(), sb.value() - 90))
            else:
                self.prev_page()
            return True
        if action_id == ACTION_NAV_DOWN:
            sb = self.scroll_area.verticalScrollBar()
            if sb.value() < sb.maximum():
                sb.setValue(min(sb.maximum(), sb.value() + 90))
            else:
                self.next_page()
            return True
        if action_id == ACTION_SELECT:
            self.set_fit_mode("page" if self._fit_mode == "width" else "width")
            return True
        return False

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Escape, Qt.Key_Backspace) or (
            self.db is not None and (matches_action(event, ACTION_NAV_BACK, self.db) or matches_action(event, ACTION_FRONTEND_MENU, self.db))
        ):
            self.close_requested.emit()
            event.accept()
            return
        if key in (Qt.Key_Right, Qt.Key_PageDown, Qt.Key_Space):
            self.next_page()
            event.accept()
            return
        if key in (Qt.Key_Left, Qt.Key_PageUp):
            self.prev_page()
            event.accept()
            return
        if key == Qt.Key_Home:
            self.go_to_page(0)
            event.accept()
            return
        if key == Qt.Key_End:
            if self._page_count > 0:
                self.go_to_page(self._page_count - 1)
            event.accept()
            return
        if key in (Qt.Key_Up,):
            self.handle_action(ACTION_NAV_UP)
            event.accept()
            return
        if key in (Qt.Key_Down,):
            self.handle_action(ACTION_NAV_DOWN)
            event.accept()
            return
        if key in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_in()
            event.accept()
            return
        if key == Qt.Key_Minus:
            self.zoom_out()
            event.accept()
            return
        if key == Qt.Key_W:
            self.set_fit_mode("width")
            event.accept()
            return
        if key == Qt.Key_P:
            self.set_fit_mode("page")
            event.accept()
            return
        super().keyPressEvent(event)


class ManualViewerDialog(QDialog):
    """Ventana modal de visor de Manual PDF para Biblioteca y Rom Manager."""

    def __init__(
        self,
        pdf_path: str | Path,
        game_title: str = "",
        db=None,
        on_change_pdf: Callable[[], str | None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("manual.dialog_title", "PDF Manual — {title}", title=game_title or Path(pdf_path).stem))
        self.resize(980, 760)
        self.setMinimumSize(700, 520)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self.viewer = ManualViewerCoreWidget(db=db, arcade_style=False, on_change_pdf=on_change_pdf, parent=self)
        self.viewer.close_requested.connect(self.accept)
        lay.addWidget(self.viewer)
        self.viewer.load_manual(pdf_path, game_title=game_title)


class ManualViewerOverlay(_BaseBackdropOverlay):
    """Overlay fullscreen transparente para leer el manual en el Frontend Arcade sin pausar el video."""

    close_requested = Signal()

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(38, 28, 38, 28)

        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: rgba(12, 16, 26, 0.94); border: 2px solid rgba(124, 58, 237, 0.85); border-radius: 14px; }"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 14, 14, 12)

        self.viewer = ManualViewerCoreWidget(db=self.db, arcade_style=True, parent=card)
        self.viewer.close_requested.connect(self.close_requested.emit)
        card_lay.addWidget(self.viewer)
        outer.addWidget(card)

    def open_manual(self, pdf_path: str | Path, game_title: str = ""):
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        self.viewer.load_manual(pdf_path, game_title=game_title)
        self.show()
        self.raise_()
        self.viewer.setFocus()

    def handle_action(self, action_id: str) -> bool:
        return self.viewer.handle_action(action_id)

    def handle_trigger(self, trigger_name: str) -> bool:
        return self.viewer.handle_trigger(trigger_name)

    def keyPressEvent(self, event):
        self.viewer.keyPressEvent(event)
