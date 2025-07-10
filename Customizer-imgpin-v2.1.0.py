import os
import json
import tkinter as tk
from tkinter import ttk, messagebox

CUSTOM_PATH = os.path.expanduser("~/.config/NBTrackr/customizations.json")

DEFAULT_CUSTOMIZATIONS = {
    "use_custom_pinned_image": False,
    "shown_measurements": 1,
    "show_angle_direction": False,
    "show_coords_based_on_dimension": False,
    "text_order": [
        "distance",
        "certainty_percentage",
        "angle",
        "overworld_coords",
        "nether_coords"
    ],
    "text_enabled": {
        "distance": True,
        "certainty_percentage": True,
        "angle": True,
        "overworld_coords": True,
        "nether_coords": True
    }
}

DISPLAY_NAMES = {
    "distance": "Distance",
    "certainty_percentage": "Certainty Percentage",
    "angle": "Angle",
    "overworld_coords": "Overworld Coords",
    "nether_coords": "Nether Coords"
}

def ensure_custom_file_exists():
    config_dir = os.path.dirname(CUSTOM_PATH)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    if not os.path.isfile(CUSTOM_PATH):
        with open(CUSTOM_PATH, "w") as f:
            json.dump(DEFAULT_CUSTOMIZATIONS, f, indent=4)

def load_customizations():
    try:
        with open(CUSTOM_PATH, "r") as f:
            data = json.load(f)
            # Migrate old keys
            if "Shown_measurements" in data and "shown_measurements" not in data:
                data["shown_measurements"] = data.pop("Shown_measurements")
            # Migrate old text keys
            rename_map = {
                "Horizontal Angle": "angle",
                "Vertical Angle": None,
                "Coordinates": "overworld_coords"
            }
            data["text_order"] = [
                rename_map.get(item, item)
                for item in data.get("text_order", DEFAULT_CUSTOMIZATIONS["text_order"])
                if rename_map.get(item, item) is not None
            ]
            data["text_enabled"] = {
                rename_map.get(k, k): v
                for k, v in data.get("text_enabled", {}).items()
                if rename_map.get(k, k) is not None
            }
            return data
    except Exception:
        return DEFAULT_CUSTOMIZATIONS.copy()

def save_customizations(data):
    with open(CUSTOM_PATH, "w") as f:
        json.dump(data, f, indent=4)

def swap_positions(lst, idx, direction):
    new_idx = idx + direction
    if 0 <= new_idx < len(lst):
        lst[idx], lst[new_idx] = lst[new_idx], lst[idx]

