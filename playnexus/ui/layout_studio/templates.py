from __future__ import annotations

from typing import Any
from playnexus.ui.layout_studio.models import LayoutElement, LayoutProject, CANONICAL_W, CANONICAL_H


def create_arcade_cabinet_template(name: str = "Mi Arcade") -> LayoutProject:
    """Crea una plantilla de Mueble Arcade con Video Snap CRT, Marquee y Ruleta."""
    proj = LayoutProject(
        name=name,
        description="Layout de Mueble Arcade interactivo con Marquee y Ruleta vertical",
        media_requirements=[
            {"key": "video", "label": "Video Snaps", "extensions": [".mp4", ".mkv", ".avi", ".webm"], "required": True},
            {"key": "wheel", "label": "Wheel Logos", "extensions": [".png", ".webp"], "required": True},
            {"key": "marquee", "label": "Marquee", "extensions": [".png", ".jpg", ".webp"], "required": False},
        ],
    )

    # 1. Fondo
    proj.add_element(LayoutElement(
        id="bg_image",
        name="Fondo / Wallpaper",
        type="image",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=1,
        resource_path="bg.jpg",
    ))

    # 2. Video Snap (Pantalla CRT del mueble)
    proj.add_element(LayoutElement(
        id="video_snap",
        name="Video Snap (Pantalla CRT)",
        type="video",
        x=330, y=340, w=640, h=480,
        z_index=5,
        media_key="video",
    ))

    # 3. Efecto Scanlines sobre la pantalla
    proj.add_element(LayoutElement(
        id="screen_scanlines",
        name="Efecto Scanlines CRT",
        type="effect",
        x=330, y=340, w=640, h=480,
        z_index=6,
        effect_type="scanlines",
        effect_intensity=0.35,
        effect_param=4.0,
    ))

    # 4. Bezel / Marco de la pantalla
    proj.add_element(LayoutElement(
        id="bezel",
        name="Bezel / Marco Pantalla",
        type="image",
        x=280, y=290, w=740, h=580,
        z_index=10,
        resource_path="bezel.png",
    ))

    # 5. Marquee Iluminado superior
    proj.add_element(LayoutElement(
        id="marquee",
        name="Marquee Superior",
        type="marquee",
        x=290, y=50, w=720, h=200,
        z_index=12,
        media_key="marquee",
        resource_path="marquee.png",
    ))

    # 6. Ruleta de Ruedas lateral
    proj.add_element(LayoutElement(
        id="wheel_list",
        name="Ruleta de Juegos",
        type="wheel",
        x=1380, y=60, w=500, h=960,
        z_index=20,
        media_key="wheel",
        wheel_orientation="vertical",
        wheel_visible_items=9,
        wheel_item_spacing=95.0,
    ))

    # 7. Contador y Título inferior
    proj.add_element(LayoutElement(
        id="title_text",
        name="Título del Juego",
        type="text",
        x=100, y=960, w=900, h=60,
        z_index=25,
        text_template="{title}",
        font_size=32,
        text_color="#f1f5f9",
    ))

    proj.add_element(LayoutElement(
        id="counter_text",
        name="Contador de Juegos",
        type="text",
        x=1400, y=1020, w=450, h=40,
        z_index=25,
        text_template="{index} / {total}",
        font_size=20,
        text_color="#94a3b8",
        text_align="right",
    ))

    return proj


def create_retro_console_template(name: str = "Mi Consola") -> LayoutProject:
    """Crea una plantilla de Consola de Videojuegos con TV y Cartucho."""
    proj = LayoutProject(
        name=name,
        description="Layout temático de Consola Retro con TV a la izquierda y Ruleta Conveyor a la derecha",
        media_requirements=[
            {"key": "video", "label": "Video Snaps", "extensions": [".mp4", ".mkv", ".avi", ".webm"], "required": True},
            {"key": "wheel", "label": "Wheel Logos", "extensions": [".png", ".webp"], "required": True},
            {"key": "cartart", "label": "Cartuchos", "extensions": [".png", ".webp"], "required": True},
            {"key": "boxart", "label": "Box Art / Cajas", "extensions": [".png", ".jpg", ".jpeg", ".webp"], "required": False},
        ],
    )

    # Fondo
    proj.add_element(LayoutElement(
        id="bg_image",
        name="Fondo de Sala Retro",
        type="image",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=1,
        resource_path="bg.jpg",
    ))

    # TV Snap Video
    proj.add_element(LayoutElement(
        id="tv_video",
        name="Pantalla TV (Video Snap)",
        type="video",
        x=100, y=200, w=620, h=470,
        z_index=5,
        media_key="video",
    ))

    # Mueble TV
    proj.add_element(LayoutElement(
        id="tv_bezel",
        name="Televisor de Tubo (TV Bezel)",
        type="image",
        x=60, y=140, w=710, h=600,
        z_index=10,
        resource_path="tv.png",
    ))

    # Consola
    proj.add_element(LayoutElement(
        id="console_art",
        name="Consola",
        type="image",
        x=820, y=600, w=450, h=400,
        z_index=12,
        resource_path="console.png",
    ))

    # Ruleta Curva
    proj.add_element(LayoutElement(
        id="wheel_list",
        name="Ruleta de Logos",
        type="wheel",
        x=1360, y=50, w=520, h=980,
        z_index=20,
        media_key="wheel",
        wheel_orientation="vertical",
        wheel_visible_items=9,
        wheel_curvature=0.15,
    ))

    # Título
    proj.add_element(LayoutElement(
        id="title_text",
        name="Título del Juego",
        type="text",
        x=80, y=940, w=670, h=50,
        z_index=25,
        text_template="{title}",
        font_size=28,
        text_color="#38bdf8",
    ))

    return proj


