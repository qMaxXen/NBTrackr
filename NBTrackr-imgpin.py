import json
import logging
import math
import os
import re
import signal
import sys
import threading
import time

import requests
import sseclient # needs "sseclient-py" package, not "sseclient"
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from core.qt_render import (
    apply_opacity,
    draw_text,
    draw_text_outlined,
    fill_rectangle,
    load_icon,
    load_qfont,
    metrics_for,
    new_canvas,
    text_height,
    text_width,
)
from core.updater import check_and_update, check_for_update
from shared.colors import (
    blind_evaluation_color,
    certainty_color,
    format_blind_evaluation,
    gradient_color,
    hex_to_rgb,
    with_alpha,
)

# Program Version
APP_VERSION = "v2.7.0"

CONFIG_DIR = os.path.expanduser("~/.config/NBTrackr")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

CUSTOMIZATIONS_FILE = os.path.join(CONFIG_DIR, "customizations.json")
HEADLESS = "--headless" in sys.argv
LOCK_OVERLAY = "--lock-overlay" in sys.argv
CLICK_THROUGH = "--click-through" in sys.argv
DEBUG_MODE_FLAG = "--debug" in sys.argv

position_set = False

_cached_customizations = None
_last_custom_mtime = 0
_last_overlay_w = 0
_last_overlay_h = 0
_window_visible = False

def _load_advanced_settings():
    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            data = json.load(f)
        return bool(data.get("debug_mode", False))
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return False

DEBUG_MODE = _load_advanced_settings()

if DEBUG_MODE or DEBUG_MODE_FLAG:
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(levelname)s %(filename)s:%(lineno)d - %(message)s",
        datefmt="%H:%M:%S",
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

logger = logging.getLogger(__name__)

def get_customizations():
    global _cached_customizations, _last_custom_mtime
    try:
        mtime = os.path.getmtime(CUSTOMIZATIONS_FILE)
    except FileNotFoundError:
        logger.debug("[Config] Customizations file not found, using defaults")
        _cached_customizations = {}
        _last_custom_mtime = 0
        return _cached_customizations
    except Exception:
        logger.exception("[Config] Failed to check customizations file modification time")
        if _cached_customizations is not None:
            return _cached_customizations
        return {}

    if _cached_customizations is not None and mtime == _last_custom_mtime:
        return _cached_customizations

    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            _cached_customizations = json.load(f)
        _last_custom_mtime = mtime
        logger.debug("[Config] Customizations reloaded from disk")
    except Exception:
        logger.exception("[Config] Failed to load customizations")
        if _cached_customizations is None:
            _cached_customizations = {}

    return _cached_customizations


def _strip_html(text):
    return re.sub(r"<[^>]+>", "", text)

def _get_virtual_desktop_geometry(app):
    combined = None
    for screen in app.screens():
        geo = screen.geometry()
        combined = geo if combined is None else combined.united(geo)
    return combined

def _get_assets_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


_nb_font_missing_warned = False


def _load_nb_font(size, custom_font_path=""):
    global _nb_font_missing_warned

    if custom_font_path:
        font = load_qfont(size, custom_font_path)
        if font is not None:
            return font
        logger.exception("Failed to load custom font: %s", custom_font_path)

    assets_dir = _get_assets_dir()
    font_path = os.path.join(assets_dir, "LiberationSans", "LiberationSans-Bold.ttf")
    if os.path.isfile(font_path):
        font = load_qfont(size, font_path)
        if font is not None:
            return font
        logger.exception("Failed to load bundled font: %s", font_path)

    if not _nb_font_missing_warned:
        logger.error(
            "Could not load bundled font at:\n"
            "  %s\n"
            "The overlay text will use a fallback font.\n"
            "Please reinstall NBTrackr: https://github.com/qMaxXen/NBTrackr/releases/latest.",
            font_path,
        )
        _nb_font_missing_warned = True
    return load_qfont(size)

# shared overlay colors

ADJ_COUNT_POSITIVE = (117, 204, 108)
ADJ_COUNT_NEGATIVE = (204, 110, 114)

NB_BG = (55, 60, 66, 255)
NB_HEADER_BG = (45, 50, 56, 255)
NB_HEADER_FG = (229, 229, 229)
NB_ROW_BG = (55, 60, 66, 255)
NB_TEXT = (255, 255, 255)
NB_THROW_HEADER_FG = (192, 192, 192)

NB_HDR_SEP = (33, 37, 41, 255)
NB_ROW_SEP = (42, 46, 50, 255)

# --------------------- Generate default pinned image overlay ---------------


def _interpolate_color(c1, c2, steps, step):
    r = int(c1[0] + (c2[0] - c1[0]) * step / max(steps - 1, 1))
    g = int(c1[1] + (c2[1] - c1[1]) * step / max(steps - 1, 1))
    b = int(c1[2] + (c2[2] - c1[2]) * step / max(steps - 1, 1))
    return (r, g, b)


_RED_HEX = (189, 65, 65)
_YELLOW = (216, 192, 100)
_GREEN_HEX = (89, 185, 75)


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
        "EXCELLENT": (_YELLOW, _GREEN_HEX, 51, 50),
        "HIGHROLL_GOOD": (_YELLOW, _GREEN_HEX, 51, 40),
        "HIGHROLL_OKAY": (_YELLOW, _GREEN_HEX, 51, 25),
        "BAD_BUT_IN_RING": (_YELLOW, _GREEN_HEX, 51, 0),
        "BAD": (_RED_HEX, _YELLOW, 51, 25),
        "NOT_IN_RING": (_RED_HEX, _YELLOW, 51, 0),
    }
    if evaluation in mapping:
        c1, c2, steps, step = mapping[evaluation]
        return _interpolate_color(c1, c2, steps, step)
    return (255, 255, 255)


def generate_default_pinned_image():
    img = None

    with status_lock:
        boat_resp = dict(status["boat_resp"])
        stronghold_resp = dict(status["stronghold_resp"])
        blind_resp = dict(status["blind_resp"])
        info_resp = dict(status["info_resp"])
        now = time.time()
        show_until = status.get("showUntil", 0)

    result_type = stronghold_resp.get("resultType")
    boat_state = boat_resp.get("boatState")
    boat_angle = boat_resp.get("boatAngle", None)
    preds = stronghold_resp.get("predictions", [])
    eye_throws = stronghold_resp.get("eyeThrows", [])
    player_pos = stronghold_resp.get("playerPosition", {})
    player_x = player_pos.get("xInOverworld")
    player_z = player_pos.get("zInOverworld")
    h_ang = player_pos.get("horizontalAngle")
    in_nether = player_pos.get("isInNether", False)
    blind_enabled = blind_resp.get("isBlindModeEnabled", False)
    blind_result = blind_resp.get("blindResult", {})

    customizations = get_customizations()
    font_size = int(customizations.get("font_size", 18))
    user_font_path = customizations.get("font_name", "")
    show_boat_icon_setting = bool(customizations.get("show_boat_icon", True))
    show_blind_info_setting = bool(customizations.get("show_blind_info", True))
    neg_coords_enabled = bool(customizations.get("negative_coords_color_enabled", False))
    neg_coords_rgb = hex_to_rgb(customizations.get("negative_coords_color", "#BA6669"), (186, 102, 105))
    ow_coords_format = customizations.get("overworld_coords_format", "four_four")
    show_adj_count = bool(customizations.get("show_angle_adjustment_count", False))
    auto_hide_window = bool(customizations.get("auto_hide_window", True))
    bg_opacity = max(0.0, min(1.0, float(customizations.get("background_opacity", 1.0))))
    text_opacity = max(0.0, min(1.0, float(customizations.get("text_opacity", 1.0))))

    if not stronghold_resp:
        if not auto_hide_window:
            img = _render_default_overlay_image(
                [],
                [],
                None,
                None,
                None,
                False,
                font_size,
                neg_coords_enabled,
                neg_coords_rgb,
                ow_coords_format,
                show_adj_count,
                boat_state="NONE",
                force_empty=True,
                user_font_path=user_font_path,
                bg_opacity=bg_opacity,
                text_opacity=text_opacity,
            )
            if img:
                _save_and_apply(img)
                return
        _schedule(clear_overlay_image)
        return

    info_messages = info_resp.get("informationMessages", [])

    if (
        result_type == "BLIND"
        and blind_enabled
        and blind_result
        and blind_result.get("evaluation")
    ):
        if not show_blind_info_setting:
            with status_lock:
                status["blindShowUntil"] = 0
                status["blindCurrentlyShowing"] = False
            _schedule(clear_overlay_image)
            return

        with status_lock:
            current_blind_show_until = status["blindShowUntil"]
            blind_currently_showing = status.get("blindCurrentlyShowing", False)

        if current_blind_show_until == -1:
            _schedule(clear_overlay_image)
            return

        if not blind_currently_showing:
            _hide_enabled = bool(customizations.get("blind_info_hide_after_enabled", False))
            _hide_after = float(customizations.get("blind_info_hide_after", 20))
            with status_lock:
                if _hide_enabled:
                    status["blindShowUntil"] = now + _hide_after
                else:
                    status["blindShowUntil"] = float("inf")
                status["blindCurrentlyShowing"] = True
                current_blind_show_until = status["blindShowUntil"]

        if current_blind_show_until == float("inf") or now < current_blind_show_until:
            img = _render_default_overlay_image(
                preds,
                eye_throws,
                player_x,
                player_z,
                h_ang,
                in_nether,
                font_size,
                neg_coords_enabled,
                neg_coords_rgb,
                ow_coords_format,
                show_adj_count,
                blind_result=blind_result,
                boat_state=boat_state,
                user_font_path=user_font_path,
                info_messages=info_messages,
                bg_opacity=bg_opacity,
                text_opacity=text_opacity,
            )
            if img is None:
                _schedule(clear_overlay_image)
                return
            _save_and_apply(img)
            return
        else:
            with status_lock:
                status["blindCurrentlyShowing"] = False
                status["blindShowUntil"] = -1

            if not auto_hide_window:
                img = _render_default_overlay_image(
                    preds,
                    eye_throws,
                    player_x,
                    player_z,
                    h_ang,
                    in_nether,
                    font_size,
                    neg_coords_enabled,
                    neg_coords_rgb,
                    ow_coords_format,
                    show_adj_count,
                    boat_state=boat_state,
                    force_empty=True,
                    user_font_path=user_font_path,
                    info_messages=info_messages,
                    bg_opacity=bg_opacity,
                    text_opacity=text_opacity,
                )
                if img:
                    _save_and_apply(img)
                    return
            _schedule(clear_overlay_image)
            return

    if (
        result_type != "BLIND"
        or not blind_enabled
        or not (blind_result and blind_result.get("evaluation"))
    ):
        with status_lock:
            if (
                status.get("blindCurrentlyShowing", False)
                and not USE_CUSTOM_PINNED_IMAGE
            ):
                status["blindCurrentlyShowing"] = False
                status["blindShowUntil"] = 0

    if result_type == "FAILED":
        img = _render_default_overlay_image(
            preds,
            eye_throws,
            player_x,
            player_z,
            h_ang,
            in_nether,
            font_size,
            neg_coords_enabled,
            neg_coords_rgb,
            ow_coords_format,
            show_adj_count,
            failed=True,
            boat_state=boat_state,
            user_font_path=user_font_path,
            info_messages=info_messages,
            bg_opacity=bg_opacity,
            text_opacity=text_opacity,
        )
        if img is None:
            img = _render_nb_failed_standalone(
                font_size, bg_opacity=bg_opacity, text_opacity=text_opacity
            )
        _save_and_apply(img)
        return

    if result_type in ("NONE",) and boat_state in ("VALID", "ERROR"):
        if not show_boat_icon_setting:
            _schedule(clear_overlay_image)
            return

        with status_lock:
            now = time.time()
            show_until = status["showUntil"]
        if now < show_until:
            if boat_state == "ERROR":
                img = _render_default_overlay_image(
                    [],
                    [],
                    None,
                    None,
                    None,
                    False,
                    font_size,
                    neg_coords_enabled,
                    neg_coords_rgb,
                    ow_coords_format,
                    show_adj_count,
                    boat_state=boat_state,
                    force_empty=True,
                    user_font_path=user_font_path,
                    bg_opacity=bg_opacity,
                    text_opacity=text_opacity,
                )
                if img is not None:
                    _save_and_apply(img)
                else:
                    _schedule(clear_overlay_image)
            elif boat_state == "VALID" and boat_angle is not None and boat_angle != 0:
                img = _render_default_overlay_image(
                    [],
                    [],
                    None,
                    None,
                    None,
                    False,
                    font_size,
                    neg_coords_enabled,
                    neg_coords_rgb,
                    ow_coords_format,
                    show_adj_count,
                    boat_state="VALID",
                    force_empty=True,
                    user_font_path=user_font_path,
                    bg_opacity=bg_opacity,
                    text_opacity=text_opacity,
                )
                if img is not None:
                    _save_and_apply(img)
                else:
                    _schedule(clear_overlay_image)
            else:
                if not auto_hide_window:
                    img = _render_default_overlay_image(
                        [],
                        [],
                        None,
                        None,
                        None,
                        False,
                        font_size,
                        neg_coords_enabled,
                        neg_coords_rgb,
                        ow_coords_format,
                        show_adj_count,
                        boat_state=boat_state,
                        force_empty=True,
                        user_font_path=user_font_path,
                        bg_opacity=bg_opacity,
                        text_opacity=text_opacity,
                    )
                    if img:
                        _save_and_apply(img)
                        return
                _schedule(clear_overlay_image)
        else:
            if not auto_hide_window:
                img = _render_default_overlay_image(
                    [],
                    [],
                    None,
                    None,
                    None,
                    False,
                    font_size,
                    neg_coords_enabled,
                    neg_coords_rgb,
                    ow_coords_format,
                    show_adj_count,
                    boat_state=boat_state,
                    force_empty=True,
                    user_font_path=user_font_path,
                    bg_opacity=bg_opacity,
                    text_opacity=text_opacity,
                )
                if img:
                    _save_and_apply(img)
                    return
            _schedule(clear_overlay_image)
        return

    if img is None:
        if (result_type in ("TRIANGULATION", "BLIND") and preds) or (
            result_type == "FAILED"
        ):
            img = _render_default_overlay_image(
                preds,
                eye_throws,
                player_x,
                player_z,
                h_ang,
                in_nether,
                font_size,
                neg_coords_enabled,
                neg_coords_rgb,
                ow_coords_format,
                show_adj_count,
                boat_state=boat_state,
                user_font_path=user_font_path,
                info_messages=info_messages,
                failed=(result_type == "FAILED"),
                bg_opacity=bg_opacity,
                text_opacity=text_opacity,
            )

    if img is None:
        if not auto_hide_window:
            img = _render_default_overlay_image(
                preds,
                eye_throws,
                player_x,
                player_z,
                h_ang,
                in_nether,
                font_size,
                neg_coords_enabled,
                neg_coords_rgb,
                ow_coords_format,
                show_adj_count,
                boat_state=boat_state,
                force_empty=True,
                user_font_path=user_font_path,
                info_messages=info_messages,
                bg_opacity=bg_opacity,
                text_opacity=text_opacity,
            )
            if img:
                _save_and_apply(img)
                return
        _schedule(clear_overlay_image)
        return

    _save_and_apply(img)

