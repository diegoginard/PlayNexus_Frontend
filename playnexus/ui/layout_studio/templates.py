from __future__ import annotations

from typing import Any
from playnexus.ui.layout_studio.models import LayoutElement, LayoutProject, CANONICAL_W, CANONICAL_H


def create_arcade_cabinet_template(name: str = "Mi Arcade") -> LayoutProject:
    """Crea una plantilla de Mueble Arcade con Video Snap CRT, Marquee y Ruleta."""
    proj = LayoutProject(
        name=name,
        description="Layout de Mueble Arcade interactivo con Marquee y Ruleta vertical",
        media_requirements=[
            {"key": "video", "label": "Video Snaps", "extensions": [".mp4", ".mkv", ".avi", ".webm"], "required": True},
            {"key": "wheel", "label": "Wheel Logos", "extensions": [".png", ".webp"], "required": True},
            {"key": "marquee", "label": "Marquee", "extensions": [".png", ".jpg", ".webp"], "required": False},
        ],
    )

    # 1. Fondo
    proj.add_element(LayoutElement(
        id="bg_image",
        name="Fondo / Wallpaper",
        type="image",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=1,
        resource_path="bg.jpg",
    ))

    # 2. Video Snap (Pantalla CRT del mueble)
    proj.add_element(LayoutElement(
        id="video_snap",
        name="Video Snap (Pantalla CRT)",
        type="video",
        x=330, y=340, w=640, h=480,
        z_index=5,
        media_key="video",
    ))

    # 3. Efecto Scanlines sobre la pantalla
    proj.add_element(LayoutElement(
        id="screen_scanlines",
        name="Efecto Scanlines CRT",
        type="effect",
        x=330, y=340, w=640, h=480,
        z_index=6,
        effect_type="scanlines",
        effect_intensity=0.35,
        effect_param=4.0,
    ))

    # 4. Bezel / Marco de la pantalla
    proj.add_element(LayoutElement(
        id="bezel",
        name="Bezel / Marco Pantalla",
        type="image",
        x=280, y=290, w=740, h=580,
        z_index=10,
        resource_path="bezel.png",
    ))

    # 5. Marquee Iluminado superior
    proj.add_element(LayoutElement(
        id="marquee",
        name="Marquee Superior",
        type="marquee",
        x=290, y=50, w=720, h=200,
        z_index=12,
        media_key="marquee",
        resource_path="marquee.png",
    ))

    # 6. Ruleta de Ruedas lateral
    proj.add_element(LayoutElement(
        id="wheel_list",
        name="Ruleta de Juegos",
        type="wheel",
        x=1380, y=60, w=500, h=960,
        z_index=20,
        media_key="wheel",
        wheel_orientation="vertical",
        wheel_visible_items=9,
        wheel_item_spacing=95.0,
    ))

    # 7. Contador y Título inferior
    proj.add_element(LayoutElement(
        id="title_text",
        name="Título del Juego",
        type="text",
        x=100, y=960, w=900, h=60,
        z_index=25,
        text_template="{title}",
        font_size=32,
        text_color="#f1f5f9",
    ))

    proj.add_element(LayoutElement(
        id="counter_text",
        name="Contador de Juegos",
        type="text",
        x=1400, y=1020, w=450, h=40,
        z_index=25,
        text_template="{index} / {total}",
        font_size=20,
        text_color="#94a3b8",
        text_align="right",
    ))

    return proj


