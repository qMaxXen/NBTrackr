import time
import math
import requests
import shutil
import subprocess
import signal
import os
import sys
import dbus
from concurrent.futures import ThreadPoolExecutor
from colorama import Fore, Style

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

def init_dbus_notify_iface(retries=3, delay=1):
    bus = dbus.SessionBus()
    for attempt in range(1, retries + 1):
        try:
            notify_service = bus.get_object(
                'org.freedesktop.Notifications',
                '/org/freedesktop/Notifications'
            )
            notify_iface = dbus.Interface(
                notify_service,
                'org.freedesktop.Notifications'
            )
            return notify_iface
        except dbus.exceptions.DBusException as e:
            print(Fore.YELLOW + f"[!] DBus notifications not ready (attempt {attempt}/{retries}). Retrying in {delay} second(s)...")
            print(Style.RESET_ALL)
            time.sleep(delay)
    print(Fore.RED + "Failed to connect to DBus notification service after installing and launching dunst.")
    print("Please run the script again.")
    print(Style.RESET_ALL)
    sys.exit(1)

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

notify_iface = init_dbus_notify_iface()

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
        return r.json().get("boatState", "UNKNOWN")
    except requests.RequestException as e:
        print(f"[Boat API Error] {e}")
        if "Connection refused" in str(e):
            print(Fore.RED + "ERROR: Ninjabrain Bot is not open OR API is not enabled in Ninjabrain Bot.")
            print(Style.RESET_ALL)
        return "UNKNOWN"

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
        print(f"[Stronghold API Error] {e}")
        if "Connection refused" in str(e):
            print(Fore.RED + "ERROR: Ninjabrain Bot is not open OR API is not enabled in Ninjabrain Bot.")
            print(Style.RESET_ALL)
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
    hints = {'urgency': dbus.Byte(urg)}
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
    last_boat_state_notified = None
    last_red_boat_notify_time = 0
    last_red_boat_angle = None
    RED_BOAT_NOTIFY_DURATION = 10

    with ThreadPoolExecutor(max_workers=2) as executor:
        while True:
            future_boat = executor.submit(get_boat_state)
            future_stronghold = executor.submit(get_stronghold_data)

            boat_state = print_boat_state(future_boat.result())

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
                if boat_state == "GREEN BOAT":
                    if result_type == "FAILED":
                        notify("NBTrackr", "Could not determine the stronghold chunk.", "critical")
                        print("Stronghold FAILED, showing error message instead of green boat.")
                    else:
                        if boat_state != last_boat_state_notified:
                            notify("NBTrackr", boat_state, "normal", 3000)
                            last_boat_state_notified = boat_state
                else:
                    close_notification()
                time.sleep(0.2)
                continue

            dist_text, x_text, z_text = format_stronghold_data(dist, cert, cx, cz, in_nether)

            if boat_state == "RED BOAT":
                current_time = time.time()
                if (last_red_boat_angle is None or
                    abs(h_ang - last_red_boat_angle) > 15 or
                    (current_time - last_red_boat_notify_time) > RED_BOAT_NOTIFY_DURATION):
                    msg = f"Stronghold chunk: {x_text}, {z_text}\nCertainty: {math.ceil(cert * 100)}%\nDistance: {dist_text}"
                    notify("NBTrackr - Red Boat", msg, "critical")
                    last_red_boat_notify_time = current_time
                    last_red_boat_angle = h_ang
                else:
                    print("Skipping Red Boat notify: angle change or timer not reached")
            else:
                notify("NBTrackr", f"Stronghold chunk: {x_text}, {z_text}\nCertainty: {math.ceil(cert * 100)}%\nDistance: {dist_text}")

            last_boat_state_notified = boat_state
            time.sleep(0.2)
