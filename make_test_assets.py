#!/usr/bin/env python3

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

BASE = Path("/opt/pi-avatar/assets")
WIDTH = 800
HEIGHT = 480

STATES = {
    "idle": ("IDLE", "Resting", (30, 40, 70)),
    "thinking": ("THINKING", "Pondering", (60, 45, 90)),
    "working": ("WORKING", "Doing chores", (70, 55, 30)),
    "success": ("SUCCESS", "All done", (35, 75, 45)),
    "error": ("ERROR", "Something broke", (90, 35, 35)),
    "offline": ("OFFLINE", "No signal", (25, 25, 25)),
    "booting": ("BOOTING", "Waking up", (30, 60, 80)),
}

def get_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

title_font = get_font(46)
small_font = get_font(26)

for state, (title, subtitle, bg) in STATES.items():
    folder = BASE / state
    folder.mkdir(parents=True, exist_ok=True)

    for i in range(8):
        img = Image.new("RGB", (WIDTH, HEIGHT), bg)
        draw = ImageDraw.Draw(img)

        # Simple subtle background grid
        for x in range(0, WIDTH, 40):
            draw.line((x, 0, x, HEIGHT), fill=tuple(min(255, c + 10) for c in bg))
        for y in range(0, HEIGHT, 40):
            draw.line((0, y, WIDTH, y), fill=tuple(min(255, c + 10) for c in bg))

        # Avatar body
        bob = int(math.sin(i / 8 * math.tau) * 8)
        cx = WIDTH // 2
        cy = HEIGHT // 2 - 10 + bob

        body_color = (220, 220, 220)
        face_color = (245, 245, 245)
        outline = (20, 20, 20)

        draw.ellipse((cx - 95, cy - 95, cx + 95, cy + 95), fill=body_color, outline=outline, width=5)
        draw.ellipse((cx - 70, cy - 65, cx + 70, cy + 75), fill=face_color, outline=outline, width=4)

        # Eyes
        blink = state == "idle" and i in (3, 4)
        if blink:
            draw.line((cx - 38, cy - 15, cx - 18, cy - 15), fill=outline, width=5)
            draw.line((cx + 18, cy - 15, cx + 38, cy - 15), fill=outline, width=5)
        else:
            draw.ellipse((cx - 43, cy - 25, cx - 23, cy - 5), fill=outline)
            draw.ellipse((cx + 23, cy - 25, cx + 43, cy - 5), fill=outline)

        # Mouth / expression
        if state == "error":
            draw.arc((cx - 35, cy + 25, cx + 35, cy + 70), 200, 340, fill=outline, width=5)
            draw.text((cx + 88, cy - 95), "!", font=title_font, fill=(255, 230, 120))
        elif state == "success":
            draw.arc((cx - 35, cy + 5, cx + 35, cy + 55), 20, 160, fill=outline, width=5)
            draw.text((cx + 90, cy - 95), "✓", font=title_font, fill=(170, 255, 170))
        elif state == "working":
            draw.line((cx - 25, cy + 35, cx + 25, cy + 35), fill=outline, width=5)
            draw.text((cx + 90, cy - 95), "⚙", font=title_font, fill=(255, 220, 140))
        elif state == "thinking":
            draw.ellipse((cx - 18, cy + 28, cx + 18, cy + 42), outline=outline, width=5)
            draw.text((cx + 88, cy - 95), "?", font=title_font, fill=(220, 220, 255))
        elif state == "offline":
            draw.line((cx - 30, cy + 30, cx + 30, cy + 30), fill=outline, width=5)
            draw.text((cx + 90, cy - 95), "Z", font=title_font, fill=(170, 170, 170))
        else:
            draw.arc((cx - 30, cy + 10, cx + 30, cy + 50), 20, 160, fill=outline, width=5)

        # Labels
        title_box = draw.textbbox((0, 0), title, font=title_font)
        title_w = title_box[2] - title_box[0]
        draw.text(((WIDTH - title_w) // 2, 36), title, font=title_font, fill=(255, 255, 255))

        sub_box = draw.textbbox((0, 0), subtitle, font=small_font)
        sub_w = sub_box[2] - sub_box[0]
        draw.text(((WIDTH - sub_w) // 2, HEIGHT - 62), subtitle, font=small_font, fill=(230, 230, 230))

        img.save(folder / f"{i:02d}.png")

print("Generated placeholder avatar assets.")
