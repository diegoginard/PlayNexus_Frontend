from __future__ import annotations

import re
import ast
from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QTextFormat, QSyntaxHighlighter,
    QTextCharFormat, QTextCursor
)
from PySide6.QtWidgets import (
    QWidget, QPlainTextEdit, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame
)


class PythonHighlighter(QSyntaxHighlighter):
    """Resaltador de sintaxis Python para el editor de código de layouts."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#f472b6"))  # Rosa fucsia elegante
        keyword_format.setFontWeight(QFont.Bold)
        keywords = [
            r"\bdef\b", r"\bclass\b", r"\breturn\b", r"\bself\b", r"\bimport\b",
            r"\bfrom\b", r"\bas\b", r"\bif\b", r"\belif\b", r"\belse\b",
            r"\bfor\b", r"\bwhile\b", r"\bin\b", r"\btry\b", r"\bexcept\b",
            r"\bfinally\b", r"\bwith\b", r"\bpass\b", r"\bTrue\b", r"\bFalse\b",
            r"\bNone\b", r"\band\b", r"\bor\b", r"\bnot\b", r"\bis\b", r"\blambda\b"
        ]
        for kw in keywords:
            self.rules.append((re.compile(kw), keyword_format))

        # Tipos y clases estándar
        type_format = QTextCharFormat()
        type_format.setForeground(QColor("#38bdf8"))  # Celeste brillante
        type_format.setFontWeight(QFont.Bold)
        types = [
            r"\bBaseLayout\b", r"\bThemeLayout\b", r"\bQWidget\b", r"\bQPainter\b",
            r"\bQRect\b", r"\bQRectF\b", r"\bQColor\b", r"\bQFont\b", r"\bQPointF\b",
            r"\bQTransform\b", r"\bQPolygonF\b", r"\bQTimer\b", r"\bQPixmap\b",
            r"\bQImage\b", r"\bQMediaPlayer\b", r"\bQVideoSink\b", r"\bint\b",
            r"\bfloat\b", r"\bstr\b", r"\blist\b", r"\bdict\b", r"\btuple\b"
        ]
        for t in types:
            self.rules.append((re.compile(t), type_format))

        # Números
        num_format = QTextCharFormat()
        num_format.setForeground(QColor("#fbbf24"))  # Ámbar
        self.rules.append((re.compile(r"\b\d+(\.\d+)?\b"), num_format))

        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#a3e635"))  # Verde lima
        self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format))
        self.rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), string_format))

        # Decoradores
        decorator_format = QTextCharFormat()
        decorator_format.setForeground(QColor("#c084fc"))  # Púrpura
        self.rules.append((re.compile(r"@[a-zA-Z_]\w*"), decorator_format))

        # Comentarios
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#64748b"))  # Gris pizarra
        comment_format.setFontItalic(True)
        self.rules.append((re.compile(r"#[^\n]*"), comment_format))

    def highlightBlock(self, text: str):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0d1117;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                selection-background-color: #264f78;
            }
        """)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def line_number_area_width(self):
        digits = max(1, len(str(self.blockCount())))
        space = 20 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#161b22")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#090d16"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#6e7681"))
                painter.setFont(self.font())
                painter.drawText(
                    0, int(top), self.line_number_area.width() - 8,
                    self.fontMetrics().height(), Qt.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1


class LayoutCodeEditorWidget(QWidget):
    """
    Panel de edición de código Python en tiempo real con resaltado de sintaxis,
    validador AST y botón de Hot Reload para aplicar al vuelo.
    """
    code_applied = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Barra superior con acciones
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel("💻  theme_layout.py (Live Editor)")
        title_lbl.setStyleSheet("font-weight: bold; color: #cbd5e1; font-size: 10pt;")
        top_bar.addWidget(title_lbl)

        top_bar.addStretch()

        self.status_lbl = QLabel("✓ Sintaxis Válida")
        self.status_lbl.setStyleSheet("color: #4ade80; font-size: 9pt; font-weight: bold;")
        top_bar.addWidget(self.status_lbl)

        self.btn_apply = QPushButton("⚡ Aplicar al Canvas (Hot Reload)")
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8b5cf6, stop:1 #6d28d9);
                color: #ffffff;
                font-weight: bold;
                border-radius: 5px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #7c3aed;
            }
        """)
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        top_bar.addWidget(self.btn_apply)

        layout.addLayout(top_bar)

        # Editor de texto con numeración de líneas
        self.editor = CodeEditor(self)
        self.highlighter = PythonHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._validate_syntax)
        layout.addWidget(self.editor)

    def set_code(self, code: str):
        """Asigna el contenido del código."""
        self.editor.setPlainText(code)
        self._validate_syntax()

    def get_code(self) -> str:
        """Obtiene el texto del código."""
        return self.editor.toPlainText()

    def _validate_syntax(self) -> bool:
        """Verifica la validez sintáctica de Python mediante ast.parse."""
        code = self.editor.toPlainText()
        try:
            ast.parse(code)
            self.status_lbl.setText("✓ Sintaxis Válida")
            self.status_lbl.setStyleSheet("color: #4ade80; font-size: 9pt; font-weight: bold;")
            self.btn_apply.setEnabled(True)
            return True
        except SyntaxError as e:
            self.status_lbl.setText(f"⚠ Error Línea {e.lineno}: {e.msg}")
            self.status_lbl.setStyleSheet("color: #f87171; font-size: 9pt; font-weight: bold;")
            return False

    def _on_apply_clicked(self):
        if self._validate_syntax():
            self.code_applied.emit(self.editor.toPlainText())
