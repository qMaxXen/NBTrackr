import tkinter as tk
from PIL import Image, ImageTk, UnidentifiedImageError
import os
import threading
import queue
import time
import requests
from datetime import datetime

# Program Version

APP_VERSION = "v2.0.0"

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
    
if __name__ == "__main__":
    print(f"NBTrackr version: {APP_VERSION}")

    latest = check_for_update(APP_VERSION)
    if latest:
        print(f"New release is available: {latest}")
        input("Press Enter to continue...\n")


# --------------------- NBTrackr Pin Image --------------------------

IMAGE_PATH = "/tmp/nb-overlay.png"
GREEN_IMG = os.path.join(os.path.dirname(__file__), "assets/boat_green.png")
RED_IMG = os.path.join(os.path.dirname(__file__), "assets/boat_red.png")

root = tk.Tk()
root.overrideredirect(True)
root.wm_attributes("-topmost", True)

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

def log(*args):
    print(datetime.now().strftime("[%H:%M:%S]"), *args)

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

def image_loader_thread():
    last_logged_state = None
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

        # Show green/red boat images only if NOT in Nether and result_type is NONE or BLIND
        if not is_in_nether and result_type in ("NONE", "BLIND"):
            if last_shown == "VALID" and now < show_until:
                path = GREEN_IMG
                decision_reason = "Showing GREEN boat image"
            elif last_shown == "ERROR" and now < show_until:
                path = RED_IMG
                decision_reason = "Showing RED boat image"

        # Show pinned overlay image for NONE or BLIND resultType
        if path is None and result_type in ("NONE", "BLIND") and boat_state in ("VALID", "ERROR") and is_image_nonempty(IMAGE_PATH) and now < show_until:
            path = IMAGE_PATH
            decision_reason = "Showing pinned overlay image"

        # Show overlay image ALWAYS if resultType == TRIANGULATION (regardless of boat state or Nether)
        if path is None and result_type == "TRIANGULATION" and is_image_nonempty(IMAGE_PATH):
            path = IMAGE_PATH
            decision_reason = "Showing overlay image for TRIANGULATION"

        if path and is_image_nonempty(path):
            try:
                img = Image.open(path).convert("RGBA")
                if image_queue.full():
                    try:
                        image_queue.get_nowait()
                    except queue.Empty:
                        pass
                image_queue.put(img)
            except (UnidentifiedImageError, OSError):
                if image_queue.full():
                    try:
                        image_queue.get_nowait()
                    except queue.Empty:
                        pass
                image_queue.put(None)
        else:
            if image_queue.full():
                try:
                    image_queue.get_nowait()
                except queue.Empty:
                    pass
            image_queue.put(None)

        current_state = (boat_state, result_type, last_shown, is_in_nether, decision_reason)
        if current_state != last_logged_state:
            log("Boat:", boat_state, "| Result:", result_type,
                "| Shown:", last_shown, "| Nether:", is_in_nether,
                "| Action:", decision_reason)
            last_logged_state = current_state

        time.sleep(0.01)

def update_image():
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

        x = root.winfo_x()
        y = root.winfo_y()
        root.geometry(f"{img.width}x{img.height}+{x}+{y}")
        root.deiconify()

    root.after(10, update_image)

def start_move(event):
    root._drag_start_x = event.x
    root._drag_start_y = event.y

def on_motion(event):
    x = event.x_root - root._drag_start_x
    y = event.y_root - root._drag_start_y
    root.geometry(f"+{x}+{y}")

label.bind("<Button-1>", start_move)
label.bind("<B1-Motion>", on_motion)

threading.Thread(target=api_polling_thread, daemon=True).start()
threading.Thread(target=image_loader_thread, daemon=True).start()

update_image()
root.mainloop()
