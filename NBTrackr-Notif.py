import time
import math
import requests
import shutil
import subprocess
import signal
import os
import sys
import dbus
from dbus import Boolean
import tempfile
import tarfile
from concurrent.futures import ThreadPoolExecutor
from colorama import Fore, Style

# Program Version

APP_VERSION = "v2.1.3"

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

        asset_name = f"NBTrackr-Notif-{latest}.tar.xz"
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
        print("[Updater] Please run the script from the new folder.")
        sys.exit(0)

    except Exception as e:
        print(f"[Updater] Update failed: {e}")

# ---------------------- AUTO UPDATER - END ----------------------


# ---------------------- Notification Daemon Setup ----------------------

KNOWN_DAEMONS = [
    "xfce4-notifyd",
    "mate-notification-daemon",
    "mako",
    "notify-osd",
    "notification-daemon",
    "swaync",
    "snixembed",
    "muffin",
    "cinnamon",
    "gala",
]

def install_dunst_if_missing():
    print("[+] Checking if dunst is installed...")
    if shutil.which("dunst") is None:
        print("[!] Dunst not found. Attempting installation...")
        if shutil.which("apt"):
            subprocess.run(["sudo", "apt", "update"])
            subprocess.run(["sudo", "apt", "install", "-y", "dunst"])
        elif shutil.which("pacman"):
            subprocess.run(["sudo", "pacman", "-Sy", "--noconfirm", "dunst"])
        elif shutil.which("dnf"):
            subprocess.run(["sudo", "dnf", "install", "-y", "dunst"])
        else:
            print(Fore.RED + "No supported package manager found. Please install dunst manually.")
            print(Style.RESET_ALL)
            sys.exit(1)

        print(Fore.YELLOW + "\n[!] Dunst has been installed. Please run this script again.\n" + Style.RESET_ALL)
        sys.exit(0) 
    else:
        print(Fore.GREEN + "Dunst is already installed.")
        print(Style.RESET_ALL)

def detect_running_notification_daemon():
    running = []
    for daemon in KNOWN_DAEMONS:
        try:
            subprocess.check_output(["pgrep", "-f", daemon], stderr=subprocess.DEVNULL)
            running.append(daemon)
        except subprocess.CalledProcessError:
            continue
    return running

def kill_notification_daemon(daemons):
    for daemon in daemons:
        print(f"[+] Killing {daemon}...")
        try:
            subprocess.run(["pkill", "-f", daemon], check=True)
        except subprocess.CalledProcessError:
            print(Fore.RED + f"Failed to kill {daemon} — continuing anyway.")
            print(Style.RESET_ALL)

def launch_dunst():
    print("[+] Launching dunst...")
    return subprocess.Popen(["dunst"])

