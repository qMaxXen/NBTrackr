import tkinter as tk
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

DEBUG_MODE = True  # Set to True to enable debug prints

# Program Version
APP_VERSION = "v2.1.3"

CONFIG_DIR = os.path.expanduser("~/.config/NBTrackr")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

CUSTOMIZATIONS_FILE = os.path.join(CONFIG_DIR, "customizations.json")

position_set = False

# --------------------- Cache --------------------------

_last_custom = None
_last_boat = None
_last_stronghold = None

_font = None
_font_name = None
_font_size = 18

def _load_font(name: str):
    """Load truetype font once; fallback to DejaVu or default."""
    global _font, _font_name
    if name == _font_name and _font:
        return _font
    for fn in (name, "DejaVuSans-Bold.ttf"):
        try:
            _font = ImageFont.truetype(fn, _font_size)
            _font_name = name
            return _font
        except Exception:
            continue
    _font = ImageFont.load_default()
    _font_name = None
    return _font


def gradient_color(angle: float):
    """
    angle: 0..180 degrees
    0° → green, 90° → yellow, 180° → red.
    """
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
    """
    pct: 0..100
    0 → red, 50 → yellow, 100 → green.
    """
    pct = max(0.0, min(100.0, pct))
    return gradient_color((100 - pct) * 1.8)


# --------------------- Cache End --------------------------


# --------------------- Generate custom pinned image --------------------------


