#!/usr/bin/env python3
"""Generate the DMG background image (600×340, Retina @2x)."""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 680   # @2x for Retina (displayed as 600×340)


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(len(c1)))


def main(out_path: str):
    img = Image.new("RGB", (W, H))

    # Gradient background: very dark navy → deep slate
    top    = (10, 14, 30)
    bottom = (18, 10, 38)
    for y in range(H):
        t = y / H
        color = lerp_color(top, bottom, t)
        ImageDraw.Draw(img).line([(0, y), (W - 1, y)], fill=color)

    draw = ImageDraw.Draw(img)

    # Subtle grid lines
    grid_col = (30, 35, 60, 80)
    grid_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid_img)
    step = W // 12
    for x in range(0, W, step):
        gd.line([(x, 0), (x, H)], fill=(40, 50, 90, 40))
    for y2 in range(0, H, step):
        gd.line([(0, y2), (W, y2)], fill=(40, 50, 90, 40))
    img = Image.alpha_composite(img.convert("RGBA"), grid_img).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Waveform decoration (thin lines, faint)
    import math
    wave_col = (50, 100, 200, 45)
    wave_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wave_img)
    for i in range(3):
        amp   = 18 + i * 12
        freq  = 0.008 - i * 0.001
        off_y = H * 0.72 + i * 18
        pts   = []
        for x in range(0, W + 1, 2):
            y_val = off_y + math.sin(x * freq + i * 1.2) * amp
            pts.append((x, y_val))
        for j in range(len(pts) - 1):
            wd.line([pts[j], pts[j + 1]], fill=(*lerp_color((30, 80, 200), (0, 180, 255), j / W), 40), width=1)
    blur_wave = wave_img.filter(ImageFilter.GaussianBlur(radius=2))
    img = Image.alpha_composite(img.convert("RGBA"), blur_wave).convert("RGB")
    draw = ImageDraw.Draw(img)

    # App name text
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 52)
        font_sub   = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 28)
    except Exception:
        try:
            font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 52)
            font_sub   = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        except Exception:
            font_title = ImageFont.load_default()
            font_sub   = font_title

    title     = "MOSS TTS"
    subtitle  = "Drag to Applications to install"

    # Title — bright
    tw = draw.textlength(title, font=font_title) if hasattr(draw, "textlength") else 200
    draw.text(((W - tw) / 2, 40), title, font=font_title, fill=(220, 235, 255))

    # Subtitle — muted
    sw = draw.textlength(subtitle, font=font_sub) if hasattr(draw, "textlength") else 320
    draw.text(((W - sw) / 2, 108), subtitle, font=font_sub, fill=(100, 120, 180))

    # Arrow between app and Applications
    ax, ay = W // 2, H // 2 + 20
    arrow_col = (60, 100, 200)
    # Simple arrow →
    draw.line([(ax - 60, ay), (ax + 60, ay)], fill=arrow_col, width=3)
    draw.polygon([(ax + 60, ay - 10), (ax + 80, ay), (ax + 60, ay + 10)], fill=arrow_col)

    img.save(out_path)
    print(f"DMG background saved: {out_path} ({W}×{H})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dmg_bg.png")
