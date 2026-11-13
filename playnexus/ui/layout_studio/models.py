from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CANONICAL_W = 1920
CANONICAL_H = 1080


@dataclass
class LayoutElement:
    """Representa un elemento visual o capa dentro del layout."""
    id: str = field(default_factory=lambda: f"elem_{uuid.uuid4().hex[:8]}")
    name: str = "Nuevo Elemento"
    type: str = "image"  # 'image', 'video', 'wheel', 'marquee', 'text', 'effect'
    
    # Coordenadas canónicas (1920 x 1080)
    x: float = 100.0
    y: float = 100.0
    w: float = 400.0
    h: float = 300.0
    rotation: float = 0.0
    opacity: float = 1.0
    z_index: int = 10
    visible: bool = True
    locked: bool = False

    # Deformación de perspectiva (Corner Pinning): 4 puntos [TL, TR, BR, BL]
    # Si es None o vacío, se utiliza la caja rectangular normal.
    corner_pins: list[tuple[float, float]] | None = None

    # Caja delimitadora nativa original (ox, oy, ow, oh) medida directamente desde ThemeLayout
    orig_rect: tuple[float, float, float, float] | None = None

    # Enlace a medios del juego o recurso local
    media_key: str = ""  # 'video', 'wheel', 'marquee', 'boxart', 'cartart', etc.
    resource_path: str = ""  # Ruta a archivo local relativo a la carpeta del layout
    
    # Propiedades para elementos de texto
    text_template: str = "{title}"
    font_file: str = ""
    font_size: int = 24
    text_color: str = "#ffffff"
    text_align: str = "left"  # 'left', 'center', 'right'

    # Propiedades para ruleta (Wheel)
    wheel_orientation: str = "vertical"  # 'vertical', 'horizontal', 'curved'
    wheel_visible_items: int = 9
    wheel_item_spacing: float = 85.0
    wheel_curvature: float = 0.0

    # Propiedades para efectos (Scanlines, CRT, Viñeta)
    effect_type: str = ""  # 'scanlines', 'vignette', 'crt_curvature'
    effect_intensity: float = 0.4
    effect_param: float = 4.0  # espaciado de scanlines o radio de viñeta

    # Propiedades para animaciones y cinemática interactiva
    # Tipos: '', 'none', 'flyer_slide_right', 'cart_drop', 'boxart_slide_fade', 'logo_bounce', 'avatar_float', 'pointer_pulse', 'disc_spin'
    anim_type: str = ""
    anim_delay: float = 0.0     # Retardo en segundos antes de disparar la transición
    anim_duration: float = 0.8  # Duración de la animación en segundos

    def has_animation(self) -> bool:
        """Determina si este elemento posee o admite una animación cinemática interactiva."""
        if self.anim_type:
            tokens = [a.strip() for a in self.anim_type.replace("+", ",").split(",") if a.strip()]
            if any(t != "none" for t in tokens):
                return True
            if all(t == "none" for t in tokens):
                return False

        # Detección semántica automática por identificador, nombre o medio asociado
        blob = f"{self.id} {self.name} {self.media_key} {self.type} {self.resource_path}".lower()
        if "disc" in blob or "cd" in blob:
            self.anim_type = "disc_rise,disc_spin"
            self.anim_delay = 0.0
            self.anim_duration = 0.8
            return True
        if "cart" in blob:
            self.anim_type = "cart_drop"
            self.anim_delay = 0.0
            self.anim_duration = 0.7
            return True
        if "box" in blob:
            self.anim_type = "boxart_slide_fade"
            self.anim_delay = 0.0
            self.anim_duration = 0.45
            return True
        if "logo" in blob:
            self.anim_type = "logo_bounce"
            self.anim_delay = 0.0
            self.anim_duration = 1.2
            return True
        if any(w in blob for w in ["avatar", "mecha", "ship", "robot"]):
            self.anim_type = "avatar_float"
            self.anim_delay = 0.0
            self.anim_duration = 3.0
            return True
        if "pointer" in blob:
            self.anim_type = "pointer_pulse"
            self.anim_delay = 0.0
            self.anim_duration = 1.0
            return True

        return False

    def to_dict(self) -> dict[str, Any]:
        """Serializa el elemento a un diccionario nativo."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "w": round(self.w, 2),
            "h": round(self.h, 2),
            "rotation": round(self.rotation, 2),
            "opacity": round(self.opacity, 3),
            "z_index": self.z_index,
            "visible": self.visible,
            "locked": self.locked,
            "corner_pins": (
                [[round(px, 2), round(py, 2)] for px, py in self.corner_pins]
                if self.corner_pins
                else None
            ),
            "orig_rect": (
                [round(v, 2) for v in self.orig_rect]
                if self.orig_rect and len(self.orig_rect) == 4
                else None
            ),
            "media_key": self.media_key,
            "resource_path": self.resource_path,
            "text_template": self.text_template,
            "font_file": self.font_file,
            "font_size": self.font_size,
            "text_color": self.text_color,
            "text_align": self.text_align,
            "wheel_orientation": self.wheel_orientation,
            "wheel_visible_items": self.wheel_visible_items,
            "wheel_item_spacing": round(self.wheel_item_spacing, 2),
            "wheel_curvature": round(self.wheel_curvature, 3),
            "effect_type": self.effect_type,
            "effect_intensity": round(self.effect_intensity, 3),
            "effect_param": round(self.effect_param, 2),
            "anim_type": self.anim_type,
            "anim_delay": round(self.anim_delay, 2),
            "anim_duration": round(self.anim_duration, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutElement:
        """Instancia un LayoutElement a partir de un diccionario."""
        pins = data.get("corner_pins")
        if pins and len(pins) == 4:
            pins = [(float(p[0]), float(p[1])) for p in pins]
        else:
            pins = None

        orec = data.get("orig_rect")
        if orec and len(orec) == 4:
            orec = (float(orec[0]), float(orec[1]), float(orec[2]), float(orec[3]))
        else:
            orec = None

        return cls(
            id=str(data.get("id", f"elem_{uuid.uuid4().hex[:8]}")),
            name=str(data.get("name", "Elemento")),
            type=str(data.get("type", "image")),
            x=float(data.get("x", 100)),
            y=float(data.get("y", 100)),
            w=float(data.get("w", 300)),
            h=float(data.get("h", 200)),
            rotation=float(data.get("rotation", 0)),
            opacity=float(data.get("opacity", 1.0)),
            z_index=int(data.get("z_index", 10)),
            visible=bool(data.get("visible", True)),
            locked=bool(data.get("locked", False)),
            corner_pins=pins,
            orig_rect=orec,
            media_key=str(data.get("media_key", "")),
            resource_path=str(data.get("resource_path", "")),
            text_template=str(data.get("text_template", "{title}")),
            font_file=str(data.get("font_file", "")),
            font_size=int(data.get("font_size", 24)),
            text_color=str(data.get("text_color", "#ffffff")),
            text_align=str(data.get("text_align", "left")),
            wheel_orientation=str(data.get("wheel_orientation", "vertical")),
            wheel_visible_items=int(data.get("wheel_visible_items", 9)),
            wheel_item_spacing=float(data.get("wheel_item_spacing", 85.0)),
            wheel_curvature=float(data.get("wheel_curvature", 0.0)),
            effect_type=str(data.get("effect_type", "")),
            effect_intensity=float(data.get("effect_intensity", 0.4)),
            effect_param=float(data.get("effect_param", 4.0)),
            anim_type=str(data.get("anim_type", "")),
            anim_delay=float(data.get("anim_delay", 0.0)),
            anim_duration=float(data.get("anim_duration", 0.8)),
        )

    def init_corner_pins(self) -> None:
        """Inicializa los 4 corner pins a las esquinas del rectángulo actual."""
        self.corner_pins = [
            (self.x, self.y),                      # TL: Superior izquierda
            (self.x + self.w, self.y),              # TR: Superior derecha
            (self.x + self.w, self.y + self.h),     # BR: Inferior derecha
            (self.x, self.y + self.h),              # BL: Inferior izquierda
        ]

    def reset_corner_pins(self) -> None:
        """Elimina la distorsión y regresa al rectángulo estándar."""
        self.corner_pins = None


@dataclass
class LayoutProject:
    """Contenedor de metadatos y capas del layout en edición."""
    name: str = "Nuevo Layout"
    description: str = "Layout creado con PlayNexus Layout Studio"
    author: str = "PlayNexus"
    elements: list[LayoutElement] = field(default_factory=list)
    media_requirements: list[dict[str, Any]] = field(default_factory=list)
    custom_code: str = ""
    folder_path: str = ""

    def add_element(self, elem: LayoutElement) -> None:
        """Agrega un elemento y asigna el z_index más alto."""
        max_z = max([e.z_index for e in self.elements], default=0)
        elem.z_index = max_z + 10
        self.elements.append(elem)

    def remove_element(self, elem_id: str) -> bool:
        """Elimina un elemento por su id."""
        for i, e in enumerate(self.elements):
            if e.id == elem_id:
                self.elements.pop(i)
                return True
        return False

    def get_element(self, elem_id: str) -> LayoutElement | None:
        """Obtiene un elemento por su id."""
        for e in self.elements:
            if e.id == elem_id:
                return e
        return None

    def clone(self) -> LayoutProject:
        """Retorna una copia profunda del proyecto."""
        return copy.deepcopy(self)

