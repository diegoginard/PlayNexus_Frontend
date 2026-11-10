from __future__ import annotations

import os
import ast
import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QRect, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QTransform,
    QPolygonF, QImage, QPixmap
)

from playnexus.ui.layout_studio.models import LayoutElement, CANONICAL_W, CANONICAL_H

NATIVE_LAYER_IDS: set[str] = {
    "bg_image",
    "video_snap",
    "scanlines_crt",
    "scratches",
    "bezel",
    "tv_bezel",
    "marquee",
    "cabinet",
    "avatar",
    "logo",
    "console",
    "cartart",
    "console_cover",
    "joystick",
    "boxart",
    "flyer",
    "wheel_shadow",
    "wheel_list",
    "pointer",
    "footer_frame",
    "title_text",
    "counter_text",
}


def get_qimage_alpha_bbox(img: QImage) -> tuple[float, float, float, float] | None:
    """
    Escanea el canal alfa de un QImage y devuelve su caja delimitadora (x, y, w, h)
    en coordenadas canónicas 1920x1080.
    """
    if img.isNull() or img.width() <= 0 or img.height() <= 0:
        return None

    scan_w, scan_h = 480, 270
    small = img if (img.width() == scan_w and img.height() == scan_h) else img.scaled(
        scan_w, scan_h, Qt.IgnoreAspectRatio, Qt.FastTransformation
    )

    min_x, min_y = scan_w, scan_h
    max_x, max_y = -1, -1

    for sy in range(scan_h):
        for sx in range(scan_w):
            alpha = (small.pixel(sx, sy) >> 24) & 0xFF
            if alpha > 12:
                if sx < min_x:
                    min_x = sx
                if sx > max_x:
                    max_x = sx
                if sy < min_y:
                    min_y = sy
                if sy > max_y:
                    max_y = sy

    if max_x < min_x or max_y < min_y:
        return None

    cx = round((min_x / scan_w) * CANONICAL_W, 1)
    cy = round((min_y / scan_h) * CANONICAL_H, 1)
    cw = max(10.0, round(((max_x - min_x + 1) / scan_w) * CANONICAL_W, 1))
    ch = max(10.0, round(((max_y - min_y + 1) / scan_h) * CANONICAL_H, 1))
    return (cx, cy, cw, ch)


def get_trimmed_image_info(
    file_path: str | Path,
    trim_alpha: bool = True
) -> tuple[QPixmap, tuple[float, float, float, float]]:
    """
    Mantiene compatibilidad para medir la caja visible de un PNG en disco cuando se requiere.
    """
    p_str = str(Path(file_path).resolve()) if file_path else ""
    if not p_str or not os.path.isfile(p_str):
        return QPixmap(), (0.0, 0.0, float(CANONICAL_W), float(CANONICAL_H))
    pix = QPixmap(p_str)
    if pix.isNull():
        return pix, (0.0, 0.0, float(CANONICAL_W), float(CANONICAL_H))
    if not trim_alpha or not pix.hasAlphaChannel():
        return pix, (0.0, 0.0, float(CANONICAL_W), float(CANONICAL_H))
    bbox = get_qimage_alpha_bbox(pix.toImage())
    if not bbox:
        return pix, (0.0, 0.0, float(CANONICAL_W), float(CANONICAL_H))
    cx, cy, cw, ch = bbox
    pw, ph = pix.width(), pix.height()
    rx = max(0, int((cx / CANONICAL_W) * pw))
    ry = max(0, int((cy / CANONICAL_H) * ph))
    rw = max(1, min(pw - rx, int((cw / CANONICAL_W) * pw)))
    rh = max(1, min(ph - ry, int((ch / CANONICAL_H) * ph)))
    return pix.copy(rx, ry, rw, rh), bbox


def should_trim_alpha(elem_id: str, resource_path: str = "") -> bool:
    return False


def _get_native_snap_rect(inst) -> QRect:
    """Obtiene el rectángulo canónico (1920x1080) del monitor/TV tal cual está en theme_layout.py."""
    if hasattr(inst, "SNAP_LOCAL_RECT"):
        r = inst.SNAP_LOCAL_RECT
        return QRect(int(r.x()), int(r.y()), int(r.width()), int(r.height()))
    if hasattr(inst, "TV_RECT"):
        vx, vy, vw, vh = inst.TV_RECT
        return QRect(
            int(CANONICAL_W * vx),
            int(CANONICAL_H * vy),
            int(CANONICAL_W * vw),
            int(CANONICAL_H * vh),
        )
    return QRect(0, 0, CANONICAL_W, CANONICAL_H)


def _get_native_marquee_rect(inst) -> QRect:
    """Obtiene el rectángulo canónico (1920x1080) de la marquesina tal cual está en theme_layout.py."""
    if hasattr(inst, "MARQUEE_LOCAL_RECT"):
        r = inst.MARQUEE_LOCAL_RECT
        return QRect(int(r.x()), int(r.y()), int(r.width()), int(r.height()))
    return QRect(138, 0, 832, 227)


