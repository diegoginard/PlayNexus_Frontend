"""Sistema liviano de partículas ambientales pre-asignadas y overlay de efectos retro."""

from __future__ import annotations

import math
import random
import time
from typing import Any

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from playnexus.ui.shaders import (
    normalize_effects_perf,
    normalize_shader_preset,
    normalize_shader_target,
    render_shader_overlay_painter,
)

# ---------------------------------------------------------------------------
# Presets declarativos de partículas
# ---------------------------------------------------------------------------

PARTICLE_PRESETS: list[tuple[str, str]] = [
    ("none", "Sin partículas"),
    ("arcade_sparks", "Chispas Arcade (Ascenso luminoso)"),
    ("neon_dust", "Polvo Neón (Flotación ambiental)"),
    ("snow_drift", "Nieve / Destellos (Caída suave)"),
    ("starfield_parallax", "Campo Estelar Parallax"),
]

VALID_PARTICLE_PRESETS: set[str] = {key for key, _ in PARTICLE_PRESETS}
PARTICLE_LABELS: dict[str, str] = dict(PARTICLE_PRESETS)

MAX_POOL_SIZE: int = 64

_PRESET_PALETTES: dict[str, tuple[QColor, ...]] = {
    "arcade_sparks": (
        QColor(255, 200, 72),
        QColor(255, 118, 48),
        QColor(72, 224, 255),
    ),
    "neon_dust": (
        QColor(56, 189, 248),
        QColor(168, 85, 247),
        QColor(34, 211, 238),
    ),
    "snow_drift": (
        QColor(241, 245, 249),
        QColor(203, 213, 225),
        QColor(186, 230, 253),
    ),
    "starfield_parallax": (
        QColor(248, 250, 252),
        QColor(191, 219, 254),
        QColor(253, 230, 138),
    ),
}

_SPRITE_CACHE: dict[tuple[int, int, int, int], QPixmap] = {}


def normalize_particle_preset(value: Any, *, allow_layout: bool = False) -> str:
    """Normaliza identificadores o etiquetas de partículas ambientales."""
    raw = str(value or "").strip().lower()
    if allow_layout and raw in ("layout", "auto", "default", "del layout"):
        return "layout"
    if not raw or raw in ("none", "off", "disabled", "ninguno", "sin particulas", "sin partículas"):
        return "none"
    if raw in VALID_PARTICLE_PRESETS:
        return raw
    for key, label in PARTICLE_PRESETS:
        if raw == label.strip().lower():
            return key
    return "none"


def _get_glow_sprite(color: QColor, diameter: int) -> QPixmap:
    d = max(4, min(28, int(diameter)))
    key = (color.red(), color.green(), color.blue(), d)
    cached = _SPRITE_CACHE.get(key)
    if cached is not None:
        return cached

    pm = QPixmap(d, d)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    center = QPointF(d * 0.5, d * 0.5)
    grad = QRadialGradient(center, d * 0.5)
    c_core = QColor(255, 255, 255, 235)
    c_mid = QColor(color.red(), color.green(), color.blue(), 170)
    c_edge = QColor(color.red(), color.green(), color.blue(), 0)
    grad.setColorAt(0.0, c_core)
    grad.setColorAt(0.32, c_mid)
    grad.setColorAt(1.0, c_edge)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawEllipse(QRectF(0, 0, d, d))
    p.end()

    if len(_SPRITE_CACHE) > 96:
        _SPRITE_CACHE.clear()
    _SPRITE_CACHE[key] = pm
    return pm


