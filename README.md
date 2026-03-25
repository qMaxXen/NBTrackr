# NBTrackr

[![GitHub release](https://img.shields.io/github/v/release/qMaxXen/NBTrackr?logo=github)](https://github.com/qMaxXen/NBTrackr/releases/latest)
[![GitHub downloads](https://img.shields.io/github/downloads/qMaxXen/NBTrackr/total?logo=github)](https://github.com/qMaxXen/NBTrackr/releases/latest)

> [!IMPORTANT]
> This script works **only on Linux**.

A Python script that displays Ninjabrain Bot's info using a pinned image overlay. It comes with two types of overlays: the default overlay shows a replica of Ninjabrain Bot's window, and a custom overlay which is a more minimal overlay with more customization options. This is mainly useful for **single-monitor** users, but also helpful for those with a second monitor.

<div align="center">
<img src="https://github.com/user-attachments/assets/277dd40a-4fae-4790-bb10-24ea6d3e6bef" width="400"/>
<img src="https://github.com/user-attachments/assets/8ef4eb48-9716-403a-b59b-37424602fe1b" width="400"/>
</div>

## Installation

1. Enable API in Ninjabrain Bot. 
![image](https://github.com/user-attachments/assets/fe684b8b-1601-4dc9-86be-97160a964954)

2. Go to the [releases](https://github.com/qMaxXen/NBTrackr/releases/latest) section of this repository and download `NBTrackr-imgpin-v2.5.0.tar.xz`.

3. Move the downloaded file to a convenient folder, then extract it using the terminal with the following command:

   ```bash
   tar -xf NBTrackr-imgpin-v2.5.0.tar.xz
   ```
4. Install the required Python packages to run NBTrackr with the following command:

   ```bash
   cd NBTrackr-imgpin-v2.5.0
   chmod +x install.sh
   ./install.sh
   ```
5. To run NBTrackr, type:
   ```bash
   nbtrackr
   ```
   To configure NBTrackr, type:
   ```bash
   nbtrackr --settings
   ```

> [!NOTE]
> On some Linux setups (especially Wayland), the **pinned image overlay** may steal focus on launch. This behavior depends
> on your window manager or desktop environment. On X11, it should not steal focus. To unfocus it, simply switch to a different
> workspace or click on another window. If you ever click on the pinned image overlay window, you will need to repeat this
> action.

## Features
Read the [FEATURES.md](https://github.com/qMaxXen/NBTrackr/blob/main/FEATURES.md) file for a full list of features.

## License
NBTrackr is licensed under the MIT license. You can view the full license [here](https://github.com/qMaxXen/NBTrackr/blob/main/LICENSE).

## Credits
- [Ninjabrain](https://github.com/Ninjabrain1) – creator of Ninjabrain Bot.
- [Marin774](https://github.com/marin774) – for creating the [Jingle Calc Overlay Plugin](https://github.com/Marin774/Jingle-CalcOverlay-Plugin), which heavily inspired the GUI for `Customizer-imgpin.py`, and for generally inspiring parts of the implementation.

---

If you have any issues, feel free to ask for help by creating a thread in the [Linux MCSR Discord server](https://discord.gg/3tm4UpUQ8t).
