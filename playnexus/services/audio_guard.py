"""
Guardián de dispositivos de audio para PlayNexus (QtMultimedia / WASAPI).

En salidas HDMI (como televisores LG / NVIDIA HD Audio), al cambiar de resolución o
entrar/salir de un emulador a pantalla completa, Windows puede invalidar temporalmente
el endpoint de audio (`AUDCLNT_E_DEVICE_INVALIDATED`) y provocar errores en cascada de
`QAudioOutput` / `QSoundEffect` (`QRtAudioEngine`).

Este módulo escucha `QMediaDevices.audioOutputsChanged`, monitorea mensajes de
invalidación de audio y reasigna automáticamente los `QAudioOutput` y `QSoundEffect`
activos cuando el dispositivo predeterminado vuelve a estar disponible y con formato válido.
"""
from __future__ import annotations

import sys
import time
from weakref import WeakSet
from typing import Any

from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, QTimer, QUrl, Qt, Slot, qInstallMessageHandler
from PySide6.QtMultimedia import QAudioDevice, QAudioOutput, QMediaDevices, QSoundEffect
from PySide6.QtWidgets import QApplication


def is_valid_audio_device(dev: QAudioDevice | None) -> bool:
    """Retorna True si el dispositivo de audio existe y declara al menos un formato válido."""
    if dev is None:
        return False
    try:
        if dev.isNull():
            return False
        fmt = dev.preferredFormat()
        if not fmt.isValid():
            return False
        return bool(dev.supportedSampleFormats())
    except Exception:
        return False