def _get_cached_scaled_pixmap(
    inst,
    cache_key: tuple,
    src_pix: QPixmap | None,
    crop_canonical: tuple[float, float, float, float] | None,
    dst_w: int,
    dst_h: int,
) -> QPixmap | None:
    """
    Recorta opcionalmente un QPixmap de lienzo 1920x1080 a su región visible `crop_canonical`
    y cachea su versión pre-escalada a `(dst_w, dst_h)` para dibujo instantáneo 1:1 en GPU/CPU.
    """
    if src_pix is None or src_pix.isNull() or dst_w <= 0 or dst_h <= 0:
        return None
    cache = getattr(inst, "_studio_pix_cache", None)
    if cache is None:
        cache = {}
        inst._studio_pix_cache = cache
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    work_pix = src_pix
    if crop_canonical is not None:
        ox, oy, ow, oh = crop_canonical
        pw, ph = src_pix.width(), src_pix.height()
        if pw > 0 and ph > 0 and (ox > 0 or oy > 0 or ow < CANONICAL_W or oh < CANONICAL_H):
            rx = max(0, int(round((ox / float(CANONICAL_W)) * pw)))
            ry = max(0, int(round((oy / float(CANONICAL_H)) * ph)))
            rw = max(1, min(pw - rx, int(round((ow / float(CANONICAL_W)) * pw))))
            rh = max(1, min(ph - ry, int(round((oh / float(CANONICAL_H)) * ph))))
            work_pix = src_pix.copy(rx, ry, rw, rh)

    if work_pix.width() == dst_w and work_pix.height() == dst_h:
        scaled = work_pix
    else:
        scaled = work_pix.scaled(dst_w, dst_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    if len(cache) > 120:
        cache.clear()
    cache[cache_key] = scaled
    return scaled


def render_native_layer(painter: QPainter, inst, elem_id: str, sr: QRect | None = None, elem: LayoutElement | None = None):
    """
    Ejecuta el paso de renderizado nativo directamente sobre la instancia real `inst` (ThemeLayout)
    leída desde `theme_layout.py`, sin diccionarios ni reimplementaciones externas.
    """
    if sr is None:
        sr = QRect(0, 0, CANONICAL_W, CANONICAL_H)
    sw, sh = sr.width(), sr.height()
    sx, sy = sr.x(), sr.y()
    eid = elem_id.lower()

    # 1. Fondo (ejecuta la lógica exacta de fondo del ThemeLayout)
    if eid == "bg_image":
        bg_vid = getattr(inst, "_bg_video_image", None)
        if bg_vid and not bg_vid.isNull():
            painter.drawImage(sr, bg_vid)
            return
        pix_bg = getattr(inst, "_pix_bg_fallback", None) or getattr(inst, "_pix_bkg", None)
        if pix_bg and not pix_bg.isNull():
            painter.drawPixmap(sr, pix_bg)
            return
        art_pix = getattr(inst, "_current_artwork_pixmap", None)
        if art_pix and not art_pix.isNull():
            painter.drawPixmap(sr, art_pix)
            return
        painter.fillRect(sr, QColor(10, 8, 16))
        return

    # 2. Video Snap (CRT / TV / Fondo Main Menu)
    if eid == "video_snap":
        snap_rect = _get_native_snap_rect(inst)
        painter.fillRect(snap_rect, QColor(0, 0, 0))
        vid_img = getattr(inst, "_game_video_image", None) or getattr(inst, "_current_video_image", None)
        if vid_img and not vid_img.isNull():
            if hasattr(inst, "SNAP_LOCAL_RECT"):
                vw, vh = vid_img.width(), vid_img.height()
                s = min(snap_rect.width() / vw, snap_rect.height() / vh) if vw > 0 and vh > 0 else 1.0
                dw, dh = int(vw * s), int(vh * s)
                vx = snap_rect.x() + (snap_rect.width() - dw) // 2
                vy = snap_rect.y() + (snap_rect.height() - dh) // 2
                painter.drawImage(QRect(vx, vy, dw, dh), vid_img)
            else:
                painter.drawImage(snap_rect, vid_img)
        return

    # 3. Scanlines CRT
    if eid == "scanlines_crt":
        if not getattr(inst, "_pix_scanlines", None):
            scan_const = getattr(inst, "SCANLINES_IMAGE", None)
            if scan_const and Path(scan_const).is_file() and hasattr(inst, "_load_pixmap"):
                inst._pix_scanlines = inst._load_pixmap(str(scan_const))
            elif hasattr(inst, "layout_dir"):
                scan_path = Path(inst.layout_dir).parent / "gtc-common" / "art" / "scanlines_1920.png"
                if scan_path.is_file() and hasattr(inst, "_load_pixmap"):
                    inst._pix_scanlines = inst._load_pixmap(str(scan_path))
        pix_scan = getattr(inst, "_pix_scanlines", None)
        if pix_scan and not pix_scan.isNull():
            snap_rect = _get_native_snap_rect(inst)
            painter.save()
            painter.setOpacity(painter.opacity() * 0.35)
            painter.drawPixmap(snap_rect, pix_scan)
            painter.restore()
        return

    # 4. Scratches (Vidrio rayado CRT)
    if eid == "scratches":
        pix_scr = getattr(inst, "_pix_scratches", None)
        if pix_scr and not pix_scr.isNull():
            snap_rect = _get_native_snap_rect(inst)
            painter.save()
            painter.setOpacity(painter.opacity() * 0.40)
            painter.drawPixmap(snap_rect, pix_scr)
            painter.restore()
        return

    # 5. Bezel Arcade
    if eid == "bezel":
        pix_bz = getattr(inst, "_current_bezel_pix", None) or getattr(inst, "_pix_bezel", None)
        if pix_bz and not pix_bz.isNull():
            snap_rect = _get_native_snap_rect(inst)
            painter.drawPixmap(snap_rect, pix_bz)
        return

    # 6. TV Bezel (Consolas)
    if eid == "tv_bezel":
        pix_tv = getattr(inst, "_pix_tv", None)
        if pix_tv and not pix_tv.isNull():
            painter.drawPixmap(sr, pix_tv)
        return

    # 7. Marquee Arcade
    if eid == "marquee":
        pix_mq = getattr(inst, "_current_marquee_pix", None) or getattr(inst, "_pix_marquee", None)
        if pix_mq and not pix_mq.isNull():
            mrect = _get_native_marquee_rect(inst)
            painter.drawPixmap(mrect, pix_mq)
            painter.fillRect(mrect, QColor(255, 255, 255, 25))
        return

    # 8. Cabinet Arcade
    if eid == "cabinet":
        pix_cab = getattr(inst, "_current_cabinet_pix", None) or getattr(inst, "_pix_cabinet", None)
        if pix_cab and not pix_cab.isNull():
            cw = int(getattr(inst, "CAB_BASE_W", 1300))
            ch = int(getattr(inst, "CAB_BASE_H", 1080))
            painter.drawPixmap(QRect(0, 0, cw, ch), pix_cab)
        return

    # 9. Avatar / Nave Espacial (llama directamente a inst._draw_avatar)
    if eid == "avatar":
        if hasattr(inst, "_draw_avatar"):
            inst._draw_avatar(painter, sr)
        return

    # 10. Logo del Sistema (llama directamente a inst._draw_logo)
    if eid == "logo":
        if hasattr(inst, "_draw_logo"):
            inst._draw_logo(painter, sr)
        return

    # 11. Consola
    if eid == "console":
        pix_con = getattr(inst, "_pix_console", None)
        if pix_con and not pix_con.isNull():
            painter.drawPixmap(sr, pix_con)
        return

    # 12. Cartucho / Disco (llama directamente a inst._draw_cart_or_disc)
    if eid == "cartart":
        if hasattr(inst, "_draw_cart_or_disc"):
            inst._draw_cart_or_disc(painter, sr)
        return

    # 13. Tapa de Consola
    if eid == "console_cover":
        pix_cov = getattr(inst, "_pix_console_cover", None)
        if pix_cov and not pix_cov.isNull():
            painter.drawPixmap(sr, pix_cov)
        return

    # 14. Joystick / Mando
    if eid == "joystick":
        pix_joy = getattr(inst, "_pix_joystick", None)
        if pix_joy and not pix_joy.isNull():
            painter.drawPixmap(sr, pix_joy)
        return

    # 15. Boxart / Carátula (llama directamente a inst._draw_boxart)
    if eid == "boxart":
        if hasattr(inst, "_draw_boxart"):
            inst._draw_boxart(painter, sr)
        return

    # 16. Flyer Arcade (llama directamente a inst._draw_flyer)
    if eid == "flyer":
        if hasattr(inst, "_draw_flyer"):
            inst._draw_flyer(painter, sw, sh)
        return

    # 17. Sombra de Ruleta (gtc-common/wheel/wheel_shadow.png)
    if eid == "wheel_shadow":
        pix_ws = getattr(inst, "_pix_wheel_shadow", None)
        if pix_ws and not pix_ws.isNull():
            painter.drawPixmap(sr, pix_ws)
        elif getattr(inst, "_pix_wheel_art", None):
            bg_w = int(sw * 0.36)
            bg_x = sx + int(sw * 0.65)
            painter.drawPixmap(QRect(bg_x, sy, bg_w, sh), inst._pix_wheel_art)
        return

    # 18. Ruleta de Ruedas (llama directamente a inst._draw_wheel_conveyor o inst._draw_wheel sin el puntero)
    if eid == "wheel_list":
        if hasattr(inst, "_draw_wheel_conveyor"):
            inst._draw_wheel_conveyor(painter, sr)
        elif hasattr(inst, "_draw_wheel"):
            saved_ptr = getattr(inst, "_pix_pointer", None)
            try:
                inst._pix_pointer = None
                inst._draw_wheel(painter, sw, sh)
            finally:
                inst._pix_pointer = saved_ptr
        return

    # 19. Puntero de Ruleta (llama directamente a inst._draw_pointer o al bloque de puntero de inst._draw_wheel)
    if eid == "pointer":
        if hasattr(inst, "_draw_pointer"):
            inst._draw_pointer(painter, sr)
        elif hasattr(inst, "_draw_wheel"):
            saved_off = getattr(inst, "_wheel_spin_offset", 0.0)
            try:
                inst._wheel_spin_offset = 999.0
                inst._draw_wheel(painter, sw, sh)
            finally:
                inst._wheel_spin_offset = saved_off
        return

    # 20. Marco / Barra Inferior (llama directamente a inst._draw_bottom_bar o inst._draw_footer sin texto)
    if eid == "footer_frame":
        if hasattr(inst, "_draw_bottom_bar"):
            saved_games = getattr(inst, "games", [])
            try:
                inst.games = []
                inst._draw_bottom_bar(painter, sr)
            finally:
                inst.games = saved_games
        elif hasattr(inst, "_draw_footer"):
            saved_games = getattr(inst, "games", [])
            try:
                inst.games = []
                inst._draw_footer(painter, sw, sh)
            finally:
                inst.games = saved_games
        return

    # 21. Título del Juego en Barra Inferior (ejecuta inst._draw_bottom_bar o inst._draw_footer en el área izquierda)
    if eid == "title_text":
        painter.save()
        painter.setClipRect(QRect(sx, sy, int(sw * 0.70), sh))
        if hasattr(inst, "_draw_bottom_bar"):
            saved_frame = getattr(inst, "_pix_frame", None)
            try:
                inst._pix_frame = None
                inst._draw_bottom_bar(painter, sr)
            finally:
                inst._pix_frame = saved_frame
        elif hasattr(inst, "_draw_footer"):
            inst._draw_footer(painter, sw, sh)
        painter.restore()
        return

    # 22. Contador de Juegos en Barra Inferior (ejecuta inst._draw_bottom_bar o inst._draw_footer en el área derecha)
    if eid == "counter_text":
        painter.save()
        painter.setClipRect(QRect(sx + int(sw * 0.70), sy, int(sw * 0.30), sh))
        if hasattr(inst, "_draw_bottom_bar"):
            saved_frame = getattr(inst, "_pix_frame", None)
            try:
                inst._pix_frame = None
                inst._draw_bottom_bar(painter, sr)
            finally:
                inst._pix_frame = saved_frame
        elif hasattr(inst, "_draw_footer"):
            inst._draw_footer(painter, sw, sh)
        painter.restore()
        return

    # 23. Capas personalizadas añadidas manualmente por el usuario en el Studio
    if elem is not None:
        rect = QRectF(elem.x, elem.y, elem.w, elem.h).toRect()
        if elem.type == "text":
            games = getattr(inst, "games", [])
            sel_idx = int(getattr(inst, "selected_index", 0))
            cur_game = games[sel_idx] if (games and 0 <= sel_idx < len(games)) else {}
            txt = (elem.text_template or "{title}").format(
                title=cur_game.get("title", "Juego"),
                year=cur_game.get("year", ""),
                manufacturer=cur_game.get("manufacturer", ""),
                genre=cur_game.get("genre", ""),
                index=(sel_idx + 1) if games else 0,
                total=len(games),
            )
            font_fam = getattr(inst, "_font_title", getattr(inst, "_font_bebas", "Segoe UI"))
            painter.setFont(QFont(font_fam, elem.font_size, QFont.Bold))
            painter.setPen(QColor(elem.text_color))
            painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, txt.upper())
        elif elem.resource_path:
            p = Path(elem.resource_path)
            if not p.is_file() and hasattr(inst, "layout_dir"):
                p = Path(inst.layout_dir) / elem.resource_path
            if p.is_file():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    painter.drawPixmap(rect, pix)


