import os
import json
import math
import tkinter as tk
import tkinter.font as tkFont
import subprocess
import threading
import time
from tkinter import ttk, messagebox, colorchooser
from PIL import Image, ImageDraw, ImageFont, ImageTk

def find_dejavu_bold_path():
    known_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",          
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",             
        "/usr/share/fonts/truetype/DejaVuSans-Bold.ttf",       
        "/run/current-system/sw/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  
        os.path.expanduser("~/.fonts/DejaVuSans-Bold.ttf"),
        os.path.expanduser("~/.local/share/fonts/DejaVuSans-Bold.ttf"),
    ]
    for p in known_paths:
        if os.path.isfile(p):
            return p

    try:
        result = subprocess.run(
            ["fc-match", "--format=%{file}", "DejaVu Sans:style=Bold"],
            capture_output=True, text=True, timeout=3
        )
        path = result.stdout.strip()
        if path and os.path.isfile(path) and path.lower().endswith((".ttf", ".otf")):
            return path
    except Exception:
        pass

    return ""

CUSTOM_PATH = os.path.expanduser("~/.config/NBTrackr/customizations.json")

DEFAULT_CUSTOMIZATIONS = {
    "use_custom_pinned_image": False,
    "shown_measurements": 1,
    "overworld_coords_format": "four_four",
    "angle_display_mode": "angle_and_change",    
    "show_angle_adjustment_count": False,
    "show_angle_error": False,
    "show_coords_based_on_dimension": False,
    "show_boat_icon": True,           
    "show_error_message": True,       
    "show_blind_info": True,
    "blind_info_hide_after": 20,
    "blind_info_hide_after_enabled": False,
    "font_name": find_dejavu_bold_path(),
    "font_size": 18,
    "background_color": "#FFFFFF",
    "text_color": "#000000",
    "negative_coords_color_enabled": False,
    "negative_coords_color": "#BA6669",
    "text_order": [
        "distance",
        "certainty_percentage",
        "angle",
        "overworld_coords",
        "nether_coords"
    ],
    "text_enabled": {
        "distance": True,
        "certainty_percentage": True,
        "angle": True,
        "overworld_coords": True,
        "nether_coords": True
    },
    "debug_mode": False,
    "idle_api_polling_rate": 0.3,
    "max_api_polling_rate": 0.15
}

DISPLAY_NAMES = {
    "distance": "Distance",
    "certainty_percentage": "Certainty Percentage",
    "angle": "Angle",
    "overworld_coords": "Overworld Coords",
    "nether_coords": "Nether Coords"
}

# ── Shared colour helpers (mirrors NBTrackr-imgpin.py) ───────────────────────

def _hex_to_rgb(hexstr, fallback=(0, 0, 0)):
    try:
        s = hexstr.strip().lstrip("#")
        if len(s) != 6:
            return fallback
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback

def _certainty_color(pct):
    pct = max(0.0, min(100.0, pct))
    angle = (100 - pct) * 1.8
    if angle <= 90:
        t = angle / 90.0
        return (int(255 * t), 255, 0)
    t = (angle - 90) / 90.0
    return (255, int(255 * (1 - t)), 0)

def _gradient_color(angle):
    if angle <= 90:
        t = angle / 90.0
        return (int(255 * t), 255, 0)
    t = (angle - 90) / 90.0
    return (255, int(255 * (1 - t)), 0)

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

def _load_preview_font(font_name, font_size):
    font = None
    if font_name:
        try:
            font = ImageFont.truetype(font_name, font_size)
            return font
        except Exception:
            pass
    for fallback in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ):
        try:
            font = ImageFont.truetype(fallback, font_size)
            return font
        except Exception:
            continue
    return ImageFont.load_default()

PREVIEW_EYE_DATA = [
    {"chunkX": 23,  "chunkZ": -41, "certainty": 0.812, "overworldDistance": 847.0},
    {"chunkX": 24,  "chunkZ": -42, "certainty": 0.134, "overworldDistance": 851.0},
    {"chunkX": 22,  "chunkZ": -41, "certainty": 0.054, "overworldDistance": 843.0},
    {"chunkX": -12, "chunkZ": 38,  "certainty": 0.000, "overworldDistance": 1203.0},
    {"chunkX": 31,  "chunkZ": -55, "certainty": 0.000, "overworldDistance": 962.0},
]
PREVIEW_PLAYER = {"xInOverworld": 120.0, "zInOverworld": -55.0,
                  "horizontalAngle": -31.5, "isInNether": False}

