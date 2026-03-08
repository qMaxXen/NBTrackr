import os
import json
import math
import tkinter as tk
import tkinter.font as tkFont
import subprocess
import threading
import time
import colorsys
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk

CUSTOM_PATH = os.path.expanduser("~/.config/NBTrackr/customizations.json")
BUNDLED_FONT_DISPLAY = "LiberationSans-Bold (Bundled)"
BUNDLED_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "LiberationSans", "LiberationSans-Bold.ttf")

DEFAULT_CUSTOMIZATIONS = {
    "use_custom_pinned_image": False,
    "shown_measurements": 5,
    "overworld_coords_format": "four_four",
    "angle_display_mode": "angle_and_change",
    "show_angle_adjustment_count": False,
    "show_angle_error": False,
    "show_overlay_header": True,
    "show_coords_based_on_dimension": False,
    "show_boat_icon": True,
    "show_error_message": True,
    "boat_info_hide_after": 10,
    "boat_info_hide_after_enabled": True,
    "show_blind_info": True,
    "blind_info_hide_after": 20,
    "blind_info_hide_after_enabled": False,
    "font_name": os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "LiberationSans", "LiberationSans-Bold.ttf"),
    "font_size": 18,
    "background_color": "#000000",
    "text_color": "#FFFFFF",
    "negative_coords_color_enabled": True,
    "negative_coords_color": "#BA6669",
    "portal_nether_color_enabled": True,
    "portal_nether_color": "#FFA500",
    "text_order": [
        "overworld_coords",
        "certainty_percentage",
        "distance",
        "nether_coords",
        "angle"
    ],
    "text_enabled": {
        "distance": True,
        "certainty_percentage": True,
        "angle": True,
        "overworld_coords": True,
        "nether_coords": True
    },
    "text_header": {
        "distance": "Text",
        "certainty_percentage": "Text",
        "angle": "Text",
        "overworld_coords": "Text",
        "nether_coords": "Text"
    },
    "debug_mode": False,
    "idle_api_polling_rate": 0.2,
    "max_api_polling_rate": 0.05
}

DISPLAY_NAMES = {
    "distance": "Distance",
    "certainty_percentage": "Certainty Percentage",
    "angle": "Angle",
    "overworld_coords": "Overworld Coords",
    "nether_coords": "Nether Coords"
}

def _hex_to_rgb(hexstr, fallback=(0, 0, 0)):
    try:
        s = hexstr.strip().lstrip("#")
        if len(s) != 6:
            return fallback
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback

def _certainty_color(pct: float):
    pct = max(0.0, min(100.0, pct))
    return _gradient_color((100 - pct) * 1.8)

def _gradient_color(angle: float):
    if angle <= 90:
        t = angle / 90.0
        red   = int(255 * t)
        green = 255
        return (red, green, 0)
    t = (angle - 90) / 90.0
    red   = 255
    green = int(255 * (1 - t))
    return (red, green, 0)

def _blind_eval_color(evaluation):
    return {
        'EXCELLENT':        (0, 255, 0),
        'HIGHROLL_GOOD':    (100, 255, 100),
        'HIGHROLL_OKAY':    (114, 214, 2),
        'BAD_BUT_IN_RING':  (222, 220, 3),
        'BAD':              (255, 100, 0),
        'NOT_IN_RING':      (255, 0, 0),
    }.get(evaluation, (255, 255, 255))

def _format_blind_eval(evaluation):
    return {
        'EXCELLENT':        'excellent',
        'HIGHROLL_GOOD':    'good for highroll',
        'HIGHROLL_OKAY':    'okay for highroll',
        'BAD_BUT_IN_RING':  'bad, but in ring',
        'BAD':              'bad',
        'NOT_IN_RING':      'not in any ring',
    }.get(evaluation, evaluation)

ADJ_POS  = (117, 204, 108)
ADJ_NEG  = (204, 110, 114)

NB_BG           = (55,  60,  66,  255)
NB_HEADER_BG    = (45,  50,  56,  255)
NB_HEADER_FG    = (229, 229, 229)
NB_ROW_ODD      = (55,  60,  66,  255)
NB_ROW_EVEN     = (55,  60,  66,  255)
NB_BORDER       = (33,  37,  41,  255)
NB_TEXT         = (255, 255, 255)
NB_THROW_HDR_FG = (192, 192, 192)

_RED_HEX   = (189, 65,  65)
_YELLOW    = (216, 192, 100)
_GREEN_HEX = (89,  185, 75)

def _interp(c1, c2, steps, step):
    r = int(c1[0] + (c2[0] - c1[0]) * step / max(steps - 1, 1))
    g = int(c1[1] + (c2[1] - c1[1]) * step / max(steps - 1, 1))
    b = int(c1[2] + (c2[2] - c1[2]) * step / max(steps - 1, 1))
    return (r, g, b)

def _nb_cert_color(pct):
    if pct >= 50:
        return _interp(_YELLOW, _GREEN_HEX, 51, int(pct - 50))
    return _interp(_RED_HEX, _YELLOW, 51, int(pct))

def _nb_dir_color(direction):
    abs_dir = abs(direction)
    if abs_dir <= 180:
        return _interp(_RED_HEX, _GREEN_HEX, 181, int(180 - abs_dir))
    return _YELLOW

def _load_preview_font(font_name, font_size):
    font = None
    if font_name:
        try:
            font = ImageFont.truetype(font_name, font_size)
            return font
        except Exception:
            pass
    _default_font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "LiberationSans", "LiberationSans-Bold.ttf")
    try:
        return ImageFont.truetype(_default_font_path, font_size)
    except Exception:
        pass
    return ImageFont.load_default()

def _load_nb_preview_font(font_size):
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "LiberationSans", "LiberationSans-Bold.ttf")
    try:
        return ImageFont.truetype(font_path, font_size)
    except Exception:
        pass
    return ImageFont.load_default()

PREVIEW_EYE_DATA = [
    {"chunkX": -149, "chunkZ": -77, "certainty": 0.999, "overworldDistance": 2992.0},
    {"chunkX": -148, "chunkZ": -84, "certainty": 0.001, "overworldDistance": 2879.0},
    {"chunkX": -124, "chunkZ": -254, "certainty": 0.000, "overworldDistance": 132.0},
    {"chunkX": -147, "chunkZ": -91, "certainty": 0.000, "overworldDistance": 2766.0},
    {"chunkX": -146, "chunkZ": -98, "certainty": 0.000, "overworldDistance": 2653.0},
]
PREVIEW_PLAYER = {"xInOverworld": -1957.0, "zInOverworld": -4190.3,
                  "horizontalAngle": 8.05, "isInNether": False}
PREVIEW_EYE_THROWS = [
    {"xInOverworld": -1954, "zInOverworld": -4197, "angle": 10.05, "error": 0.0021},
    {"xInOverworld": -1955, "zInOverworld": -4190, "angle": 9.01, "error": 0.0034},
    {"xInOverworld": -1957, "zInOverworld": -4190, "angle": 8.04, "error": -0.0008},
]

