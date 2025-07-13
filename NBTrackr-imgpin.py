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

# Program Version

DEBUG_MODE = True  # Set to True to enable debug prints
APP_VERSION = "v2.1.1"

CONFIG_DIR = os.path.expanduser("~/.config/NBTrackr")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

CUSTOMIZATIONS_FILE = os.path.join(CONFIG_DIR, "customizations.json")

position_set = False

# --------------------- Generate custom pinned image --------------------------


def generate_custom_pinned_image():
    try:
        with open(CUSTOMIZATIONS_FILE, "r") as f:
            custom = json.load(f)
    except Exception as e:
        log("Failed to read customizations:", e)
        return

    show_coords_by_dim = custom.get("show_coords_based_on_dimension", True)


    # 1) check boat state
    try:
        boat_state = requests.get(
            "http://localhost:52533/api/v1/boat", timeout=2
        ).json().get("boatState")
        if boat_state in ("ERROR", "MEASURING") or boat_state is None:
            root.withdraw()
            return
    except Exception as e:
        log("Failed to fetch boat data:", e)
        return

    # 2) fetch stronghold
    try:
        data = requests.get(
            "http://localhost:52533/api/v1/stronghold", timeout=2
        ).json()
    except Exception as e:
        log("Failed to fetch stronghold data:", e)
        return

    preds      = data.get("predictions", [])
    px         = data["playerPosition"].get("xInOverworld")
    pz         = data["playerPosition"].get("zInOverworld")
    h_ang      = data["playerPosition"].get("horizontalAngle")
    in_nether  = data["playerPosition"].get("isInNether", False)

    shown_count = custom.get("shown_measurements", 5)
    order       = custom.get("text_order", [])
    enabled     = custom.get("text_enabled", {})
    show_dir    = custom.get("show_angle_direction", True)

    def gradient_color(pct: float):
        """
        pct: 0..100
        0 → red, 50 → yellow, 100 → green
        """
        if pct <= 50:
            t = pct / 50.0
            return (255, int(255 * t), 0)
        else:
            t = (pct - 50) / 50.0
            return (
                int(255 * (1 - t)),
                int(255 * (1 - t) + 206 * t),
                int(41 * t),
            )

    # build lines of parts
    lines = []
    for pred in preds[:shown_count]:
        cx, cz = pred.get("chunkX"), pred.get("chunkZ")
        cert, dist = pred.get("certainty"), pred.get("overworldDistance")
        if None in (cx, cz, cert, dist):
            continue

        parts = []
        for key in order:
            if not enabled.get(key, True):
                continue

            if key == "distance":
                v = round(dist/8) if in_nether else round(dist)
                parts.append(("text", str(v)))

            elif key == "certainty_percentage":
                pct = round(cert * 100)
                parts.append(("certainty", f"{pct}%"))

            elif key == "angle" and None not in (h_ang, px, pz, cx, cz):
                sx, sz = cx*16+4, cz*16+4
                if in_nether:
                    sx, sz, px, pz = sx/8, sz/8, px/8, pz/8
                dx, dz = sx-px, sz-pz
                tgt = (math.degrees(math.atan2(dz, dx)) + 270) % 360
                signed = ((tgt+180)%360) - 180
                turn = ((tgt - (h_ang % 360) + 180) % 360) - 180
                # stronghold angle
                parts.append(("text", f"{signed:.2f}"))
                # arrow + magnitude
                if show_dir:
                    arrow = "->" if turn>0 else "<-"
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

    # pick a font
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
        ascent, descent = font.getmetrics()
        line_h = ascent + descent + 6
    except IOError:
        font = ImageFont.load_default()
        # measure default line height via textbbox
        dummy_bbox = ImageDraw.Draw(Image.new("RGBA",(1,1))).textbbox((0,0),"Ay",font=font)
        line_h = (dummy_bbox[3]-dummy_bbox[1]) + 4

    # canvas size
    max_width = 0
    height = line_h * len(lines) + 10
    img = Image.new("RGBA", (800, height), (255,255,255,255))  # start wide
    draw = ImageDraw.Draw(img)

    for row_idx, parts in enumerate(lines):
        x = 10
        y = 5 + row_idx * line_h
        skip_space = False  
        for kind, txt in parts:
            if kind == "certainty":
                pct = float(txt.rstrip("%"))
                fill = gradient_color(pct)
            elif kind == "angle_adjust":
                mag = min(int(float(txt)), 170)
                pct = 100 - (mag/170*100)
                fill = gradient_color(pct)
            else:
                fill = (0,0,0)

            draw.text((x, y), txt, font=font, fill=fill)

            space_str = "   "  
            if txt in ("->", "<-"):  
                space_str = " "
                skip_space = True

            bbox = draw.textbbox((0, 0), txt + space_str, font=font)
            w = bbox[2] - bbox[0]
            x += w
        # After finishing the line, track max width used
        if x > max_width:
            max_width = x

    # crop the image width to max_width + some padding (e.g., 10px)
    cropped_img = img.crop((0, 0, int(max_width + 10), height))

    # save and display cropped image
    cropped_img.save(IMAGE_PATH)
    log("Custom pinned image saved.")

    tk_img = ImageTk.PhotoImage(cropped_img)
    label.config(image=tk_img)
    label.image = tk_img
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

        time.sleep(0.2)


def custom_image_update_thread():
    while True:
        if USE_CUSTOM_PINNED_IMAGE:
            generate_custom_pinned_image()
        time.sleep(0.2) 


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
