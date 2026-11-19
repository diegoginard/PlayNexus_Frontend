import os
import threading
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal, Qt, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QPainterPath
from playnexus.services.media import find_media_file, resolve_game_media


class CoverCacheLRU:
    """Caché acotada LRU para pixmaps pre-escalados evitando fugas de VRAM/RAM."""

    def __init__(self, max_items: int = 512):
        self._max_items = max(16, int(max_items))
        self._data: OrderedDict[Any, Any] = OrderedDict()

    def get(self, key: Any) -> Any:
        val = self._data.get(key)
        if val is not None:
            self._data.move_to_end(key)
        return val

    def __contains__(self, key: Any) -> bool:
        return key in self._data

    def put(self, key: Any, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self._max_items:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


def _scale_qimage_cover(
    img: QImage,
    target_w: int,
    target_h: int,
    aspect_mode: Qt.AspectRatioMode = Qt.KeepAspectRatioByExpanding,
) -> QImage:
    """Pre-escala un QImage en hilo worker al tamaño exacto destino con recorte centrado si expande."""
    if img.isNull() or target_w <= 0 or target_h <= 0:
        return QImage()
    if img.width() == target_w and img.height() == target_h:
        return img
    scaled = img.scaled(QSize(target_w, target_h), aspect_mode, Qt.SmoothTransformation)
    if aspect_mode == Qt.KeepAspectRatioByExpanding and (scaled.width() > target_w or scaled.height() > target_h):
        crop_x = max(0, (scaled.width() - target_w) // 2)
        crop_y = max(0, (scaled.height() - target_h) // 2)
        return scaled.copy(crop_x, crop_y, min(target_w, scaled.width()), min(target_h, scaled.height()))
    return scaled


def make_rounded_cover_pixmap(
    src: QPixmap | QImage | None,
    width: int,
    height: int,
    radius: int = 10,
    aspect_mode: Qt.AspectRatioMode = Qt.KeepAspectRatioByExpanding,
) -> QPixmap:
    """Convierte y recorta con bordes redondeados un QImage/QPixmap una única vez fuera de `paint()`."""
    if src is None or width <= 0 or height <= 0:
        return QPixmap()
    if isinstance(src, QImage):
        if src.isNull():
            return QPixmap()
        if src.width() != width or src.height() != height:
            src = _scale_qimage_cover(src, width, height, aspect_mode)
        pix = QPixmap.fromImage(src)
    else:
        if src.isNull():
            return QPixmap()
        if src.width() != width or src.height() != height:
            scaled = src.scaled(QSize(width, height), aspect_mode, Qt.SmoothTransformation)
            if aspect_mode == Qt.KeepAspectRatioByExpanding and (scaled.width() > width or scaled.height() > height):
                cx = max(0, (scaled.width() - width) // 2)
                cy = max(0, (scaled.height() - height) // 2)
                pix = scaled.copy(cx, cy, min(width, scaled.width()), min(height, scaled.height()))
            else:
                pix = scaled
        else:
            pix = src

    if radius <= 0 and pix.width() == width and pix.height() == height:
        return pix

    out = QPixmap(width, height)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    if radius > 0:
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, width, height, radius, radius)
        painter.setClipPath(clip)
    dx = (width - pix.width()) // 2
    dy = (height - pix.height()) // 2
    painter.drawPixmap(dx, dy, pix)
    painter.end()
    return out


class WheelPreloadWorker(QThread):
    """
    Hilo de trabajo en segundo plano para pre-cargar y pre-escalar logotipos de rueda (wheel)
    de forma asíncrona sin bloquear jamás el renderizado de la interfaz ni la tasa de cuadros.
    """
    wheel_loaded = Signal(int, QImage)  # (game_id, scaled_qimage)

    def __init__(self, parent=None, max_w: int = 480, max_h: int = 240):
        super().__init__(parent)
        self.max_w = max_w
        self.max_h = max_h
        self._queue = deque()
        self._queued_ids = set()
        self._lock = threading.Lock()
        self._running = True
        self._event = threading.Event()

    def stop(self):
        self._running = False
        self._event.set()
        self.wait(500)

    def clear(self):
        with self._lock:
            self._queue.clear()
            self._queued_ids.clear()

    def queue_game(self, game: dict, priority: bool = False):
        gid = game.get("id")
        if not gid:
            return
        with self._lock:
            if gid not in self._queued_ids:
                if priority:
                    self._queue.appendleft(game)
                else:
                    self._queue.append(game)
                self._queued_ids.add(gid)
        self._event.set()

    def queue_games(self, games_list: list[dict], priority: bool = False):
        with self._lock:
            items = reversed(games_list) if priority else games_list
            for g in items:
                gid = g.get("id")
                if gid and gid not in self._queued_ids:
                    if priority:
                        self._queue.appendleft(g)
                    else:
                        self._queue.append(g)
                    self._queued_ids.add(gid)
        self._event.set()

    def run(self):
        img_exts = (".png", ".webp", ".jpg", ".jpeg")
        while self._running:
            game = None
            with self._lock:
                if self._queue:
                    game = self._queue.popleft()
                else:
                    self._event.clear()

            if not game:
                self._event.wait(timeout=0.05)
                continue

            gid = game.get("id")
            try:
                w_file = None
                wheel_folder = game.get("wheel_path")
                rom = game.get("rom_path", "")
                stem = Path(rom).stem if rom else ""
                if wheel_folder and stem:
                    w_file = find_media_file(wheel_folder, stem, img_exts)
                if not w_file:
                    fb = resolve_game_media(game)
                    w_file = fb.get("wheel") or fb.get("logo")
                if w_file and os.path.isfile(w_file):
                    img = QImage(w_file)
                    if not img.isNull():
                        if img.width() > self.max_w or img.height() > self.max_h:
                            img = img.scaled(self.max_w, self.max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.wheel_loaded.emit(gid, img)
            except Exception:
                pass


class CoverPreloadWorker(QThread):
    """Hilo en segundo plano para cargar/pre-escalar portadas y leer metadatos sin bloquear `paint()`."""

    cover_loaded = Signal(int, int, int, QImage)  # (game_id, target_w, target_h, scaled_qimage)
    rom_size_loaded = Signal(int, str)            # (game_id, size_str)

    def __init__(
        self,
        parent=None,
        aspect_mode: Qt.AspectRatioMode = Qt.KeepAspectRatioByExpanding,
        collect_rom_size: bool = False,
    ):
        super().__init__(parent)
        self._aspect_mode = aspect_mode
        self._collect_rom_size = bool(collect_rom_size)
        self._queue: deque[tuple[dict, int, int]] = deque()
        self._queued_keys: set[tuple[int, int, int]] = set()
        self._lock = threading.Lock()
        self._running = True
        self._event = threading.Event()

    def stop(self):
        self._running = False
        self._event.set()
        self.wait(500)

    def clear(self):
        with self._lock:
            self._queue.clear()
            self._queued_keys.clear()

    def queue_game(self, game: dict, target_w: int, target_h: int, priority: bool = False):
        gid = game.get("id")
        tw = max(1, int(target_w))
        th = max(1, int(target_h))
        if not gid:
            return
        key = (int(gid), tw, th)
        with self._lock:
            if key not in self._queued_keys:
                item = (game, tw, th)
                if priority:
                    self._queue.appendleft(item)
                else:
                    self._queue.append(item)
                self._queued_keys.add(key)
        self._event.set()

    def queue_games(self, games_list: list[dict], target_w: int, target_h: int, priority: bool = False):
        tw = max(1, int(target_w))
        th = max(1, int(target_h))
        with self._lock:
            items = reversed(games_list) if priority else games_list
            for g in items:
                gid = g.get("id")
                if not gid:
                    continue
                key = (int(gid), tw, th)
                if key not in self._queued_keys:
                    entry = (g, tw, th)
                    if priority:
                        self._queue.appendleft(entry)
                    else:
                        self._queue.append(entry)
                    self._queued_keys.add(key)
        self._event.set()

    def run(self):
        while self._running:
            entry = None
            with self._lock:
                if self._queue:
                    entry = self._queue.popleft()
                else:
                    self._event.clear()

            if not entry:
                self._event.wait(timeout=0.05)
                continue

            game, tw, th = entry
            gid = game.get("id")
            if not gid:
                continue

            try:
                if self._collect_rom_size:
                    rom_path = game.get("rom_path", "")
                    size_str = "?"
                    if rom_path and os.path.isfile(rom_path):
                        try:
                            mb = os.path.getsize(rom_path) / (1024 * 1024)
                            size_str = f"{mb:.1f} MB"
                        except OSError:
                            size_str = "?"
                    self.rom_size_loaded.emit(int(gid), size_str)

                cover_file = game.get("cover_path")
                if not (cover_file and os.path.isfile(str(cover_file))):
                    fb = resolve_game_media(game)
                    cover_file = fb.get("boxart") or fb.get("cover") or fb.get("flyer")

                if cover_file and os.path.isfile(str(cover_file)):
                    img = QImage(str(cover_file))
                    if not img.isNull():
                        scaled = _scale_qimage_cover(img, tw, th, self._aspect_mode)
                        if not scaled.isNull():
                            self.cover_loaded.emit(int(gid), tw, th, scaled)
                            continue
                self.cover_loaded.emit(int(gid), tw, th, QImage())
            except Exception:
                pass