def _write_image_to_path(img, path):
    tmp = f"{path}.{threading.get_ident()}.tmp.png"
    try:
        if not img.save(tmp, "PNG"):
            raise OSError(f"QImage.save returned False for {tmp}")
    except Exception:
        logger.exception("Failed to save image to tmp file: %s", tmp)
        return
    try:
        os.replace(tmp, path)
    except Exception:
        logger.exception("Failed to replace image file, trying fallback: %s", path)
        try:
            if os.path.exists(path):
                os.remove(path)
            os.rename(tmp, path)
        except Exception:
            logger.exception("Failed to move tmp image file: %s", path)

def _save_and_apply(img):
    _schedule(lambda im=img: apply_overlay_from_qimage(im))
    _write_image_to_path(img, IMAGE_PATH)


def clear_overlay_image():
    empty = new_canvas(1, 1, (0, 0, 0, 0))
    _write_image_to_path(empty, IMAGE_PATH)
    if not HEADLESS:
        customizations = get_customizations()
        if bool(customizations.get("auto_hide_window", True)):
            _schedule(hide_window)
        else:
            if bool(customizations.get("use_custom_pinned_image", False)):
                _render_and_apply_blank_custom_overlay(customizations)
            else:
                empty = new_canvas(1, 1, (0, 0, 0, 0))
                _schedule(lambda im=empty: apply_overlay_from_qimage(im))


def _schedule(function):
    if HEADLESS:
        function()
    else:
        _scheduler.schedule(function)


def _make_draw_surface(w, h):
    img = new_canvas(w, h, NB_ROW_BG)
    painter = QPainter(img)
    return img, painter


