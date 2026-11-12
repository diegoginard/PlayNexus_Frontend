from __future__ import annotations

import os
import math
from pathlib import Path
from typing import Any
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, Signal, QSize, QRect, QUrl
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QTransform,
    QPolygonF, QImage, QPixmap, QCursor
)
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink

from playnexus.ui.layout_studio.models import LayoutElement, LayoutProject, CANONICAL_W, CANONICAL_H
from playnexus.ui.layout_studio.runtime_hook import (
    NATIVE_LAYER_IDS,
    get_trimmed_image_info,
    should_trim_alpha,
    render_element_with_transform,
    compute_element_animation,
)
from playnexus.services.media import resolve_game_media

HANDLE_SIZE = 10
PIN_HANDLE_SIZE = 12

# Modos de interacción con el ratón
MODE_NONE = 0
MODE_MOVE = 1
MODE_RESIZE = 2
MODE_PIN_DRAG = 3


class LayoutCanvasWidget(QWidget):
    """
    Lienzo WYSIWYG interactivo en tiempo real para diseño y manipulación de elementos de layout.
    Soporta selección, traslación, redimensionamiento con 8 gizmos,
    deformación de perspectiva con 4 pines de esquina (Corner Pinning / Skew)
    y previsualización de animaciones por elemento.
    """
    element_selected = Signal(str)       # elem_id
    element_dragging = Signal(str)       # elem_id (notificación ultraligera durante el arrastre)
    element_modified = Signal(str)       # elem_id (commit al soltar el botón del ratón)
    canvas_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.project: LayoutProject | None = None
        self.layout_instance = None
        self.selected_elem_id: str | None = None
        self.skew_mode: bool = False  # Modo deformación de perspectiva (4 pines)
        self._anim_time: float = 0.0
        self._is_previewing_anim: bool = False

        # Estado del arrastre
        self._interaction_mode = MODE_NONE
        self._active_handle: str | None = None
        self._active_pin_index: int = -1
        self._drag_start_pos = QPointF(0, 0)
        self._elem_start_rect = (0.0, 0.0, 0.0, 0.0)
        self._elem_start_pins: list[tuple[float, float]] | None = None
        self._is_dragging_active = False

        # Caché de imágenes, texturas y fotogramas de video pausados
        self._pixmap_cache: dict[str, QPixmap] = {}
        self._video_frame_cache: dict[str, QPixmap] = {}
        self._video_frame_pix: QPixmap | None = None
        self._grabbing_video_path: str | None = None

        # Extractor ligero de 1 fotograma para mostrar vista pausada real de videos .mp4 (0% CPU en reposo)
        self._grab_player: QMediaPlayer | None = None
        self._grab_sink: QVideoSink | None = None

        self._sample_game: dict[str, Any] = {
            "title": "Street Fighter II: The World Warrior",
            "year": "1991",
            "manufacturer": "Capcom",
            "genre": "Fighting",
        }
        self._sample_games_list: list[dict[str, Any]] = [self._sample_game]

    def _ensure_frame_grabber(self):
        if self._grab_player is None:
            try:
                self._grab_sink = QVideoSink(self)
                self._grab_sink.videoFrameChanged.connect(self._on_grab_video_frame)
                self._grab_player = QMediaPlayer(self)
                self._grab_player.setAudioOutput(None)
                self._grab_player.setVideoSink(self._grab_sink)
            except Exception:
                self._grab_player = None
                self._grab_sink = None

    def _sync_video_frame_to_instance(self):
        """Sincroniza el fotograma pausado actual con la instancia de ThemeLayout."""
        if not self.layout_instance:
            return
        img = self._video_frame_pix.toImage() if (self._video_frame_pix and not self._video_frame_pix.isNull()) else None
        if hasattr(self.layout_instance, "_game_video_image"):
            self.layout_instance._game_video_image = img
        if hasattr(self.layout_instance, "_current_video_image"):
            self.layout_instance._current_video_image = img

    def _on_grab_video_frame(self, frame):
        """Captura el primer fotograma válido del video .mp4, lo guarda en caché y detiene el decodificador."""
        if not frame.isValid() or not self._grabbing_video_path:
            return
        img = frame.toImage()
        if not img.isNull():
            pix = QPixmap.fromImage(img)
            if not pix.isNull():
                vpath = self._grabbing_video_path
                self._video_frame_cache[vpath] = pix
                self._video_frame_pix = pix
                self._grabbing_video_path = None
                self._sync_video_frame_to_instance()
                if self._grab_player:
                    try:
                        self._grab_player.stop()
                    except Exception:
                        pass
                self.update()

    def _request_video_frame(self, video_path: str | None):
        """Obtiene o extrae un fotograma pausado real desde un archivo de video .mp4."""
        if not video_path or not os.path.isfile(video_path):
            if self._grab_player:
                try:
                    self._grab_player.stop()
                except Exception:
                    pass
            self._grabbing_video_path = None
            self._video_frame_pix = None
            self._sync_video_frame_to_instance()
            return

        if video_path in self._video_frame_cache:
            self._video_frame_pix = self._video_frame_cache[video_path]
            self._grabbing_video_path = None
            self._sync_video_frame_to_instance()
            return

        self._video_frame_pix = None
        self._sync_video_frame_to_instance()
        self._grabbing_video_path = video_path
        self._ensure_frame_grabber()
        if self._grab_player:
            try:
                self._grab_player.stop()
                self._grab_player.setSource(QUrl.fromLocalFile(video_path))
                self._grab_player.play()
            except Exception:
                pass

    def set_project(self, project: LayoutProject | None):
        """Asigna el proyecto de layout activo."""
        self.project = project
        self.selected_elem_id = None
        self._interaction_mode = MODE_NONE
        self._is_previewing_anim = False
        self._pixmap_cache.clear()
        self.update()

    def cleanup(self):
        """Libera de forma segura cualquier recurso multimedia activo."""
        if self._grab_player:
            try:
                self._grab_player.stop()
                self._grab_player.setSource(QUrl())
            except Exception:
                pass
        inst = getattr(self, "layout_instance", None)
        if inst:
            self.layout_instance = None
            try:
                if hasattr(inst, "_anim_timer") and hasattr(inst._anim_timer, "stop"):
                    inst._anim_timer.stop()
                if hasattr(inst, "cleanup") and callable(inst.cleanup):
                    inst.cleanup()
                elif hasattr(inst, "close"):
                    inst.close()
                if hasattr(inst, "_wheel_worker") and inst._wheel_worker:
                    try:
                        inst._wheel_worker.stop()
                        inst._wheel_worker.wait(500)
                    except Exception:
                        pass
                if hasattr(inst, "stop_media"):
                    inst.stop_media()
                inst.deleteLater()
            except Exception:
                pass

    def set_layout_instance(self, inst):
        """Asigna la instancia real de ThemeLayout del layout activo."""
        if hasattr(self, "layout_instance") and self.layout_instance and self.layout_instance != inst:
            self.cleanup()
        self.layout_instance = inst
        if self.layout_instance:
            self.layout_instance.hide()
            self.layout_instance.resize(CANONICAL_W, CANONICAL_H)
            self._sync_video_frame_to_instance()
        self.update()

    def set_sample_games_list(self, games: list[dict[str, Any]]):
        """Asigna la lista de juegos de la colección activa para poblar la ruleta de muestra."""
        self._sample_games_list = games if games else [self._sample_game]
        self._pixmap_cache.clear()
        self.update()

    def set_sample_game(self, game: dict[str, Any]):
        """Asigna un juego de muestra para renderizar títulos, artes y vista pausada del video."""
        self._sample_game = game
        self._pixmap_cache.clear()
        self._video_frame_pix = None
        self._sync_video_frame_to_instance()

        # Resolver captura estática o extraer fotograma real pausado del video .mp4
        if game:
            media = resolve_game_media(game)
            snap_cand = media.get("snap")
            titles_cand = media.get("titles")
            vid_cand = media.get("video")
            static_exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
            video_exts = (".mp4", ".mkv", ".avi", ".webm")

            if snap_cand and os.path.isfile(snap_cand) and snap_cand.lower().endswith(static_exts):
                pix = QPixmap(snap_cand)
                if not pix.isNull():
                    self._video_frame_pix = pix
                    self._sync_video_frame_to_instance()
            elif titles_cand and os.path.isfile(titles_cand) and titles_cand.lower().endswith(static_exts):
                pix = QPixmap(titles_cand)
                if not pix.isNull():
                    self._video_frame_pix = pix
                    self._sync_video_frame_to_instance()
            elif vid_cand and os.path.isfile(vid_cand) and vid_cand.lower().endswith(video_exts):
                self._request_video_frame(vid_cand)
            elif snap_cand and os.path.isfile(snap_cand) and snap_cand.lower().endswith(video_exts):
                self._request_video_frame(snap_cand)
            else:
                self._request_video_frame(None)

        self.update()

    def select_element(self, elem_id: str | None):
        """Selecciona un elemento por su ID."""
        if self.selected_elem_id != elem_id:
            self.selected_elem_id = elem_id
            self._is_previewing_anim = False
            self.element_selected.emit(elem_id or "")
            self.update()

    def set_skew_mode(self, enabled: bool):
        """Activa o desactiva el modo de deformación por 4 esquinas."""
        self.skew_mode = enabled
        if enabled and self.selected_elem_id and self.project:
            elem = self.project.get_element(self.selected_elem_id)
            if elem and not elem.corner_pins:
                elem.init_corner_pins()
                self.element_modified.emit(elem.id)
        self.update()

    def calculate_element_transform(self, elem: LayoutElement, t: float) -> tuple[float, float, float]:
        """
        Calcula el desplazamiento cinemático (dx, dy) y el factor de opacidad
        según el instante de tiempo t (en segundos) para el elemento seleccionado.
        """
        if not self._is_previewing_anim or not elem.has_animation():
            return 0.0, 0.0, 1.0
        return compute_element_animation(elem, t)

    def apply_animation_time(self, t: float, preview_active: bool = True):
        """
        Sincroniza y avanza el estado de la animación del elemento seleccionado al instante t (en segundos).
        """
        self._anim_time = max(0.0, float(t))
        self._is_previewing_anim = preview_active
        self.update()

    # -------------------------------------------------------------------------
    # TRANSFORMACIONES DE COORDENADAS (CANONICAL 1920x1080 <-> PANTALLA)
    # -------------------------------------------------------------------------
    def _get_canvas_viewport(self) -> tuple[float, float, float, float, float]:
        """Calcula el rectángulo y factor de escala para mantener el ratio 16:9 centrado."""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return 0, 0, 1, 0, 0

        scale = min((w - 40) / CANONICAL_W, (h - 40) / CANONICAL_H)
        scale = max(scale, 0.1)

        cw = CANONICAL_W * scale
        ch = CANONICAL_H * scale
        ox = (w - cw) / 2.0
        oy = (h - ch) / 2.0
        return ox, oy, scale, cw, ch

    def _screen_to_canonical(self, pos: QPointF) -> QPointF:
        ox, oy, scale, _, _ = self._get_canvas_viewport()
        return QPointF((pos.x() - ox) / scale, (pos.y() - oy) / scale)

    def _canonical_to_screen(self, pos: QPointF) -> QPointF:
        ox, oy, scale, _, _ = self._get_canvas_viewport()
        return QPointF(pos.x() * scale + ox, pos.y() * scale + oy)

    # -------------------------------------------------------------------------
    # RENDERIZADO WYSIWYG EN TIEMPO REAL
    # -------------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 1. Fondo del área de trabajo (Gris grafito oscuro con sutil cuadrícula)
        painter.fillRect(self.rect(), QColor("#0b0f19"))
        self._draw_grid_pattern(painter)

        ox, oy, scale, cw, ch = self._get_canvas_viewport()
        canvas_rect = QRectF(ox, oy, cw, ch)

        # 2. Sombra y Marco del Lienzo 16:9
        painter.fillRect(canvas_rect.adjusted(4, 4, 4, 4), QColor(0, 0, 0, 120))
        painter.fillRect(canvas_rect, QColor("#020617"))
        painter.setPen(QPen(QColor("#334155"), 1.5))
        painter.drawRect(canvas_rect)

        if not self.project:
            painter.setPen(QColor("#64748b"))
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(canvas_rect, Qt.AlignCenter, "Ningún Layout Cargado\nSelecciona uno o crea uno nuevo")
            return

        # 3. Renderizado Directo por Capas en Tiempo Real (respeta X, Y, W, H, 4 Esquinas, Z-Order y Visibilidad)
        painter.save()
        painter.setClipRect(canvas_rect)
        painter.translate(ox, oy)
        painter.scale(scale, scale)

        sorted_elements = sorted(self.project.elements, key=lambda e: e.z_index)
        for elem in sorted_elements:
            if elem.visible:
                self._draw_element(painter, elem)

        painter.restore()

        # 4. Gizmos de Selección, Redimensionamiento y Deformación de 4 Esquinas (Sobre el lienzo)
        if self.selected_elem_id:
            elem = self.project.get_element(self.selected_elem_id)
            if elem and elem.visible:
                self._draw_element_gizmos(painter, elem, ox, oy, scale)

    def _draw_grid_pattern(self, painter: QPainter):
        """Dibuja una rejilla sutil de fondo en el área del editor."""
        pen = QPen(QColor("#1e293b"), 0.5)
        painter.setPen(pen)
        step = 30
        w, h = self.width(), self.height()
        for x in range(0, w, step):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            painter.drawLine(0, y, w, y)

    def _resolve_pixmap(self, elem: LayoutElement) -> QPixmap | None:
        """Resuelve la imagen de un elemento personalizado agregado manualmente en el Inspector."""
        if self._sample_game and elem.media_key:
            game_media = resolve_game_media(self._sample_game)
            resolved_file = game_media.get(elem.media_key)
            if elem.type == "video" or (resolved_file and resolved_file.lower().endswith((".mp4", ".mkv", ".avi", ".webm"))):
                resolved_file = None
                snap_cand = game_media.get("snap")
                if snap_cand and os.path.isfile(snap_cand) and not snap_cand.lower().endswith((".mp4", ".mkv", ".avi", ".webm")):
                    resolved_file = snap_cand
                else:
                    titles_cand = game_media.get("titles")
                    if titles_cand and os.path.isfile(titles_cand) and not titles_cand.lower().endswith((".mp4", ".mkv", ".avi", ".webm")):
                        resolved_file = titles_cand

            if resolved_file and os.path.isfile(resolved_file):
                cache_key = f"game_{elem.media_key}_{resolved_file}"
                if cache_key in self._pixmap_cache:
                    return self._pixmap_cache[cache_key]
                pix = QPixmap(resolved_file)
                if not pix.isNull():
                    self._pixmap_cache[cache_key] = pix
                    return pix

        if elem.resource_path:
            folder = Path(self.project.folder_path) if (self.project and self.project.folder_path) else None
            common_dir = folder.parent / "gtc-common" if folder else None
            candidates: list[Path | None] = [Path(elem.resource_path)]
            if folder:
                candidates.append(folder / elem.resource_path)
            if common_dir:
                candidates.append(common_dir / elem.resource_path)

            for c in candidates:
                if c and c.is_file():
                    c_str = str(c.resolve())
                    trim = should_trim_alpha(elem.id, c_str)
                    cache_key = f"file_{c_str}_trim_{trim}"
                    if cache_key in self._pixmap_cache:
                        return self._pixmap_cache[cache_key]
                    pix, _ = get_trimmed_image_info(c_str, trim_alpha=trim)
                    if not pix.isNull():
                        self._pixmap_cache[cache_key] = pix
                        return pix

        return None

    def _resolve_game_wheel_logo(self, game: dict[str, Any]) -> QPixmap | None:
        """Resuelve el logotipo wheel de un juego específico."""
        if not game:
            return None
        gid = game.get("id", game.get("title", ""))
        cache_key = f"wheel_logo_{gid}"
        if cache_key in self._pixmap_cache:
            return self._pixmap_cache[cache_key]
        media = resolve_game_media(game)
        w_file = media.get("wheel")
        if w_file and os.path.isfile(w_file):
            pix = QPixmap(w_file)
            if not pix.isNull():
                self._pixmap_cache[cache_key] = pix
                return pix
        return None

    def _draw_element(self, painter: QPainter, elem: LayoutElement):
        """
        Renderiza un elemento ejecutando directamente el método de dibujo real de ThemeLayout
        (theme_layout.py) con su transformación geométrica en tiempo real.
        """
        dx, dy, op_factor = 0.0, 0.0, 1.0
        if self.selected_elem_id == elem.id and self._is_previewing_anim:
            dx, dy, op_factor = self.calculate_element_transform(elem, self._anim_time)

        # 1. Si tenemos la instancia real de ThemeLayout y es una capa del theme_layout.py,
        # ejecutar el código nativo del layout con la matriz QTransform.quadToQuad
        if self.layout_instance is not None and elem.orig_rect is not None and elem.id in NATIVE_LAYER_IDS:
            render_element_with_transform(
                painter,
                self.layout_instance,
                elem,
                anim_dx=dx,
                anim_dy=dy,
                anim_op=op_factor,
            )
            # Si el juego seleccionado no tiene arte cargada en disco, dibujar guía sutil en el editor
            if elem.id in ("flyer", "cartart", "boxart"):
                pix_val = None
                if elem.id == "flyer":
                    pix_val = getattr(self.layout_instance, "_current_flyer_pix", None) or getattr(self.layout_instance, "_pix_flyer", None)
                elif elem.id == "cartart":
                    pix_val = getattr(self.layout_instance, "_current_cart_pixmap", None) or getattr(self.layout_instance, "_pix_cartart_frame", None)
                elif elem.id == "boxart":
                    pix_val = getattr(self.layout_instance, "_current_box_pixmap", None) or getattr(self.layout_instance, "_pix_boxart_frame", None)

                if pix_val is None or pix_val.isNull():
                    painter.save()
                    r = QRectF(elem.x + dx, elem.y + dy, elem.w, elem.h)
                    painter.fillRect(r, QColor(15, 23, 42, 130))
                    painter.setPen(QPen(QColor("#38bdf8"), 1.5, Qt.DashLine))
                    painter.drawRoundedRect(r, 8, 8)
                    painter.setPen(QColor("#e2e8f0"))
                    painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
                    painter.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, f"🖼 {elem.name}\n(Sin arte en este juego)")
                    painter.restore()
            return

        painter.save()
        painter.setOpacity(max(0.0, min(1.0, elem.opacity * op_factor)))

        x, y, w, h = elem.x + dx, elem.y + dy, elem.w, elem.h
        pins = elem.corner_pins

        # Si tiene deformación de 4 esquinas (Corner Pinning / Perspectiva)
        if pins and len(pins) == 4:
            src_poly = QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)])
            dst_poly = QPolygonF([QPointF(p[0] + dx, p[1] + dy) for p in pins])
            trans = QTransform()
            if QTransform.quadToQuad(src_poly, dst_poly, trans):
                painter.setTransform(trans * painter.transform())
                x, y = 0, 0

        rect = QRectF(x, y, w, h)
        irect = rect.toRect()

        if elem.type == "video":
            # Mostrar captura estática o el fotograma real extraído del video .mp4
            pix = self._resolve_pixmap(elem) or self._video_frame_pix
            if pix and not pix.isNull():
                painter.fillRect(rect, QColor(0, 0, 0))
                painter.drawPixmap(irect, pix)

                # Filtro CRT sutil con scanlines
                painter.fillRect(rect, QColor(0, 0, 0, 35))
                painter.setPen(QPen(QColor(0, 0, 0, 55), 1))
                for ly in range(int(y), int(y + h), 4):
                    painter.drawLine(int(x), ly, int(x + w), ly)

                # Insignia sutil de vista pausada
                painter.setPen(QPen(QColor("#38bdf8"), 1.2))
                painter.drawRect(rect)
                badge_rect = QRectF(x + 10, y + 10, 135, 24)
                painter.fillRect(badge_rect, QColor(15, 23, 42, 215))
                painter.setPen(QPen(QColor("#38bdf8"), 1))
                painter.drawRect(badge_rect)
                painter.setPen(QColor("#38bdf8"))
                painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                painter.drawText(badge_rect, Qt.AlignCenter, "⏸ VIDEO SNAP")
            else:
                # Marco simulador de video CRT con scanlines y título del juego actual
                painter.fillRect(rect, QColor("#050914"))
                painter.setPen(QPen(QColor("#0ea5e9"), 1.5))
                painter.drawRect(rect)

                painter.setPen(QPen(QColor(0, 0, 0, 100), 1))
                for ly in range(int(y), int(y + h), 4):
                    painter.drawLine(int(x), ly, int(x + w), ly)

                painter.setPen(QColor("#38bdf8"))
                painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
                title = self._sample_game.get("title", "VIDEO SNAP")
                painter.drawText(rect, Qt.AlignCenter, f"⏸  VIDEO SNAP (PAUSADO)\n[{title}]")

        elif elem.type in ("image", "marquee", "cabinet"):
            pix = self._resolve_pixmap(elem)
            if pix and not pix.isNull():
                eid = elem.id.lower()
                if eid in ("flyer", "cartart", "boxart", "pointer"):
                    # Preservar proporción del flyer / cartucho / boxart / puntero dentro de su caja editable
                    pw, ph = pix.width(), pix.height()
                    s = min(w / pw, h / ph) if pw > 0 and ph > 0 else 1.0
                    dw, dh = int(pw * s), int(ph * s)
                    ax = int(x + (w - dw) / 2)
                    ay = int(y + (h - dh) / 2) if eid != "boxart" else int(y + h - dh)
                    painter.drawPixmap(QRect(ax, ay, dw, dh), pix)
                else:
                    painter.drawPixmap(irect, pix)
            else:
                # Tarjeta visual clara para elementos sin arte en el juego actual (ej. Flyer o Boxart)
                painter.fillRect(rect, QColor(15, 23, 42, 185))
                painter.setPen(QPen(QColor("#38bdf8"), 1.5, Qt.DashLine))
                painter.drawRoundedRect(rect, 8, 8)
                painter.setPen(QColor("#e2e8f0"))
                painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
                lbl = elem.name if elem.name else elem.type.upper()
                title = self._sample_game.get("title", "")
                painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, f"🖼 {lbl}\n{title}\n({int(w)}x{int(h)})")

        elif elem.type == "wheel":
            # Renderizado de la ruleta curva con logotipos reales de la lista activa
            painter.fillRect(rect, QColor(10, 15, 29, 75))
            painter.setPen(QPen(QColor("#6366f1"), 1.2, Qt.DashLine))
            painter.drawRoundedRect(rect, 8, 8)

            item_count = max(3, elem.wheel_visible_items)
            half_slots = item_count // 2
            games = self._sample_games_list if self._sample_games_list else [self._sample_game]
            n = len(games)
            # Encontrar el índice del juego seleccionado actualmente
            sel_idx = 0
            cur_id = self._sample_game.get("id")
            for idx_g, g in enumerate(games):
                if g.get("id") == cur_id:
                    sel_idx = idx_g
                    break

            for offset in range(-half_slots, half_slots + 1):
                game = games[(sel_idx + offset) % n]
                angle = (offset / float(half_slots + 1)) * (math.pi * 0.42)
                curv_x = math.cos(angle)
                curv_y = math.sin(angle)

                center_x = x + w * 0.62 - curv_x * (w * 0.28)
                center_y = y + h * 0.50 + curv_y * (h * 0.44)

                is_center = (offset == 0)
                slot_scale = max(0.4, 1.0 - (abs(offset) * 0.10))
                if is_center:
                    slot_w = w * 0.52 * 1.45
                    slot_h = h * 0.09 * 1.55
                    alpha = 1.0
                else:
                    slot_w = w * 0.52 * slot_scale
                    slot_h = h * 0.09 * slot_scale
                    alpha = max(0.25, (220 - abs(offset) * 35) / 255.0)

                item_rect = QRectF(center_x - slot_w / 2, center_y - slot_h / 2, slot_w, slot_h)
                logo_pix = self._resolve_game_wheel_logo(game)

                painter.save()
                painter.setOpacity(painter.opacity() * alpha)
                if logo_pix and not logo_pix.isNull():
                    pw, ph = logo_pix.width(), logo_pix.height()
                    s = min(slot_w / pw, slot_h / ph) if pw > 0 and ph > 0 else 1.0
                    dw, dh = int(pw * s), int(ph * s)
                    lx = int(center_x - dw / 2)
                    ly = int(center_y - dh / 2)
                    painter.drawPixmap(QRect(lx, ly, dw, dh), logo_pix)
                else:
                    painter.fillRect(item_rect, QColor(99, 102, 241, 150) if is_center else QColor(30, 41, 59, 120))
                    painter.setPen(QColor("#ffffff") if is_center else QColor("#cbd5e1"))
                    painter.setFont(QFont("Segoe UI", 11 if is_center else 9, QFont.Bold))
                    painter.drawText(item_rect, Qt.AlignCenter | Qt.TextWordWrap, game.get("title", "Juego"))
                painter.restore()

        elif elem.type == "text":
            tpl = elem.text_template or "{title}"
            games = self._sample_games_list if self._sample_games_list else [self._sample_game]
            txt = tpl.format(
                title=self._sample_game.get("title", "Juego de Muestra"),
                year=self._sample_game.get("year", "1995"),
                manufacturer=self._sample_game.get("manufacturer", "Empresa"),
                genre=self._sample_game.get("genre", "Arcade"),
                index=1,
                total=len(games),
            )
            painter.setFont(QFont("Segoe UI", elem.font_size, QFont.Bold))
            painter.setPen(QColor(elem.text_color))
            flags = Qt.AlignVCenter
            if elem.text_align == "center":
                flags |= Qt.AlignHCenter
            elif elem.text_align == "right":
                flags |= Qt.AlignRight
            else:
                flags |= Qt.AlignLeft
            painter.drawText(rect, flags, txt.upper())

        elif elem.type == "effect":
            pix = self._resolve_pixmap(elem)
            if pix and not pix.isNull():
                painter.drawPixmap(irect, pix)
            elif elem.effect_type == "scanlines":
                intensity = elem.effect_intensity
                painter.setPen(QPen(QColor(0, 0, 0, int(255 * intensity)), 1))
                spacing = max(int(elem.effect_param), 2)
                for ly in range(int(y), int(y + h), spacing):
                    painter.drawLine(int(x), ly, int(x + w), ly)
            elif elem.effect_type == "vignette":
                painter.setPen(QPen(QColor(0, 0, 0, int(255 * elem.effect_intensity)), 10))
                painter.drawRect(rect)

        painter.restore()

    def _draw_element_gizmos(self, painter: QPainter, elem: LayoutElement, ox: float, oy: float, scale: float):
        """Dibuja los controles interactivos de selección, tamaño o deformación de 4 esquinas."""
        painter.save()

        dx, dy, _ = (
            self.calculate_element_transform(elem, self._anim_time)
            if (self.selected_elem_id == elem.id and self._is_previewing_anim)
            else (0.0, 0.0, 1.0)
        )

        # Si el elemento está en modo Deformación (Corner Pinning / 4 Esquinas)
        if self.skew_mode and elem.corner_pins and len(elem.corner_pins) == 4:
            pts_screen = [self._canonical_to_screen(QPointF(px + dx, py + dy)) for px, py in elem.corner_pins]
            poly = QPolygonF(pts_screen)

            # Polígono de conexión de los 4 pines
            painter.setPen(QPen(QColor("#f59e0b"), 2, Qt.DashLine))
            painter.setBrush(QColor(245, 158, 11, 20))
            painter.drawPolygon(poly)

            # 4 Manijas circulares de las esquinas
            pin_labels = ["TL", "TR", "BR", "BL"]
            for i, pt in enumerate(pts_screen):
                is_active = (self._interaction_mode == MODE_PIN_DRAG and self._active_pin_index == i)
                color = QColor("#ef4444") if is_active else QColor("#fbbf24")

                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.setBrush(QBrush(color))
                painter.drawEllipse(pt, PIN_HANDLE_SIZE, PIN_HANDLE_SIZE)

                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                painter.setPen(QColor("#000000"))
                painter.drawText(QRectF(pt.x() - 10, pt.y() - 10, 20, 20), Qt.AlignCenter, pin_labels[i])
        else:
            # Modo estándar: Bounding Box rectangular con 8 gizmos de redimensionamiento
            p1 = self._canonical_to_screen(QPointF(elem.x + dx, elem.y + dy))
            p2 = self._canonical_to_screen(QPointF(elem.x + elem.w + dx, elem.y + elem.h + dy))
            screen_rect = QRectF(p1, p2)

            # Borde de selección
            painter.setPen(QPen(QColor("#38bdf8"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(screen_rect)

            # Etiqueta superior con nombre y dimensiones en vivo
            lbl_rect = QRectF(screen_rect.x(), max(2.0, screen_rect.y() - 22.0), min(280.0, max(140.0, screen_rect.width())), 20.0)
            painter.fillRect(lbl_rect, QColor(2, 132, 199, 220))
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(lbl_rect.adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, f"{elem.name} ({int(elem.w)}x{int(elem.h)})")

            # 8 Handles de redimensionamiento
            handles = self._get_resize_handles(screen_rect)
            for h_name, h_rect in handles.items():
                is_active = (self._interaction_mode == MODE_RESIZE and self._active_handle == h_name)
                painter.setPen(QPen(QColor("#0284c7"), 1.5))
                painter.setBrush(QBrush(QColor("#38bdf8") if not is_active else QColor("#ffffff")))
                painter.drawRect(h_rect)

        painter.restore()

    def _get_resize_handles(self, rect: QRectF) -> dict[str, QRectF]:
        """Calcula los rectángulos en pantalla de los 8 tiradores de redimensionamiento."""
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        hs = HANDLE_SIZE
        hs2 = hs / 2.0
        return {
            "nw": QRectF(x - hs2, y - hs2, hs, hs),
            "n":  QRectF(x + w / 2 - hs2, y - hs2, hs, hs),
            "ne": QRectF(x + w - hs2, y - hs2, hs, hs),
            "e":  QRectF(x + w - hs2, y + h / 2 - hs2, hs, hs),
            "se": QRectF(x + w - hs2, y + h - hs2, hs, hs),
            "s":  QRectF(x + w / 2 - hs2, y + h - hs2, hs, hs),
            "sw": QRectF(x - hs2, y + h - hs2, hs, hs),
            "w":  QRectF(x - hs2, y + h / 2 - hs2, hs, hs),
        }

    # -------------------------------------------------------------------------
    # INTERACCIÓN CON EL RATÓN
    # -------------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self.project:
            return

        # Al interactuar en el lienzo para mover/redimensionar, posicionar en reposo
        self._is_previewing_anim = False

        pos = event.position()
        c_pos = self._screen_to_canonical(pos)

        # 1. Verificar si se hizo clic en un pin de esquina (si está en modo Skew)
        if self.skew_mode and self.selected_elem_id:
            elem = self.project.get_element(self.selected_elem_id)
            if elem and elem.corner_pins:
                for i, (px, py) in enumerate(elem.corner_pins):
                    s_pt = self._canonical_to_screen(QPointF(px, py))
                    dist = math.hypot(pos.x() - s_pt.x(), pos.y() - s_pt.y())
                    if dist <= PIN_HANDLE_SIZE + 4:
                        self._interaction_mode = MODE_PIN_DRAG
                        self._active_pin_index = i
                        self._drag_start_pos = c_pos
                        self._elem_start_pins = list(elem.corner_pins)
                        self.update()
                        return

        # 2. Verificar si se hizo clic en un tirador de redimensionamiento
        if self.selected_elem_id and not self.skew_mode:
            elem = self.project.get_element(self.selected_elem_id)
            if elem:
                p1 = self._canonical_to_screen(QPointF(elem.x, elem.y))
                p2 = self._canonical_to_screen(QPointF(elem.x + elem.w, elem.y + elem.h))
                handles = self._get_resize_handles(QRectF(p1, p2))
                for h_name, h_rect in handles.items():
                    if h_rect.contains(pos):
                        self._interaction_mode = MODE_RESIZE
                        self._active_handle = h_name
                        self._drag_start_pos = c_pos
                        self._elem_start_rect = (elem.x, elem.y, elem.w, elem.h)
                        self._elem_start_pins = list(elem.corner_pins) if elem.corner_pins else None
                        self.update()
                        return

        # 3. Verificar si se hizo clic sobre un elemento para seleccionarlo o moverlo
        # Si ya hay un elemento seleccionado en el panel izquierdo y el usuario hace clic dentro
        # de su caja delimitadora, priorizarlo para permitir moverlo sin que capas frontales
        # (sombras, scanlines, ruleta) le roben la selección.
        clicked_elem = None
        if self.selected_elem_id:
            sel_elem = self.project.get_element(self.selected_elem_id)
            if sel_elem and sel_elem.visible and not sel_elem.locked:
                r_sel = QRectF(sel_elem.x, sel_elem.y, sel_elem.w, sel_elem.h)
                if r_sel.contains(c_pos):
                    clicked_elem = sel_elem

        if not clicked_elem:
            sorted_desc = sorted(self.project.elements, key=lambda e: e.z_index, reverse=True)
            for elem in sorted_desc:
                if not elem.visible or elem.locked:
                    continue
                r = QRectF(elem.x, elem.y, elem.w, elem.h)
                if r.contains(c_pos):
                    clicked_elem = elem
                    break

        if clicked_elem:
            self.select_element(clicked_elem.id)
            self._interaction_mode = MODE_MOVE
            self._drag_start_pos = c_pos
            self._elem_start_rect = (clicked_elem.x, clicked_elem.y, clicked_elem.w, clicked_elem.h)
            if clicked_elem.corner_pins:
                self._elem_start_pins = list(clicked_elem.corner_pins)
            else:
                self._elem_start_pins = None
            self.update()
        else:
            self.select_element(None)
            self.canvas_clicked.emit()
            self._interaction_mode = MODE_NONE
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        c_pos = self._screen_to_canonical(pos)

        # Si estamos arrastrando (Traslación)
        if self._interaction_mode == MODE_MOVE and self.selected_elem_id and self.project:
            elem = self.project.get_element(self.selected_elem_id)
            if elem:
                dx = c_pos.x() - self._drag_start_pos.x()
                dy = c_pos.y() - self._drag_start_pos.y()
                sx, sy, sw, sh = self._elem_start_rect
                elem.x = round(sx + dx, 1)
                elem.y = round(sy + dy, 1)
                if self._elem_start_pins:
                    elem.corner_pins = [(round(px + dx, 1), round(py + dy, 1)) for px, py in self._elem_start_pins]
                self._is_dragging_active = True
                self.element_dragging.emit(elem.id)
                self.update()
                return

        # Si estamos redimensionando (Escala con 8 manijas)
        elif self._interaction_mode == MODE_RESIZE and self.selected_elem_id and self.project:
            elem = self.project.get_element(self.selected_elem_id)
            if elem:
                dx = c_pos.x() - self._drag_start_pos.x()
                dy = c_pos.y() - self._drag_start_pos.y()
                sx, sy, sw, sh = self._elem_start_rect
                h = self._active_handle

                nx, ny, nw, nh = sx, sy, sw, sh

                if "e" in h:
                    nw = max(sw + dx, 20.0)
                if "s" in h:
                    nh = max(sh + dy, 20.0)
                if "w" in h:
                    diff = min(dx, sw - 20.0)
                    nx = sx + diff
                    nw = sw - diff
                if "n" in h:
                    diff = min(dy, sh - 20.0)
                    ny = sy + diff
                    nh = sh - diff

                elem.x = round(nx, 1)
                elem.y = round(ny, 1)
                elem.w = round(nw, 1)
                elem.h = round(nh, 1)

                # Si tenía corner_pins activos, reescalar proporcionalmente los 4 pines
                if self._elem_start_pins and len(self._elem_start_pins) == 4 and sw > 0 and sh > 0:
                    new_pins = []
                    for px, py in self._elem_start_pins:
                        rx = (px - sx) / sw
                        ry = (py - sy) / sh
                        new_pins.append((round(nx + rx * nw, 1), round(ny + ry * nh, 1)))
                    elem.corner_pins = new_pins

                self._is_dragging_active = True
                self.element_dragging.emit(elem.id)
                self.update()
                return

        # Si estamos deformando una esquina (Perspectiva / Skew de 4 pines)
        elif self._interaction_mode == MODE_PIN_DRAG and self.selected_elem_id and self.project:
            elem = self.project.get_element(self.selected_elem_id)
            if elem and elem.corner_pins and 0 <= self._active_pin_index < len(elem.corner_pins):
                dx = c_pos.x() - self._drag_start_pos.x()
                dy = c_pos.y() - self._drag_start_pos.y()
                orig_x, orig_y = self._elem_start_pins[self._active_pin_index]
                new_pins = list(elem.corner_pins)
                new_pins[self._active_pin_index] = (round(orig_x + dx, 1), round(orig_y + dy, 1))
                elem.corner_pins = new_pins
                self._is_dragging_active = True
                self.element_dragging.emit(elem.id)
                self.update()
                return

        # Actualización de cursor según posición
        self._update_hover_cursor(pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._interaction_mode = MODE_NONE
            self._active_handle = None
            self._active_pin_index = -1
            self.setCursor(Qt.ArrowCursor)
            if self._is_dragging_active and self.selected_elem_id:
                self.element_modified.emit(self.selected_elem_id)
            self._is_dragging_active = False
            self.update()

    def _update_hover_cursor(self, pos: QPointF):
        """Actualiza el cursor del ratón según la manija sobre la que esté posicionado."""
        if self._interaction_mode != MODE_NONE or not self.project:
            return

        if self.skew_mode and self.selected_elem_id:
            elem = self.project.get_element(self.selected_elem_id)
            if elem and elem.corner_pins:
                for px, py in elem.corner_pins:
                    s_pt = self._canonical_to_screen(QPointF(px, py))
                    dist = math.hypot(pos.x() - s_pt.x(), pos.y() - s_pt.y())
                    if dist <= PIN_HANDLE_SIZE + 4:
                        self.setCursor(Qt.CrossCursor)
                        return

        if self.selected_elem_id and not self.skew_mode:
            elem = self.project.get_element(self.selected_elem_id)
            if elem:
                p1 = self._canonical_to_screen(QPointF(elem.x, elem.y))
                p2 = self._canonical_to_screen(QPointF(elem.x + elem.w, elem.y + elem.h))
                handles = self._get_resize_handles(QRectF(p1, p2))
                for h_name, h_rect in handles.items():
                    if h_rect.contains(pos):
                        if h_name in ("nw", "se"):
                            self.setCursor(Qt.SizeFDiagCursor)
                        elif h_name in ("ne", "sw"):
                            self.setCursor(Qt.SizeBDiagCursor)
                        elif h_name in ("n", "s"):
                            self.setCursor(Qt.SizeVerCursor)
                        elif h_name in ("w", "e"):
                            self.setCursor(Qt.SizeHorCursor)
                        return

                if QRectF(p1, p2).contains(pos):
                    self.setCursor(Qt.SizeAllCursor)
                    return

        self.setCursor(Qt.ArrowCursor)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
