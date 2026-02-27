from multiprocessing import dummy
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
APP_VERSION = "v2.3.0"

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
        return False, 0.3, 0.15

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


# --------------------- Generate custom pinned image --------------------------


def generate_custom_pinned_image():
    global _last_custom, _last_boat, _last_stronghold, _last_blind

    global _cached_customizations
    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            custom = json.load(f)
        _cached_customizations = custom  
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
    show_blind_info    = custom.get("show_blind_info", True)
    blind_hide_after   = custom.get("blind_info_hide_after", 20)
    blind_hide_after_enabled  = custom.get("blind_info_hide_after_enabled", False)
    font_size          = custom.get("font_size", 18)
    show_adj_count     = custom.get("show_angle_adjustment_count", False)
    ow_coords_format   = custom.get("overworld_coords_format", "four_four")
    neg_coords_enabled = custom.get("negative_coords_color_enabled", False)
    neg_coords_hex     = custom.get("negative_coords_color", "#CC6E72")
    neg_coords_rgb     = hex_to_rgb(neg_coords_hex, fallback=(204, 110, 114))
    show_angle_error   = custom.get("show_angle_error", False)
    angle_display_mode = custom.get("angle_display_mode", "angle_and_change")

    try:
        boat_resp       = requests.get("http://localhost:52533/api/v1/boat", timeout=1).json()
        stronghold_resp = requests.get("http://localhost:52533/api/v1/stronghold", timeout=1).json()
        blind_resp      = requests.get("http://localhost:52533/api/v1/blind", timeout=1).json()
    except requests.exceptions.RequestException:
        print("ERROR: Ninjabrain Bot is not open or API is not enabled in Ninjabrain Bot.")
        return
    except Exception as e:
        log("API request failed in generate_custom_pinned_image:", e)
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
            
            line1_pre = f"Blind coords ({int(x_nether)}, {int(z_nether)}) are "
            line1_eval = eval_text
            
            highroll_pct_text = f"{highroll_prob:.1f}%"
            line2_post = f" chance of <{int(highroll_thresh)} block blind"
            
            improve_deg = math.degrees(improve_dir)
            line3 = f"Head {improve_deg:.0f}°, {int(improve_dist)} blocks away, for better coords."
            
            font_name = custom.get("font_name", "")
            font = None
            if font_name:
                try:
                    font = ImageFont.truetype(font_name, font_size)
                except Exception:
                    pass
            if font is None:
                for fallback in (
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
                    "DejaVuSans-Bold.ttf",
                ):
                    try:
                        font = ImageFont.truetype(fallback, font_size)
                        break
                    except Exception:
                        continue
            if font is None:
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
            for fallback in (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
                "DejaVuSans-Bold.ttf",
            ):
                try:
                    font = ImageFont.truetype(fallback, font_size)
                    break
                except Exception:
                    continue
        if font is None:
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

    if show_boat_icon and result_type != "TRIANGULATION":
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
                parts.append(("coords", (nx, nz)))

        if parts:
            lines.append(parts)

        if eye_throws and pred_idx < len(eye_throws):
            throw = eye_throws[pred_idx]
            if show_adj_count:
                angle_with    = throw.get("angle", 0.0)
                angle_without = throw.get("angleWithoutCorrection", 0.0)
                correction    = angle_with - angle_without
                nb_settings   = get_ninjabrainbot_settings()
                increments    = calculate_correction_increments(correction, nb_settings)
                log("Throw", pred_idx, "adj count:", increments)
                if increments != 0:
                    sign = "+" if increments >= 0 else ""
                    adj_count_overlays.append((f"{angle_without:.2f}", f"{sign}{increments}", increments))
            if show_angle_error:
                error_val = throw.get("error", None)
                if error_val is not None:
                    angle_error_overlays.append((f"{error_val:.4f}",))
                    log("Throw", pred_idx, "angle error:", error_val)

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
        for fallback in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ):
            try:
                font = ImageFont.truetype(fallback, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 6

    has_header = any(text_header.get(k, "Text") == "Text" for k in order if enabled.get(k, True))
    header_h = line_h if has_header else 0

    max_w  = 0
    n_bottom_rows = max(len(adj_count_overlays), len(angle_error_overlays))
    bottom_extra_h = (line_h - 4) * n_bottom_rows
    height = header_h + line_h * len(lines) + 10 + bottom_extra_h

    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def _item_display_width(kind, val):
        if kind == "distance":
            try:
                txt, _ = val
            except Exception:
                txt = str(val)
        elif kind == "coords":
            cx_v, cz_v = val
            txt = f"({cx_v}, {cz_v})"
        elif kind == "angle_change":
            arrow, num = val
            txt = arrow + num
            w = dummy.textbbox((0, 0), arrow, font=font)[2] + 5 + dummy.textbbox((0, 0), num, font=font)[2]
            return w + 14, txt
        else:
            txt = str(val)
        gap = 14
        return dummy.textbbox((0, 0), txt, font=font)[2] + gap, txt

    col_widths = [] 
    for parts in lines:
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
            span_start = col_x[first_slot]
            span_end = col_x[last_slot] + col_widths[last_slot]
            span_w = span_end - span_start
            tw = draw.textbbox((0, 0), hdr_txt, font=font)[2]
            hx = span_start + (span_w - tw) // 2
            draw.text((hx, 5), hdr_txt, font=font, fill=text_rgb)

    for row, parts in enumerate(lines):
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
                arrow_w = draw.textbbox((0, 0), arrow, font=font)[2]
                total_w = arrow_w + 4 + draw.textbbox((0, 0), num, font=font)[2]
                col_start = col_left + (col_w - total_w) // 2
                draw.text((col_start, y), arrow, font=font, fill=fill)
                draw.text((col_start + arrow_w + 5, y), num, font=font, fill=fill)

            elif kind == "distance":
                try:
                    txt, dval = val
                except Exception:
                    txt = str(val)
                    dval = None
                if in_nether:
                    fill = text_rgb
                else:
                    fill = (255, 165, 0) if (dval is not None and dval <= 193) else text_rgb
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

        max_w = max(max_w, rightmost_x)

    actual_left = None
    actual_right = None
    for parts in lines[-1:]:
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
            elif kind == "coords":
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
    for oi in range(n_overlay_rows):
        row_y = (header_h + line_h * len(lines) + 10) + oi * (line_h - 4) - 2

        if oi < len(adj_count_overlays):
            angle_txt, count_txt, adj_raw = adj_count_overlays[oi]
            adj_fill = ADJ_COUNT_POSITIVE if adj_raw >= 0 else ADJ_COUNT_NEGATIVE
            angle_w  = draw.textbbox((0, 0), angle_txt, font=font)[2]
            count_w  = draw.textbbox((0, 0), count_txt, font=font)[2]
            total_w  = angle_w + count_w
            adj_x    = actual_right - total_w
            adj_x    = max(adj_x, actual_left)
            draw.text((adj_x, row_y), angle_txt, font=font, fill=text_rgb)
            draw.text((adj_x + angle_w, row_y), count_txt, font=font, fill=adj_fill)

        if oi < len(angle_error_overlays):
            err_txt = angle_error_overlays[oi][0]
            draw.text((actual_left, row_y), err_txt, font=font, fill=text_rgb)
    
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

# --------------------- END Generate custom pinned image ----------------------


def get_latest_github_release_version():
    url = "https://api.github.com/repos/qMaxXen/NBTrackr/releases/latest"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("tag_name")
    except Exception as e:
        if e.response.status_code == 403:
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
            print(f"[Updater] Couldn’t find asset {asset_name} in release {latest}.")
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
        print("    ./install.sh")
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
    log("apply_overlay_from_pil: running on main thread")
    try:
        tk_img = ImageTk.PhotoImage(pil_img)
        label.config(image=tk_img)
        label.image = tk_img

        w = int(width) if width is not None else pil_img.width
        h = int(height) if height is not None else pil_img.height

        place_window(w, h)
        show_window()
        log("apply_overlay_from_pil: overlay applied (w=%d h=%d)" % (w, h))
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
    print(f"NBTrackr version: {APP_VERSION}")

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

# --------------------- NBTrackr Pinned Image Overlay --------------------------


IMAGE_PATH_DEFAULT = "/tmp/nb-overlay.png"
IMAGE_PATH_CUSTOM  = "/tmp/imgpin-overlay.png"


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
    "resultType": None,
    "isInNether": False,
    "lastShown": None,
    "showUntil": 0,
    "lastAngle": None,
    "blindModeEnabled": False,
    "blindResult": None,
    "blindShowUntil": 0,
    "blindCurrentlyShowing": False
}

