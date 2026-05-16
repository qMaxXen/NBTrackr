# Features

## Arguments
- `--settings` - Opens a window to configure NBTrackr. For more information, see [Configuring Pinned Image Overlay](https://github.com/qMaxXen/NBTrackr/blob/main/FEATURES.md#configuring-pinned-image-overlay).
- `--headless` - Makes the window not appear. The information is written to `/tmp/imgpin-overlay.png`.

*Example usage:*
```bash
nbtrackr --headless
```

## General Pinned Image Overlay Features
- The pinned image overlay will not appear if Ninjabrain Bot has no calculations.
- The pinned image overlay appears on top of your Minecraft window.
- You can freely move the overlay.
- The pinned image position gets saved and restored.
  - Position data is saved in `~/.config/NBTrackr/settings.json`.

## Default Pinned Image Overlay Features
- Shows a full replica of Ninjabrain Bot's window.
- Shows the information messages:
  - "Detected unusually large errors, you probably mismeasured or your standard deviation is too low."
  - "You might not be able to nether travel into the stronghold due to portal linking."
  - "Go left X blocks, or right X blocks, for ~95% certainty after next measurement."
  - "Nether coords X have X% chance to hit the stronghold (it is between the top 2 offsets)."
- Shows the blind information.
- Shows the "Could not determine" error message.
- Shows boat states.

<img src="https://github.com/user-attachments/assets/8b72d5be-77bd-401e-8466-2a8449bb7d0f" width="400"/>
<img src="https://github.com/user-attachments/assets/54bd9bcd-da36-4c4f-99d0-258c2476ad17" width="400"/>
<img src="https://github.com/user-attachments/assets/0325eb88-6b3e-4f61-a372-424cb45e7ab6" width="400"/>
<img src="https://github.com/user-attachments/assets/b28b5865-1dca-4fa8-a7f0-3badcd1a87b7" width="400"/>

## Custom Pinned Image Overlay
- Shows a more minimal overlay with significantly more customization options compared to the default pinned image overlay.
- Shows the blind information.
- Shows the "Could not determine" error message.
- Shows boat states.

<img src="https://github.com/user-attachments/assets/88ede89b-ae2a-4b07-ab6a-b2f889377195" width="500"/>

## Configuring Pinned Image Overlay
- Type `nbtrackr --settings` in the terminal to customize the pinned image overlay.
- Every customization is saved to `~/.config/NBTrackr/customizations.json`.
- Note that when `Use custom pinned image overlay` is disabled under the `General` tab, many settings will be grayed out, as they only apply to the custom pinned image overlay.

### General tab
<img width="597" height="442" alt="image" src="https://github.com/user-attachments/assets/5d001060-e362-4e8e-96d6-7df2f93a7b04" />

### Eye Throws Overlay tab
<img width="597" height="679" alt="image" src="https://github.com/user-attachments/assets/27ae6a82-f872-4096-b83b-a286eaa5bd66" />

### Blind Coords Overlay tab
<img width="597" height="148" alt="image" src="https://github.com/user-attachments/assets/0f3c613f-3bd8-4493-b426-29b8917c139a" />

### Advanced tab
<img width="597" height="262" alt="image" src="https://github.com/user-attachments/assets/b745c015-2496-49f2-9f30-c2de3d786bff" />