def main():
    ensure_custom_file_exists()
    customizations = load_customizations()

    root = tk.Tk()
    root.title("NBTrackr Customizer")
    root.geometry("450x480")
    root.resizable(False, False)

    tk.Label(root, text="Customize Pinned Image Overlay", font=("Helvetica", 14)).pack(pady=10)

    container = tk.Frame(root)
    container.pack(pady=5, fill="x")

    frame_custom_image = tk.Frame(container)
    frame_custom_image.pack(fill="x", pady=5, padx=10)
    use_custom_image_var = tk.BooleanVar(value=customizations.get("use_custom_pinned_image", False))
    tk.Label(frame_custom_image, text="Use custom pinned image", anchor="w").pack(side="left")
    use_custom_image_cb = tk.Checkbutton(frame_custom_image, variable=use_custom_image_var)
    use_custom_image_cb.pack(side="left", padx=10)

    frame_shown = tk.Frame(container)
    frame_shown.pack(fill="x", pady=5, padx=10)
    tk.Label(frame_shown, text="Shown measurements:", width=18, anchor="w").pack(side="left")
    shown_var = tk.IntVar(value=customizations.get("shown_measurements", 1))
    shown_dropdown = ttk.Combobox(frame_shown, width=5, textvariable=shown_var, state="readonly")
    shown_dropdown['values'] = [1, 2, 3, 4, 5]
    shown_dropdown.pack(side="left")

    frame_angle_dir = tk.Frame(container)
    frame_angle_dir.pack(fill="x", pady=5, padx=10)
    show_angle_var = tk.BooleanVar(value=customizations.get("show_angle_direction", False))
    tk.Label(frame_angle_dir, text="Show angle direction (e.g. <- 24.3)", anchor="w").pack(side="left")
    show_angle_cb = tk.Checkbutton(frame_angle_dir, variable=show_angle_var)
    show_angle_cb.pack(side="left", padx=10)

    frame_coords_dim = tk.Frame(container)
    frame_coords_dim.pack(fill="x", pady=5, padx=10)
    show_coords_dim_var = tk.BooleanVar(value=customizations.get("show_coords_based_on_dimension", False))
    tk.Label(frame_coords_dim, text="Show Overworld/Nether coords based on dimension", anchor="w").pack(side="left")
    show_coords_dim_cb = tk.Checkbutton(frame_coords_dim, variable=show_coords_dim_var)
    show_coords_dim_cb.pack(side="left", padx=10)

    tk.Label(container, text="Text Elements:", font=("Helvetica", 12)).pack(pady=(15, 5), anchor="w", padx=10)

    text_order = customizations.get("text_order", DEFAULT_CUSTOMIZATIONS["text_order"].copy())
    text_enabled = customizations.get("text_enabled", DEFAULT_CUSTOMIZATIONS["text_enabled"].copy())

    text_frame = tk.Frame(container)
    text_frame.pack(fill="x", padx=10)

    check_vars = {}
    buttons_for_items = {}

    def redraw_text_items():
        for child in text_frame.winfo_children():
            child.destroy()
        buttons_for_items.clear()

        for idx, item_key in enumerate(text_order):
            frame = tk.Frame(text_frame)
            frame.pack(fill="x", pady=2)

            display_name = DISPLAY_NAMES.get(item_key, item_key)
            var = check_vars.get(item_key)
            if var is None:
                var = tk.BooleanVar(value=text_enabled.get(item_key, True))
                check_vars[item_key] = var

            c = tk.Checkbutton(frame, text=display_name, variable=var)
            c.pack(side="left", padx=(0, 15))

            def move_left_closure(i=idx):
                def inner():
                    swap_positions(text_order, i, -1)
                    redraw_text_items()
                    update_widgets_state()
                return inner
            btn_left = tk.Button(frame, text="Move left", width=8, command=move_left_closure())
            btn_left.pack(side="left", padx=5)
            if idx == 0:
                btn_left.config(state="disabled")

            def move_right_closure(i=idx):
                def inner():
                    swap_positions(text_order, i, +1)
                    redraw_text_items()
                    update_widgets_state()
                return inner
            btn_right = tk.Button(frame, text="Move right", width=8, command=move_right_closure())
            btn_right.pack(side="left", padx=5)
            if idx == len(text_order) - 1:
                btn_right.config(state="disabled")

            buttons_for_items[item_key] = (c, btn_left, btn_right)

    redraw_text_items()

    def update_widgets_state(*args):
        enabled = use_custom_image_var.get()
        shown_dropdown.config(state="readonly" if enabled else "disabled")
        show_angle_cb.config(state="normal" if enabled else "disabled")
        show_coords_dim_cb.config(state="normal" if enabled else "disabled")

        for idx, item in enumerate(text_order):
            checkbox, btn_left, btn_right = buttons_for_items[item]
            checkbox.config(state="normal" if enabled else "disabled")
            btn_left.config(state="disabled" if idx == 0 or not enabled else "normal")
            btn_right.config(state="disabled" if idx == len(text_order) - 1 or not enabled else "normal")

    use_custom_image_var.trace_add("write", update_widgets_state)
    update_widgets_state()

    def on_save():
        customizations["use_custom_pinned_image"] = use_custom_image_var.get()
        customizations["shown_measurements"] = shown_var.get()
        customizations["show_angle_direction"] = show_angle_var.get()
        customizations["show_coords_based_on_dimension"] = show_coords_dim_var.get()

        for key, var in check_vars.items():
            text_enabled[key] = var.get()

        customizations["text_order"] = text_order
        customizations["text_enabled"] = text_enabled

        save_customizations(customizations)
        messagebox.showinfo("Settings Saved", "Your settings have been saved successfully.")

    def on_reset():
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset to default settings?"):
            save_customizations(DEFAULT_CUSTOMIZATIONS.copy())

            customizations.clear()
            customizations.update(DEFAULT_CUSTOMIZATIONS)

            use_custom_image_var.set(customizations["use_custom_pinned_image"])
            shown_var.set(customizations["shown_measurements"])
            show_angle_var.set(customizations["show_angle_direction"])
            show_coords_dim_var.set(customizations["show_coords_based_on_dimension"])

            text_order.clear()
            text_order.extend(customizations["text_order"])
            for key, var in check_vars.items():
                var.set(customizations["text_enabled"].get(key, True))

            redraw_text_items()
            update_widgets_state()
            messagebox.showinfo("Reset Complete", "Settings have been reset to defaults.")

    bottom_frame = tk.Frame(root)
    bottom_frame.pack(side="bottom", fill="x", pady=10, padx=10)

    save_btn = tk.Button(bottom_frame, text="Save Settings", command=on_save)
    save_btn.pack(side="left")

    reset_btn = tk.Button(bottom_frame, text="Reset", command=on_reset)
    reset_btn.pack(side="left", padx=10)

    exit_btn = tk.Button(bottom_frame, text="Exit", command=root.destroy)
    exit_btn.pack(side="right")

    root.mainloop()

if __name__ == "__main__":
    main()