def create_retro_console_template(name: str = "Mi Consola") -> LayoutProject:
    """Crea una plantilla de Consola de Videojuegos con TV y Cartucho."""
    proj = LayoutProject(
        name=name,
        description="Layout temático de Consola Retro con TV a la izquierda y Ruleta Conveyor a la derecha",
        media_requirements=[
            {"key": "video", "label": "Video Snaps", "extensions": [".mp4", ".mkv", ".avi", ".webm"], "required": True},
            {"key": "wheel", "label": "Wheel Logos", "extensions": [".png", ".webp"], "required": True},
            {"key": "cartart", "label": "Cartuchos", "extensions": [".png", ".webp"], "required": True},
            {"key": "boxart", "label": "Box Art / Cajas", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
        ],
    )

    # Fondo
    proj.add_element(LayoutElement(
        id="bg_image",
        name="Fondo de Sala Retro",
        type="image",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=1,
        resource_path="bg.jpg",
    ))

    # TV Snap Video
    proj.add_element(LayoutElement(
        id="tv_video",
        name="Pantalla TV (Video Snap)",
        type="video",
        x=100, y=200, w=620, h=470,
        z_index=5,
        media_key="video",
    ))

    # Mueble TV
    proj.add_element(LayoutElement(
        id="tv_bezel",
        name="Televisor de Tubo (TV Bezel)",
        type="image",
        x=60, y=140, w=710, h=600,
        z_index=10,
        resource_path="tv.png",
    ))

    # Consola
    proj.add_element(LayoutElement(
        id="console_art",
        name="Consola",
        type="image",
        x=820, y=600, w=450, h=400,
        z_index=12,
        resource_path="console.png",
    ))

    # Ruleta Curva
    proj.add_element(LayoutElement(
        id="wheel_list",
        name="Ruleta de Logos",
        type="wheel",
        x=1360, y=50, w=520, h=980,
        z_index=20,
        media_key="wheel",
        wheel_orientation="vertical",
        wheel_visible_items=9,
        wheel_curvature=0.15,
    ))

    # Título
    proj.add_element(LayoutElement(
        id="title_text",
        name="Título del Juego",
        type="text",
        x=80, y=940, w=670, h=50,
        z_index=25,
        text_template="{title}",
        font_size=28,
        text_color="#38bdf8",
    ))

    return proj


def create_minimalist_fullscreen_template(name: str = "Minimalista Fullscreen") -> LayoutProject:
    """Crea una plantilla minimalista de video a pantalla completa con scanlines y rueda flotante."""
    proj = LayoutProject(
        name=name,
        description="Layout minimalista con video snap a pantalla completa y ruleta estilizada",
        media_requirements=[
            {"key": "video", "label": "Video Snaps", "extensions": [".mp4", ".mkv", ".avi", ".webm"], "required": True},
            {"key": "wheel", "label": "Wheel Logos", "extensions": [".png", ".webp"], "required": True},
        ],
    )

    # Video fullscreen
    proj.add_element(LayoutElement(
        id="fullscreen_video",
        name="Video Snap Pantalla Completa",
        type="video",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=1,
        media_key="video",
    ))

    # Scanlines globales
    proj.add_element(LayoutElement(
        id="scanlines_overlay",
        name="Scanlines CRT",
        type="effect",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=5,
        effect_type="scanlines",
        effect_intensity=0.25,
        effect_param=3.0,
    ))

    # Viñeta oscura perimetral
    proj.add_element(LayoutElement(
        id="vignette_overlay",
        name="Viñeta Sombra Perimetral",
        type="effect",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=6,
        effect_type="vignette",
        effect_intensity=0.55,
        effect_param=50.0,
    ))

    # Ruleta flotante
    proj.add_element(LayoutElement(
        id="floating_wheel",
        name="Ruleta Flotante",
        type="wheel",
        x=1420, y=50, w=460, h=980,
        z_index=15,
        media_key="wheel",
        wheel_orientation="vertical",
        wheel_visible_items=9,
    ))

    # Barra inferior con título
    proj.add_element(LayoutElement(
        id="title_hud",
        name="HUD Título",
        type="text",
        x=60, y=980, w=1200, h=60,
        z_index=20,
        text_template="{title}  ({year})",
        font_size=30,
        text_color="#f8fafc",
    ))

    return proj


TEMPLATES_LIBRARY = {
    "Arcade Cabinet (Clásico)": create_arcade_cabinet_template,
    "Consola Retro (TV + Cartucho)": create_retro_console_template,
    "Minimalista Fullscreen": create_minimalist_fullscreen_template,
}


def generate_layout_code(project: LayoutProject) -> str:
    """
    Genera el código fuente en Python de theme_layout.py
    que compila y ejecuta directamente en PlayNexus conforme a las directivas de GEMINI.md.
    """
    elements_code = []
    for elem in sorted(project.elements, key=lambda e: e.z_index):
        if not elem.visible:
            continue
        d = elem.to_dict()
        elements_code.append(f"        {d!r},")

    media_reqs_code = []
    for m in project.media_requirements:
        media_reqs_code.append(f"        {m!r},")

    code = f'''"""
=============================================================================
Layout Autónomo: {project.name}
Generado automáticamente por PlayNexus Layout Studio
=============================================================================
"""
import os
import math
from pathlib import Path
from PySide6.QtCore import Qt, QRect, QRectF, QPointF, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPixmap, QImage, QTransform, QPolygonF, QPen, QBrush
)
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from playnexus.ui.layouts.base import BaseLayout
from playnexus.services.media import resolve_game_media
from playnexus.services.controls import (
    matches_action, ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_PAGE_UP,
    ACTION_PAGE_DOWN, ACTION_SELECT, ACTION_MUTE, ACTION_NAV_BACK
)

LAYOUT_DIR = Path(__file__).resolve().parent


class ThemeLayout(BaseLayout):
    LAYOUT_NAME = "{project.name}"
    LAYOUT_DESCRIPTION = "{project.description}"

    CANONICAL_W = {CANONICAL_W}
    CANONICAL_H = {CANONICAL_H}

    # Requerimientos de medios explícitos
    MEDIA_REQUIREMENTS = [
{chr(10).join(media_reqs_code)}
    ]

    # Elementos y capas visuales definidas en Layout Studio
    ELEMENTS = [
{chr(10).join(elements_code)}
    ]

    def __init__(self, theme_name: str = "{project.name}", parent=None):
        super().__init__(parent)
        self.theme_name = theme_name
        self.layout_dir = LAYOUT_DIR
        self.setFocusPolicy(Qt.StrongFocus)

        self._current_index = 0
        self._wheel_offset = 0.0
        self._target_offset = 0.0
        self._nav_key_pressed = False

        # Caché de imágenes y texturas
        self._pixmap_cache = {{}}

        # Reproductor de video
        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._sink = QVideoSink(self)
        self._player.setAudioOutput(self._audio_out)
        self._player.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._on_video_frame)

        # Animación de ruleta a 60 FPS
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._on_tick)

        # Debounce para commit de medios al soltar teclas
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(180)
        self._commit_timer.timeout.connect(self._commit_selection)

    def _on_tick(self):
        diff = self._target_offset - self._wheel_offset
        if abs(diff) > 0.001:
            self._wheel_offset += diff * 0.30
            self.update()
        else:
            self._wheel_offset = self._target_offset
            self._anim_timer.stop()
            self.update()

    def _on_video_frame(self, frame):
        self.update()

    def _commit_selection(self):
        if self._nav_key_pressed:
            return
        if not self.games or self._current_index >= len(self.games):
            return
        game = self.games[self._current_index]
        self.game_selected.emit(game)
        self._load_game_media(game)

    def _load_game_media(self, game: dict):
        video_path = resolve_game_media(game, "video")
        if video_path and os.path.isfile(video_path):
            self._player.setSource(video_path)
            self._player.play()

    def set_games(self, games: list[dict], initial_game_id: int | None = None):
        super().set_games(games, initial_game_id)
        if initial_game_id and games:
            for i, g in enumerate(games):
                if g.get("id") == initial_game_id:
                    self._current_index = i
                    break
        self._commit_selection()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Escalar coordenadas canónicas al tamaño del widget
        scale_x = self.width() / self.CANONICAL_W
        scale_y = self.height() / self.CANONICAL_H
        painter.scale(scale_x, scale_y)

        for elem in self.ELEMENTS:
            if not elem.get("visible", True):
                continue
            self._render_element(painter, elem)

    def _render_element(self, painter: QPainter, elem: dict):
        painter.save()
        opacity = elem.get("opacity", 1.0)
        painter.setOpacity(opacity)

        x, y, w, h = elem.get("x", 0), elem.get("y", 0), elem.get("w", 100), elem.get("h", 100)
        e_type = elem.get("type", "image")
        pins = elem.get("corner_pins")

        # Deformación de perspectiva si tiene corner pins
        if pins and len(pins) == 4:
            src_poly = QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)])
            dst_poly = QPolygonF([QPointF(p[0], p[1]) for p in pins])
            trans = QTransform()
            if QTransform.quadToQuad(src_poly, dst_poly, trans):
                painter.setTransform(trans * painter.transform())
                x, y = 0, 0

        if e_type == "video":
            frame = self._sink.currentVideoFrame()
            if frame.isValid():
                img = frame.toImage()
                painter.drawImage(QRectF(x, y, w, h), img)
            else:
                painter.fillRect(QRectF(x, y, w, h), QColor("#090d16"))

        elif e_type == "text":
            game = self.games[self._current_index] if (self.games and self._current_index < len(self.games)) else {{}}
            tpl = elem.get("text_template", "{{title}}")
            txt = tpl.format(
                title=game.get("title", "Sin Juego"),
                year=game.get("year", "N/A"),
                manufacturer=game.get("manufacturer", "N/A"),
                index=self._current_index + 1 if self.games else 0,
                total=len(self.games) if self.games else 0,
            )
            painter.setFont(QFont("Arial", elem.get("font_size", 24)))
            painter.setPen(QColor(elem.get("text_color", "#ffffff")))
            painter.drawText(QRectF(x, y, w, h), Qt.AlignVCenter | Qt.AlignLeft, txt)

        elif e_type == "effect" and elem.get("effect_type") == "scanlines":
            intensity = elem.get("effect_intensity", 0.3)
            pen = QPen(QColor(0, 0, 0, int(255 * intensity)), 1)
            painter.setPen(pen)
            spacing = int(elem.get("effect_param", 4))
            for ly in range(int(y), int(y + h), max(spacing, 2)):
                painter.drawLine(int(x), ly, int(x + w), ly)

        painter.restore()

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        if matches_action(event, ACTION_NAV_DOWN):
            self._nav_key_pressed = True
            if self.games and self._current_index < len(self.games) - 1:
                self._current_index += 1
                self._target_offset += 1.0
                if not self._anim_timer.isActive():
                    self._anim_timer.start()
        elif matches_action(event, ACTION_NAV_UP):
            self._nav_key_pressed = True
            if self.games and self._current_index > 0:
                self._current_index -= 1
                self._target_offset -= 1.0
                if not self._anim_timer.isActive():
                    self._anim_timer.start()

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        self._nav_key_pressed = False
        self._commit_timer.start()
'''
    return code

