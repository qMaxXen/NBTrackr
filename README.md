# NBTrackr

> [!IMPORTANT]
> This script works **only on Linux**.


A Python script that displays Ninjabrain Bot info using desktop notifications (Linux). This is meant for people with a single monitor.

## Installation

> [!CAUTION]
> This script requires the **dunst notification daemon** to display notifications correctly. It automatically checks if dunst is installed, and if not, installs and it, then disables your current notification daemon and starts dunst.

1. Enable API in Ninjabrain Bot. 
![image](https://github.com/user-attachments/assets/fe684b8b-1601-4dc9-86be-97160a964954)
2. Go to the [releases](https://github.com/qMaxXen/NBTrackr/releases/tag/v1.0.2) section of this repository and download **NBTrackr-v1.0.2.tar.xz**.
3. Move the downloaded **NBTrackr-v1.0.2.tar.xz** file to a convenient folder, then extract it using the terminal with the following command:
```bash
tar -xf NBTrackr-v1.0.2.tar.xz
```
> [!IMPORTANT]
> Make sure you have **Python 3** installed.
> You can check by running:
> ```bash
> python3 --version
> ```
> If it’s not installed, use your Linux distribution’s package manager to install it.
4. You have to install the required Python packages to run NBTrackr with the following command:
```bash
cd NBTrackr-v1.0.2
pip3 install -r requirements.txt
```
5. Now run the script with the following command:
```bash
python3 NBTrackr.py
```

## Features

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

> [!TIP]
> - You should set a hotkey to reset Ninjabrain Bot calculations in Ninjabrain Bot > Settings > Hotkeys, by binding a key to Reset.

---

If you need help or have any questions, feel free to contact me on Discord: **qMaxXen**.