class ParticleSystem:
    """Emisor de partículas pre-asignadas con presupuesto estricto de CPU/FPS.

    Mantiene arreglos de tamaño fijo (`MAX_POOL_SIZE = 64`) para garantizar cero
    asignaciones dinámicas dentro del bucle `paintEvent` / `step`.
    """

    def __init__(self, preset: str = "none", perf_profile: str = "high", seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._preset: str = normalize_particle_preset(preset)
        self._perf: str = normalize_effects_perf(perf_profile)
        self._time: float = 0.0

        # Buffers pre-asignados en espacio normalizado [0.0 .. 1.0]
        self._x: list[float] = [0.0] * MAX_POOL_SIZE
        self._y: list[float] = [0.0] * MAX_POOL_SIZE
        self._vx: list[float] = [0.0] * MAX_POOL_SIZE
        self._vy: list[float] = [0.0] * MAX_POOL_SIZE
        self._size: list[int] = [6] * MAX_POOL_SIZE
        self._alpha: list[float] = [0.6] * MAX_POOL_SIZE
        self._phase: list[float] = [0.0] * MAX_POOL_SIZE
        self._color_idx: list[int] = [0] * MAX_POOL_SIZE
        self._depth: list[float] = [1.0] * MAX_POOL_SIZE

        self._seed_pool()

    @property
    def preset(self) -> str:
        return self._preset

    @property
    def perf_profile(self) -> str:
        return self._perf

    @property
    def pool_capacity(self) -> int:
        return MAX_POOL_SIZE

    @property
    def active_count(self) -> int:
        """Cantidad de partículas activas según el preset y perfil de rendimiento."""
        if self._preset == "none" or self._perf == "off":
            return 0
        base = {
            "arcade_sparks": 40,
            "neon_dust": 44,
            "snow_drift": 48,
            "starfield_parallax": 56,
        }.get(self._preset, 32)
        if self._perf == "balanced":
            return max(12, base // 2)
        return min(MAX_POOL_SIZE, base)

    def set_preset(self, preset: str) -> None:
        norm = normalize_particle_preset(preset)
        if norm != self._preset:
            self._preset = norm
            self._seed_pool()

    def set_perf_profile(self, perf_profile: str) -> None:
        self._perf = normalize_effects_perf(perf_profile)

    def _seed_pool(self) -> None:
        for i in range(MAX_POOL_SIZE):
            self._reset_slot(i, initial=True)

    def _reset_slot(self, idx: int, initial: bool = False) -> None:
        r = self._rng
        self._phase[idx] = r.uniform(0.0, math.tau)
        self._color_idx[idx] = i_col = idx % 3
        _ = i_col

        if self._preset == "arcade_sparks":
            self._x[idx] = r.uniform(0.02, 0.98)
            self._y[idx] = r.uniform(0.05, 1.0) if initial else r.uniform(0.96, 1.06)
            self._vx[idx] = r.uniform(-0.022, 0.022)
            self._vy[idx] = -r.uniform(0.08, 0.22)
            self._size[idx] = r.randint(6, 13)
            self._alpha[idx] = r.uniform(0.35, 0.85)
            self._depth[idx] = r.uniform(0.7, 1.2)

        elif self._preset == "neon_dust":
            self._x[idx] = r.uniform(0.0, 1.0)
            self._y[idx] = r.uniform(0.0, 1.0)
            self._vx[idx] = r.uniform(-0.018, 0.018)
            self._vy[idx] = r.uniform(-0.025, 0.015)
            self._size[idx] = r.randint(7, 16)
            self._alpha[idx] = r.uniform(0.22, 0.62)
            self._depth[idx] = r.uniform(0.5, 1.0)

        elif self._preset == "snow_drift":
            self._x[idx] = r.uniform(0.0, 1.0)
            self._y[idx] = r.uniform(0.0, 1.0) if initial else r.uniform(-0.08, -0.01)
            self._vx[idx] = r.uniform(-0.015, 0.032)
            self._vy[idx] = r.uniform(0.045, 0.13)
            self._size[idx] = r.randint(5, 12)
            self._alpha[idx] = r.uniform(0.32, 0.78)
            self._depth[idx] = r.uniform(0.6, 1.1)

        elif self._preset == "starfield_parallax":
            depth = r.uniform(0.25, 1.25)
            self._depth[idx] = depth
            self._x[idx] = r.uniform(0.0, 1.0) if initial else r.uniform(1.01, 1.08)
            self._y[idx] = r.uniform(0.02, 0.98)
            self._vx[idx] = -0.065 * depth
            self._vy[idx] = 0.0
            self._size[idx] = max(4, int(4 + depth * 5))
            self._alpha[idx] = min(0.95, 0.25 + depth * 0.55)
        else:
            self._x[idx] = r.uniform(0.0, 1.0)
            self._y[idx] = r.uniform(0.0, 1.0)
            self._vx[idx] = 0.0
            self._vy[idx] = 0.0
            self._size[idx] = 6
            self._alpha[idx] = 0.0
            self._depth[idx] = 1.0

    def step(self, dt: float) -> None:
        """Avanza la simulación con un paso temporal acotado."""
        count = self.active_count
        if count <= 0:
            return

        dt_clamped = max(0.001, min(0.10, float(dt)))
        self._time += dt_clamped
        preset = self._preset

        for i in range(count):
            if preset == "arcade_sparks":
                wobble = math.sin(self._time * 3.1 + self._phase[i]) * 0.015
                self._x[i] += (self._vx[i] + wobble) * dt_clamped
                self._y[i] += self._vy[i] * dt_clamped
                if self._y[i] < -0.05 or self._x[i] < -0.06 or self._x[i] > 1.06:
                    self._reset_slot(i, initial=False)

            elif preset == "neon_dust":
                self._x[i] += (self._vx[i] + math.cos(self._time * 0.8 + self._phase[i]) * 0.012) * dt_clamped
                self._y[i] += (self._vy[i] + math.sin(self._time * 0.9 + self._phase[i]) * 0.012) * dt_clamped
                self._x[i] %= 1.0
                self._y[i] %= 1.0

            elif preset == "snow_drift":
                sway = math.sin(self._time * 1.8 + self._phase[i]) * 0.018
                self._x[i] = (self._x[i] + (self._vx[i] + sway) * dt_clamped) % 1.0
                self._y[i] += self._vy[i] * dt_clamped
                if self._y[i] > 1.05:
                    self._reset_slot(i, initial=False)

            elif preset == "starfield_parallax":
                self._x[i] += self._vx[i] * dt_clamped
                if self._x[i] < -0.04:
                    self._x[i] = 1.04
                    self._y[i] = self._rng.uniform(0.02, 0.98)

    def paint(self, painter: QPainter, rect: QRect | QRectF, scale: float = 1.0) -> None:
        """Renderiza todas las partículas activas dentro de rect usando sprites cacheados."""
        count = self.active_count
        if count <= 0:
            return

        r = QRectF(rect)
        if r.width() < 4 or r.height() < 4:
            return

        palette = _PRESET_PALETTES.get(self._preset, _PRESET_PALETTES["neon_dust"])
        sc = max(0.35, min(2.0, float(scale)))

        painter.save()
        try:
            painter.setClipRect(r)
            for i in range(count):
                px = r.x() + self._x[i] * r.width()
                py = r.y() + self._y[i] * r.height()
                diam = max(4, int(round(self._size[i] * sc)))
                col = palette[self._color_idx[i] % len(palette)]
                sprite = _get_glow_sprite(col, diam)

                twinkle = 0.85 + 0.15 * math.sin(self._time * 2.6 + self._phase[i])
                painter.setOpacity(max(0.08, min(1.0, self._alpha[i] * twinkle)))
                half = diam * 0.5
                painter.drawPixmap(int(px - half), int(py - half), sprite)
        finally:
            painter.restore()


class RetroEffectOverlayWidget(QWidget):
    """Capa transparente click-through para partículas y shaders globales en vivo.

    No roba foco ni bloquea eventos de mouse/teclado; pensado para superponerse
    sin fricciones sobre `PlayerWindow` o la vista Sandbox.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._shader_preset: str = "none"
        self._shader_target: str = "tv_rect"
        self._particle_preset: str = "none"
        self._perf_profile: str = "high"

        self._particles = ParticleSystem("none", self._perf_profile)
        self._start_ts: float = time.monotonic()
        self._last_ts: float = self._start_ts

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

    @property
    def particle_system(self) -> ParticleSystem:
        return self._particles

    def configure(
        self,
        *,
        shader_preset: str | None = None,
        shader_target: str | None = None,
        particle_preset: str | None = None,
        perf_profile: str | None = None,
    ) -> None:
        if shader_preset is not None:
            self._shader_preset = normalize_shader_preset(shader_preset)
        if shader_target is not None:
            self._shader_target = normalize_shader_target(shader_target)
        if perf_profile is not None:
            self._perf_profile = normalize_effects_perf(perf_profile)
            self._particles.set_perf_profile(self._perf_profile)
        if particle_preset is not None:
            self._particle_preset = normalize_particle_preset(particle_preset)
            self._particles.set_preset(self._particle_preset)

        self._sync_timer_and_visibility()
        self.update()

    def _has_active_visuals(self) -> bool:
        if self._perf_profile == "off":
            return False
        has_parts = self._particle_preset != "none" and self._particles.active_count > 0
        has_global_shader = self._shader_preset != "none" and self._shader_target == "global"
        return has_parts or has_global_shader

    def _needs_animation_timer(self) -> bool:
        if self._perf_profile == "off":
            return False
        if self._particle_preset != "none":
            return True
        return self._shader_target == "global" and self._shader_preset == "vhs_arcade"

    def _sync_timer_and_visibility(self) -> None:
        active = self._has_active_visuals()
        if not active:
            self._timer.stop()
            self.hide()
            return

        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
            self.raise_()
        self.show()

        if self._needs_animation_timer():
            interval = 33 if self._perf_profile == "balanced" else 16
            if self._timer.interval() != interval or not self._timer.isActive():
                self._last_ts = time.monotonic()
                self._timer.start(interval)
        else:
            self._timer.stop()

    def stop(self) -> None:
        self._timer.stop()

    def _on_tick(self) -> None:
        now = time.monotonic()
        dt = max(0.004, min(0.08, now - self._last_ts))
        self._last_ts = now
        if self._particle_preset != "none":
            self._particles.step(dt)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._has_active_visuals():
            return
        painter = QPainter(self)
        rect = self.rect()
        if self._particle_preset != "none":
            scale = max(0.45, min(1.5, rect.width() / 1920.0))
            self._particles.paint(painter, rect, scale=scale)
        if self._shader_preset != "none" and self._shader_target == "global":
            elapsed = time.monotonic() - self._start_ts
            render_shader_overlay_painter(painter, rect, self._shader_preset, elapsed=elapsed)
        painter.end()
