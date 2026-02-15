# NBTrackr

[![GitHub release](https://img.shields.io/github/v/release/qMaxXen/NBTrackr?logo=github)](https://github.com/qMaxXen/NBTrackr/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/qMaxXen/NBTrackr/total?logo=github)](https://github.com/qMaxXen/NBTrackr/releases)

> [!IMPORTANT]
> This script works **only on Linux**.

Python scripts that display Ninjabrain Bot info using notifications or pinned image overlays (Linux).  This is mainly useful for **single-monitor** users, but also helpful for those with a second monitor.

## Display Methods
I created two ways to display Ninjabrain Bot info. The first uses desktop notifications, while the second shows the built-in overlay provided by Ninjabrain Bot as a pinned image. You can also customize the pinned image overlay. Choose whichever method you prefer.
- To use desktop notifications, download `NBTrackr-Notif-v2.1.7.tar.xz`.
- To use the pinned image overlay, download `NBTrackr-imgpin-v2.1.7.tar.xz`.

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

2. Go to the [releases](https://github.com/qMaxXen/NBTrackr/releases/latest) section of this repository and download your preferred version.
   - For desktop notifications, download `NBTrackr-Notif-v2.1.7.tar.xz`
   - For pinned image overlay, download `NBTrackr-imgpin-v2.1.7.tar.xz`
3. Move the downloaded file to a convenient folder, then extract it using the terminal with the following command:

   ```bash
   tar -xf <filename>
   ```
4. If you're using the **pinned image overlay method**, you must have tkinter installed:
   - Debian/Ubuntu: `sudo apt install python3-tk`
   - Arch Linux: `sudo pacman -S tk`
   - Fedora: `sudo dnf install python3-tkinter`
5. Install the required Python packages to run NBTrackr with the following command:

   ```bash
   cd <extracted-folder>
   pip3 install -r requirements.txt
   ```
> [!TIP]
> Getting the `PEP 668 (externally-managed-environment)` error after running `pip3 install -r requirements.txt`? Create a Python virtual environment:
> ```bash
> # Make sure you are in the extracted folder
> python3 -m venv venv
> source venv/bin/activate
> pip install -r requirements.txt
> ```
> To run the script from the terminal without needing to enter the venv, use the Python binary inside the venv:
> ```bash
> /full/path/to/venv/bin/python <script>.py
> ```

6. Now run the script with the following command in the terminal:
   - For desktop notifications: `python3 NBTrackr-Notif.py`
   - For pinned image overlay: `python3 NBTrackr-imgpin.py`
> [!NOTE]
> On some Linux setups (especially Wayland), the **pinned image overlay** may steal focus on first launch. This behavior depends
> on your window manager or desktop environment. On X11, it should not steal focus. To unfocus it, simply switch to a different
> workspace or click on another window. If you ever click on the pinned image overlay window, you will need to repeat this
> action.

## Features: Desktop Notifications

- The notification will not appear if Ninjabrain Bot has no calculations.
- The notification appears on top of your Minecraft window.
- Shows whether you have a red or green boat:
  - The red or green boat notification is shown for only 10 seconds.
  - If you have blue boat, no notification will be shown.
  - If you're using `Green Boat` mode in Ninjabrain Bot, boat notifications will not be shown.

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

### Basic Pinned Image Overlay Features

- The pinned image overlay will not appear if Ninjabrain Bot has no calculations.
- The pinned image overlay appears on top of your Minecraft window.
- Shows whether you have a red or green boat:
  - The red or green boat pinned image is shown for only 10 seconds.
  - If you have blue boat, no pinned image will be shown.
- You can freely move the overlay.
- The pinned image position gets saved and restored.
  - Position data is saved in `~/.config/NBTrackr/settings.json`
<img src="https://github.com/user-attachments/assets/16035fd8-3ced-4733-b665-be802fc4c40b" width="400"/>
<img src="https://github.com/user-attachments/assets/5cc0f894-6c93-486a-8f02-6be4c9193e60" width="400"/>
<img src="https://github.com/user-attachments/assets/3aaecc98-92ed-45db-a828-2f9751f48acf" width="400"/>


> [!TIP]
> I recommend using the [custom pinned image overlay](https://github.com/qMaxXen/NBTrackr?tab=readme-ov-file#customization-custom-pinned-image-overlay), as the default one uses Ninjabrain Bot’s `nb-overlay.png`, which updates with a delay. The custom pinned image overlay uses the API directly, so it updates instantly with no delay.

### Customization: Custom pinned image overlay

- Run the `Customizer-imgpin.py` script to choose your overlay preferences.
  - Customization settings are saved to `~/.config/NBTrackr/customizations.json`.
- To display the overlay in-game, run the `NBTrackr-imgpin.py` script.

<img src="https://github.com/user-attachments/assets/b51263d4-731e-4dd4-b8e1-4ec81fc4b2cd" width="300"/>
<br />
<img src="https://github.com/user-attachments/assets/eaca085e-83bb-4e7e-93b3-3921edcdd1e3" width="500"/>

## Credits
- [Ninjabrain](https://github.com/Ninjabrain1) – creator of Ninjabrain Bot.
- [Marin774](https://github.com/marin774) – for creating the [Jingle CalcOverlay Plugin](https://github.com/Marin774/Jingle-CalcOverlay-Plugin), which inspired the GUI for `Customizer-imgpin.py`.

---

If you have any issues, feel free to ask for help in the `#public-help` channel in the [Linux MCSR Discord server](https://discord.gg/3tm4UpUQ8t).