USE_CUSTOM_PINNED_IMAGE = load_customizations()
IMAGE_PATH = IMAGE_PATH_CUSTOM if USE_CUSTOM_PINNED_IMAGE else IMAGE_PATH_DEFAULT

if USE_CUSTOM_PINNED_IMAGE:
    generate_custom_pinned_image()

def is_image_nonempty(path):
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return False
    try:
        with Image.open(path) as img:
            img = img.convert("RGBA")
            alpha = img.getchannel("A")
            return any(pixel != 0 for pixel in alpha.get_flattened_data())
    except Exception:
        return False

def idle_update_frequency():
    with status_lock:
        result_type = status["resultType"]
        blind_showing = status.get("blindCurrentlyShowing", False)
    
    if result_type == "TRIANGULATION" or (result_type == "BLIND" and blind_showing):
        return MAX_API_POLLING_RATE
    
    return IDLE_API_POLLING_RATE

def api_polling_thread():
    while True:
        try:
            boat_resp = requests.get("http://localhost:52533/api/v1/boat", timeout=0.5).json()
            stronghold_resp = requests.get("http://localhost:52533/api/v1/stronghold", timeout=0.5).json()
            blind_resp = requests.get("http://localhost:52533/api/v1/blind", timeout=0.5).json()

            boat_state = boat_resp.get("boatState")
            result_type = stronghold_resp.get("resultType")
            player_angle = stronghold_resp.get("playerPosition", {}).get("horizontalAngle")
            is_in_nether = stronghold_resp.get("playerPosition", {}).get("isInNether", False)

            now = time.time()
            
            blind_enabled = blind_resp.get("isBlindModeEnabled", False)
            blind_result = blind_resp.get("blindResult", {})
            
            with status_lock:
                prev_state = status["lastShown"]
                prev_angle = status["lastAngle"]
                expired = now >= status["showUntil"]
                prev_blind_result = status["blindResult"]
                prev_blind_enabled = status["blindModeEnabled"]

                status["boatState"] = boat_state
                status["resultType"] = result_type
                status["isInNether"] = is_in_nether
                status["blindModeEnabled"] = blind_enabled
                
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
                
                if blind_changed or (blind_enabled and not prev_blind_enabled and blind_result):
                    _c = get_customizations()
                    _hide_enabled = _c.get("blind_info_hide_after_enabled", False)
                    _hide_after = _c.get("blind_info_hide_after", 20)
                    status["blindShowUntil"] = (now + _hide_after) if _hide_enabled else float("inf")
                
                if not blind_enabled or result_type == "TRIANGULATION":
                    if status["blindShowUntil"] > 0:
                        log("Clearing blind timer: disabled or triangulation mode")
                    status["blindShowUntil"] = 0

                if result_type in ("NONE", "BLIND") and boat_state in ("VALID", "ERROR"):
                    if boat_state == "VALID":
                        if boat_state != prev_state:
                            status["lastShown"] = boat_state
                            status["showUntil"] = now + 10
                            status["lastAngle"] = None
                        elif expired:
                            status["showUntil"] = 0
                    elif boat_state == "ERROR":
                        if boat_state != prev_state:
                            status["lastShown"] = boat_state
                            status["showUntil"] = now + 10
                            status["lastAngle"] = player_angle
                        elif expired:
                            if player_angle != prev_angle:
                                status["showUntil"] = now + 10
                                status["lastAngle"] = player_angle
                            else:
                                status["showUntil"] = 0
                else:
                    status["lastShown"] = None
                    status["showUntil"] = 0
                    status["lastAngle"] = None

        except Exception:
            with status_lock:
                status["boatState"] = None
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