def _render_default_overlay_image(
    preds,
    eye_throws,
    player_x,
    player_z,
    h_ang,
    in_nether,
    font_size,
    neg_coords_enabled,
    neg_coords_rgb,
    ow_coords_format,
    show_adj_count,
    blind_result=None,
    failed=False,
    boat_state=None,
    force_empty=False,
    user_font_path="",
    info_messages=None,
    bg_opacity=1.0,
    text_opacity=1.0,
):
    if info_messages is None:
        info_messages = []
    show_angle = h_ang is not None and player_x is not None and player_z is not None

    def _bc(color):
        return with_alpha(color[:3], bg_opacity)

    def _tc(color):
        return with_alpha(color[:3], text_opacity)

    def _tc_dyn(color):
        return with_alpha(color[:3], text_opacity)

    _NB_ROW_BG = _bc(NB_ROW_BG)
    _NB_HEADER_BG = _bc(NB_HEADER_BG)
    _NB_HDR_SEP = _bc(NB_HDR_SEP)
    _NB_ROW_SEP = _bc(NB_ROW_SEP)
    _NEW_HEADER_BG = _bc((0x21, 0x25, 0x29))

    _NB_TEXT = _tc(NB_TEXT)
    _NB_THROW_HDR_FG = _tc(NB_THROW_HEADER_FG)
    _NEW_HDR_VER_FG = _tc((0x80, 0x80, 0x80))
    _PORTAL_WARN_COLOR = _tc(NB_THROW_HEADER_FG)

    def _load_font_for_size(size):
        return _load_nb_font(size, user_font_path)

    hdr_font = _load_font_for_size(font_size)
    body_font = _load_font_for_size(font_size)

    portal_warn_font = _load_font_for_size(max(8, int(font_size * 0.85)))
    small_font = _load_font_for_size(max(8, int(font_size * 0.85)))
    new_header_font = _load_font_for_size(max(10, int(font_size * 1.05)))
    new_header_ver_font = _load_font_for_size(max(8, int(font_size * 0.85)))

    new_header_h = text_height(new_header_font) + 8

    def measure_text_width(text, fnt=body_font):
        return text_width(text, fnt)

    def measure_text_height(fnt=body_font):
        return text_height(fnt)

    CELL_PAD_MAIN = 3
    CELL_PAD_THROW = 14
    HDR_SEP = 1
    ROW_SEP = 1
    body_h = measure_text_height(body_font) + 4
    throw_body_h = measure_text_height(body_font) + 2
    hdr_h = measure_text_height(hdr_font) + 4
    small_h = measure_text_height(small_font) + 2

    rows = []
    for pred in preds[:5]:
        cx, cz = pred.get("chunkX"), pred.get("chunkZ")
        cert = pred.get("certainty")
        dist = pred.get("overworldDistance")
        if None in (cx, cz, cert, dist):
            continue

        if ow_coords_format == "chunk":
            ox, oz = cx, cz
        elif ow_coords_format == "eight_eight":
            ox, oz = cx * 16 + 8, cz * 16 + 8
        else:
            ox, oz = cx * 16 + 4, cz * 16 + 4

        nx, nz = round((cx * 16 + 4) / 8), round((cz * 16 + 4) / 8)
        cert_pct = cert * 100
        dist_disp = int(dist / 8) if in_nether else int(dist)

        angle_str = None
        dir_val = None
        if show_angle:
            sx = cx * 16 + 4
            sz = cz * 16 + 4
            if in_nether:
                sx /= 8.0
                sz /= 8.0
                px, pz = player_x / 8.0, player_z / 8.0
            else:
                px, pz = player_x, player_z
            dx, dz = sx - px, sz - pz
            tgt = (math.degrees(math.atan2(dz, dx)) + 270) % 360
            signed = ((tgt + 180) % 360) - 180
            turn = ((tgt - (h_ang % 360) + 180) % 360) - 180
            angle_str = f"{signed:.2f}"
            dir_val = turn

        rows.append(
            {
                "loc": (ox, oz),
                "cert_pct": cert_pct,
                "dist": dist_disp,
                "nether": (nx, nz),
                "angle": angle_str,
                "dir": dir_val,
            }
        )

    hide_row_dividers = blind_result is not None or failed
    num_display_rows = max(len(rows), 5) if hide_row_dividers else len(rows)
    if not rows and not hide_row_dividers and not force_empty:
        return None
    if force_empty:
        num_display_rows = 5

    adj_count_by_throw = {}
    if show_adj_count and eye_throws:
        for throw_idx, throw in enumerate(eye_throws):
            angle_without = throw.get("angleWithoutCorrection", 0.0) or 0.0
            increments = throw.get("correctionIncrements", 0) or 0
            if increments != 0:
                sign = "+" if increments >= 0 else ""
                adj_count_by_throw[throw_idx] = (
                    f"{angle_without:.2f}",
                    f"{sign}{increments}",
                    increments,
                )
            else:
                adj_count_by_throw[throw_idx] = (f"{angle_without:.2f}", None, None)

    loc_label = "Chunk" if ow_coords_format == "chunk" else "Location"
    col_keys = ["loc", "cert", "dist", "nether"]
    hdr_labels = {"loc": loc_label, "cert": "%", "dist": "Dist.", "nether": "Nether"}
    if show_angle or force_empty:
        col_keys.append("angle")
        hdr_labels["angle"] = "Angle"

    col_widths = {}
    if ow_coords_format == "chunk":
        _loc_sample = f"({-999}, {-999})"
    else:
        _loc_sample = f"({12345}, {12345})"
    _rep_samples = {
        "loc": _loc_sample,
        "cert": "100.0%",
        "dist": "10000",
        "nether": f"({12345}, {12345})",
        "angle": "180.0 (-> 180.0)",
    }
    for key in col_keys:
        col_widths[key] = max(
            measure_text_width(hdr_labels[key], hdr_font) + CELL_PAD_MAIN * 2,
            measure_text_width(_rep_samples.get(key, ""), hdr_font) + CELL_PAD_MAIN * 2,
        )

    for r in rows:
        col_widths["loc"] = max(
            col_widths["loc"], measure_text_width(f"({r['loc'][0]}, {r['loc'][1]})") + CELL_PAD_MAIN * 2
        )
        col_widths["cert"] = max(
            col_widths["cert"], measure_text_width(f"{r['cert_pct']:.1f}%") + CELL_PAD_MAIN * 2
        )
        col_widths["dist"] = max(
            col_widths["dist"], measure_text_width(str(r["dist"])) + CELL_PAD_MAIN * 2
        )
        col_widths["nether"] = max(
            col_widths["nether"],
            measure_text_width(f"({r['nether'][0]}, {r['nether'][1]})") + CELL_PAD_MAIN * 2,
        )
        if show_angle and r["angle"] is not None:
            full_a = r["angle"]
            if r["dir"] is not None:
                arrow = "->" if r["dir"] > 0 else "<-"
                full_a = full_a + f" ({arrow} {abs(r['dir']):.1f})"
            col_widths["angle"] = max(
                col_widths.get("angle", 0), measure_text_width(full_a) + CELL_PAD_MAIN * 2
            )

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

        throw_rows_data.append(
            (
                f"{float(x_val):.2f}",
                f"{float(z_val):.2f}",
                angle_cell,
                f"{t.get('error', 0.0):.4f}",
            )
        )

    throw_nat = [measure_text_width(h, small_font) + CELL_PAD_THROW * 2 for h in throw_headers]
    for trow in throw_rows_data:
        for i, cell in enumerate(trow):
            throw_nat[i] = max(throw_nat[i], measure_text_width(cell, small_font) + CELL_PAD_THROW * 2)

    main_table_w = sum(col_widths[k] for k in col_keys)

    min_blind_text_w = 0
    if blind_result is not None:
        evaluation = blind_result.get("evaluation", "")
        x_nether = blind_result.get("xInNether", 0)
        z_nether = blind_result.get("zInNether", 0)
        highroll_prob = blind_result.get("highrollProbability", 0) * 100
        highroll_thresh = blind_result.get("highrollThreshold", 400)
        improve_dir = blind_result.get("improveDirection", 0)
        improve_dist = blind_result.get("improveDistance", 0)
        _eval_text = format_blind_evaluation(evaluation)
        _prefix = f"Blind coords ({round(x_nether)}, {round(z_nether)}) are "
        _l2p = f"{highroll_prob:.1f}%"
        _l2s = f" chance of <{int(highroll_thresh)} block blind"
        _l3 = f"Head {math.degrees(improve_dir):.0f}°, {round(improve_dist)} blocks away, for better coords."
        min_blind_text_w = (
            max(
                measure_text_width(_prefix) + measure_text_width(_eval_text),
                measure_text_width(_l2p) + measure_text_width(_l2s),
                measure_text_width(_l3),
            )
            + CELL_PAD_MAIN * 2
        )
    elif failed:
        _fl = [
            "Could not determine the stronghold chunk.",
            "",
            "You probably misread one of the eyes.",
        ]
        min_blind_text_w = max(measure_text_width(line) for line in _fl if line) + CELL_PAD_MAIN * 2

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
        calc_col_w[key] = max(
            col_widths.get(key, 0), measure_text_width(sample, hdr_font) + CELL_PAD_MAIN * 2
        )

    calc_main_table_w = sum(calc_col_w[k] for k in col_keys)

    rep_throw_samples = ["12345.67", "12345.67", "180.0", "0.0000"]
    calc_throw_nat = [measure_text_width(h, small_font) + CELL_PAD_THROW * 2 for h in throw_headers]
    for i, sample in enumerate(rep_throw_samples):
        calc_throw_nat[i] = max(
            calc_throw_nat[i], measure_text_width(sample, small_font) + CELL_PAD_THROW * 2
        )

    img_w = max(
        main_table_w,
        sum(throw_nat),
        min_blind_text_w,
        calc_main_table_w,
        sum(calc_throw_nat),
    )

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

    leftover = img_w - sum(throw_nat)
    leftover = max(leftover, 0)

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

    show_portal_warning = any(m.get("type") == "PORTAL_LINKING" for m in info_messages)

    top_headers_h = hdr_h

    _row_slot = body_h + (ROW_SEP if not hide_row_dividers else 0)
    main_h = (
        new_header_h
        + HDR_SEP
        + HDR_SEP
        + top_headers_h
        + HDR_SEP
        + num_display_rows * _row_slot
    )

    _display_info_messages = [
        m
        for m in info_messages
        if m.get("type")
        in (
            "PORTAL_LINKING",
            "NEXT_THROW_DIRECTION",
            "MISMEASURE",
            "COMBINED_CERTAINTY",
        )
    ]
    warn_text_h = measure_text_height(portal_warn_font)
    _TWO_LINE_TYPES = (
        "NEXT_THROW_DIRECTION",
        "MISMEASURE",
        "PORTAL_LINKING",
        "COMBINED_CERTAINTY",
    )

    def _info_msg_h(msg):
        if msg.get("type") in _TWO_LINE_TYPES:
            return warn_text_h * 2 + 4 + 6
        return warn_text_h + 6

    total_info_h = sum(_info_msg_h(m) for m in _display_info_messages)
    if _display_info_messages:
        total_info_h += ROW_SEP
    if len(_display_info_messages) > 1:
        total_info_h += ROW_SEP * (len(_display_info_messages) - 1)
    main_h += total_info_h

    num_throw_rows = max(len(throw_rows_data), 3)
    throw_h = 0
    if num_throw_rows:
        throw_h = (
            HDR_SEP
            + hdr_h
            + small_h
            + HDR_SEP
            + num_throw_rows * (throw_body_h + ROW_SEP)
        )

    img_h = main_h + throw_h

    img = new_canvas(img_w, img_h, _NB_ROW_BG)
    painter = QPainter(img)

    fill_rectangle(painter, 0, 0, img_w - 1, new_header_h - 1, _NEW_HEADER_BG)
    nh_text_x = CELL_PAD_MAIN + 4
    nh_text_y = (new_header_h - measure_text_height(new_header_font)) // 2
    draw_text(painter, nh_text_x, nh_text_y, "NBTrackr", new_header_font, _NB_TEXT)
    ver_x = nh_text_x + measure_text_width("NBTrackr", new_header_font) + 8
    m_title = metrics_for(new_header_font)
    m_ver = metrics_for(new_header_ver_font)
    title_baseline = nh_text_y + m_title.ascent()
    ver_y = title_baseline - m_ver.ascent()
    draw_text(painter, ver_x, ver_y, APP_VERSION, new_header_ver_font, _NEW_HDR_VER_FG)

    _boat_icon_map = {
        "VALID": "boat_green_icon.png",
        "ERROR": "boat_red_icon.png",
        "MEASURING": "boat_blue_icon.png",
        "NONE": "boat_gray_icon.png",
    }
    _boat_icon_file = _boat_icon_map.get(boat_state)
    if _boat_icon_file:
        _boat_icon_path = os.path.join(_get_assets_dir(), _boat_icon_file)
        try:
            _icon_size = new_header_h - 8
            _boat_icon_image = load_icon(_boat_icon_path, _icon_size)
            if _boat_icon_image is not None:
                _boat_icon_image = apply_opacity(_boat_icon_image, text_opacity)
                _icon_x = img_w - _icon_size - 20
                _icon_y = (new_header_h - _icon_size) // 2
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
                painter.drawImage(_icon_x, _icon_y, _boat_icon_image)
        except Exception:
            logger.exception("Failed to load boat icon: %s", _boat_icon_path)

    new_header_bottom = new_header_h + HDR_SEP

    top_header_y0 = new_header_bottom
    top_header_y1 = top_header_y0 + hdr_h - 1
    if not (blind_result is not None or failed):
        fill_rectangle(painter, 0, top_header_y0, img_w - 1, top_header_y0 + HDR_SEP - 1, _NB_HDR_SEP)
        fill_rectangle(painter, 0, top_header_y0 + HDR_SEP, img_w - 1, top_header_y1 + HDR_SEP, _NB_HEADER_BG)
        x = 0
        for key in col_keys:
            cw = col_widths[key]
            lbl = hdr_labels[key]
            lw = measure_text_width(lbl, hdr_font)
            if key == "angle" and show_angle:
                rep_base = measure_text_width("000.00", hdr_font)
                rep_dir = measure_text_width(" (-> 000.0)", hdr_font)
                rep_full = rep_base + rep_dir
                cell_bx = x + (cw - rep_full) // 2
                dir_start = cell_bx + rep_base
                text_x_pos = dir_start + (rep_dir - lw) // 2
                text_x_pos = max(x, min(text_x_pos, x + cw - lw))
            else:
                text_x_pos = x + (cw - lw) // 2
            draw_text(
                painter,
                text_x_pos,
                top_header_y0 + HDR_SEP + (hdr_h - measure_text_height(hdr_font)) // 2,
                lbl,
                hdr_font,
                _NB_TEXT,
            )
            x += cw
        fill_rectangle(
            painter,
            0,
            top_header_y1 + HDR_SEP + 1,
            img_w - 1,
            top_header_y1 + HDR_SEP + 1 + HDR_SEP - 1,
            _NB_HDR_SEP,
        )

    row_area_y = new_header_bottom + HDR_SEP + hdr_h + HDR_SEP

    for row_idx in range(num_display_rows):
        row_slot = body_h + (ROW_SEP if not hide_row_dividers else 0)
        y = row_area_y + row_idx * row_slot
        if (not hide_row_dividers and row_idx < num_display_rows - 1) or (
            show_portal_warning and row_idx == num_display_rows - 1
        ):
            fill_rectangle(painter, 0, y + body_h, img_w - 1, y + body_h + ROW_SEP - 1, _NB_ROW_SEP)

        text_y = y + (body_h - measure_text_height(body_font)) // 2
        x = 0

        def draw_cell_centered(key, text, fill=_NB_TEXT, fnt=body_font):
            nonlocal x
            cw = col_widths[key]
            tw_ = text_width(text, fnt)
            draw_text(painter, x + (cw - tw_) // 2, text_y, text, fnt, fill)
            x += cw

        def draw_coord_cell(key, coord_pair):
            nonlocal x
            cw = col_widths[key]
            cx_v, cz_v = coord_pair
            parts = [
                ("(", _NB_TEXT),
                (
                    str(cx_v),
                    _tc(neg_coords_rgb)
                    if neg_coords_enabled and cx_v < 0
                    else _NB_TEXT,
                ),
                (", ", _NB_TEXT),
                (
                    str(cz_v),
                    _tc(neg_coords_rgb)
                    if neg_coords_enabled and cz_v < 0
                    else _NB_TEXT,
                ),
                (")", _NB_TEXT),
            ]
            full_w = sum(measure_text_width(p[0]) for p in parts)
            bx = x + (cw - full_w) // 2
            for pt, pc in parts:
                draw_text(painter, bx, text_y, pt, body_font, pc)
                bx += measure_text_width(pt)
            x += cw

        if row_idx >= len(rows):
            x = 0
            for key in col_keys:
                x += col_widths[key]
        else:
            r = rows[row_idx]
            x = 0
            draw_coord_cell("loc", r["loc"])
            cert_txt = f"{r['cert_pct']:.1f}%"
            draw_cell_centered(
                "cert", cert_txt, fill=_tc_dyn(certainty_color(r["cert_pct"]))
            )
            draw_cell_centered("dist", str(r["dist"]))
            draw_coord_cell("nether", r["nether"])

            if show_angle and r["angle"] is not None:
                cw = col_widths["angle"]
                base_str = r["angle"]
                dir_part = ""
                dir_col = _NB_TEXT
                if r["dir"] is not None:
                    arrow = "->" if r["dir"] > 0 else "<-"
                    dir_part = f" ({arrow} {abs(r['dir']):.1f})"
                    dir_col = _tc_dyn(gradient_color(abs(r["dir"])))
                full_w = measure_text_width(base_str) + measure_text_width(dir_part)
                bx = x + (cw - full_w) // 2
                draw_text(painter, bx, text_y, base_str, body_font, _NB_TEXT)
                if dir_part:
                    draw_text(
                        painter,
                        bx + measure_text_width(base_str),
                        text_y,
                        dir_part,
                        body_font,
                        dir_col,
                    )
                x += cw

    if _display_info_messages:
        info_area_start_y = row_area_y + num_display_rows * _row_slot

        def _split_two_lines(msg_type, text):
            if msg_type == "NEXT_THROW_DIRECTION":
                marker = "after next"
                idx = text.find(marker)
                if idx != -1:
                    split_pos = idx + len(marker)
                    line1 = text[:split_pos].rstrip()
                    line2 = text[split_pos:].lstrip()
                    if line2:
                        return line1, line2
                return text, None
            if msg_type == "MISMEASURE":
                marker = "mismeasured or"
                idx = text.find(marker)
                if idx != -1:
                    split_pos = idx + len(marker)
                    line1 = text[:split_pos].rstrip()
                    line2 = text[split_pos:].lstrip()
                    if line2:
                        return line1, line2
                return text, None
            if msg_type == "PORTAL_LINKING":
                marker = "due to"
                idx = text.find(marker)
                if idx != -1:
                    split_pos = idx + len(marker)
                    line1 = text[:split_pos].rstrip()
                    line2 = text[split_pos:].lstrip()
                    if line2:
                        return line1, line2
                return text, None
            if msg_type == "COMBINED_CERTAINTY":
                marker = "stronghold (it"
                idx = text.find(marker)
                if idx != -1:
                    split_pos = idx + len(marker)
                    line1 = text[:split_pos].rstrip()
                    line2 = text[split_pos:].lstrip()
                    if line2:
                        return line1, line2
                return text, None
            return text, None

        current_info_y = info_area_start_y
        fill_rectangle(painter, 0, current_info_y, img_w - 1, current_info_y + ROW_SEP - 1, _NB_ROW_SEP)
        current_info_y += ROW_SEP
        for msg_idx, msg in enumerate(_display_info_messages):
            severity = msg.get("severity", "WARNING")
            msg_type = msg.get("type", "")
            text = _strip_html(msg.get("message", ""))
            text_h = measure_text_height(portal_warn_font)
            icon_size = int(text_h * 1.1)
            this_msg_h = _info_msg_h(msg)
            row_y = current_info_y

            if severity == "INFO":
                icon_file = "info_icon.png"
            else:
                icon_file = "warning_icon.png"
            icon_path = os.path.join(_get_assets_dir(), icon_file)
            try:
                icon_img = load_icon(icon_path, icon_size)
                if icon_img is not None:
                    icon_img = apply_opacity(icon_img, text_opacity)
                    icon_y = row_y + (this_msg_h - icon_size) // 2
                    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
                    painter.drawImage(CELL_PAD_MAIN, icon_y, icon_img)
                text_start_x = CELL_PAD_MAIN + icon_size + 8
            except Exception:
                logger.exception("Failed to load info message icon: %s", icon_path)
                text_start_x = CELL_PAD_MAIN

            if msg_type in _TWO_LINE_TYPES:
                line1, line2 = _split_two_lines(msg_type, text)
                if line2:
                    line_gap = 4
                    total_text_h = text_h * 2 + line_gap
                    text_y1 = row_y + (this_msg_h - total_text_h) // 2
                    text_y2 = text_y1 + text_h + line_gap
                    if msg_type == "COMBINED_CERTAINTY":
                        pct_match = re.search(r"(\d+\.?\d*%)", line1)
                        if pct_match:
                            before = line1[: pct_match.start()]
                            pct_str = pct_match.group(1)
                            after = line1[pct_match.end() :]
                            try:
                                pct_val = float(pct_str.rstrip("%"))
                                pct_color = _tc_dyn(_nb_certainty_color(pct_val))
                            except Exception:
                                logger.exception(
                                    "Failed to parse percentage from COMBINED_CERTAINTY message: %r",
                                    pct_str,
                                )
                                pct_color = _PORTAL_WARN_COLOR
                            bx = text_start_x
                            draw_text(painter, bx, text_y1, before, portal_warn_font, _PORTAL_WARN_COLOR)
                            bx += measure_text_width(before, portal_warn_font)
                            draw_text(painter, bx, text_y1, pct_str, portal_warn_font, pct_color)
                            bx += measure_text_width(pct_str, portal_warn_font)
                            draw_text(painter, bx, text_y1, after, portal_warn_font, _PORTAL_WARN_COLOR)
                        else:
                            draw_text(painter, text_start_x, text_y1, line1, portal_warn_font, _PORTAL_WARN_COLOR)
                        draw_text(painter, text_start_x, text_y2, line2, portal_warn_font, _PORTAL_WARN_COLOR)
                    else:
                        draw_text(painter, text_start_x, text_y1, line1, portal_warn_font, _PORTAL_WARN_COLOR)
                        draw_text(painter, text_start_x, text_y2, line2, portal_warn_font, _PORTAL_WARN_COLOR)
                else:
                    ty = row_y + (this_msg_h - text_h) // 2
                    draw_text(painter, text_start_x, ty, line1, portal_warn_font, _PORTAL_WARN_COLOR)
            else:
                ty = row_y + (this_msg_h - text_h) // 2
                draw_text(painter, text_start_x, ty, text, portal_warn_font, _PORTAL_WARN_COLOR)

            current_info_y += this_msg_h
            if msg_idx < len(_display_info_messages) - 1:
                fill_rectangle(painter, 0, current_info_y, img_w - 1, current_info_y + ROW_SEP - 1, _NB_ROW_SEP)
                current_info_y += ROW_SEP

    if blind_result is not None:
        eval_color = _tc_dyn(blind_evaluation_color(evaluation))
        txt_x = CELL_PAD_MAIN
        txt_y = new_header_bottom + (body_h - measure_text_height(body_font)) // 2
        lsep = body_h
        draw_text(painter, txt_x, txt_y, _prefix, body_font, _NB_TEXT)
        draw_text(painter, txt_x + measure_text_width(_prefix), txt_y, _eval_text, body_font, eval_color)
        draw_text(painter, txt_x, txt_y + lsep, _l2p, body_font, eval_color)
        draw_text(painter, txt_x + measure_text_width(_l2p), txt_y + lsep, _l2s, body_font, _NB_TEXT)
        draw_text(painter, txt_x, txt_y + lsep * 2, _l3, body_font, _NB_TEXT)
    elif failed:
        txt_x = CELL_PAD_MAIN
        for li, line in enumerate(_fl):
            if not line:
                continue
            ty = new_header_bottom + li * body_h + (body_h - measure_text_height(body_font)) // 2
            draw_text(painter, txt_x, ty, line, body_font, _NB_TEXT)

    if num_throw_rows:
        throw_base_y = main_h
        fill_rectangle(painter, 0, throw_base_y, img_w - 1, throw_base_y + HDR_SEP - 1, _NB_HDR_SEP)
        th_title_y = throw_base_y + HDR_SEP
        fill_rectangle(painter, 0, th_title_y, img_w - 1, th_title_y + hdr_h - 1, _NB_HEADER_BG)
        title_ty = th_title_y + (hdr_h - measure_text_height(hdr_font)) // 2
        draw_text(painter, CELL_PAD_MAIN + 6, title_ty, "Ender eye throws", hdr_font, _NB_TEXT)

        th_hdr_y = th_title_y + hdr_h
        fill_rectangle(painter, 0, th_hdr_y, img_w - 1, th_hdr_y + small_h - 1, _NB_HEADER_BG)
        x = 0
        for i, thdr in enumerate(throw_headers):
            cw = throw_col_widths[i]
            lw = measure_text_width(thdr, small_font)
            ty = th_hdr_y + (small_h - measure_text_height(small_font)) // 2
            draw_text(painter, x + (cw - lw) // 2, ty, thdr, small_font, _NB_TEXT)
            x += cw

        sep2_y = th_hdr_y + small_h
        fill_rectangle(painter, 0, sep2_y, img_w - 1, sep2_y + HDR_SEP - 1, _NB_HDR_SEP)

        for ti in range(num_throw_rows):
            ty = sep2_y + HDR_SEP + ti * (throw_body_h + ROW_SEP)
            if ti < num_throw_rows - 1:
                fill_rectangle(painter, 0, ty + throw_body_h, img_w - 1, ty + throw_body_h + ROW_SEP - 1, _NB_ROW_SEP)
            x = 0
            if ti < len(throw_rows_data):
                trow = throw_rows_data[ti]
                for i, cell in enumerate(trow):
                    cw = throw_col_widths[i]
                    ty2 = ty + (throw_body_h - measure_text_height(small_font)) // 2
                    if failed and i == 3:
                        x += cw
                        continue
                    if i == 2 and show_adj_count and ti in adj_count_by_throw:
                        aw_str, cnt_str, cnt_raw = adj_count_by_throw[ti]
                        if cnt_str:
                            adj_col = _tc_dyn(
                                ADJ_COUNT_POSITIVE
                                if (cnt_raw is None or cnt_raw >= 0)
                                else ADJ_COUNT_NEGATIVE
                            )
                            full_w = measure_text_width(aw_str, small_font) + measure_text_width(cnt_str, small_font)
                            bx = x + (cw - full_w) // 2
                            draw_text(painter, bx, ty2, aw_str, small_font, _NB_THROW_HDR_FG)
                            draw_text(painter, bx + measure_text_width(aw_str, small_font), ty2, cnt_str, small_font, adj_col)
                        else:
                            cw_ = measure_text_width(aw_str, small_font)
                            draw_text(painter, x + (cw - cw_) // 2, ty2, aw_str, small_font, _NB_THROW_HDR_FG)
                    else:
                        cw_ = measure_text_width(cell, small_font)
                        draw_text(painter, x + (cw - cw_) // 2, ty2, cell, small_font, _NB_THROW_HDR_FG)
                    x += cw
            else:
                for cw in throw_col_widths:
                    x += cw
    painter.end()
    return img


def certainty_color_for_turn(abs_turn):
    return gradient_color(abs_turn)


def _render_nb_failed_standalone(font_size, bg_opacity=1.0, text_opacity=1.0):
    font = _load_nb_font(font_size)
    body_h = text_height(font) + 10
    lines = [
        "Could not determine the stronghold chunk.",
        "You probably misread one of the eyes.",
    ]
    max_w = max(text_width(line, font) for line in lines)
    PAD = 20
    img_w = max_w + PAD * 2
    img_h = body_h * len(lines) + PAD
    img = new_canvas(img_w, img_h, with_alpha(NB_ROW_BG[:3], bg_opacity))
    painter = QPainter(img)
    t_col = with_alpha(NB_TEXT, text_opacity)
    for i, line in enumerate(lines):
        y = PAD // 2 + i * body_h
        lw = text_width(line, font)
        draw_text(painter, (img_w - lw) // 2, y + (body_h - text_height(font)) // 2, line, font, t_col)
    painter.end()
    return img


# --------------------- END Generate default pinned image overlay -----------


# --------------------- Generate custom pinned image overlay --------------------------


def generate_custom_pinned_image():
    customizations = get_customizations()

    bg_hex = customizations.get("background_color", "#1E1E1E")
    text_hex = customizations.get("text_color", "#000000")
    bg_rgb = hex_to_rgb(bg_hex, fallback=(255, 255, 255))
    text_rgb = hex_to_rgb(text_hex, fallback=(0, 0, 0))
    bg_opacity = max(0.0, min(1.0, float(customizations.get("background_opacity", 1.0))))
    text_opacity = max(0.0, min(1.0, float(customizations.get("text_opacity", 1.0))))
    text_outline_enabled = bool(customizations.get("text_outline_enabled", False))
    text_outline_color_hex = customizations.get("text_outline_color", "#000000")
    text_outline_rgb = hex_to_rgb(text_outline_color_hex, (0, 0, 0))
    text_outline_width = int(customizations.get("text_outline_width", 2))
    text_outline_width = max(1, min(10, text_outline_width))

    bg_rgba = with_alpha(bg_rgb, bg_opacity)
    text_rgba = with_alpha(text_rgb, text_opacity)
    outline_rgba = with_alpha(text_outline_rgb, text_opacity)

    def _draw_text_with_optional_outline(x, y, text, fnt, fill):
        if text_outline_enabled:
            draw_text_outlined(painter, x, y, text, fnt, fill, outline_rgba, text_outline_width)
        else:
            draw_text(painter, x, y, text, fnt, fill)

    show_boat_icon = customizations.get("show_boat_icon", False)
    show_coords_by_dim = customizations.get("show_coords_based_on_dimension", True)
    show_error_message = customizations.get("show_error_message", False)
    show_blind_info = customizations.get("show_blind_info", True)
    font_size = customizations.get("font_size", 18)
    show_adj_count = customizations.get("show_angle_adjustment_count", False)
    ow_coords_format = customizations.get("overworld_coords_format", "four_four")
    neg_coords_enabled = customizations.get("negative_coords_color_enabled", False)
    neg_coords_hex = customizations.get("negative_coords_color", "#CC6E72")
    neg_coords_rgb = hex_to_rgb(neg_coords_hex, fallback=(204, 110, 114))
    portal_nether_enabled = customizations.get("portal_nether_color_enabled", True)
    portal_nether_hex = customizations.get("portal_nether_color", "#FFA500")
    portal_nether_rgb = hex_to_rgb(portal_nether_hex, fallback=(255, 165, 0))
    show_angle_error = customizations.get("show_angle_error", False)
    angle_display_mode = customizations.get("angle_display_mode", "angle_and_change")
    show_overlay_header = customizations.get("show_overlay_header", False)

    with status_lock:
        boat_resp = dict(status["boat_resp"])
        stronghold_resp = dict(status["stronghold_resp"])
        blind_resp = dict(status["blind_resp"])
        show_until = status.get("showUntil", 0)

    if not stronghold_resp:
        _schedule(clear_overlay_image)
        return

    boat_state = boat_resp.get("boatState")
    boat_angle = boat_resp.get("boatAngle", None)
    result_type = stronghold_resp.get("resultType")
    blind_enabled = blind_resp.get("isBlindModeEnabled", False)
    blind_result = blind_resp.get("blindResult", {})

    now = time.time()

    has_valid_blind_result = blind_result and blind_result.get("evaluation") is not None

    with status_lock:
        blind_was_showing = status.get("blindCurrentlyShowing", False)

    should_show_blind = (
        show_blind_info
        and blind_enabled
        and has_valid_blind_result
        and result_type in ("NONE", "BLIND")
    )

    if blind_was_showing:
        should_hide = False

        if not show_blind_info or not blind_enabled or not has_valid_blind_result or result_type not in ("NONE", "BLIND"):
            should_hide = True

        if should_hide:
            logger.debug("[Render] Hiding blind info")
            with status_lock:
                status["blindCurrentlyShowing"] = False

    if should_show_blind:
        with status_lock:
            blind_show_until = status["blindShowUntil"]

        if now < blind_show_until:
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

            font_name = customizations.get("font_name", "")
            font = _load_nb_font(font_size, font_name)

            w_line1_pre = text_width(line1_pre, font)
            w_line1_eval = text_width(line1_eval, font)
            w_line2_pct = text_width(highroll_pct_text, font)
            w_line2_post = text_width(line2_post, font)
            w_line3 = text_width(line3, font)
            max_w = max(w_line1_pre + w_line1_eval, w_line2_pct + w_line2_post, w_line3)

            line_h = text_height(font) + 6
            height = line_h * 3 + 20
            pad = 10

            img = new_canvas(int(max_w + 2 * pad), height, bg_rgba)
            painter = QPainter(img)
            eval_color_rgba = with_alpha(blind_evaluation_color(evaluation), text_opacity)

            x, y = pad, 10
            _draw_text_with_optional_outline(x, y, line1_pre, font, text_rgba)
            _draw_text_with_optional_outline(x + w_line1_pre, y, line1_eval, font, eval_color_rgba)
            x = pad
            y += line_h
            _draw_text_with_optional_outline(x, y, highroll_pct_text, font, eval_color_rgba)
            _draw_text_with_optional_outline(x + w_line2_pct, y, line2_post, font, text_rgba)
            y += line_h
            _draw_text_with_optional_outline(pad, y, line3, font, text_rgba)
            painter.end()

            _schedule(lambda im=img: apply_overlay_from_qimage(im))
            _write_image_to_path(img, IMAGE_PATH)
            logger.debug(
                "[Render] Saved blind overlay image (Expires: %.2f)",
                blind_show_until,
            )

            with status_lock:
                status["blindCurrentlyShowing"] = True
            return

    if result_type == "TRIANGULATION":
        with status_lock:
            if status["blindShowUntil"] > 0:
                logger.debug("[System] Result type is TRIANGULATION (Clearing blind timer)")
                status["blindShowUntil"] = 0

    if show_error_message and result_type == "FAILED":
        text = "Could not determine the stronghold chunk."
        font_name = customizations.get("font_name", "")
        font = _load_nb_font(font_size, font_name)

        text_w = text_width(text, font)
        text_h = text_height(font)
        pad = 10
        img = new_canvas(text_w + 2 * pad, text_h + 2 * pad, bg_rgba)
        painter = QPainter(img)
        _draw_text_with_optional_outline(pad, pad, text, font, text_rgba)
        painter.end()
        _schedule(lambda im=img: apply_overlay_from_qimage(im))
        _write_image_to_path(img, IMAGE_PATH)
        return

    with status_lock:
        last_shown = status["lastShown"]
        show_until = status["showUntil"]

    if show_boat_icon and result_type == "NONE":
        if boat_state == "VALID" and boat_angle == 0:
            if not bool(customizations.get("auto_hide_window", True)):
                _render_and_apply_blank_custom_overlay(customizations)
            else:
                _schedule(clear_overlay_image)
            return

        if boat_state == last_shown and now < show_until:
            icon_file = (
                "boat_green_icon.png" if boat_state == "VALID" else "boat_red_icon.png"
            )
            icon_path = os.path.join(os.path.dirname(__file__), "assets", icon_file)
            try:
                icon = load_icon(icon_path, 64)
                if icon is not None:
                    icon = apply_opacity(icon, text_opacity)
            except Exception:
                logger.exception("[Render] Failed to load icon")
            else:
                if icon is not None:
                    _schedule(lambda im=icon: apply_overlay_from_qimage(im, 64, 64))
                    _write_image_to_path(icon, IMAGE_PATH)
                else:
                    logger.error("[Render] Failed to load boat icon: %s", icon_path)
        else:
            if not bool(customizations.get("auto_hide_window", True)):
                _render_and_apply_blank_custom_overlay(customizations)
            else:
                _schedule(clear_overlay_image)
        return

    preds = stronghold_resp.get("predictions", [])
    eye_throws = stronghold_resp.get("eyeThrows", [])
    player_pos = stronghold_resp.get("playerPosition", {})
    player_x = player_pos.get("xInOverworld")
    player_z = player_pos.get("zInOverworld")
    h_ang = player_pos.get("horizontalAngle")
    in_nether = player_pos.get("isInNether", False)

    shown_count = customizations.get("shown_measurements", 5)
    order = customizations.get("text_order", [])
    enabled = customizations.get("text_enabled", {})
    text_header = customizations.get("text_header", {})
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
        cert = pred.get("certainty")
        dist = pred.get("overworldDistance")
        if None in (cx, cz, cert, dist):
            continue

        parts = []
        for key in order:
            if not enabled.get(key, True):
                continue

            if key == "distance":
                d = dist / 8 if in_nether else dist
                parts.append(("distance", (str(int(d)), d)))

            elif key == "certainty_percentage":
                pct = round(cert * 100, 1)
                parts.append(("certainty", f"{pct}%"))

            elif key == "angle" and None not in (h_ang, player_x, player_z):
                sx = cx * 16 + 4
                sz = cz * 16 + 4
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
                tgt = (math.degrees(math.atan2(dz, dx)) + 270) % 360
                signed = ((tgt + 180) % 360) - 180
                turn = ((tgt - (h_ang % 360) + 180) % 360) - 180
                show_ang = angle_display_mode in ("angle_and_change", "angle_only")
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
                    ox, oz = cx * 16 + 8, cz * 16 + 8
                else:
                    ox, oz = cx * 16 + 4, cz * 16 + 4
                if show_coords_by_dim and in_nether:
                    ox, oz = round(ox / 8), round(oz / 8)
                parts.append(("coords", (ox, oz)))
            elif key == "nether_coords":
                nx, nz = cx * 16 + 4, cz * 16 + 4
                if not (show_coords_by_dim and not in_nether):
                    nx, nz = round(nx / 8), round(nz / 8)
                parts.append(("nether_coords_val", (nx, nz)))
        if parts:
            _flag = (
                _portal_link_flags[pred_idx]
                if pred_idx < len(_portal_link_flags)
                else False
            )
            lines.append((parts, _flag))

    adj_count_overlays = []
    angle_error_overlays = []
    if eye_throws:
        for throw_idx, throw in enumerate(eye_throws):
            if show_adj_count:
                angle_without = throw.get("angleWithoutCorrection", 0.0)
                increments = throw.get("correctionIncrements", 0) or 0

                if increments != 0:
                    sign = "+" if increments >= 0 else ""
                    adj_count_overlays.append(
                        (f"{angle_without:.2f}", f"{sign}{increments}", increments)
                    )
                else:
                    adj_count_overlays.append((f"{angle_without:.2f}", None, None))
            if show_angle_error:
                error_val = throw.get("error", None)
                if error_val is not None:
                    angle_error_overlays.append((f"{error_val:.4f}",))

    if not lines:
        if not bool(customizations.get("auto_hide_window", True)):
            _render_and_apply_blank_custom_overlay(customizations)
            return
        else:
            _schedule(clear_overlay_image)
            return

    font_name = customizations.get("font_name", "")
    font = _load_nb_font(font_size, font_name)

    line_h = text_height(font) + 6

    has_header = any(
        text_header.get(k, "Text") == "Text" for k in order if enabled.get(k, True)
    )
    header_h = line_h if has_header else 0

    n_bottom_rows = max(len(adj_count_overlays), len(angle_error_overlays))
    small_font_size = max(8, int(font_size * 0.90))
    small_font = _load_nb_font(small_font_size, font_name)

    small_line_h = text_height(small_font) + 4

    overlay_header_h_calc = (
        small_line_h if (show_overlay_header and n_bottom_rows > 0) else 0
    )
    bottom_extra_h = (
        (overlay_header_h_calc + (small_line_h - 2) * n_bottom_rows + 4)
        if n_bottom_rows > 0
        else 0
    )
    height = header_h + line_h * len(lines) + 10 + bottom_extra_h

    def _item_display_width(kind, val):
        if kind == "distance":
            txt = val[0] if isinstance(val, tuple) else str(val)
        elif kind in ("coords", "nether_coords_val"):
            cx_v, cz_v = val
            parts = ["(", str(cx_v), ", ", str(cz_v), ")"]
            total = sum(text_width(p, font) for p in parts)
            return total + 14, f"({cx_v}, {cz_v})"
        elif kind == "angle_change":
            arrow, num = val
            full_change = f"({arrow} {num})"
            return text_width(full_change, font) + 14, full_change
        else:
            txt = str(val)
        return text_width(txt, font) + 14, txt

    col_widths = []
    for parts, _plink in lines:
        for slot_idx, item in enumerate(parts):
            w, _ = _item_display_width(item[0], item[1])
            if slot_idx >= len(col_widths):
                col_widths.append(w)
            else:
                col_widths[slot_idx] = max(col_widths[slot_idx], w)

    required_w = 10 + sum(col_widths) + 10
    img = new_canvas(int(required_w + 10), height, bg_rgba)
    painter = QPainter(img)

    col_x = []
    cx_acc = 10
    for w in col_widths:
        col_x.append(cx_acc)
        cx_acc += w
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
            tw_val = text_width(hdr_txt, font)
            if key == "angle" and angle_display_mode in ("angle_and_change",):
                change_slot = slots[-1]
                if change_slot < len(col_x) and change_slot < len(col_widths):
                    hx = col_x[change_slot] + (col_widths[change_slot] - tw_val) // 2
                else:
                    hx = col_x[first_slot] + (col_widths[first_slot] - tw_val) // 2
            else:
                span_start = col_x[first_slot]
                span_end = col_x[last_slot] + col_widths[last_slot]
                hx = span_start + (span_end - span_start - tw_val) // 2
            _draw_text_with_optional_outline(hx, 5, hdr_txt, font, text_rgba)

    for row, (parts, _portal_link) in enumerate(lines):
        y = 5 + header_h + row * line_h
        for _item in parts:
            if _item[0] == "angle_change":
                try:
                    _last_turn_pct[0] = float(_item[1][1])
                except Exception:
                    logger.exception(
                        "Failed to parse angle_change value for turn percentage: %r",
                        _item[1],
                    )
                break

        for slot_idx, item in enumerate(parts):
            kind = item[0]
            val = item[1]
            col_left = col_x[slot_idx] if slot_idx < len(col_x) else 10
            col_w = col_widths[slot_idx] if slot_idx < len(col_widths) else 0

            def _cx(txt):
                tw_v = text_width(txt, font)
                return col_left + (col_w - tw_v) // 2

            if kind == "certainty":
                txt = val
                try:
                    pct = float(txt.rstrip("%"))
                    fill = with_alpha(certainty_color(pct), text_opacity)
                except Exception:
                    logger.exception(
                        "Failed to parse certainty percentage for color: %r", txt
                    )
                    fill = text_rgba
                _draw_text_with_optional_outline(_cx(txt), y, txt, font, fill)

            elif kind == "angle_change":
                arrow, num = val
                try:
                    _last_turn_pct[0] = float(num)
                except Exception:
                    logger.exception(
                        "Failed to parse angle_change num for gradient color: %r", num
                    )
                fill = with_alpha(gradient_color(_last_turn_pct[0]), text_opacity)
                full_change = f"({arrow} {num})"
                cw_ = text_width(full_change, font)
                _draw_text_with_optional_outline(col_left + (col_w - cw_) // 2, y, full_change, font, fill)

            elif kind == "distance":
                txt = val[0] if isinstance(val, tuple) else str(val)
                _draw_text_with_optional_outline(_cx(txt), y, txt, font, text_rgba)

            elif kind == "coords":
                cx_v, cz_v = val
                x_str = str(cx_v)
                z_str = str(cz_v)
                x_fill = (
                    with_alpha(neg_coords_rgb, text_opacity)
                    if neg_coords_enabled and cx_v < 0
                    else text_rgba
                )
                z_fill = (
                    with_alpha(neg_coords_rgb, text_opacity)
                    if neg_coords_enabled and cz_v < 0
                    else text_rgba
                )
                _coord_parts = [
                    ("(", text_rgba),
                    (x_str, x_fill),
                    (", ", text_rgba),
                    (z_str, z_fill),
                    (")", text_rgba),
                ]
                _coord_total_w = sum(text_width(p, font) for p, _ in _coord_parts)
                bx = col_left + (col_w - _coord_total_w) // 2
                for part_txt, part_fill in _coord_parts:
                    _draw_text_with_optional_outline(bx, y, part_txt, font, part_fill)
                    bx += text_width(part_txt, font)

            elif kind == "nether_coords_val":
                cx_v, cz_v = val
                x_str = str(cx_v)
                z_str = str(cz_v)
                _is_portal = portal_nether_enabled and _portal_link
                punct_fill = (
                    with_alpha(portal_nether_rgb, text_opacity)
                    if _is_portal
                    else text_rgba
                )
                x_fill = (
                    with_alpha(portal_nether_rgb, text_opacity)
                    if _is_portal
                    else (
                        with_alpha(neg_coords_rgb, text_opacity)
                        if neg_coords_enabled and cx_v < 0
                        else text_rgba
                    )
                )
                z_fill = (
                    with_alpha(portal_nether_rgb, text_opacity)
                    if _is_portal
                    else (
                        with_alpha(neg_coords_rgb, text_opacity)
                        if neg_coords_enabled and cz_v < 0
                        else text_rgba
                    )
                )
                _nether_parts = [
                    ("(", punct_fill),
                    (x_str, x_fill),
                    (", ", punct_fill),
                    (z_str, z_fill),
                    (")", punct_fill),
                ]
                _nether_total_w = sum(text_width(p, font) for p, _ in _nether_parts)
                bx = col_left + (col_w - _nether_total_w) // 2
                for part_txt, part_fill in _nether_parts:
                    _draw_text_with_optional_outline(bx, y, part_txt, font, part_fill)
                    bx += text_width(part_txt, font)

            else:
                txt = str(val)
                _draw_text_with_optional_outline(_cx(txt), y, txt, font, text_rgba)

    actual_left = actual_right = None
    for parts, _plink_last in lines[-1:]:
        for slot_idx, item in enumerate(parts):
            kind, val = item[0], item[1]
            if slot_idx >= len(col_x) or slot_idx >= len(col_widths):
                continue
            c_left = col_x[slot_idx]
            c_w = col_widths[slot_idx]
            if kind == "distance":
                txt = val[0] if isinstance(val, tuple) else str(val)
            elif kind in ("coords", "nether_coords_val"):
                cx_v, cz_v = val
                txt = f"({cx_v}, {cz_v})"
            elif kind == "angle_change":
                arrow, num = val
                arrow_w = text_width(arrow, font)
                total_w = arrow_w + 4 + text_width(num, font)
                cs = c_left + (c_w - total_w) // 2
                ce = cs + total_w
                actual_left = cs if actual_left is None else min(actual_left, cs)
                actual_right = ce if actual_right is None else max(actual_right, ce)
                continue
            else:
                txt = str(val)
            txt_w = text_width(txt, font)
            cs = c_left + (c_w - txt_w) // 2
            ce = cs + txt_w
            actual_left = cs if actual_left is None else min(actual_left, cs)
            actual_right = ce if actual_right is None else max(actual_right, ce)
    if actual_left is None:
        actual_left = 10
    if actual_right is None:
        actual_right = 10

    n_overlay_rows = max(len(adj_count_overlays), len(angle_error_overlays))
    if n_overlay_rows > 0:
        overlay_header_h = overlay_header_h_calc
        base_y = header_h + line_h * len(lines) + 10
        first_err_x = first_err_w = first_adj_x = first_adj_total_w = None

        for oi in range(n_overlay_rows):
            row_y = base_y + overlay_header_h + oi * (small_line_h - 2) - 2
            if oi < len(adj_count_overlays):
                angle_txt, count_txt, adj_raw = adj_count_overlays[oi]
                angle_w = text_width(angle_txt, small_font)
                count_w = (
                    text_width(count_txt, small_font)
                    if count_txt
                    else 0
                )
                total_w = angle_w + count_w
                adj_x = (
                    actual_right - total_w
                    if oi == 0
                    else first_adj_x + (first_adj_total_w - total_w) // 2
                )
                if oi == 0:
                    first_adj_x = adj_x
                    first_adj_total_w = total_w
                _draw_text_with_optional_outline(adj_x, row_y, angle_txt, small_font, text_rgba)
                if count_txt:
                    base_color = (
                        ADJ_COUNT_POSITIVE
                        if (adj_raw is None or adj_raw >= 0)
                        else ADJ_COUNT_NEGATIVE
                    )
                    adj_fill = with_alpha(base_color, text_opacity)
                    _draw_text_with_optional_outline(adj_x + angle_w, row_y, count_txt, small_font, adj_fill)
            if oi < len(angle_error_overlays):
                err_txt = angle_error_overlays[oi][0]
                err_txt_w = text_width(err_txt, small_font)
                err_x = (
                    actual_left
                    if oi == 0
                    else first_err_x + (first_err_w - err_txt_w) // 2
                )
                if oi == 0:
                    first_err_x = err_x
                    first_err_w = err_txt_w
                _draw_text_with_optional_outline(err_x, row_y, err_txt, small_font, text_rgba)

        if show_overlay_header and n_overlay_rows > 0:
            hdr_y = base_y - 2
            if (
                angle_error_overlays
                and first_err_x is not None
                and first_err_w is not None
            ):
                w_e = text_width("Error", small_font)
                _draw_text_with_optional_outline(first_err_x + (first_err_w - w_e) // 2, hdr_y, "Error", small_font, text_rgba)
            if (
                adj_count_overlays
                and first_adj_x is not None
                and first_adj_total_w is not None
            ):
                w_a = text_width("Angle", small_font)
                _draw_text_with_optional_outline(first_adj_x + (first_adj_total_w - w_a) // 2, hdr_y, "Angle", small_font, text_rgba)

    painter.end()

    _schedule(lambda im=img: apply_overlay_from_qimage(im))
    _write_image_to_path(img, IMAGE_PATH)


# --------------------- END Generate custom pinned image overlay ----------------------


_window_hiding_method = None


def get_window_hiding_method():
    global _window_hiding_method
    if _window_hiding_method is not None:
        return _window_hiding_method
    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            data = json.load(f)
        _window_hiding_method = data.get("hide_method", "withdraw")
    except FileNotFoundError:
        logger.debug("[Window] Customizations file not found, using default hide method")
        _window_hiding_method = "withdraw"
    except Exception:
        logger.exception("[Window] Failed to read window hiding method")
        _window_hiding_method = "withdraw"
    logger.debug("[Window] Hide method loaded from config: %s", _window_hiding_method)
    return _window_hiding_method


# ---------------------- Qt Scheduler ----------------------


class _Scheduler(QObject):
    _function_signal = Signal(object)

    def __init__(self):
        super().__init__()
        self._function_signal.connect(self._invoke, Qt.QueuedConnection)

    @staticmethod
    def _invoke(function):
        try:
            function()
        except Exception:
            logger.exception("[Scheduler] Exception in scheduled call")

    def schedule(self, function):
        self._function_signal.emit(function)


# ---------------------- Qt Overlay Window ----------------------


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()

        if CLICK_THROUGH:
            self.setWindowFlags(
                Qt.FramelessWindowHint
                | Qt.WindowStaysOnTopHint
                | Qt.Tool
                | Qt.X11BypassWindowManagerHint
                | Qt.WindowTransparentForInput
            )
        else:
            self.setWindowFlags(
                Qt.FramelessWindowHint
                | Qt.WindowStaysOnTopHint
                | Qt.Tool
                | Qt.X11BypassWindowManagerHint
            )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setContentsMargins(0, 0, 0, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._label = QLabel(self)
        self._label.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        self._drag_pos = None

    def mousePressEvent(self, event):
        if not LOCK_OVERLAY and event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if (
            not LOCK_OVERLAY
            and self._drag_pos is not None
            and event.buttons() & Qt.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if (
            not LOCK_OVERLAY
            and event.button() == Qt.LeftButton
            and self._drag_pos is not None
        ):
            self._drag_pos = None
            if self.width() > 1 and self.height() > 1:
                save_config()
                logger.debug(
                    f"[Window] Manual window repositioning finished (pos: {self.x()},{self.y()})"
                )
            event.accept()


# ---------------------- Helpers ----------------------




def show_window():
    if HEADLESS:
        return
    global _window_visible
    _window_visible = True
    method = get_window_hiding_method()
    logger.debug("[Window] Showing overlay window")
    try:
        if method == "withdraw":
            window.show()
            window.raise_()
        else:
            window.show()
    except Exception:
        logger.exception("[Window] Failed to show window")


def hide_window():
    if HEADLESS:
        return
    global _window_visible
    _window_visible = False
    method = get_window_hiding_method()
    pos = window.pos()
    logger.debug(
        "[Window] Hiding overlay window (Method: %s, Pos: %s, %s)",
        method,
        pos.x(),
        pos.y(),
    )
    try:
        if method == "withdraw":
            window.hide()
        elif method == "one_pixel":
            label.clear()
            window.resize(1, 1)
            window.move(0, 0)
        else:
            window.move(-10000, -10000)
    except Exception:
        logger.exception("[Window] Failed to hide window")


def place_window(width, height):
    if HEADLESS:
        return
    try:
        pos = load_config()
        if pos:
            sx, sy = pos
            window.setGeometry(int(sx), int(sy), int(width), int(height))
        else:
            cur_x = window.x()
            cur_y = window.y()
            if cur_x <= -9000 or cur_y <= -9000:
                cur_x, cur_y = 0, 0
            window.setGeometry(cur_x, cur_y, int(width), int(height))
    except Exception:
        logger.exception("Failed to set window geometry, falling back to resize")
        try:
            window.resize(int(width), int(height))
        except Exception:
            logger.exception("Fallback window resize failed")


def _render_and_apply_blank_custom_overlay(customizations):
    bg_hex = customizations.get("background_color", "#1E1E1E")
    bg_rgb = hex_to_rgb(bg_hex, (255, 255, 255))
    bg_opacity = max(0.0, min(1.0, float(customizations.get("background_opacity", 1.0))))

    blank_img = new_canvas(500, 100, with_alpha(bg_rgb, bg_opacity))
    _schedule(lambda im=blank_img: apply_overlay_from_qimage(im))
    _write_image_to_path(blank_img, IMAGE_PATH)


def apply_overlay_from_qimage(qimg, width=None, height=None):
    if HEADLESS:
        w = int(width) if width is not None else qimg.width()
        h = int(height) if height is not None else qimg.height()
        logger.debug("[System] Headless mode: overlay written (%sx%spx)", w, h)
        return
    try:
        qpixmap = QPixmap.fromImage(qimg)
        label.setPixmap(qpixmap)

        w = int(width) if width is not None else qimg.width()
        h = int(height) if height is not None else qimg.height()

        global _last_overlay_w, _last_overlay_h
        if w > 100:
            _last_overlay_w, _last_overlay_h = w, h

        place_window(w, h)
        show_window()

        logger.debug(
            "[Window] Applying overlay (%dx%dpx) at (%d,%d)",
            w,
            h,
            window.x(),
            window.y(),
        )
    except Exception:
        logger.exception("[Window] Failed to apply overlay")


def check_ninjabrainbot_version():
    sent_print_error = False
    required = [1, 5, 2]

    while True:
        try:
            resp = requests.get("http://localhost:52533/api/v1/version", timeout=3)
            resp.raise_for_status()
            data = resp.json()
            version_str = data.get("version", "")
            parts = [int(x) for x in version_str.split(".")]
            if parts < required:
                print(
                    f"NBTrackr requires Ninjabrain Bot version 1.5.2+ to work properly.\n"
                    f"You are running version {version_str}.\n"
                    f"Please update to the latest version:\n"
                    f"https://github.com/Ninjabrain1/Ninjabrain-Bot/releases/latest"
                )
                sys.exit(1)
            return
        except SystemExit:
            raise
        except requests.exceptions.RequestException:
            if not sent_print_error:
                logger.debug("Could not connect to Ninjabrain Bot while checking version", exc_info=True)
                print("ERROR: Cannot connect to Ninjabrain Bot. Make sure it is running and API is enabled in Ninjabrain Bot > Settings > Advanced.")
                sent_print_error = True
            else:
                logger.debug("Still could not connect to Ninjabrain Bot to verify version")
            time.sleep(1)
        except Exception:
            if not sent_print_error:
                logger.exception("Unexpected error while checking Ninjabrain Bot version")
                print("ERROR: Cannot connect to Ninjabrain Bot. Make sure it is running and API is enabled in Ninjabrain Bot > Settings > Advanced.")
                sent_print_error = True
            else:
                logger.debug("Still could not connect to Ninjabrain Bot to verify version")
            time.sleep(1)

# ---------------------- Helpers - END ----------------------

# --------------------- Config load/save --------------------------


def load_config():
    try:
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            pos = config.get("position")
            if pos and isinstance(pos, dict):
                x = pos.get("x")
                y = pos.get("y")
                if isinstance(x, int) and isinstance(y, int):
                    logger.debug("[Config] Loaded window position: x=%d, y=%d", x, y)
                    return x, y
    except Exception:
        logger.exception("[Config] Failed to load settings.json")
    return None


def save_config():
    try:
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
        x = window.x()
        y = window.y()
        config = {"position": {"x": x, "y": y}}
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        logger.debug("[Config] Saved window position: x=%d, y=%d", x, y)
    except Exception:
        logger.exception("[Config] Failed to save settings.json")

# --------------------- Startup --------------------------

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    print(f"NBTrackr version: {APP_VERSION}\n")

    os.environ["QT_QPA_PLATFORM"] = "xcb"
    logger.debug(
        "[System] QT_QPA_PLATFORM set to: %s",
        os.environ.get("QT_QPA_PLATFORM"),
    )

    check_ninjabrainbot_version()

    latest = check_for_update(APP_VERSION)
    if latest:
        print("=== New Release Available! ===")
        print(f"Version: {latest}")
        print("You should update to the latest version!")
        print("1) Continue with the current version")
        print("2) Automatically update to the latest version")
        choice = input("Enter choice [1/2]: ").strip()
        print()
        if choice == "2":
            check_and_update(APP_VERSION, os.path.dirname(os.path.abspath(__file__)))
        else:
            print("Skipping update. Continuing with current version", APP_VERSION, "\n")

# --------------------- Qt Application & Overlay Window --------------------------


IMAGE_PATH = "/tmp/imgpin-overlay.png"

GREEN_IMG = os.path.join(os.path.dirname(__file__), "assets/boat_green.png")
RED_IMG = os.path.join(os.path.dirname(__file__), "assets/boat_red.png")

if HEADLESS:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication(sys.argv)
    window = None
    label = None
    _scheduler = None
else:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = OverlayWindow()

    saved_pos = load_config()
    if saved_pos:
        sx, sy = saved_pos
        try:
            window.move(sx, sy)

            desktop_rect = _get_virtual_desktop_geometry(app)
            logger.debug("[Window] Desktop rect: %s", desktop_rect)
            logger.debug("[Window] Window rect: %s", window.geometry())

            if not desktop_rect.intersects(window.geometry()):
                print(f"Window at ({sx}, {sy}) is off-screen. Resetting to (0, 0).")
                window.move(0, 0)
                save_config()

        except Exception:
            logger.exception("Failed to restore saved window position (%s, %s)", sx, sy)

    else:
        logger.debug("[Window] No saved position found (first launch), placing window at (0, 0)")
        window.move(0, 0)
        save_config()

    label = window._label

_scheduler = _Scheduler() if not HEADLESS else None


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
    "info_resp": {},
}

USE_CUSTOM_PINNED_IMAGE = bool(get_customizations().get("use_custom_pinned_image", False))

_nb_subscriber_connected = threading.Event()
_nb_subscriber_stop_functions = []


def _sse_try_ping():
    try:
        resp = requests.get("http://localhost:52533/api/v1/ping", timeout=0.5)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        logger.debug("Cannot connect to Ninjabrain Bot. Make sure it is running and API is enabled in Ninjabrain Bot > Settings > Advanced.")
        return False

    except Exception:
        logger.exception("Unexpected error while pinging Ninjabrain Bot.")
        return False


def _sse_subscribe(endpoint, on_event, on_disconnect):
    stop_flag = {"stop": False}
    resp_holder = {"resp": None}

    def _run():
        try:
            resp = requests.get(f"http://localhost:52533/api/v1/{endpoint}/events",stream=True,headers={"Accept": "text/event-stream"},)
            resp_holder["resp"] = resp
            resp.raise_for_status()
            client = sseclient.SSEClient(resp)
            for event in client.events():
                if stop_flag["stop"]:
                    break
                if not event.data:
                    continue
                try:
                    data = json.loads(event.data)
                except Exception:
                    logger.exception("[SSE] Failed to parse %s event", endpoint)
                    continue
                try:
                    on_event(data)
                except Exception:
                    logger.exception("[SSE] Event handler failed on %s", endpoint)
        except requests.exceptions.RequestException:
            if not stop_flag["stop"]:
                logger.debug("[SSE] Connection to %s lost", endpoint, exc_info=True)
        except Exception:
            if not stop_flag["stop"]:
                logger.exception("[SSE] Unexpected error on %s", endpoint)
        finally:
            if not stop_flag["stop"]:
                on_disconnect()

    sse_thread = threading.Thread(target=_run, daemon=True, name=f"sse-{endpoint}")
    sse_thread.start()

    def stop():
        stop_flag["stop"] = True
        resp = resp_holder["resp"]
        if resp is not None:
            try:
                resp.close()
            except Exception:
                logger.exception("Failed to close SSE response for %s", endpoint)

    return stop


def _reset_status_disconnected():
    with status_lock:
        status.update(
            {
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
                "info_resp": {},
            }
        )


_disconnect_lock = threading.Lock()

def _handle_nb_disconnect():
    with _disconnect_lock:
        if not _nb_subscriber_connected.is_set():
            return

        _nb_subscriber_connected.clear()

    print("Lost connection to Ninjabrain Bot.")
    logger.debug("[Connection] Connection lost")

    for stop_function in _nb_subscriber_stop_functions:
        try:
            stop_function()
        except Exception:
            logger.exception("Failed to stop an SSE subscriber during disconnect")

    _nb_subscriber_stop_functions.clear()

    _reset_status_disconnected()
    _schedule(clear_overlay_image)


_render_requested = threading.Event()
_render_lock = threading.Lock()

def _render_worker():
    while True:
        _render_requested.wait()
        time.sleep(0.005)
        _render_requested.clear()
        with _render_lock:
            if USE_CUSTOM_PINNED_IMAGE:
                generate_custom_pinned_image()
            else:
                generate_default_pinned_image()


def _trigger_render():
    _render_requested.set()


def _update_boat_visibility(boat_state, boat_angle, result_type, player_angle, customizations, boat_state_changed):
    prev_state = status["lastShown"]
    prev_angle = status["lastAngle"]
    now = time.time()
    expired = now >= status["showUntil"]

    show_boat_icon_setting = bool(customizations.get("show_boat_icon", True))
    boat_info_hide_after_enabled_setting = bool(customizations.get("boat_info_hide_after_enabled", True))
    boat_info_hide_after_setting = float(customizations.get("boat_info_hide_after", 10))
    boat_hide_duration = (
        boat_info_hide_after_setting
        if boat_info_hide_after_enabled_setting
        else float("inf")
    )

    if result_type not in ("NONE", "BLIND") or boat_state not in ("VALID", "ERROR"):
        status["lastShown"] = None
        status["showUntil"] = 0
        status["lastAngle"] = None
        return

    if not show_boat_icon_setting:
        status["lastShown"] = None
        status["showUntil"] = 0
        status["lastAngle"] = None
        return

    if boat_state == "VALID":
        if boat_angle == 0:
            status["lastShown"] = None
            status["showUntil"] = 0
            status["lastAngle"] = None
        elif boat_state_changed and boat_state != prev_state:
            status["lastShown"] = boat_state
            status["showUntil"] = now + boat_hide_duration
            status["lastAngle"] = None
        elif expired:
            status["showUntil"] = 0
    elif boat_state == "ERROR":
        if boat_state_changed and boat_state != prev_state:
            status["lastShown"] = boat_state
            status["showUntil"] = now + boat_hide_duration
            status["lastAngle"] = player_angle
        elif expired:
            if player_angle != prev_angle:
                status["lastShown"] = boat_state
                status["showUntil"] = now + boat_hide_duration
                status["lastAngle"] = player_angle
            else:
                status["showUntil"] = 0

def _on_boat_event(boat_resp):
    with status_lock:
        customizations = get_customizations()
        boat_state = boat_resp.get("boatState")
        boat_angle = boat_resp.get("boatAngle", None)
        result_type = status["resultType"]
        player_angle = status.get("stronghold_resp", {}).get("playerPosition", {}).get("horizontalAngle")

        status["boatState"] = boat_state
        status["boatAngle"] = boat_angle
        status["boat_resp"] = boat_resp

        _update_boat_visibility(
            boat_state, boat_angle, result_type, player_angle, customizations,
            boat_state_changed=True,
        )

    _trigger_render()


def _on_stronghold_event(stronghold_resp):
    with status_lock:
        customizations = get_customizations()
        result_type = stronghold_resp.get("resultType")
        player_angle = stronghold_resp.get("playerPosition", {}).get("horizontalAngle")
        is_in_nether = stronghold_resp.get("playerPosition", {}).get("isInNether", False)
        status["resultType"] = result_type
        status["isInNether"] = is_in_nether
        status["stronghold_resp"] = stronghold_resp

        if not status.get("blindModeEnabled") or result_type == "TRIANGULATION":
            if status["blindShowUntil"] > 0:
                logger.debug("Clearing blind timer")
            status["blindShowUntil"] = 0

        boat_state = status["boatState"]
        boat_angle = status["boatAngle"]
        _update_boat_visibility(
            boat_state, boat_angle, result_type, player_angle, customizations,
            boat_state_changed=False,
        )

    _trigger_render()


def _on_blind_event(blind_resp):
    with status_lock:
        customizations = get_customizations()
        now = time.time()

        blind_enabled = blind_resp.get("isBlindModeEnabled", False)
        blind_result = blind_resp.get("blindResult", {})

        prev_blind_result = status["blindResult"]
        prev_blind_enabled = status["blindModeEnabled"]

        status["blindModeEnabled"] = blind_enabled
        status["blind_resp"] = blind_resp

        has_valid_result = blind_result and blind_result.get("evaluation") is not None
        prev_had_valid_result = prev_blind_result and prev_blind_result.get("evaluation") is not None

        blind_changed = False
        if has_valid_result and prev_had_valid_result:
            if (
                blind_result.get("evaluation") != prev_blind_result.get("evaluation")
                or blind_result.get("xInNether") != prev_blind_result.get("xInNether")
                or blind_result.get("zInNether") != prev_blind_result.get("zInNether")
            ):
                blind_changed = True
        elif has_valid_result and not prev_had_valid_result:
            blind_changed = True
        elif not has_valid_result and prev_had_valid_result:
            logger.debug("Blind result cleared")
            status["blindShowUntil"] = 0

        status["blindResult"] = blind_result if has_valid_result else None

        show_blind_info_setting = bool(customizations.get("show_blind_info", True))

        if blind_changed or (blind_enabled and not prev_blind_enabled and blind_result):
            if not show_blind_info_setting:
                status["blindShowUntil"] = 0
            else:
                _hide_enabled = customizations.get("blind_info_hide_after_enabled", False)
                _hide_after = customizations.get("blind_info_hide_after", 20)
                status["blindShowUntil"] = (
                    (now + _hide_after) if _hide_enabled else float("inf")
                )

        if not blind_enabled or status["resultType"] == "TRIANGULATION":
            if status["blindShowUntil"] > 0:
                logger.debug("Clearing blind timer")
            status["blindShowUntil"] = 0

    _trigger_render()


def _on_info_messages_event(info_resp):
    with status_lock:
        status["info_resp"] = info_resp
    _trigger_render()


def nb_connection_thread():
    logger.debug("[System] SSE connection started")
    logged_fail = False

    while True:
        if _nb_subscriber_connected.is_set():
            time.sleep(2)
            continue

        if _sse_try_ping():
            print("Connected to Ninjabrain Bot.")
            logger.debug("[Connection] Successfully connected to Ninjabrain Bot API")
            _nb_subscriber_connected.set()
            logged_fail = False

            stop_functions = [
                _sse_subscribe("boat", _on_boat_event, _handle_nb_disconnect),
                _sse_subscribe("stronghold", _on_stronghold_event, _handle_nb_disconnect),
                _sse_subscribe("blind", _on_blind_event, _handle_nb_disconnect),
                _sse_subscribe("information-messages", _on_info_messages_event, _handle_nb_disconnect),
            ]
            _nb_subscriber_stop_functions.clear()
            _nb_subscriber_stop_functions.extend(stop_functions)

        else:
            if not logged_fail:
                print("ERROR: Cannot connect to Ninjabrain Bot. Make sure it is running and API is enabled in Ninjabrain Bot > Settings > Advanced.")
                logged_fail = True

        time.sleep(2)


def blind_timer_monitor_thread():
    logger.debug("[System] Timer monitor thread started")
    while True:
        with status_lock:
            blind_show_until = status["blindShowUntil"]
            blind_currently_showing = status.get("blindCurrentlyShowing", False)

        if blind_currently_showing and blind_show_until > 0:
            now = time.time()
            time_remaining = blind_show_until - now

            if time_remaining <= 0:
                logger.debug("[Timer Monitor] Blind timer expired, hiding")
                with status_lock:
                    status["blindCurrentlyShowing"] = False
                    status["blindShowUntil"] = -1
                try:
                    _schedule(hide_window)
                except Exception:
                    logger.exception("Failed to schedule hide_window from blind timer monitor")
                time.sleep(1)
            else:
                time.sleep(min(time_remaining, 1.0))
        else:
            time.sleep(1)


def boat_timer_monitor_thread():
    logger.debug("[System] Boat timer monitor thread started")
    while True:
        with status_lock:
            show_until = status["showUntil"]
            last_shown = status["lastShown"]

        if last_shown is not None and show_until not in (0, float("inf")):
            now = time.time()
            time_remaining = show_until - now

            if time_remaining <= 0:
                logger.debug("[Timer Monitor] Boat icon timer expired, hiding")
                with status_lock:
                    status["lastShown"] = None
                    status["showUntil"] = 0
                _trigger_render()
                time.sleep(1)
            else:
                time.sleep(min(time_remaining, 1.0))
        else:
            time.sleep(1)

threading.Thread(target=nb_connection_thread, daemon=True).start()
threading.Thread(target=blind_timer_monitor_thread, daemon=True).start()
threading.Thread(target=boat_timer_monitor_thread, daemon=True).start()
threading.Thread(target=_render_worker, daemon=True).start()

if HEADLESS:
    print("Running in headless mode. The overlay is always written to", IMAGE_PATH)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
else:
    sys.exit(app.exec())