def render_default_preview(settings: dict) -> Image.Image:
    CELL_PAD_MAIN = 3
    HDR_SEP_PX    = 1

    try:
        font_size = int(settings.get("font_size", 18))
    except Exception:
        font_size = 18

    neg_coords_enabled = settings.get("negative_coords_color_enabled", False)
    neg_coords_rgb     = _hex_to_rgb(settings.get("negative_coords_color", "#BA6669"), (186, 102, 105))
    ow_coords_format   = settings.get("overworld_coords_format", "four_four")

    font       = _load_nb_preview_font(font_size)
    small_font = _load_nb_preview_font(max(8, int(font_size * 0.85)))

    dummy_img  = Image.new("RGBA", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)

    def tw(text, fnt=font):
        return dummy_draw.textbbox((0, 0), text, font=fnt)[2]

    def th(fnt=font):
        a, d = fnt.getmetrics()
        return a + d

    def th_full(fnt=font):
        a, d = fnt.getmetrics()
        return a + d

    body_h  = th(font)       + 4
    hdr_h   = th(font)       + 4
    small_h = th(small_font) + 2
    ROW_SEP = 1

    a_new, d_new = font.getmetrics()
    NB_NEW_HDR_H = a_new + d_new + 8

    preds     = PREVIEW_EYE_DATA
    player_x  = PREVIEW_PLAYER["xInOverworld"]
    player_z  = PREVIEW_PLAYER["zInOverworld"]
    h_ang     = PREVIEW_PLAYER["horizontalAngle"]
    in_nether = PREVIEW_PLAYER["isInNether"]

    loc_label = "Chunk" if ow_coords_format == "chunk" else "Location"
    col_keys  = ["loc", "cert", "dist", "nether", "angle"]
    hdr_labels = {"loc": loc_label, "cert": "%", "dist": "Dist.", "nether": "Nether", "angle": "Angle"}

    _rep_samples = {
        "loc":    f"({12345}, {12345})",
        "cert":   "100.0%",
        "dist":   "10000",
        "nether": f"({12345}, {12345})",
        "angle":  "180.0 (-> 180.0)",
    }

    rows = []
    for pred in preds:
        cx, cz = pred["chunkX"], pred["chunkZ"]
        cert   = pred["certainty"]
        dist   = pred["overworldDistance"]

        if ow_coords_format == "chunk":
            ox, oz = cx, cz
        elif ow_coords_format == "eight_eight":
            ox, oz = cx * 16 + 8, cz * 16 + 8
        else:
            ox, oz = cx * 16 + 4, cz * 16 + 4

        nx, nz = round((cx * 16 + 4) / 8), round((cz * 16 + 4) / 8)
        cert_pct  = cert * 100
        dist_disp = int(dist)

        sx, sz = cx * 16 + 4, cz * 16 + 4
        dx, dz = sx - player_x, sz - player_z
        tgt    = (math.degrees(math.atan2(dz, dx)) + 270) % 360
        signed = ((tgt + 180) % 360) - 180
        turn   = ((tgt - (h_ang % 360) + 180) % 360) - 180

        rows.append({
            "loc":      (ox, oz),
            "cert_pct": cert_pct,
            "dist":     dist_disp,
            "nether":   (nx, nz),
            "angle":    f"{signed:.1f}",
            "dir":      turn,
        })

    col_widths = {}
    for key in col_keys:
        col_widths[key] = max(
            tw(hdr_labels[key]) + CELL_PAD_MAIN * 2,
            tw(_rep_samples.get(key, "")) + CELL_PAD_MAIN * 2,
        )

    for r in rows:
        col_widths["loc"]    = max(col_widths["loc"],
                                   tw(f"({r['loc'][0]}, {r['loc'][1]})") + CELL_PAD_MAIN * 2)
        col_widths["cert"]   = max(col_widths["cert"],
                                   tw(f"{r['cert_pct']:.1f}%") + CELL_PAD_MAIN * 2)
        col_widths["dist"]   = max(col_widths["dist"],
                                   tw(str(r['dist'])) + CELL_PAD_MAIN * 2)
        col_widths["nether"] = max(col_widths["nether"],
                                   tw(f"({r['nether'][0]}, {r['nether'][1]})") + CELL_PAD_MAIN * 2)
        angle_full = r['angle'] + f" ({'-> ' if r['dir'] > 0 else '<- '}{abs(r['dir']):.1f})"
        col_widths["angle"]  = max(col_widths["angle"],
                                   tw(angle_full) + CELL_PAD_MAIN * 2)

    throw_headers = ["x", "z", "Angle", "Error"]
    throw_col_widths = [tw(h, small_font) + 14 * 2 for h in throw_headers]
    for trow in PREVIEW_EYE_THROWS:
        cells = [str(int(trow["xInOverworld"])), str(int(trow["zInOverworld"])),
                 f"{trow['angle']:.1f}", f"{trow['error']:.4f}"]
        for i, cell in enumerate(cells):
            throw_col_widths[i] = max(throw_col_widths[i], tw(cell, small_font) + 14 * 2)

    main_table_w = sum(col_widths[k] for k in col_keys)
    throw_total  = sum(throw_col_widths)
    img_w        = max(main_table_w, throw_total)

    if main_table_w < img_w:
        extra = img_w - main_table_w
        per_col = extra // len(col_keys)
        for k in col_keys:
            col_widths[k] += per_col
        col_widths[col_keys[-1]] += img_w - sum(col_widths[k] for k in col_keys)

    leftover = img_w - sum(throw_col_widths)
    if leftover > 0:
        ob = int(leftover * 0.20)
        cb = int(leftover * 0.30)
        throw_col_widths[0] += ob
        throw_col_widths[1] += cb
        throw_col_widths[2] += cb
        throw_col_widths[3] += ob
        diff = img_w - sum(throw_col_widths)
        throw_col_widths[3] += diff

    num_rows      = len(rows)
    num_throw_rows = len(PREVIEW_EYE_THROWS)

    main_h  = (NB_NEW_HDR_H + HDR_SEP_PX
               + HDR_SEP_PX + hdr_h + HDR_SEP_PX
               + num_rows * body_h + num_rows * ROW_SEP)
    throw_h = HDR_SEP_PX + hdr_h + small_h + HDR_SEP_PX + num_throw_rows * (body_h + ROW_SEP)
    img_h   = main_h + throw_h

    NEW_HEADER_BG_C  = (0x21, 0x25, 0x29, 255)
    NB_HDR_SEP_C     = (33,  37,  41,  255)
    NB_HEADER_BG_C   = (45,  50,  56,  255)
    NB_ROW_BG_C      = (55,  60,  66,  255)
    NB_TEXT_C        = (255, 255, 255)
    NB_VER_FG_C      = (0x80, 0x80, 0x80)
    NB_ROW_SEP_C     = (42,  46,  50,  255)
    NB_THROW_HDR_FG_C= (192, 192, 192)

    img  = Image.new("RGBA", (img_w, img_h), NB_ROW_BG_C)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w - 1, NB_NEW_HDR_H - 1], fill=NEW_HEADER_BG_C)
    draw.text((CELL_PAD_MAIN + 4, (NB_NEW_HDR_H - th()) // 2),
              "NBTrackr", font=font, fill=NB_TEXT_C)
    ver_text = "(preview)"
    ver_x    = CELL_PAD_MAIN + 4 + tw("NBTrackr") + 8
    a_t, _   = font.getmetrics()
    a_v, _   = small_font.getmetrics()
    ver_y    = (NB_NEW_HDR_H - th()) // 2 + a_t - a_v
    draw.text((ver_x, ver_y), ver_text, font=small_font, fill=NB_VER_FG_C)

    _bp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "boat_green_icon.png")
    try:
        _isz = NB_NEW_HDR_H - 8
        with Image.open(_bp) as _bi:
            _bi = _bi.convert("RGBA").resize((_isz, _isz), Image.Resampling.LANCZOS)
            _icon_x = img_w - _isz - 20
            _icon_y = (NB_NEW_HDR_H - _isz) // 2
            img.alpha_composite(_bi, (_icon_x, _icon_y))
    except Exception:
        pass

    y0 = NB_NEW_HDR_H
    draw.rectangle([0, y0, img_w - 1, y0 + HDR_SEP_PX - 1], fill=NB_HDR_SEP_C)

    col_hdr_y0 = y0 + HDR_SEP_PX
    draw.rectangle([0, col_hdr_y0, img_w - 1, col_hdr_y0 + HDR_SEP_PX - 1], fill=NB_HDR_SEP_C)

    col_hdr_start = col_hdr_y0 + HDR_SEP_PX
    draw.rectangle([0, col_hdr_start, img_w - 1, col_hdr_start + hdr_h - 1], fill=NB_HEADER_BG_C)
    x = 0
    for key in col_keys:
        cw  = col_widths[key]
        lbl = hdr_labels[key]
        lw  = tw(lbl)
        if key == "angle":
            rep_base  = tw("000.00")
            rep_dir   = tw(" (-> 000.0)")
            rep_full  = rep_base + rep_dir
            cell_bx   = x + (cw - rep_full) // 2
            dir_start = cell_bx + rep_base
            text_x    = dir_start + (rep_dir - lw) // 2
            text_x    = max(x, min(text_x, x + cw - lw))
        else:
            text_x = x + (cw - lw) // 2
        draw.text((text_x, col_hdr_start + (hdr_h - th()) // 2), lbl, font=font, fill=NB_TEXT_C)
        x += cw

    sep_below_hdr = col_hdr_start + hdr_h
    draw.rectangle([0, sep_below_hdr, img_w - 1, sep_below_hdr + HDR_SEP_PX - 1], fill=NB_HDR_SEP_C)

    row_area_y = sep_below_hdr + HDR_SEP_PX

    for row_idx, r in enumerate(rows):
        y = row_area_y + row_idx * (body_h + ROW_SEP)
        draw.rectangle([0, y, img_w - 1, y + body_h - 1], fill=NB_ROW_BG_C)
        if row_idx < num_rows - 1:
            draw.rectangle([0, y + body_h, img_w - 1, y + body_h + ROW_SEP - 1], fill=NB_ROW_SEP_C)

        a_body, d_body = font.getmetrics()
        text_y = y + (body_h - (a_body + d_body)) // 2
        x = 0

        def draw_cell(key, text, fill=NB_TEXT_C, fnt=font):
            nonlocal x
            cw  = col_widths[key]
            tw_ = dummy_draw.textbbox((0, 0), text, font=fnt)[2]
            draw.text((x + (cw - tw_) // 2, text_y), text, font=fnt, fill=fill)
            x += cw

        def draw_coord_cell(key, coord_pair):
            nonlocal x
            cw      = col_widths[key]
            cx_v, cz_v = coord_pair
            parts   = [
                ("(", NB_TEXT_C),
                (str(cx_v), neg_coords_rgb if neg_coords_enabled and cx_v < 0 else NB_TEXT_C),
                (", ", NB_TEXT_C),
                (str(cz_v), neg_coords_rgb if neg_coords_enabled and cz_v < 0 else NB_TEXT_C),
                (")", NB_TEXT_C),
            ]
            full_w = sum(tw(p[0]) for p in parts)
            bx = x + (cw - full_w) // 2
            for pt, pc in parts:
                draw.text((bx, text_y), pt, font=font, fill=pc)
                bx += tw(pt)
            x += cw

        draw_coord_cell("loc", r['loc'])
        draw_cell("cert", f"{r['cert_pct']:.1f}%", fill=_certainty_color(r['cert_pct']))
        draw_cell("dist", str(r['dist']))
        draw_coord_cell("nether", r['nether'])

        lx = x; cw = col_widths["angle"]
        base_str = r['angle']
        arrow    = "->" if r['dir'] > 0 else "<-"
        dir_part = f" ({arrow} {abs(r['dir']):.1f})"
        dir_col  = _gradient_color(abs(r['dir']))
        full_w   = tw(base_str) + tw(dir_part)
        bx       = lx + (cw - full_w) // 2
        draw.text((bx, text_y), base_str, font=font, fill=NB_TEXT_C)
        draw.text((bx + tw(base_str), text_y), dir_part, font=font, fill=dir_col)
        x += cw

    throw_base_y = main_h
    draw.rectangle([0, throw_base_y, img_w - 1, throw_base_y + HDR_SEP_PX - 1], fill=NB_HDR_SEP_C)

    th_title_y = throw_base_y + HDR_SEP_PX
    draw.rectangle([0, th_title_y, img_w - 1, th_title_y + hdr_h - 1], fill=NB_HEADER_BG_C)
    draw.text((CELL_PAD_MAIN + 6, th_title_y + (hdr_h - th()) // 2),
              "Ender eye throws", font=font, fill=NB_TEXT_C)

    th_hdr_y = th_title_y + hdr_h
    draw.rectangle([0, th_hdr_y, img_w - 1, th_hdr_y + small_h - 1], fill=NB_HEADER_BG_C)
    x = 0
    for i, thdr in enumerate(throw_headers):
        cw = throw_col_widths[i]
        lw = tw(thdr, small_font)
        ty = th_hdr_y + (small_h - th(small_font)) // 2
        draw.text((x + (cw - lw) // 2, ty), thdr, font=small_font, fill=NB_TEXT_C)
        x += cw

    sep2_y = th_hdr_y + small_h
    draw.rectangle([0, sep2_y, img_w - 1, sep2_y + HDR_SEP_PX - 1], fill=NB_HDR_SEP_C)

    for ti, trow in enumerate(PREVIEW_EYE_THROWS):
        ty  = sep2_y + HDR_SEP_PX + ti * (body_h + ROW_SEP)
        if ti < num_throw_rows - 1:
            draw.rectangle([0, ty + body_h, img_w - 1, ty + body_h + ROW_SEP - 1], fill=NB_ROW_SEP_C)
        x = 0
        cells = [str(int(trow["xInOverworld"])), str(int(trow["zInOverworld"])),
                 f"{trow['angle']:.1f}", f"{trow['error']:.4f}"]
        for i, cell in enumerate(cells):
            cw  = throw_col_widths[i]
            cw_ = tw(cell, small_font)
            a_s, d_s = small_font.getmetrics()
            sy  = ty + (body_h - (a_s + d_s)) // 2
            draw.text((x + (cw - cw_) // 2, sy), cell, font=small_font, fill=NB_THROW_HDR_FG_C)
            x += cw

    return img

def render_default_blind_preview() -> Image.Image:
    font_size = 18
    font       = _load_nb_preview_font(font_size)
    small_font = _load_nb_preview_font(max(8, int(font_size * 0.85)))

    dummy_img  = Image.new("RGBA", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)

    def tw(text, fnt=font):
        return dummy_draw.textbbox((0, 0), text, font=fnt)[2]

    def th(fnt=font):
        a, d = fnt.getmetrics()
        return a + d

    body_h  = th(font)       + 4
    hdr_h   = th(font)       + 4
    small_h = th(small_font) + 2
    HDR_SEP = 1
    ROW_SEP = 1
    CELL_PAD = 3

    NEW_HEADER_BG  = (0x21, 0x25, 0x29, 255)
    NB_HDR_SEP_C   = (33, 37, 41, 255)
    NB_HEADER_BG_C = (45, 50, 56, 255)
    NB_ROW_BG_C    = (55, 60, 66, 255)
    NB_TEXT_C      = (255, 255, 255)
    NB_VER_FG      = (0x80, 0x80, 0x80)

    a_new, d_new = font.getmetrics()
    new_header_h = a_new + d_new + 8

    br = PREVIEW_BLIND
    evaluation      = br["evaluation"]
    x_nether        = br["xInNether"]
    z_nether        = br["zInNether"]
    highroll_prob   = br["highrollProbability"] * 100
    highroll_thresh = br["highrollThreshold"]
    improve_deg     = math.degrees(br["improveDirection"])
    improve_dist    = br["improveDistance"]

    eval_text = _format_blind_eval(evaluation)
    _prefix   = f"Blind coords ({round(x_nether)}, {round(z_nether)}) are "
    _l2p      = f"{highroll_prob:.1f}%"
    _l2s      = f" chance of <{int(highroll_thresh)} block blind"
    _l3       = f"Head {improve_deg:.0f}°, {round(improve_dist)} blocks away, for better coords."

    eval_color = _blind_eval_color(evaluation)

    num_display_rows = 5
    col_keys   = ["loc", "cert", "dist", "nether", "angle"]
    hdr_labels = {"loc": "Location", "cert": "%", "dist": "Dist.", "nether": "Nether", "angle": "Angle"}

    col_widths = {k: tw(hdr_labels[k]) + CELL_PAD * 2 for k in col_keys}

    samples = {
        "loc":    "(12345, 12345)",
        "cert":   "100.0%",
        "dist":   "10000",
        "nether": "(12345, 12345)",
        "angle":  "180.0 (-> 180.0)",
    }
    for k, s in samples.items():
        col_widths[k] = max(col_widths[k], tw(s) + CELL_PAD * 2)

    min_blind_w = max(tw(_prefix) + tw(eval_text), tw(_l2p) + tw(_l2s), tw(_l3)) + CELL_PAD * 2

    main_table_w = sum(col_widths[k] for k in col_keys)
    img_w = max(main_table_w, min_blind_w)

    if main_table_w < img_w:
        extra = img_w - main_table_w
        per_col = extra // len(col_keys)
        for k in col_keys:
            col_widths[k] += per_col
        col_widths[col_keys[-1]] += img_w - sum(col_widths[k] for k in col_keys)

    throw_headers = ["x", "z", "Angle", "Error"]
    throw_col_widths = [tw(h, small_font) + 14 * 2 for h in throw_headers]
    throw_samples = ["12345.67", "12345.67", "180.0", "0.0000"]
    for i, s in enumerate(throw_samples):
        throw_col_widths[i] = max(throw_col_widths[i], tw(s, small_font) + 14 * 2)

    leftover = img_w - sum(throw_col_widths)
    if leftover > 0:
        ob = int(leftover * 0.20)
        cb = int(leftover * 0.30)
        throw_col_widths[0] += ob
        throw_col_widths[1] += cb
        throw_col_widths[2] += cb
        throw_col_widths[3] += ob
        diff = img_w - sum(throw_col_widths)
        throw_col_widths[3] += diff

    num_throw_rows = 3
    main_h = (new_header_h + HDR_SEP + HDR_SEP + hdr_h + HDR_SEP
              + num_display_rows * body_h)
    throw_h = HDR_SEP + hdr_h + small_h + HDR_SEP + num_throw_rows * (body_h + ROW_SEP)
    img_h   = main_h + throw_h

    img  = Image.new("RGBA", (img_w, img_h), NB_ROW_BG_C)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w - 1, new_header_h - 1], fill=NEW_HEADER_BG)
    draw.text((CELL_PAD + 4, (new_header_h - th()) // 2), "NBTrackr", font=font, fill=NB_TEXT_C)
    ver_x = CELL_PAD + 4 + tw("NBTrackr") + 8
    a_t, _ = font.getmetrics(); a_v, _ = small_font.getmetrics()
    ver_y = (new_header_h - th()) // 2 + a_t - a_v
    draw.text((ver_x, ver_y), "(preview)", font=small_font, fill=NB_VER_FG)

    _bp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "boat_gray_icon.png")
    try:
        _isz = new_header_h - 4
        with Image.open(_bp) as _bi:
            _bi = _bi.convert("RGBA").resize((_isz, _isz), Image.Resampling.LANCZOS)
            img.alpha_composite(_bi, (img_w - _isz - 4, (new_header_h - _isz) // 2))
    except Exception:
        pass

    draw.rectangle([0, new_header_h, img_w - 1, new_header_h + HDR_SEP - 1], fill=NB_HDR_SEP_C)

    col_hdr_y0 = new_header_h + HDR_SEP
    draw.rectangle([0, col_hdr_y0, img_w - 1, col_hdr_y0 + HDR_SEP - 1], fill=NB_HDR_SEP_C)

    col_hdr_start = col_hdr_y0 + HDR_SEP

    draw.rectangle([0, col_hdr_start + hdr_h, img_w - 1, col_hdr_start + hdr_h + HDR_SEP - 1], fill=NB_HDR_SEP_C)

    row_area_y = col_hdr_start + hdr_h + HDR_SEP



    txt_x = CELL_PAD
    txt_y = new_header_h + HDR_SEP + (body_h - th()) // 2
    lsep  = body_h
    draw.text((txt_x, txt_y), _prefix, font=font, fill=NB_TEXT_C)
    draw.text((txt_x + tw(_prefix), txt_y), eval_text, font=font, fill=eval_color)
    draw.text((txt_x, txt_y + lsep), _l2p, font=font, fill=eval_color)
    draw.text((txt_x + tw(_l2p), txt_y + lsep), _l2s, font=font, fill=NB_TEXT_C)
    draw.text((txt_x, txt_y + lsep * 2), _l3, font=font, fill=NB_TEXT_C)

    throw_base_y = main_h
    draw.rectangle([0, throw_base_y, img_w - 1, throw_base_y + HDR_SEP - 1], fill=NB_HDR_SEP_C)
    th_title_y = throw_base_y + HDR_SEP
    draw.rectangle([0, th_title_y, img_w - 1, th_title_y + hdr_h - 1], fill=NB_HEADER_BG_C)
    draw.text((CELL_PAD + 6, th_title_y + (hdr_h - th()) // 2), "Ender eye throws", font=font, fill=NB_TEXT_C)
    th_hdr_y = th_title_y + hdr_h
    draw.rectangle([0, th_hdr_y, img_w - 1, th_hdr_y + small_h - 1], fill=NB_HEADER_BG_C)
    x = 0
    for i, thdr in enumerate(throw_headers):
        cw = throw_col_widths[i]
        lw = tw(thdr, small_font)
        ty2 = th_hdr_y + (small_h - th(small_font)) // 2
        draw.text((x + (cw - lw) // 2, ty2), thdr, font=small_font, fill=NB_TEXT_C)
        x += cw
    sep2_y = th_hdr_y + small_h
    draw.rectangle([0, sep2_y, img_w - 1, sep2_y + HDR_SEP - 1], fill=NB_HDR_SEP_C)

    for ti in range(num_throw_rows):
        ty = sep2_y + HDR_SEP + ti * (body_h + ROW_SEP)
        if ti < num_throw_rows - 1:
            draw.rectangle([0, ty + body_h, img_w - 1, ty + body_h + ROW_SEP - 1],
                           fill=(42, 46, 50, 255))

    return img

def render_eye_throws_preview(settings: dict) -> Image.Image:
    bg_hex   = settings.get("background_color", "#000000")
    text_hex = settings.get("text_color", "#FFFFFF")
    bg_rgb      = _hex_to_rgb(bg_hex, (255, 255, 255))
    text_rgb    = _hex_to_rgb(text_hex, (0, 0, 0))
    neg_coords_enabled = settings.get("negative_coords_color_enabled", False)
    neg_coords_rgb     = _hex_to_rgb(settings.get("negative_coords_color", "#BA6669"), (204, 110, 114))
    portal_dist_enabled = settings.get("portal_nether_color_enabled", False)
    portal_dist_rgb     = _hex_to_rgb(settings.get("portal_nether_color", "#FFA500"), (255, 165, 0))
    bg_rgba     = (*bg_rgb, 255)

    shown_count = settings.get("shown_measurements", 1)
    order       = settings.get("text_order", ["distance", "certainty_percentage", "angle",
                                               "overworld_coords", "nether_coords"])
    enabled     = settings.get("text_enabled", {k: True for k in order})
    show_dir    = settings.get("show_angle_direction", True)
    show_adj          = settings.get("show_angle_adjustment_count", False)
    show_angle_error  = settings.get("show_angle_error", False)
    angle_display_mode = settings.get("angle_display_mode", "angle_and_change")
    in_nether   = PREVIEW_PLAYER["isInNether"]
    font_name   = settings.get("font_name", "")
    font_size   = settings.get("font_size", 18)
    show_coords_by_dim = settings.get("show_coords_based_on_dimension", False)
    ow_coords_format   = settings.get("overworld_coords_format", "four_four")

    font = _load_preview_font(font_name, font_size)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 6
    text_header = settings.get("text_header", {})
    HEADER_LABELS = {
        "distance": "Dist.",
        "certainty_percentage": "%",
        "angle": "Angle",
        "overworld_coords": "Chunk" if settings.get("overworld_coords_format", "four_four") == "chunk" else "Location",
        "nether_coords": "Nether",
    }

    preds = PREVIEW_EYE_DATA[:shown_count]
    player_x = PREVIEW_PLAYER["xInOverworld"]
    player_z = PREVIEW_PLAYER["zInOverworld"]
    h_ang    = PREVIEW_PLAYER["horizontalAngle"]

    if show_adj:
        adj_count_overlays = [
            ("100.21", "+2", 2),
            ("98.43", "-1", -1),
            ("99.00", None, None)
        ]
    else:
        adj_count_overlays = []
    angle_error_overlays = [
        ("0.0002",),
        ("-0.0015",),
        ("0.0034",)
    ] if show_angle_error else []
    n_bottom_rows  = max(len(adj_count_overlays), len(angle_error_overlays))
    _portal_link_flags = []
    if portal_dist_enabled and PREVIEW_EYE_THROWS:
        _ft = PREVIEW_EYE_THROWS[0]
        _approx_nx = (_ft.get("xInOverworld") or 0.0) / 8.0
        _approx_nz = (_ft.get("zInOverworld") or 0.0) / 8.0
        for pred in preds:
            cx = pred.get("chunkX", 0)
            cz = pred.get("chunkZ", 0)
            _best_nx = cx * 16 / 8.0 + 0.5
            _best_nz = cz * 16 / 8.0 + 0.5
            _max_axis = max(abs(_approx_nx - _best_nx), abs(_approx_nz - _best_nz))
            _portal_link_flags.append(_max_axis < 24)
    else:
        _portal_link_flags = [False] * shown_count

    lines = []
    for pred_idx, pred in enumerate(preds):
        cx, cz = pred["chunkX"], pred["chunkZ"]
        cert   = pred["certainty"]
        dist   = pred["overworldDistance"]
        parts  = []
        for key in order:
            if not enabled.get(key, True):
                continue
            if key == "distance":
                d = dist / 8 if in_nether else dist
                parts.append(("distance", (str(int(d)), d)))
            elif key == "certainty_percentage":
                pct = round(cert * 100, 1)
                parts.append(("certainty", f"{pct}%"))
            elif key == "angle":
                sx, sz = cx * 16 + 4, cz * 16 + 4
                if in_nether:
                    sx /= 8.0; sz /= 8.0
                    px, pz = player_x / 8.0, player_z / 8.0
                else:
                    px, pz = player_x, player_z
                dx, dz = sx - px, sz - pz
                tgt    = (math.degrees(math.atan2(dz, dx)) + 270) % 360
                signed = ((tgt + 180) % 360) - 180
                turn   = ((tgt - (h_ang % 360) + 180) % 360) - 180

                show_ang    = angle_display_mode in ("angle_and_change", "angle_only")
                show_change = angle_display_mode in ("angle_and_change", "change_only")

                if show_ang:
                    parts.append(("text", f"{signed:.2f}"))

                if show_change:
                    arrow = "->" if turn > 0 else "<-"
                    parts.append(("angle_change", (arrow, f"{abs(turn):.1f}")))
            elif key == "overworld_coords":
                if ow_coords_format == "chunk":
                    ox, oz = cx, cz
                elif ow_coords_format == "eight_eight":
                    ox, oz = cx*16+8, cz*16+8
                else:
                    ox, oz = cx*16+4, cz*16+4
                if show_coords_by_dim and in_nether:
                    ox, oz = round(ox/8), round(oz/8)
                parts.append(("coords", (ox, oz)))
            elif key == "nether_coords":
                nx, nz = cx * 16 + 4, cz * 16 + 4
                if not (show_coords_by_dim and not in_nether):
                    nx, nz = round(nx / 8), round(nz / 8)
                parts.append(("nether_coords_val", (nx, nz)))
        if parts:
            _flag = _portal_link_flags[pred_idx] if pred_idx < len(_portal_link_flags) else False
            lines.append((parts, _flag))

    if not lines:
        img = Image.new("RGBA", (200, 40), bg_rgba)
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "(nothing to show)", font=font, fill=text_rgb)
        return img

    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def _pw(kind, val):
        if kind == "distance":
            txt = val[0]
        elif kind in ("coords", "nether_coords_val"):
            cx_v, cz_v = val
            txt = f"({cx_v}, {cz_v})"
        elif kind == "angle_change":
            full_change = f"({val[0]} {val[1]})"
            return dummy.textbbox((0, 0), full_change, font=font)[2] + 14
        else:
            txt = str(val)
        gap = 14
        return dummy.textbbox((0, 0), txt, font=font)[2] + gap

    col_widths = []
    for parts_tuple, _plink in lines:
        for slot_idx, item in enumerate(parts_tuple):
            w = _pw(item[0], item[1])
            if slot_idx >= len(col_widths):
                col_widths.append(w)
            else:
                col_widths[slot_idx] = max(col_widths[slot_idx], w)

    required_w = 10 + sum(col_widths) + 10

    col_x = []
    cx_acc = 10
    for w in col_widths:
        col_x.append(cx_acc)
        cx_acc += w

    has_header = any(text_header.get(k, "Text") == "Text" for k in order if enabled.get(k, True))
    header_h = line_h if has_header else 0
    show_overlay_header = settings.get("show_overlay_header", False)

    small_font_size = max(8, int(font_size * 0.90))
    small_font = _load_preview_font(font_name, small_font_size)
    small_ascent, small_descent = small_font.getmetrics()
    small_line_h = small_ascent + small_descent + 4

    overlay_header_h = small_line_h if (show_overlay_header and n_bottom_rows > 0) else 0
    bottom_extra_h = (overlay_header_h + (small_line_h - 2) * n_bottom_rows + 4) if n_bottom_rows > 0 else 0
    height = header_h + line_h * len(lines) + 10 + bottom_extra_h

    img  = Image.new("RGBA", (int(required_w + 10), height), bg_rgba)
    draw = ImageDraw.Draw(img)
    if has_header:
        visible_keys = [k for k in order if enabled.get(k, True)]
        key_slots = {}
        slot = 0
        for key in visible_keys:
            if key == "angle":
                slots = []
                if angle_display_mode in ("angle_and_change", "angle_only"):
                    slots.append(slot)
                    slot += 1
                if angle_display_mode in ("angle_and_change", "change_only"):
                    slots.append(slot)
                    slot += 1
                key_slots[key] = slots
            else:
                key_slots[key] = [slot]
                slot += 1
        for key in visible_keys:
            if text_header.get(key, "Text") != "Text":
                continue
            slots = key_slots.get(key, [])
            if not slots:
                continue
            first_slot = slots[0]
            last_slot = slots[-1]
            if first_slot >= len(col_x) or last_slot >= len(col_widths):
                continue
            hdr_txt = HEADER_LABELS.get(key, "")
            if not hdr_txt:
                continue
            tw_hdr = draw.textbbox((0, 0), hdr_txt, font=font)[2]
            if key == "angle" and angle_display_mode in ("angle_and_change",):
                change_slot = slots[-1]
                if change_slot < len(col_x) and change_slot < len(col_widths):
                    span_start = col_x[change_slot]
                    col_w_change = col_widths[change_slot]
                    hx = span_start + (col_w_change - tw_hdr) // 2
                else:
                    span_start = col_x[first_slot]
                    span_end = col_x[last_slot] + col_widths[last_slot]
                    hx = span_start + (span_end - span_start - tw_hdr) // 2
            else:
                span_start = col_x[first_slot]
                span_end = col_x[last_slot] + col_widths[last_slot]
                span_w = span_end - span_start
                hx = span_start + (span_w - tw_hdr) // 2
            draw.text((hx, 5), hdr_txt, font=font, fill=text_rgb)

    _last_turn_pct = [0.0]

    for row, (parts, _portal_link) in enumerate(lines):
        y = 5 + header_h + row * line_h

        for _item in parts:
            if _item[0] == "angle_change":
                try:
                    _last_turn_pct[0] = float(_item[1][1])
                except Exception:
                    pass
                break

        for slot_idx, item in enumerate(parts):
            kind, val = item
            col_left = col_x[slot_idx] if slot_idx < len(col_x) else 10
            col_w    = col_widths[slot_idx] if slot_idx < len(col_widths) else 0

            def _cx(txt):
                tw = draw.textbbox((0, 0), txt, font=font)[2]
                return col_left + (col_w - tw) // 2

            if kind == "certainty":
                txt = val
                try:
                    fill = _certainty_color(float(txt.rstrip("%")))
                except Exception:
                    fill = text_rgb
                draw.text((_cx(txt), y), txt, font=font, fill=fill)

            elif kind == "angle_change":
                arrow, num = val
                try:
                    _last_turn_pct[0] = float(num)
                except Exception:
                    pass
                fill = _gradient_color(_last_turn_pct[0])
                full_change = f"({arrow} {num})"
                cw_ = draw.textbbox((0, 0), full_change, font=font)[2]
                col_start = col_left + (col_w - cw_) // 2
                draw.text((col_start, y), full_change, font=font, fill=fill)

            elif kind == "distance":
                try:
                    txt, dval = val
                except Exception:
                    txt = str(val)
                    dval = None
                draw.text((_cx(txt), y), txt, font=font, fill=text_rgb)

            elif kind == "coords":
                cx_v, cz_v = val
                x_str = str(cx_v)
                z_str = str(cz_v)
                x_fill = (neg_coords_rgb if neg_coords_enabled and cx_v < 0 else text_rgb)
                z_fill = (neg_coords_rgb if neg_coords_enabled and cz_v < 0 else text_rgb)
                full_txt = f"({cx_v}, {cz_v})"
                bx = col_left + (col_w - draw.textbbox((0, 0), full_txt, font=font)[2]) // 2
                draw.text((bx, y), "(", font=font, fill=text_rgb)
                bx += draw.textbbox((0, 0), "(", font=font)[2]
                draw.text((bx, y), x_str, font=font, fill=x_fill)
                bx += draw.textbbox((0, 0), x_str, font=font)[2]
                draw.text((bx, y), ", ", font=font, fill=text_rgb)
                bx += draw.textbbox((0, 0), ", ", font=font)[2]
                draw.text((bx, y), z_str, font=font, fill=z_fill)
                bx += draw.textbbox((0, 0), z_str, font=font)[2]
                draw.text((bx, y), ")", font=font, fill=text_rgb)

            elif kind == "nether_coords_val":
                cx_v, cz_v = val
                x_str = str(cx_v)
                z_str = str(cz_v)
                _is_portal = portal_dist_enabled and _portal_link
                punct_fill = portal_dist_rgb if _is_portal else text_rgb
                x_fill = (portal_dist_rgb if _is_portal
                          else (neg_coords_rgb if neg_coords_enabled and cx_v < 0 else text_rgb))
                z_fill = (portal_dist_rgb if _is_portal
                          else (neg_coords_rgb if neg_coords_enabled and cz_v < 0 else text_rgb))
                full_txt = f"({cx_v}, {cz_v})"
                bx = col_left + (col_w - draw.textbbox((0, 0), full_txt, font=font)[2]) // 2
                draw.text((bx, y), "(", font=font, fill=punct_fill)
                bx += draw.textbbox((0, 0), "(", font=font)[2]
                draw.text((bx, y), x_str, font=font, fill=x_fill)
                bx += draw.textbbox((0, 0), x_str, font=font)[2]
                draw.text((bx, y), ", ", font=font, fill=punct_fill)
                bx += draw.textbbox((0, 0), ", ", font=font)[2]
                draw.text((bx, y), z_str, font=font, fill=z_fill)
                bx += draw.textbbox((0, 0), z_str, font=font)[2]
                draw.text((bx, y), ")", font=font, fill=punct_fill)

            else:
                txt = str(val)
                draw.text((_cx(txt), y), txt, font=font, fill=text_rgb)

    actual_left = None
    actual_right = None
    for parts, _plink_last in lines[-1:]:
        for slot_idx, item in enumerate(parts):
            kind, val = item[0], item[1]
            if slot_idx >= len(col_x) or slot_idx >= len(col_widths):
                continue
            c_left = col_x[slot_idx]
            c_w = col_widths[slot_idx]
            if kind == "distance":
                txt = val[0]
            elif kind in ("coords", "nether_coords_val"):
                cx_v, cz_v = val
                txt = f"({cx_v}, {cz_v})"
            elif kind == "angle_change":
                arrow, num = val
                arrow_w = draw.textbbox((0, 0), arrow, font=font)[2]
                total_w = arrow_w + 4 + draw.textbbox((0, 0), num, font=font)[2]
                centered_start = c_left + (c_w - total_w) // 2
                centered_end = centered_start + total_w
                if actual_left is None or centered_start < actual_left:
                    actual_left = centered_start
                if actual_right is None or centered_end > actual_right:
                    actual_right = centered_end
                continue
            else:
                txt = str(val)
            txt_w = draw.textbbox((0, 0), txt, font=font)[2]
            centered_start = c_left + (c_w - txt_w) // 2
            centered_end = centered_start + txt_w
            if actual_left is None or centered_start < actual_left:
                actual_left = centered_start
            if actual_right is None or centered_end > actual_right:
                actual_right = centered_end

    if actual_left is None:
        actual_left = 10
    if actual_right is None:
        actual_right = 10

    n_overlay_rows = max(len(adj_count_overlays), len(angle_error_overlays))
    if n_overlay_rows == 0:
        return img

    overlay_header_h = small_line_h if show_overlay_header else 0
    base_y = header_h + line_h * len(lines) + 10

    first_err_x = None
    first_err_w = None
    first_adj_x = None
    first_adj_total_w = None

    for oi in range(n_overlay_rows):
        row_y = base_y + overlay_header_h + oi * (small_line_h - 2) - 2

        if oi < len(adj_count_overlays):
            angle_txt, count_txt, adj_raw = adj_count_overlays[oi]

            angle_w = draw.textbbox((0, 0), angle_txt, font=small_font)[2]
            if count_txt is not None:
                count_w = draw.textbbox((0, 0), count_txt, font=small_font)[2]
            else:
                count_w = 0

            total_w = angle_w + count_w

            if oi == 0:
                adj_x = actual_right - total_w
                first_adj_x = adj_x
                first_adj_total_w = total_w
            else:
                adj_x = first_adj_x + (first_adj_total_w - total_w) // 2

            draw.text((adj_x, row_y), angle_txt, font=small_font, fill=text_rgb)

            if count_txt is not None:
                adj_fill = ADJ_POS if (adj_raw is None or adj_raw >= 0) else ADJ_NEG
                draw.text((adj_x + angle_w, row_y), count_txt, font=small_font, fill=adj_fill)

        if oi < len(angle_error_overlays):
            err_txt = angle_error_overlays[oi][0]
            err_txt_w = draw.textbbox((0, 0), err_txt, font=small_font)[2]
            if oi == 0:
                err_x = actual_left
                first_err_x = err_x
                first_err_w = err_txt_w
            else:
                err_x = first_err_x + (first_err_w - err_txt_w) // 2
            draw.text((err_x, row_y), err_txt, font=small_font, fill=text_rgb)

    if show_overlay_header and n_overlay_rows > 0:
        hdr_y = base_y - 2
        if angle_error_overlays and first_err_x is not None and first_err_w is not None:
            err_hdr_w = draw.textbbox((0, 0), "Error", font=small_font)[2]
            err_hdr_x = first_err_x + (first_err_w - err_hdr_w) // 2
            draw.text((err_hdr_x, hdr_y), "Error", font=small_font, fill=text_rgb)
        if adj_count_overlays and first_adj_x is not None and first_adj_total_w is not None:
            adj_hdr_w = draw.textbbox((0, 0), "Angle", font=small_font)[2]
            adj_hdr_x = first_adj_x + (first_adj_total_w - adj_hdr_w) // 2
            draw.text((adj_hdr_x, hdr_y), "Angle", font=small_font, fill=text_rgb)
    return img

PREVIEW_BLIND = {
    "evaluation": "HIGHROLL_GOOD",
    "xInNether": 312,
    "zInNether": -87,
    "highrollProbability": 0.734,
    "highrollThreshold": 400,
    "improveDirection": math.radians(47),
    "improveDistance": 62,
}

def render_blind_preview(settings: dict) -> Image.Image:
    bg_hex   = settings.get("background_color", "#FFFFFF")
    text_hex = settings.get("text_color", "#000000")
    bg_rgb   = _hex_to_rgb(bg_hex, (255, 255, 255))
    text_rgb = _hex_to_rgb(text_hex, (0, 0, 0))
    bg_rgba  = (*bg_rgb, 255)

    font_name = settings.get("font_name", "")
    font_size = settings.get("font_size", 18)
    font = _load_preview_font(font_name, font_size)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 6

    br = PREVIEW_BLIND
    evaluation   = br["evaluation"]
    x_nether     = br["xInNether"]
    z_nether     = br["zInNether"]
    highroll_prob = br["highrollProbability"] * 100
    highroll_thresh = br["highrollThreshold"]
    improve_deg  = math.degrees(br["improveDirection"])
    improve_dist = br["improveDistance"]

    eval_text      = _format_blind_eval(evaluation)
    eval_color     = _blind_eval_color(evaluation)
    line1_pre      = f"Blind coords ({int(x_nether)}, {int(z_nether)}) are "
    line1_eval     = eval_text
    highroll_txt   = f"{highroll_prob:.1f}%"
    line2_post     = f" chance of <{int(highroll_thresh)} block blind"
    line3          = f"Head {improve_deg:.0f}°, {round(improve_dist)} blocks away, for better coords."

    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    def tw(t): return dummy.textbbox((0, 0), t, font=font)[2]

    max_w = max(tw(line1_pre) + tw(line1_eval),
                tw(highroll_txt) + tw(line2_post),
                tw(line3))
    height = line_h * 3 + 20
    pad = 10
    img  = Image.new("RGBA", (int(max_w + 2 * pad), height), bg_rgba)
    draw = ImageDraw.Draw(img)

    x, y = pad, 10
    draw.text((x, y), line1_pre, font=font, fill=text_rgb)
    draw.text((x + tw(line1_pre), y), line1_eval, font=font, fill=eval_color)

    y += line_h
    draw.text((pad, y), highroll_txt, font=font, fill=eval_color)
    draw.text((pad + tw(highroll_txt), y), line2_post, font=font, fill=text_rgb)

    y += line_h
    draw.text((pad, y), line3, font=font, fill=text_rgb)

    return img

def ensure_custom_file_exists():
    cfg_dir = os.path.dirname(CUSTOM_PATH)
    if not os.path.isdir(cfg_dir):
        os.makedirs(cfg_dir)
    if not os.path.isfile(CUSTOM_PATH):
        with open(CUSTOM_PATH, "w") as f:
            json.dump(DEFAULT_CUSTOMIZATIONS, f, indent=4)

def load_customizations():
    try:
        with open(CUSTOM_PATH, "r") as f:
            data = json.load(f)

            for key, val in DEFAULT_CUSTOMIZATIONS.items():
                if key not in data:
                    data[key] = val
                else:
                    if isinstance(val, dict) and isinstance(data.get(key), dict):
                        for sub_key, sub_val in val.items():
                            if sub_key not in data[key]:
                                data[key][sub_key] = sub_val

            return data
    except Exception:
        return DEFAULT_CUSTOMIZATIONS.copy()

def save_customizations(data):
    with open(CUSTOM_PATH, "w") as f:
        json.dump(data, f, indent=4)

def swap_positions(lst, idx, direction):
    new_idx = idx + direction
    if 0 <= new_idx < len(lst):
        lst[idx], lst[new_idx] = lst[new_idx], lst[idx]

def pick_color(var):
    initial_hex = var.get().strip()
    try:
        s = initial_hex.lstrip("#")
        init_r, init_g, init_b = int(s[0:2],16)/255, int(s[2:4],16)/255, int(s[4:6],16)/255
        init_h, init_s, init_v = colorsys.rgb_to_hsv(init_r, init_g, init_b)
    except Exception:
        init_h, init_s, init_v = 0.0, 1.0, 1.0

    win = tk.Toplevel()
    win.title("Choose Color")
    win.resizable(False, False)
    win.grab_set()

    SQ   = 220
    HUE_H = 22
    PAD  = 12

    state = {"h": init_h, "s": init_s, "v": init_v,
             "dragging_sq": False, "dragging_hue": False}

    total_w = PAD + SQ + PAD
    total_h = PAD + SQ + PAD + HUE_H + PAD + 30 + PAD + 36

    canvas = tk.Canvas(win, width=total_w, height=total_h, highlightthickness=0)
    canvas.pack(padx=0, pady=0)

    SQ_X  = PAD
    SQ_Y  = PAD
    HUE_X = PAD
    HUE_Y = PAD + SQ + PAD

    _sq_tk   = [None]
    _hue_tk  = [None]
    _sw_tk   = [None]

    def make_sq_image(size, hue):
        img = Image.new("RGB", (size, size))
        px  = img.load()
        hue_rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        hr, hg, hb = hue_rgb[0]*255, hue_rgb[1]*255, hue_rgb[2]*255
        for py in range(size):
            v_factor = 1.0 - py / (size - 1)
            for pxx in range(size):
                s_factor = pxx / (size - 1)
                r = int((1 - s_factor) * 255 * v_factor + s_factor * hr * v_factor)
                g = int((1 - s_factor) * 255 * v_factor + s_factor * hg * v_factor)
                b = int((1 - s_factor) * 255 * v_factor + s_factor * hb * v_factor)
                px[pxx, py] = (r, g, b)
        return img

    def make_hue_image(w, h):
        img = Image.new("RGB", (w, h))
        px  = img.load()
        for pxx in range(w):
            hue = pxx / (w - 1)
            rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            col = (int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
            for py in range(h):
                px[pxx, py] = col
        return img

    def redraw_all():
        h, s, v = state["h"], state["s"], state["v"]

        sq_img = make_sq_image(SQ, h)
        _sq_tk[0] = ImageTk.PhotoImage(sq_img)
        canvas.delete("sq")
        canvas.create_image(SQ_X, SQ_Y, anchor="nw", image=_sq_tk[0], tags="sq")

        mx = SQ_X + s * (SQ - 1)
        my = SQ_Y + (1.0 - v) * (SQ - 1)
        canvas.delete("cross")
        canvas.create_oval(mx-6, my-6, mx+6, my+6, outline="white", width=2, tags="cross")
        canvas.create_oval(mx-7, my-7, mx+7, my+7, outline="black", width=1, tags="cross")

        hue_img = make_hue_image(SQ, HUE_H)
        _hue_tk[0] = ImageTk.PhotoImage(hue_img)
        canvas.delete("hue")
        canvas.create_image(HUE_X, HUE_Y, anchor="nw", image=_hue_tk[0], tags="hue")

        hx = HUE_X + int(h * (SQ - 1))
        canvas.delete("hue_marker")
        canvas.create_line(hx, HUE_Y - 2, hx, HUE_Y + HUE_H + 2,
                           fill="white", width=2, tags="hue_marker")
        canvas.create_line(hx, HUE_Y - 2, hx, HUE_Y + HUE_H + 2,
                           fill="black", width=1, tags="hue_marker")

        rgb = colorsys.hsv_to_rgb(h, s, v)
        rc, gc, bc = int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255)
        hex_str = "#{:02X}{:02X}{:02X}".format(rc, gc, bc)
        sw_y = HUE_Y + HUE_H + PAD
        sw_img = Image.new("RGB", (SQ, 28), (rc, gc, bc))
        _sw_tk[0] = ImageTk.PhotoImage(sw_img)
        canvas.delete("swatch")
        canvas.create_image(SQ_X, sw_y, anchor="nw", image=_sw_tk[0], tags="swatch")
        luma = 0.299*rc + 0.587*gc + 0.114*bc
        canvas.delete("hexlabel")
        canvas.create_text(SQ_X + SQ//2, sw_y + 14, text=hex_str,
                           fill="white" if luma < 140 else "black",
                           font=("Helvetica", 10, "bold"), tags="hexlabel")
        hex_var.set(hex_str)

    def sq_pick(ex, ey):
        s = max(0.0, min(1.0, (ex - SQ_X) / (SQ - 1)))
        v = max(0.0, min(1.0, 1.0 - (ey - SQ_Y) / (SQ - 1)))
        state["s"], state["v"] = s, v
        redraw_all()

    def hue_pick(ex):
        state["h"] = max(0.0, min(1.0, (ex - HUE_X) / (SQ - 1)))
        redraw_all()

    def on_press(e):
        if SQ_X <= e.x <= SQ_X+SQ and SQ_Y <= e.y <= SQ_Y+SQ:
            state["dragging_sq"] = True
            sq_pick(e.x, e.y)
        elif HUE_X <= e.x <= HUE_X+SQ and HUE_Y <= e.y <= HUE_Y+HUE_H:
            state["dragging_hue"] = True
            hue_pick(e.x)

    def on_drag(e):
        if state["dragging_sq"]:
            sq_pick(e.x, e.y)
        elif state["dragging_hue"]:
            hue_pick(e.x)

    def on_release_color(e):
        state["dragging_sq"]  = False
        state["dragging_hue"] = False

    canvas.bind("<ButtonPress-1>",   on_press)
    canvas.bind("<B1-Motion>",       on_drag)
    canvas.bind("<ButtonRelease-1>", on_release_color)

    hex_var = tk.StringVar()

    hex_frame = tk.Frame(win)
    hex_frame.pack(pady=(4, 0))
    tk.Label(hex_frame, text="Hex:").pack(side="left")
    hex_entry = tk.Entry(hex_frame, textvariable=hex_var, width=10)
    hex_entry.pack(side="left", padx=4)

    def on_hex_commit(e=None):
        val = hex_var.get().strip()
        try:
            s2 = val.lstrip("#")
            if len(s2) != 6:
                return
            r2, g2, b2 = int(s2[0:2],16)/255, int(s2[2:4],16)/255, int(s2[4:6],16)/255
            h2, s3, v2 = colorsys.rgb_to_hsv(r2, g2, b2)
            state["h"], state["s"], state["v"] = h2, s3, v2
            redraw_all()
        except Exception:
            pass

    hex_entry.bind("<Return>",   on_hex_commit)
    hex_entry.bind("<FocusOut>", on_hex_commit)

    btn_row = tk.Frame(win)
    btn_row.pack(pady=(4, 10))

    def on_ok():
        var.set(hex_var.get())
        win.destroy()

    tk.Button(btn_row, text="OK",     width=8, command=on_ok).pack(side="left", padx=4)
    tk.Button(btn_row, text="Cancel", width=8, command=win.destroy).pack(side="left", padx=4)

    redraw_all()
    win.wait_window()

def is_valid_hex(s):
    if not isinstance(s, str):
        return False
    if len(s) != 7 or not s.startswith("#"):
        return False
    try:
        int(s[1:], 16)
        return True
    except ValueError:
        return False

def find_system_fonts():
    fonts = {}

    search_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/run/current-system/sw/share/fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for fname in files:
                if fname.lower().endswith((".ttf", ".otf")):
                    path = os.path.join(root, fname)
                    display = os.path.splitext(fname)[0]
                    fonts[display] = path

    if not fonts:
        try:
            result = subprocess.run(
                ["fc-list", "--format=%{file}\n"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                path = line.strip()
                if path and os.path.isfile(path) and path.lower().endswith((".ttf", ".otf")):
                    display = os.path.splitext(os.path.basename(path))[0]
                    fonts[display] = path
        except Exception:
            pass

    sorted_fonts = dict(sorted(fonts.items(), key=lambda x: x[0].lower()))

    result_fonts = {BUNDLED_FONT_DISPLAY: BUNDLED_FONT_PATH}
    result_fonts.update(sorted_fonts)
    return result_fonts

def _collect_eye_settings(vars_dict: dict) -> dict:
    order   = list(vars_dict["order"])
    enabled = {k: v.get() for k, v in vars_dict["check_vars"].items()}
    _fv = vars_dict["font_var"].get()
    font_name = vars_dict["system_fonts"].get(_fv, BUNDLED_FONT_PATH)
    try:
        font_size = int(vars_dict["font_size_var"].get())
    except Exception:
        font_size = 18
    return {
        "background_color":              vars_dict["bg_var"].get(),
        "text_color":                    vars_dict["text_var"].get(),
        "negative_coords_color_enabled": vars_dict["neg_coords_enabled_var"].get(),
        "negative_coords_color":         vars_dict["neg_coords_color_var"].get(),
        "portal_nether_color_enabled": vars_dict["portal_dist_enabled_var"].get(),
        "portal_nether_color":         vars_dict["portal_dist_color_var"].get(),
        "font_name":                     font_name,
        "font_size":                     font_size,
        "shown_measurements":            vars_dict["shown_var"].get(),
        "overworld_coords_format": vars_dict["_OW_COORDS_KEY_FROM_DISPLAY"].get(
                                       vars_dict["ow_coords_var"].get(), "four_four"),
        "angle_display_mode":            vars_dict["_ANG_KEY_FROM_DISPLAY"].get(
                                         vars_dict["ang_mode_combo"].get(), "angle_and_change"),
        "show_angle_adjustment_count":   vars_dict["adj_count_var"].get(),
        "show_angle_error":              vars_dict["angle_error_var"].get(),
        "show_overlay_header":           vars_dict["overlay_header_var"].get(),
        "show_coords_based_on_dimension":vars_dict["dim_var"].get(),
        "text_order":                    order,
        "text_enabled":                  enabled,
        "text_header":                   {k: v.get() for k, v in vars_dict["header_vars"].items()},
        "overworld_coords_format":       vars_dict["_OW_COORDS_KEY_FROM_DISPLAY"].get(
                                             vars_dict["ow_coords_var"].get(), "four_four"),
    }

def _collect_default_settings(vars_dict: dict) -> dict:
    try:
        font_size = int(vars_dict["font_size_var"].get())
    except Exception:
        font_size = 18
    return {
        "font_size":                     font_size,
        "negative_coords_color_enabled": vars_dict["neg_coords_enabled_var"].get(),
        "negative_coords_color":         vars_dict["neg_coords_color_var"].get(),
        "overworld_coords_format":       vars_dict["_OW_COORDS_KEY_FROM_DISPLAY"].get(
                                             vars_dict["ow_coords_var"].get(), "four_four"),
    }

def _collect_blind_settings(vars_dict: dict) -> dict:
    font_name = vars_dict["system_fonts"].get(vars_dict["font_var"].get(), "")
    try:
        font_size = int(vars_dict["font_size_var"].get())
    except Exception:
        font_size = 18
    return {
        "background_color": vars_dict["bg_var"].get(),
        "text_color":       vars_dict["text_var"].get(),
        "font_name":        font_name,
        "font_size":        font_size,
    }


def open_default_preview(vars_dict: dict):
    win = tk.Toplevel()
    win.title("Default Overlay — Preview")
    win.resizable(False, False)

    lbl = tk.Label(win, bd=0, highlightthickness=0)
    lbl.pack(padx=20, pady=20)

    tk.Button(win, text="Exit", command=win.destroy).pack(pady=(0, 10))

    _tk_img_ref  = [None]
    _running     = [True]
    _first_frame = [True]

    def _refresh():
        if not _running[0] or not win.winfo_exists():
            return
        try:
            settings = _collect_default_settings(vars_dict)
            pil_img  = render_default_preview(settings)
            tk_img   = ImageTk.PhotoImage(pil_img)
            _tk_img_ref[0] = tk_img
            lbl.config(image=tk_img)
            if _first_frame[0]:
                win.geometry("")
                _first_frame[0] = False
        except Exception:
            pass
        win.after(300, _refresh)

    def _on_close():
        _running[0] = False
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)
    _refresh()


def open_eye_preview(vars_dict: dict):
    win = tk.Toplevel()
    win.title("Eye Throws Overlay — Preview")
    win.resizable(False, False)

    lbl = tk.Label(win, bd=0, highlightthickness=0)
    lbl.pack(padx=20, pady=20)

    tk.Button(win, text="Exit", command=win.destroy).pack(pady=(0, 10))

    _tk_img_ref  = [None]
    _running     = [True]
    _first_frame = [True]

    def _refresh():
        if not _running[0] or not win.winfo_exists():
            return
        try:
            settings = _collect_eye_settings(vars_dict)
            pil_img  = render_eye_throws_preview(settings)
            tk_img   = ImageTk.PhotoImage(pil_img)
            _tk_img_ref[0] = tk_img
            lbl.config(image=tk_img)
            if _first_frame[0]:
                win.geometry("")
                _first_frame[0] = False
        except Exception:
            pass
        win.after(300, _refresh)

    def _on_close():
        _running[0] = False
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)
    _refresh()

def open_default_blind_preview():
    win = tk.Toplevel()
    win.title("Default Blind Coords Overlay — Preview")
    win.resizable(False, False)

    lbl = tk.Label(win, bd=0, highlightthickness=0)
    lbl.pack(padx=20, pady=20)

    tk.Button(win, text="Exit", command=win.destroy).pack(pady=(0, 10))

    _tk_img_ref  = [None]
    _running     = [True]
    _first_frame = [True]

    def _refresh():
        if not _running[0] or not win.winfo_exists():
            return
        try:
            pil_img  = render_default_blind_preview()
            tk_img   = ImageTk.PhotoImage(pil_img)
            _tk_img_ref[0] = tk_img
            lbl.config(image=tk_img)
            if _first_frame[0]:
                win.geometry("")
                _first_frame[0] = False
        except Exception:
            pass
        win.after(300, _refresh)

    def _on_close():
        _running[0] = False
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)
    _refresh()

def open_blind_preview(vars_dict: dict):
    win = tk.Toplevel()
    win.title("Blind Coords Overlay — Preview")
    win.resizable(False, False)

    lbl = tk.Label(win, bd=0, highlightthickness=0)
    lbl.pack(padx=20, pady=20)

    tk.Button(win, text="Exit", command=win.destroy).pack(pady=(0, 10))

    _tk_img_ref  = [None]
    _running     = [True]
    _first_frame = [True]

    def _refresh():
        if not _running[0] or not win.winfo_exists():
            return
        try:
            settings = _collect_blind_settings(vars_dict)
            pil_img  = render_blind_preview(settings)
            tk_img   = ImageTk.PhotoImage(pil_img)
            _tk_img_ref[0] = tk_img
            lbl.config(image=tk_img)
            if _first_frame[0]:
                win.geometry("")
                _first_frame[0] = False
        except Exception:
            pass
        win.after(300, _refresh)

    def _on_close():
        _running[0] = False
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)
    _refresh()

def main():
    ensure_custom_file_exists()
    custom = load_customizations()

    root = tk.Tk()
    root.title("NBTrackr Pinned Image Overlay Customizer")
    root.resizable(False, False)

    use_var = tk.BooleanVar(value=custom.get("use_custom_pinned_image", False))

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    tab_general  = tk.Frame(notebook)
    tab_eye      = tk.Frame(notebook)
    tab_blind    = tk.Frame(notebook)
    tab_advanced = tk.Frame(notebook)

    notebook.add(tab_general,  text="General")
    notebook.add(tab_eye,      text="Eye Throws Overlay")
    notebook.add(tab_blind,    text="Blind Coords Overlay")
    notebook.add(tab_advanced, text="Advanced")

    g = tk.Frame(tab_general)
    g.pack(padx=10, pady=10, fill="x")

    f1 = tk.Frame(g); f1.pack(fill="x", pady=5)
    tk.Label(f1, text="Use custom pinned image overlay", anchor="w").pack(side="left")
    tk.Checkbutton(f1, variable=use_var, relief="flat", bd=0).pack(side="left", padx=5)

    f5 = tk.Frame(g); f5.pack(fill="x", pady=5)
    tk.Label(f5, text="Font", width=26, anchor="w").pack(side="left")

    system_fonts = find_system_fonts()
    font_path_to_display = {v: k for k, v in system_fonts.items()}

    saved_font_path = custom.get("font_name", "")
    if not saved_font_path or saved_font_path == BUNDLED_FONT_PATH:
        saved_font_display = BUNDLED_FONT_DISPLAY
    else:
        saved_font_display = font_path_to_display.get(saved_font_path, BUNDLED_FONT_DISPLAY)

    font_var = tk.StringVar(value=saved_font_display)
    font_dropdown = ttk.Combobox(f5, textvariable=font_var, state="readonly")
    font_dropdown['values'] = list(system_fonts.keys())
    font_dropdown.pack(side="left", fill="x", expand=True)
    font_dropdown.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear())

    def apply_font_dropdown(*_):
        try:
            font_dropdown.configure(font=(font_var.get(), 10))
        except tk.TclError:
            font_dropdown.configure(font=("Helvetica", 10))

    font_var.trace_add("write", apply_font_dropdown)
    root.after(100, apply_font_dropdown)

    f_size = tk.Frame(g); f_size.pack(fill="x", pady=5)
    tk.Label(f_size, text="Font size", width=26, anchor="w").pack(side="left")
    font_size_var = tk.IntVar(value=custom.get("font_size", DEFAULT_CUSTOMIZATIONS["font_size"]))
    font_size_spinbox = tk.Spinbox(f_size, from_=8, to=48, textvariable=font_size_var, width=8)
    font_size_spinbox.pack(side="left", padx=5)

    f_bg = tk.Frame(g); f_bg.pack(fill="x", pady=(5, 2))
    tk.Label(f_bg, text="Background color", width=26, anchor="w").pack(side="left")
    bg_var = tk.StringVar(value=custom.get("background_color", DEFAULT_CUSTOMIZATIONS["background_color"]))
    bg_entry = tk.Entry(f_bg, textvariable=bg_var, width=10)
    bg_entry.pack(side="left", padx=5)
    bg_choose_btn = tk.Button(f_bg, text="Choose", command=lambda: pick_color(bg_var))
    bg_choose_btn.pack(side="left", padx=(0, 10))

    f_text = tk.Frame(g); f_text.pack(fill="x", pady=(2, 5))
    tk.Label(f_text, text="Text color", width=26, anchor="w").pack(side="left")
    text_var = tk.StringVar(value=custom.get("text_color", DEFAULT_CUSTOMIZATIONS["text_color"]))
    text_entry = tk.Entry(f_text, textvariable=text_var, width=10)
    text_entry.pack(side="left", padx=5)
    text_choose_btn = tk.Button(f_text, text="Choose", command=lambda: pick_color(text_var))
    text_choose_btn.pack(side="left")

    f_neg = tk.Frame(g); f_neg.pack(fill="x", pady=(2, 5))
    neg_coords_enabled_var = tk.BooleanVar(value=custom.get("negative_coords_color_enabled", False))
    neg_coords_checkbox = tk.Checkbutton(f_neg, variable=neg_coords_enabled_var,
                                         relief="flat", bd=0)
    neg_coords_checkbox.pack(side="left")
    neg_coords_label = tk.Label(f_neg, text="Display negative coords in a different color",
                                anchor="w")
    neg_coords_label.pack(side="left", padx=(4,0))
    neg_coords_color_var = tk.StringVar(
        value=custom.get("negative_coords_color", DEFAULT_CUSTOMIZATIONS["negative_coords_color"]))
    neg_coords_entry = tk.Entry(f_neg, textvariable=neg_coords_color_var, width=10)
    neg_coords_entry.pack(side="left", padx=5)
    neg_coords_choose_btn = tk.Button(f_neg, text="Choose",
                                      command=lambda: pick_color(neg_coords_color_var))
    neg_coords_choose_btn.pack(side="left")

    f_portal_dist = tk.Frame(g); f_portal_dist.pack(fill="x", pady=(2, 5))
    portal_dist_enabled_var = tk.BooleanVar(value=custom.get("portal_nether_color_enabled", True))
    portal_dist_checkbox = tk.Checkbutton(f_portal_dist, variable=portal_dist_enabled_var,
                                        relief="flat", bd=0)
    portal_dist_checkbox.pack(side="left")
    portal_dist_label = tk.Label(f_portal_dist,
                                text="Display nether coords in a different color when portal link",
                                anchor="w")
    portal_dist_label.pack(side="left", padx=(4, 0))
    portal_dist_color_var = tk.StringVar(
        value=custom.get("portal_nether_color", "#FFA500"))
    portal_dist_entry = tk.Entry(f_portal_dist, textvariable=portal_dist_color_var, width=10)
    portal_dist_entry.pack(side="left", padx=5)
    portal_dist_choose_btn = tk.Button(f_portal_dist, text="Choose",
                                    command=lambda: pick_color(portal_dist_color_var))
    portal_dist_choose_btn.pack(side="left")

    def _update_neg_coords_state(*_):
        neg_coords_checkbox.config(state="normal")
        neg_coords_label.config(fg="#000000")
        en_neg = neg_coords_enabled_var.get()
        neg_coords_entry.config(state="normal" if en_neg else "disabled")
        neg_coords_choose_btn.config(state="normal" if en_neg else "disabled")

    def _update_portal_dist_state(*_):
        en_main = use_var.get()
        portal_dist_checkbox.config(state="normal" if en_main else "disabled")
        portal_dist_label.config(fg="#000000" if en_main else "#777777")
        en_sub = portal_dist_enabled_var.get() and en_main
        portal_dist_entry.config(state="normal" if en_sub else "disabled")
        portal_dist_choose_btn.config(state="normal" if en_sub else "disabled")

    portal_dist_enabled_var.trace_add("write", _update_portal_dist_state)
    neg_coords_enabled_var.trace_add("write", _update_neg_coords_state)

    e = tk.Frame(tab_eye)
    e.pack(padx=10, pady=10, fill="x")

    f_prev = tk.Frame(e); f_prev.pack(fill="x", pady=(0, 4))
    tk.Button(f_prev, text="Preview Default Overlay",
              command=lambda: open_default_preview(_preview_vars)).pack(side="left", padx=(0, 8))
    tk.Button(f_prev, text="Preview Custom Overlay",
              command=lambda: open_eye_preview(_preview_vars)).pack(side="left")
    ttk.Separator(e, orient="horizontal").pack(fill="x", pady=(4, 10))

    f2 = tk.Frame(e); f2.pack(fill="x", pady=5)
    tk.Label(f2, text="Shown measurements", width=34, anchor="w").pack(side="left")
    shown_var = tk.IntVar(value=custom.get("shown_measurements", 5))
    cb_shown = ttk.Combobox(f2, textvariable=shown_var, state="readonly", width=5)
    cb_shown['values'] = [1, 2, 3, 4, 5]
    cb_shown.pack(side="left", padx=5)
    cb_shown.bind("<<ComboboxSelected>>", lambda ev: ev.widget.selection_clear())

    _OW_COORDS_DISPLAY = {
        "four_four":  "(4, 4)",
        "eight_eight":"(8, 8)",
        "chunk":      "Chunk",
    }
    _OW_COORDS_KEY_FROM_DISPLAY = {v: k for k, v in _OW_COORDS_DISPLAY.items()}
    f2b = tk.Frame(e); f2b.pack(fill="x", pady=5)
    tk.Label(f2b, text="Overworld coords format:", width=34, anchor="w").pack(side="left")
    ow_coords_var = tk.StringVar(
        value=_OW_COORDS_DISPLAY.get(custom.get("overworld_coords_format", "four_four"), "(4, 4)"))
    ow_coords_combo = ttk.Combobox(f2b, textvariable=ow_coords_var, state="readonly", width=12)
    ow_coords_combo['values'] = list(_OW_COORDS_DISPLAY.values())
    ow_coords_combo.pack(side="left", padx=5)
    ow_coords_combo.bind("<<ComboboxSelected>>", lambda ev: ev.widget.selection_clear())

    f3 = tk.Frame(e); f3.pack(fill="x", pady=5)
    tk.Label(f3, text="Show angle", width=34, anchor="w").pack(side="left")
    ang_mode_var = tk.StringVar(value=custom.get("angle_display_mode", "angle_and_change"))
    ang_mode_combo = ttk.Combobox(f3, textvariable=ang_mode_var, state="readonly", width=34)

    _ANG_DISPLAY = {
        "angle_and_change": "Show angle and angle change",
        "angle_only":       "Show only the angle (e.g. 35.53)",
        "change_only":      "Show only the angle change (e.g. <- 8.4)",
    }
    ang_mode_combo['values'] = list(_ANG_DISPLAY.values())
    _ANG_KEY_FROM_DISPLAY = {v: k for k, v in _ANG_DISPLAY.items()}
    ang_mode_combo.set(_ANG_DISPLAY.get(ang_mode_var.get(), _ANG_DISPLAY["angle_and_change"]))
    ang_mode_combo.pack(side="left", padx=5)
    ang_mode_combo.bind("<<ComboboxSelected>>", lambda ev: ev.widget.selection_clear())

    def on_adj_count_toggled(*_):
        if adj_count_var.get():
            messagebox.showwarning(
                "NBTrackr - Angle Adjustment Count",
                "The angle adjustment count is an estimate because\n"
                "Ninjabrain Bot API doesn't provide the exact number of adjustments.\n\n"
                "It should work correctly most of the time,\n"
                "but be aware that it's not 100% accurate.\n\n"
                "This will be fixed in Ninjabrain Bot v1.5.2+."
            )

    f4 = tk.Frame(e); f4.pack(fill="x", pady=5)
    dim_var = tk.BooleanVar(value=custom.get("show_coords_based_on_dimension", False))
    tk.Label(f4, text="Show Overworld/Nether coords based on dimension", anchor="w").pack(side="left")
    dim_checkbox = tk.Checkbutton(f4, variable=dim_var)
    dim_checkbox.pack(side="left", padx=5)

    f_boat = tk.Frame(e); f_boat.pack(fill="x", pady=5)
    boat_var = tk.BooleanVar(value=custom.get("show_boat_icon", True))
    tk.Label(f_boat, text="Show green/red boat", anchor="w").pack(side="left")
    boat_checkbox = tk.Checkbutton(f_boat, variable=boat_var)
    boat_checkbox.pack(side="left", padx=5)

    f_boat_sub = tk.Frame(e); f_boat_sub.pack(fill="x", pady=(0, 5))
    boat_hide_after_enabled_var = tk.BooleanVar(value=custom.get("boat_info_hide_after_enabled", True))
    tk.Label(f_boat_sub, text="    •", anchor="w", fg="#000000").pack(side="left")
    boat_hide_after_check = tk.Checkbutton(f_boat_sub, variable=boat_hide_after_enabled_var)
    boat_hide_after_check.pack(side="left")
    boat_hide_after_label = tk.Label(f_boat_sub, text="Hide after", anchor="w")
    boat_hide_after_label.pack(side="left", padx=(4, 5))
    boat_hide_after_var = tk.IntVar(value=custom.get("boat_info_hide_after", 10))
    boat_hide_spinbox = tk.Spinbox(f_boat_sub, from_=1, to=300, textvariable=boat_hide_after_var, width=5)
    boat_hide_spinbox.pack(side="left", padx=5)
    boat_hide_seconds_label = tk.Label(f_boat_sub, text="seconds", anchor="w")
    boat_hide_seconds_label.pack(side="left")

    f_error = tk.Frame(e); f_error.pack(fill="x", pady=5)
    error_var = tk.BooleanVar(value=custom.get("show_error_message", False))
    tk.Label(f_error, text='Show "Could not determine" error', anchor="w").pack(side="left")
    error_checkbox = tk.Checkbutton(f_error, variable=error_var)
    error_checkbox.pack(side="left", padx=5)

    f3b = tk.Frame(e); f3b.pack(fill="x", pady=5)
    adj_count_var = tk.BooleanVar(value=custom.get("show_angle_adjustment_count", False))
    tk.Label(f3b, text="Show angle adjustment count", anchor="w").pack(side="left")
    adj_count_checkbox = tk.Checkbutton(f3b, variable=adj_count_var)
    adj_count_checkbox.pack(side="left", padx=5)

    adj_count_var.trace_add("write", on_adj_count_toggled)

    f3d = tk.Frame(e); f3d.pack(fill="x", pady=5)
    angle_error_var = tk.BooleanVar(value=custom.get("show_angle_error", False))
    tk.Label(f3d, text="Show angle error", anchor="w").pack(side="left")
    angle_error_checkbox = tk.Checkbutton(f3d, variable=angle_error_var)
    angle_error_checkbox.pack(side="left", padx=5)

    f3e = tk.Frame(e); f3e.pack(fill="x", pady=5)
    overlay_header_var = tk.BooleanVar(value=custom.get("show_overlay_header", False))
    tk.Label(f3e, text='Show headers for angle error and angle adjustment count', anchor="w").pack(side="left")
    overlay_header_checkbox = tk.Checkbutton(f3e, variable=overlay_header_var)
    overlay_header_checkbox.pack(side="left", padx=5)

    container = tk.LabelFrame(e,
                            text="Columns",
                            font=("Helvetica", 12),
                            bd=1,
                            relief="solid",
                            padx=6, pady=6)
    container.pack(fill="x", padx=0, pady=(8, 0))

    order = custom.get("text_order", DEFAULT_CUSTOMIZATIONS["text_order"].copy())
    enabled = custom.get("text_enabled", DEFAULT_CUSTOMIZATIONS["text_enabled"].copy())

    text_frame = tk.Frame(container)
    text_frame.pack(fill="x", padx=0, pady=0)

    check_vars = {}
    header_vars = {}
    buttons = {}

    def redraw_items():
        for w in text_frame.winfo_children():
            w.destroy()
        buttons.clear()
        en = use_var.get()

        tk.Label(text_frame, text="", width=20, anchor="w", pady=0).grid(row=0, column=0, padx=5, pady=0)
        tk.Label(text_frame, text="Header", width=10, anchor="center", pady=0).grid(row=0, column=1, padx=5, pady=0)
        tk.Label(text_frame, text="Move left", width=10, anchor="center", pady=0).grid(row=0, column=2, padx=5, pady=0)
        tk.Label(text_frame, text="Move right", width=10, anchor="center", pady=0).grid(row=0, column=3, padx=5, pady=0)

        for idx, key in enumerate(order):
            row = idx + 1

            var = check_vars.get(key, tk.BooleanVar(value=enabled.get(key, True)))
            check_vars[key] = var
            name = DISPLAY_NAMES.get(key, key)
            tk.Checkbutton(text_frame, text=name, variable=var,
                           state="normal" if en else "disabled",
                           anchor="w", width=18).grid(row=row, column=0, padx=5, pady=2, sticky="w")

            hvar = header_vars.get(key)
            if hvar is None:
                saved_headers = custom.get("text_header", {})
                hvar = tk.StringVar(value=saved_headers.get(key, "Text"))
                header_vars[key] = hvar
            header_combo = ttk.Combobox(text_frame, textvariable=hvar,
                                        state="readonly" if en else "disabled", width=10)
            header_combo['values'] = ["Nothing", "Text"]
            header_combo.grid(row=row, column=1, padx=5, pady=2)
            header_combo.bind("<<ComboboxSelected>>", lambda ev: ev.widget.selection_clear())

            def mk_left(i=idx):
                return lambda: (swap_positions(order, i, -1), redraw_items(), update_state())

            btnL = tk.Button(text_frame, text="Move left", width=10, command=mk_left(),
                             state="normal" if en else "disabled")
            btnL.grid(row=row, column=2, padx=5, pady=2)

            def mk_right(i=idx):
                return lambda: (swap_positions(order, i, 1), redraw_items(), update_state())

            btnR = tk.Button(text_frame, text="Move right", width=10, command=mk_right(),
                             state="normal" if en else "disabled")
            btnR.grid(row=row, column=3, padx=5, pady=2)

            buttons[key] = (btnL, btnR)

        _apply_eye_button_states()

    def _apply_eye_button_states():
        en = use_var.get()
        for idx, key in enumerate(order):
            if key not in buttons:
                continue
            btnL, btnR = buttons[key]
            btnL.config(state="normal" if (en and idx > 0) else "disabled")
            btnR.config(state="normal" if (en and idx < len(order) - 1) else "disabled")

    redraw_items()

    b = tk.Frame(tab_blind)
    b.pack(padx=10, pady=10, fill="x")

    f_blind_prev = tk.Frame(b); f_blind_prev.pack(anchor="w", pady=(0, 10))
    tk.Button(f_blind_prev, text="Preview Blind Coords Overlay (default)",
              command=lambda: open_default_blind_preview()).pack(side="left", padx=(0, 8))
    tk.Button(f_blind_prev, text="Preview Blind Coords Overlay (custom)",
              command=lambda: open_blind_preview(_preview_vars)).pack(side="left")
    ttk.Separator(b, orient="horizontal").pack(fill="x", pady=(0, 10))

    f_blind = tk.Frame(b); f_blind.pack(fill="x", pady=(5, 0))
    blind_info_var = tk.BooleanVar(value=custom.get("show_blind_info", True))
    tk.Label(f_blind, text="Show blind information", anchor="w").pack(side="left")
    blind_info_checkbox = tk.Checkbutton(f_blind, variable=blind_info_var, relief="flat", bd=0)
    blind_info_checkbox.pack(side="left", padx=5)

    f_blind_sub = tk.Frame(b); f_blind_sub.pack(fill="x", pady=(0, 5))
    blind_hide_after_enabled_var = tk.BooleanVar(value=custom.get("blind_info_hide_after_enabled", False))
    tk.Label(f_blind_sub, text="    •", anchor="w", fg="#000000").pack(side="left")
    blind_hide_after_check = tk.Checkbutton(f_blind_sub, variable=blind_hide_after_enabled_var)
    blind_hide_after_check.pack(side="left")
    blind_hide_after_label = tk.Label(f_blind_sub, text="Hide after", anchor="w")
    blind_hide_after_label.pack(side="left", padx=(4, 5))
    blind_hide_after_var = tk.IntVar(value=custom.get("blind_info_hide_after", 20))
    blind_hide_spinbox = tk.Spinbox(f_blind_sub, from_=1, to=300, textvariable=blind_hide_after_var, width=5)
    blind_hide_spinbox.pack(side="left", padx=5)
    blind_hide_seconds_label = tk.Label(f_blind_sub, text="seconds", anchor="w")
    blind_hide_seconds_label.pack(side="left")

    adv = tk.Frame(tab_advanced)
    adv.pack(padx=10, pady=10, fill="x")

    f_debug = tk.Frame(adv); f_debug.pack(fill="x", pady=5)
    debug_var = tk.BooleanVar(value=custom.get("debug_mode", DEFAULT_CUSTOMIZATIONS["debug_mode"]))
    tk.Label(f_debug, text="Debug mode", anchor="w").pack(side="left")
    tk.Checkbutton(f_debug, variable=debug_var, relief="flat", bd=0).pack(side="left", padx=5)

    f_idle = tk.Frame(adv); f_idle.pack(fill="x", pady=(5, 0))
    tk.Label(f_idle, text="Idle API polling rate (s)", width=26, anchor="w").pack(side="left")
    idle_rate_var = tk.DoubleVar(value=custom.get("idle_api_polling_rate",
                                                   DEFAULT_CUSTOMIZATIONS["idle_api_polling_rate"]))
    idle_rate_entry = tk.Entry(f_idle, textvariable=idle_rate_var, width=8)
    idle_rate_entry.pack(side="left", padx=5)
    idle_rate_hint = tk.Label(adv, text="  Default 0.2s. Higher value = lower CPU usage when idle.",
                              anchor="w", fg="#666666", font=("Helvetica", 9, "italic"))
    idle_rate_hint.pack(fill="x", pady=(0, 5))

    f_max = tk.Frame(adv); f_max.pack(fill="x", pady=(5, 0))
    tk.Label(f_max, text="Max API polling rate (s)", width=26, anchor="w").pack(side="left")
    max_rate_var = tk.DoubleVar(value=custom.get("max_api_polling_rate",
                                                  DEFAULT_CUSTOMIZATIONS["max_api_polling_rate"]))
    max_rate_entry = tk.Entry(f_max, textvariable=max_rate_var, width=8)
    max_rate_entry.pack(side="left", padx=5)
    max_rate_hint = tk.Label(adv, text="  Default 0.05s. The program will never poll slower than this.",
                             anchor="w", fg="#666666", font=("Helvetica", 9, "italic"))
    max_rate_hint.pack(fill="x", pady=(0, 5))

    _preview_vars = {
        "order":        order,
        "check_vars":   check_vars,
        "header_vars":  header_vars,
        "system_fonts": system_fonts,
        "font_var":     font_var,
        "font_size_var":font_size_var,
        "bg_var":       bg_var,
        "text_var":     text_var,
        "neg_coords_enabled_var":  neg_coords_enabled_var,
        "neg_coords_color_var":    neg_coords_color_var,
        "shown_var":    shown_var,
        "ow_coords_var":             ow_coords_var,
        "_OW_COORDS_KEY_FROM_DISPLAY": _OW_COORDS_KEY_FROM_DISPLAY,
        "ang_mode_combo":ang_mode_combo,
        "_ANG_KEY_FROM_DISPLAY":_ANG_KEY_FROM_DISPLAY,
        "adj_count_var":adj_count_var,
        "angle_error_var": angle_error_var,
        "overlay_header_var": overlay_header_var,
        "dim_var":      dim_var,
        "portal_dist_enabled_var": portal_dist_enabled_var,
        "portal_dist_color_var":   portal_dist_color_var,
    }

    def update_blind_hide_after_state(*_):
        blind_on = blind_info_var.get()
        blind_hide_after_check.config(state="normal" if blind_on else "disabled")
        enabled_sub = blind_hide_after_enabled_var.get() and blind_on
        sub_state = "normal" if enabled_sub else "disabled"
        blind_hide_spinbox.config(state=sub_state)
        blind_hide_after_label.config(state=sub_state)
        blind_hide_seconds_label.config(state=sub_state)

    blind_hide_after_enabled_var.trace_add("write", update_blind_hide_after_state)
    blind_info_var.trace_add("write", update_blind_hide_after_state)

    def update_boat_hide_after_state(*_):
        boat_on = boat_var.get()
        boat_hide_after_check.config(state="normal" if boat_on else "disabled")
        boat_hide_after_label.config(fg="#000000" if boat_on else "#777777")

        enabled_sub = boat_hide_after_enabled_var.get() and boat_on
        sub_state = "normal" if enabled_sub else "disabled"
        boat_hide_spinbox.config(state=sub_state)
        boat_hide_after_label.config(fg="#000000" if sub_state == "normal" else "#777777")
        boat_hide_seconds_label.config(fg="#000000" if sub_state == "normal" else "#777777")

    boat_hide_after_enabled_var.trace_add("write", update_boat_hide_after_state)
    boat_var.trace_add("write", update_boat_hide_after_state)

    def update_state(*_):
        en = use_var.get()

        font_dropdown.config(state="readonly")

        font_size_spinbox.config(state="normal")

        color_state = "normal" if en else "disabled"
        bg_entry.config(state=color_state)
        bg_choose_btn.config(state=color_state)
        text_entry.config(state=color_state)
        text_choose_btn.config(state=color_state)

        _update_neg_coords_state()

        _update_portal_dist_state()

        cb_shown.config(state="readonly" if en else "disabled")

        ow_coords_combo.config(state="readonly")

        ang_mode_combo.config(state="readonly" if en else "disabled")
        adj_count_checkbox.config(state="normal")
        angle_error_checkbox.config(state="normal" if en else "disabled")
        overlay_header_checkbox.config(state="normal" if en else "disabled")
        dim_checkbox.config(state="normal" if en else "disabled")
        boat_checkbox.config(state="normal")
        error_checkbox.config(state="normal" if en else "disabled")
        redraw_items()

        blind_info_checkbox.config(state="normal")
        update_blind_hide_after_state()
        update_boat_hide_after_state()

        idle_rate_entry.config(state="normal")

    use_var.trace_add("write", update_state)
    update_state()
    update_blind_hide_after_state()
    update_boat_hide_after_state()

    def on_save():
        bg_val = bg_var.get().strip()
        txt_val = text_var.get().strip()
        if not is_valid_hex(bg_val):
            messagebox.showerror("Invalid Color", "Background color must be a hex code like #RRGGBB.")
            return
        if not is_valid_hex(txt_val):
            messagebox.showerror("Invalid Color", "Text color must be a hex code like #RRGGBB.")
            return

        try:
            idle_val = float(idle_rate_var.get())
            if idle_val <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid Value", "Idle API polling rate must be a positive number.")
            return

        try:
            max_val = float(max_rate_var.get())
            if max_val <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid Value", "Max API polling rate must be a positive number.")
            return

        if idle_val < max_val:
            messagebox.showerror("Invalid Value",
                                 "Idle API polling rate should be greater than or equal to Max API polling rate.")
            return

        custom.update({
            "use_custom_pinned_image": use_var.get(),
            "shown_measurements": shown_var.get(),
            "overworld_coords_format": _OW_COORDS_KEY_FROM_DISPLAY.get(ow_coords_var.get(), "four_four"),
            "angle_display_mode": _ANG_KEY_FROM_DISPLAY.get(ang_mode_combo.get(), "angle_and_change"),
            "show_angle_adjustment_count": adj_count_var.get(),
            "show_angle_error": angle_error_var.get(),
            "show_overlay_header": overlay_header_var.get(),
            "show_coords_based_on_dimension": dim_var.get(),
            "show_boat_icon": boat_var.get(),
            "show_error_message": error_var.get(),
            "boat_info_hide_after": boat_hide_after_var.get(),
            "boat_info_hide_after_enabled": boat_hide_after_enabled_var.get(),
            "show_blind_info": blind_info_var.get(),
            "blind_info_hide_after": blind_hide_after_var.get(),
            "blind_info_hide_after_enabled": blind_hide_after_enabled_var.get(),
            "font_name": system_fonts.get(font_var.get(), BUNDLED_FONT_PATH),
            "font_size": font_size_var.get(),
            "background_color": bg_val,
            "text_color": txt_val,
            "negative_coords_color_enabled": neg_coords_enabled_var.get(),
            "negative_coords_color": neg_coords_color_var.get().strip(),
            "text_order": order,
            "text_enabled": {k: var.get() for k, var in check_vars.items()},
            "text_header": {k: var.get() for k, var in header_vars.items()},
            "debug_mode": debug_var.get(),
            "idle_api_polling_rate": idle_val,
            "max_api_polling_rate": max_val,
            "portal_nether_color_enabled": portal_dist_enabled_var.get(),
            "portal_nether_color":         portal_dist_color_var.get().strip(),
        })
        save_customizations(custom)
        messagebox.showinfo("Settings Saved", "Your settings have been saved successfully.")

    def on_reset():
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset to defaults?"):
            save_customizations(DEFAULT_CUSTOMIZATIONS.copy())
            custom.clear()
            custom.update(DEFAULT_CUSTOMIZATIONS)
            use_var.set(custom["use_custom_pinned_image"])
            shown_var.set(custom["shown_measurements"])
            ow_coords_var.set(_OW_COORDS_DISPLAY.get(custom.get("overworld_coords_format", "four_four"), "(4, 4)"))
            ang_mode_combo.set(_ANG_DISPLAY.get(custom.get("angle_display_mode", "angle_and_change"),
                                                 _ANG_DISPLAY["angle_and_change"]))
            adj_count_var.set(custom["show_angle_adjustment_count"])
            angle_error_var.set(custom.get("show_angle_error", False))
            overlay_header_var.set(custom.get("show_overlay_header", False))
            dim_var.set(custom["show_coords_based_on_dimension"])
            boat_var.set(custom["show_boat_icon"])
            error_var.set(custom["show_error_message"])
            _reset_font_path = custom.get("font_name", BUNDLED_FONT_PATH)
            if not _reset_font_path or _reset_font_path == BUNDLED_FONT_PATH:
                font_var.set(BUNDLED_FONT_DISPLAY)
            else:
                font_var.set(font_path_to_display.get(_reset_font_path, BUNDLED_FONT_DISPLAY))
            font_size_var.set(custom["font_size"])
            blind_info_var.set(custom["show_blind_info"])
            blind_hide_after_var.set(custom["blind_info_hide_after"])
            blind_hide_after_enabled_var.set(custom.get("blind_info_hide_after_enabled", False))
            boat_hide_after_var.set(custom.get("boat_info_hide_after", 10))
            boat_hide_after_enabled_var.set(custom.get("boat_info_hide_after_enabled", True))
            bg_var.set(custom["background_color"])
            text_var.set(custom["text_color"])
            neg_coords_enabled_var.set(custom.get("negative_coords_color_enabled", False))
            neg_coords_color_var.set(custom.get("negative_coords_color",
                                                  DEFAULT_CUSTOMIZATIONS["negative_coords_color"]))
            _update_neg_coords_state()
            portal_dist_enabled_var.set(custom.get("portal_nether_color_enabled", False))
            portal_dist_color_var.set(custom.get("portal_nether_color", "#FFA500"))
            _update_portal_dist_state()
            debug_var.set(custom["debug_mode"])
            idle_rate_var.set(custom["idle_api_polling_rate"])
            max_rate_var.set(custom["max_api_polling_rate"])
            order[:] = custom["text_order"]
            for k, var in check_vars.items():
                var.set(custom["text_enabled"].get(k, True))
            for k, var in header_vars.items():
                var.set(custom.get("text_header", {}).get(k, "Text"))
            redraw_items()
            update_state()
            update_blind_hide_after_state()
            messagebox.showinfo("Reset Complete", "Settings have been reset to defaults.")

    btn_frame = tk.Frame(root)
    btn_frame.pack(side="bottom", fill="x", pady=10, padx=10)
    tk.Button(btn_frame, text="Save Settings", command=on_save).pack(side="left")
    tk.Button(btn_frame, text="Reset", command=on_reset).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Exit", command=root.destroy).pack(side="right")

    def adjust_window_height():
        root.update_idletasks()
        root.geometry("")

    root.after(150, adjust_window_height)

    root.mainloop()

if __name__ == "__main__":
    main()