def create_minimalist_fullscreen_template(name: str = "Minimalista Fullscreen") -> LayoutProject:
    """Crea una plantilla minimalista de video a pantalla completa con scanlines y rueda flotante."""
    proj = LayoutProject(
        name=name,
        description="Layout minimalista con video snap a pantalla completa y ruleta estilizada",
        media_requirements=[
            {"key": "video", "label": "Video Snaps", "extensions": [".mp4", ".mkv", ".avi", ".webm"], "required": True},
            {"key": "wheel", "label": "Wheel Logos", "extensions": [".png", ".webp"], "required": True},
        ],
    )

    # Video fullscreen
    proj.add_element(LayoutElement(
        id="fullscreen_video",
        name="Video Snap Pantalla Completa",
        type="video",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=1,
        media_key="video",
    ))

    # Scanlines globales
    proj.add_element(LayoutElement(
        id="scanlines_overlay",
        name="Scanlines CRT",
        type="effect",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=5,
        effect_type="scanlines",
        effect_intensity=0.25,
        effect_param=3.0,
    ))

    # Viñeta oscura perimetral
    proj.add_element(LayoutElement(
        id="vignette_overlay",
        name="Viñeta Sombra Perimetral",
        type="effect",
        x=0, y=0, w=CANONICAL_W, h=CANONICAL_H,
        z_index=6,
        effect_type="vignette",
        effect_intensity=0.55,
        effect_param=50.0,
    ))

    # Ruleta flotante
    proj.add_element(LayoutElement(
        id="floating_wheel",
        name="Ruleta Flotante",
        type="wheel",
        x=1420, y=50, w=460, h=980,
        z_index=15,
        media_key="wheel",
        wheel_orientation="vertical",
        wheel_visible_items=9,
    ))

    # Barra inferior con título
    proj.add_element(LayoutElement(
        id="title_hud",
        name="HUD Título",
        type="text",
        x=60, y=980, w=1200, h=60,
        z_index=20,
        text_template="{title}  ({year})",
        font_size=30,
        text_color="#f8fafc",
    ))

    return proj


TEMPLATES_LIBRARY = {
    "Arcade Cabinet (Clásico)": create_arcade_cabinet_template,
    "Consola Retro (TV + Cartucho)": create_retro_console_template,
    "Minimalista Fullscreen": create_minimalist_fullscreen_template,
}


from playnexus.ui.layout_studio.canonical_template import (
    generate_canonical_theme_layout_code,
    setup_new_layout_files,
    get_default_media_requirements,
)


def generate_layout_code(project: LayoutProject) -> str:
    """
    Genera el código fuente canónico en Python de theme_layout.py
    que compila y ejecuta directamente en PlayNexus conforme a las directivas estrictas
    de GEMINI.md (Reglas 4, 5, 6 y 8).
    """
    name_lower = (project.name or "").lower()
    desc_lower = (project.description or "").lower()
    layout_type = "arcade" if ("arcade" in name_lower or "arcade" in desc_lower) else "console"
    is_cd = ("cd" in name_lower or "disco" in name_lower or "disc" in name_lower)

    elements_dicts = []
    for elem in sorted(project.elements, key=lambda e: e.z_index):
        if not elem.visible:
            continue
        elements_dicts.append(elem.to_dict())

    return generate_canonical_theme_layout_code(
        name=project.name,
        description=project.description,
        layout_type=layout_type,
        is_cd=is_cd,
        elements=elements_dicts if elements_dicts else None,
    )