def render_eye_throws_preview(settings: dict) -> Image.Image:
    bg_hex      = settings.get("background_color", "#FFFFFF")
    text_hex    = settings.get("text_color", "#000000")
    bg_rgb      = _hex_to_rgb(bg_hex, (255, 255, 255))
    text_rgb    = _hex_to_rgb(text_hex, (0, 0, 0))
    neg_coords_enabled = settings.get("negative_coords_color_enabled", False)
    neg_coords_rgb     = _hex_to_rgb(settings.get("negative_coords_color", "#BA6669"), (204, 110, 114))
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

    preds = PREVIEW_EYE_DATA[:shown_count]
    player_x = PREVIEW_PLAYER["xInOverworld"]
    player_z = PREVIEW_PLAYER["zInOverworld"]
    h_ang    = PREVIEW_PLAYER["horizontalAngle"]

    adj_count_overlays   = [("100.21", "+2", 2), ("98.43", "-1", -1)] if show_adj else []
    angle_error_overlays = [("0.0002",), ("-0.0015",)] if show_angle_error else []
    n_bottom_rows  = max(len(adj_count_overlays), len(angle_error_overlays))
    bottom_extra_h = (line_h + 4) * n_bottom_rows
    lines = []
    for pred in preds:
        cx, cz = pred["chunkX"], pred["chunkZ"]
        cert   = pred["certainty"]
        dist   = pred["overworldDistance"]
        parts  = []
        for key in order:
            if not enabled.get(key, True):
                continue
            if key == "distance":
                d = dist / 8 if in_nether else dist
                parts.append(("distance", (str(round(d)), d)))
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
                    parts.append(("angle_arrow", arrow))
                    parts.append(("angle_adjust", f"{abs(turn):.1f}"))
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
                parts.append(("coords", (nx, nz)))
        if parts:
            lines.append(parts)

    if not lines:
        img = Image.new("RGBA", (200, 40), bg_rgba)
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "(nothing to show)", font=font, fill=text_rgb)
        return img

    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def _pw(kind, val):
        if kind == "distance":
            txt = val[0]
        elif kind == "coords":
            cx_v, cz_v = val
            txt = f"({cx_v}, {cz_v})"
        else:
            txt = str(val)
        gap = 6 if kind == "angle_arrow" else 14
        return dummy.textbbox((0, 0), txt, font=font)[2] + gap

    col_widths = []
    for parts in lines:
        for slot_idx, item in enumerate(parts):
            w = _pw(item[0], item[1])
            if slot_idx >= len(col_widths):
                col_widths.append(w)
            else:
                col_widths[slot_idx] = max(col_widths[slot_idx], w)

    required_w = 10 + sum(col_widths) + 10

    height = line_h * len(lines) + 10 + bottom_extra_h
    img  = Image.new("RGBA", (int(required_w + 10), height), bg_rgba)
    draw = ImageDraw.Draw(img)

    col_x = []
    cx_acc = 10
    for w in col_widths:
        col_x.append(cx_acc)
        cx_acc += w
    rightmost_x    = cx_acc
    _last_turn_pct = [0.0]

    for row, parts in enumerate(lines):
        y = 5 + row * line_h

        for _item in parts:
            if _item[0] == "angle_adjust":
                try:
                    _last_turn_pct[0] = float(_item[1])
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

            elif kind in ("angle_arrow", "angle_adjust"):
                txt = val
                if kind == "angle_adjust":
                    try:
                        _last_turn_pct[0] = float(val)
                    except Exception:
                        pass
                draw.text((_cx(txt), y), txt, font=font,
                          fill=_gradient_color(_last_turn_pct[0]))

            elif kind == "distance":
                txt, dval = val
                fill = (255, 165, 0) if (not in_nether and dval <= 193) else text_rgb
                draw.text((_cx(txt), y), txt, font=font, fill=fill)

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

            else:
                txt = str(val)
                draw.text((_cx(txt), y), txt, font=font, fill=text_rgb)

    n_overlay_rows = max(len(adj_count_overlays), len(angle_error_overlays))
    for oi in range(n_overlay_rows):
        row_y = (line_h * len(lines) + 10) + oi * (line_h + 4) + 2

        if oi < len(adj_count_overlays):
            angle_txt, count_txt, adj_raw = adj_count_overlays[oi]
            adj_fill = ADJ_POS if adj_raw >= 0 else ADJ_NEG
            angle_w  = draw.textbbox((0, 0), angle_txt, font=font)[2]
            count_w  = draw.textbbox((0, 0), count_txt, font=font)[2]
            total_w  = angle_w + count_w
            adj_x    = rightmost_x - 14 - total_w
            adj_x    = max(adj_x, 10)
            draw.text((adj_x, row_y), angle_txt, font=font, fill=text_rgb)
            draw.text((adj_x + angle_w, row_y), count_txt, font=font, fill=adj_fill)

        if oi < len(angle_error_overlays):
            err_txt = angle_error_overlays[oi][0]
            draw.text((10, row_y), err_txt, font=font, fill=text_rgb)

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
    line3          = f"Head {improve_deg:.0f}°, {int(improve_dist)} blocks away, for better coords."

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
    col = colorchooser.askcolor(title="Choose color")
    if col and col[1]:
        var.set(col[1])

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

    return dict(sorted(fonts.items(), key=lambda x: x[0].lower()))

