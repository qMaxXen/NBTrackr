import sys
import tkinter as tk
from tkinter import font
from PIL import Image, ImageTk, UnidentifiedImageError, ImageDraw, ImageFont
import math
import os
import threading
import queue
import time
import requests
from datetime import datetime
import json
import atexit
import tempfile
import tarfile
import sys

# Program Version
APP_VERSION = "v2.4.0"

CONFIG_DIR = os.path.expanduser("~/.config/NBTrackr")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

CUSTOMIZATIONS_FILE = os.path.join(CONFIG_DIR, "customizations.json")

position_set = False

# --------------------- Cache --------------------------

_last_custom = None
_last_boat = None
_last_stronghold = None
_last_blind = None
_cached_customizations = None

_nb_settings_cache = None
_nb_settings_cache_time = 0
NB_SETTINGS_CACHE_TTL = 60.0

_last_custom_mtime = 0

def get_customizations():
    global _cached_customizations
    if _cached_customizations is not None:
        return _cached_customizations
    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            _cached_customizations = json.load(f)
    except Exception:
        _cached_customizations = {}
    return _cached_customizations

def _load_advanced_settings():
    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            data = json.load(f)
        return (
            bool(data.get("debug_mode", False)),
            float(data.get("idle_api_polling_rate", 0.3)),
            float(data.get("max_api_polling_rate", 0.15)),
        )
    except Exception:
        return False, 0.2, 0.05

DEBUG_MODE, IDLE_API_POLLING_RATE, MAX_API_POLLING_RATE = _load_advanced_settings()

def get_ninjabrainbot_settings():
    global _nb_settings_cache, _nb_settings_cache_time
    now = time.time()
    if _nb_settings_cache is not None and (now - _nb_settings_cache_time) < NB_SETTINGS_CACHE_TTL:
        return _nb_settings_cache

    prefs_path = os.path.expanduser("~/.java/.userPrefs/ninjabrainbot/prefs.xml")
    result = {}
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(prefs_path)
        root_el = tree.getroot()
        for entry in root_el.iter("entry"):
            key = entry.get("key")
            val = entry.get("value")
            if key is None or val is None:
                continue
            try:
                result[key] = int(val)
                continue
            except ValueError:
                pass
            try:
                result[key] = float(val)
                continue
            except ValueError:
                pass
            result[key] = val
    except Exception as e:
        log("get_ninjabrain_settings: failed to read NB prefs:", e)

    _nb_settings_cache = result
    _nb_settings_cache_time = now
    return result


def calculate_correction_increments(correction: float, settings: dict) -> int:
    BETA = -31.0
    adj_type = int(settings.get("angle_adjustment_type", 0))

    if adj_type == 1:
        to_rad = math.pi / 180.0
        height = float(settings.get("resolution_height", 16384.0))
        change = math.atan(2 * math.tan(15 * to_rad) / height) / math.cos(BETA * to_rad) / to_rad
    elif adj_type == 2:
        change = float(settings.get("custom_adjustment", 0.01))
    else:
        change = 0.01

    if change == 0:
        return 0

    raw = correction / change
    return int(math.floor(raw + 0.5))

def gradient_color(angle: float):
    if angle <= 90:
        t = angle / 90.0
        red   = int(255 * t)
        green = 255
        return (red, green, 0)
    t = (angle - 90) / 90.0
    red   = 255
    green = int(255 * (1 - t))
    return (red, green, 0)

def certainty_color(pct: float):
    pct = max(0.0, min(100.0, pct))
    return gradient_color((100 - pct) * 1.8)

ADJ_COUNT_POSITIVE = (117, 204, 108)
ADJ_COUNT_NEGATIVE = (204, 110, 114)

def blind_evaluation_color(evaluation):
    colors = {
        'EXCELLENT': (0, 255, 0),
        'HIGHROLL_GOOD': (100, 255, 100),
        'HIGHROLL_OKAY': (114, 214, 2),
        'BAD_BUT_IN_RING': (222, 220, 3),
        'BAD': (255, 100, 0),
        'NOT_IN_RING': (255, 0, 0)
    }
    return colors.get(evaluation, (255, 255, 255))

def format_blind_evaluation(evaluation):
    evaluations = {
        'EXCELLENT': 'excellent',
        'HIGHROLL_GOOD': 'good for highroll',
        'HIGHROLL_OKAY': 'okay for highroll',
        'BAD_BUT_IN_RING': 'bad, but in ring',
        'BAD': 'bad',
        'NOT_IN_RING': 'not in any ring'
    }
    return evaluations.get(evaluation, evaluation)

def hex_to_rgb(hexstr, fallback=(0, 0, 0)):
    try:
        if not isinstance(hexstr, str):
            return fallback
        s = hexstr.strip()
        if s.startswith("#"):
            s = s[1:]
        if len(s) != 6:
            return fallback
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except Exception:
        return fallback


# --------------------- Cache End --------------------------

def _get_assets_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

_nb_font_missing_warned = False

