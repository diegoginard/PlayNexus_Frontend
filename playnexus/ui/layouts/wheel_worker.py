import os
import threading
from collections import deque
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage
from playnexus.services.media import find_media_file, resolve_game_media


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