def generate_custom_pinned_image():
    global _last_custom, _last_boat, _last_stronghold

    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            custom = json.load(f)
    except Exception as e:
        log("Failed to read customizations:", e)
        return

    show_boat_icon     = custom.get("show_boat_icon", False)
    show_coords_by_dim = custom.get("show_coords_based_on_dimension", True)
    show_error_message = custom.get("show_error_message", False)

    try:
        boat_resp       = requests.get("http://localhost:52533/api/v1/boat", timeout=1).json()
        stronghold_resp = requests.get("http://localhost:52533/api/v1/stronghold", timeout=1).json()
    except Exception:
        return

    boat_state  = boat_resp.get("boatState")
    result_type = stronghold_resp.get("resultType")


    if show_error_message and result_type == "FAILED":
        _last_custom, _last_boat, _last_stronghold = custom, boat_resp, stronghold_resp
        
        text = "Could not determine the stronghold chunk."
        font_name = custom.get("font_name", "")
        try:
            font = ImageFont.truetype(font_name, _font_size)
        except:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", _font_size) if _load_font else ImageFont.load_default()

        dummy = ImageDraw.Draw(Image.new("RGBA",(1,1)))
        bbox = dummy.textbbox((0,0), text, font=font)
        text_w, text_h = bbox[2]-bbox[0], bbox[3]-bbox[1]

        pad = 10
        img = Image.new("RGBA", (text_w+2*pad, text_h+2*pad), (255,255,255,255))
        draw = ImageDraw.Draw(img)
        draw.text((pad, pad), text, font=font, fill=(0,0,0))

        img.save(IMAGE_PATH)
        tk_img = ImageTk.PhotoImage(img)
        label.config(image=tk_img); label.image = tk_img
        root.geometry(f"{img.width}x{img.height}")
        root.deiconify()
        return

    with status_lock:
        last_shown = status["lastShown"]
        show_until = status["showUntil"]
    now = time.time()

    if show_boat_icon and result_type != "TRIANGULATION":
        if boat_state == last_shown and now < show_until:
            icon_file = "boat_green_icon.png" if boat_state == "VALID" else "boat_red_icon.png"
            icon_path = os.path.join(os.path.dirname(__file__), "assets", icon_file)
            try:
                icon = Image.open(icon_path).convert("RGBA")
                icon = icon.resize((64, 64), Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(icon)
                label.config(image=tk_img)
                label.image = tk_img
                root.geometry("64x64")
                root.deiconify()
            except Exception as e:
                log("Failed to load/process icon:", e)
        else:
            root.withdraw()
        return

    if (custom == _last_custom and
        boat_resp == _last_boat and
        stronghold_resp == _last_stronghold):
        return
    _last_custom, _last_boat, _last_stronghold = custom, boat_resp, stronghold_resp

    preds      = stronghold_resp.get("predictions", [])
    player_pos = stronghold_resp.get("playerPosition", {})
    player_x   = player_pos.get("xInOverworld")
    player_z   = player_pos.get("zInOverworld")
    h_ang      = player_pos.get("horizontalAngle")
    in_nether  = player_pos.get("isInNether", False)

    shown_count = custom.get("shown_measurements", 5)
    order       = custom.get("text_order", [])
    enabled     = custom.get("text_enabled", {})
    show_dir    = custom.get("show_angle_direction", True)

    lines = []
    for pred in preds[:shown_count]:
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
                parts.append(("text", str(round(d))))

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

                parts.append(("text", f"{signed:.2f}"))
                if show_dir:
                    arrow = "->" if turn > 0 else "<-"
                    parts.append(("text", arrow))
                    parts.append(("angle_adjust", f"{abs(turn):.1f}"))

            elif key == "overworld_coords":
                x, z = cx*16+4, cz*16+4
                if show_coords_by_dim and in_nether:
                    x, z = round(x/8), round(z/8)
                parts.append(("text", f"({x}, {z})"))

            elif key == "nether_coords":
                x, z = cx*16+4, cz*16+4
                if show_coords_by_dim and not in_nether:
                    x, z = cx*16+4, cz*16+4
                else:
                    x, z = round(x/8), round(z/8)
                parts.append(("text", f"({x}, {z})"))

        if parts:
            lines.append(parts)

    if not lines:
        root.withdraw()
        return

    font_name = custom.get("font_name", "")
    try:
        font = ImageFont.truetype(font_name, _font_size)
    except:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", _font_size)
        except:
            font = ImageFont.load_default()
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 6

    max_w  = 0
    height = line_h * len(lines) + 10
    img    = Image.new("RGBA", (800, height), (255,255,255,255))
    draw   = ImageDraw.Draw(img)

    for row, parts in enumerate(lines):
        x = 10
        y = 5 + row * line_h
        for kind, txt in parts:
            if kind == "certainty":
                pct  = float(txt.rstrip("%"))
                fill = certainty_color(pct)
            elif kind == "angle_adjust":
                pct  = float(txt)
                fill = gradient_color(pct)
            else:
                fill = (0,0,0)

            draw.text((x, y), txt, font=font, fill=fill)
            spacer = " " if txt in ("->","<-") else "   "
            w = draw.textbbox((0,0), txt+spacer, font=font)[2]
            x += w
        max_w = max(max_w, x)

    cropped = img.crop((0, 0, int(max_w+10), height))
    cropped.save(IMAGE_PATH)
    tk_img = ImageTk.PhotoImage(cropped)
    label.config(image=tk_img)
    label.image = tk_img
    root.geometry(f"{cropped.width}x{cropped.height}")
    root.deiconify()





# --------------------- END Generate custom pinned image ----------------------


def get_latest_github_release_version():
    url = "https://api.github.com/repos/qMaxXen/NBTrackr/releases/latest"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("tag_name")
    except Exception as e:
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
        print("https://github.com/qMaxXen/NBTrackr/releases\n")
        input("Press Enter to continue...")
        print("==============================")

# --------------------- NBTrackr Pin Image --------------------------


IMAGE_PATH_DEFAULT = "/tmp/nb-overlay.png"
IMAGE_PATH_CUSTOM  = "/tmp/imgpin-overlay.png"


GREEN_IMG = os.path.join(os.path.dirname(__file__), "assets/boat_green.png")
RED_IMG = os.path.join(os.path.dirname(__file__), "assets/boat_red.png")

root = tk.Tk()
root.overrideredirect(True)
root.wm_attributes("-topmost", True)

saved_pos = load_config()
if saved_pos:
    x, y = saved_pos
    root.geometry(f"+{x}+{y}")

label = tk.Label(root, borderwidth=0, highlightthickness=0)
label.pack()

image_queue = queue.Queue(maxsize=1)

status_lock = threading.Lock()
status = {
    "boatState": None,
    "resultType": None,
    "isInNether": False,
    "lastShown": None,
    "showUntil": 0,
    "lastAngle": None
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
            return any(pixel != 0 for pixel in alpha.getdata())
    except Exception:
        return False

def api_polling_thread():
    while True:
        try:
            boat_resp = requests.get("http://localhost:52533/api/v1/boat", timeout=0.5).json()
            stronghold_resp = requests.get("http://localhost:52533/api/v1/stronghold", timeout=0.5).json()

            boat_state = boat_resp.get("boatState")
            result_type = stronghold_resp.get("resultType")
            player_angle = stronghold_resp.get("playerPosition", {}).get("horizontalAngle")
            is_in_nether = stronghold_resp.get("playerPosition", {}).get("isInNether", False)

            now = time.time()
            with status_lock:
                prev_state = status["lastShown"]
                prev_angle = status["lastAngle"]
                expired = now >= status["showUntil"]

                status["boatState"] = boat_state
                status["resultType"] = result_type
                status["isInNether"] = is_in_nether

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

        time.sleep(0.3)

def custom_image_update_thread():
    while True:
        if USE_CUSTOM_PINNED_IMAGE:
            generate_custom_pinned_image()
        time.sleep(0.3) 


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
        root.withdraw()
    else:
        tk_img = ImageTk.PhotoImage(img)
        label.configure(image=tk_img)
        label.image = tk_img

        if not position_set and saved_pos:
            x, y = saved_pos
            root.geometry(f"{img.width}x{img.height}+{x}+{y}")
            position_set = True
        else:
            x = root.winfo_x()
            y = root.winfo_y()
            root.geometry(f"{img.width}x{img.height}+{x}+{y}")

        root.deiconify()

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

atexit.register(save_config)

root.after(100, update_image)

threading.Thread(target=api_polling_thread, daemon=True).start()

if USE_CUSTOM_PINNED_IMAGE:
    threading.Thread(target=custom_image_update_thread, daemon=True).start()
else:
    threading.Thread(target=image_loader_thread, daemon=True).start()

root.mainloop()
