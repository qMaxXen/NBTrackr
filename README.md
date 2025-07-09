# NBTrackr

> [!IMPORTANT]
> This script works **only on Linux**.

Python scripts that display Ninjabrain Bot info using notifications or pinned image overlays (Linux).  This is meant for people with a single monitor.

## Display Methods
I created two ways to display Ninjabrain Bot info. The first uses desktop notifications, while the second shows the built-in overlay provided by Ninjabrain Bot as a pinned image. You can choose whichever method you prefer.
- To use desktop notifications, download `NBTrackr-Notif-v2.0.0.tar.xz`.
- To use the pinned image overlay, download `NBTrackr-imgpin-v2.0.0.tar.xz`.

> You can scroll down to the [Features](https://github.com/qMaxXen/NBTrackr?tab=readme-ov-file#features-desktop-notifications) section to see what each method looks like.

## Installation

> [!CAUTION]
> The **desktop notifications method** requires the **dunst notification daemon** to display notifications correctly. It automatically checks if dunst is installed, and if not, installs it, then disables your current notification daemon and starts dunst.

1. Enable API in Ninjabrain Bot. 
![image](https://github.com/user-attachments/assets/fe684b8b-1601-4dc9-86be-97160a964954)

> [!IMPORTANT]
> If you're using the **pinned image overlay method**, you must also enable the **OBS Overlay** option in Ninjabrain Bot settings.  
> This is required for the overlay image to appear on your screen.
> <img src="https://github.com/user-attachments/assets/31afbb2b-597d-447e-9578-652a21d21d1d" width="500"/>

3. Go to the [releases](https://github.com/qMaxXen/NBTrackr/releases/tag/v2.0.0) section of this repository and download your preferred version.
- For desktop notifications, download `NBTrackr-Notif-v2.0.0.tar.xz`
- For pinned image overlay, download `NBTrackr-imgpin-v2.0.0.tar.xz`
3. Move the downloaded file to a convenient folder, then extract it using the terminal with the following command:
```bash
tar -xf <filename>
```
4. You have to install the required Python packages to run NBTrackr with the following command:
```bash
cd <extracted-folder>
pip3 install -r requirements.txt
```
5. Now run the script with the following command:

For desktop notifications:
```bash
python3 NBTrackr-Notif.py
```
For pinned image overlay:
```bash
python3 NBTrackr-imgpin.py
```

## Features: Desktop Notifications

- The notification will not appear if Ninjabrain Bot has no calculations.
- The notification appears on top of your Minecraft window.
- Shows whether you have a red or green boat:
  - The red or green boat notification is shown for only 10 seconds.
  - If you have blue boat, no notification will be shown.

![image](https://github.com/user-attachments/assets/e8afa63d-fc1e-4f1c-b9c3-bdc33462c6d4)
![image](https://github.com/user-attachments/assets/f20d5543-ca3b-4fef-9510-b5b285e5bf62)

- Displays an error when the stronghold chunk cannot be determined:

![image](https://github.com/user-attachments/assets/34ea3230-9929-4879-8574-bee31db80a75)

- Shows the following stronghold info:
  - Distance
  - X coordinate
  - Z coordinate
  - Stronghold Angle
  - Adjust Angle 
    - Displays `<--` / `-->` depending on which direction you need to turn.

![image](https://github.com/user-attachments/assets/52e77fc6-3eca-4081-8146-23299ecbe257)

## Features: Pinned Image Overlay

- The pinned image overlay will not appear if Ninjabrain Bot has no calculations.
- The pinned image overlay appears on top of your Minecraft window.
- Shows whether you have a red or green boat:
  - The red or green boat pinned image is shown for only 10 seconds.
  - If you have blue boat, no pinned image will be shown.
- You can freely move the overlay.
<img src="https://github.com/user-attachments/assets/16035fd8-3ced-4733-b665-be802fc4c40b" width="500"/>
<img src="https://github.com/user-attachments/assets/5cc0f894-6c93-486a-8f02-6be4c9193e60" width="500"/>
<img src="https://github.com/user-attachments/assets/3aaecc98-92ed-45db-a828-2f9751f48acf" width="500"/>



---

> [!TIP]
> - You should set a hotkey to reset Ninjabrain Bot calculations in Ninjabrain Bot > Settings > Hotkeys, by binding a key to Reset.

If you need help or have any questions, feel free to contact me on Discord: **qMaxXen**.
