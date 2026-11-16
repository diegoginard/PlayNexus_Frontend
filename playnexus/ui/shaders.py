"""Pipeline modular de shaders retro (GPU GLSL con fallback automático a CPU QPainter)."""

from __future__ import annotations

import math
import os
import struct
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QOffscreenSurface,
    QOpenGLContext,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
    QSurfaceFormat,
)
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLFramebufferObjectFormat,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

# ---------------------------------------------------------------------------
# Registros declarativos de shaders y perfiles
# ---------------------------------------------------------------------------

SHADER_PRESETS: list[tuple[str, str]] = [
    ("none", "Sin shader (Nativo)"),
    ("crt_aperture", "CRT Aperture (Curvatura + Trinitron + Scanlines)"),
    ("crt_bloom", "CRT Bloom (Halo fósforo cálido + CRT)"),
    ("lcd_handheld", "LCD Handheld (Matriz subpíxeles portátil)"),
    ("vhs_arcade", "VHS / Arcade Analógico (Aberración + Ruido)"),
]

SHADER_TARGETS: list[tuple[str, str]] = [
    ("tv_rect", "Solo pantalla / Video (TV_RECT)"),
    ("global", "Post-proceso global de pantalla"),
]

EFFECT_PERF_PROFILES: list[tuple[str, str]] = [
    ("high", "Alto (GPU + Efectos completos 60 FPS)"),
    ("balanced", "Equilibrado (Efectos optimizados 30-60 FPS)"),
    ("off", "Desactivado (Máximo rendimiento CPU/GPU)"),
]

VALID_SHADER_PRESETS: set[str] = {key for key, _ in SHADER_PRESETS}
VALID_SHADER_TARGETS: set[str] = {key for key, _ in SHADER_TARGETS}
VALID_PERF_PROFILES: set[str] = {key for key, _ in EFFECT_PERF_PROFILES}

SHADER_LABELS: dict[str, str] = dict(SHADER_PRESETS)
TARGET_LABELS: dict[str, str] = dict(SHADER_TARGETS)
PERF_LABELS: dict[str, str] = dict(EFFECT_PERF_PROFILES)


def normalize_shader_preset(value: Any, *, allow_layout: bool = False) -> str:
    """Normaliza cualquier identificador o etiqueta de preset de shader."""
    raw = str(value or "").strip().lower()
    if allow_layout and raw in ("layout", "auto", "default", "del layout"):
        return "layout"
    if not raw or raw in ("none", "off", "disabled", "sin shader", "ninguno"):
        return "none"
    if raw in VALID_SHADER_PRESETS:
        return raw
    for key, label in SHADER_PRESETS:
        if raw == label.strip().lower():
            return key
    return "none"


def normalize_shader_target(value: Any) -> str:
    """Normaliza el objetivo de aplicación del shader ('tv_rect' o 'global')."""
    raw = str(value or "").strip().lower()
    if raw in VALID_SHADER_TARGETS:
        return raw
    if "global" in raw or "post" in raw:
        return "global"
    return "tv_rect"


def normalize_effects_perf(value: Any) -> str:
    """Normaliza el perfil de rendimiento de efectos GPU/partículas."""
    raw = str(value or "").strip().lower()
    if raw in VALID_PERF_PROFILES:
        return raw
    if raw in ("low", "off", "disabled", "desactivado"):
        return "off"
    if raw in ("med", "medium", "balanced", "equilibrado"):
        return "balanced"
    return "high"


# ---------------------------------------------------------------------------
# Shaders GLSL compatibles con Desktop OpenGL 2.1+ y OpenGL ES 2.0 / ANGLE
# ---------------------------------------------------------------------------

_VERTEX_SHADER_SRC = """
attribute vec2 a_pos;
attribute vec2 a_uv;
varying vec2 v_uv;
void main() {
    v_uv = a_uv;
    gl_Position = vec4(a_pos, 0.0, 1.0);
}
"""

