"""Motor de renderizado acelerado por GPU (OpenGL vía PySide6) para PlayNexus.

Características principales de Fase 1:
  - `GpuTextureCache`: Caché LRU de texturas `QOpenGLTexture` residentes en VRAM.
  - `GpuVideoSurface`: Carga directa de `QVideoFrame` sin pasar por `frame.toImage()`
    (soporta NV12/NV21, YUV420P/YV12 y planos RGB/BGRA con conversión en shader GPU).
  - `GpuSceneViewport`: Viewport `QOpenGLWidget` con homografía proyectiva de 4 puntos
    (`corner_pins`), composición premultiplicada, shaders retro sin readback (`fbo.toImage()`),
    escalado HiDPI exacto y respaldo automático a `QPainter` si OpenGL no está disponible.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import math
import os
import struct
import time
from typing import Any, Callable
import weakref

try:
    import shiboken6  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    shiboken6 = None  # type: ignore[assignment]

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QImage,
    QOffscreenSurface,
    QOpenGLContext,
    QPainter,
    QPixmap,
    QPolygonF,
    QSurfaceFormat,
    QTransform,
)
from PySide6.QtMultimedia import QVideoFrame, QVideoFrameFormat
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLFramebufferObjectFormat,
    QOpenGLPixelTransferOptions,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from playnexus.i18n import tr
from playnexus.ui.particles import (
    _PRESET_PALETTES,
    ParticleSystem,
    _get_glow_sprite,
    normalize_particle_preset,
)
from playnexus.ui.shaders import (
    _FRAGMENT_SHADERS,
    apply_shader_to_image,
    normalize_effects_perf,
    normalize_shader_preset,
)


# ---------------------------------------------------------------------------
# Perfiles de backend y detección de entorno gráfico
# ---------------------------------------------------------------------------

_RENDER_BACKEND_ALIASES: dict[str, str] = {
    "automático (gpu opengl con respaldo software)": "auto",
    "automatico (gpu opengl con respaldo software)": "auto",
    "automatic (gpu opengl with software fallback)": "auto",
    "gpu opengl (máxima fluidez)": "gpu",
    "gpu opengl (maxima fluidez)": "gpu",
    "gpu opengl (maximum smoothness)": "gpu",
    "software (qpainter clásico)": "software",
    "software (qpainter clasico)": "software",
    "software (classic qpainter)": "software",
}


def get_render_backend_profiles() -> list[tuple[str, str]]:
    """Devuelve la lista localizada de perfiles de renderizado `(id, etiqueta)`."""
    return [
        ("auto", tr("gpu.backend_auto", "Automatic (GPU OpenGL with Software fallback)")),
        ("gpu", tr("gpu.backend_gpu", "GPU OpenGL (Maximum smoothness)")),
        ("software", tr("gpu.backend_software", "Software (Classic QPainter)")),
    ]


RENDER_BACKEND_PROFILES: list[tuple[str, str]] = get_render_backend_profiles()

VALID_RENDER_BACKENDS: set[str] = {key for key, _ in RENDER_BACKEND_PROFILES}
RENDER_BACKEND_LABELS: dict[str, str] = dict(RENDER_BACKEND_PROFILES)


def normalize_render_backend(value: Any) -> str:
    """Normaliza el perfil de backend de renderizado ('auto', 'gpu' o 'software')."""
    raw = str(value or "").strip().lower()
    if not raw:
        return "auto"
    if raw in VALID_RENDER_BACKENDS:
        return raw
    if raw in ("opengl", "gl", "hardware", "hw"):
        return "gpu"
    if raw in ("cpu", "qpainter", "sw", "off"):
        return "software"
    if raw in _RENDER_BACKEND_ALIASES:
        return _RENDER_BACKEND_ALIASES[raw]
    for key, label in get_render_backend_profiles():
        if raw == label.strip().lower():
            return key
    return "auto"


def is_offscreen_qt_platform() -> bool:
    """Detecta plataformas Qt headless donde QOpenGLWidget no tiene swapchain nativo."""
    app = QCoreApplication.instance()
    if app is not None:
        try:
            pname = str(app.platformName() or "").strip().lower()
            if pname in ("offscreen", "minimal", "vnc"):
                return True
        except Exception:
            pass
    return str(os.environ.get("QT_QPA_PLATFORM", "")).strip().lower() in (
        "offscreen",
        "minimal",
        "vnc",
    )


def is_gpu_rendering_permitted(backend: str | None = None) -> bool:
    """Indica si el backend actual permite intentar aceleración GPU en widget."""
    norm = normalize_render_backend(backend)
    if norm == "software":
        return False
    if is_offscreen_qt_platform():
        return False
    return True


# ---------------------------------------------------------------------------
# Shaders GLSL del compositor (compatibles con OpenGL 2.1+ y GLES 2.0/ANGLE)
# ---------------------------------------------------------------------------

# Cuadrado unitario en orden GL_TRIANGLE_STRIP: TL -> TR -> BL -> BR
_UNIT_QUAD_DATA = struct.pack(
    "8f",
    0.0, 0.0,
    1.0, 0.0,
    0.0, 1.0,
    1.0, 1.0,
)

_PROJECTIVE_VERTEX_SHADER = """
attribute vec2 a_uv;
varying vec2 v_uv;
uniform vec3 u_col0;
uniform vec3 u_col1;
uniform vec3 u_col2;
uniform float u_flip_v;
void main() {
    vec3 res = u_col0 * a_uv.x + u_col1 * a_uv.y + u_col2;
    if (res.z < 0.0) {
        res = -res;
    }
    gl_Position = vec4(res.x, res.y, 0.0, max(res.z, 0.0001));
    v_uv = vec2(a_uv.x, u_flip_v > 0.5 ? (1.0 - a_uv.y) : a_uv.y);
}
"""

_FRAG_SOLID = """
uniform vec4 u_color;
void main() {
    gl_FragColor = u_color;
}
"""

_FRAG_SPRITE = """
uniform sampler2D u_tex;
uniform float u_opacity;
varying vec2 v_uv;
void main() {
    vec4 c = texture2D(u_tex, v_uv);
    gl_FragColor = c * clamp(u_opacity, 0.0, 1.0);
}
"""

_FRAG_VIDEO_RGBA = """
uniform sampler2D u_tex;
uniform float u_opacity;
uniform float u_swap_rb;
uniform float u_force_opaque;
varying vec2 v_uv;
void main() {
    vec4 c = texture2D(u_tex, v_uv);
    vec3 rgb = u_swap_rb > 0.5 ? c.bgr : c.rgb;
    float src_a = u_force_opaque > 0.5 ? 1.0 : c.a;
    float out_a = src_a * clamp(u_opacity, 0.0, 1.0);
    gl_FragColor = vec4(rgb * out_a, out_a);
}
"""

_FRAG_VIDEO_NV12 = """
uniform sampler2D u_tex_y;
uniform sampler2D u_tex_uv;
uniform float u_opacity;
uniform float u_swap_uv;
varying vec2 v_uv;
void main() {
    float y = (texture2D(u_tex_y, v_uv).r - 0.0627451) * 1.16438356;
    vec2 uv_s = texture2D(u_tex_uv, v_uv).rg;
    float u = (u_swap_uv > 0.5 ? uv_s.y : uv_s.x) - 0.5;
    float v = (u_swap_uv > 0.5 ? uv_s.x : uv_s.y) - 0.5;
    vec3 rgb = clamp(vec3(
        y + 1.59602678 * v,
        y - 0.39176229 * u - 0.81296765 * v,
        y + 2.01723214 * u
    ), 0.0, 1.0);
    float a = clamp(u_opacity, 0.0, 1.0);
    gl_FragColor = vec4(rgb * a, a);
}
"""

_FRAG_VIDEO_YUV420P = """
uniform sampler2D u_tex_y;
uniform sampler2D u_tex_u;
uniform sampler2D u_tex_v;
uniform float u_opacity;
varying vec2 v_uv;
void main() {
    float y = (texture2D(u_tex_y, v_uv).r - 0.0627451) * 1.16438356;
    float u = texture2D(u_tex_u, v_uv).r - 0.5;
    float v = texture2D(u_tex_v, v_uv).r - 0.5;
    vec3 rgb = clamp(vec3(
        y + 1.59602678 * v,
        y - 0.39176229 * u - 0.81296765 * v,
        y + 2.01723214 * u
    ), 0.0, 1.0);
    float a = clamp(u_opacity, 0.0, 1.0);
    gl_FragColor = vec4(rgb * a, a);
}
"""

# Mapeo de formatos de QVideoFrame -> descriptor compacto de subida GPU
_PF = QVideoFrameFormat.PixelFormat
_RGB_PIXEL_FORMATS: dict[Any, tuple[bool, bool]] = {}
for _fmt_name, _swap_rb, _force_opaque in (
    ("Format_RGBA8888", False, False),
    ("Format_RGBA8888_Premultiplied", False, False),
    ("Format_RGBX8888", False, True),
    ("Format_BGRA8888", True, False),
    ("Format_BGRA8888_Premultiplied", True, False),
    ("Format_BGRX8888", True, True),
):
    _fmt_val = getattr(_PF, _fmt_name, None)
    if _fmt_val is not None:
        _RGB_PIXEL_FORMATS[_fmt_val] = (_swap_rb, _force_opaque)


# ---------------------------------------------------------------------------
# Utilidades geométricas de proyección
# ---------------------------------------------------------------------------


def _set_uniform(prog: QOpenGLShaderProgram, name: str, *values: Any) -> None:
    """Establece un uniforme GLSL resolviendo su ubicación entera (compatible PySide6 6.x)."""
    cache = getattr(prog, "_pn_ulocs", None)
    if cache is None:
        cache = {}
        setattr(prog, "_pn_ulocs", cache)
    loc = cache.get(name)
    if loc is None:
        loc = int(prog.uniformLocation(name))
        cache[name] = loc
    if loc < 0:
        return
    n = len(values)
    if n == 1:
        v = values[0]
        if isinstance(v, int) and not isinstance(v, bool):
            prog.setUniformValue1i(loc, v)
        else:
            prog.setUniformValue1f(loc, float(v))
    elif n == 2:
        prog.setUniformValue(loc, float(values[0]), float(values[1]))
    elif n == 3:
        prog.setUniformValue(loc, float(values[0]), float(values[1]), float(values[2]))
    elif n == 4:
        prog.setUniformValue(loc, float(values[0]), float(values[1]), float(values[2]), float(values[3]))


def pixels_to_ndc(px: float, py: float, viewport_w: float, viewport_h: float) -> tuple[float, float]:
    """Convierte píxeles lógicos (arriba-izquierda = 0,0) a NDC OpenGL (-1..+1)."""
    vw = max(1.0, float(viewport_w))
    vh = max(1.0, float(viewport_h))
    return (2.0 * (float(px) / vw) - 1.0, 1.0 - 2.0 * (float(py) / vh))


def compute_quad_homography(
    dst_ndc_points: list[tuple[float, float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    """Calcula la homografía 3x3 (u,v,1)->(x',y',w') en formato 3 columnas vec3."""
    if len(dst_ndc_points) != 4:
        return (2.0, 0.0, 0.0), (0.0, -2.0, 0.0), (-1.0, 1.0, 1.0)

    src_poly = QPolygonF([
        QPointF(0.0, 0.0),
        QPointF(1.0, 0.0),
        QPointF(1.0, 1.0),
        QPointF(0.0, 1.0),
    ])
    dst_poly = QPolygonF([QPointF(float(x), float(y)) for x, y in dst_ndc_points])
    trans = QTransform()
    if not QTransform.quadToQuad(src_poly, dst_poly, trans):
        return (2.0, 0.0, 0.0), (0.0, -2.0, 0.0), (-1.0, 1.0, 1.0)

    col0 = (float(trans.m11()), float(trans.m12()), float(trans.m13()))
    col1 = (float(trans.m21()), float(trans.m22()), float(trans.m23()))
    col2 = (float(trans.m31()), float(trans.m32()), float(trans.m33()))
    return col0, col1, col2


def build_rect_ndc_points(
    x: float,
    y: float,
    w: float,
    h: float,
    viewport_w: float,
    viewport_h: float,
    rotation_deg: float = 0.0,
) -> list[tuple[float, float]]:
    """Genera los 4 vértices TL, TR, BR, BL en NDC aplicando rotación alrededor del centro."""
    corners = [
        (float(x), float(y)),
        (float(x + w), float(y)),
        (float(x + w), float(y + h)),
        (float(x), float(y + h)),
    ]
    if abs(float(rotation_deg)) > 1e-4:
        cx = x + w / 2.0
        cy = y + h / 2.0
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(float(rotation_deg))
        t.translate(-cx, -cy)
        rotated: list[tuple[float, float]] = []
        for px, py in corners:
            pt = t.map(QPointF(px, py))
            rotated.append((pt.x(), pt.y()))
        corners = rotated
    return [pixels_to_ndc(px, py, viewport_w, viewport_h) for px, py in corners]


# ---------------------------------------------------------------------------
# Caché de texturas residentes en VRAM
# ---------------------------------------------------------------------------


def _image_to_premultiplied_rgba(src: QPixmap | QImage | None) -> QImage | None:
    if src is None or src.isNull():
        return None
    img = src.toImage() if isinstance(src, QPixmap) else src
    if img.isNull():
        return None
    if img.format() != QImage.Format.Format_RGBA8888_Premultiplied:
        img = img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
    return img


def _upload_premultiplied_level0(tex: QOpenGLTexture, img: QImage) -> None:
    """Sube bytes RGBA premultiplicados sin alterar al nivel base de la textura."""
    upload_img = img if (img.bytesPerLine() % 4 == 0) else img.copy()
    pto = QOpenGLPixelTransferOptions()
    pto.setAlignment(4)
    pto.setRowLength(max(upload_img.width(), upload_img.bytesPerLine() // 4))
    tex.setData(
        0,
        QOpenGLTexture.PixelFormat.RGBA,
        QOpenGLTexture.PixelType.UInt8,
        upload_img.constBits(),
        pto,
    )


def _is_qt_valid(obj: Any) -> bool:
    """Devuelve True si el objeto Python/Shiboken sigue teniendo instancia C++ válida."""
    if obj is None:
        return False
    if shiboken6 is not None:
        try:
            return bool(shiboken6.isValid(obj))
        except Exception:
            return False
    return True


def _contexts_compatible(owner_ctx: QOpenGLContext | None, cur_ctx: QOpenGLContext | None) -> bool:
    """Indica si `cur_ctx` puede destruir recursos creados en `owner_ctx` sin warnings."""
    if cur_ctx is None or not _is_qt_valid(cur_ctx):
        return False
    if owner_ctx is None:
        return True
    if not _is_qt_valid(owner_ctx):
        return False
    if cur_ctx is owner_ctx:
        return True
    try:
        return bool(QOpenGLContext.areSharing(owner_ctx, cur_ctx))
    except Exception:
        return False


def _ctx_make_current_safe(ctx: QOpenGLContext | None) -> tuple[QOpenGLContext | None, Any, bool]:
    """Activa temporalmente `ctx` si no comparte con el contexto actual."""
    if ctx is None or not _is_qt_valid(ctx):
        return None, None, False
    try:
        if not ctx.isValid():
            return None, None, False
        cur = QOpenGLContext.currentContext()
        if _contexts_compatible(ctx, cur):
            return cur, None, False
        surf = ctx.surface()
        if surf is None:
            return cur, None, False
        prev_surf = cur.surface() if (cur is not None and _is_qt_valid(cur)) else None
        if ctx.makeCurrent(surf):
            return cur, prev_surf, True
    except Exception:
        pass
    return None, None, False


def _restore_ctx_safe(
    owner_ctx: QOpenGLContext | None,
    prev_ctx: QOpenGLContext | None,
    prev_surf: Any,
    switched: bool,
) -> None:
    if not switched:
        return
    try:
        if (
            prev_ctx is not None
            and prev_surf is not None
            and _is_qt_valid(prev_ctx)
            and prev_ctx.isValid()
            and prev_ctx.makeCurrent(prev_surf)
        ):
            return
        if _is_qt_valid(owner_ctx):
            owner_ctx.doneCurrent()
    except Exception:
        pass


def _destroy_gl_texture_safe(
    tex: QOpenGLTexture | None,
    owner_ctx: QOpenGLContext | None = None,
) -> None:
    """Destruye un `QOpenGLTexture` únicamente en su contexto dueño o uno compartido."""
    if not _is_qt_valid(tex):
        return
    try:
        if not tex.isCreated():
            return
    except Exception:
        return

    target_ctx = owner_ctx if _is_qt_valid(owner_ctx) else QOpenGLContext.currentContext()
    prev_ctx, prev_surf, switched = _ctx_make_current_safe(target_ctx)
    try:
        cur = QOpenGLContext.currentContext()
        if _contexts_compatible(owner_ctx, cur):
            tex.destroy()
    except Exception:
        pass
    finally:
        _restore_ctx_safe(target_ctx, prev_ctx, prev_surf, switched)


class _AncestorGlCleanupFilter(QObject):
    """Captura `DeferredDelete`, `Close` y `WinIdChange` del padre/ventana antes de `~QOpenGLWidget`."""

    def __init__(self, viewport: Any) -> None:
        super().__init__(viewport)
        self._vp_ref = weakref.ref(viewport)
        self._watched: weakref.WeakSet[QObject] = weakref.WeakSet()

    def watch(self, target: QObject | None) -> None:
        if not _is_qt_valid(target) or target in self._watched:
            return
        try:
            target.installEventFilter(self)
            self._watched.add(target)
        except Exception:
            pass

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        ev_type = event.type()
        if ev_type in (
            QEvent.Type.DeferredDelete,
            QEvent.Type.Close,
            QEvent.Type.WinIdChange,
        ):
            vp = self._vp_ref()
            if vp is not None and _is_qt_valid(vp):
                try:
                    if ev_type == QEvent.Type.WinIdChange:
                        vp.release_gl_textures()
                    else:
                        vp.cleanup_gl()
                except Exception:
                    pass
        return False


def _install_ctx_destroy_hook(
    ctx: QOpenGLContext | None,
    pipeline: Any,
) -> None:
    """Conecta `ctx.aboutToBeDestroyed` sin depender del wrapper C++ del `QOpenGLWidget`.

    Cuando Qt destruye un widget padre o `deleteLater()`, el `QOpenGLWidget` puede
    marcarse como eliminado en Shiboken antes de emitirse `ctx.aboutToBeDestroyed`.
    Reteniendo temporalmente solo `pipeline` (soltado tras ejecutarse) y `ctx` en
    referencia débil garantizamos que las texturas no mueran en GC fuera de contexto.
    """
    if not _is_qt_valid(ctx) or pipeline is None:
        return
    if getattr(ctx, "_pn_destroy_hook_installed", False):
        return
    ctx_ref = weakref.ref(ctx)
    pipe_holder: list[Any] = [pipeline]

    def _on_ctx_about_to_be_destroyed() -> None:
        if not pipe_holder:
            return
        pipe = pipe_holder[0]
        pipe_holder.clear()
        c = ctx_ref()
        temp_offscreen = None
        prev_ctx = None
        prev_surf = None
        switched = False
        try:
            if _is_qt_valid(c) and c.isValid():
                cur = QOpenGLContext.currentContext()
                if not _contexts_compatible(c, cur):
                    prev_ctx = cur
                    prev_surf = cur.surface() if _is_qt_valid(cur) else None
                    surf = c.surface()
                    if surf is not None:
                        switched = bool(c.makeCurrent(surf))
                    else:
                        try:
                            temp_offscreen = QOffscreenSurface(c.screen())
                            temp_offscreen.setFormat(c.format())
                            temp_offscreen.create()
                            if temp_offscreen.isValid():
                                switched = bool(c.makeCurrent(temp_offscreen))
                        except Exception:
                            temp_offscreen = None
            pipe.cleanup()
        except Exception:
            pass
        finally:
            if switched and _is_qt_valid(c):
                _restore_ctx_safe(c, prev_ctx, prev_surf, True)
            if temp_offscreen is not None:
                try:
                    temp_offscreen.destroy()
                except Exception:
                    pass

    try:
        ctx.aboutToBeDestroyed.connect(_on_ctx_about_to_be_destroyed)
        setattr(ctx, "_pn_destroy_hook_installed", True)
        setattr(pipeline, "_ctx_destroy_cb", _on_ctx_about_to_be_destroyed)
    except Exception:
        pipe_holder.clear()


class GpuTextureCache:
    """Caché LRU de `QOpenGLTexture` residentes en VRAM ligado a un contexto OpenGL."""

    def __init__(self, max_entries: int = 128) -> None:
        self._max_entries = max(16, int(max_entries))
        self._textures: OrderedDict[Any, QOpenGLTexture] = OrderedDict()
        self._dynamic_revs: dict[Any, int] = {}
        self._owner_ctx_ref: weakref.ref[QOpenGLContext] | None = None

    def set_owner_context(self, ctx: QOpenGLContext | None) -> None:
        """Asocia el caché al `QOpenGLContext` dueño y limpia entradas si cambió."""
        prev = self._owner_ctx_ref() if self._owner_ctx_ref is not None else None
        if prev is not None and ctx is not None and not _contexts_compatible(prev, ctx):
            self.clear()
        self._owner_ctx_ref = weakref.ref(ctx) if _is_qt_valid(ctx) else None

    def _get_owner_context(self) -> QOpenGLContext | None:
        return self._owner_ctx_ref() if self._owner_ctx_ref is not None else None

    def __len__(self) -> int:
        return len(self._textures)

    def _evict_overflow(self) -> None:
        owner_ctx = self._get_owner_context()
        while len(self._textures) > self._max_entries:
            old_key, old_tex = self._textures.popitem(last=False)
            self._dynamic_revs.pop(old_key, None)
            _destroy_gl_texture_safe(old_tex, owner_ctx)

    def get_or_upload(
        self,
        key: Any,
        source: QPixmap | QImage | None,
        *,
        linear: bool = True,
        mipmaps: bool = True,
    ) -> QOpenGLTexture | None:
        """Devuelve la textura GL en VRAM o la sube preservando alfa premultiplicado."""
        cur_ctx = QOpenGLContext.currentContext()
        if cur_ctx is not None:
            if self._owner_ctx_ref is None:
                self._owner_ctx_ref = weakref.ref(cur_ctx)
            else:
                owner_ctx = self._get_owner_context()
                if owner_ctx is not None and not _contexts_compatible(owner_ctx, cur_ctx):
                    self.clear()
                    self._owner_ctx_ref = weakref.ref(cur_ctx)

        tex = self._textures.get(key)
        if tex is not None and tex.isCreated():
            self._textures.move_to_end(key)
            return tex

        img = _image_to_premultiplied_rgba(source)
        if img is None or img.isNull():
            return None

        # Usar Target2D + setData directo porque QOpenGLTexture(QImage) des-premultiplica el RGB
        tex = QOpenGLTexture(QOpenGLTexture.Target.Target2D)
        tex.setFormat(QOpenGLTexture.TextureFormat.RGBA8_UNorm)
        tex.setSize(img.width(), img.height())
        use_mipmaps = bool(mipmaps and linear and tex.maximumMipLevels() > 1)
        tex.setMipLevels(tex.maximumMipLevels() if use_mipmaps else 1)
        tex.setAutoMipMapGenerationEnabled(False)
        tex.allocateStorage()
        if not tex.isCreated():
            return None

        _upload_premultiplied_level0(tex, img)
        if use_mipmaps:
            tex.generateMipMaps()
            tex.setMinificationFilter(QOpenGLTexture.Filter.LinearMipMapLinear)
            tex.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
            try:
                tex.setLevelofDetailBias(-0.75)
            except Exception:
                pass
        else:
            filt = QOpenGLTexture.Filter.Linear if linear else QOpenGLTexture.Filter.Nearest
            tex.setMinMagFilters(filt, filt)
        tex.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)

        self._textures[key] = tex
        self._textures.move_to_end(key)
        self._evict_overflow()
        return tex

    def update_or_upload(
        self,
        key: Any,
        source: QPixmap | QImage | None,
        rev: int,
        *,
        linear: bool = True,
    ) -> QOpenGLTexture | None:
        """Reutiliza in-place la textura VRAM de capas dinámicas cuando el tamaño coincide."""
        tex = self._textures.get(key)
        if tex is not None and tex.isCreated():
            if self._dynamic_revs.get(key) == rev:
                self._textures.move_to_end(key)
                return tex
            img = _image_to_premultiplied_rgba(source)
            if img is None or img.isNull():
                return None
            if tex.width() == img.width() and tex.height() == img.height():
                _upload_premultiplied_level0(tex, img)
                if tex.mipLevels() > 1:
                    tex.generateMipMaps()
                self._dynamic_revs[key] = rev
                self._textures.move_to_end(key)
                return tex
            # Si cambiaron dimensiones, destruir textura vieja y crear nueva
            self._textures.pop(key, None)
            self._dynamic_revs.pop(key, None)
            _destroy_gl_texture_safe(tex, self._get_owner_context())
            tex = self.get_or_upload(key, img, linear=linear, mipmaps=False)
            if tex is not None:
                self._dynamic_revs[key] = rev
            return tex

        tex = self.get_or_upload(key, source, linear=linear, mipmaps=False)
        if tex is not None:
            self._dynamic_revs[key] = rev
        return tex

    def clear(self) -> None:
        """Libera todas las texturas GL almacenadas (debe llamarse con contexto activo)."""
        owner_ctx = self._get_owner_context()
        textures = list(self._textures.values())
        self._textures.clear()
        self._dynamic_revs.clear()
        for tex in textures:
            _destroy_gl_texture_safe(tex, owner_ctx)


# ---------------------------------------------------------------------------
# Superficie de video directa (Zero-toImage para NV12 / YUV420P / BGRA)
# ---------------------------------------------------------------------------


def _tighten_plane_bytes(mv: memoryview, bytes_per_line: int, row_bytes: int, height: int) -> bytes:
    """Compacta filas cuando el stride tiene relleno no divisible por bytes por píxel."""
    if bytes_per_line == row_bytes:
        return bytes(mv[: row_bytes * height])
    out = bytearray(row_bytes * height)
    for row in range(height):
        src_off = row * bytes_per_line
        dst_off = row * row_bytes
        out[dst_off : dst_off + row_bytes] = mv[src_off : src_off + row_bytes]
    return bytes(out)


class GpuVideoSurface:
    """Recibe `QVideoFrame` sin convertir a CPU y sube sus planos crudos a VRAM."""

    def __init__(self) -> None:
        self._pending_frame: QVideoFrame | None = None
        self._dirty: bool = False
        self._has_video: bool = False
        self._mode: str = "none"  # "nv12" | "yuv420p" | "rgba"
        self._swap_uv: bool = False
        self._swap_rb: bool = False
        self._force_opaque: bool = True
        self._video_size: tuple[int, int] = (0, 0)
        self._tex_planes: list[QOpenGLTexture] = []
        self._plane_dims: list[tuple[int, int, Any]] = []
        self._fallback_conversions: int = 0
        self._direct_uploads: int = 0

    @property
    def has_video(self) -> bool:
        return self._has_video or (self._pending_frame is not None and self._pending_frame.isValid())

    @property
    def video_size(self) -> tuple[int, int]:
        return self._video_size

    @property
    def direct_uploads(self) -> int:
        return self._direct_uploads

    @property
    def fallback_conversions(self) -> int:
        return self._fallback_conversions

    def set_frame(self, frame: QVideoFrame | None) -> bool:
        """Almacena el último `QVideoFrame` sin ejecutar conversión en CPU."""
        if frame is None or not frame.isValid():
            return False
        self._pending_frame = QVideoFrame(frame)
        self._video_size = (max(0, int(frame.width())), max(0, int(frame.height())))
        self._dirty = True
        self._has_video = True
        return True

    def clear(self) -> None:
        """Limpia el estado actual de video (sin destruir texturas si no hay contexto GL)."""
        self._pending_frame = None
        self._dirty = False
        self._has_video = False

    def destroy_gl(self) -> None:
        """Destruye texturas OpenGL asociadas (requiere contexto GL actual)."""
        for tex in self._tex_planes:
            try:
                if tex.isCreated():
                    tex.destroy()
            except Exception:
                pass
        self._tex_planes.clear()
        self._plane_dims.clear()
        self._has_video = False

    def _ensure_plane_textures(self, specs: list[tuple[int, int, Any, Any]]) -> bool:
        """Crea o reutiliza las texturas por plano si coinciden dimensiones y formato."""
        dims_sig = [(w, h, tfmt) for (w, h, tfmt, _pfmt) in specs]
        if len(self._tex_planes) == len(specs) and self._plane_dims == dims_sig:
            if all(t.isCreated() for t in self._tex_planes):
                return True

        for tex in self._tex_planes:
            try:
                if tex.isCreated():
                    tex.destroy()
            except Exception:
                pass
        self._tex_planes.clear()
        self._plane_dims.clear()

        for w, h, tfmt, pfmt in specs:
            tex = QOpenGLTexture(QOpenGLTexture.Target.Target2D)
            tex.setSize(max(1, int(w)), max(1, int(h)))
            tex.setFormat(tfmt)
            tex.setMinMagFilters(QOpenGLTexture.Filter.Linear, QOpenGLTexture.Filter.Linear)
            tex.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
            tex.allocateStorage(pfmt, QOpenGLTexture.PixelType.UInt8)
            if not tex.isCreated():
                return False
            self._tex_planes.append(tex)
        self._plane_dims = dims_sig
        return True

    @staticmethod
    def _upload_plane(
        tex: QOpenGLTexture,
        pixel_fmt: Any,
        plane_bits: Any,
        width: int,
        height: int,
        bytes_per_line: int,
        bytes_per_pixel: int,
    ) -> None:
        row_bytes = width * bytes_per_pixel
        pto = QOpenGLPixelTransferOptions()
        pto.setAlignment(1)
        if bytes_per_line >= row_bytes and bytes_per_line % bytes_per_pixel == 0:
            pto.setRowLength(bytes_per_line // bytes_per_pixel)
            tex.setData(pixel_fmt, QOpenGLTexture.PixelType.UInt8, plane_bits, pto)
        else:
            tight = _tighten_plane_bytes(memoryview(plane_bits), bytes_per_line, row_bytes, height)
            pto.setRowLength(width)
            tex.setData(pixel_fmt, QOpenGLTexture.PixelType.UInt8, tight, pto)

    def sync_to_gpu(self) -> bool:
        """Sube el frame pendiente a texturas OpenGL (llamar solo dentro del contexto GL activo)."""
        if not self._dirty or self._pending_frame is None:
            return self._has_video and bool(self._tex_planes)

        frame = self._pending_frame
        self._dirty = False
        if not frame.isValid():
            return False

        w = int(frame.width())
        h = int(frame.height())
        if w <= 0 or h <= 0:
            return False

        pfmt = frame.pixelFormat()
        mapped = frame.map(QVideoFrame.MapMode.ReadOnly)
        if not mapped:
            return self._has_video and bool(self._tex_planes)

        try:
            planes = int(frame.planeCount())
            if pfmt in (_PF.Format_NV12, _PF.Format_NV21) and planes >= 2:
                uv_w = max(1, (w + 1) // 2)
                uv_h = max(1, (h + 1) // 2)
                specs = [
                    (w, h, QOpenGLTexture.TextureFormat.R8_UNorm, QOpenGLTexture.PixelFormat.Red),
                    (uv_w, uv_h, QOpenGLTexture.TextureFormat.RG8_UNorm, QOpenGLTexture.PixelFormat.RG),
                ]
                if not self._ensure_plane_textures(specs):
                    return False
                self._upload_plane(
                    self._tex_planes[0],
                    QOpenGLTexture.PixelFormat.Red,
                    frame.bits(0),
                    w,
                    h,
                    int(frame.bytesPerLine(0)),
                    1,
                )
                self._upload_plane(
                    self._tex_planes[1],
                    QOpenGLTexture.PixelFormat.RG,
                    frame.bits(1),
                    uv_w,
                    uv_h,
                    int(frame.bytesPerLine(1)),
                    2,
                )
                self._mode = "nv12"
                self._swap_uv = (pfmt == _PF.Format_NV21)
                self._video_size = (w, h)
                self._direct_uploads += 1
                self._has_video = True
                return True

            if pfmt in (_PF.Format_YUV420P, _PF.Format_YV12) and planes >= 3:
                uv_w = max(1, (w + 1) // 2)
                uv_h = max(1, (h + 1) // 2)
                specs = [
                    (w, h, QOpenGLTexture.TextureFormat.R8_UNorm, QOpenGLTexture.PixelFormat.Red),
                    (uv_w, uv_h, QOpenGLTexture.TextureFormat.R8_UNorm, QOpenGLTexture.PixelFormat.Red),
                    (uv_w, uv_h, QOpenGLTexture.TextureFormat.R8_UNorm, QOpenGLTexture.PixelFormat.Red),
                ]
                if not self._ensure_plane_textures(specs):
                    return False
                u_idx, v_idx = (2, 1) if pfmt == _PF.Format_YV12 else (1, 2)
                self._upload_plane(self._tex_planes[0], QOpenGLTexture.PixelFormat.Red, frame.bits(0), w, h, int(frame.bytesPerLine(0)), 1)
                self._upload_plane(self._tex_planes[1], QOpenGLTexture.PixelFormat.Red, frame.bits(u_idx), uv_w, uv_h, int(frame.bytesPerLine(u_idx)), 1)
                self._upload_plane(self._tex_planes[2], QOpenGLTexture.PixelFormat.Red, frame.bits(v_idx), uv_w, uv_h, int(frame.bytesPerLine(v_idx)), 1)
                self._mode = "yuv420p"
                self._video_size = (w, h)
                self._direct_uploads += 1
                self._has_video = True
                return True

            if pfmt in _RGB_PIXEL_FORMATS and planes >= 1:
                swap_rb, force_opaque = _RGB_PIXEL_FORMATS[pfmt]
                specs = [
                    (w, h, QOpenGLTexture.TextureFormat.RGBA8_UNorm, QOpenGLTexture.PixelFormat.RGBA),
                ]
                if not self._ensure_plane_textures(specs):
                    return False
                self._upload_plane(
                    self._tex_planes[0],
                    QOpenGLTexture.PixelFormat.RGBA,
                    frame.bits(0),
                    w,
                    h,
                    int(frame.bytesPerLine(0)),
                    4,
                )
                self._mode = "rgba"
                self._swap_rb = swap_rb
                self._force_opaque = force_opaque
                self._video_size = (w, h)
                self._direct_uploads += 1
                self._has_video = True
                return True
        finally:
            frame.unmap()

        # Fallback seguro solo si el decodificador entrega un formato poco común
        img = frame.toImage()
        if img.isNull():
            return False
        if img.format() != QImage.Format.Format_RGBA8888:
            img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        specs = [(img.width(), img.height(), QOpenGLTexture.TextureFormat.RGBA8_UNorm, QOpenGLTexture.PixelFormat.RGBA)]
        if not self._ensure_plane_textures(specs):
            return False
        self._upload_plane(
            self._tex_planes[0],
            QOpenGLTexture.PixelFormat.RGBA,
            img.constBits(),
            img.width(),
            img.height(),
            img.bytesPerLine(),
            4,
        )
        self._mode = "rgba"
        self._swap_rb = False
        self._force_opaque = True
        self._video_size = (img.width(), img.height())
        self._fallback_conversions += 1
        self._has_video = True
        return True

    def bind_to_program(self, gl_funcs: Any, prog: QOpenGLShaderProgram) -> str | None:
        """Enlaza los samplers activos en el programa shader y retorna el modo ('nv12'|'yuv420p'|'rgba')."""
        if not self.sync_to_gpu() or not self._tex_planes:
            return None

        if self._mode == "nv12" and len(self._tex_planes) >= 2:
            gl_funcs.glActiveTexture(0x84C0)  # GL_TEXTURE0
            self._tex_planes[0].bind()
            _set_uniform(prog, "u_tex_y", 0)
            gl_funcs.glActiveTexture(0x84C1)  # GL_TEXTURE1
            self._tex_planes[1].bind()
            _set_uniform(prog, "u_tex_uv", 1)
            _set_uniform(prog, "u_swap_uv", 1.0 if self._swap_uv else 0.0)
            return "nv12"

        if self._mode == "yuv420p" and len(self._tex_planes) >= 3:
            gl_funcs.glActiveTexture(0x84C0)
            self._tex_planes[0].bind()
            _set_uniform(prog, "u_tex_y", 0)
            gl_funcs.glActiveTexture(0x84C1)
            self._tex_planes[1].bind()
            _set_uniform(prog, "u_tex_u", 1)
            gl_funcs.glActiveTexture(0x84C2)
            self._tex_planes[2].bind()
            _set_uniform(prog, "u_tex_v", 2)
            return "yuv420p"

        gl_funcs.glActiveTexture(0x84C0)
        self._tex_planes[0].bind()
        _set_uniform(prog, "u_tex", 0)
        _set_uniform(prog, "u_swap_rb", 1.0 if self._swap_rb else 0.0)
        _set_uniform(prog, "u_force_opaque", 1.0 if self._force_opaque else 0.0)
        return "rgba"


# ---------------------------------------------------------------------------
# Primitiva declarativa de capa GPU y compositor OpenGL
# ---------------------------------------------------------------------------


@dataclass
class GpuQuadCommand:
    """Comando de dibujo de una capa individual para el frame actual."""

    kind: str  # "pixmap" | "video" | "solid"
    dst_ndc_pts: list[tuple[float, float]]
    opacity: float = 1.0
    tex_key: Any = None
    pixmap: QPixmap | QImage | None = None
    video_surface: GpuVideoSurface | None = None
    color: QColor | None = None
    shader_preset: str = "none"
    shader_elapsed: float = 0.0
    target_px: tuple[int, int] = (0, 0)
    fill_color: QColor | None = None
    dynamic_rev: int | None = None


class GpuQuadPipeline:
    """Motor OpenGL reutilizable (apto para `QOpenGLWidget` y `QOffscreenSurface`)."""

    def __init__(self, parent_qobject: Any = None) -> None:
        self._parent = parent_qobject
        self._ready: bool = False
        self._error: str = ""
        self._programs: dict[str, QOpenGLShaderProgram] = {}
        self._vbo: QOpenGLBuffer | None = None
        self._fbos: dict[tuple[str, int, int], QOpenGLFramebufferObject] = {}
        self.texture_cache = GpuTextureCache(max_entries=144)

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def last_error(self) -> str:
        return self._error

    def _compile_prog(self, frag_src: str) -> QOpenGLShaderProgram:
        prog = QOpenGLShaderProgram(self._parent)
        if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, _PROJECTIVE_VERTEX_SHADER):
            raise RuntimeError(f"VS: {prog.log()}")
        if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag_src):
            raise RuntimeError(f"FS: {prog.log()}")
        if not prog.link():
            raise RuntimeError(f"Link: {prog.log()}")
        return prog

    def initialize(self) -> bool:
        if self._ready:
            return True
        try:
            progs: dict[str, QOpenGLShaderProgram] = {
                "solid": self._compile_prog(_FRAG_SOLID),
                "sprite": self._compile_prog(_FRAG_SPRITE),
                "video_rgba": self._compile_prog(_FRAG_VIDEO_RGBA),
                "video_nv12": self._compile_prog(_FRAG_VIDEO_NV12),
                "video_yuv420p": self._compile_prog(_FRAG_VIDEO_YUV420P),
            }
            for preset_id, frag_src in _FRAGMENT_SHADERS.items():
                progs[f"fx:{preset_id}"] = self._compile_prog(frag_src)

            vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            if not vbo.create():
                raise RuntimeError("No se pudo crear VBO GPU")
            vbo.bind()
            vbo.allocate(_UNIT_QUAD_DATA, len(_UNIT_QUAD_DATA))
            vbo.release()

            self._programs = progs
            self._vbo = vbo
            self._ready = True
            self._error = ""
            return True
        except Exception as exc:
            self._ready = False
            self._error = str(exc)
            return False

    def track_video_surface(self, surf: GpuVideoSurface | None) -> None:
        """Registra una superficie de video para destruir sus planos GL al limpiar el pipeline."""
        if surf is None:
            return
        tracked = getattr(self, "_tracked_surfaces", None)
        if tracked is None:
            tracked = weakref.WeakSet()
            self._tracked_surfaces = tracked
        try:
            tracked.add(surf)
        except Exception:
            pass

    def cleanup(self) -> None:
        tracked = getattr(self, "_tracked_surfaces", None)
        if tracked is not None:
            for surf in list(tracked):
                try:
                    surf.destroy_gl()
                except Exception:
                    pass
        self.texture_cache.clear()
        self._fbos.clear()
        if _is_qt_valid(self._vbo):
            try:
                self._vbo.destroy()
            except Exception:
                pass
        self._vbo = None
        for prog in self._programs.values():
            if _is_qt_valid(prog):
                try:
                    prog.removeAllShaders()
                except Exception:
                    pass
        self._programs.clear()
        self._ready = False

    def _get_fbo(self, slot_key: str, w: int, h: int) -> QOpenGLFramebufferObject:
        rw = max(16, min(4096, int(w)))
        rh = max(16, min(4096, int(h)))
        key = (slot_key, rw, rh)
        fbo = self._fbos.get(key)
        if fbo is None or not fbo.isValid():
            # Mantener acotada la cantidad de FBOs por slot
            stale = [k for k in self._fbos if k[0] == slot_key]
            for sk in stale:
                self._fbos.pop(sk, None)
            fmt = QOpenGLFramebufferObjectFormat()
            fmt.setAttachment(QOpenGLFramebufferObject.Attachment.NoAttachment)
            fbo = QOpenGLFramebufferObject(rw, rh, fmt)
            self._fbos[key] = fbo
        return fbo

    def _bind_quad_geometry(
        self,
        prog: QOpenGLShaderProgram,
        col0: tuple[float, float, float],
        col1: tuple[float, float, float],
        col2: tuple[float, float, float],
        *,
        flip_v: bool = False,
    ) -> int:
        assert self._vbo is not None
        self._vbo.bind()
        uv_loc = prog.attributeLocation("a_uv")
        prog.enableAttributeArray(uv_loc)
        prog.setAttributeBuffer(uv_loc, 0x1406, 0, 2, 8)  # GL_FLOAT
        _set_uniform(prog, "u_col0", col0[0], col0[1], col0[2])
        _set_uniform(prog, "u_col1", col1[0], col1[1], col1[2])
        _set_uniform(prog, "u_col2", col2[0], col2[1], col2[2])
        _set_uniform(prog, "u_flip_v", 1.0 if flip_v else 0.0)
        return uv_loc

    def _draw_bound_quad(self, gl_funcs: Any, prog: QOpenGLShaderProgram, uv_loc: int) -> None:
        gl_funcs.glDrawArrays(0x0005, 0, 4)  # GL_TRIANGLE_STRIP
        prog.disableAttributeArray(uv_loc)
        if self._vbo is not None:
            self._vbo.release()
        prog.release()

    def draw_solid(
        self,
        gl_funcs: Any,
        dst_ndc_pts: list[tuple[float, float]],
        color: QColor,
        opacity: float = 1.0,
    ) -> None:
        prog = self._programs.get("solid")
        if prog is None or self._vbo is None:
            return
        a = color.alphaF() * max(0.0, min(1.0, float(opacity)))
        col0, col1, col2 = compute_quad_homography(dst_ndc_pts)
        prog.bind()
        uv_loc = self._bind_quad_geometry(prog, col0, col1, col2)
        _set_uniform(prog, "u_color", color.redF() * a, color.greenF() * a, color.blueF() * a, a)
        self._draw_bound_quad(gl_funcs, prog, uv_loc)

    def draw_texture(
        self,
        gl_funcs: Any,
        tex_id: int,
        dst_ndc_pts: list[tuple[float, float]],
        opacity: float = 1.0,
        *,
        flip_v: bool = False,
        shader_preset: str = "none",
        resolution_px: tuple[int, int] = (0, 0),
        elapsed: float = 0.0,
    ) -> None:
        norm_fx = normalize_shader_preset(shader_preset)
        prog = self._programs.get(f"fx:{norm_fx}") if norm_fx != "none" else self._programs.get("sprite")
        if prog is None or self._vbo is None:
            prog = self._programs.get("sprite")
        if prog is None:
            return

        col0, col1, col2 = compute_quad_homography(dst_ndc_pts)
        prog.bind()
        uv_loc = self._bind_quad_geometry(prog, col0, col1, col2, flip_v=flip_v)
        gl_funcs.glActiveTexture(0x84C0)
        gl_funcs.glBindTexture(0x0DE1, int(tex_id))  # GL_TEXTURE_2D
        _set_uniform(prog, "u_tex", 0)
        if norm_fx != "none":
            _set_uniform(prog, "u_resolution", max(1, resolution_px[0]), max(1, resolution_px[1]))
            _set_uniform(prog, "u_time", elapsed)
            _set_uniform(prog, "u_intensity", 1.0)
        else:
            _set_uniform(prog, "u_opacity", max(0.0, min(1.0, float(opacity))))
        self._draw_bound_quad(gl_funcs, prog, uv_loc)

    def draw_pixmap_cmd(self, gl_funcs: Any, cmd: GpuQuadCommand) -> None:
        if cmd.dynamic_rev is not None:
            tex = self.texture_cache.update_or_upload(cmd.tex_key, cmd.pixmap, cmd.dynamic_rev)
        else:
            tex = self.texture_cache.get_or_upload(cmd.tex_key, cmd.pixmap)
        if tex is None:
            return
        self.draw_texture(
            gl_funcs,
            tex.textureId(),
            cmd.dst_ndc_pts,
            opacity=cmd.opacity,
        )

    def draw_video_cmd(
        self,
        gl_funcs: Any,
        cmd: GpuQuadCommand,
        *,
        outer_fbo_id: int = 0,
        outer_viewport: tuple[int, int] = (1, 1),
    ) -> None:
        if cmd.fill_color is not None:
            self.draw_solid(gl_funcs, cmd.dst_ndc_pts, cmd.fill_color, opacity=cmd.opacity)

        surf = cmd.video_surface
        if surf is None:
            return
        self.track_video_surface(surf)
        if not surf.sync_to_gpu():
            return

        norm_fx = normalize_shader_preset(cmd.shader_preset)
        use_fx_fbo = norm_fx != "none" and f"fx:{norm_fx}" in self._programs

        if use_fx_fbo:
            tw, th = cmd.target_px
            if tw <= 0 or th <= 0:
                vw, vh = surf.video_size
                tw, th = max(64, vw), max(64, vh)
            tv_fbo = self._get_fbo("tv_fx", tw, th)
            tv_fbo.bind()
            gl_funcs.glViewport(0, 0, tv_fbo.width(), tv_fbo.height())
            gl_funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
            gl_funcs.glClear(0x00004000)

            full_pts = [(-1.0, 1.0), (1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)]
            self._draw_video_raw(gl_funcs, surf, full_pts, opacity=1.0)
            tv_fbo.release()

            gl_funcs.glBindFramebuffer(0x8D40, int(outer_fbo_id))  # GL_FRAMEBUFFER
            gl_funcs.glViewport(0, 0, max(1, outer_viewport[0]), max(1, outer_viewport[1]))
            self.draw_texture(
                gl_funcs,
                tv_fbo.texture(),
                cmd.dst_ndc_pts,
                opacity=cmd.opacity,
                flip_v=True,
                shader_preset=norm_fx,
                resolution_px=(tv_fbo.width(), tv_fbo.height()),
                elapsed=cmd.shader_elapsed,
            )
            return

        self._draw_video_raw(gl_funcs, surf, cmd.dst_ndc_pts, opacity=cmd.opacity)

    def execute_commands(
        self,
        gl_funcs: Any,
        commands: list[GpuQuadCommand],
        *,
        outer_fbo_id: int = 0,
        outer_viewport: tuple[int, int] = (1, 1),
    ) -> None:
        """Ejecuta comandos GPU agrupando ráfagas `pixmap` sin bind/release redundantes por quad."""
        if not commands or self._vbo is None:
            return

        sprite_prog = self._programs.get("sprite")
        batch_active = False
        batch_uv_loc = -1
        last_tex_id = -1
        last_opacity = -1.0

        def _end_sprite_batch() -> None:
            nonlocal batch_active, batch_uv_loc, last_tex_id, last_opacity
            if not batch_active:
                return
            if sprite_prog is not None:
                sprite_prog.disableAttributeArray(batch_uv_loc)
                sprite_prog.release()
            if self._vbo is not None:
                self._vbo.release()
            batch_active = False
            batch_uv_loc = -1
            last_tex_id = -1
            last_opacity = -1.0

        try:
            for cmd in commands:
                if cmd.kind == "pixmap" and sprite_prog is not None:
                    tex = (
                        self.texture_cache.update_or_upload(cmd.tex_key, cmd.pixmap, cmd.dynamic_rev)
                        if cmd.dynamic_rev is not None
                        else self.texture_cache.get_or_upload(cmd.tex_key, cmd.pixmap)
                    )
                    if tex is None:
                        continue

                    if not batch_active:
                        sprite_prog.bind()
                        self._vbo.bind()
                        batch_uv_loc = sprite_prog.attributeLocation("a_uv")
                        sprite_prog.enableAttributeArray(batch_uv_loc)
                        sprite_prog.setAttributeBuffer(batch_uv_loc, 0x1406, 0, 2, 8)
                        _set_uniform(sprite_prog, "u_flip_v", 0.0)
                        gl_funcs.glActiveTexture(0x84C0)
                        _set_uniform(sprite_prog, "u_tex", 0)
                        batch_active = True

                    tex_id = int(tex.textureId())
                    if tex_id != last_tex_id:
                        gl_funcs.glBindTexture(0x0DE1, tex_id)
                        last_tex_id = tex_id

                    op = max(0.0, min(1.0, float(cmd.opacity)))
                    if abs(op - last_opacity) > 1e-4:
                        _set_uniform(sprite_prog, "u_opacity", op)
                        last_opacity = op

                    col0, col1, col2 = compute_quad_homography(cmd.dst_ndc_pts)
                    _set_uniform(sprite_prog, "u_col0", col0[0], col0[1], col0[2])
                    _set_uniform(sprite_prog, "u_col1", col1[0], col1[1], col1[2])
                    _set_uniform(sprite_prog, "u_col2", col2[0], col2[1], col2[2])
                    gl_funcs.glDrawArrays(0x0005, 0, 4)
                    continue

                _end_sprite_batch()
                if cmd.kind == "solid" and cmd.color is not None:
                    self.draw_solid(gl_funcs, cmd.dst_ndc_pts, cmd.color, opacity=cmd.opacity)
                elif cmd.kind == "pixmap":
                    self.draw_pixmap_cmd(gl_funcs, cmd)
                elif cmd.kind == "video":
                    self.draw_video_cmd(
                        gl_funcs,
                        cmd,
                        outer_fbo_id=outer_fbo_id,
                        outer_viewport=outer_viewport,
                    )
        finally:
            _end_sprite_batch()

    def _draw_video_raw(
        self,
        gl_funcs: Any,
        surf: GpuVideoSurface,
        dst_ndc_pts: list[tuple[float, float]],
        opacity: float,
    ) -> None:
        self.track_video_surface(surf)
        if self._vbo is None or not surf.sync_to_gpu():
            return
        # Determinar shader acorde al formato actual tras sync_to_gpu()
        prog_key = {
            "nv12": "video_nv12",
            "yuv420p": "video_yuv420p",
        }.get(surf._mode, "video_rgba")
        prog = self._programs.get(prog_key)
        if prog is None:
            return

        col0, col1, col2 = compute_quad_homography(dst_ndc_pts)
        prog.bind()
        mode = surf.bind_to_program(gl_funcs, prog)
        if mode is None:
            prog.release()
            return
        uv_loc = self._bind_quad_geometry(prog, col0, col1, col2, flip_v=False)
        _set_uniform(prog, "u_opacity", max(0.0, min(1.0, float(opacity))))
        self._draw_bound_quad(gl_funcs, prog, uv_loc)


# ---------------------------------------------------------------------------
# Widget Viewport OpenGL de escena en tiempo real
# ---------------------------------------------------------------------------


def build_particle_quad_commands(
    particles: Any,
    viewport_w: int,
    viewport_h: int,
    scale: float = 1.0,
) -> list[GpuQuadCommand]:
    """Convierte las partículas activas en quads GPU con sprites cacheados en VRAM."""
    if particles is None:
        return []
    count = int(getattr(particles, "active_count", 0) or 0)
    if count <= 0 or viewport_w < 4 or viewport_h < 4:
        return []

    preset = str(getattr(particles, "_preset", "neon_dust") or "neon_dust")
    palette = _PRESET_PALETTES.get(preset, _PRESET_PALETTES["neon_dust"])
    sc = max(0.35, min(2.0, float(scale)))
    cur_t = float(getattr(particles, "_time", 0.0) or 0.0)

    cmds: list[GpuQuadCommand] = []
    xs = particles._x
    ys = particles._y
    sizes = particles._size
    alphas = particles._alpha
    phases = particles._phase
    cidxs = particles._color_idx

    for i in range(count):
        px = float(xs[i]) * viewport_w
        py = float(ys[i]) * viewport_h
        diam = max(4, min(28, int(round(float(sizes[i]) * sc))))
        col = palette[int(cidxs[i]) % len(palette)]
        sprite = _get_glow_sprite(col, diam)
        twinkle = 0.85 + 0.15 * math.sin(cur_t * 2.6 + float(phases[i]))
        op = max(0.08, min(1.0, float(alphas[i]) * twinkle))
        half = diam * 0.5
        cmds.append(
            GpuQuadCommand(
                kind="pixmap",
                dst_ndc_pts=build_rect_ndc_points(px - half, py - half, float(diam), float(diam), viewport_w, viewport_h),
                opacity=op,
                tex_key=("particle_glow", col.red(), col.green(), col.blue(), diam),
                pixmap=sprite,
            )
        )
    return cmds


class GpuSceneViewport(QOpenGLWidget):
    """Viewport OpenGL transparente a entrada que dibuja escenas de PlayNexus en GPU."""

    def __init__(self, parent: QWidget | None = None) -> None:
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setAlphaBufferSize(8)
        super().__init__(parent)
        self.setFormat(fmt)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.pipeline = GpuQuadPipeline(self)
        self._scene_builder: Callable[[int, int], tuple[list[GpuQuadCommand], dict[str, Any]]] | None = None
        self._fallback_triggered: bool = False
        self._frame_counter: int = 0
        self._on_frame_rendered: Callable[[], None] | None = None

    @property
    def gl_ready(self) -> bool:
        return self.pipeline.ready and not self._fallback_triggered

    @property
    def frame_counter(self) -> int:
        return self._frame_counter

    def set_scene_builder(
        self,
        builder: Callable[[int, int], tuple[list[GpuQuadCommand], dict[str, Any]]] | None,
    ) -> None:
        self._scene_builder = builder

    def set_on_frame_rendered(self, cb: Callable[[], None] | None) -> None:
        self._on_frame_rendered = cb

    def register_video_surface(self, surf: GpuVideoSurface | None) -> None:
        """Registra una `GpuVideoSurface` para liberar sus texturas en VRAM al cerrar."""
        self.pipeline.track_video_surface(surf)

    def _with_ctx_current(self, fn: Callable[[], None]) -> None:
        if not _is_qt_valid(self):
            return
        ctx = None
        try:
            ctx = self.context()
        except Exception:
            ctx = None

        if _is_qt_valid(ctx) and ctx.isValid():
            prev_ctx = None
            prev_surf = None
            switched = False
            made_widget_current = False
            try:
                cur = QOpenGLContext.currentContext()
                if not _contexts_compatible(ctx, cur):
                    prev_ctx = cur
                    prev_surf = cur.surface() if _is_qt_valid(cur) else None
                    surf = ctx.surface()
                    if surf is not None:
                        switched = bool(ctx.makeCurrent(surf))
                    if not switched:
                        self.makeCurrent()
                        made_widget_current = True
                if QOpenGLContext.currentContext() is not None:
                    fn()
            except Exception:
                pass
            finally:
                if made_widget_current:
                    try:
                        if prev_ctx is not None and prev_surf is not None and _is_qt_valid(prev_ctx) and prev_ctx.isValid():
                            prev_ctx.makeCurrent(prev_surf)
                        else:
                            self.doneCurrent()
                    except Exception:
                        pass
                elif switched:
                    _restore_ctx_safe(ctx, prev_ctx, prev_surf, True)

    def release_gl_textures(self) -> None:
        """Libera texturas, FBOs y planos de video mientras el contexto aún es válido (ej. al ocultar/recrear ventana)."""
        def _do_release() -> None:
            tracked = getattr(self.pipeline, "_tracked_surfaces", None)
            if tracked is not None:
                for surf in list(tracked):
                    try:
                        surf.destroy_gl()
                    except Exception:
                        pass
            self.pipeline.texture_cache.clear()
            self.pipeline._fbos.clear()

        self._with_ctx_current(_do_release)

    def cleanup_gl(self) -> None:
        """Libera de forma síncrona las texturas, FBOs, shaders y superficies de video en VRAM."""
        if getattr(self, "_pn_gl_cleaned", False) and not self.pipeline._ready and len(self.pipeline.texture_cache) == 0:
            tracked = getattr(self.pipeline, "_tracked_surfaces", None)
            if not tracked:
                return
        if not _is_qt_valid(self):
            try:
                self.pipeline.cleanup()
            except Exception:
                pass
            return

        ctx = None
        try:
            ctx = self.context()
        except Exception:
            ctx = None

        if _is_qt_valid(ctx) and ctx.isValid():
            self._with_ctx_current(self.pipeline.cleanup)
        else:
            try:
                self.pipeline.cleanup()
            except Exception:
                pass
        self._pn_gl_cleaned = True

    def initializeGL(self) -> None:  # noqa: N802
        ctx = self.context()
        prev_ctx_ref = getattr(self, "_bound_ctx_ref", None)
        prev_ctx = prev_ctx_ref() if prev_ctx_ref is not None else None
        if prev_ctx_ref is not None and ctx is not prev_ctx:
            # El contexto OpenGL fue recreado (p. ej. cambio fullscreen/bordes): limpiar estado previo
            prev_p, prev_s, sw = _ctx_make_current_safe(prev_ctx)
            try:
                self.pipeline.cleanup()
            except Exception:
                pass
            finally:
                _restore_ctx_safe(prev_ctx, prev_p, prev_s, sw)
            if _is_qt_valid(ctx) and QOpenGLContext.currentContext() is not ctx:
                surf = ctx.surface()
                if surf is not None:
                    try:
                        ctx.makeCurrent(surf)
                    except Exception:
                        pass
                else:
                    try:
                        self.makeCurrent()
                    except Exception:
                        pass

        self._pn_gl_cleaned = False
        self.pipeline.texture_cache.set_owner_context(ctx)
        ok = self.pipeline.initialize()
        self._fallback_triggered = not ok
        if _is_qt_valid(ctx):
            self._bound_ctx_ref = weakref.ref(ctx)
            _install_ctx_destroy_hook(ctx, self.pipeline)
        else:
            self._bound_ctx_ref = None

        anc_filter = getattr(self, "_ancestor_cleanup_filter", None)
        if anc_filter is None:
            anc_filter = _AncestorGlCleanupFilter(self)
            self._ancestor_cleanup_filter = anc_filter
        anc_filter.watch(self.parentWidget())
        anc_filter.watch(self.window())

    def hideEvent(self, event) -> None:  # noqa: N802
        self.release_gl_textures()
        super().hideEvent(event)

    def _on_context_destroyed(self) -> None:
        self.cleanup_gl()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.cleanup_gl()
        super().closeEvent(event)

    def paintGL(self) -> None:  # noqa: N802
        ctx = self.context()
        if ctx is None or not self.gl_ready:
            return
        gl_funcs = ctx.functions()

        log_w = max(1, int(self.width()))
        log_h = max(1, int(self.height()))
        dpr = max(1.0, float(self.devicePixelRatioF() or 1.0))
        fb_w = max(1, int(round(log_w * dpr)))
        fb_h = max(1, int(round(log_h * dpr)))

        commands: list[GpuQuadCommand] = []
        meta: dict[str, Any] = {}
        if self._scene_builder is not None:
            try:
                commands, meta = self._scene_builder(log_w, log_h)
            except Exception:
                commands, meta = [], {}

        global_fx = normalize_shader_preset(meta.get("global_shader", "none"))
        elapsed = float(meta.get("elapsed", 0.0) or 0.0)
        particles = meta.get("particles")
        particle_scale = float(meta.get("particle_scale", 1.0) or 1.0)
        if particles is not None:
            commands.extend(build_particle_quad_commands(particles, log_w, log_h, scale=particle_scale))

        default_fbo = int(self.defaultFramebufferObject())
        use_global_fbo = global_fx != "none" and f"fx:{global_fx}" in self.pipeline._programs

        active_fbo = default_fbo
        active_w, active_h = fb_w, fb_h
        scene_fbo = None
        if use_global_fbo:
            scene_fbo = self.pipeline._get_fbo("global_scene", fb_w, fb_h)
            scene_fbo.bind()
            active_fbo = int(scene_fbo.handle())
            active_w, active_h = scene_fbo.width(), scene_fbo.height()

        gl_funcs.glViewport(0, 0, active_w, active_h)
        gl_funcs.glDisable(0x0B71)  # GL_DEPTH_TEST
        gl_funcs.glEnable(0x0BE2)   # GL_BLEND
        gl_funcs.glBlendFunc(1, 0x0303)  # GL_ONE, GL_ONE_MINUS_SRC_ALPHA
        gl_funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
        gl_funcs.glClear(0x00004000)

        self.pipeline.execute_commands(
            gl_funcs,
            commands,
            outer_fbo_id=active_fbo,
            outer_viewport=(active_w, active_h),
        )

        if use_global_fbo and scene_fbo is not None:
            if scene_fbo.isBound():
                scene_fbo.release()
            gl_funcs.glBindFramebuffer(0x8D40, default_fbo)
            gl_funcs.glViewport(0, 0, fb_w, fb_h)
            gl_funcs.glEnable(0x0BE2)
            gl_funcs.glBlendFunc(1, 0x0303)
            gl_funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
            gl_funcs.glClear(0x00004000)
            full_pts = [(-1.0, 1.0), (1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)]
            self.pipeline.draw_texture(
                gl_funcs,
                scene_fbo.texture(),
                full_pts,
                opacity=1.0,
                flip_v=True,
                shader_preset=global_fx,
                resolution_px=(fb_w, fb_h),
                elapsed=elapsed,
            )

        gl_funcs.glActiveTexture(0x84C0)
        gl_funcs.glBindTexture(0x0DE1, 0)

        self._frame_counter += 1
        if self._on_frame_rendered is not None:
            try:
                self._on_frame_rendered()
            except Exception:
                pass


class GpuVideoPlayerWidget(QWidget):
    """Reproductor de video reutilizable en GPU (`QVideoFrame` directo a VRAM) con respaldo software."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        background_color: QColor | None = None,
        render_backend: str = "auto",
    ) -> None:
        super().__init__(parent)
        self._bg_color = QColor(background_color) if background_color is not None else QColor(0, 0, 0)
        self._backend = normalize_render_backend(render_backend)
        self._shader_preset = "none"
        self._particle_preset = "none"
        self._perf_profile = "high"
        self._start_ts = time.monotonic()
        self._last_fx_tick = self._start_ts
        self._particles = ParticleSystem("none", self._perf_profile)

        self.surface = GpuVideoSurface()
        self._fallback_img: QImage | None = None
        self._has_video = False

        self.viewport: GpuSceneViewport | None = None
        if is_gpu_rendering_permitted(self._backend):
            self.viewport = GpuSceneViewport(self)
            self.viewport.set_scene_builder(self._build_scene)
            self.viewport.setGeometry(0, 0, max(1, self.width()), max(1, self.height()))
            self.viewport.show()

        self._fx_timer = QTimer(self)
        self._fx_timer.setInterval(16)
        self._fx_timer.timeout.connect(self._on_fx_tick)

    def is_gpu_active(self) -> bool:
        vp = self.viewport
        return (
            vp is not None
            and not getattr(vp, "_fallback_triggered", True)
            and is_gpu_rendering_permitted(self._backend)
        )

    def video_size(self) -> tuple[int, int]:
        if self.surface.has_video:
            return self.surface.video_size
        if self._fallback_img is not None and not self._fallback_img.isNull():
            return (self._fallback_img.width(), self._fallback_img.height())
        return (0, 0)

    def set_background_color(self, color: QColor) -> None:
        self._bg_color = QColor(color)
        self._refresh_target()

    def set_render_backend(self, backend: str | None) -> bool:
        self._backend = normalize_render_backend(backend)
        permitted = is_gpu_rendering_permitted(self._backend)
        if permitted and self.viewport is None:
            self.viewport = GpuSceneViewport(self)
            self.viewport.set_scene_builder(self._build_scene)
            self.viewport.setGeometry(0, 0, max(1, self.width()), max(1, self.height()))
        if self.viewport is not None:
            if permitted and not getattr(self.viewport, "_fallback_triggered", True):
                self.viewport.setGeometry(0, 0, max(1, self.width()), max(1, self.height()))
                self.viewport.show()
                self.viewport.update()
                return bool(self.viewport.gl_ready)
            if self.viewport.isVisible():
                self.viewport.hide()
        self.update()
        return False

    def set_effects(
        self,
        *,
        shader_preset: str | None = None,
        particle_preset: str | None = None,
        perf_profile: str | None = None,
    ) -> None:
        if shader_preset is not None:
            self._shader_preset = normalize_shader_preset(shader_preset)
        if perf_profile is not None:
            self._perf_profile = normalize_effects_perf(perf_profile)
            self._particles.set_perf_profile(self._perf_profile)
        if particle_preset is not None:
            self._particle_preset = normalize_particle_preset(particle_preset)
            self._particles.set_preset(self._particle_preset)

        needs_anim = self._perf_profile != "off" and (
            self._particle_preset != "none" or self._shader_preset == "vhs_arcade"
        )
        if needs_anim and not self._fx_timer.isActive():
            self._last_fx_tick = time.monotonic()
            self._fx_timer.start()
        elif not needs_anim and self._fx_timer.isActive():
            self._fx_timer.stop()
        self._refresh_target()

    def present_frame(self, frame: QVideoFrame | None) -> bool:
        """Presenta un `QVideoFrame` en VRAM si GPU está activa, o convierte a CPU en respaldo."""
        if frame is None or not frame.isValid():
            return False
        if self.is_gpu_active():
            if self.surface.set_frame(frame):
                self._fallback_img = None
                self._has_video = True
                self._refresh_target()
                return True
        img = frame.toImage()
        if img.isNull():
            return False
        self._fallback_img = img
        self._has_video = True
        self._refresh_target()
        return False

    def clear_frame(self) -> None:
        self._has_video = False
        self._fallback_img = None
        self.surface.clear()
        self._refresh_target()

    def _on_fx_tick(self) -> None:
        now = time.monotonic()
        dt = max(0.004, min(0.08, now - self._last_fx_tick))
        self._last_fx_tick = now
        if self._perf_profile != "off" and self._particle_preset != "none":
            self._particles.step(dt)
        self._refresh_target()

    def _refresh_target(self) -> None:
        vp = self.viewport
        if vp is not None and vp.isVisible():
            vp.update()
        else:
            self.update()

    def _aspect_fit_rect(self, w: int, h: int, vw: int, vh: int) -> QRectF:
        if vw <= 0 or vh <= 0 or w <= 0 or h <= 0:
            return QRectF(0.0, 0.0, float(max(1, w)), float(max(1, h)))
        scale = min(w / float(vw), h / float(vh))
        dw = vw * scale
        dh = vh * scale
        return QRectF((w - dw) * 0.5, (h - dh) * 0.5, dw, dh)

    def _build_scene(self, log_w: int, log_h: int) -> tuple[list[GpuQuadCommand], dict[str, Any]]:
        cmds: list[GpuQuadCommand] = [
            GpuQuadCommand(
                kind="solid",
                dst_ndc_pts=build_rect_ndc_points(0.0, 0.0, float(log_w), float(log_h), log_w, log_h),
                color=self._bg_color,
                opacity=1.0,
            )
        ]
        elapsed = max(0.0, time.monotonic() - self._start_ts)
        sh = self._shader_preset if self._perf_profile != "off" else "none"
        if self._has_video and self.surface.has_video:
            vw, vh = self.surface.video_size
            r = self._aspect_fit_rect(log_w, log_h, vw, vh)
            cmds.append(
                GpuQuadCommand(
                    kind="video",
                    dst_ndc_pts=build_rect_ndc_points(r.x(), r.y(), r.width(), r.height(), log_w, log_h),
                    opacity=1.0,
                    video_surface=self.surface,
                    shader_preset=sh,
                    shader_elapsed=elapsed,
                    target_px=(max(16, int(round(r.width()))), max(16, int(round(r.height())))),
                )
            )
        parts = self._particles if (self._perf_profile != "off" and self._particle_preset != "none") else None
        return cmds, {
            "global_shader": "none",
            "elapsed": elapsed,
            "particles": parts,
            "particle_scale": max(0.45, min(1.5, log_w / 1280.0)),
        }

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.viewport is not None:
            self.viewport.setGeometry(0, 0, max(1, self.width()), max(1, self.height()))

    def paintEvent(self, event) -> None:  # noqa: N802
        if self.is_gpu_active() and self.viewport is not None and self.viewport.isVisible():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        w, h = max(1, self.width()), max(1, self.height())
        painter.fillRect(0, 0, w, h, self._bg_color)
        if self._has_video and self._fallback_img is not None and not self._fallback_img.isNull():
            r = self._aspect_fit_rect(w, h, self._fallback_img.width(), self._fallback_img.height())
            img = self._fallback_img
            if self._perf_profile != "off" and self._shader_preset != "none":
                elapsed = max(0.0, time.monotonic() - self._start_ts)
                img = apply_shader_to_image(
                    img,
                    QRect(0, 0, max(16, int(round(r.width()))), max(16, int(round(r.height())))).size(),
                    self._shader_preset,
                    elapsed=elapsed,
                )
            painter.drawImage(r, img)
        if self._perf_profile != "off" and self._particle_preset != "none":
            self._particles.paint(painter, QRectF(0.0, 0.0, float(w), float(h)), scale=max(0.45, min(1.5, w / 1280.0)))
        painter.end()

    def cleanup(self) -> None:
        """Detiene efectos y libera los recursos OpenGL y la superficie de video."""
        if self._fx_timer.isActive():
            self._fx_timer.stop()
        if self.viewport is not None:
            try:
                self.viewport.register_video_surface(self.surface)
                self.viewport.cleanup_gl()
            except Exception:
                pass
        else:
            try:
                self.surface.clear()
            except Exception:
                pass

    def closeEvent(self, event) -> None:  # noqa: N802
        self.cleanup()
        super().closeEvent(event)
