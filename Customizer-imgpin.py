import os
import json
import tkinter as tk
import tkinter.font as tkFont
from tkinter import ttk, messagebox

CUSTOM_PATH = os.path.expanduser("~/.config/NBTrackr/customizations.json")

DEFAULT_CUSTOMIZATIONS = {
    "use_custom_pinned_image": False,
    "shown_measurements": 1,
    "show_angle_direction": False,
    "show_coords_based_on_dimension": False,
    "show_boat_icon": False,
    "show_error_message": False,
    "font_name": "Helvetica",
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
    cfg_dir = os.path.dirname(CUSTOM_PATH)
    if not os.path.isdir(cfg_dir):
        os.makedirs(cfg_dir)
    if not os.path.isfile(CUSTOM_PATH):
        with open(CUSTOM_PATH, "w") as f:
            json.dump(DEFAULT_CUSTOMIZATIONS, f, indent=4)

def load_customizations():
    try:
        with open(CUSTOM_PATH, "r") as f:
            data = json.load(f)

            # Merge missing keys from default without overwriting existing keys
            for key, val in DEFAULT_CUSTOMIZATIONS.items():
                if key not in data:
                    data[key] = val
                else:
                    # For nested dict (like text_enabled), merge keys as well
                    if isinstance(val, dict) and isinstance(data.get(key), dict):
                        for sub_key, sub_val in val.items():
                            if sub_key not in data[key]:
                                data[key][sub_key] = sub_val

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
    custom = load_customizations()

    root = tk.Tk()
    root.title("NBTrackr Customizer")
    root.geometry("450x590")
    root.resizable(False, False)

    tk.Label(root, text="Customize Pinned Image Overlay", font=("Helvetica", 14)).pack(pady=10)
    container = tk.Frame(root)
    container.pack(padx=10, fill="x")

    # Use custom pinned image
    f1 = tk.Frame(container); f1.pack(fill="x", pady=5)
    use_var = tk.BooleanVar(value=custom.get("use_custom_pinned_image", False))
    tk.Label(f1, text="Use custom pinned image", anchor="w").pack(side="left")
    tk.Checkbutton(f1, variable=use_var).pack(side="left", padx=5)

    # Shown measurements
    f2 = tk.Frame(container); f2.pack(fill="x", pady=5)
    tk.Label(f2, text="Shown measurements:", width=18, anchor="w").pack(side="left")
    shown_var = tk.IntVar(value=custom.get("shown_measurements", 1))
    cb_shown = ttk.Combobox(f2, textvariable=shown_var, state="readonly", width=5)
    cb_shown['values'] = [1,2,3,4,5]
    cb_shown.pack(side="left", padx=5)

    def clear_selection(event):
        event.widget.selection_clear()
    
    cb_shown.bind("<<ComboboxSelected>>", clear_selection)
    

    # Show angle direction
    f3 = tk.Frame(container); f3.pack(fill="x", pady=5)
    ang_var = tk.BooleanVar(value=custom.get("show_angle_direction", False))
    tk.Label(f3, text="Show angle direction (e.g. <- 24.3)", anchor="w").pack(side="left")
    tk.Checkbutton(f3, variable=ang_var).pack(side="left", padx=5)

    # Show coords by dimension
    f4 = tk.Frame(container); f4.pack(fill="x", pady=5)
    dim_var = tk.BooleanVar(value=custom.get("show_coords_based_on_dimension", False))
    tk.Label(f4, text="Show Overworld/Nether coords based on dimension", anchor="w").pack(side="left")
    tk.Checkbutton(f4, variable=dim_var).pack(side="left", padx=5)

    # Show boat icon toggle
    f_boat = tk.Frame(container); f_boat.pack(fill="x", pady=5)
    boat_var = tk.BooleanVar(value=custom.get("show_boat_icon", False))
    tk.Label(f_boat, text="Show green/red boat icon", anchor="w").pack(side="left")
    tk.Checkbutton(f_boat, variable=boat_var).pack(side="left", padx=5)

    # Show Could‑not‑determine error
    f_error = tk.Frame(container); f_error.pack(fill="x", pady=5)
    error_var = tk.BooleanVar(value=custom.get("show_error_message", False))
    tk.Label(f_error, text="Show “Could not determine” error", anchor="w").pack(side="left")
    tk.Checkbutton(f_error, variable=error_var).pack(side="left", padx=5)

    # Appearance section
    tk.Label(container, text="Appearance:", font=("Helvetica", 12)).pack(pady=(15,5), anchor="w")
    f5 = tk.Frame(container); f5.pack(fill="x", pady=5)
    tk.Label(f5, text="Font:", width=12, anchor="w").pack(side="left")
    font_var = tk.StringVar(value=custom.get("font_name", DEFAULT_CUSTOMIZATIONS["font_name"]))
    all_fonts = sorted(tkFont.families())
    font_dropdown = ttk.Combobox(f5, textvariable=font_var, state="readonly")
    font_dropdown['values'] = all_fonts
    font_dropdown.pack(side="left", fill="x", expand=True)

    def clear_selection(event):
        # Clear any selection/highlight in the combobox Entry widget
        event.widget.selection_clear()

    font_dropdown.bind("<<ComboboxSelected>>", clear_selection)


    def apply_font_dropdown(*_):
        try:
            font_dropdown.configure(font=(font_var.get(), 10))
        except tk.TclError:
            font_dropdown.configure(font=("Helvetica", 10))

    font_var.trace_add("write", apply_font_dropdown)
    root.after(100, apply_font_dropdown)  # Apply font after initialization

    # Text Elements header
    tk.Label(container, text="Text Elements:", font=("Helvetica", 12)).pack(pady=(15,5), anchor="w")

    # Text order & enable/disable
    order = custom.get("text_order", DEFAULT_CUSTOMIZATIONS["text_order"].copy())
    enabled = custom.get("text_enabled", DEFAULT_CUSTOMIZATIONS["text_enabled"].copy())
    text_frame = tk.Frame(container); text_frame.pack(fill="x", padx=10)
    check_vars = {}
    buttons = {}

    def redraw_items():
        for w in text_frame.winfo_children():
            w.destroy()
        buttons.clear()
        for idx, key in enumerate(order):
            frm = tk.Frame(text_frame); frm.pack(fill="x", pady=2)
            name = DISPLAY_NAMES.get(key, key)
            var = check_vars.get(key, tk.BooleanVar(value=enabled.get(key, True)))
            check_vars[key] = var
            tk.Checkbutton(frm, text=name, variable=var).pack(side="left", padx=(0,15))
            def mk_left(i=idx):
                return lambda: (swap_positions(order,i,-1), redraw_items(), update_state())
            btnL = tk.Button(frm, text="Move left", width=8, command=mk_left())
            btnL.pack(side="left", padx=5)
            if idx==0: btnL.config(state="disabled")
            def mk_right(i=idx):
                return lambda: (swap_positions(order,i,1), redraw_items(), update_state())
            btnR = tk.Button(frm, text="Move right", width=8, command=mk_right())
            btnR.pack(side="left", padx=5)
            if idx==len(order)-1: btnR.config(state="disabled")
            buttons[key] = (btnL, btnR)

    redraw_items()

    def update_state(*_):
        en = use_var.get()
        cb_shown.config(state="readonly" if en else "disabled")
        ang_cb_state = "normal" if en else "disabled"
        dim_cb_state = "normal" if en else "disabled"
        ang_var_checkbox = f3.winfo_children()[1]  # The Checkbutton in f3
        dim_var_checkbox = f4.winfo_children()[1]  # The Checkbutton in f4
        boat_var_checkbox = f_boat.winfo_children()[1]
        error_var_checkbox = f_error.winfo_children()[1]
        ang_var_checkbox.config(state=ang_cb_state)
        dim_var_checkbox.config(state=dim_cb_state)
        boat_var_checkbox.config(state=dim_cb_state)
        error_var_checkbox.config(state="normal" if en else "disabled")
        for i,key in enumerate(order):
            btnL, btnR = buttons[key]
            state = "normal" if en and i>0 else "disabled"
            btnL.config(state=state)
            state = "normal" if en and i< len(order)-1 else "disabled"
            btnR.config(state=state)

    use_var.trace_add("write", update_state)
    update_state()

    # Save / Reset / Exit buttons
    def on_save():
        custom.update({
            "use_custom_pinned_image": use_var.get(),
            "shown_measurements": shown_var.get(),
            "show_angle_direction": ang_var.get(),
            "show_coords_based_on_dimension": dim_var.get(),
            "show_boat_icon": boat_var.get(),
            "show_error_message": error_var.get(),
            "font_name": font_var.get(),
            "text_order": order,
            "text_enabled": {k: var.get() for k,var in check_vars.items()}
        })
        save_customizations(custom)
        messagebox.showinfo("Settings Saved", "Your settings have been saved successfully.")

    def on_reset():
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset to defaults?"):
            save_customizations(DEFAULT_CUSTOMIZATIONS.copy())
            custom.clear(); custom.update(DEFAULT_CUSTOMIZATIONS)
            use_var.set(custom["use_custom_pinned_image"])
            shown_var.set(custom["shown_measurements"])
            ang_var.set(custom["show_angle_direction"])
            dim_var.set(custom["show_coords_based_on_dimension"])
            boat_var.set(custom["show_boat_icon"])
            error_var.set(custom["show_error_message"])
            font_var.set(custom["font_name"])
            order[:] = custom["text_order"]
            for k,var in check_vars.items():
                var.set(custom["text_enabled"].get(k, True))
            redraw_items()
            update_state()
            messagebox.showinfo("Reset Complete", "Settings have been reset to defaults.")

    btn_frame = tk.Frame(root); btn_frame.pack(side="bottom", fill="x", pady=10, padx=10)
    tk.Button(btn_frame, text="Save Settings", command=on_save).pack(side="left")
    tk.Button(btn_frame, text="Reset", command=on_reset).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Exit", command=root.destroy).pack(side="right")

    root.mainloop()

if __name__ == "__main__":
    main()
