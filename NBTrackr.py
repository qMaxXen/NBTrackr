import time
import math
import requests
import dbus
from concurrent.futures import ThreadPoolExecutor

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
        return r.json().get("boatState", "UNKNOWN")
    except requests.RequestException as e:
        print(f"[Boat API Error] {e}")
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
    with ThreadPoolExecutor(max_workers=2) as executor:
        while True:
            future_boat = executor.submit(get_boat_state)
            future_stronghold = executor.submit(get_stronghold_data)

            boat_state = print_boat_state(future_boat.result())
            if boat_state == "BLUE BOAT":
                print("Boat is blue, skipping notification…")
                close_notification()
                time.sleep(0.2)
                continue

            (result_type,
             dist, cert, cx, cz,
             in_nether, h_ang, px, pz) = future_stronghold.result()

            if boat_state == "RED BOAT" and in_nether:
                print("In Nether with Red Boat, skipping notification…")
                close_notification()
                time.sleep(0.2)
                continue

            if result_type == "FAILED":
                lines = [
                    boat_state,
                    "Could not determine the stronghold chunk."
                ]
                notify("NBTrackr", "\n".join(lines), "critical")
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
            print("-" * 30)
            time.sleep(0.2)
