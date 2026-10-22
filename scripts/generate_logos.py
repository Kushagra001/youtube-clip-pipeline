"""Generates high-resolution (512x512) circular vector-style PNG logo avatars
for all 10 channels. Transparent background, anti-aliased gradient shield,
sleek metallic border, and custom iconic emblems.
"""
import os
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "logos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHANNELS = {
    "acc_01_cats": {
        "title": "DAILY WHISKERS",
        "bg_dark": (26, 18, 12),
        "primary": (255, 175, 40),
        "accent": (255, 220, 120),
        "symbol": "cat",
    },
    "acc_02_dogs": {
        "title": "GOOD BOYS CLUB",
        "bg_dark": (12, 22, 38),
        "primary": (45, 180, 255),
        "accent": (130, 225, 255),
        "symbol": "paw",
    },
    "acc_03_fitness": {
        "title": "GRIND & BUILD",
        "bg_dark": (20, 20, 16),
        "primary": (255, 230, 0),
        "accent": (255, 255, 160),
        "symbol": "bolt",
    },
    "acc_04_motivation": {
        "title": "STOIC SOCIETY",
        "bg_dark": (24, 20, 16),
        "primary": (235, 195, 125),
        "accent": (255, 235, 180),
        "symbol": "pillar",
    },
    "acc_05_finance": {
        "title": "WEALTH NEXUS",
        "bg_dark": (10, 30, 20),
        "primary": (0, 230, 130),
        "accent": (120, 255, 190),
        "symbol": "chart",
    },
    "acc_06_business": {
        "title": "FOUNDER CENTRAL",
        "bg_dark": (18, 14, 38),
        "primary": (145, 90, 255),
        "accent": (200, 155, 255),
        "symbol": "rocket",
    },
    "acc_07_food": {
        "title": "FOOD VIDEOS DAILY",
        "bg_dark": (35, 14, 14),
        "primary": (255, 85, 55),
        "accent": (255, 165, 140),
        "symbol": "flame",
    },
    "acc_08_ai_tools": {
        "title": "AI TOOLS DAILY",
        "bg_dark": (10, 24, 36),
        "primary": (0, 240, 255),
        "accent": (140, 250, 255),
        "symbol": "chip",
    },
    "acc_09_grooming": {
        "title": "THE GROOMED MAN",
        "bg_dark": (24, 20, 20),
        "primary": (220, 170, 135),
        "accent": (248, 215, 190),
        "symbol": "crown",
    },
    "acc_10_mental_health": {
        "title": "CALM YOUR MIND",
        "bg_dark": (14, 26, 30),
        "primary": (40, 220, 200),
        "accent": (150, 248, 235),
        "symbol": "lotus",
    },
}