def _load_nb_font(size):
    global _nb_font_missing_warned
    assets_dir = _get_assets_dir()
    font_path = os.path.join(assets_dir, "LiberationSans", "LiberationSans-Bold.ttf")
    if os.path.isfile(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    if not _nb_font_missing_warned:
        print(
            "ERROR: Could not find the bundled font at:\n"
            f"  {font_path}\n"
            "The overlay text will use a fallback font and may look incorrect.\n"
            "Please reinstall NBTrackr to restore the missing file."
        )
        _nb_font_missing_warned = True
    return ImageFont.load_default()

NB_BG              = (55,  60,  66,  255)
NB_HEADER_BG       = (45,  50,  56,  255)
NB_HEADER_FG       = (229, 229, 229)
NB_ROW_BG          = (55,  60,  66,  255)
NB_TEXT            = (255, 255, 255)
NB_THROW_HEADER_FG = (192, 192, 192)

NB_HDR_SEP   = (33,  37,  41,  255)
NB_ROW_SEP   = (42,  46,  50,  255)

# --------------------- Generate default pinned image overlay ---------------

_last_default_stronghold = None
_last_default_boat = None
_last_default_blind = None

def _interpolate_color(c1, c2, steps, step):
    r = int(c1[0] + (c2[0] - c1[0]) * step / max(steps - 1, 1))
    g = int(c1[1] + (c2[1] - c1[1]) * step / max(steps - 1, 1))
    b = int(c1[2] + (c2[2] - c1[2]) * step / max(steps - 1, 1))
    return (r, g, b)

_RED_HEX   = (189, 65,  65)
_YELLOW    = (216, 192, 100)
_GREEN_HEX = (89,  185, 75)

def _nb_certainty_color(certainty_pct):
    if certainty_pct >= 50:
        return _interpolate_color(_YELLOW, _GREEN_HEX, 51, int(certainty_pct - 50))
    else:
        return _interpolate_color(_RED_HEX, _YELLOW, 51, int(certainty_pct))

def _nb_direction_color(direction):
    abs_dir = abs(direction)
    if abs_dir <= 180:
        return _interpolate_color(_RED_HEX, _GREEN_HEX, 181, int(180 - abs_dir))
    return _YELLOW

def _nb_blind_eval_color(evaluation):
    mapping = {
        'EXCELLENT':       (_YELLOW, _GREEN_HEX, 51, 50),
        'HIGHROLL_GOOD':   (_YELLOW, _GREEN_HEX, 51, 40),
        'HIGHROLL_OKAY':   (_YELLOW, _GREEN_HEX, 51, 25),
        'BAD_BUT_IN_RING': (_YELLOW, _GREEN_HEX, 51, 0),
        'BAD':             (_RED_HEX, _YELLOW,    51, 25),
        'NOT_IN_RING':     (_RED_HEX, _YELLOW,    51, 0),
    }
    if evaluation in mapping:
        c1, c2, steps, step = mapping[evaluation]
        return _interpolate_color(c1, c2, steps, step)
    return (255, 255, 255)

def generate_default_pinned_image():
    global _last_default_stronghold, _last_default_boat, _last_default_blind

    with status_lock:
        boat_resp       = dict(status["boat_resp"])
        stronghold_resp = dict(status["stronghold_resp"])
        blind_resp      = dict(status["blind_resp"])
        now             = time.time()
        show_until      = status.get("showUntil", 0)

    if not stronghold_resp:
        root.after(0, hide_window)
        return

    result_type   = stronghold_resp.get("resultType")
    boat_state    = boat_resp.get("boatState")
    boat_angle    = boat_resp.get("boatAngle", None)
    preds         = stronghold_resp.get("predictions", [])
    eye_throws    = stronghold_resp.get("eyeThrows", [])
    player_pos    = stronghold_resp.get("playerPosition", {})
    player_x      = player_pos.get("xInOverworld")
    player_z      = player_pos.get("zInOverworld")
    h_ang         = player_pos.get("horizontalAngle")
    in_nether     = player_pos.get("isInNether", False)
    blind_enabled = blind_resp.get("isBlindModeEnabled", False)
    blind_result  = blind_resp.get("blindResult", {})

    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            custom = json.load(f)
    except Exception:
        custom = {}

    try:
        font_size = int(custom.get("font_size", 18))
    except Exception:
        font_size = 18

    user_font_path     = custom.get("font_name", "")

    show_boat_icon_setting = bool(custom.get("show_boat_icon", True))
    boat_info_hide_after_enabled_setting = bool(custom.get("boat_info_hide_after_enabled", True))
    boat_info_hide_after_setting = float(custom.get("boat_info_hide_after", 10))
    show_blind_info_setting = bool(custom.get("show_blind_info", True))

    try:
        neg_coords_enabled = bool(custom.get("negative_coords_color_enabled", False))
        neg_coords_rgb = hex_to_rgb(custom.get("negative_coords_color", "#BA6669"), (186, 102, 105))
    except Exception:
        neg_coords_enabled = False
        neg_coords_rgb = (186, 102, 105)

    ow_coords_format   = custom.get("overworld_coords_format", "four_four")
    show_adj_count     = bool(custom.get("show_angle_adjustment_count", False))

    cache_key = (result_type, boat_state, boat_angle, in_nether,
                 repr(preds[:5]), repr(eye_throws),
                 repr(blind_result), blind_enabled, font_size,
                 neg_coords_enabled, neg_coords_rgb, ow_coords_format,
                 show_adj_count, user_font_path,
                 player_x, player_z, h_ang,
                 int(show_until * 10) if show_until != float("inf") else sys.maxsize)
    if (cache_key == _last_default_stronghold and
            boat_resp == _last_default_boat):
        try:
            visible = bool(root.winfo_ismapped() and root.attributes("-alpha") and root.attributes("-alpha") > 0.0)
        except Exception:
            visible = True
        if visible:
            return

    _last_default_stronghold = cache_key
    _last_default_boat = boat_resp

    if result_type == "BLIND" and blind_enabled and blind_result and blind_result.get("evaluation"):
        if not show_blind_info_setting:
            with status_lock:
                status["blindShowUntil"] = 0
                status["blindCurrentlyShowing"] = False
            root.after(0, hide_window)
            return

        with status_lock:
            current_blind_show_until = status["blindShowUntil"]
            blind_currently_showing = status.get("blindCurrentlyShowing", False)

        if current_blind_show_until == -1:
            root.after(0, hide_window)
            return

        if not blind_currently_showing:
            _hide_enabled = bool(custom.get("blind_info_hide_after_enabled", False))
            _hide_after = float(custom.get("blind_info_hide_after", 20))
            with status_lock:
                if _hide_enabled:
                    status["blindShowUntil"] = now + _hide_after
                else:
                    status["blindShowUntil"] = float("inf")
                status["blindCurrentlyShowing"] = True
                current_blind_show_until = status["blindShowUntil"]

        if current_blind_show_until == float("inf") or now < current_blind_show_until:
            img = _render_nb_stronghold(
                preds, eye_throws, player_x, player_z, h_ang, in_nether,
                font_size, neg_coords_enabled, neg_coords_rgb, ow_coords_format,
                show_adj_count,
                blind_result=blind_result,
                boat_state=boat_state,
                user_font_path=user_font_path,
            )
            if img is None:
                root.after(0, hide_window)
                return
            _save_and_apply(img)
            return
        else:
            with status_lock:
                status["blindCurrentlyShowing"] = False
                status["blindShowUntil"] = -1
            root.after(0, hide_window)
            return

    if result_type != "BLIND" or not blind_enabled or not (blind_result and blind_result.get("evaluation")):
        with status_lock:
            if status.get("blindCurrentlyShowing", False) and not USE_CUSTOM_PINNED_IMAGE:
                status["blindCurrentlyShowing"] = False
                status["blindShowUntil"] = 0

    if result_type == "FAILED":
        img = _render_nb_stronghold(
            preds, eye_throws, player_x, player_z, h_ang, in_nether,
            font_size, neg_coords_enabled, neg_coords_rgb, ow_coords_format,
            show_adj_count,
            failed=True,
            boat_state=boat_state,
            user_font_path=user_font_path,
        )
        if img is None:
            img = _render_nb_failed_standalone(font_size)
        _save_and_apply(img)
        return

    if result_type in ("NONE",) and boat_state in ("VALID", "ERROR"):
        if not show_boat_icon_setting:
            root.after(0, hide_window)
            return

        with status_lock:
            now = time.time()
            show_until = status["showUntil"]
        if now < show_until:
            if boat_state == "ERROR":
                img = _render_nb_stronghold(
                    [], [], None, None, None, False,
                    font_size, neg_coords_enabled, neg_coords_rgb, ow_coords_format,
                    show_adj_count,
                    boat_state=boat_state,
                    force_empty=True,
                    user_font_path=user_font_path,
                )
                if img is not None:
                    _save_and_apply(img)
                else:
                    root.after(0, hide_window)
            elif boat_state == "VALID" and boat_angle is not None and boat_angle != 0:
                img = _render_nb_stronghold(
                    [], [], None, None, None, False,
                    font_size, neg_coords_enabled, neg_coords_rgb, ow_coords_format,
                    show_adj_count,
                    boat_state="VALID",
                    force_empty=True,
                    user_font_path=user_font_path,
                )
                if img is not None:
                    _save_and_apply(img)
                else:
                    root.after(0, hide_window)
            else:
                root.after(0, hide_window)
        else:
            root.after(0, hide_window)
        return

    if result_type not in ("TRIANGULATION", "BLIND") or not preds:
        root.after(0, hide_window)
        return

    img = _render_nb_stronghold(
        preds, eye_throws, player_x, player_z, h_ang, in_nether,
        font_size, neg_coords_enabled, neg_coords_rgb, ow_coords_format,
        show_adj_count,
        boat_state=boat_state,
        user_font_path=user_font_path,
    )
    if img is None:
        root.after(0, hide_window)
        return

    _save_and_apply(img)

def _save_and_apply(img):
    tmp = IMAGE_PATH + ".tmp.png"
    try:
        img.save(tmp, format="PNG")
        try:
            os.replace(tmp, IMAGE_PATH)
        except Exception:
            try:
                if os.path.exists(IMAGE_PATH):
                    os.remove(IMAGE_PATH)
                os.rename(tmp, IMAGE_PATH)
            except Exception as e:
                log("Failed to move tmp overlay file:", e)
    except Exception as e:
        log("Failed to save default overlay image:", e)
    root.after(0, lambda im=img: apply_overlay_from_pil(im))

def _make_draw_surface(w, h):
    img = Image.new("RGBA", (w, h), NB_ROW_BG)
    draw = ImageDraw.Draw(img)
    return img, draw

def _render_nb_stronghold(preds, eye_throws, player_x, player_z, h_ang,
                           in_nether, font_size, neg_coords_enabled,
                           neg_coords_rgb, ow_coords_format, show_adj_count,
                           blind_result=None, failed=False,
                           boat_state=None, force_empty=False, user_font_path=""):
    show_angle = (h_ang is not None and player_x is not None and player_z is not None)

    def _load_font_for_size(size):
        if user_font_path:
            try:
                return ImageFont.truetype(user_font_path, size)
            except Exception:
                pass
        return _load_nb_font(size)

    hdr_font   = _load_font_for_size(font_size)
    body_font  = _load_font_for_size(font_size)

    portal_warn_font    = _load_font_for_size(max(8, int(font_size * 0.85)))
    portal_warn_color   = NB_THROW_HEADER_FG
    small_font          = _load_font_for_size(max(8, int(font_size * 0.85)))
    new_header_font     = _load_font_for_size(max(10, int(font_size * 1.05)))
    new_header_ver_font = _load_font_for_size(max(8, int(font_size * 0.85)))

    a_new, d_new = new_header_font.getmetrics()
    new_header_h = a_new + d_new + 8

    NEW_HEADER_BG = (0x21, 0x25, 0x29)
    NEW_HEADER_VER_FG = (0x80, 0x80, 0x80)

    dummy_img  = Image.new("RGBA", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)

    def tw(text, fnt=body_font):
        return dummy_draw.textbbox((0, 0), text, font=fnt)[2]

    def th(fnt=body_font):
        a, d = fnt.getmetrics()
        return a + d

    CELL_PAD_MAIN  = 3
    CELL_PAD_THROW = 14
    HDR_SEP        = 1
    ROW_SEP        = 1
    body_h       = th(body_font)  + 4
    throw_body_h = th(body_font)  + 2
    hdr_h     = th(hdr_font)   + 4
    small_h = th(small_font) + 2

    rows = []
    for pred in preds[:5]:
        cx, cz = pred.get("chunkX"), pred.get("chunkZ")
        cert   = pred.get("certainty")
        dist   = pred.get("overworldDistance")
        if None in (cx, cz, cert, dist):
            continue

        if ow_coords_format == "chunk":
            ox, oz = cx, cz
        elif ow_coords_format == "eight_eight":
            ox, oz = cx * 16 + 8, cz * 16 + 8
        else:
            ox, oz = cx * 16 + 4, cz * 16 + 4
        if in_nether:
            ox, oz = round(ox / 8), round(oz / 8)

        nx, nz = round((cx * 16 + 4) / 8), round((cz * 16 + 4) / 8)
        cert_pct  = cert * 100
        dist_disp = int(dist / 8) if in_nether else int(dist)

        angle_str = None
        dir_val   = None
        if show_angle:
            sx = cx * 16 + 4
            sz = cz * 16 + 4
            if in_nether:
                sx /= 8.0; sz /= 8.0
                px, pz = player_x / 8.0, player_z / 8.0
            else:
                px, pz = player_x, player_z
            dx, dz = sx - px, sz - pz
            tgt    = (math.degrees(math.atan2(dz, dx)) + 270) % 360
            signed = ((tgt + 180) % 360) - 180
            turn   = ((tgt - (h_ang % 360) + 180) % 360) - 180
            angle_str = f"{signed:.2f}"
            dir_val   = turn

        rows.append({
            "loc":      (ox, oz),
            "cert_pct": cert_pct,
            "dist":     dist_disp,
            "nether":   (nx, nz),
            "angle":    angle_str,
            "dir":      dir_val,
        })

    hide_row_dividers = blind_result is not None or failed
    num_display_rows  = max(len(rows), 5) if hide_row_dividers else len(rows)
    if not rows and not hide_row_dividers and not force_empty:
        return None
    if force_empty:
        num_display_rows = 5

    adj_count_by_throw = {}
    if show_adj_count and eye_throws:
        nb_settings = get_ninjabrainbot_settings()
        for throw_idx, throw in enumerate(eye_throws):
            angle_with    = throw.get("angle", 0.0) or 0.0
            angle_without = throw.get("angleWithoutCorrection", 0.0) or 0.0
            correction    = angle_with - angle_without
            increments    = calculate_correction_increments(correction, nb_settings)
            if increments != 0:
                sign = "+" if increments >= 0 else ""
                adj_count_by_throw[throw_idx] = (f"{angle_without:.2f}", f"{sign}{increments}", increments)
            else:
                adj_count_by_throw[throw_idx] = (f"{angle_without:.2f}", None, None)

    loc_label  = "Chunk" if ow_coords_format == "chunk" else "Location"
    col_keys   = ["loc", "cert", "dist", "nether"]
    hdr_labels = {"loc": loc_label, "cert": "%", "dist": "Dist.", "nether": "Nether"}
    if show_angle or force_empty:
        col_keys.append("angle")
        hdr_labels["angle"] = "Angle"

    col_widths = {}
    _rep_samples = {
        "loc":    f"({12345}, {12345})",
        "cert":   "100.0%",
        "dist":   "10000",
        "nether": f"({12345}, {12345})",
        "angle":  "180.0 (-> 180.0)",
    }
    for key in col_keys:
        col_widths[key] = max(
            tw(hdr_labels[key], hdr_font) + CELL_PAD_MAIN * 2,
            tw(_rep_samples.get(key, ""), hdr_font) + CELL_PAD_MAIN * 2,
        )

    for r in rows:
        col_widths["loc"] = max(col_widths["loc"],
                                tw(f"({r['loc'][0]}, {r['loc'][1]})") + CELL_PAD_MAIN * 2)
        col_widths["cert"] = max(col_widths["cert"],
                                tw(f"{r['cert_pct']:.1f}%") + CELL_PAD_MAIN * 2)
        col_widths["dist"] = max(col_widths["dist"],
                                tw(str(r['dist'])) + CELL_PAD_MAIN * 2)
        col_widths["nether"] = max(col_widths["nether"],
                                tw(f"({r['nether'][0]}, {r['nether'][1]})") + CELL_PAD_MAIN * 2)
        if show_angle and r['angle'] is not None:
            full_a = r['angle']
            if r['dir'] is not None:
                arrow  = "->" if r['dir'] > 0 else "<-"
                full_a = full_a + f" ({arrow} {abs(r['dir']):.1f})"
            col_widths["angle"] = max(col_widths.get("angle", 0),
                                      tw(full_a) + CELL_PAD_MAIN * 2)

    throw_headers = ["x", "z", "Angle", "Error"]
    throw_rows_data = []
    for ti, t in enumerate(eye_throws):
        if show_adj_count and ti in adj_count_by_throw:
            aw_str, cnt_str, _ = adj_count_by_throw[ti]
            angle_cell = aw_str + (cnt_str if cnt_str else "")
        else:
            angle_cell = f"{t.get('angleWithoutCorrection', 0.0):.2f}"

        x_val = t.get("xInOverworld", 0.0) or 0.0
        z_val = t.get("zInOverworld", 0.0) or 0.0
        x_str = f"{float(x_val):.2f}"
        z_str = f"{float(z_val):.2f}"

        throw_rows_data.append((
            x_str,
            z_str,
            angle_cell,
            f"{t.get('error', 0.0):.4f}",
        ))

    throw_nat = [tw(h, small_font) + CELL_PAD_THROW * 2 for h in throw_headers]
    for trow in throw_rows_data:
        for i, cell in enumerate(trow):
            throw_nat[i] = max(throw_nat[i], tw(cell, small_font) + CELL_PAD_THROW * 2)

    main_table_w = sum(col_widths[k] for k in col_keys)

    min_blind_text_w = 0
    if blind_result is not None:
        evaluation    = blind_result.get("evaluation", "")
        x_nether      = blind_result.get("xInNether", 0)
        z_nether      = blind_result.get("zInNether", 0)
        highroll_prob  = blind_result.get("highrollProbability", 0) * 100
        highroll_thresh = blind_result.get("highrollThreshold", 400)
        improve_dir   = blind_result.get("improveDirection", 0)
        improve_dist  = blind_result.get("improveDistance", 0)
        _eval_text    = format_blind_evaluation(evaluation)
        _prefix       = f"Blind coords ({round(x_nether)}, {round(z_nether)}) are "
        _l2p          = f"{highroll_prob:.1f}%"
        _l2s          = f" chance of <{int(highroll_thresh)} block blind"
        _l3           = f"Head {math.degrees(improve_dir):.0f}°, {round(improve_dist)} blocks away, for better coords."
        min_blind_text_w = max(
            tw(_prefix) + tw(_eval_text),
            tw(_l2p) + tw(_l2s),
            tw(_l3),
        ) + CELL_PAD_MAIN * 2
    elif failed:
        _fl = [
            "Could not determine the stronghold chunk.",
            "",
            "You probably misread one of the eyes.",
        ]
        min_blind_text_w = max(tw(l) for l in _fl if l) + CELL_PAD_MAIN * 2

    rep_loc_sample = f"({12345}, {12345})"
    rep_cert_sample = "100.0%"
    rep_dist_sample = "10000"
    rep_nether_sample = rep_loc_sample
    rep_angle_sample = "180.0 (-> 180.0)"

    calc_col_w = {}
    for key in col_keys:
        if key == "loc":
            sample = rep_loc_sample
        elif key == "cert":
            sample = rep_cert_sample
        elif key == "dist":
            sample = rep_dist_sample
        elif key == "nether":
            sample = rep_nether_sample
        elif key == "angle":
            sample = rep_angle_sample
        else:
            sample = hdr_labels.get(key, "")
        calc_col_w[key] = max(col_widths.get(key, 0), tw(sample, hdr_font) + CELL_PAD_MAIN * 2)

    calc_main_table_w = sum(calc_col_w[k] for k in col_keys)

    rep_throw_samples = ["12345.67", "12345.67", "180.0", "0.0000"]
    calc_throw_nat = [tw(h, small_font) + CELL_PAD_THROW * 2 for h in throw_headers]
    for i, sample in enumerate(rep_throw_samples):
        calc_throw_nat[i] = max(calc_throw_nat[i], tw(sample, small_font) + CELL_PAD_THROW * 2)

    img_w = max(main_table_w, sum(throw_nat), min_blind_text_w, calc_main_table_w, sum(calc_throw_nat))

    current_main_w = sum(col_widths[k] for k in col_keys)

    if current_main_w < img_w:
        extra = img_w - current_main_w
        expand_keys = [k for k in col_keys if k != "angle"]
        if not expand_keys:
            expand_keys = col_keys
        per_col = extra // len(expand_keys)
        for k in expand_keys:
            col_widths[k] += per_col

        col_widths[expand_keys[-1]] += img_w - sum(col_widths[k] for k in col_keys)

    THROW_OUTER_PAD = CELL_PAD_THROW
    leftover = img_w - sum(throw_nat)
    if leftover < 0:
        leftover = 0

    outer_bonus = int(leftover * 0.20)
    centre_bonus = int(leftover * 0.30)

    throw_col_widths = list(throw_nat)
    throw_col_widths[0] += outer_bonus
    throw_col_widths[1] += centre_bonus
    throw_col_widths[2] += centre_bonus
    throw_col_widths[3] += outer_bonus

    throw_total = sum(throw_col_widths)
    if throw_total < img_w:
        diff = img_w - throw_total
        throw_col_widths[0] += diff // 4
        throw_col_widths[1] += diff // 4
        throw_col_widths[2] += diff // 4
        throw_col_widths[3] += img_w - throw_total - 3 * (diff // 4)

    top_headers_h = hdr_h
    top_headers_gap = HDR_SEP

    show_portal_warning = False
    if not hide_row_dividers and rows and eye_throws:
        first_throw = eye_throws[0]
        t_x = (first_throw.get("xInOverworld") or 0.0)
        t_z = (first_throw.get("zInOverworld") or 0.0)
        approx_portal_nether_x = t_x / 8.0
        approx_portal_nether_z = t_z / 8.0
        best = preds[0]
        best_nether_x = best.get("chunkX", 0) * 16 / 8.0 + 0.5
        best_nether_z = best.get("chunkZ", 0) * 16 / 8.0 + 0.5
        max_axis_distance = max(
            abs(approx_portal_nether_x - best_nether_x),
            abs(approx_portal_nether_z - best_nether_z),
        )
        show_portal_warning = max_axis_distance < 24

    _row_slot = body_h + (ROW_SEP if not hide_row_dividers else 0)
    main_h = new_header_h + HDR_SEP + HDR_SEP + top_headers_h + HDR_SEP + num_display_rows * _row_slot
    
    if show_portal_warning:
        warn_text_h = th(portal_warn_font)
        compact_warn_h = (warn_text_h * 2) + 1 + 5
        main_h += compact_warn_h

    num_throw_rows = max(len(throw_rows_data), 3)

    throw_h = 0
    if num_throw_rows:
        throw_h = HDR_SEP + hdr_h + small_h + HDR_SEP + num_throw_rows * (throw_body_h + ROW_SEP)

    img_h = main_h + throw_h

    img  = Image.new("RGBA", (img_w, img_h), NB_ROW_BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w - 1, new_header_h - 1], fill=NEW_HEADER_BG)
    nh_text_x = CELL_PAD_MAIN + 4
    nh_text_y = (new_header_h - th(new_header_font)) // 2
    draw.text((nh_text_x, nh_text_y), "NBTrackr", font=new_header_font, fill=NB_TEXT)
    ver_x = nh_text_x + tw("NBTrackr", new_header_font) + 8
    a_title, d_title = new_header_font.getmetrics()
    a_ver, d_ver = new_header_ver_font.getmetrics()

    title_baseline = nh_text_y + a_title
    ver_y = title_baseline - a_ver
    try:
        draw.text((ver_x, ver_y), APP_VERSION, font=new_header_ver_font, fill=NEW_HEADER_VER_FG)
    except Exception:
        pass

    _boat_icon_map = {
        "VALID":     "boat_green_icon.png",
        "ERROR":     "boat_red_icon.png",
        "MEASURING": "boat_blue_icon.png",
        "NONE":      "boat_gray_icon.png",
    }
    _boat_icon_file = _boat_icon_map.get(boat_state)
    if _boat_icon_file:
        _boat_icon_path = os.path.join(_get_assets_dir(), _boat_icon_file)
        try:
            _icon_size = new_header_h - 8
            with Image.open(_boat_icon_path) as _bicon:
                _bicon = _bicon.convert("RGBA").resize((_icon_size, _icon_size), Image.Resampling.LANCZOS)
                _icon_x = img_w - _icon_size - 20
                _icon_y = (new_header_h - _icon_size) // 2
                img.alpha_composite(_bicon, (_icon_x, _icon_y))
        except Exception:
            pass

    new_header_bottom = new_header_h + HDR_SEP

    top_header_y0 = new_header_bottom
    top_header_y1 = top_header_y0 + hdr_h - 1
    if not (blind_result is not None or failed):
        draw.rectangle([0, top_header_y0, img_w - 1, top_header_y0 + HDR_SEP - 1], fill=NB_HDR_SEP)
        draw.rectangle([0, top_header_y0 + HDR_SEP, img_w - 1, top_header_y1 + HDR_SEP], fill=NB_HEADER_BG)
        x = 0
        for key in col_keys:
            cw  = col_widths[key]
            lbl = hdr_labels[key]
            lw  = tw(lbl, hdr_font)
            if key == "angle" and show_angle:
                rep_base  = tw("000.00", hdr_font)
                rep_dir   = tw(" (-> 000.0)", hdr_font)
                rep_full  = rep_base + rep_dir
                cell_bx   = x + (cw - rep_full) // 2
                dir_start = cell_bx + rep_base
                text_x    = dir_start + (rep_dir - lw) // 2
                text_x    = max(x, min(text_x, x + cw - lw))
            else:
                text_x = x + (cw - lw) // 2
            draw.text((text_x, top_header_y0 + HDR_SEP + (hdr_h - th(hdr_font)) // 2),
                                lbl, font=hdr_font, fill=NB_TEXT)
            x += cw

        draw.rectangle([0, top_header_y1 + HDR_SEP + 1, img_w - 1, top_header_y1 + HDR_SEP + 1 + HDR_SEP - 1], fill=NB_HDR_SEP)

    row_area_y = new_header_bottom + HDR_SEP + hdr_h + HDR_SEP

    for row_idx in range(num_display_rows):
        row_slot = body_h + (ROW_SEP if not hide_row_dividers else 0)
        y = row_area_y + row_idx * row_slot
        if (not hide_row_dividers and row_idx < num_display_rows - 1) or (show_portal_warning and row_idx == num_display_rows - 1):
            draw.rectangle([0, y + body_h, img_w - 1, y + body_h + ROW_SEP - 1],
                           fill=NB_ROW_SEP)

        a_body, d_body = body_font.getmetrics()
        text_y = y + (body_h - (a_body + d_body)) // 2
        x = 0

        def draw_cell_centered(key, text, fill=NB_TEXT, fnt=body_font):
            nonlocal x
            cw  = col_widths[key]
            tw_ = dummy_draw.textbbox((0, 0), text, font=fnt)[2]
            draw.text((x + (cw - tw_) // 2, text_y), text, font=fnt, fill=fill)
            x += cw

        def draw_coord_cell(key, coord_pair):
            nonlocal x
            cw     = col_widths[key]
            cx_v, cz_v = coord_pair
            parts  = [
                ("(", NB_TEXT),
                (str(cx_v), neg_coords_rgb if neg_coords_enabled and cx_v < 0 else NB_TEXT),
                (", ", NB_TEXT),
                (str(cz_v), neg_coords_rgb if neg_coords_enabled and cz_v < 0 else NB_TEXT),
                (")", NB_TEXT),
            ]
            full_w = sum(tw(p[0]) for p in parts)
            bx = x + (cw - full_w) // 2
            for pt, pc in parts:
                draw.text((bx, text_y), pt, font=body_font, fill=pc)
                bx += tw(pt)
            x += cw

        if row_idx >= len(rows):
            for key in col_keys:
                x += col_widths[key]
            continue

        r = rows[row_idx]
        x = 0

        draw_coord_cell("loc", r['loc'])

        cert_txt = f"{r['cert_pct']:.1f}%"
        draw_cell_centered("cert", cert_txt, fill=certainty_color(r['cert_pct']))
        draw_cell_centered("dist", str(r['dist']))
        draw_coord_cell("nether", r['nether'])

        if show_angle and r['angle'] is not None:
            cw       = col_widths["angle"]
            base_str = r['angle']
            dir_part = ""
            dir_col  = NB_TEXT
            if r['dir'] is not None:
                arrow    = "->" if r['dir'] > 0 else "<-"
                dir_part = f" ({arrow} {abs(r['dir']):.1f})"
                dir_col  = gradient_color(abs(r['dir']))
            full_w = tw(base_str) + tw(dir_part)
            bx = x + (cw - full_w) // 2
            draw.text((bx, text_y), base_str, font=body_font, fill=NB_TEXT)
            if dir_part:
                draw.text((bx + tw(base_str), text_y), dir_part, font=body_font, fill=dir_col)
            x += cw

    if show_portal_warning:
        warn_area_start_y = row_area_y + num_display_rows * _row_slot
        warn_y = warn_area_start_y + 1 
        
        line1 = "You might not be able to nether travel into the stronghold due to"
        line2 = "portal linking."
        
        text_h = th(portal_warn_font)
        line_spacing = 1 
        total_text_h = (text_h * 2) + line_spacing

        icon_size = int(text_h * 1.1) 
        
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "warning_icon.png")
            with Image.open(icon_path) as icon_img:
                icon_img = icon_img.convert("RGBA").resize((icon_size, icon_size), Image.Resampling.LANCZOS)

                icon_y = warn_y + (total_text_h - icon_size) // 2
                img.alpha_composite(icon_img, (CELL_PAD_MAIN, icon_y))
                text_start_x = CELL_PAD_MAIN + icon_size + 8
        except Exception:
            text_start_x = CELL_PAD_MAIN

        draw.text((text_start_x, warn_y), line1, font=portal_warn_font, fill=portal_warn_color)
        draw.text((text_start_x, warn_y + text_h + line_spacing), line2, font=portal_warn_font, fill=portal_warn_color)

    if blind_result is not None:
        eval_color  = blind_evaluation_color(evaluation)
        txt_x  = CELL_PAD_MAIN
        txt_y  = new_header_bottom + (body_h - th(body_font)) // 2
        lsep   = body_h
        draw.text((txt_x, txt_y),          _prefix,   font=body_font, fill=NB_TEXT)
        draw.text((txt_x + tw(_prefix), txt_y), _eval_text, font=body_font, fill=eval_color)
        draw.text((txt_x, txt_y + lsep),   _l2p,      font=body_font, fill=eval_color)
        draw.text((txt_x + tw(_l2p), txt_y + lsep), _l2s, font=body_font, fill=NB_TEXT)
        draw.text((txt_x, txt_y + lsep * 2), _l3,     font=body_font, fill=NB_TEXT)
    elif failed:
        txt_x = CELL_PAD_MAIN
        for li, line in enumerate(_fl):
            if not line:
                continue
            txt_y = new_header_bottom + li * body_h + (body_h - th(body_font)) // 2
            draw.text((txt_x, txt_y), line, font=body_font, fill=NB_TEXT)

    if num_throw_rows:
        throw_base_y = main_h

        draw.rectangle([0, throw_base_y, img_w - 1, throw_base_y + HDR_SEP - 1],
                       fill=NB_HDR_SEP)

        throw_title_h = hdr_h
        th_title_y = throw_base_y + HDR_SEP
        draw.rectangle([0, th_title_y, img_w - 1, th_title_y + throw_title_h - 1], fill=NB_HEADER_BG)
        title_ty = th_title_y + (throw_title_h - th(hdr_font)) // 2
        draw.text((CELL_PAD_MAIN + 6, title_ty), "Ender eye throws", font=hdr_font, fill=NB_TEXT)

        th_hdr_y = th_title_y + throw_title_h
        draw.rectangle([0, th_hdr_y, img_w - 1, th_hdr_y + small_h - 1], fill=NB_HEADER_BG)
        x = 0
        for i, thdr in enumerate(throw_headers):
            cw = throw_col_widths[i]
            lw = tw(thdr, small_font)
            ty = th_hdr_y + (small_h - th(small_font)) // 2
            draw.text((x + (cw - lw) // 2, ty), thdr, font=small_font, fill=NB_TEXT)
            x += cw

        sep2_y = th_hdr_y + small_h
        draw.rectangle([0, sep2_y, img_w - 1, sep2_y + HDR_SEP - 1], fill=NB_HDR_SEP)

        for ti in range(num_throw_rows):
            ty = sep2_y + HDR_SEP + ti * (throw_body_h + ROW_SEP)

            if ti < num_throw_rows - 1:
                draw.rectangle([0, ty + throw_body_h, img_w - 1, ty + throw_body_h + ROW_SEP - 1],
                               fill=NB_ROW_SEP)

            x = 0
            if ti < len(throw_rows_data):
                trow = throw_rows_data[ti]
                for i, cell in enumerate(trow):
                    cw  = throw_col_widths[i]
                    a_small, _ = small_font.getmetrics()
                    ty2 = ty + (throw_body_h - a_small) // 2

                    if failed and i == 3:
                        x += cw
                        continue

                    if i == 2 and show_adj_count and ti in adj_count_by_throw:
                        aw_str, cnt_str, cnt_raw = adj_count_by_throw[ti]
                        if cnt_str:
                            adj_col  = ADJ_COUNT_POSITIVE if (cnt_raw is None or cnt_raw >= 0) else ADJ_COUNT_NEGATIVE
                            full_w   = tw(aw_str, small_font) + tw(cnt_str, small_font)
                            bx       = x + (cw - full_w) // 2
                            draw.text((bx, ty2), aw_str, font=small_font, fill=NB_THROW_HEADER_FG)
                            draw.text((bx + tw(aw_str, small_font),  ty2), cnt_str, font=small_font, fill=adj_col)
                        else:
                            cw_ = tw(aw_str, small_font)
                            draw.text((x + (cw - cw_) // 2, ty2), aw_str, font=small_font, fill=NB_THROW_HEADER_FG)
                    
                    else:
                        cw_ = tw(cell, small_font)
                        draw.text((x + (cw - cw_) // 2, ty2), cell, font=small_font, fill=NB_THROW_HEADER_FG)
                    x += cw
            else:
                for cw in throw_col_widths:
                    x += cw
    return img


def certainty_color_for_turn(abs_turn):
    return gradient_color(abs_turn)


def _render_nb_failed_standalone(font_size):
    font = _load_nb_font(font_size)
    a, d = font.getmetrics()
    body_h = a + d + 10
    dummy_img  = Image.new("RGBA", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    lines = [
        "Could not determine the stronghold chunk.",
        "You probably misread one of the eyes.",
    ]
    max_w = max(dummy_draw.textbbox((0, 0), l, font=font)[2] for l in lines)
    PAD  = 20
    img_w = max_w + PAD * 2
    img_h = body_h * len(lines) + PAD
    img  = Image.new("RGBA", (img_w, img_h), NB_ROW_BG)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        y  = PAD // 2 + i * body_h
        lw = dummy_draw.textbbox((0, 0), line, font=font)[2]
        draw.text(((img_w - lw) // 2, y + (body_h - (a + d)) // 2),
                  line, font=font, fill=NB_TEXT)
    return img

# --------------------- END Generate default pinned image overlay -----------


# --------------------- Generate custom pinned image overlay --------------------------


def generate_custom_pinned_image():
    global _last_custom, _last_boat, _last_stronghold, _last_blind

    global _cached_customizations, _last_custom_mtime
    try:
        mtime = os.path.getmtime(CUSTOMIZATIONS_FILE)
        if _cached_customizations is not None and mtime == _last_custom_mtime:
            custom = _cached_customizations
        else:
            with open(CUSTOMIZATIONS_FILE, "r") as f:
                custom = json.load(f)
            _cached_customizations = custom
            _last_custom_mtime = mtime
            log(f"[Config] Customizations reloaded from disk")
    except Exception as e:
        log("Failed to read customizations:", e)
        return

    bg_hex = custom.get("background_color", "#FFFFFF")
    text_hex = custom.get("text_color", "#000000")

    bg_rgb = hex_to_rgb(bg_hex, fallback=(255, 255, 255))
    text_rgb = hex_to_rgb(text_hex, fallback=(0, 0, 0))

    bg_rgba = (bg_rgb[0], bg_rgb[1], bg_rgb[2], 255)

    show_boat_icon     = custom.get("show_boat_icon", False)
    show_coords_by_dim = custom.get("show_coords_based_on_dimension", True)
    show_error_message = custom.get("show_error_message", False)
    boat_info_hide_after_enabled_setting = bool(custom.get("boat_info_hide_after_enabled", True))
    boat_info_hide_after_setting = float(custom.get("boat_info_hide_after", 10))
    show_blind_info    = custom.get("show_blind_info", True)
    blind_hide_after   = custom.get("blind_info_hide_after", 20)
    blind_hide_after_enabled  = custom.get("blind_info_hide_after_enabled", False)
    font_size          = custom.get("font_size", 18)
    show_adj_count     = custom.get("show_angle_adjustment_count", False)
    ow_coords_format   = custom.get("overworld_coords_format", "four_four")
    neg_coords_enabled = custom.get("negative_coords_color_enabled", False)
    neg_coords_hex     = custom.get("negative_coords_color", "#CC6E72")
    neg_coords_rgb     = hex_to_rgb(neg_coords_hex, fallback=(204, 110, 114))
    portal_nether_enabled = custom.get("portal_nether_color_enabled", True)
    portal_nether_hex     = custom.get("portal_nether_color", "#FFA500")
    portal_nether_rgb     = hex_to_rgb(portal_nether_hex, fallback=(255, 165, 0))
    show_angle_error    = custom.get("show_angle_error", False)
    angle_display_mode  = custom.get("angle_display_mode", "angle_and_change")
    show_overlay_header = custom.get("show_overlay_header", False)

    with status_lock:
        boat_resp       = dict(status["boat_resp"])
        stronghold_resp = dict(status["stronghold_resp"])
        blind_resp      = dict(status["blind_resp"])

    if not stronghold_resp:
        return

    boat_state  = boat_resp.get("boatState")
    boat_angle  = boat_resp.get("boatAngle", None)

    result_type = stronghold_resp.get("resultType")

    blind_enabled = blind_resp.get("isBlindModeEnabled", False)
    blind_result = blind_resp.get("blindResult", {})

    now = time.time()

    has_valid_blind_result = blind_result and blind_result.get("evaluation") is not None

    with status_lock:
        blind_was_showing = status.get("blindCurrentlyShowing", False)

    should_show_blind = (show_blind_info and blind_enabled and has_valid_blind_result and
                        result_type in ("NONE", "BLIND"))

    if blind_was_showing:
        should_hide = False

        if not show_blind_info:
            should_hide = True
        elif not blind_enabled:
            should_hide = True
        elif not has_valid_blind_result:
            should_hide = True
        elif result_type not in ("NONE", "BLIND"):
            should_hide = True

        if should_hide:
            log("Hiding blind info and clearing cache for regeneration")
            with status_lock:
                status["blindCurrentlyShowing"] = False
            _last_blind = None
            _last_custom = None
            _last_boat = None
            _last_stronghold = None

    if should_show_blind:
        with status_lock:
            blind_show_until = status["blindShowUntil"]
            blind_currently_showing = status.get("blindCurrentlyShowing", False)

            if blind_show_until > 0 and not blind_currently_showing:
                if blind_hide_after_enabled:
                    status["blindShowUntil"] = now + blind_hide_after
                    blind_show_until = status["blindShowUntil"]
                else:
                    status["blindShowUntil"] = float("inf")
                    blind_show_until = status["blindShowUntil"]

        if now < blind_show_until:
            blind_cache_key = (
                blind_result.get("evaluation"),
                blind_result.get("xInNether"),
                blind_result.get("zInNether"),
                blind_result.get("highrollProbability"),
                blind_result.get("highrollThreshold"),
                blind_result.get("improveDirection"),
                blind_result.get("improveDistance"),
                font_size,
                bg_hex,
                text_hex
            )

            if blind_currently_showing and blind_cache_key == _last_blind:
                log("Blind info unchanged, skipping regeneration")
                return

            _last_blind = blind_cache_key

            evaluation = blind_result.get("evaluation", "")
            x_nether = blind_result.get("xInNether", 0)
            z_nether = blind_result.get("zInNether", 0)
            highroll_prob = blind_result.get("highrollProbability", 0) * 100
            highroll_thresh = blind_result.get("highrollThreshold", 400)
            improve_dir = blind_result.get("improveDirection", 0)
            improve_dist = blind_result.get("improveDistance", 0)

            eval_text = format_blind_evaluation(evaluation)

            line1_pre = f"Blind coords ({round(x_nether)}, {round(z_nether)}) are "
            line1_eval = eval_text

            highroll_pct_text = f"{highroll_prob:.1f}%"
            line2_post = f" chance of <{int(highroll_thresh)} block blind"

            improve_deg = math.degrees(improve_dir)
            line3 = f"Head {improve_deg:.0f}°, {round(improve_dist)} blocks away, for better coords."

            font_name = custom.get("font_name", "")
            font = None
            if font_name:
                try:
                    font = ImageFont.truetype(font_name, font_size)
                except Exception:
                    pass
            if font is None:
                _default_font_path = os.path.join(_get_assets_dir(), "LiberationSans", "LiberationSans-Bold.ttf")
                try:
                    font = ImageFont.truetype(_default_font_path, font_size)
                except Exception:
                    font = ImageFont.load_default()

            dummy = ImageDraw.Draw(Image.new("RGBA",(1,1)))

            bbox_line1_pre = dummy.textbbox((0,0), line1_pre, font=font)
            bbox_line1_eval = dummy.textbbox((0,0), line1_eval, font=font)
            w_line1_pre = bbox_line1_pre[2] - bbox_line1_pre[0]
            w_line1_eval = bbox_line1_eval[2] - bbox_line1_eval[0]

            bbox_line2_pct = dummy.textbbox((0,0), highroll_pct_text, font=font)
            bbox_line2_post = dummy.textbbox((0,0), line2_post, font=font)
            w_line2_pct = bbox_line2_pct[2] - bbox_line2_pct[0]
            w_line2_post = bbox_line2_post[2] - bbox_line2_post[0]

            bbox_line3 = dummy.textbbox((0,0), line3, font=font)
            w_line3 = bbox_line3[2] - bbox_line3[0]

            max_w = max(w_line1_pre + w_line1_eval, w_line2_pct + w_line2_post, w_line3)

            ascent, descent = font.getmetrics()
            line_h = ascent + descent + 6
            height = line_h * 3 + 20

            pad = 10
            img = Image.new("RGBA", (int(max_w + 2*pad), height), bg_rgba)
            draw = ImageDraw.Draw(img)

            eval_color = blind_evaluation_color(evaluation)

            x = pad
            y = 10
            draw.text((x, y), line1_pre, font=font, fill=text_rgb)
            x += w_line1_pre
            draw.text((x, y), line1_eval, font=font, fill=eval_color)

            x = pad
            y += line_h
            draw.text((x, y), highroll_pct_text, font=font, fill=eval_color)
            x += w_line2_pct
            draw.text((x, y), line2_post, font=font, fill=text_rgb)

            y += line_h
            draw.text((pad, y), line3, font=font, fill=text_rgb)

            try:
                img.save(IMAGE_PATH)
                log(f"Saved blind overlay image, timer expires at {blind_show_until:.2f}")
            except Exception as e:
                log("Failed to save blind overlay image:", e)

            with status_lock:
                status["blindCurrentlyShowing"] = True

            root.after(0, lambda im=img: apply_overlay_from_pil(im))
            return



    if result_type == "TRIANGULATION":
        with status_lock:
            if status["blindShowUntil"] > 0:
                log("Result type is TRIANGULATION, clearing blind timer")
                status["blindShowUntil"] = 0

    if show_error_message and result_type == "FAILED":
        _last_custom, _last_boat, _last_stronghold = custom, boat_resp, stronghold_resp
        _cached_customizations = custom

        text = "Could not determine the stronghold chunk."
        font_name = custom.get("font_name", "")

        font_size = custom.get("font_size", 18)
        font = None
        if font_name:
            try:
                font = ImageFont.truetype(font_name, font_size)
            except Exception:
                pass
        if font is None:
            _default_font_path = os.path.join(_get_assets_dir(), "LiberationSans", "LiberationSans-Bold.ttf")
            try:
                font = ImageFont.truetype(_default_font_path, font_size)
            except Exception:
                font = ImageFont.load_default()

        dummy = ImageDraw.Draw(Image.new("RGBA",(1,1)))
        bbox = dummy.textbbox((0,0), text, font=font)
        text_w  = bbox[2] - bbox[0]
        text_h  = bbox[3] - bbox[1]
        offset_x = bbox[0]
        offset_y = bbox[1]

        pad = 10

        img = Image.new("RGBA", (text_w+2*pad, text_h+2*pad), bg_rgba)
        draw = ImageDraw.Draw(img)
        draw.text((pad - offset_x, pad - offset_y), text, font=font, fill=text_rgb)

        try:
            img.save(IMAGE_PATH)
        except Exception as e:
            log("Failed to save overlay image (error message):", e)
        root.after(0, lambda im=img: apply_overlay_from_pil(im))
        return

    with status_lock:
        last_shown = status["lastShown"]
        show_until = status["showUntil"]
    now = time.time()

    if show_boat_icon and result_type == "NONE":
        if boat_state == "VALID" and boat_angle == 0:
            root.after(0, hide_window)
            return

        if boat_state == last_shown and now < show_until:
            icon_file = "boat_green_icon.png" if boat_state == "VALID" else "boat_red_icon.png"
            icon_path = os.path.join(os.path.dirname(__file__), "assets", icon_file)
            try:
                icon = Image.open(icon_path).convert("RGBA")
                icon = icon.resize((64, 64), Image.LANCZOS)
            except Exception as e:
                log("Failed to load/process icon:", e)
            else:
                root.after(0, lambda im=icon: apply_overlay_from_pil(im, 64, 64))
        else:
            root.after(0, hide_window)
        return

    try:
        visible = False
        try:
            visible = bool(root.winfo_ismapped() and root.attributes("-alpha") and root.attributes("-alpha") > 0.0)
        except Exception:
            visible = bool(root.winfo_ismapped())
    except Exception:
        visible = True

    if (custom == _last_custom and
        boat_resp == _last_boat and
        stronghold_resp == _last_stronghold and
        visible):
        return

    _last_custom, _last_boat, _last_stronghold = custom, boat_resp, stronghold_resp

    preds      = stronghold_resp.get("predictions", [])
    eye_throws = stronghold_resp.get("eyeThrows", [])
    player_pos = stronghold_resp.get("playerPosition", {})
    player_x   = player_pos.get("xInOverworld")
    player_z   = player_pos.get("zInOverworld")
    h_ang      = player_pos.get("horizontalAngle")
    in_nether  = player_pos.get("isInNether", False)

    shown_count  = custom.get("shown_measurements", 5)
    order        = custom.get("text_order", [])
    enabled      = custom.get("text_enabled", {})
    show_dir     = custom.get("show_angle_direction", True)
    text_header  = custom.get("text_header", {})
    HEADER_LABELS = {
        "distance": "Dist.",
        "certainty_percentage": "%",
        "angle": "Angle",
        "overworld_coords": "Chunk" if ow_coords_format == "chunk" else "Location",
        "nether_coords": "Nether",
    }

    lines = []
    adj_count_overlays = []
    angle_error_overlays = []

    _portal_link_flags = []
    if portal_nether_enabled and eye_throws:
        _ft = eye_throws[0]
        _approx_nx = (_ft.get("xInOverworld") or 0.0) / 8.0
        _approx_nz = (_ft.get("zInOverworld") or 0.0) / 8.0
        for pred in preds[:shown_count]:
            cx = pred.get("chunkX", 0)
            cz = pred.get("chunkZ", 0)
            _best_nx = cx * 16 / 8.0 + 0.5
            _best_nz = cz * 16 / 8.0 + 0.5
            _max_axis = max(abs(_approx_nx - _best_nx), abs(_approx_nz - _best_nz))
            _portal_link_flags.append(_max_axis < 24)
    else:
        _portal_link_flags = [False] * shown_count

    for pred_idx, pred in enumerate(preds[:shown_count]):
        cx, cz = pred.get("chunkX"), pred.get("chunkZ")
        cert   = pred.get("certainty")
        dist   = pred.get("overworldDistance")
        if None in (cx, cz, cert, dist):
            continue

        parts = []
        for key in order:
            if not enabled.get(key, True):
                continue

            if key == "distance":
                d = dist/8 if in_nether else dist
                parts.append(("distance", (str(int(d)), d)))

            elif key == "certainty_percentage":
                pct = round(cert * 100, 1)
                parts.append(("certainty", f"{pct}%"))

            elif key == "angle" and None not in (h_ang, player_x, player_z):
                sx = cx*16 + 4
                sz = cz*16 + 4

                if in_nether:
                    sx /= 8.0
                    sz /= 8.0
                    p_x = player_x / 8.0
                    p_z = player_z / 8.0
                else:
                    p_x = player_x
                    p_z = player_z

                dx = sx - p_x
                dz = sz - p_z
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
                nx, nz = cx*16+4, cz*16+4
                if not (show_coords_by_dim and not in_nether):
                    nx, nz = round(nx/8), round(nz/8)
                parts.append(("nether_coords_val", (nx, nz)))

        if parts:
            _flag = _portal_link_flags[pred_idx] if pred_idx < len(_portal_link_flags) else False
            lines.append((parts, _flag))

    adj_count_overlays = []
    angle_error_overlays = []

    if eye_throws:
        for throw_idx, throw in enumerate(eye_throws):
            if show_adj_count:
                angle_with    = throw.get("angle", 0.0)
                angle_without = throw.get("angleWithoutCorrection", 0.0)
                correction    = angle_with - angle_without
                nb_settings   = get_ninjabrainbot_settings()
                increments    = calculate_correction_increments(correction, nb_settings)
                log("Throw", throw_idx, "adj count:", increments)

                if increments != 0:
                    sign = "+" if increments >= 0 else ""
                    adj_count_overlays.append((f"{angle_without:.2f}", f"{sign}{increments}", increments))
                else:
                    adj_count_overlays.append((f"{angle_without:.2f}", None, None))
                    log("Throw", throw_idx, "adj count: zero -> will display angleWithoutCorrection only")

            if show_angle_error:
                error_val = throw.get("error", None)
                if error_val is not None:
                    angle_error_overlays.append((f"{error_val:.4f}",))
                    log("Throw", throw_idx, "angle error:", error_val)

    log("generate_custom_pinned_image: predictions lines:", len(lines), "resultType:", result_type, "boatState:", boat_state)

    if not lines:
        root.after(0, hide_window)
        return

    font_name = custom.get("font_name", "")
    font_size = custom.get("font_size", 18)
    font = None
    if font_name:
        try:
            font = ImageFont.truetype(font_name, font_size)
        except Exception:
            pass
    if font is None:
        _default_font_path = os.path.join(_get_assets_dir(), "LiberationSans", "LiberationSans-Bold.ttf")
        try:
            font = ImageFont.truetype(_default_font_path, font_size)
        except Exception:
            font = ImageFont.load_default()

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 6

    has_header = any(text_header.get(k, "Text") == "Text" for k in order if enabled.get(k, True))
    header_h = line_h if has_header else 0

    max_w  = 0
    n_bottom_rows = max(len(adj_count_overlays), len(angle_error_overlays))

    small_font_size = max(8, int(font_size * 0.90))
    small_font_name = custom.get("font_name", "")
    small_font = None
    if small_font_name:
        try:
            small_font = ImageFont.truetype(small_font_name, small_font_size)
        except Exception:
            pass
    if small_font is None:
        _default_font_path = os.path.join(_get_assets_dir(), "LiberationSans", "LiberationSans-Bold.ttf")
        try:
            small_font = ImageFont.truetype(_default_font_path, small_font_size)
        except Exception:
            small_font = ImageFont.load_default()

    small_ascent, small_descent = small_font.getmetrics()
    small_line_h = small_ascent + small_descent + 4

    overlay_header_h_calc = small_line_h if (show_overlay_header and n_bottom_rows > 0) else 0
    bottom_extra_h = (overlay_header_h_calc + (small_line_h - 2) * n_bottom_rows + 4) if n_bottom_rows > 0 else 0
    height = header_h + line_h * len(lines) + 10 + bottom_extra_h

    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def _item_display_width(kind, val):
        if kind == "distance":
            try:
                txt, _ = val
            except Exception:
                txt = str(val)
        elif kind in ("coords", "nether_coords_val"):
            cx_v, cz_v = val
            txt = f"({cx_v}, {cz_v})"
        elif kind == "angle_change":
            arrow, num = val
            full_change = f"({arrow} {num})"
            return dummy.textbbox((0, 0), full_change, font=font)[2] + 14, full_change
        else:
            txt = str(val)
        gap = 14
        return dummy.textbbox((0, 0), txt, font=font)[2] + gap, txt

    col_widths = []
    for parts, _plink in lines:
        for slot_idx, item in enumerate(parts):
            w, _ = _item_display_width(item[0], item[1])
            if slot_idx >= len(col_widths):
                col_widths.append(w)
            else:
                col_widths[slot_idx] = max(col_widths[slot_idx], w)

    required_w = 10 + sum(col_widths) + 10

    img  = Image.new("RGBA", (int(required_w + 10), height), bg_rgba)
    draw = ImageDraw.Draw(img)

    col_x = []
    cx_acc = 10
    for w in col_widths:
        col_x.append(cx_acc)
        cx_acc += w
    rightmost_x = cx_acc
    _last_turn_pct = [0.0]

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
            tw_val = draw.textbbox((0, 0), hdr_txt, font=font)[2]
            if key == "angle" and angle_display_mode in ("angle_and_change",):
                change_slot = slots[-1]
                if change_slot < len(col_x) and change_slot < len(col_widths):
                    span_start = col_x[change_slot]
                    col_w_change = col_widths[change_slot]
                    hx = span_start + (col_w_change - tw_val) // 2
                else:
                    span_start = col_x[first_slot]
                    col_w_first = col_widths[first_slot]
                    hx = span_start + (col_w_first - tw_val) // 2
            else:
                span_start = col_x[first_slot]
                span_end = col_x[last_slot] + col_widths[last_slot]
                span_w = span_end - span_start
                hx = span_start + (span_w - tw_val) // 2
            draw.text((hx, 5), hdr_txt, font=font, fill=text_rgb)

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
            kind = item[0]
            val  = item[1]
            col_left  = col_x[slot_idx] if slot_idx < len(col_x) else 10
            col_w     = col_widths[slot_idx] if slot_idx < len(col_widths) else 0

            def _cx(txt):
                tw = draw.textbbox((0, 0), txt, font=font)[2]
                return col_left + (col_w - tw) // 2

            if kind == "certainty":
                txt = val
                try:
                    pct = float(txt.rstrip("%"))
                    fill = certainty_color(pct)
                except Exception:
                    fill = text_rgb
                draw.text((_cx(txt), y), txt, font=font, fill=fill)

            elif kind == "angle_change":
                arrow, num = val
                try:
                    _last_turn_pct[0] = float(num)
                except Exception:
                    pass
                fill = gradient_color(_last_turn_pct[0])
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
                _is_portal = portal_nether_enabled and _portal_link
                punct_fill = portal_nether_rgb if _is_portal else text_rgb
                x_fill = (portal_nether_rgb if _is_portal
                          else (neg_coords_rgb if neg_coords_enabled and cx_v < 0 else text_rgb))
                z_fill = (portal_nether_rgb if _is_portal
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

        max_w = max(max_w, rightmost_x)

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
                try:
                    txt, _ = val
                except Exception:
                    txt = str(val)
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
        pass
    else:
        overlay_header_h = overlay_header_h_calc
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
                    adj_fill = ADJ_COUNT_POSITIVE if (adj_raw is None or adj_raw >= 0) else ADJ_COUNT_NEGATIVE
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

    tmp = IMAGE_PATH + ".tmp.png"
    try:
        img.save(tmp, format="PNG")
        try:
            os.replace(tmp, IMAGE_PATH)
            log("Saved overlay image:", IMAGE_PATH)
        except Exception:
            try:
                if os.path.exists(IMAGE_PATH):
                    os.remove(IMAGE_PATH)
                os.rename(tmp, IMAGE_PATH)
                log("Saved overlay image via fallback rename:", IMAGE_PATH)
            except Exception as e:
                log("Failed to move tmp overlay file into place:", e)
    except Exception as e:
        log("Failed to save overlay image:", e)

    root.after(0, lambda im=img: apply_overlay_from_pil(im))

# --------------------- END Generate custom pinned image overlay ----------------------


def get_latest_github_release_version():
    url = "https://api.github.com/repos/qMaxXen/NBTrackr/releases/latest"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("tag_name")
    except Exception as e:
        if hasattr(e, 'response') and e.response is not None and e.response.status_code == 403:
            print("[Version Check] rate limit hit, skipping update check.")
            return None
        print(f"[Version Check Error] {e}")
        return None

def check_for_update(current_version):
    latest_version = get_latest_github_release_version()
    if latest_version and latest_version != current_version:
        return latest_version
    return None

def log(*args):
    if DEBUG_MODE:
        print(datetime.now().strftime("[%H:%M:%S]"), *args)


# ---------------------- AUTO UPDATER ----------------------

GITHUB_API = "https://api.github.com/repos/qMaxXen/NBTrackr/releases/latest"

def check_and_update(current_version):
    try:
        resp = requests.get(GITHUB_API, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        latest = data["tag_name"]
        if latest == current_version:
            return
        asset_name = f"NBTrackr-imgpin-{latest}.tar.xz"
        folder_name = asset_name.replace(".tar.xz", "")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        folder_path = os.path.join(parent_dir, folder_name)
        if os.path.exists(folder_path):
            print(f"[Updater] Latest version ({latest}) is already downloaded.")
            print(f"[Updater] Please navigate to the following folder to continue:")
            print(f"    {folder_path}")
            print("[Updater] Then run the script again from the new version.")
            sys.exit(0)
        download_url = next(
            (a["browser_download_url"] for a in data["assets"]
             if a["name"] == asset_name),
            None
        )
        if not download_url:
            print(f"[Updater] Couldn't find asset {asset_name} in release {latest}.")
            return
        print(f"[Updater] Downloading {asset_name} …")
        tmpdir = tempfile.mkdtemp()
        archive_path = os.path.join(tmpdir, asset_name)
        with requests.get(download_url, stream=True, timeout=10) as dl:
            dl.raise_for_status()
            with open(archive_path, "wb") as f:
                for chunk in dl.iter_content(8192):
                    f.write(chunk)
        print(f"[Updater] Extracting to {parent_dir} …")
        with tarfile.open(archive_path, "r:xz") as tar:
            tar.extractall(
                path=parent_dir,
                filter=lambda tarinfo, memberpath: tarinfo
            )
        os.remove(archive_path)
        body = data.get("body", "").strip()
        if body:
            print("\n[Updater] What's new:")
            print("-" * 40)
            print(body)
            print("-" * 40)
        print(f"\n[Updater] Update completed. New version extracted to:")
        print(f"    {folder_path}")
        print("[Updater] To finish setup, navigate to the new folder and run:")
        print("    chmod +x install.sh  # Make script executable")
        print("    ./install.sh         # Run installer")
        sys.exit(0)
    except Exception as e:
        print(f"[Updater] Update failed: {e}")

# ---------------------- AUTO UPDATER - END ----------------------

# ---------------------- Helpers ----------------------

def show_window():
    try:
        try:
            root.attributes("-disabled", False)
        except Exception:
            pass
        root.attributes("-alpha", 1.0)
        root.update_idletasks()
    except Exception:
        root.deiconify()

def hide_window():
    try:
        root.attributes("-alpha", 0.0)
        try:
            label.config(image=TRANSPARENT_TK)
            label.image = TRANSPARENT_TK
        except Exception:
            pass
        try:
            root.geometry(f"1x1+0+0")
        except Exception:
            root.geometry("1x1+0+0")
        root.update_idletasks()
    except Exception:
        try:
            label.config(image=TRANSPARENT_TK)
            label.image = TRANSPARENT_TK
        except Exception:
            pass
        root.withdraw()

def place_window(width, height):
    try:
        pos = load_config()
        if pos:
            sx, sy = pos
            root.geometry(f"{int(width)}x{int(height)}+{int(sx)}+{int(sy)}")
        else:
            cur_x = root.winfo_x()
            cur_y = root.winfo_y()
            root.geometry(f"{int(width)}x{int(height)}+{cur_x}+{cur_y}")
    except Exception:
        try:
            root.geometry(f"{int(width)}x{int(height)}+0+0")
        except Exception:
            pass

def apply_overlay_from_pil(pil_img, width=None, height=None):
    try:
        tk_img = ImageTk.PhotoImage(pil_img)
        label.config(image=tk_img)
        label.image = tk_img

        w = int(width) if width is not None else pil_img.width
        h = int(height) if height is not None else pil_img.height

        log(f"apply_overlay_from_pil: Applying overlay ({w}x{h}px)")

        place_window(w, h)
        show_window()
    except Exception as e:
        log("apply_overlay_from_pil: failed to apply overlay:", e)


# ---------------------- Helpers - END ----------------------

# --------------------- Config load/save --------------------------

def load_config():
    try:
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
            log(f"Created config directory: {CONFIG_DIR}")

        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            pos = config.get("position")
            if pos and isinstance(pos, dict):
                x = pos.get("x")
                y = pos.get("y")
                if isinstance(x, int) and isinstance(y, int):
                    log(f"Loaded window position from config: x={x}, y={y}")
                    return x, y
    except Exception as e:
        log(f"Failed to load config: {e}")
    return None

def save_config():
    try:
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
            log(f"Created config directory: {CONFIG_DIR}")

        x = root.winfo_x()
        y = root.winfo_y()
        config = {"position": {"x": x, "y": y}}
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        log(f"Saved window position to config: x={x}, y={y}")
    except Exception as e:
        log(f"Failed to save config: {e}")

def load_customizations():
    try:
        if os.path.exists(CUSTOMIZATIONS_FILE):
            with open(CUSTOMIZATIONS_FILE, "r") as f:
                data = json.load(f)
            val = data.get("use_custom_pinned_image", False)
            if isinstance(val, bool):
                log(f"Customizations: use_custom_pinned_image = {val}")
                return val
    except Exception as e:
        log(f"Failed to load customizations: {e}")
    return False

if __name__ == "__main__":
    print(f"NBTrackr version: {APP_VERSION}\n")

    latest = check_for_update(APP_VERSION)
    if latest:
        print(f"\n=== New Release Available! ===")
        print(f"Version: {latest}")
        print("You should update to the latest version!")
        print("1) Continue with the current version")
        print("2) Automatically update to the latest version")
        choice = input("Enter choice [1/2]: ").strip()
        print()
        if choice == "2":
            check_and_update(APP_VERSION)
        else:
            print("Skipping update. Continuing with current version", APP_VERSION, "\n")

# --------------------- NBTrackr Pinned Image Overlay Overlay --------------------------

IMAGE_PATH = "/tmp/imgpin-overlay.png"

GREEN_IMG = os.path.join(os.path.dirname(__file__), "assets/boat_green.png")
RED_IMG = os.path.join(os.path.dirname(__file__), "assets/boat_red.png")

root = tk.Tk()
root.overrideredirect(True)
root.wm_attributes("-topmost", True)

try:
    root.attributes("-alpha", 0.0)
except Exception:
    root.withdraw()

saved_pos = load_config()
if saved_pos:
    sx, sy = saved_pos
    try:
        root.geometry(f"+{sx}+{sy}")
    except Exception:
        pass

label = tk.Label(root, borderwidth=0, highlightthickness=0)
label.pack()

TRANSPARENT_IMG = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
TRANSPARENT_TK = ImageTk.PhotoImage(TRANSPARENT_IMG)

image_queue = queue.Queue(maxsize=1)

status_lock = threading.Lock()
status = {
    "boatState": None,
    "boatAngle": None,
    "resultType": None,
    "isInNether": False,
    "lastShown": None,
    "showUntil": 0,
    "lastAngle": None,
    "blindModeEnabled": False,
    "blindResult": None,
    "blindShowUntil": 0,
    "blindCurrentlyShowing": False,
    "boat_resp": {},
    "stronghold_resp": {},
    "blind_resp": {},
}

USE_CUSTOM_PINNED_IMAGE = load_customizations()

def idle_update_frequency():
    with status_lock:
        result_type = status["resultType"]
        blind_showing = status.get("blindCurrentlyShowing", False)

    if result_type == "TRIANGULATION" or (result_type == "BLIND" and blind_showing):
        return MAX_API_POLLING_RATE
    return IDLE_API_POLLING_RATE

def api_polling_thread():
    _nb_was_connected = False
    _nb_error_printed = False

    while True:
        try:
            boat_resp = requests.get("http://localhost:52533/api/v1/boat", timeout=0.5).json()
            stronghold_resp = requests.get("http://localhost:52533/api/v1/stronghold", timeout=0.5).json()
            blind_resp = requests.get("http://localhost:52533/api/v1/blind", timeout=0.5).json()

            if not _nb_was_connected:
                print("Connected to Ninjabrain Bot.")
                _nb_was_connected = True
                _nb_error_printed = False

            boat_state   = boat_resp.get("boatState")
            boat_angle   = boat_resp.get("boatAngle", None)
            result_type  = stronghold_resp.get("resultType")
            player_angle = stronghold_resp.get("playerPosition", {}).get("horizontalAngle")
            is_in_nether = stronghold_resp.get("playerPosition", {}).get("isInNether", False)

            now = time.time()

            blind_enabled = blind_resp.get("isBlindModeEnabled", False)
            blind_result = blind_resp.get("blindResult", {})

            with status_lock:
                _c = get_customizations()
                prev_state = status["lastShown"]
                prev_angle = status["lastAngle"]
                expired = now >= status["showUntil"]
                prev_blind_result = status["blindResult"]
                prev_blind_enabled = status["blindModeEnabled"]

                status["boatState"] = boat_state
                status["boatAngle"] = boat_angle
                status["resultType"] = result_type
                status["isInNether"] = is_in_nether
                status["blindModeEnabled"] = blind_enabled
                status["boat_resp"]       = boat_resp
                status["stronghold_resp"] = stronghold_resp
                status["blind_resp"]      = blind_resp

                blind_changed = False
                has_valid_result = blind_result and blind_result.get("evaluation") is not None
                prev_had_valid_result = prev_blind_result and prev_blind_result.get("evaluation") is not None

                if has_valid_result and prev_had_valid_result:
                    if (blind_result.get("evaluation") != prev_blind_result.get("evaluation") or
                        blind_result.get("xInNether") != prev_blind_result.get("xInNether") or
                        blind_result.get("zInNether") != prev_blind_result.get("zInNether")):
                        blind_changed = True
                elif has_valid_result and not prev_had_valid_result:
                    blind_changed = True
                elif not has_valid_result and prev_had_valid_result:
                    log("Blind result cleared (no calculations)")
                    status["blindShowUntil"] = 0

                status["blindResult"] = blind_result if has_valid_result else None

                show_blind_info_setting = bool(_c.get("show_blind_info", True))

                if blind_changed or (blind_enabled and not prev_blind_enabled and blind_result):
                    if not show_blind_info_setting:
                        status["blindShowUntil"] = 0
                    else:
                        _hide_enabled = _c.get("blind_info_hide_after_enabled", False)
                        _hide_after = _c.get("blind_info_hide_after", 20)
                        status["blindShowUntil"] = (now + _hide_after) if _hide_enabled else float("inf")

                if not blind_enabled or result_type == "TRIANGULATION":
                    if status["blindShowUntil"] > 0:
                        log("Clearing blind timer: disabled or triangulation mode")
                    status["blindShowUntil"] = 0

                show_boat_icon_setting = bool(_c.get("show_boat_icon", True))
                boat_info_hide_after_enabled_setting = bool(_c.get("boat_info_hide_after_enabled", True))
                boat_info_hide_after_setting = float(_c.get("boat_info_hide_after", 10))

                boat_hide_duration = boat_info_hide_after_setting if boat_info_hide_after_enabled_setting else float("inf")

                if result_type in ("NONE", "BLIND") and boat_state in ("VALID", "ERROR"):
                    if not show_boat_icon_setting:
                        status["lastShown"] = None
                        status["showUntil"] = 0
                        status["lastAngle"] = None
                    else:
                        if boat_state == "VALID":
                            if boat_angle == 0:
                                status["lastShown"] = None
                                status["showUntil"] = 0
                                status["lastAngle"] = None
                            elif boat_state != prev_state:
                                status["lastShown"] = boat_state
                                status["showUntil"] = now + boat_hide_duration
                                status["lastAngle"] = None
                            elif expired:
                                status["showUntil"] = 0
                        elif boat_state == "ERROR":
                            if boat_state != prev_state:
                                status["lastShown"] = boat_state
                                status["showUntil"] = now + boat_hide_duration
                                status["lastAngle"] = player_angle
                            elif expired:
                                if player_angle != prev_angle:
                                    status["showUntil"] = now + boat_hide_duration
                                    status["lastAngle"] = player_angle
                                else:
                                    status["showUntil"] = 0
                else:
                    status["lastShown"] = None
                    status["showUntil"] = 0
                    status["lastAngle"] = None

        except Exception:
            if _nb_was_connected:
                print("ERROR: Lost connection to Ninjabrain Bot.")
                _nb_was_connected = False
                _nb_error_printed = False
            if not _nb_error_printed:
                print("ERROR: Cannot connect to Ninjabrain Bot. Make sure it is running and API is enabled in Ninjabrain Bot > Settings > Advanced.")
                _nb_error_printed = True

            with status_lock:
                status["boatState"] = None
                status["boatAngle"] = None
                status["resultType"] = None
                status["isInNether"] = False
                status["lastShown"] = None
                status["showUntil"] = 0
                status["lastAngle"] = None
                status["blindModeEnabled"] = False
                status["blindResult"] = None
                status["blindShowUntil"] = 0
                status["blindCurrentlyShowing"] = False

        time.sleep(MAX_API_POLLING_RATE)

def image_update_thread():
    while True:
        if USE_CUSTOM_PINNED_IMAGE:
            generate_custom_pinned_image()
        else:
            generate_default_pinned_image()
        time.sleep(idle_update_frequency())

def blind_timer_monitor_thread():
    while True:
        with status_lock:
            blind_show_until = status["blindShowUntil"]
            blind_currently_showing = status.get("blindCurrentlyShowing", False)

        if blind_currently_showing and blind_show_until > 0:
            now = time.time()
            time_remaining = blind_show_until - now

            if time_remaining <= 0:
                log(f"[Timer Monitor] Blind timer expired, hiding")
                with status_lock:
                    status["blindCurrentlyShowing"] = False
                    status["blindShowUntil"] = -1
                try:
                    root.after(0, hide_window)
                except:
                    pass
                time.sleep(1)
            else:
                sleep_time = min(time_remaining, 1.0)
                log(f"[Timer Monitor] Sleeping {sleep_time:.1f}s until blind expires")
                time.sleep(sleep_time)
        else:
            time.sleep(1)

def update_image():
    global position_set

    try:
        img = image_queue.get_nowait()
    except queue.Empty:
        root.after(10, update_image)
        return

    if img is None:
        hide_window()
    else:
        tk_img = ImageTk.PhotoImage(img)
        label.configure(image=tk_img)
        label.image = tk_img

        place_window(img.width, img.height)
        position_set = True

        show_window()
    root.after(100, update_image)


def start_move(event):
    root._drag_start_x = event.x
    root._drag_start_y = event.y

def on_motion(event):
    x = event.x_root - root._drag_start_x
    y = event.y_root - root._drag_start_y
    root.geometry(f"+{x}+{y}")

def on_release(event):
    save_config()


root.bind("<ButtonPress-1>", start_move)
root.bind("<B1-Motion>", on_motion)
root.bind("<ButtonRelease-1>", on_release)

root.after(100, update_image)

threading.Thread(target=api_polling_thread, daemon=True).start()

threading.Thread(target=image_update_thread, daemon=True).start()
threading.Thread(target=blind_timer_monitor_thread, daemon=True).start()

root.mainloop()