def custom_image_update_thread():
    while True:
        if USE_CUSTOM_PINNED_IMAGE:
            generate_custom_pinned_image()
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
                    status["blindShowUntil"] = 0
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

def image_loader_thread():
    last_logged_state = None
    last_used_path = None
    last_mod_time = 0

    while True:
        with status_lock:
            boat_state = status["boatState"]
            result_type = status["resultType"]
            last_shown = status["lastShown"]
            show_until = status["showUntil"]
            is_in_nether = status["isInNether"]
            now = time.time()

        path = None
        decision_reason = ""

        if not USE_CUSTOM_PINNED_IMAGE:
            if not is_in_nether and result_type in ("NONE", "BLIND"):
                if last_shown == "VALID" and now < show_until:
                    path = GREEN_IMG
                    decision_reason = "Showing GREEN boat image"
                elif last_shown == "ERROR" and now < show_until:
                    path = RED_IMG
                    decision_reason = "Showing RED boat image"


        if path is None and result_type in ("NONE", "BLIND") and boat_state in ("VALID", "ERROR") and now < show_until:
            if not USE_CUSTOM_PINNED_IMAGE and is_image_nonempty(IMAGE_PATH):
                path = IMAGE_PATH
                decision_reason = "Showing pinned overlay image"
            else:
                decision_reason = "Skipped pinned overlay image due to custom pinned image flag"

        if path is None and result_type == "TRIANGULATION":
            if not USE_CUSTOM_PINNED_IMAGE and is_image_nonempty(IMAGE_PATH):
                path = IMAGE_PATH
                decision_reason = "Showing overlay image for TRIANGULATION"
            else:
                decision_reason = "Skipped overlay image for TRIANGULATION due to custom pinned image flag"

        if path and is_image_nonempty(path):
            try:
                mod_time = os.path.getmtime(path)
                if path != last_used_path or mod_time != last_mod_time:
                    img = Image.open(path).convert("RGBA")
                    if image_queue.full():
                        try:
                            image_queue.get_nowait()
                        except queue.Empty:
                            pass
                    image_queue.put(img)
                    last_used_path = path
                    last_mod_time = mod_time
            except (UnidentifiedImageError, OSError):
                if image_queue.full():
                    try:
                        image_queue.get_nowait()
                    except queue.Empty:
                        pass
                image_queue.put(None)
                last_used_path = None
                last_mod_time = 0
        else:
            if image_queue.full():
                try:
                    image_queue.get_nowait()
                except queue.Empty:
                    pass
            image_queue.put(None)
            last_used_path = None
            last_mod_time = 0

        current_state = (boat_state, result_type, last_shown, is_in_nether, decision_reason)
        if current_state != last_logged_state:
            log("Boat:", boat_state, "| Result:", result_type,
                "| Shown:", last_shown, "| Nether:", is_in_nether,
                "| Action:", decision_reason)
            last_logged_state = current_state

        time.sleep(0.1)

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

if USE_CUSTOM_PINNED_IMAGE:
    threading.Thread(target=custom_image_update_thread, daemon=True).start()
    threading.Thread(target=blind_timer_monitor_thread, daemon=True).start()
else:
    threading.Thread(target=image_loader_thread, daemon=True).start()

root.mainloop()