def draw_cat(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Sleek geometric feline silhouette
    # Head circle
    draw.ellipse([186, 210, 326, 350], fill=p)
    # Left ear
    draw.polygon([(180, 240), (210, 140), (250, 220)], fill=a)
    # Right ear
    draw.polygon([(332, 240), (302, 140), (262, 220)], fill=a)
    # Eyes
    draw.ellipse([216, 255, 244, 285], fill=(20, 15, 10))
    draw.ellipse([268, 255, 296, 285], fill=(20, 15, 10))
    # Nose & Whiskers
    draw.polygon([(250, 298), (262, 298), (256, 308)], fill=a)
    # Whiskers
    draw.line([(140, 295), (220, 305)], fill=a, width=4)
    draw.line([(140, 315), (220, 315)], fill=a, width=4)
    draw.line([(372, 295), (292, 305)], fill=a, width=4)
    draw.line([(372, 315), (292, 315)], fill=a, width=4)


def draw_paw(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Main pad
    draw.ellipse([196, 250, 316, 360], fill=p)
    # 4 Toe pads
    draw.ellipse([160, 200, 205, 250], fill=a)
    draw.ellipse([215, 160, 260, 215], fill=a)
    draw.ellipse([270, 160, 315, 215], fill=a)
    draw.ellipse([325, 200, 370, 250], fill=a)


def draw_bolt(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Dynamic angular lightning bolt
    pts = [
        (280, 120),
        (190, 255),
        (255, 255),
        (220, 390),
        (335, 235),
        (270, 235),
    ]
    draw.polygon(pts, fill=p)
    # Inner accent
    inner = [
        (270, 160),
        (215, 245),
        (260, 245),
        (238, 330),
        (310, 245),
        (265, 245),
    ]
    draw.polygon(inner, fill=a)


def draw_pillar(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Classical Roman Stoic column / temple
    # Capital / top
    draw.rectangle([180, 160, 332, 185], fill=a)
    draw.rectangle([195, 185, 317, 200], fill=p)
    # Columns (3 fluted pillars)
    draw.rectangle([205, 200, 225, 330], fill=p)
    draw.rectangle([246, 200, 266, 330], fill=a)
    draw.rectangle([287, 200, 307, 330], fill=p)
    # Base
    draw.rectangle([195, 330, 317, 345], fill=p)
    draw.rectangle([180, 345, 332, 370], fill=a)


def draw_chart(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Ascending financial geometric crest
    # 3 growth bars
    draw.rectangle([170, 290, 215, 360], fill=p)
    draw.rectangle([235, 230, 280, 360], fill=p)
    draw.rectangle([300, 165, 345, 360], fill=a)
    # Arrow diagonal across
    draw.line([(150, 330), (330, 150)], fill=a, width=12)
    # Arrow head
    draw.polygon([(345, 135), (300, 150), (330, 180)], fill=a)


def draw_rocket(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Startup launch rocket
    # Rocket body
    draw.ellipse([216, 140, 296, 320], fill=p)
    # Cockpit window
    draw.ellipse([240, 190, 272, 222], fill=a)
    # Fins
    draw.polygon([(216, 260), (160, 320), (225, 305)], fill=a)
    draw.polygon([(296, 260), (352, 320), (287, 305)], fill=a)
    # Thrust flame
    draw.polygon([(236, 320), (256, 385), (276, 320)], fill=(255, 200, 50))


def draw_flame(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Culinary flame & knife silhouette
    draw.polygon([
        (256, 130),
        (320, 220),
        (335, 300),
        (295, 365),
        (215, 365),
        (175, 300),
        (190, 220),
    ], fill=p)
    draw.polygon([
        (256, 200),
        (295, 260),
        (280, 340),
        (230, 340),
        (215, 260),
    ], fill=a)


def draw_chip(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Futuristic AI neural processor
    # Chip core
    draw.rectangle([196, 196, 316, 316], fill=p)
    draw.rectangle([226, 226, 286, 286], fill=a)
    # Outer pins (3 on each side)
    for offset in [220, 256, 292]:
        # Top
        draw.line([(offset, 196), (offset, 155)], fill=a, width=8)
        # Bottom
        draw.line([(offset, 316), (offset, 357)], fill=a, width=8)
        # Left
        draw.line([(196, offset), (155, offset)], fill=a, width=8)
        # Right
        draw.line([(316, offset), (357, offset)], fill=a, width=8)


def draw_crown(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Refined gentleman crest / crown
    pts = [
        (170, 230),
        (210, 320),
        (302, 320),
        (342, 230),
        (296, 265),
        (256, 180),
        (216, 265),
    ]
    draw.polygon(pts, fill=p)
    # Base ribbon
    draw.rectangle([190, 335, 322, 355], fill=a)


def draw_lotus(draw: ImageDraw.Draw, p: tuple, a: tuple):
    # Symmetrical zen lotus petals
    # Center petal
    draw.ellipse([236, 160, 276, 330], fill=a)
    # Left petal
    draw.ellipse([180, 210, 265, 335], fill=p)
    # Right petal
    draw.ellipse([247, 210, 332, 335], fill=p)
    # Base crescent
    draw.arc([180, 290, 332, 360], start=0, end=180, fill=a, width=6)


DRAW_FUNCS = {
    "cat": draw_cat,
    "paw": draw_paw,
    "bolt": draw_bolt,
    "pillar": draw_pillar,
    "chart": draw_chart,
    "rocket": draw_rocket,
    "flame": draw_flame,
    "chip": draw_chip,
    "crown": draw_crown,
    "lotus": draw_lotus,
}


def generate_logo(channel_id: str, cfg: dict) -> Path:
    size = (512, 512)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    p = cfg["primary"]
    a = cfg["accent"]
    bg = cfg["bg_dark"]

    # 1. Outer Circular Base with Solid Fill
    draw.ellipse([16, 16, 496, 496], fill=(*bg, 250))

    # 2. Outer Gradient Rings / Borders
    draw.ellipse([16, 16, 496, 496], outline=p, width=8)
    draw.ellipse([32, 32, 480, 480], outline=(*a, 80), width=3)
    draw.ellipse([44, 44, 468, 468], outline=(255, 255, 255, 30), width=2)

    # 3. Inner Decorative Ring
    draw.ellipse([80, 80, 432, 432], outline=(*p, 60), width=2)

    # 4. Draw Specific Iconic Emblem
    symbol = cfg["symbol"]
    func = DRAW_FUNCS.get(symbol)
    if func:
        func(draw, p, a)

    # 5. Bottom Circular Arch Accent Line
    draw.arc([100, 100, 412, 412], start=45, end=135, fill=p, width=4)

    out_file = OUTPUT_DIR / f"{channel_id}.png"
    img.save(out_file, "PNG")
    return out_file


def main():
    print(f"Generating professional circular logos in: {OUTPUT_DIR}")
    for cid, cfg in CHANNELS.items():
        p = generate_logo(cid, cfg)
        print(f"  * Generated: {p.name} ({cfg['title']})")
    print("\nAll 10 channel logos generated successfully!")


if __name__ == "__main__":
    main()