def _collect_eye_settings(vars_dict: dict) -> dict:
    order   = list(vars_dict["order"])
    enabled = {k: v.get() for k, v in vars_dict["check_vars"].items()}
    font_name = vars_dict["system_fonts"].get(vars_dict["font_var"].get(), "")
    try:
        font_size = int(vars_dict["font_size_var"].get())
    except Exception:
        font_size = 18
    return {
        "background_color":              vars_dict["bg_var"].get(),
        "text_color":                    vars_dict["text_var"].get(),
        "negative_coords_color_enabled": vars_dict["neg_coords_enabled_var"].get(),
        "negative_coords_color":         vars_dict["neg_coords_color_var"].get(),
        "font_name":                     font_name,
        "font_size":                     font_size,
        "shown_measurements":            vars_dict["shown_var"].get(),
        "overworld_coords_format": vars_dict["_OW_COORDS_KEY_FROM_DISPLAY"].get(
                                       vars_dict["ow_coords_var"].get(), "four_four"),
        "angle_display_mode":            vars_dict["_ANG_KEY_FROM_DISPLAY"].get(
                                         vars_dict["ang_mode_combo"].get(), "angle_and_change"),
        "show_angle_adjustment_count":   vars_dict["adj_count_var"].get(),
        "show_angle_error":              vars_dict["angle_error_var"].get(),
        "show_coords_based_on_dimension":vars_dict["dim_var"].get(),
        "text_order":                    order,
        "text_enabled":                  enabled,
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
    tk.Label(f5, text="Font", width=18, anchor="w").pack(side="left")

    system_fonts = find_system_fonts()
    font_path_to_display = {v: k for k, v in system_fonts.items()}

    saved_font_path = custom.get("font_name", "")
    saved_font_display = font_path_to_display.get(saved_font_path, "")

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
    tk.Label(f_size, text="Font size", width=18, anchor="w").pack(side="left")
    font_size_var = tk.IntVar(value=custom.get("font_size", DEFAULT_CUSTOMIZATIONS["font_size"]))
    font_size_spinbox = tk.Spinbox(f_size, from_=8, to=48, textvariable=font_size_var, width=8)
    font_size_spinbox.pack(side="left", padx=5)

    f_bg = tk.Frame(g); f_bg.pack(fill="x", pady=(5, 2))
    tk.Label(f_bg, text="Background color", width=18, anchor="w").pack(side="left")
    bg_var = tk.StringVar(value=custom.get("background_color", DEFAULT_CUSTOMIZATIONS["background_color"]))
    bg_entry = tk.Entry(f_bg, textvariable=bg_var, width=10)
    bg_entry.pack(side="left", padx=5)
    bg_choose_btn = tk.Button(f_bg, text="Choose", command=lambda: pick_color(bg_var))
    bg_choose_btn.pack(side="left", padx=(0, 10))

    f_text = tk.Frame(g); f_text.pack(fill="x", pady=(2, 5))
    tk.Label(f_text, text="Text color", width=18, anchor="w").pack(side="left")
    text_var = tk.StringVar(value=custom.get("text_color", DEFAULT_CUSTOMIZATIONS["text_color"]))
    text_entry = tk.Entry(f_text, textvariable=text_var, width=10)
    text_entry.pack(side="left", padx=5)
    text_choose_btn = tk.Button(f_text, text="Choose", command=lambda: pick_color(text_var))
    text_choose_btn.pack(side="left")

    f_neg = tk.Frame(g); f_neg.pack(fill="x", pady=(2, 5))
    neg_coords_enabled_var = tk.BooleanVar(value=custom.get("negative_coords_color_enabled", False))
    tk.Checkbutton(f_neg, variable=neg_coords_enabled_var,
                   relief="flat", bd=0).pack(side="left")
    tk.Label(f_neg, text="Display negative coords in a different color",
             anchor="w").pack(side="left")
    neg_coords_color_var = tk.StringVar(
        value=custom.get("negative_coords_color", DEFAULT_CUSTOMIZATIONS["negative_coords_color"]))
    neg_coords_entry = tk.Entry(f_neg, textvariable=neg_coords_color_var, width=10)
    neg_coords_entry.pack(side="left", padx=5)
    neg_coords_choose_btn = tk.Button(f_neg, text="Choose",
                                      command=lambda: pick_color(neg_coords_color_var))
    neg_coords_choose_btn.pack(side="left")

    def _update_neg_coords_state(*_):
        en_main = use_var.get()
        en_neg  = neg_coords_enabled_var.get() and en_main
        neg_coords_entry.config(state="normal" if en_neg else "disabled")
        neg_coords_choose_btn.config(state="normal" if en_neg else "disabled")

    neg_coords_enabled_var.trace_add("write", _update_neg_coords_state)
    _update_neg_coords_state()

    e = tk.Frame(tab_eye)
    e.pack(padx=10, pady=10, fill="x")

    tk.Button(e, text="Preview Eye Throws Overlay",
              command=lambda: open_eye_preview(_preview_vars)).pack(anchor="w", pady=(0, 10))
    ttk.Separator(e, orient="horizontal").pack(fill="x", pady=(0, 10))

    f2 = tk.Frame(e); f2.pack(fill="x", pady=5)
    tk.Label(f2, text="Shown measurements", width=30, anchor="w").pack(side="left")
    shown_var = tk.IntVar(value=custom.get("shown_measurements", 1))
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
    tk.Label(f2b, text="Overworld coords:", width=30, anchor="w").pack(side="left")
    ow_coords_var = tk.StringVar(
        value=_OW_COORDS_DISPLAY.get(custom.get("overworld_coords_format", "four_four"), "(4, 4)"))
    ow_coords_combo = ttk.Combobox(f2b, textvariable=ow_coords_var, state="readonly", width=12)
    ow_coords_combo['values'] = list(_OW_COORDS_DISPLAY.values())
    ow_coords_combo.pack(side="left", padx=5)
    ow_coords_combo.bind("<<ComboboxSelected>>", lambda ev: ev.widget.selection_clear())

    f3 = tk.Frame(e); f3.pack(fill="x", pady=5)
    tk.Label(f3, text="Show angle", width=30, anchor="w").pack(side="left")
    ang_mode_var = tk.StringVar(value=custom.get("angle_display_mode", "angle_and_change"))
    ang_mode_combo = ttk.Combobox(f3, textvariable=ang_mode_var, state="readonly", width=34)
    ang_mode_combo['values'] = [
        "angle_and_change",
        "angle_only",
        "change_only",
    ]
    ang_mode_combo.pack(side="left", padx=5)
    ang_mode_combo.bind("<<ComboboxSelected>>", lambda ev: ev.widget.selection_clear())

    _ANG_DISPLAY = {
        "angle_and_change": "Show angle and angle change",
        "angle_only":       "Show only the angle (e.g. 35.53)",
        "change_only":      "Show only the angle change (e.g. <- 8.4)",
    }
    ang_mode_combo['values'] = list(_ANG_DISPLAY.values())
    _ANG_KEY_FROM_DISPLAY = {v: k for k, v in _ANG_DISPLAY.items()}
    ang_mode_combo.set(_ANG_DISPLAY.get(ang_mode_var.get(), _ANG_DISPLAY["angle_and_change"]))

    f3b = tk.Frame(e); f3b.pack(fill="x", pady=5)
    adj_count_var = tk.BooleanVar(value=custom.get("show_angle_adjustment_count", False))
    tk.Label(f3b, text="Show angle adjustment count", anchor="w").pack(side="left")
    adj_count_checkbox = tk.Checkbutton(f3b, variable=adj_count_var)
    adj_count_checkbox.pack(side="left", padx=5)

    f3d = tk.Frame(e); f3d.pack(fill="x", pady=5)
    angle_error_var = tk.BooleanVar(value=custom.get("show_angle_error", False))
    tk.Label(f3d, text="Show angle error", anchor="w").pack(side="left")
    angle_error_checkbox = tk.Checkbutton(f3d, variable=angle_error_var)
    angle_error_checkbox.pack(side="left", padx=5)

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

    adj_count_var.trace_add("write", on_adj_count_toggled)

    f4 = tk.Frame(e); f4.pack(fill="x", pady=5)
    dim_var = tk.BooleanVar(value=custom.get("show_coords_based_on_dimension", False))
    tk.Label(f4, text="Show Overworld/Nether coords based on dimension", anchor="w").pack(side="left")
    dim_checkbox = tk.Checkbutton(f4, variable=dim_var)
    dim_checkbox.pack(side="left", padx=5)

    f_boat = tk.Frame(e); f_boat.pack(fill="x", pady=5)
    boat_var = tk.BooleanVar(value=custom.get("show_boat_icon", False))
    tk.Label(f_boat, text="Show green/red boat icon", anchor="w").pack(side="left")
    boat_checkbox = tk.Checkbutton(f_boat, variable=boat_var)
    boat_checkbox.pack(side="left", padx=5)

    f_error = tk.Frame(e); f_error.pack(fill="x", pady=5)
    error_var = tk.BooleanVar(value=custom.get("show_error_message", False))
    tk.Label(f_error, text='Show "Could not determine" error', anchor="w").pack(side="left")
    error_checkbox = tk.Checkbutton(f_error, variable=error_var)
    error_checkbox.pack(side="left", padx=5)

    tk.Label(e, text="Text Elements:", font=("Helvetica", 12)).pack(pady=(15, 5), anchor="w")

    order = custom.get("text_order", DEFAULT_CUSTOMIZATIONS["text_order"].copy())
    enabled = custom.get("text_enabled", DEFAULT_CUSTOMIZATIONS["text_enabled"].copy())
    text_frame = tk.Frame(e)
    text_frame.pack(fill="x", padx=10)
    check_vars = {}
    buttons = {}

    def redraw_items():
        for w in text_frame.winfo_children():
            w.destroy()
        buttons.clear()
        en = use_var.get()
        for idx, key in enumerate(order):
            frm = tk.Frame(text_frame)
            frm.pack(fill="x", pady=2)
            name = DISPLAY_NAMES.get(key, key)
            var = check_vars.get(key, tk.BooleanVar(value=enabled.get(key, True)))
            check_vars[key] = var
            tk.Checkbutton(frm, text=name, variable=var,
                           state="normal" if en else "disabled").pack(side="left", padx=(0, 15))

            def mk_left(i=idx):
                return lambda: (swap_positions(order, i, -1), redraw_items(), update_state())

            btnL = tk.Button(frm, text="Move left", width=8, command=mk_left())
            btnL.pack(side="left", padx=5)

            def mk_right(i=idx):
                return lambda: (swap_positions(order, i, 1), redraw_items(), update_state())

            btnR = tk.Button(frm, text="Move right", width=8, command=mk_right())
            btnR.pack(side="left", padx=5)
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

    tk.Button(b, text="Preview Blind Coords Overlay",
              command=lambda: open_blind_preview(_preview_vars)).pack(anchor="w", pady=(0, 10))
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
    idle_rate_hint = tk.Label(adv, text="  Default 0.3s. Higher value = lower CPU usage when idle.",
                              anchor="w", fg="#666666", font=("Helvetica", 9, "italic"))
    idle_rate_hint.pack(fill="x", pady=(0, 5))

    f_max = tk.Frame(adv); f_max.pack(fill="x", pady=(5, 0))
    tk.Label(f_max, text="Max API polling rate (s)", width=26, anchor="w").pack(side="left")
    max_rate_var = tk.DoubleVar(value=custom.get("max_api_polling_rate",
                                                  DEFAULT_CUSTOMIZATIONS["max_api_polling_rate"]))
    max_rate_entry = tk.Entry(f_max, textvariable=max_rate_var, width=8)
    max_rate_entry.pack(side="left", padx=5)
    max_rate_hint = tk.Label(adv, text="  Default 0.15s. The program will never poll slower than this.",
                             anchor="w", fg="#666666", font=("Helvetica", 9, "italic"))
    max_rate_hint.pack(fill="x", pady=(0, 5))

    _preview_vars = {
        "order":        order,
        "check_vars":   check_vars,
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
        "dim_var":      dim_var,
    }

    def update_blind_hide_after_state(*_):
        blind_on = blind_info_var.get() and use_var.get()
        blind_hide_after_check.config(state="normal" if blind_on else "disabled")
        enabled_sub = blind_hide_after_enabled_var.get() and blind_on
        sub_state = "normal" if enabled_sub else "disabled"
        blind_hide_spinbox.config(state=sub_state)
        blind_hide_after_label.config(state=sub_state)
        blind_hide_seconds_label.config(state=sub_state)

    blind_hide_after_enabled_var.trace_add("write", update_blind_hide_after_state)
    blind_info_var.trace_add("write", update_blind_hide_after_state)

    def update_state(*_):
        en = use_var.get()

        font_state = "readonly" if en else "disabled"
        font_dropdown.config(state=font_state)
        font_size_spinbox.config(state="normal" if en else "disabled")
        color_state = "normal" if en else "disabled"
        bg_entry.config(state=color_state)
        bg_choose_btn.config(state=color_state)
        text_entry.config(state=color_state)
        text_choose_btn.config(state=color_state)

        _update_neg_coords_state()

        cb_shown.config(state="readonly" if en else "disabled")
        ow_coords_combo.config(state="readonly" if en else "disabled")
        ang_mode_combo.config(state="readonly" if en else "disabled")
        adj_count_checkbox.config(state="normal" if en else "disabled")
        angle_error_checkbox.config(state="normal" if en else "disabled")
        dim_checkbox.config(state="normal" if en else "disabled")
        boat_checkbox.config(state="normal" if en else "disabled")
        error_checkbox.config(state="normal" if en else "disabled")
        redraw_items()  

        blind_info_checkbox.config(state="normal" if en else "disabled")
        update_blind_hide_after_state()

        idle_rate_entry.config(state="normal" if en else "disabled")

    use_var.trace_add("write", update_state)
    update_state()
    update_blind_hide_after_state()

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
            "show_coords_based_on_dimension": dim_var.get(),
            "show_boat_icon": boat_var.get(),
            "show_error_message": error_var.get(),
            "show_blind_info": blind_info_var.get(),
            "blind_info_hide_after": blind_hide_after_var.get(),
            "blind_info_hide_after_enabled": blind_hide_after_enabled_var.get(),
            "font_name": system_fonts.get(font_var.get(), ""),
            "font_size": font_size_var.get(),
            "background_color": bg_val,
            "text_color": txt_val,
            "negative_coords_color_enabled": neg_coords_enabled_var.get(),
            "negative_coords_color": neg_coords_color_var.get().strip(),
            "text_order": order,
            "text_enabled": {k: var.get() for k, var in check_vars.items()},
            "debug_mode": debug_var.get(),
            "idle_api_polling_rate": idle_val,
            "max_api_polling_rate": max_val,
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
            dim_var.set(custom["show_coords_based_on_dimension"])
            boat_var.set(custom["show_boat_icon"])
            error_var.set(custom["show_error_message"])
            font_var.set(font_path_to_display.get(custom["font_name"], ""))
            font_size_var.set(custom["font_size"])
            blind_info_var.set(custom["show_blind_info"])
            blind_hide_after_var.set(custom["blind_info_hide_after"])
            blind_hide_after_enabled_var.set(custom.get("blind_info_hide_after_enabled", False))
            bg_var.set(custom["background_color"])
            text_var.set(custom["text_color"])
            neg_coords_enabled_var.set(custom.get("negative_coords_color_enabled", False))
            neg_coords_color_var.set(custom.get("negative_coords_color",
                                                  DEFAULT_CUSTOMIZATIONS["negative_coords_color"]))
            _update_neg_coords_state()
            debug_var.set(custom["debug_mode"])
            idle_rate_var.set(custom["idle_api_polling_rate"])
            max_rate_var.set(custom["max_api_polling_rate"])
            order[:] = custom["text_order"]
            for k, var in check_vars.items():
                var.set(custom["text_enabled"].get(k, True))
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