def measure_native_layer_bbox(inst, elem_id: str) -> tuple[float, float, float, float]:
    """
    Mide la caja delimitadora exacta (ox, oy, ow, oh) en 1920x1080 ejecutando el renderizado
    nativo de `inst` para esa capa sobre un buffer transparente.
    """
    eid = elem_id.lower()
    if eid == "bg_image":
        return (0.0, 0.0, float(CANONICAL_W), float(CANONICAL_H))

    if eid in ("video_snap", "scanlines_crt", "scratches", "bezel"):
        r = _get_native_snap_rect(inst)
        return (float(r.x()), float(r.y()), float(r.width()), float(r.height()))

    if eid == "marquee":
        r = _get_native_marquee_rect(inst)
        return (float(r.x()), float(r.y()), float(r.width()), float(r.height()))

    if eid == "cabinet":
        return (0.0, 0.0, float(getattr(inst, "CAB_BASE_W", 1300)), float(getattr(inst, "CAB_BASE_H", 1080)))

    if eid == "flyer":
        w = round(CANONICAL_W * 0.22 * 1.30, 1)
        h = round(CANONICAL_H * 0.52 * 1.30, 1)
        x = round(CANONICAL_W * 0.67, 1)
        y = round(CANONICAL_H * 0.26, 1)
        return (x, y, w, h)

    if eid == "cartart" and (hasattr(inst, "CART_RECT") or hasattr(inst, "DISC_RECT")):
        rect_attr = getattr(inst, "DISC_RECT", getattr(inst, "CART_RECT", (0.55, 0.60, 0.19, 0.30)))
        cx = float(getattr(inst, "_disc_end_x_ratio", getattr(inst, "DISC_END_X", getattr(inst, "_cart_end_x_ratio", getattr(inst, "CART_END_X", rect_attr[0])))))
        cy = float(getattr(inst, "_disc_end_y_ratio", getattr(inst, "DISC_END_Y", getattr(inst, "_cart_end_y_ratio", getattr(inst, "CART_END_Y", rect_attr[1])))))
        cw = float(rect_attr[2])
        ch = float(rect_attr[3])
        return (
            round(cx * CANONICAL_W, 1),
            round(cy * CANONICAL_H, 1),
            round(cw * CANONICAL_W, 1),
            round(ch * CANONICAL_H, 1),
        )

    if eid == "boxart" and hasattr(inst, "BOXART_W") and hasattr(inst, "BOXART_H"):
        bw = round(float(inst.BOXART_W) * CANONICAL_W, 1)
        bh = round(float(inst.BOXART_H) * CANONICAL_H, 1)
        bx = round(float(getattr(inst, "BOXART_X", 0.015)) * CANONICAL_W, 1)
        bottom_y = float(getattr(inst, "BOXART_BOTTOM_Y", 0.928)) * CANONICAL_H
        by = round(bottom_y - bh, 1)
        return (bx, by, bw, bh)

    if eid in ("footer_frame", "title_text", "counter_text"):
        bar_h = float(int(CANONICAL_H * 0.075)) if hasattr(inst, "_draw_bottom_bar") else float(max(26, int(CANONICAL_H * 0.042)))
        bar_y = float(CANONICAL_H) - bar_h
        if eid == "footer_frame":
            return (0.0, bar_y, float(CANONICAL_W), bar_h)
        if eid == "title_text":
            x_off = round(CANONICAL_W * (0.08 if hasattr(inst, "_draw_bottom_bar") else 0.04), 1)
            return (x_off, bar_y, round(CANONICAL_W * 0.62, 1), bar_h)
        if eid == "counter_text":
            return (round(CANONICAL_W * 0.70, 1), bar_y, round(CANONICAL_W * 0.26, 1), bar_h)

    # Para cualquier otra capa (tv_bezel, console, console_cover, joystick, avatar, logo,
    # wheel_shadow, wheel_list, pointer), ejecutamos su renderizado real en un QImage 480x270
    # y medimos los píxeles reales que el código de theme_layout.py pintó.
    scan_w, scan_h = 480, 270
    img = QImage(scan_w, scan_h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(scan_w / float(CANONICAL_W), scan_h / float(CANONICAL_H))
    try:
        render_native_layer(p, inst, elem_id, QRect(0, 0, CANONICAL_W, CANONICAL_H))
    finally:
        p.end()

    bbox = get_qimage_alpha_bbox(img)
    if bbox:
        return bbox
    return (0.0, 0.0, float(CANONICAL_W), float(CANONICAL_H))


def sync_quiet_studio_instance(inst, games: list[dict[str, Any]], selected_game: dict[str, Any] | None = None):
    """
    Sincroniza la instancia real de ThemeLayout (`inst`) para el editor de Layout Studio:
    - Detiene todos los temporizadores y reproductores en segundo plano (0% CPU en reposo).
    - Carga los artes del juego de muestra (`_update_current_selection`, `_on_art_debounce_timeout`, `_load_pending_art`).
    - Coloca las variables de animación en su posición final de reposo para que todos los elementos
      (`flyer`, `cartart`, `boxart`, `logo`, `avatar`, `pointer`, `wheel`) sean 100% visibles y editables.
    """
    if not inst:
        return

    from PySide6.QtCore import QTimer
    from PySide6.QtMultimedia import QMediaPlayer

    inst.hide()
    inst.resize(CANONICAL_W, CANONICAL_H)
    if hasattr(inst, "set_media_muted"):
        inst.set_media_muted(True)

    # Detener worker asíncrono si existe
    if hasattr(inst, "_wheel_worker") and inst._wheel_worker:
        try:
            inst._wheel_worker.stop()
            inst._wheel_worker.wait(100)
        except Exception:
            pass

    # Asignar lista de juegos y seleccionar el índice actual
    safe_games = list(games) if games else []
    if not safe_games and selected_game:
        safe_games = [selected_game]
    inst.games = safe_games

    sel_idx = 0
    if selected_game and safe_games:
        target_id = selected_game.get("id")
        for i, g in enumerate(safe_games):
            if g.get("id") == target_id:
                sel_idx = i
                break
    inst.selected_index = sel_idx

    # Ejecutar la lógica nativa de selección de juego del propio ThemeLayout
    try:
        if hasattr(inst, "_update_current_selection"):
            inst._update_current_selection()
        if hasattr(inst, "_on_art_debounce_timeout"):
            inst._on_art_debounce_timeout()
        if hasattr(inst, "_load_pending_art"):
            inst._load_pending_art()
        if hasattr(inst, "_on_flyer_delay_timeout"):
            inst._on_flyer_delay_timeout()
    except Exception:
        pass

    # Si el juego seleccionado no tenía flyer en disco, buscar en la lista actual el primer flyer real disponible
    if hasattr(inst, "_current_flyer_pix") and (inst._current_flyer_pix is None or inst._current_flyer_pix.isNull()):
        if safe_games and hasattr(inst, "_resolve_game_media") and hasattr(inst, "_get_cached_art_pixmap"):
            for g in safe_games[:80]:
                try:
                    m = inst._resolve_game_media(g)
                    ff = m.get("flyer") if m else None
                    if ff and os.path.isfile(ff):
                        fpix = inst._get_cached_art_pixmap(ff)
                        if fpix and not fpix.isNull():
                            inst._current_flyer_pix = fpix
                            break
                except Exception:
                    pass

    # Precargar sincrónicamente solo los 13 logos visibles alrededor del juego seleccionado
    if safe_games and hasattr(inst, "_wheel_pixmaps"):
        from playnexus.services.media import resolve_game_media
        n = len(safe_games)
        for off in range(-6, 7):
            g = safe_games[(sel_idx + off) % n]
            gid = g.get("id")
            if gid and gid not in inst._wheel_pixmaps:
                m = resolve_game_media(g)
                wf = m.get("wheel")
                if wf and os.path.isfile(wf):
                    pix = QPixmap(wf)
                    if not pix.isNull():
                        inst._wheel_pixmaps[gid] = pix

    # Desactivar banderas de reproducción automática para que ningún callback de Media Foundation
    # reactive videos en segundo plano en la instancia oculta del editor
    inst._is_emulator_running = True
    inst._want_game_video_playing = False
    inst._want_video_playing = False

    # Detener todos los QTimer y QMediaPlayer hijos de esta instancia de edición
    from PySide6.QtCore import QUrl
    for timer in inst.findChildren(QTimer):
        try:
            timer.stop()
        except Exception:
            pass
    for player in inst.findChildren(QMediaPlayer):
        try:
            player.blockSignals(True)
            player.stop()
            player.setSource(QUrl())
        except Exception:
            pass

    # Fijar estado de reposo para que todos los elementos animados se dibujen en su posición final
    if hasattr(inst, "_flyer_ready"):
        inst._flyer_ready = True
    if hasattr(inst, "_flyer_slide"):
        inst._flyer_slide = 0.0
    if hasattr(inst, "_wheel_alpha"):
        inst._wheel_alpha = 255.0
    if hasattr(inst, "_wheel_spin_offset"):
        inst._wheel_spin_offset = 0.0
    if hasattr(inst, "_logo_current_y_offset_ratio"):
        inst._logo_current_y_offset_ratio = 0.0
    if hasattr(inst, "_boxart_current_x_offset_ratio"):
        inst._boxart_current_x_offset_ratio = 0.0
    if hasattr(inst, "_boxart_current_x_ratio"):
        inst._boxart_current_x_ratio = getattr(inst, "_boxart_end_x_ratio", getattr(inst, "BOXART_END_X", getattr(inst, "BOXART_X", 0.015)))
    if hasattr(inst, "_boxart_current_y_ratio"):
        inst._boxart_current_y_ratio = getattr(inst, "_boxart_end_y_ratio", getattr(inst, "BOXART_END_Y", getattr(inst, "BOXART_BOTTOM_Y", 0.928)))
    if hasattr(inst, "_boxart_alpha"):
        inst._boxart_alpha = 1.0
    if hasattr(inst, "_avatar_offset_x"):
        inst._avatar_offset_x = 0.0
    if hasattr(inst, "_avatar_offset_y"):
        inst._avatar_offset_y = 0.0
    if hasattr(inst, "CART_RECT"):
        inst._cart_current_x_ratio = getattr(inst, "_cart_end_x_ratio", getattr(inst, "CART_END_X", inst.CART_RECT[0]))
        inst._cart_current_y_ratio = getattr(inst, "_cart_end_y_ratio", getattr(inst, "CART_END_Y", inst.CART_RECT[1]))
    if hasattr(inst, "DISC_RECT") or hasattr(inst, "_disc_current_y_ratio"):
        disc_rect = getattr(inst, "DISC_RECT", getattr(inst, "CART_RECT", (0.55, 0.60, 0.19, 0.30)))
        if hasattr(inst, "_disc_current_x_ratio"):
            inst._disc_current_x_ratio = getattr(inst, "_disc_end_x_ratio", getattr(inst, "DISC_END_X", disc_rect[0]))
        inst._disc_current_y_ratio = getattr(inst, "_disc_end_y_ratio", getattr(inst, "DISC_END_Y", disc_rect[1]))
    if hasattr(inst, "_pointer_rest_x_ratio"):
        inst._pointer_current_x_ratio = inst._pointer_rest_x_ratio
        inst._pointer_anim_tick = 0


def extract_elements_from_theme_instance(inst, code: str) -> list[LayoutElement]:
    """
    Lee el AST de `paintEvent` en `theme_layout.py` en orden exacto de líneas de ejecución
    y consulta los atributos y métodos reales cargados en `inst` para construir las capas
    del Studio con 100% de fidelidad al código del layout.
    """
    # Mapear tokens de atributos/métodos de self usados en paintEvent -> (elem_id, nombre, tipo, media_key, anim_type)
    TOKEN_SPEC: dict[str, tuple[str, str, str, str, str]] = {
        "_bg_video_image": ("bg_image", "Fondo (Video / Imagen)", "image", "", ""),
        "_pix_bg_fallback": ("bg_image", "Fondo (gtc-common)", "image", "", ""),
        "_pix_bkg": ("bg_image", "Fondo del Layout", "image", "", ""),
        "_current_artwork_pixmap": ("bg_image", "Artwork de Fondo", "image", "", ""),
        "_game_video_image": ("video_snap", "Pantalla CRT (Video Snap)", "video", "video", ""),
        "_current_video_image": ("video_snap", "Pantalla TV / Video Snap", "video", "video", ""),
        "_pix_scanlines": ("scanlines_crt", "Scanlines CRT (gtc-common)", "effect", "", ""),
        "_pix_scratches": ("scratches", "Reflejo Vidrio CRT (gtc-common)", "effect", "", ""),
        "_current_bezel_pix": ("bezel", "Bisel de Monitor (Bezel)", "image", "bezel", ""),
        "_pix_tv": ("tv_bezel", "Televisor CRT (tv.png)", "image", "", ""),
        "_current_marquee_pix": ("marquee", "Marquesina (Marquee)", "marquee", "marquee", ""),
        "_current_cabinet_pix": ("cabinet", "Mueble Arcade (Cabinet)", "cabinet", "cabinet", ""),
        "_pix_cabinet": ("cabinet", "Mueble Arcade (Cabinet)", "cabinet", "cabinet", ""),
        "_draw_avatar": ("avatar", "Avatar / Personaje", "image", "", "avatar_float"),
        "_draw_logo": ("logo", "Logotipo del Sistema", "image", "", "logo_bounce"),
        "_pix_console": ("console", "Consola (console.png)", "image", "", ""),
        "_draw_cart_or_disc": ("cartart", "Cartucho / Disco", "image", "cartart", "cart_drop"),
        "_pix_console_cover": ("console_cover", "Tapa de Consola (console_cover.png)", "image", "", ""),
        "_pix_joystick": ("joystick", "Joystick / Mando (joystick.png)", "image", "", ""),
        "_draw_boxart": ("boxart", "Carátula (Box Art)", "image", "boxart", "boxart_slide_fade"),
        "_draw_flyer": ("flyer", "Flyer Publicitario", "image", "flyer", "flyer_slide_right"),
        "_pix_wheel_shadow": ("wheel_shadow", "Sombra de Ruleta (gtc-common)", "image", "", ""),
        "_draw_wheel_conveyor": ("wheel_list", "Ruleta Curva (Wheel Conveyor)", "wheel", "wheel", ""),
        "_draw_pointer": ("pointer", "Puntero de Ruleta", "image", "", "pointer_pulse"),
    }

    ordered_tokens: list[str] = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "paintEvent":
                subnodes = [
                    sub for sub in ast.walk(node)
                    if isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "self"
                ]
                subnodes.sort(key=lambda s: (getattr(s, "lineno", 0), getattr(s, "col_offset", 0)))
                for sub in subnodes:
                    ordered_tokens.append(sub.attr)
                break
    except Exception:
        pass

    # Asegurar que las animaciones de `inst` estén en su estado de reposo para medir su caja exacta
    if hasattr(inst, "_flyer_ready"):
        inst._flyer_ready = True
    if hasattr(inst, "_flyer_slide"):
        inst._flyer_slide = 0.0
    if hasattr(inst, "_logo_current_y_offset_ratio"):
        inst._logo_current_y_offset_ratio = 0.0
    if hasattr(inst, "_boxart_current_x_offset_ratio"):
        inst._boxart_current_x_offset_ratio = 0.0
    if hasattr(inst, "_boxart_current_x_ratio"):
        inst._boxart_current_x_ratio = getattr(inst, "_boxart_end_x_ratio", getattr(inst, "BOXART_END_X", getattr(inst, "BOXART_X", 0.015)))
    if hasattr(inst, "_boxart_current_y_ratio"):
        inst._boxart_current_y_ratio = getattr(inst, "_boxart_end_y_ratio", getattr(inst, "BOXART_END_Y", getattr(inst, "BOXART_BOTTOM_Y", 0.928)))
    if hasattr(inst, "_boxart_alpha"):
        inst._boxart_alpha = 1.0
    if hasattr(inst, "_avatar_offset_x"):
        inst._avatar_offset_x = 0.0
    if hasattr(inst, "_avatar_offset_y"):
        inst._avatar_offset_y = 0.0
    if hasattr(inst, "CART_RECT"):
        inst._cart_current_x_ratio = getattr(inst, "_cart_end_x_ratio", getattr(inst, "CART_END_X", inst.CART_RECT[0]))
        inst._cart_current_y_ratio = getattr(inst, "_cart_end_y_ratio", getattr(inst, "CART_END_Y", inst.CART_RECT[1]))
    if hasattr(inst, "DISC_RECT") or hasattr(inst, "_disc_current_y_ratio"):
        disc_rect = getattr(inst, "DISC_RECT", getattr(inst, "CART_RECT", (0.55, 0.60, 0.19, 0.30)))
        if hasattr(inst, "_disc_current_x_ratio"):
            inst._disc_current_x_ratio = getattr(inst, "_disc_end_x_ratio", getattr(inst, "DISC_END_X", disc_rect[0]))
        inst._disc_current_y_ratio = getattr(inst, "_disc_end_y_ratio", getattr(inst, "DISC_END_Y", disc_rect[1]))
    if hasattr(inst, "_pointer_rest_x_ratio"):
        inst._pointer_current_x_ratio = inst._pointer_rest_x_ratio
        inst._pointer_anim_tick = 0

    elements: list[LayoutElement] = []
    seen_ids: set[str] = set()
    z_counter = 5

    def _add_step(eid: str, name: str, etype: str, media_key: str, anim_type: str):
        nonlocal z_counter
        if eid in seen_ids:
            return
        # Verificar si el recurso opcional realmente existe en esta instancia
        if eid == "console_cover" and not getattr(inst, "_pix_console_cover", None):
            return
        if eid == "joystick" and not getattr(inst, "_pix_joystick", None):
            return
        if eid == "tv_bezel" and not getattr(inst, "_pix_tv", None):
            return
        if eid == "console" and not getattr(inst, "_pix_console", None):
            return
        if eid == "avatar" and not getattr(inst, "_pix_avatar", None):
            return
        if eid == "logo" and not getattr(inst, "_pix_logo", None):
            return
        if eid == "scratches" and not getattr(inst, "_pix_scratches", None):
            return
        if eid == "wheel_shadow" and not (getattr(inst, "_pix_wheel_shadow", None) or getattr(inst, "_pix_wheel_art", None)):
            return

        seen_ids.add(eid)
        ox, oy, ow, oh = measure_native_layer_bbox(inst, eid)
        elem = LayoutElement(
            id=eid,
            name=name,
            type=etype,
            x=ox,
            y=oy,
            w=ow,
            h=oh,
            orig_rect=(ox, oy, ow, oh),
            z_index=z_counter,
            media_key=media_key,
            anim_type=anim_type,
        )
        elements.append(elem)
        z_counter += 5

    for tok in ordered_tokens:
        if tok in TOKEN_SPEC:
            _add_step(*TOKEN_SPEC[tok])
        elif tok == "_draw_wheel":
            # En At-The-Arcade Flex, _draw_wheel dibuja la ruleta y el puntero
            _add_step("wheel_list", "Ruleta de Ruedas (Wheel)", "wheel", "wheel", "")
            _add_step("pointer", "Puntero de Ruleta", "image", "", "pointer_pulse")
        elif tok in ("_draw_bottom_bar", "_draw_footer"):
            if getattr(inst, "_pix_frame", None) or tok == "_draw_footer":
                _add_step("footer_frame", "Barra Inferior (Footer)", "image", "", "")
            _add_step("title_text", "Título del Juego (Footer)", "text", "", "")
            _add_step("counter_text", "Contador de Juegos (Footer)", "text", "", "")

    return elements


def _get_cached_rest_layer_pixmap(
    inst,
    elem_id: str,
    orig_rect: tuple[float, float, float, float],
    dst_w: int,
    dst_h: int,
) -> QPixmap | None:
    """
    Renderiza una única vez la capa estática/en reposo (`avatar`, `logo`, `pointer`) en 1920x1080,
    recorta su `orig_rect` y cachea el `QPixmap` pre-escalado a `(dst_w, dst_h)` para dibujo 1:1 en ~0.1 ms.
    """
    if dst_w <= 0 or dst_h <= 0:
        return None
    cache = getattr(inst, "_studio_pix_cache", None)
    if cache is None:
        cache = {}
        inst._studio_pix_cache = cache

    ox, oy, ow, oh = orig_rect
    key = ("rest_layer", elem_id, round(ox, 1), round(oy, 1), round(ow, 1), round(oh, 1), dst_w, dst_h)
    cached = cache.get(key)
    if cached is not None:
        return cached

    base_key = ("rest_base_1080", elem_id, round(ox, 1), round(oy, 1), round(ow, 1), round(oh, 1))
    cropped_base = cache.get(base_key)
    if cropped_base is None:
        # Guardar y fijar estado de reposo temporalmente para capturar la textura base exacta
        saved_av_x = getattr(inst, "_avatar_offset_x", 0.0)
        saved_av_y = getattr(inst, "_avatar_offset_y", 0.0)
        saved_logo_y = getattr(inst, "_logo_current_y_offset_ratio", 0.0)
        saved_ptr_x = getattr(inst, "_pointer_current_x_ratio", getattr(inst, "_pointer_rest_x_ratio", 0.0))
        saved_ptr_t = getattr(inst, "_pointer_anim_tick", 0)
        try:
            if hasattr(inst, "_avatar_offset_x"):
                inst._avatar_offset_x = 0.0
                inst._avatar_offset_y = 0.0
            if hasattr(inst, "_logo_current_y_offset_ratio"):
                inst._logo_current_y_offset_ratio = 0.0
            if hasattr(inst, "_pointer_rest_x_ratio"):
                inst._pointer_current_x_ratio = inst._pointer_rest_x_ratio
                inst._pointer_anim_tick = 0

            full_img = QImage(CANONICAL_W, CANONICAL_H, QImage.Format_ARGB32_Premultiplied)
            full_img.fill(Qt.transparent)
            p = QPainter(full_img)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            render_native_layer(p, inst, elem_id, QRect(0, 0, CANONICAL_W, CANONICAL_H))
            p.end()

            rx = max(0, int(round(ox)))
            ry = max(0, int(round(oy)))
            rw = max(1, min(CANONICAL_W - rx, int(round(ow))))
            rh = max(1, min(CANONICAL_H - ry, int(round(oh))))
            cropped_base = QPixmap.fromImage(full_img.copy(rx, ry, rw, rh))
            cache[base_key] = cropped_base
        finally:
            if hasattr(inst, "_avatar_offset_x"):
                inst._avatar_offset_x = saved_av_x
                inst._avatar_offset_y = saved_av_y
            if hasattr(inst, "_logo_current_y_offset_ratio"):
                inst._logo_current_y_offset_ratio = saved_logo_y
            if hasattr(inst, "_pointer_rest_x_ratio"):
                inst._pointer_current_x_ratio = saved_ptr_x
                inst._pointer_anim_tick = saved_ptr_t

    if cropped_base.width() == dst_w and cropped_base.height() == dst_h:
        scaled = cropped_base
    else:
        scaled = cropped_base.scaled(dst_w, dst_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    cache[key] = scaled
    return scaled


def render_element_in_screen_space(
    painter: QPainter,
    inst,
    elem: LayoutElement,
    sr: QRect,
    anim_dx: float = 0.0,
    anim_dy: float = 0.0,
    anim_op: float = 1.0,
):
    """
    Renderiza una capa directamente en las coordenadas reales de pantalla `sr = QRect(sx, sy, sw, sh)`
    usando texturas `QPixmap` pre-recortadas y pre-escaladas a relación 1:1 (~0.2 ms por capa)
    y respetando el 100% del tamaño real y animaciones de `theme_layout.py`.
    """
    sx, sy, sw, sh = sr.x(), sr.y(), sr.width(), sr.height()
    if sw <= 0 or sh <= 0:
        return

    scale_x = sw / float(CANONICAL_W)
    scale_y = sh / float(CANONICAL_H)

    ox, oy, ow, oh = elem.orig_rect if (elem.orig_rect and len(elem.orig_rect) == 4) else (elem.x, elem.y, elem.w, elem.h)
    ow = max(1.0, ow)
    oh = max(1.0, oh)

    pins = elem.corner_pins
    if pins and len(pins) == 4:
        # Si tiene deformación de perspectiva de 4 esquinas, usar matriz proyectiva quadToQuad
        painter.save()
        painter.translate(sx, sy)
        painter.scale(scale_x, scale_y)
        render_element_with_transform(painter, inst, elem, anim_dx=anim_dx, anim_dy=anim_dy, anim_op=anim_op)
        painter.restore()
        return

    painter.save()
    painter.setOpacity(max(0.0, min(1.0, elem.opacity * anim_op)))

    tx = elem.x + anim_dx
    ty = elem.y + anim_dy
    tw = max(1.0, elem.w)
    th = max(1.0, elem.h)

    rel_sx = tw / ow
    rel_sy = th / oh

    dst_x = sx + int(round(tx * scale_x))
    dst_y = sy + int(round(ty * scale_y))
    dst_w = max(1, int(round(tw * scale_x)))
    dst_h = max(1, int(round(th * scale_y)))
    dst_rect = QRect(dst_x, dst_y, dst_w, dst_h)

    # Rectángulo virtual 16:9 que proyecta linealmente orig_rect -> dst_rect para métodos nativos _draw_*
    mw = max(1, int(round(sw * rel_sx)))
    mh = max(1, int(round(sh * rel_sy)))
    mx = dst_x - int(round((ox / float(CANONICAL_W)) * mw))
    my = dst_y - int(round((oy / float(CANONICAL_H)) * mh))
    sr_mapped = QRect(mx, my, mw, mh)

    eid = elem.id.lower()

    if eid == "bg_image":
        bg_vid = getattr(inst, "_bg_video_image", None)
        if bg_vid and not bg_vid.isNull():
            painter.drawImage(dst_rect, bg_vid)
        else:
            pix_bg = (
                getattr(inst, "_pix_bg_fallback", None)
                or getattr(inst, "_pix_bkg", None)
                or getattr(inst, "_current_artwork_pixmap", None)
            )
            if pix_bg and not pix_bg.isNull():
                spix = _get_cached_scaled_pixmap(inst, ("bg_image", id(pix_bg), dst_w, dst_h), pix_bg, None, dst_w, dst_h)
                if spix:
                    painter.drawPixmap(dst_x, dst_y, spix)
            else:
                painter.fillRect(dst_rect, QColor(10, 8, 16))
        painter.restore()
        return

    if eid == "video_snap":
        painter.fillRect(dst_rect, QColor(0, 0, 0))
        vid_img = getattr(inst, "_game_video_image", None) or getattr(inst, "_current_video_image", None)
        if vid_img and not vid_img.isNull():
            if hasattr(inst, "SNAP_LOCAL_RECT"):
                vw, vh = vid_img.width(), vid_img.height()
                s = min(dst_w / vw, dst_h / vh) if vw > 0 and vh > 0 else 1.0
                dw, dh = int(vw * s), int(vh * s)
                vx = dst_x + (dst_w - dw) // 2
                vy = dst_y + (dst_h - dh) // 2
                painter.drawImage(QRect(vx, vy, dw, dh), vid_img)
            else:
                painter.drawImage(dst_rect, vid_img)
        painter.restore()
        return

    if eid == "scanlines_crt":
        if not getattr(inst, "_pix_scanlines", None):
            scan_const = getattr(inst, "SCANLINES_IMAGE", None)
            if scan_const and Path(scan_const).is_file() and hasattr(inst, "_load_pixmap"):
                inst._pix_scanlines = inst._load_pixmap(str(scan_const))
            elif hasattr(inst, "layout_dir"):
                scan_path = Path(inst.layout_dir).parent / "gtc-common" / "art" / "scanlines_1920.png"
                if scan_path.is_file() and hasattr(inst, "_load_pixmap"):
                    inst._pix_scanlines = inst._load_pixmap(str(scan_path))
        pix_scan = getattr(inst, "_pix_scanlines", None)
        if pix_scan and not pix_scan.isNull():
            spix = _get_cached_scaled_pixmap(inst, ("scanlines", id(pix_scan), dst_w, dst_h), pix_scan, None, dst_w, dst_h)
            if spix:
                painter.setOpacity(painter.opacity() * 0.35)
                painter.drawPixmap(dst_x, dst_y, spix)
        painter.restore()
        return

    if eid == "scratches":
        pix_scr = getattr(inst, "_pix_scratches", None)
        if pix_scr and not pix_scr.isNull():
            spix = _get_cached_scaled_pixmap(inst, ("scratches", id(pix_scr), dst_w, dst_h), pix_scr, None, dst_w, dst_h)
            if spix:
                painter.setOpacity(painter.opacity() * 0.40)
                painter.drawPixmap(dst_x, dst_y, spix)
        painter.restore()
        return

    if eid == "bezel":
        pix_bz = getattr(inst, "_current_bezel_pix", None) or getattr(inst, "_pix_bezel", None)
        if pix_bz and not pix_bz.isNull():
            spix = _get_cached_scaled_pixmap(inst, ("bezel", id(pix_bz), dst_w, dst_h), pix_bz, None, dst_w, dst_h)
            if spix:
                painter.drawPixmap(dst_x, dst_y, spix)
        painter.restore()
        return

    if eid == "marquee":
        pix_mq = getattr(inst, "_current_marquee_pix", None) or getattr(inst, "_pix_marquee", None)
        if pix_mq and not pix_mq.isNull():
            spix = _get_cached_scaled_pixmap(inst, ("marquee", id(pix_mq), dst_w, dst_h), pix_mq, None, dst_w, dst_h)
            if spix:
                painter.drawPixmap(dst_x, dst_y, spix)
                painter.fillRect(dst_rect, QColor(255, 255, 255, 25))
        painter.restore()
        return

    if eid == "cabinet":
        pix_cab = getattr(inst, "_current_cabinet_pix", None) or getattr(inst, "_pix_cabinet", None)
        if pix_cab and not pix_cab.isNull():
            spix = _get_cached_scaled_pixmap(inst, ("cabinet", id(pix_cab), dst_w, dst_h), pix_cab, None, dst_w, dst_h)
            if spix:
                painter.drawPixmap(dst_x, dst_y, spix)
        painter.restore()
        return

    if eid in ("tv_bezel", "console", "console_cover", "joystick", "wheel_shadow"):
        attr_map = {
            "tv_bezel": "_pix_tv",
            "console": "_pix_console",
            "console_cover": "_pix_console_cover",
            "joystick": "_pix_joystick",
            "wheel_shadow": "_pix_wheel_shadow",
        }
        pix = getattr(inst, attr_map[eid], None)
        if pix and not pix.isNull():
            spix = _get_cached_scaled_pixmap(inst, (eid, id(pix), dst_w, dst_h), pix, (ox, oy, ow, oh), dst_w, dst_h)
            if spix:
                painter.drawPixmap(dst_x, dst_y, spix)
        elif eid == "wheel_shadow" and getattr(inst, "_pix_wheel_art", None):
            w_art = inst._pix_wheel_art
            spix = _get_cached_scaled_pixmap(inst, ("wheel_art", id(w_art), dst_w, dst_h), w_art, None, dst_w, dst_h)
            if spix:
                painter.drawPixmap(dst_x, dst_y, spix)
        painter.restore()
        return

    if eid == "avatar":
        spix = _get_cached_rest_layer_pixmap(inst, "avatar", (ox, oy, ow, oh), dst_w, dst_h)
        if spix:
            adx = int(round(getattr(inst, "_avatar_offset_x", 0.0) * scale_x * rel_sx))
            ady = int(round(getattr(inst, "_avatar_offset_y", 0.0) * scale_y * rel_sy))
            painter.drawPixmap(dst_x + adx, dst_y + ady, spix)
        painter.restore()
        return

    if eid == "logo":
        spix = _get_cached_rest_layer_pixmap(inst, "logo", (ox, oy, ow, oh), dst_w, dst_h)
        if spix:
            ady = int(round(mh * getattr(inst, "_logo_current_y_offset_ratio", 0.0)))
            painter.drawPixmap(dst_x, dst_y + ady, spix)
        painter.restore()
        return

    if eid == "pointer":
        spix = _get_cached_rest_layer_pixmap(inst, "pointer", (ox, oy, ow, oh), dst_w, dst_h)
        if spix:
            rest_r = getattr(inst, "_pointer_rest_x_ratio", 0.0)
            cur_r = getattr(inst, "_pointer_current_x_ratio", rest_r)
            tick = getattr(inst, "_pointer_anim_tick", 0)
            pulse = int(round(mw * (rest_r - cur_r)))
            osc = int(round(mw * (math.sin(tick * 0.08) * 0.002)))
            if hasattr(inst, "_wheel_alpha"):
                painter.setOpacity(painter.opacity() * (getattr(inst, "_wheel_alpha", 255.0) / 255.0))
            painter.drawPixmap(dst_x - pulse + osc, dst_y, spix)
        painter.restore()
        return

    if eid in ("cartart", "boxart", "wheel_list"):
        if eid == "wheel_list" and hasattr(inst, "_wheel_alpha"):
            painter.setOpacity(painter.opacity() * (getattr(inst, "_wheel_alpha", 255.0) / 255.0))
        if eid == "wheel_list" and not hasattr(inst, "_draw_wheel_conveyor") and hasattr(inst, "_draw_wheel"):
            painter.translate(mx, my)
            render_native_layer(painter, inst, eid, QRect(0, 0, mw, mh), elem=elem)
        else:
            render_native_layer(painter, inst, eid, sr_mapped, elem=elem)
        painter.restore()
        return

    if eid == "flyer":
        painter.translate(mx, my)
        render_native_layer(painter, inst, eid, QRect(0, 0, mw, mh), elem=elem)
        painter.restore()
        return

    if eid in ("footer_frame", "title_text", "counter_text"):
        if hasattr(inst, "_draw_bottom_bar"):
            render_native_layer(painter, inst, eid, sr_mapped, elem=elem)
        else:
            painter.translate(mx, my)
            render_native_layer(painter, inst, eid, QRect(0, 0, mw, mh), elem=elem)
        painter.restore()
        return

    # Capas personalizadas
    render_native_layer(painter, inst, eid, sr_mapped, elem=elem)
    painter.restore()


def render_element_with_transform(
    painter: QPainter,
    inst,
    elem: LayoutElement,
    anim_dx: float = 0.0,
    anim_dy: float = 0.0,
    anim_op: float = 1.0,
):
    """
    Renderiza un elemento en coordenadas canónicas 1920x1080 (o con 4 pines de perspectiva).
    """
    pins = elem.corner_pins
    if not (pins and len(pins) == 4):
        render_element_in_screen_space(
            painter,
            inst,
            elem,
            QRect(0, 0, CANONICAL_W, CANONICAL_H),
            anim_dx=anim_dx,
            anim_dy=anim_dy,
            anim_op=anim_op,
        )
        return

    painter.save()
    painter.setOpacity(max(0.0, min(1.0, elem.opacity * anim_op)))

    ox, oy, ow, oh = elem.orig_rect if (elem.orig_rect and len(elem.orig_rect) == 4) else (elem.x, elem.y, elem.w, elem.h)
    ow = max(1.0, ow)
    oh = max(1.0, oh)

    src_poly = QPolygonF([
        QPointF(ox, oy),
        QPointF(ox + ow, oy),
        QPointF(ox + ow, oy + oh),
        QPointF(ox, oy + oh),
    ])
    dst_poly = QPolygonF([QPointF(p[0] + anim_dx, p[1] + anim_dy) for p in pins])

    if src_poly != dst_poly:
        trans = QTransform()
        if QTransform.quadToQuad(src_poly, dst_poly, trans):
            painter.setTransform(trans * painter.transform())

    render_native_layer(painter, inst, elem.id, QRect(0, 0, CANONICAL_W, CANONICAL_H), elem=elem)
    painter.restore()


def update_studio_overrides(layout_widget, elements_list: list[LayoutElement | dict[str, Any]]):
    """Actualiza en caliente la lista de elementos del Sandbox sin reiniciar la ventana."""
    parsed: list[LayoutElement] = []
    for item in elements_list:
        if isinstance(item, LayoutElement):
            parsed.append(item)
        elif isinstance(item, dict):
            parsed.append(LayoutElement.from_dict(item))
    layout_widget._studio_elements = sorted(parsed, key=lambda e: e.z_index)
    layout_widget._studio_elements_map = {e.id: e for e in parsed}
    layout_widget.update()


def install_studio_overrides(layout_widget, elements_list: list[LayoutElement | dict[str, Any]]):
    """
    Instala el motor de renderizado de alta velocidad (1:1 pre-escalado) sobre `layout_widget`
    (Sandbox o Layout guardado), respetando el 100% del tamaño real y animaciones del layout.
    """
    update_studio_overrides(layout_widget, elements_list)

    def _studio_paint_event(event):
        painter = QPainter(layout_widget)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w, h = layout_widget.width(), layout_widget.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        painter.fillRect(0, 0, w, h, QColor(0, 0, 0))

        if hasattr(layout_widget, "_get_target_rect"):
            sr = layout_widget._get_target_rect()
        else:
            sr = QRect(0, 0, w, h)

        elems: list[LayoutElement] = getattr(layout_widget, "_studio_elements", [])
        for elem in elems:
            if not elem.visible:
                continue
            render_element_in_screen_space(painter, layout_widget, elem, sr)

        painter.end()

    layout_widget._studio_override_installed = True
    layout_widget.paintEvent = _studio_paint_event