class _AudioDeviceGuardian(QObject):
    """Supervisor singleton que mantiene sanos los `QAudioOutput` y `QSoundEffect` tras resets HDMI/WASAPI."""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._tracked_roots: WeakSet[QObject] = WeakSet()
        self._media_devices: QMediaDevices | None = None
        self._shutting_down: bool = False
        self._refreshing: bool = False
        self._pending_force_rebind: bool = False
        self._retry_count: int = 0
        self._last_error_trigger_ts: float = 0.0
        self._handler_installed: bool = False
        self._prev_msg_handler: Any = None

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._perform_refresh)

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._perform_refresh)

    def ensure_initialized(self, track_obj: QObject | None = None) -> None:
        if track_obj is not None:
            try:
                self._tracked_roots.add(track_obj)
            except TypeError:
                pass

        app = QCoreApplication.instance()
        if app is None or self._shutting_down:
            return

        if self._media_devices is None:
            try:
                self._media_devices = QMediaDevices(self)
                self._media_devices.audioOutputsChanged.connect(self._on_audio_outputs_changed)
                app.aboutToQuit.connect(self._on_about_to_quit)
            except Exception:
                self._media_devices = None

        if not self._handler_installed:
            self._install_msg_hook()

    def _install_msg_hook(self) -> None:
        def _qt_audio_msg_handler(msg_type, context, message):
            text = str(message or "")
            if (
                not self._shutting_down
                and not self._refreshing
                and ("AUDCLNT_E_DEVICE_INVALIDATED" in text or "QRtAudioEngine" in text)
            ):
                now = time.monotonic()
                if now - self._last_error_trigger_ts >= 0.6:
                    self._last_error_trigger_ts = now
                    try:
                        QMetaObject.invokeMethod(
                            self,
                            "_schedule_from_any_thread",
                            Qt.QueuedConnection,
                        )
                    except Exception:
                        pass

            prev = self._prev_msg_handler
            if callable(prev):
                try:
                    prev(msg_type, context, message)
                    return
                except Exception:
                    pass
            try:
                if sys.stderr is not None:
                    sys.stderr.write(text + "\n")
            except Exception:
                pass

        try:
            self._prev_msg_handler = qInstallMessageHandler(_qt_audio_msg_handler)
            self._handler_installed = True
        except Exception:
            self._handler_installed = False

    @Slot()
    def _on_about_to_quit(self) -> None:
        self._shutting_down = True
        try:
            self._debounce_timer.stop()
            self._retry_timer.stop()
        except Exception:
            pass
        if self._handler_installed:
            try:
                qInstallMessageHandler(self._prev_msg_handler)
            except Exception:
                pass
            self._handler_installed = False

    @Slot()
    def _schedule_from_any_thread(self) -> None:
        self.schedule_recovery(delay_ms=250, force_rebind=True)

    @Slot()
    def _on_audio_outputs_changed(self) -> None:
        self.schedule_recovery(delay_ms=220, force_rebind=True)

    def schedule_recovery(self, delay_ms: int = 220, force_rebind: bool = True) -> None:
        if self._shutting_down or QCoreApplication.instance() is None:
            return
        if force_rebind:
            self._pending_force_rebind = True
        self._retry_count = 0
        self._retry_timer.stop()
        self._debounce_timer.start(max(40, int(delay_ms)))

    def refresh_now(self, force_rebind: bool = False) -> int:
        if force_rebind:
            self._pending_force_rebind = True
        self._debounce_timer.stop()
        self._retry_timer.stop()
        return self._perform_refresh()

    def _collect_audio_objects(self) -> tuple[list[QAudioOutput], list[QSoundEffect]]:
        roots: list[QObject] = []
        app = QCoreApplication.instance()
        if isinstance(app, QApplication):
            try:
                roots.extend(w for w in app.topLevelWidgets() if w is not None)
            except Exception:
                pass
        for obj in list(self._tracked_roots):
            try:
                if obj is not None:
                    roots.append(obj)
            except RuntimeError:
                pass

        audio_outputs: dict[int, QAudioOutput] = {}
        sound_effects: dict[int, QSoundEffect] = {}

        for root in roots:
            try:
                if isinstance(root, QAudioOutput):
                    audio_outputs[id(root)] = root
                elif isinstance(root, QSoundEffect):
                    sound_effects[id(root)] = root
                for ao in root.findChildren(QAudioOutput):
                    audio_outputs[id(ao)] = ao
                for sfx in root.findChildren(QSoundEffect):
                    sound_effects[id(sfx)] = sfx
            except RuntimeError:
                continue
            except Exception:
                continue

        return list(audio_outputs.values()), list(sound_effects.values())

    @Slot()
    def _perform_refresh(self) -> int:
        if self._shutting_down or self._refreshing or QCoreApplication.instance() is None:
            return 0

        default_dev = QMediaDevices.defaultAudioOutput()
        if not is_valid_audio_device(default_dev):
            if self._retry_count < 6:
                self._retry_count += 1
                self._retry_timer.start(450)
            return 0

        self._retry_count = 0
        force_rebind = self._pending_force_rebind
        self._pending_force_rebind = False

        rebound = 0
        self._refreshing = True
        try:
            default_id = default_dev.id()
            audio_outputs, sound_effects = self._collect_audio_objects()

            for ao in audio_outputs:
                try:
                    cur_dev = ao.device()
                    same_id = (not cur_dev.isNull()) and (cur_dev.id() == default_id)
                    if not force_rebind and same_id:
                        continue
                    vol = ao.volume()
                    muted = ao.isMuted()
                    if force_rebind and same_id:
                        ao.setDevice(QAudioDevice())
                    ao.setDevice(default_dev)
                    ao.setVolume(vol)
                    ao.setMuted(muted)
                    rebound += 1
                except RuntimeError:
                    continue
                except Exception:
                    continue

            for sfx in sound_effects:
                try:
                    cur_dev = sfx.audioDevice()
                    was_err = sfx.status() == QSoundEffect.Error
                    same_id = (not cur_dev.isNull()) and (cur_dev.id() == default_id)
                    if not force_rebind and not was_err and same_id:
                        continue
                    src = sfx.source()
                    vol = sfx.volume()
                    muted = sfx.isMuted()
                    if sfx.isPlaying():
                        sfx.stop()
                    if (force_rebind or was_err) and same_id:
                        sfx.setAudioDevice(QAudioDevice())
                    sfx.setAudioDevice(default_dev)
                    if was_err and not src.isEmpty():
                        sfx.setSource(QUrl())
                        sfx.setSource(src)
                    sfx.setVolume(vol)
                    sfx.setMuted(muted)
                    rebound += 1
                except RuntimeError:
                    continue
                except Exception:
                    continue
        finally:
            self._refreshing = False

        return rebound


_GUARDIAN_SINGLETON: _AudioDeviceGuardian | None = None


def get_audio_device_guardian() -> _AudioDeviceGuardian | None:
    global _GUARDIAN_SINGLETON
    app = QCoreApplication.instance()
    if app is None:
        return None
    if _GUARDIAN_SINGLETON is None:
        _GUARDIAN_SINGLETON = _AudioDeviceGuardian(app)
    return _GUARDIAN_SINGLETON


def ensure_audio_guard_installed(track_obj: QObject | None = None) -> _AudioDeviceGuardian | None:
    """Instala el guardián global de audio si hay una aplicación Qt activa y registra `track_obj`."""
    guard = get_audio_device_guardian()
    if guard is not None:
        guard.ensure_initialized(track_obj)
    return guard


def refresh_audio_devices(force_rebind: bool = False) -> int:
    """Reasigna de inmediato los `QAudioOutput` y `QSoundEffect` al dispositivo válido actual."""
    guard = ensure_audio_guard_installed()
    if guard is None:
        return 0
    return guard.refresh_now(force_rebind=force_rebind)


def schedule_audio_recovery(delay_ms: int = 220, force_rebind: bool = True) -> None:
    """Programa una recuperación tras cambio HDMI / salida de emulador / dispositivo invalidado."""
    guard = ensure_audio_guard_installed()
    if guard is not None:
        guard.schedule_recovery(delay_ms=delay_ms, force_rebind=force_rebind)