_FRAGMENT_SHADERS: dict[str, str] = {
    "crt_aperture": """
uniform sampler2D u_tex;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_intensity;
varying vec2 v_uv;

vec2 barrelDistort(vec2 uv, float amt) {
    vec2 cc = uv - 0.5;
    float r2 = dot(cc, cc);
    return uv + cc * r2 * amt;
}

void main() {
    float inten = clamp(u_intensity, 0.0, 1.5);
    vec2 uv = mix(v_uv, barrelDistort(v_uv, 0.14 * inten), 0.75);

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        gl_FragColor = vec4(0.02, 0.02, 0.025, 1.0);
        return;
    }

    // Convergencia sutil RGB estilo Trinitron
    float px = 0.65 / max(u_resolution.x, 1.0);
    float r = texture2D(u_tex, vec2(uv.x + px, uv.y)).r;
    float g = texture2D(u_tex, uv).g;
    float b = texture2D(u_tex, vec2(uv.x - px, uv.y)).b;
    float a = texture2D(u_tex, uv).a;
    vec3 col = vec3(r, g, b);

    // Scanlines independientes de resolucion
    float scanFreq = clamp(u_resolution.y * 0.62, 160.0, 420.0);
    float scan = 0.87 + 0.13 * sin(uv.y * scanFreq * 3.14159265);
    col *= mix(1.0, scan, clamp(0.85 * inten, 0.0, 1.0));

    // Mascara vertical RGB tipo Aperture Grille
    float gx = mod(floor(uv.x * max(u_resolution.x, 320.0)), 3.0);
    vec3 mask = vec3(
        gx < 0.5 ? 1.06 : 0.90,
        (gx >= 0.5 && gx < 1.5) ? 1.06 : 0.90,
        gx >= 1.5 ? 1.06 : 0.90
    );
    col *= mix(vec3(1.0), mask, clamp(0.58 * inten, 0.0, 0.85));

    // Viñeteado suave de bordes CRT
    vec2 edge = uv * (1.0 - uv);
    float vig = clamp(pow(edge.x * edge.y * 16.0, 0.16), 0.0, 1.0);
    col *= mix(1.0, vig, 0.55);

    gl_FragColor = vec4(clamp(col * 1.05, 0.0, 1.0), a);
}
""",
    "crt_bloom": """
uniform sampler2D u_tex;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_intensity;
varying vec2 v_uv;

vec2 curveUV(vec2 uv, float amt) {
    vec2 c = uv - 0.5;
    return uv + c * dot(c, c) * amt;
}

void main() {
    float inten = clamp(u_intensity, 0.0, 1.5);
    vec2 uv = curveUV(v_uv, 0.11 * inten);

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        gl_FragColor = vec4(0.015, 0.015, 0.02, 1.0);
        return;
    }

    vec4 center = texture2D(u_tex, uv);
    vec2 stepUv = vec2(2.2 / max(u_resolution.x, 1.0), 2.2 / max(u_resolution.y, 1.0));

    vec3 bloom = vec3(0.0);
    bloom += texture2D(u_tex, clamp(uv + vec2( stepUv.x,  0.0), 0.001, 0.999)).rgb;
    bloom += texture2D(u_tex, clamp(uv + vec2(-stepUv.x,  0.0), 0.001, 0.999)).rgb;
    bloom += texture2D(u_tex, clamp(uv + vec2( 0.0,  stepUv.y), 0.001, 0.999)).rgb;
    bloom += texture2D(u_tex, clamp(uv + vec2( 0.0, -stepUv.y), 0.001, 0.999)).rgb;
    bloom += texture2D(u_tex, clamp(uv + stepUv * 1.4, 0.001, 0.999)).rgb * 0.6;
    bloom += texture2D(u_tex, clamp(uv - stepUv * 1.4, 0.001, 0.999)).rgb * 0.6;
    bloom /= 5.2;

    float luma = dot(bloom, vec3(0.299, 0.587, 0.114));
    vec3 warmBloom = bloom * smoothstep(0.32, 0.95, luma) * vec3(1.10, 1.02, 0.92);

    float scan = 0.89 + 0.11 * sin(uv.y * clamp(u_resolution.y * 0.55, 140.0, 380.0) * 3.14159);
    vec3 col = center.rgb * mix(1.0, scan, 0.65 * inten) + warmBloom * (0.48 * inten);

    vec2 edge = uv * (1.0 - uv);
    float vig = clamp(pow(edge.x * edge.y * 15.0, 0.18), 0.0, 1.0);
    col *= mix(1.0, vig, 0.45);

    gl_FragColor = vec4(clamp(col, 0.0, 1.0), center.a);
}
""",
    "lcd_handheld": """
uniform sampler2D u_tex;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_intensity;
varying vec2 v_uv;

void main() {
    float inten = clamp(u_intensity, 0.0, 1.5);
    vec2 gridCells = vec2(clamp(u_resolution.x * 0.34, 160.0, 320.0),
                          clamp(u_resolution.y * 0.34, 120.0, 220.0));
    vec2 cellUv = (floor(v_uv * gridCells) + 0.5) / gridCells;
    vec2 sampleUv = mix(v_uv, cellUv, 0.28 * inten);

    vec4 texCol = texture2D(u_tex, clamp(sampleUv, 0.001, 0.999));
    vec2 sub = fract(v_uv * gridCells);

    // Rejilla LCD y separacion sutil de subpixeles
    float borderX = smoothstep(0.0, 0.14, sub.x) * (1.0 - smoothstep(0.86, 1.0, sub.x));
    float borderY = smoothstep(0.0, 0.14, sub.y) * (1.0 - smoothstep(0.86, 1.0, sub.y));
    float lcdMask = mix(1.0, 0.78 + 0.22 * borderX * borderY, clamp(0.85 * inten, 0.0, 1.0));

    vec3 subRgb = vec3(
        sub.x < 0.333 ? 1.05 : 0.93,
        (sub.x >= 0.333 && sub.x < 0.666) ? 1.05 : 0.93,
        sub.x >= 0.666 ? 1.05 : 0.93
    );

    vec3 col = texCol.rgb * lcdMask * mix(vec3(1.0), subRgb, 0.40 * inten);
    // Ligero tono retroiluminado calido
    col *= mix(vec3(1.0), vec3(1.02, 1.04, 0.97), 0.35 * inten);

    gl_FragColor = vec4(clamp(col, 0.0, 1.0), texCol.a);
}
""",
    "vhs_arcade": """
uniform sampler2D u_tex;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_intensity;
varying vec2 v_uv;

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

void main() {
    float inten = clamp(u_intensity, 0.0, 1.5);
    float bandPos = fract(u_time * 0.18);
    float band = exp(-pow((v_uv.y - bandPos) * 14.0, 2.0));
    float jitter = sin(v_uv.y * 90.0 + u_time * 16.0) * 0.0012 * (0.35 + band * 1.6) * inten;

    vec2 uv = vec2(clamp(v_uv.x + jitter, 0.001, 0.999), v_uv.y);
    float chroma = (0.0022 + band * 0.0025) * inten;

    float r = texture2D(u_tex, vec2(clamp(uv.x + chroma, 0.001, 0.999), uv.y)).r;
    float g = texture2D(u_tex, uv).g;
    float b = texture2D(u_tex, vec2(clamp(uv.x - chroma, 0.001, 0.999), uv.y)).b;
    float a = texture2D(u_tex, uv).a;
    vec3 col = vec3(r, g, b);

    // Ruido analogico ligero y banda VHS
    float grain = (hash12(floor(uv * max(u_resolution, vec2(320.0, 240.0))) + fract(u_time * 24.0) * 57.0) - 0.5);
    col += vec3(grain * 0.055 * inten);
    col += vec3(band * 0.06 * inten);

    float scan = 0.93 + 0.07 * sin(uv.y * clamp(u_resolution.y * 0.5, 120.0, 320.0) * 3.14159);
    col *= mix(1.0, scan, 0.6 * inten);

    gl_FragColor = vec4(clamp(col, 0.0, 1.0), a);
}
""",
}

