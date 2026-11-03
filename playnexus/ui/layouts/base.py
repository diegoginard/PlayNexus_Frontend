from pathlib import Path
from PySide6.QtCore import Signal, QPoint, Qt
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QMediaPlayer
from playnexus.services.controls import (
    matches_action, ACTION_NAV_UP, ACTION_NAV_DOWN, ACTION_SELECT,
    ACTION_NAV_LETTER, ACTION_NAV_STEP5,
    ACTION_NAV_LETTER_FWD, ACTION_NAV_LETTER_BACK,
    ACTION_NAV_STEP5_FWD, ACTION_NAV_STEP5_BACK,
    ACTION_PAGE_UP, ACTION_PAGE_DOWN
)
from playnexus.ui.layouts.wheel_worker import WheelPreloadWorker

class BaseLayout(QWidget):
    """
    Clase base abstracta para todos los layouts personalizados de PlayNexus.
    Cualquier layout personalizado debe heredar de esta clase e implementar sus métodos.
    """
    # Señales para comunicar eventos a MainWindow / PlayerWindow
    game_selected = Signal(int)           # Emite game_id cuando se selecciona un juego
    game_activated = Signal(int)          # Emite game_id al hacer doble clic o Enter (ejecutar)
    context_menu_requested = Signal(int, QPoint)  # Emite (game_id, posición_global)
    nav_back_requested = Signal()         # Emite al solicitar volver atrás (Escape, Retroceso o botón B)

    # Identificadores del layout
    LAYOUT_NAME = "Base"
    LAYOUT_DESCRIPTION = "Layout base"

    def __init__(self, parent=None, theme_name: str | None = None, **kwargs):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.theme_name = theme_name
        self.games = []
        self.current_game_id = None

    def set_games(self, games: list):
        """Recibe la lista de juegos a mostrar (diccionarios de juegos)."""
        self.games = [dict(g) if hasattr(g, "keys") else g for g in games]
        self.render_games()

    def render_games(self):
        """Renderiza los juegos en la interfaz del layout. Debe ser implementado por subclases."""
        raise NotImplementedError

    def select_game_by_id(self, game_id: int):
        """Selecciona visualmente el juego con el ID indicado."""
        self.current_game_id = game_id

    def _can_activate_game(self) -> bool:
        """Evita ráfagas o dobles ejecuciones consecutivas por doble clic, joystick o teclado.
        La ventana de bloqueo se basa en el intervalo de doble clic del sistema (mín. 0.6 s)
        para descartar el segundo clic sin bloquear activaciones legítimas posteriores
        (ej: entrar a un sistema y elegir un juego enseguida)."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            return False
        import time
        from PySide6.QtWidgets import QApplication
        try:
            window = max(0.6, QApplication.doubleClickInterval() / 1000.0 + 0.2)
        except Exception:
            window = 0.7
        now = time.perf_counter()
        last = getattr(self, "_last_activate_time", 0.0)
        if last and (now - last < window):
            return False
        self._last_activate_time = now
        return True

    def mousePressEvent(self, event):
        """Descarta clics si un emulador está iniciándose o en ejecución."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        self.setFocus()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        event.accept()

    def wheelEvent(self, event):
        """Permite navegar fluidamente por la lista utilizando la rueda del ratón."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self.navigate_steps(-1)
            event.accept()
        elif delta < 0:
            self.navigate_steps(1)
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Descarta el doble clic izquierdo: el primer clic (mousePressEvent) ya activó el juego.
        Por defecto QWidget reenvía el doble clic a mousePressEvent, lo que provocaba
        una segunda activación del juego o del sistema seleccionado."""
        from PySide6.QtCore import Qt
        if event.button() == Qt.LeftButton:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def get_selected_game_id(self) -> int | None:
        """Retorna el ID del juego actualmente seleccionado."""
        return self.current_game_id

    def clear(self):
        """Limpia los elementos del layout."""
        self.games = []
        self.current_game_id = None

    def stop_media(self):
        """Detiene cualquier reproducción multimedia (video, música, efectos) activa en el layout."""
        if hasattr(self, "_want_game_video_playing"):
            self._want_game_video_playing = False
        if hasattr(self, "_want_video_playing"):
            self._want_video_playing = False
        if hasattr(self, "_pending_video_path"):
            self._pending_video_path = None
        for timer_name in ("_video_debounce_timer", "_video_watchdog_timer", "video_timer"):
            if hasattr(self, timer_name):
                try:
                    getattr(self, timer_name).stop()
                except Exception:
                    pass
        for audio_name in ("audio_output", "game_audio", "_audio_output"):
            if hasattr(self, audio_name):
                ao = getattr(self, audio_name)
                if ao:
                    try:
                        ao.setMuted(True)
                        ao.setVolume(0.0)
                    except Exception:
                        pass
        for player_name in ("player", "game_player", "_player"):
            if hasattr(self, player_name):
                p = getattr(self, player_name)
                if p:
                    try:
                        p.stop()
                        from PySide6.QtCore import QUrl
                        p.setSource(QUrl())
                    except Exception:
                        pass
        if hasattr(self, "_current_video_image"):
            self._current_video_image = None
        if hasattr(self, "_game_video_image"):
            self._game_video_image = None
        try:
            self.update()
        except Exception:
            pass

    def pause_media(self):
        """Pausa la reproducción multimedia y silencia el audio mientras el emulador está activo."""
        self._is_emulator_running = True
        if hasattr(self, "_want_game_video_playing"):
            self._want_game_video_playing = False
        if hasattr(self, "_want_video_playing"):
            self._want_video_playing = False
        for timer_name in ("_video_debounce_timer", "_video_watchdog_timer", "video_timer"):
            if hasattr(self, timer_name):
                try:
                    getattr(self, timer_name).stop()
                except Exception:
                    pass
        for audio_name in ("audio_output", "game_audio", "_audio_output"):
            if hasattr(self, audio_name):
                ao = getattr(self, audio_name)
                if ao:
                    try:
                        ao.setMuted(True)
                        ao.setVolume(0.0)
                    except Exception:
                        pass
        for player_name in ("player", "game_player", "bg_player", "_player"):
            if hasattr(self, player_name):
                p = getattr(self, player_name)
                if p:
                    try:
                        p.pause()
                    except Exception:
                        pass
        try:
            self.update()
        except Exception:
            pass

    def showEvent(self, event):
        """Asegura que el video snap o tema comience al hacerse visible este layout."""
        super().showEvent(event)
        if getattr(self, "_pending_video_play_on_show", False):
            self._pending_video_play_on_show = False
            if hasattr(self, "_play_debounced_video") and callable(self._play_debounced_video):
                self._play_debounced_video()
                return
            elif hasattr(self, "_update_current_selection") and callable(self._update_current_selection):
                self._update_current_selection()
                return
        for player_name in ("player", "game_player", "bg_player", "_player"):
            if hasattr(self, player_name):
                p = getattr(self, player_name)
                if p and (p.source().isEmpty() or p.playbackState() != QMediaPlayer.PlayingState):
                    if hasattr(self, "_play_debounced_video") and callable(self._play_debounced_video):
                        self._play_debounced_video()
                        break
                    elif hasattr(self, "_update_current_selection") and callable(self._update_current_selection):
                        self._update_current_selection()
                        break

    def resume_media(self):
        """Reanuda la reproducción multimedia y el audio cuando el emulador finaliza."""
        self._is_emulator_running = False
        if hasattr(self, "_want_game_video_playing"):
            self._want_game_video_playing = True
        if hasattr(self, "_want_video_playing"):
            self._want_video_playing = True
        for audio_name in ("audio_output", "game_audio", "_audio_output"):
            if hasattr(self, audio_name):
                ao = getattr(self, audio_name)
                if ao:
                    try:
                        is_muted = getattr(self, "_media_muted", False)
                        ao.setMuted(is_muted)
                        ao.setVolume(0.0 if is_muted else 0.8)
                    except Exception:
                        pass
        for player_name in ("player", "game_player", "bg_player", "_player"):
            if hasattr(self, player_name):
                p = getattr(self, player_name)
                if p:
                    try:
                        from PySide6.QtMultimedia import QMediaPlayer
                        if p.source().isEmpty() or p.playbackState() != QMediaPlayer.PlayingState:
                            if hasattr(self, "_play_debounced_video") and callable(self._play_debounced_video):
                                self._play_debounced_video()
                                break
                            elif hasattr(self, "_update_current_selection") and callable(self._update_current_selection):
                                self._update_current_selection()
                                break
                            else:
                                p.play()
                        else:
                            p.play()
                    except Exception:
                        pass
        for timer_name in ("_video_watchdog_timer",):
            if hasattr(self, timer_name):
                try:
                    getattr(self, timer_name).start()
                except Exception:
                    pass
        try:
            self.update()
        except Exception:
            pass

    def set_media_muted(self, muted: bool):
        """Silencia o restaura todo el audio del layout (video snaps, efectos de navegación y selección)."""
        self._media_muted = muted
        for audio_name in ("audio_output", "game_audio", "_audio_output"):
            if hasattr(self, audio_name):
                ao = getattr(self, audio_name)
                if ao:
                    try:
                        ao.setMuted(muted)
                        ao.setVolume(0.0 if muted else 0.8)
                    except Exception:
                        pass
        for effect_name in ("_sound_effect", "_select_sound_effect", "_wheel_sound_effect"):
            if hasattr(self, effect_name):
                se = getattr(self, effect_name)
                if se:
                    try:
                        se.setMuted(muted)
                        se.setVolume(0.0 if muted else 0.5)
                    except Exception:
                        pass
        if hasattr(self, "mute_btn") and self.mute_btn:
            try:
                self.mute_btn.setChecked(muted)
                self.mute_btn.setText("🔇 Silenciado" if muted else "🔊 Silenciar video")
            except Exception:
                pass

    def is_muted(self) -> bool:
        return getattr(self, "_media_muted", False)

    def jump_to_next_letter(self):
        """
        Salta al primer juego de la siguiente letra en orden alfabético.
        Ej: si el juego actual empieza con 'A', salta al primer juego que empieza con 'B'.
        """
        if not self.games or len(self.games) <= 1:
            return

        def _get_initial(title: str) -> str:
            clean = (title or "").strip().upper()
            for ch in clean:
                if ch.isalnum():
                    return ch if ch.isalpha() else "#"
            return "#"

        n = len(self.games)
        curr_idx = None
        if hasattr(self, "selected_index") and isinstance(self.selected_index, int) and 0 <= self.selected_index < n:
            curr_idx = self.selected_index
        elif self.current_game_id is not None:
            for idx, g in enumerate(self.games):
                if g.get("id") == self.current_game_id:
                    curr_idx = idx
                    break
        elif hasattr(self, "wheel_list") and hasattr(self.wheel_list, "currentRow"):
            row = self.wheel_list.currentRow()
            if 0 <= row < n:
                curr_idx = row
        elif hasattr(self, "table") and hasattr(self.table, "currentRow"):
            row = self.table.currentRow()
            if 0 <= row < n:
                curr_idx = row

        if curr_idx is None:
            curr_idx = 0

        curr_title = self.games[curr_idx].get("title") or self.games[curr_idx].get("rom_name") or ""
        curr_initial = _get_initial(curr_title)

        found_idx = None
        for i in range(1, n):
            target = (curr_idx + i) % n
            title = self.games[target].get("title") or self.games[target].get("rom_name") or ""
            init = _get_initial(title)
            if init != curr_initial:
                found_idx = target
                break

        if found_idx is not None:
            if hasattr(self, "_target_pos") and hasattr(self, "_current_pos"):
                self.selected_index = found_idx
                self._current_pos = float(found_idx - 1)
                self._target_pos = float(found_idx)
                if hasattr(self, "_anim_timer") and not self._anim_timer.isActive():
                    import time
                    self._last_anim_time = time.perf_counter()
                    self._anim_timer.start(16)
                if hasattr(self, "_update_selected_media"):
                    self._update_selected_media(fast_repeat=False)
                elif hasattr(self, "_update_current_selection"):
                    self._update_current_selection()
                if hasattr(self, "_play_nav_sound"):
                    self._play_nav_sound()
                elif hasattr(self, "_play_wheel_sound"):
                    self._play_wheel_sound()
                gid = self.get_selected_game_id()
                if gid:
                    self.game_selected.emit(gid)
                self.update()
            elif hasattr(self, "_wheel_spin_offset"):
                self.selected_index = found_idx
                self._wheel_spin_offset = 2.0
                if hasattr(self, "_wheel_spin_timer") and not self._wheel_spin_timer.isActive():
                    self._wheel_spin_timer.start(16)
                if hasattr(self, "_update_current_selection"):
                    self._update_current_selection()
                if hasattr(self, "_play_wheel_sound"):
                    self._play_wheel_sound()
                gid = self.get_selected_game_id()
                if gid:
                    self.game_selected.emit(gid)
                self.update()
            elif hasattr(self, "_navigate_steps"):
                steps = (found_idx - curr_idx) % n
                self._navigate_steps(steps)
            elif hasattr(self, "wheel_list") and hasattr(self.wheel_list, "setCurrentRow"):
                self.wheel_list.setCurrentRow(found_idx)
            elif hasattr(self, "table") and hasattr(self.table, "selectRow"):
                self.table.selectRow(found_idx)
            else:
                self.selected_index = found_idx
                target_gid = self.games[found_idx].get("id")
                if target_gid is not None:
                    self.select_game_by_id(target_gid)
                    self.game_selected.emit(target_gid)

    def jump_to_prev_letter(self):
        """
        Salta al primer juego de la letra anterior en orden alfabético.
        Ej: si el juego actual empieza con 'B', salta al primer juego que empieza con 'A'.
        """
        if not self.games or len(self.games) <= 1:
            return

        def _get_initial(title: str) -> str:
            clean = (title or "").strip().upper()
            for ch in clean:
                if ch.isalnum():
                    return ch if ch.isalpha() else "#"
            return "#"

        n = len(self.games)
        curr_idx = None
        if hasattr(self, "selected_index") and isinstance(self.selected_index, int) and 0 <= self.selected_index < n:
            curr_idx = self.selected_index
        elif self.current_game_id is not None:
            for idx, g in enumerate(self.games):
                if g.get("id") == self.current_game_id:
                    curr_idx = idx
                    break
        elif hasattr(self, "wheel_list") and hasattr(self.wheel_list, "currentRow"):
            row = self.wheel_list.currentRow()
            if 0 <= row < n:
                curr_idx = row
        elif hasattr(self, "table") and hasattr(self.table, "currentRow"):
            row = self.table.currentRow()
            if 0 <= row < n:
                curr_idx = row

        if curr_idx is None:
            curr_idx = 0

        curr_title = self.games[curr_idx].get("title") or self.games[curr_idx].get("rom_name") or ""
        curr_initial = _get_initial(curr_title)

        # 1. Buscar hacia atrás el primer juego con letra diferente a curr_initial
        prev_initial = None
        first_diff_idx = None
        for i in range(1, n):
            target = (curr_idx - i) % n
            title = self.games[target].get("title") or self.games[target].get("rom_name") or ""
            init = _get_initial(title)
            if init != curr_initial:
                prev_initial = init
                first_diff_idx = target
                break

        if prev_initial is None or first_diff_idx is None:
            return

        # 2. Encontrar el inicio de ese grupo de letras (el primer juego con prev_initial)
        found_idx = first_diff_idx
        for i in range(1, n):
            target = (first_diff_idx - i) % n
            title = self.games[target].get("title") or self.games[target].get("rom_name") or ""
            init = _get_initial(title)
            if init != prev_initial:
                found_idx = (target + 1) % n
                break
        else:
            found_idx = 0

        if found_idx is not None:
            if hasattr(self, "_target_pos") and hasattr(self, "_current_pos"):
                self.selected_index = found_idx
                self._current_pos = float(found_idx + 1)
                self._target_pos = float(found_idx)
                if hasattr(self, "_anim_timer") and not self._anim_timer.isActive():
                    import time
                    self._last_anim_time = time.perf_counter()
                    self._anim_timer.start(16)
                if hasattr(self, "_update_selected_media"):
                    self._update_selected_media(fast_repeat=False)
                elif hasattr(self, "_update_current_selection"):
                    self._update_current_selection()
                if hasattr(self, "_play_nav_sound"):
                    self._play_nav_sound()
                elif hasattr(self, "_play_wheel_sound"):
                    self._play_wheel_sound()
                gid = self.get_selected_game_id()
                if gid:
                    self.game_selected.emit(gid)
                self.update()
            elif hasattr(self, "_wheel_spin_offset"):
                self.selected_index = found_idx
                self._wheel_spin_offset = -2.0
                if hasattr(self, "_wheel_spin_timer") and not self._wheel_spin_timer.isActive():
                    self._wheel_spin_timer.start(16)
                if hasattr(self, "_update_current_selection"):
                    self._update_current_selection()
                if hasattr(self, "_play_wheel_sound"):
                    self._play_wheel_sound()
                gid = self.get_selected_game_id()
                if gid:
                    self.game_selected.emit(gid)
                self.update()
            elif hasattr(self, "_navigate_steps"):
                steps = -((curr_idx - found_idx) % n)
                self._navigate_steps(steps)
            elif hasattr(self, "wheel_list") and hasattr(self.wheel_list, "setCurrentRow"):
                self.wheel_list.setCurrentRow(found_idx)
            elif hasattr(self, "table") and hasattr(self.table, "selectRow"):
                self.table.selectRow(found_idx)
            else:
                self.selected_index = found_idx
                target_gid = self.games[found_idx].get("id")
                if target_gid is not None:
                    self.select_game_by_id(target_gid)
                    self.game_selected.emit(target_gid)

    def navigate_steps(self, steps: int):
        """Avanza o retrocede 'steps' elementos en la lista de juegos (ej: saltar de a 5)."""
        if not self.games:
            return

        if hasattr(self, "_navigate_steps"):
            self._navigate_steps(steps)
        elif hasattr(self, "wheel_list") and hasattr(self.wheel_list, "currentRow"):
            cur = self.wheel_list.currentRow()
            total = self.wheel_list.count()
            if total > 0:
                new_row = max(0, min(total - 1, cur + steps))
                self.wheel_list.setCurrentRow(new_row)
        elif hasattr(self, "table") and hasattr(self.table, "currentRow"):
            cur = self.table.currentRow()
            total = self.table.rowCount()
            if total > 0:
                new_row = max(0, min(total - 1, cur + steps))
                self.table.selectRow(new_row)
        else:
            n = len(self.games)
            curr_idx = 0
            if hasattr(self, "selected_index") and isinstance(self.selected_index, int) and 0 <= self.selected_index < n:
                curr_idx = self.selected_index
            elif self.current_game_id is not None:
                for idx, g in enumerate(self.games):
                    if g.get("id") == self.current_game_id:
                        curr_idx = idx
                        break
            new_idx = max(0, min(n - 1, curr_idx + steps))
            self.selected_index = new_idx
            target_gid = self.games[new_idx].get("id")
            if target_gid is not None:
                self.select_game_by_id(target_gid)
                self.game_selected.emit(target_gid)

    def keyPressEvent(self, event):
        """Manejo genérico de atajos de navegación, salto de letra y saltos de a 5."""
        from playnexus.services.emulator_manager import EMULATOR_MANAGER
        if EMULATOR_MANAGER.is_launching_or_running():
            event.accept()
            return
        if matches_action(event, ACTION_NAV_UP, getattr(self, "db", None)):
            self.navigate_steps(-1)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_DOWN, getattr(self, "db", None)):
            self.navigate_steps(1)
            event.accept()
            return
        elif matches_action(event, ACTION_SELECT, getattr(self, "db", None)):
            if event.isAutoRepeat():
                event.accept()
                return
            gid = self.get_selected_game_id()
            if gid and self._can_activate_game():
                self.game_activated.emit(gid)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_LETTER_BACK, getattr(self, "db", None)):
            self.jump_to_prev_letter()
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_LETTER_FWD, getattr(self, "db", None)) or matches_action(event, ACTION_NAV_LETTER, getattr(self, "db", None)):
            self.jump_to_next_letter()
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_STEP5_BACK, getattr(self, "db", None)) or matches_action(event, ACTION_PAGE_UP, getattr(self, "db", None)):
            self.navigate_steps(-5)
            event.accept()
            return
        elif matches_action(event, ACTION_NAV_STEP5_FWD, getattr(self, "db", None)) or matches_action(event, ACTION_NAV_STEP5, getattr(self, "db", None)) or matches_action(event, ACTION_PAGE_DOWN, getattr(self, "db", None)):
            self.navigate_steps(5)
            event.accept()
            return
        super().keyPressEvent(event)
