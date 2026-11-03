"""
Diálogo de confirmación para salir de PlayNexus.
Diseñado para modo arcade y frontend a pantalla completa:
- Totalmente navegable mediante Teclado y Mando / Gamepad (Flechas, Enter/A para confirmar, Escape/B para cancelar).
- Estilo visual oscuro acorde al resto del frontend.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QColor


class ExitConfirmDialog(QDialog):
    """
    Diálogo modal de confirmación de salida de PlayNexus.
    Soporta controles de gamepad y teclado arcade.
    """
    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Salir de PlayNexus")
        self.setFixedSize(480, 260)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Contenedor con borde y sombra estética
        card = QFrame(self)
        card.setStyleSheet("""
            QFrame {
                background-color: #1a1d27;
                border: 2px solid #5d48d9;
                border-radius: 14px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 24)
        card_layout.setSpacing(16)

        # Icono y título
        header_layout = QHBoxLayout()
        icon_lbl = QLabel("🚪")
        icon_lbl.setStyleSheet("font-size: 26pt; background: transparent; border: none;")
        header_layout.addWidget(icon_lbl)
        header_layout.addSpacing(10)

        title_layout = QVBoxLayout()
        title_lbl = QLabel("¿Deseas salir de PlayNexus?")
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title_lbl.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        sub_lbl = QLabel("Se cerrará la aplicación y volverás a Windows.")
        sub_lbl.setFont(QFont("Segoe UI", 10))
        sub_lbl.setStyleSheet("color: #9aa5b8; background: transparent; border: none;")
        title_layout.addWidget(title_lbl)
        title_layout.addWidget(sub_lbl)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        card_layout.addLayout(header_layout)
        card_layout.addStretch()

        # Botones de acción
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #2b3145;
                color: #ffffff;
                border: 2px solid #3d4560;
                border-radius: 8px;
                padding: 10px 24px;
            }
            QPushButton:hover, QPushButton:focus {
                background-color: #3d4560;
                border-color: #7866ed;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_exit = QPushButton("Salir del Frontend")
        self.btn_exit.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_exit.setCursor(Qt.PointingHandCursor)
        self.btn_exit.setStyleSheet("""
            QPushButton {
                background-color: #d9383a;
                color: #ffffff;
                border: 2px solid #b32a2c;
                border-radius: 8px;
                padding: 10px 24px;
            }
            QPushButton:hover, QPushButton:focus {
                background-color: #ef4444;
                border-color: #f87171;
            }
        """)
        self.btn_exit.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_exit)
        card_layout.addLayout(btn_layout)

        main_layout.addWidget(card)

        # Foco por defecto en Cancelar para evitar cierres accidentales
        self.btn_cancel.setFocus()

        # Conectar mando si el gestor está disponible
        self._gamepad_conn = None
        try:
            from playnexus.services.gamepad import get_gamepad_manager
            mgr = get_gamepad_manager(self.db)
            if mgr:
                self._gamepad_conn = mgr.action_triggered.connect(self._on_gamepad_action)
        except Exception:
            pass

    def _on_gamepad_action(self, action_id: str):
        from playnexus.services.controls import (
            ACTION_NAV_LEFT, ACTION_NAV_RIGHT, ACTION_SELECT, ACTION_NAV_BACK, ACTION_CLOSE_FRONTEND
        )
        if action_id in (ACTION_NAV_LEFT, "nav_letter_back"):
            self.btn_cancel.setFocus()
        elif action_id in (ACTION_NAV_RIGHT, "nav_letter_fwd"):
            self.btn_exit.setFocus()
        elif action_id == ACTION_SELECT:
            if self.btn_exit.hasFocus():
                self.accept()
            else:
                self.reject()
        elif action_id in (ACTION_NAV_BACK, ACTION_CLOSE_FRONTEND):
            self.reject()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_Up):
            self.btn_cancel.setFocus()
            event.accept()
            return
        elif key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Tab):
            if self.btn_cancel.hasFocus():
                self.btn_exit.setFocus()
            else:
                self.btn_cancel.setFocus()
            event.accept()
            return
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if self.btn_exit.hasFocus():
                self.accept()
            else:
                self.reject()
            event.accept()
            return
        elif key == Qt.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._gamepad_conn:
            try:
                from playnexus.services.gamepad import get_gamepad_manager
                mgr = get_gamepad_manager(self.db)
                if mgr:
                    mgr.action_triggered.disconnect(self._on_gamepad_action)
            except Exception:
                pass
        super().closeEvent(event)

