#!/usr/bin/env python3
"""Generate a polished MOSS TTS app icon at every required macOS size."""

import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZES = [16, 32, 64, 128, 256, 512, 1024]


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(len(c1)))


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size

    # ── Background rounded rect ──────────────────────────────────────────────
    margin = s * 0.04
    r = s * 0.22   # corner radius

    # Gradient: top-left = dark navy, bottom-right = deep slate
    bg = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    top_col    = (15, 20, 42)    # deep midnight blue
    bottom_col = (28, 15, 52)    # deep violet

    for y in range(s):
        t = y / s
        row_col = lerp_color(top_col, bottom_col, t)
        bg_draw.line([(0, y), (s - 1, y)], fill=(*row_col, 255))

    # Mask to rounded rect
    mask = Image.new("L", (s, s), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([margin, margin, s - margin, s - margin],
                                  radius=r, fill=255)
    img.paste(bg, (0, 0), mask)

    # ── Subtle inner highlight (top rim) ────────────────────────────────────
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rounded_rectangle(
        [margin, margin, s - margin, s * 0.55],
        radius=r,
        fill=(80, 100, 200, 18),
    )
    img = Image.alpha_composite(img, glow)

    # ── Waveform bars ────────────────────────────────────────────────────────
    # 7 bars in a balanced "mountain" profile
    bar_heights = [0.18, 0.35, 0.55, 0.78, 1.0, 0.68, 0.38, 0.22]
    n = len(bar_heights)

    total_bar_w = s * 0.62
    spacing     = total_bar_w / (n * 2 - 1)
    bar_w       = spacing * 1.0
    x_start     = (s - total_bar_w) / 2

    max_bar_h   = s * 0.46
    center_y    = s * 0.52

    for i, h_frac in enumerate(bar_heights):
        bh   = max_bar_h * h_frac
        bx   = x_start + i * (bar_w + spacing)
        by1  = center_y - bh
        by2  = center_y + bh
        br   = bar_w * 0.45    # bar corner radius

        # Per-bar gradient: cool blue → electric cyan
        t_horiz = i / (n - 1)
        top_bar  = lerp_color((50, 130, 255), (0, 220, 255), t_horiz)
        bot_bar  = lerp_color((30,  80, 200), (0, 160, 220), t_horiz)

        # Draw gradient bar via scanline
        bar_img  = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(bar_img)

        # Fill the bar shape with rounded caps
        bar_draw.rounded_rectangle(
            [bx, by1, bx + bar_w, by2],
            radius=br,
            fill=(*top_bar, 255),
        )
        # Overlay a gradient tint (lighter top, darker bottom)
        for row_y in range(int(by1), int(by2) + 1):
            tr = (row_y - by1) / max(by2 - by1, 1)
            row_col = lerp_color(top_bar, bot_bar, tr)
            bar_draw.line([(bx, row_y), (bx + bar_w, row_y)],
                          fill=(*row_col, 255))

        # Re-mask to rounded rect (gradient overwrote the mask)
        bar_mask = Image.new("L", (s, s), 0)
        bm_draw = ImageDraw.Draw(bar_mask)
        bm_draw.rounded_rectangle(
            [bx, by1, bx + bar_w, by2],
            radius=br,
            fill=255,
        )
        img = Image.alpha_composite(img, Image.composite(bar_img, Image.new("RGBA", (s, s), (0,0,0,0)), bar_mask))

    # ── Bar glow (bloom) ─────────────────────────────────────────────────────
    if size >= 64:
        bloom_layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        bloom_draw  = ImageDraw.Draw(bloom_layer)
        for i, h_frac in enumerate(bar_heights):
            bh  = max_bar_h * h_frac
            bx  = x_start + i * (bar_w + spacing)
            t_h = i / (n - 1)
            gc  = lerp_color((80, 160, 255), (0, 230, 255), t_h)
            bloom_draw.rounded_rectangle(
                [bx - bar_w * 0.3, center_y - bh - bar_w * 0.3,
                 bx + bar_w * 1.3, center_y + bh + bar_w * 0.3],
                radius=bar_w,
                fill=(*gc, 35),
            )
        bloom_blur = bloom_layer.filter(ImageFilter.GaussianBlur(radius=max(2, size // 40)))
        img = Image.alpha_composite(img, bloom_blur)

    # ── Outer border highlight ────────────────────────────────────────────────
    border = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bd     = ImageDraw.Draw(border)
    bw     = max(1, s // 180)
    bd.rounded_rectangle(
        [margin + bw, margin + bw, s - margin - bw, s - margin - bw],
        radius=r - bw,
        outline=(120, 160, 255, 45),
        width=bw,
    )
    img = Image.alpha_composite(img, border)

    return img


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("MossTTS.app/Contents/Resources/AppIcon.iconset")
    out_dir.mkdir(parents=True, exist_ok=True)

    for size in SIZES:
        icon = make_icon(size)
        # 1× slot
        if size <= 512:
            icon.save(out_dir / f"icon_{size}x{size}.png")
        # 2× slot (this size is the @2x for the half-size)
        if size >= 32:
            half = size // 2
            icon.save(out_dir / f"icon_{half}x{half}@2x.png")

    print(f"Icon PNGs written to {out_dir}  ({len(list(out_dir.glob('*.png')))} files)")


if __name__ == "__main__":
    main()