# Quad fullscreen con UV top-left (0,0) -> (1,1) para evitar mirror vertical en FBO/toImage
_FULLSCREEN_QUAD_DATA = struct.pack(
    "16f",
    -1.0, -1.0, 0.0, 1.0,
     1.0, -1.0, 1.0, 1.0,
    -1.0,  1.0, 0.0, 0.0,
     1.0,  1.0, 1.0, 0.0,
)

# ---------------------------------------------------------------------------
# Cache liviana de texturas patrón para modo CPU/Overlay (QPainter > 120 FPS)
# ---------------------------------------------------------------------------

_TILE_PATTERN_CACHE: dict[tuple[str, int, int], QPixmap] = {}


def _get_scanline_tile(spacing: int = 3, alpha: int = 58) -> QPixmap:
    key = ("scan", spacing, alpha)
    cached = _TILE_PATTERN_CACHE.get(key)
    if cached is not None:
        return cached
    pm = QPixmap(8, max(2, spacing))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.fillRect(0, pm.height() - 1, pm.width(), 1, QColor(0, 0, 0, alpha))
    p.end()
    _TILE_PATTERN_CACHE[key] = pm
    return pm


def _get_aperture_tile(alpha: int = 32) -> QPixmap:
    key = ("aperture", alpha, 3)
    cached = _TILE_PATTERN_CACHE.get(key)
    if cached is not None:
        return cached
    pm = QPixmap(6, 4)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.fillRect(0, 0, 1, 4, QColor(255, 64, 64, alpha))
    p.fillRect(1, 0, 1, 4, QColor(64, 255, 96, alpha))
    p.fillRect(2, 0, 1, 4, QColor(64, 140, 255, alpha))
    p.fillRect(3, 0, 1, 4, QColor(255, 64, 64, alpha // 2))
    p.fillRect(4, 0, 1, 4, QColor(64, 255, 96, alpha // 2))
    p.fillRect(5, 0, 1, 4, QColor(64, 140, 255, alpha // 2))
    p.fillRect(0, 3, 6, 1, QColor(0, 0, 0, min(95, alpha + 38)))
    p.end()
    _TILE_PATTERN_CACHE[key] = pm
    return pm


def _get_lcd_tile(cell: int = 4, alpha: int = 48) -> QPixmap:
    key = ("lcd", cell, alpha)
    cached = _TILE_PATTERN_CACHE.get(key)
    if cached is not None:
        return cached
    s = max(3, cell)
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.fillRect(0, s - 1, s, 1, QColor(0, 0, 0, alpha))
    p.fillRect(s - 1, 0, 1, s, QColor(0, 0, 0, alpha))
    p.fillRect(0, 0, 1, 1, QColor(255, 255, 255, 14))
    p.end()
    _TILE_PATTERN_CACHE[key] = pm
    return pm


def render_shader_overlay_painter(
    painter: QPainter,
    rect: QRect | QRectF,
    preset: str,
    elapsed: float = 0.0,
    intensity: float = 1.0,
) -> None:
    """Dibuja un overlay retro optimizado mediante QPainter sobre rect.

    Soporta tanto presets de shader ('crt_aperture', 'crt_bloom', 'lcd_handheld',
    'vhs_arcade') como efectos clásicos de Layout Studio ('scanlines', 'vignette').
    """
    raw = str(preset or "").strip().lower()
    if raw in ("", "none", "off"):
        return

    r = rect.toRect() if isinstance(rect, QRectF) else QRect(rect)
    if r.width() < 4 or r.height() < 4:
        return

    inten = max(0.0, min(1.5, float(intensity)))
    painter.save()
    try:
        painter.setClipRect(r)

        if raw == "scanlines":
            tile = _get_scanline_tile(3, int(68 * inten))
            painter.drawTiledPixmap(r, tile)
            return

        if raw == "vignette":
            center = QRectF(r).center()
            rad = max(r.width(), r.height()) * 0.72
            grad = QRadialGradient(center, rad)
            grad.setColorAt(0.45, QColor(0, 0, 0, 0))
            grad.setColorAt(1.0, QColor(0, 0, 0, min(220, int(155 * inten))))
            painter.fillRect(r, grad)
            return

        norm = normalize_shader_preset(raw)
        if norm == "crt_aperture":
            painter.drawTiledPixmap(r, _get_aperture_tile(int(26 * inten)))
            painter.drawTiledPixmap(r, _get_scanline_tile(3, int(52 * inten)))
            grad = QRadialGradient(QRectF(r).center(), max(r.width(), r.height()) * 0.72)
            grad.setColorAt(0.55, QColor(0, 0, 0, 0))
            grad.setColorAt(1.0, QColor(0, 0, 0, min(180, int(105 * inten))))
            painter.fillRect(r, grad)
            # Marco redondeado sutil simulando tubo CRT
            painter.setPen(QPen(QColor(0, 0, 0, 120), max(2, min(r.width(), r.height()) // 110)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(r.adjusted(1, 1, -1, -1), 16, 16)

        elif norm == "crt_bloom":
            painter.fillRect(r, QColor(255, 224, 170, int(16 * inten)))
            painter.drawTiledPixmap(r, _get_scanline_tile(4, int(42 * inten)))
            bloom_grad = QRadialGradient(QRectF(r).center(), max(r.width(), r.height()) * 0.65)
            bloom_grad.setColorAt(0.0, QColor(255, 244, 214, int(24 * inten)))
            bloom_grad.setColorAt(0.68, QColor(255, 200, 140, int(8 * inten)))
            bloom_grad.setColorAt(1.0, QColor(0, 0, 0, min(170, int(92 * inten))))
            painter.fillRect(r, bloom_grad)

        elif norm == "lcd_handheld":
            cell = 4 if r.width() >= 480 else 3
            painter.fillRect(r, QColor(14, 26, 18, int(14 * inten)))
            painter.drawTiledPixmap(r, _get_lcd_tile(cell, int(54 * inten)))

        elif norm == "vhs_arcade":
            painter.drawTiledPixmap(r, _get_scanline_tile(4, int(38 * inten)))
            # Banda de tracking analógica desplazándose suavemente
            band_pos = (elapsed * 0.18) % 1.0
            by = r.y() + int(band_pos * r.height())
            bh = max(6, r.height() // 26)
            band_grad = QLinearGradient(r.x(), by - bh, r.x(), by + bh)
            band_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            band_grad.setColorAt(0.5, QColor(210, 235, 255, int(28 * inten)))
            band_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(QRect(r.x(), by - bh, r.width(), bh * 2), band_grad)
            # Aberración sutil lateral roja/cian
            edge_w = max(2, r.width() // 240)
            painter.fillRect(QRect(r.x(), r.y(), edge_w, r.height()), QColor(255, 40, 60, int(35 * inten)))
            painter.fillRect(QRect(r.right() - edge_w, r.y(), edge_w, r.height()), QColor(40, 210, 255, int(35 * inten)))
    finally:
        painter.restore()


# ---------------------------------------------------------------------------
# Procesador GPU GLSL Offscreen con fallback automático a CPU
# ---------------------------------------------------------------------------


class OffscreenShaderProcessor:
    """Compila y ejecuta shaders GLSL offscreen en GPU vía FBO, con fallback a QPainter.

    Diseñado para procesar fotogramas de video/canvas en `TV_RECT` sin bloquear
    la interfaz y sin requerir dependencias externas.
    """

    def __init__(self) -> None:
        self._initialized: bool = False
        self._gl_available: bool = False
        self._gl_error: str = ""
        self._context: QOpenGLContext | None = None
        self._surface: QOffscreenSurface | None = None
        self._programs: dict[str, QOpenGLShaderProgram] = {}
        self._vbo: QOpenGLBuffer | None = None
        self._fbos: dict[tuple[int, int], QOpenGLFramebufferObject] = {}
        self._frame_cache: dict[tuple[Any, ...], QImage] = {}
        self._max_frame_cache: int = 8

    @property
    def gl_active(self) -> bool:
        """Indica si el pipeline OpenGL GLSL está compilado y operativo."""
        if not self._initialized:
            self.initialize()
        return self._gl_available

    @property
    def last_error(self) -> str:
        return self._gl_error

    def _is_offscreen_platform(self) -> bool:
        app = QCoreApplication.instance()
        if app is not None:
            try:
                pname = str(app.platformName() or "").lower()
                if pname in ("offscreen", "minimal", "vnc"):
                    return True
            except Exception:
                pass
        return str(os.environ.get("QT_QPA_PLATFORM", "")).lower() in ("offscreen", "minimal")

    def initialize(self) -> bool:
        """Inicializa el contexto OpenGL offscreen y compila los shaders."""
        if self._initialized:
            return self._gl_available
        self._initialized = True

        if QCoreApplication.instance() is None:
            self._gl_available = False
            self._gl_error = "Sin QApplication activa"
            return False

        if self._is_offscreen_platform():
            self._gl_available = False
            self._gl_error = "Plataforma Qt offscreen/minimal; usando fallback QPainter"
            return False

        try:
            fmt = QSurfaceFormat()
            fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
            fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.SingleBuffer)

            ctx = QOpenGLContext()
            ctx.setFormat(fmt)
            if not ctx.create():
                self._gl_available = False
                self._gl_error = "QOpenGLContext.create() devolvió False"
                return False

            surf = QOffscreenSurface()
            surf.setFormat(ctx.format())
            surf.create()
            if not surf.isValid() or not ctx.makeCurrent(surf):
                self._gl_available = False
                self._gl_error = "No se pudo activar QOffscreenSurface"
                return False

            programs: dict[str, QOpenGLShaderProgram] = {}
            for preset_id, frag_src in _FRAGMENT_SHADERS.items():
                prog = QOpenGLShaderProgram()
                if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX_SHADER_SRC):
                    raise RuntimeError(f"VS {preset_id}: {prog.log()}")
                if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag_src):
                    raise RuntimeError(f"FS {preset_id}: {prog.log()}")
                if not prog.link():
                    raise RuntimeError(f"Link {preset_id}: {prog.log()}")
                programs[preset_id] = prog

            vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            if not vbo.create():
                raise RuntimeError("No se pudo crear VBO")
            vbo.bind()
            vbo.allocate(_FULLSCREEN_QUAD_DATA, len(_FULLSCREEN_QUAD_DATA))
            vbo.release()

            ctx.doneCurrent()

            self._context = ctx
            self._surface = surf
            self._programs = programs
            self._vbo = vbo
            self._gl_available = True
            self._gl_error = ""
            return True
        except Exception as exc:
            try:
                if ctx := locals().get("ctx"):
                    ctx.doneCurrent()
            except Exception:
                pass
            self._gl_available = False
            self._gl_error = str(exc)
            return False

    def _get_fbo(self, w: int, h: int) -> QOpenGLFramebufferObject:
        key = (w, h)
        fbo = self._fbos.get(key)
        if fbo is None or not fbo.isValid():
            if len(self._fbos) >= 6:
                self._fbos.clear()
            fmt = QOpenGLFramebufferObjectFormat()
            fmt.setAttachment(QOpenGLFramebufferObject.Attachment.NoAttachment)
            fbo = QOpenGLFramebufferObject(w, h, fmt)
            self._fbos[key] = fbo
        return fbo

    def process_image(
        self,
        src_image: QImage,
        target_size: QSize | tuple[int, int] | None,
        preset: str,
        elapsed: float = 0.0,
        intensity: float = 1.0,
    ) -> QImage:
        """Aplica el shader al QImage origen devolviendo la imagen filtrada al tamaño destino."""
        if src_image is None or src_image.isNull():
            return src_image

        norm = normalize_shader_preset(preset)
        if target_size is None:
            tw, th = src_image.width(), src_image.height()
        elif isinstance(target_size, QSize):
            tw, th = target_size.width(), target_size.height()
        else:
            tw, th = int(target_size[0]), int(target_size[1])

        tw = max(4, min(3840, tw))
        th = max(4, min(2160, th))

        if norm == "none" or norm not in _FRAGMENT_SHADERS:
            return src_image

        # Cuantizamos el bucket temporal: estático para shaders espaciales, 24 Hz para VHS animado
        time_bucket = int(elapsed * 24.0) if norm == "vhs_arcade" else 0
        cache_key = (int(src_image.cacheKey()), tw, th, norm, time_bucket, round(intensity, 2))
        cached = self._frame_cache.get(cache_key)
        if cached is not None:
            return cached

        out: QImage | None = None
        if self.gl_active:
            out = self._process_gpu(src_image, tw, th, norm, elapsed, intensity)

        if out is None or out.isNull():
            out = self._process_software(src_image, tw, th, norm, elapsed, intensity)

        if out is not None and not out.isNull():
            if len(self._frame_cache) >= self._max_frame_cache:
                oldest = next(iter(self._frame_cache))
                self._frame_cache.pop(oldest, None)
            self._frame_cache[cache_key] = out
            return out
        return src_image

    def _process_gpu(
        self,
        src_image: QImage,
        tw: int,
        th: int,
        preset: str,
        elapsed: float,
        intensity: float,
    ) -> QImage | None:
        if (
            self._context is None
            or self._surface is None
            or self._vbo is None
            or preset not in self._programs
        ):
            return None

        tex: QOpenGLTexture | None = None
        made_current = False
        try:
            if not self._context.makeCurrent(self._surface):
                return None
            made_current = True

            upload_img = src_image
            if upload_img.format() not in (
                QImage.Format.Format_RGBA8888,
                QImage.Format.Format_ARGB32,
                QImage.Format.Format_RGB32,
                QImage.Format.Format_ARGB32_Premultiplied,
            ):
                upload_img = upload_img.convertToFormat(QImage.Format.Format_RGBA8888)

            f = self._context.functions()
            fbo = self._get_fbo(tw, th)
            if not fbo.isValid() or not fbo.bind():
                return None

            tex = QOpenGLTexture(upload_img, QOpenGLTexture.MipMapGeneration.DontGenerateMipMaps)
            tex.setMinMagFilters(
                QOpenGLTexture.Filter.Linear,
                QOpenGLTexture.Filter.Linear,
            )
            tex.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)

            prog = self._programs[preset]
            prog.bind()
            self._vbo.bind()

            f.glViewport(0, 0, tw, th)
            f.glClearColor(0.0, 0.0, 0.0, 0.0)
            f.glClear(0x00004000)

            pos_loc = prog.attributeLocation("a_pos")
            uv_loc = prog.attributeLocation("a_uv")
            prog.enableAttributeArray(pos_loc)
            prog.enableAttributeArray(uv_loc)
            prog.setAttributeBuffer(pos_loc, 0x1406, 0, 2, 16)
            prog.setAttributeBuffer(uv_loc, 0x1406, 8, 2, 16)

            f.glActiveTexture(0x84C0)
            tex.bind()
            prog.setUniformValue("u_tex", 0)
            prog.setUniformValue("u_resolution", float(tw), float(th))
            prog.setUniformValue("u_time", float(elapsed))
            prog.setUniformValue("u_intensity", float(intensity))

            f.glDrawArrays(0x0005, 0, 4)

            prog.disableAttributeArray(pos_loc)
            prog.disableAttributeArray(uv_loc)
            self._vbo.release()
            prog.release()
            fbo.release()

            result = fbo.toImage()
            tex.destroy()
            tex = None
            return result
        except Exception as exc:
            self._gl_error = str(exc)
            self._gl_available = False
            return None
        finally:
            if tex is not None and made_current:
                try:
                    tex.destroy()
                except Exception:
                    pass
            if made_current and self._context is not None:
                try:
                    self._context.doneCurrent()
                except Exception:
                    pass

    def _process_software(
        self,
        src_image: QImage,
        tw: int,
        th: int,
        preset: str,
        elapsed: float,
        intensity: float,
    ) -> QImage:
        out = QImage(tw, th, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(QColor(0, 0, 0, 255))
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        dest = QRect(0, 0, tw, th)
        if preset == "vhs_arcade":
            jitter = int(math.sin(elapsed * 14.0) * max(1, tw // 320))
            painter.drawImage(dest.translated(jitter, 0), src_image)
        else:
            painter.drawImage(dest, src_image)

        render_shader_overlay_painter(painter, dest, preset, elapsed=elapsed, intensity=intensity)
        painter.end()
        return out

    def cleanup(self) -> None:
        """Libera recursos OpenGL de forma segura antes del cierre de QApplication."""
        if self._context is not None and self._surface is not None:
            try:
                if self._context.makeCurrent(self._surface):
                    self._fbos.clear()
                    if self._vbo is not None:
                        self._vbo.destroy()
                    self._programs.clear()
                    self._context.doneCurrent()
            except Exception:
                pass
        self._frame_cache.clear()
        self._fbos.clear()
        self._programs.clear()
        self._vbo = None
        self._surface = None
        self._context = None
        self._gl_available = False


_GLOBAL_PROCESSOR: OffscreenShaderProcessor | None = None


def get_shader_processor() -> OffscreenShaderProcessor:
    """Devuelve la instancia compartida del procesador de shaders."""
    global _GLOBAL_PROCESSOR
    if _GLOBAL_PROCESSOR is None:
        _GLOBAL_PROCESSOR = OffscreenShaderProcessor()
        app = QCoreApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.connect(_GLOBAL_PROCESSOR.cleanup)
            except Exception:
                pass
    return _GLOBAL_PROCESSOR


def apply_shader_to_image(
    src_image: QImage,
    target_size: QSize | tuple[int, int] | None,
    preset: str,
    elapsed: float = 0.0,
    intensity: float = 1.0,
) -> QImage:
    """Atajo de alto nivel para aplicar un preset de shader a una textura QImage."""
    return get_shader_processor().process_image(
        src_image, target_size, preset, elapsed=elapsed, intensity=intensity
    )


# ---------------------------------------------------------------------------
# Widget QOpenGLWidget para previsualización directa GPU / verificación
# ---------------------------------------------------------------------------


class RetroShaderPreviewGLWidget(QOpenGLWidget):
    """Viewport OpenGL hardware que renderiza un QImage con shaders GLSL en tiempo real."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: QImage = QImage()
        self._preset: str = "crt_aperture"
        self._intensity: float = 1.0
        self._elapsed: float = 0.0
        self._programs: dict[str, QOpenGLShaderProgram] = {}
        self._vbo: QOpenGLBuffer | None = None
        self._texture: QOpenGLTexture | None = None
        self._texture_dirty: bool = False
        self._gl_ready: bool = False

    def set_preset(self, preset: str) -> None:
        self._preset = normalize_shader_preset(preset)
        self.update()

    def set_image(self, image: QImage) -> None:
        self._image = image
        self._texture_dirty = True
        self.update()

    def set_elapsed(self, elapsed: float) -> None:
        self._elapsed = float(elapsed)
        self.update()

    @property
    def gl_ready(self) -> bool:
        return self._gl_ready

    def initializeGL(self) -> None:  # noqa: N802
        try:
            for preset_id, frag_src in _FRAGMENT_SHADERS.items():
                prog = QOpenGLShaderProgram(self)
                if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX_SHADER_SRC):
                    return
                if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag_src):
                    return
                if not prog.link():
                    return
                self._programs[preset_id] = prog

            vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            vbo.create()
            vbo.bind()
            vbo.allocate(_FULLSCREEN_QUAD_DATA, len(_FULLSCREEN_QUAD_DATA))
            vbo.release()
            self._vbo = vbo
            self._gl_ready = True
        except Exception:
            self._gl_ready = False

    def _ensure_texture(self) -> None:
        if not self._texture_dirty:
            return
        self._texture_dirty = False
        if self._texture is not None:
            self._texture.destroy()
            self._texture = None
        if not self._image.isNull():
            img = self._image
            if img.format() not in (
                QImage.Format.Format_RGBA8888,
                QImage.Format.Format_ARGB32,
                QImage.Format.Format_RGB32,
            ):
                img = img.convertToFormat(QImage.Format.Format_RGBA8888)
            self._texture = QOpenGLTexture(img, QOpenGLTexture.MipMapGeneration.DontGenerateMipMaps)
            self._texture.setMinMagFilters(QOpenGLTexture.Filter.Linear, QOpenGLTexture.Filter.Linear)
            self._texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)

    def paintGL(self) -> None:  # noqa: N802
        ctx = self.context()
        if ctx is None or not self._gl_ready:
            return
        f = ctx.functions()
        f.glViewport(0, 0, max(1, self.width()), max(1, self.height()))
        f.glClearColor(0.04, 0.05, 0.08, 1.0)
        f.glClear(0x00004000)

        self._ensure_texture()
        if self._texture is None or self._vbo is None:
            return

        preset_key = self._preset if self._preset in self._programs else "crt_aperture"
        prog = self._programs.get(preset_key)
        if prog is None:
            return

        prog.bind()
        self._vbo.bind()
        pos_loc = prog.attributeLocation("a_pos")
        uv_loc = prog.attributeLocation("a_uv")
        prog.enableAttributeArray(pos_loc)
        prog.enableAttributeArray(uv_loc)
        prog.setAttributeBuffer(pos_loc, 0x1406, 0, 2, 16)
        prog.setAttributeBuffer(uv_loc, 0x1406, 8, 2, 16)

        f.glActiveTexture(0x84C0)
        self._texture.bind()
        prog.setUniformValue("u_tex", 0)
        prog.setUniformValue("u_resolution", float(max(1, self.width())), float(max(1, self.height())))
        prog.setUniformValue("u_time", float(self._elapsed))
        prog.setUniformValue("u_intensity", float(0.0 if self._preset == "none" else self._intensity))

        f.glDrawArrays(0x0005, 0, 4)

        prog.disableAttributeArray(pos_loc)
        prog.disableAttributeArray(uv_loc)
        self._vbo.release()
        prog.release()


def resolve_widget_effect_settings(widget: Any) -> tuple[str, str, str, str]:
    """Resuelve (shader_preset, shader_target, particle_preset, perf_profile) para un layout.

    Combina las constantes declaradas por el propio layout (`SHADER_PRESET`, `SHADER_TARGET`,
    `PARTICLE_PRESET` o las variantes de Layout Studio `_studio_*`) con los overrides
    en tiempo de ejecución del usuario (`_pn_shader_override`, etc.).
    """
    perf = normalize_effects_perf(getattr(widget, "_pn_effects_perf", "high"))
    if perf == "off":
        return "none", "tv_rect", "none", "off"

    # Evitar import circular con particles usando lógica local equivalente
    raw_layout_pt = str(
        getattr(widget, "_studio_particle_preset", getattr(widget, "PARTICLE_PRESET", None)) or ""
    ).strip().lower()
    layout_particle = (
        raw_layout_pt
        if raw_layout_pt in ("arcade_sparks", "neon_dust", "snow_drift", "starfield_parallax")
        else "none"
    )

    layout_shader = normalize_shader_preset(
        getattr(widget, "_studio_shader_preset", getattr(widget, "SHADER_PRESET", None))
    )
    layout_target = normalize_shader_target(
        getattr(widget, "_studio_shader_target", getattr(widget, "SHADER_TARGET", "tv_rect"))
    )

    user_sh = normalize_shader_preset(
        getattr(widget, "_pn_shader_override", "layout"),
        allow_layout=True,
    )
    shader_preset = layout_shader if user_sh == "layout" else user_sh

    raw_user_tg = str(getattr(widget, "_pn_shader_target_override", "layout") or "layout").strip().lower()
    shader_target = layout_target if raw_user_tg in ("", "layout", "auto") else normalize_shader_target(raw_user_tg)

    raw_user_pt = str(getattr(widget, "_pn_particle_override", "layout") or "layout").strip().lower()
    if raw_user_pt in ("", "layout", "auto", "default", "del layout"):
        particle_preset = layout_particle
    elif raw_user_pt in ("arcade_sparks", "neon_dust", "snow_drift", "starfield_parallax"):
        particle_preset = raw_user_pt
    else:
        particle_preset = "none"

    return shader_preset, shader_target, particle_preset, perf


def _compute_layout_tv_target_size(widget: QWidget) -> QSize | None:
    rect_tuple = getattr(widget, "TV_RECT", None) or getattr(widget, "SNAP_LOCAL_RECT", None)
    if not rect_tuple or len(rect_tuple) < 4:
        return None
    try:
        rx, ry, rw, rh = [float(v) for v in rect_tuple[:4]]
        _ = rx, ry
        if rw <= 1.5 and rh <= 1.5:
            return QSize(max(16, int(widget.width() * rw)), max(16, int(widget.height() * rh)))
        return QSize(max(16, int(rw)), max(16, int(rh)))
    except Exception:
        return None


def install_layout_runtime_fx_hook(layout_widget: QWidget) -> None:
    """Envuelve de forma no destructiva `paintEvent` en layouts nativos de producción.

    Permite aplicar shaders GPU GLSL / fallback sobre `TV_RECT` antes de dibujar biseles,
    ruletas y overlays, sin modificar ningún archivo `Layouts/*/theme_layout.py`.
    """
    if layout_widget is None:
        return
    if getattr(layout_widget, "_pn_runtime_fx_hooked", False):
        return
    if getattr(layout_widget, "_studio_override_installed", False):
        return

    layout_widget._pn_runtime_fx_hooked = True
    layout_widget._pn_fx_start_ts = time.monotonic()
    orig_paint = layout_widget.paintEvent

    def _fx_wrapped_paint(event) -> None:
        sh_preset, sh_target, _pt_preset, fx_perf = resolve_widget_effect_settings(layout_widget)
        if fx_perf == "off" or sh_preset == "none" or sh_target != "tv_rect":
            orig_paint(event)
            return

        saved_attrs: list[tuple[str, QImage]] = []
        elapsed = max(0.0, time.monotonic() - float(getattr(layout_widget, "_pn_fx_start_ts", 0.0)))
        target_sz = _compute_layout_tv_target_size(layout_widget)
        try:
            for attr_name in ("_current_video_image", "_game_video_image"):
                img = getattr(layout_widget, attr_name, None)
                if isinstance(img, QImage) and not img.isNull():
                    filtered = apply_shader_to_image(
                        img,
                        target_sz or img.size(),
                        sh_preset,
                        elapsed=elapsed,
                    )
                    if filtered is not None and not filtered.isNull() and filtered is not img:
                        saved_attrs.append((attr_name, img))
                        setattr(layout_widget, attr_name, filtered)
            orig_paint(event)
        finally:
            for attr_name, raw_img in saved_attrs:
                setattr(layout_widget, attr_name, raw_img)

    layout_widget.paintEvent = _fx_wrapped_paint