def stop_dunst(proc):
    if proc and proc.poll() is None:
        print("[+] Stopping dunst...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

install_dunst_if_missing()
daemons_found = detect_running_notification_daemon()
if daemons_found:
    print(f"Found active notification daemon(s): {', '.join(daemons_found)}")
    kill_notification_daemon(daemons_found)
else:
    print(Fore.RED + "No known notification daemon is running.")
    print(Style.RESET_ALL)

dunst_process = launch_dunst()

def on_exit(signum, frame):
    stop_dunst(dunst_process)
    sys.exit(0)

signal.signal(signal.SIGINT, on_exit)
signal.signal(signal.SIGTERM, on_exit)

print(Style.RESET_ALL)

# -----------------------------------------------------------------------

BOAT_API_URL       = "http://localhost:52533/api/v1/boat"
STRONGHOLD_API_URL = "http://localhost:52533/api/v1/stronghold"

_notification_id = 0

bus = dbus.SessionBus()
notify_service = bus.get_object(
    'org.freedesktop.Notifications',
    '/org/freedesktop/Notifications'
)
notify_iface = dbus.Interface(
    notify_service,
    'org.freedesktop.Notifications'
)

def close_notification():
    global _notification_id
    try:
        notify_iface.CloseNotification(dbus.UInt32(_notification_id))
    except Exception:
        pass
    _notification_id = 0

def get_boat_state():
    try:
        r = requests.get(BOAT_API_URL, timeout=1)
        r.raise_for_status()
        data = r.json()
        state = data.get("boatState", "UNKNOWN")
        angle = data.get("boatAngle", 0)
        return state, angle
    except requests.RequestException as e:
        if "Connection refused" in str(e):
            print(Fore.RED + "ERROR: Ninjabrain Bot is not open OR API is not enabled in Ninjabrain Bot.")
            print(Style.RESET_ALL)
        return "UNKNOWN", 0

def get_stronghold_data():
    try:
        r = requests.get(STRONGHOLD_API_URL, timeout=1)
        r.raise_for_status()
        d = r.json()
        preds = d.get("predictions", [])
        pp   = d.get("playerPosition", {})
        return (
            d.get("resultType"),
            preds[0].get("overworldDistance") if preds else None,
            preds[0].get("certainty")          if preds else None,
            preds[0].get("chunkX")             if preds else None,
            preds[0].get("chunkZ")             if preds else None,
            pp.get("isInNether", False),
            pp.get("horizontalAngle", None),
            pp.get("xInOverworld", None),
            pp.get("zInOverworld", None),
        )
    except requests.RequestException as e:
        return (None,) * 9

def print_boat_state(s):
    if s == "MEASURING":
        print("Blue Boat")
        return "BLUE BOAT"
    elif s == "ERROR":
        print("Red Boat")
        return "RED BOAT"
    elif s == "VALID":
        print("Green Boat")
        return "GREEN BOAT"
    else:
        print(f"Unknown boat state: {s}")
        return "UNKNOWN BOAT"

def notify(title, message, urgency='normal', timeout=0):
    global _notification_id
    urg = {'low': 0, 'normal': 1, 'critical': 2}[urgency]
    hints = {
        'urgency': dbus.Byte(urg),
        'markup': Boolean(False)        #
    }
    nid = notify_iface.Notify(
        "NBTrackr",
        dbus.UInt32(_notification_id),
        "",
        title,
        message,
        [],
        hints,
        dbus.Int32(timeout)
    )
    _notification_id = int(nid)

def format_stronghold_data(dist, cert, cx, cz, in_nether):
    if None in (dist, cert, cx, cz):
        return None, None, None
    if in_nether:
        d = round(dist / 8)
    else:
        d = math.ceil(dist)
    cp = math.ceil(cert * 100)
    x = cx * 16 + 4
    z = cz * 16 + 4
    if in_nether:
        x = round(x / 8)
        z = round(z / 8)
    print(f"Distance: {d}, Certainty: {cp}%")
    print(f"X: {x}\nZ: {z}")
    return f"Distance: {d}", f"X: {x}", f"Z: {z}"

if __name__ == "__main__":
# --- Check for updates ---
    print(f"NBTrackr version: {APP_VERSION}")

    def check_for_update(current_version):
        latest_version = get_latest_github_release_version()
        if latest_version and latest_version != current_version:
            return latest_version
        return None


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

# --------- END ----
    last_boat_state_notified = None
    last_red_boat_notify_time = 0
    last_red_boat_angle = None
    RED_BOAT_NOTIFY_DURATION = 10

    with ThreadPoolExecutor(max_workers=2) as executor:
        while True:
            future_boat = executor.submit(get_boat_state)
            future_stronghold = executor.submit(get_stronghold_data)

            raw_state, boat_angle = future_boat.result()
            boat_state = print_boat_state(raw_state)
            
            if boat_state == "BLUE BOAT":
                print("Boat is blue, skipping notification…")
                close_notification()
                last_boat_state_notified = None
                last_red_boat_angle = None
                last_red_boat_notify_time = 0
                time.sleep(0.2)
                continue

            (result_type,
             dist, cert, cx, cz,
             in_nether, h_ang, px, pz) = future_stronghold.result()

            if result_type is None or None in (dist, cert, cx, cz):
                if boat_angle == 0:
                    close_notification()
                if boat_state == "GREEN BOAT":
                    if result_type == "FAILED":
                        notify("NBTrackr", "Could not determine the stronghold chunk.", "critical")
                        print("Stronghold FAILED, showing error message instead of green boat.")
                    else:
                        if boat_angle != 0 and boat_state != last_boat_state_notified:
                            notify("NBTrackr", boat_state, "normal", timeout=10_000)
                            last_boat_state_notified = boat_state
                            print("Showing GREEN BOAT (no info) once for 10 seconds.")
                        else:
                            print("Boat angle is 0°, skipping GREEN BOAT notification.")
                elif boat_state == "RED BOAT":
                    current_time = time.time()
                    if last_boat_state_notified != "RED BOAT":
                        notify("NBTrackr", boat_state, "critical", timeout=10_000)
                        last_boat_state_notified = "RED BOAT"
                        last_red_boat_notify_time = current_time
                        last_red_boat_angle = h_ang
                        print("Showing RED BOAT (no info) once for 10 seconds.")
                    else:
                        if current_time - last_red_boat_notify_time >= RED_BOAT_NOTIFY_DURATION:
                            if h_ang is not None and last_red_boat_angle is not None:
                                angle_diff = abs((h_ang - last_red_boat_angle + 180) % 360 - 180)
                                if angle_diff > 0.1:
                                    notify("NBTrackr", boat_state, "critical", timeout=10_000)
                                    last_red_boat_notify_time = current_time
                                    last_red_boat_angle = h_ang
                                    print(f"Angle changed by {angle_diff:.2f}°, showing RED BOAT again for 10 seconds.")
                                else:
                                    print(f"Angle did not change (diff {angle_diff:.2f}°), no new RED BOAT notification.")
                            else:
                                notify("NBTrackr", boat_state, "critical", timeout=10_000)
                                last_red_boat_notify_time = current_time
                                last_red_boat_angle = h_ang
                                print("Angle unknown, showing RED BOAT again for 10 seconds.")
                        else:
                            print("RED BOAT notification active, waiting before showing again.")
                time.sleep(0.2)
                continue

            last_boat_state_notified = None
            last_red_boat_angle = None
            last_red_boat_notify_time = 0

            if result_type == "FAILED":
                lines = [
                    boat_state,
                    "Could not determine the stronghold chunk."
                ]
                notify("NBTrackr", "\n".join(lines), "critical")
                last_boat_state_notified = boat_state
                print("Stronghold FAILED, showing error message.")
                time.sleep(0.2)
                continue

            dist_str, x_str, z_str = format_stronghold_data(dist, cert, cx, cz, in_nether)
            urgency = "critical" if boat_state == "RED BOAT" else "normal"

            angle_info = ""
            if None not in (h_ang, px, pz, cx, cz):
                sx = cx * 16 + 4; sz = cz * 16 + 4
                if in_nether:
                    sx /= 8; sz /= 8; px /= 8; pz /= 8
                dx = sx - px; dz = sz - pz
                tgt = (math.degrees(math.atan2(dz, dx)) + 270) % 360
                current = h_ang % 360
                signed_target = ((tgt + 180) % 360) - 180
                turn = round(((tgt - current + 180) % 360) - 180)
                print(f"Angle Of player: {round(((current + 180) % 360) - 180, 2)}°")
                print(f"Stronghold Angle: {round(signed_target, 2)}°")
                print(f"Adjust Angle: {turn}°")
                if turn > 0:
                    dir_sym = "-->"; print("Go right")
                elif turn < 0:
                    dir_sym = "<--"; print("Go left")
                else:
                    dir_sym = ""; print("You are aligned")
                angle_info = (
                    f"Stronghold Angle: {round(signed_target)}°\n"
                    f"Adjust Angle: {dir_sym} {abs(turn)}°"
                )

            lines = [boat_state]
            if dist is not None:
                lines += [dist_str, x_str, z_str]
            if angle_info:
                lines.append(angle_info)

            notify("NBTrackr", "\n".join(lines), urgency)
            last_boat_state_notified = boat_state
            print("-" * 30)
            time.sleep(0.2)
