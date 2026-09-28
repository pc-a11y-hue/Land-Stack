"""
Satellite change-detection module.

In a production Land Stack, this would pull real before/after satellite
tiles for a parcel and run a proper computer-vision change-detection model.
For this prototype (no external network access), we generate deterministic
synthetic "before" and "after" tiles per-parcel and run a genuine pixel-diff
algorithm against them.

Images are generated on first request and cached in memory so repeated
requests for the same parcel return the same pair.
"""

import hashlib
import io
import random

from PIL import Image, ImageDraw
import numpy as np

_CACHE = {}  # ulpin -> {"before": bytes, "after": bytes, "change_pct": float, "flag": bool}

TILE_SIZE = 220


def _seeded_random(ulpin):
    seed = int(hashlib.md5(ulpin.encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def _draw_base_terrain(draw, rnd, size):
    base_colors = [(120, 150, 90), (110, 140, 85), (130, 158, 95), (100, 130, 75)]
    cell = 14
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            color = rnd.choice(base_colors)
            draw.rectangle([x, y, x + cell, y + cell], fill=color)
    draw.line([(0, size), (size, 0)], fill=(90, 100, 70), width=2)


def _draw_building(draw, rnd, size, footprint_scale=1.0):
    w = int(rnd.randint(35, 55) * footprint_scale)
    h = int(rnd.randint(30, 50) * footprint_scale)
    x0 = rnd.randint(20, size - w - 20)
    y0 = rnd.randint(20, size - h - 20)
    draw.rectangle([x0, y0, x0 + w, y0 + h], fill=(150, 150, 155), outline=(90, 90, 95))
    draw.line([(x0, y0 + h // 2), (x0 + w, y0 + h // 2)], fill=(110, 110, 115), width=2)


def _generate_pair(ulpin, seed_unauthorized_change):
    rnd = _seeded_random(ulpin)
    before = Image.new("RGB", (TILE_SIZE, TILE_SIZE))
    d_before = ImageDraw.Draw(before)
    _draw_base_terrain(d_before, rnd, TILE_SIZE)

    rnd2 = _seeded_random(ulpin)
    after = Image.new("RGB", (TILE_SIZE, TILE_SIZE))
    d_after = ImageDraw.Draw(after)
    _draw_base_terrain(d_after, rnd2, TILE_SIZE)

    if seed_unauthorized_change:
        _draw_building(d_after, rnd2, TILE_SIZE)

    return before, after


def _to_png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _compute_change_pct(before_img, after_img):
    a = np.array(before_img).astype(np.int16)
    b = np.array(after_img).astype(np.int16)
    diff = np.abs(a - b).sum(axis=2)
    changed_pixels = int(np.count_nonzero(diff > 40))
    total_pixels = int(diff.shape[0] * diff.shape[1])
    return round(100 * changed_pixels / total_pixels, 2)


def get_satellite_analysis(ulpin, seed_unauthorized_change, zoning):
    if ulpin in _CACHE:
        return _CACHE[ulpin]

    before_img, after_img = _generate_pair(ulpin, seed_unauthorized_change)
    change_pct = _compute_change_pct(before_img, after_img)

    disallowed_zoning = zoning not in ("Residential", "Commercial")
    flag = bool(change_pct > 3.0 and disallowed_zoning)

    result = {
        "before_png": _to_png_bytes(before_img),
        "after_png": _to_png_bytes(after_img),
        "change_pct": change_pct,
        "flag": flag,
        "reason": (
            f"{change_pct}% of parcel area shows new structure on land zoned '{zoning}'"
            if flag else
            f"{change_pct}% change detected — within expected range for zoning '{zoning}'"
        ),
    }
    _CACHE[ulpin] = result
    return result
