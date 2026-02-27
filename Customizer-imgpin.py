import os
import json
import tkinter as tk
import tkinter.font as tkFont
import subprocess
from tkinter import ttk, messagebox, colorchooser

def find_dejavu_bold_path():
    known_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",          
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",             
        "/usr/share/fonts/truetype/DejaVuSans-Bold.ttf",       
        "/run/current-system/sw/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  
        os.path.expanduser("~/.fonts/DejaVuSans-Bold.ttf"),
        os.path.expanduser("~/.local/share/fonts/DejaVuSans-Bold.ttf"),
    ]
    for p in known_paths:
        if os.path.isfile(p):
            return p

    try:
        result = subprocess.run(
            ["fc-match", "--format=%{file}", "DejaVu Sans:style=Bold"],
            capture_output=True, text=True, timeout=3
        )
        path = result.stdout.strip()
        if path and os.path.isfile(path) and path.lower().endswith((".ttf", ".otf")):
            return path
    except Exception:
        pass

    return ""

CUSTOM_PATH = os.path.expanduser("~/.config/NBTrackr/customizations.json")

DEFAULT_CUSTOMIZATIONS = {
    "use_custom_pinned_image": False,
    "shown_measurements": 1,
    "show_angle_direction": True,    
    "show_angle_adjustment_count": False,
    "show_coords_based_on_dimension": False,
    "show_boat_icon": True,           
    "show_error_message": True,       
    "show_blind_info": True,
    "blind_info_hide_after": 20,
    "blind_info_hide_after_enabled": False,
    "font_name": find_dejavu_bold_path(),
    "font_size": 18,
    "background_color": "#FFFFFF",
    "text_color": "#000000",
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
    },
    "debug_mode": False,
    "idle_api_polling_rate": 0.3,
    "max_api_polling_rate": 0.15
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

            for key, val in DEFAULT_CUSTOMIZATIONS.items():
                if key not in data:
                    data[key] = val
                else:
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

def pick_color(var):
    col = colorchooser.askcolor(title="Choose color")
    if col and col[1]:
        var.set(col[1])

def is_valid_hex(s):
    if not isinstance(s, str):
        return False
    if len(s) != 7 or not s.startswith("#"):
        return False
    try:
        int(s[1:], 16)
        return True
    except ValueError:
        return False

def find_system_fonts():
    fonts = {}

    search_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/run/current-system/sw/share/fonts",          
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for fname in files:
                if fname.lower().endswith((".ttf", ".otf")):
                    path = os.path.join(root, fname)
                    display = os.path.splitext(fname)[0]
                    fonts[display] = path

    if not fonts:
        try:
            result = subprocess.run(
                ["fc-list", "--format=%{file}\n"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                path = line.strip()
                if path and os.path.isfile(path) and path.lower().endswith((".ttf", ".otf")):
                    display = os.path.splitext(os.path.basename(path))[0]
                    fonts[display] = path
        except Exception:
            pass

    return dict(sorted(fonts.items(), key=lambda x: x[0].lower()))

def main():
    ensure_custom_file_exists()
    custom = load_customizations()

    root = tk.Tk()
    root.title("NBTrackr Pinned Image Overlay Customizer")
    root.resizable(False, False)

    use_var = tk.BooleanVar(value=custom.get("use_custom_pinned_image", False))

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    tab_general  = tk.Frame(notebook)
    tab_eye      = tk.Frame(notebook)
    tab_blind    = tk.Frame(notebook)
    tab_advanced = tk.Frame(notebook)

    notebook.add(tab_general,  text="General")
    notebook.add(tab_eye,      text="Eye Throws Overlay")
    notebook.add(tab_blind,    text="Blind Coords Overlay")
    notebook.add(tab_advanced, text="Advanced")

    g = tk.Frame(tab_general)
    g.pack(padx=10, pady=10, fill="x")

    f1 = tk.Frame(g); f1.pack(fill="x", pady=5)
    tk.Label(f1, text="Use custom pinned image overlay", anchor="w").pack(side="left")
    tk.Checkbutton(f1, variable=use_var, relief="flat", bd=0).pack(side="left", padx=5)

    f5 = tk.Frame(g); f5.pack(fill="x", pady=5)
    tk.Label(f5, text="Font", width=18, anchor="w").pack(side="left")

    system_fonts = find_system_fonts()
    font_path_to_display = {v: k for k, v in system_fonts.items()}

    saved_font_path = custom.get("font_name", "")
    saved_font_display = font_path_to_display.get(saved_font_path, "")

    font_var = tk.StringVar(value=saved_font_display)
    font_dropdown = ttk.Combobox(f5, textvariable=font_var, state="readonly")
    font_dropdown['values'] = list(system_fonts.keys())
    font_dropdown.pack(side="left", fill="x", expand=True)
    font_dropdown.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear())

    def apply_font_dropdown(*_):
        try:
            font_dropdown.configure(font=(font_var.get(), 10))
        except tk.TclError:
            font_dropdown.configure(font=("Helvetica", 10))

    font_var.trace_add("write", apply_font_dropdown)
    root.after(100, apply_font_dropdown)

    f_size = tk.Frame(g); f_size.pack(fill="x", pady=5)
    tk.Label(f_size, text="Font size", width=18, anchor="w").pack(side="left")
    font_size_var = tk.IntVar(value=custom.get("font_size", DEFAULT_CUSTOMIZATIONS["font_size"]))
    font_size_spinbox = tk.Spinbox(f_size, from_=8, to=48, textvariable=font_size_var, width=8)
    font_size_spinbox.pack(side="left", padx=5)

    f_bg = tk.Frame(g); f_bg.pack(fill="x", pady=(5, 2))
    tk.Label(f_bg, text="Background color", width=18, anchor="w").pack(side="left")
    bg_var = tk.StringVar(value=custom.get("background_color", DEFAULT_CUSTOMIZATIONS["background_color"]))
    bg_entry = tk.Entry(f_bg, textvariable=bg_var, width=10)
    bg_entry.pack(side="left", padx=5)
    bg_choose_btn = tk.Button(f_bg, text="Choose", command=lambda: pick_color(bg_var))
    bg_choose_btn.pack(side="left", padx=(0, 10))

    f_text = tk.Frame(g); f_text.pack(fill="x", pady=(2, 5))
    tk.Label(f_text, text="Text color", width=18, anchor="w").pack(side="left")
    text_var = tk.StringVar(value=custom.get("text_color", DEFAULT_CUSTOMIZATIONS["text_color"]))
    text_entry = tk.Entry(f_text, textvariable=text_var, width=10)
    text_entry.pack(side="left", padx=5)
    text_choose_btn = tk.Button(f_text, text="Choose", command=lambda: pick_color(text_var))
    text_choose_btn.pack(side="left")

    e = tk.Frame(tab_eye)
    e.pack(padx=10, pady=10, fill="x")

    f2 = tk.Frame(e); f2.pack(fill="x", pady=5)
    tk.Label(f2, text="Shown measurements", width=30, anchor="w").pack(side="left")
    shown_var = tk.IntVar(value=custom.get("shown_measurements", 1))
    cb_shown = ttk.Combobox(f2, textvariable=shown_var, state="readonly", width=5)
    cb_shown['values'] = [1, 2, 3, 4, 5]
    cb_shown.pack(side="left", padx=5)
    cb_shown.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear())

    f3 = tk.Frame(e); f3.pack(fill="x", pady=5)
    ang_var = tk.BooleanVar(value=custom.get("show_angle_direction", False))
    tk.Label(f3, text="Show angle direction (e.g. <- 24.3)", anchor="w").pack(side="left")
    ang_checkbox = tk.Checkbutton(f3, variable=ang_var)
    ang_checkbox.pack(side="left", padx=5)

    f3b = tk.Frame(e); f3b.pack(fill="x", pady=5)
    adj_count_var = tk.BooleanVar(value=custom.get("show_angle_adjustment_count", False))
    tk.Label(f3b, text="Show angle adjustment count", anchor="w").pack(side="left")
    adj_count_checkbox = tk.Checkbutton(f3b, variable=adj_count_var)
    adj_count_checkbox.pack(side="left", padx=5)

    def on_adj_count_toggled(*_):
        if adj_count_var.get():
            messagebox.showwarning(
                "NBTrackr - Angle Adjustment Count",
                "The angle adjustment count is an estimate because\n"
                "Ninjabrain Bot API doesn't provide the exact number of adjustments.\n\n"
                "It should work correctly most of the time,\n"
                "but be aware that it's not 100% accurate.\n\n"
                "This will be fixed in Ninjabrain Bot v1.5.2+."
            )

    adj_count_var.trace_add("write", on_adj_count_toggled)

    f4 = tk.Frame(e); f4.pack(fill="x", pady=5)
    dim_var = tk.BooleanVar(value=custom.get("show_coords_based_on_dimension", False))
    tk.Label(f4, text="Show Overworld/Nether coords based on dimension", anchor="w").pack(side="left")
    dim_checkbox = tk.Checkbutton(f4, variable=dim_var)
    dim_checkbox.pack(side="left", padx=5)

    f_boat = tk.Frame(e); f_boat.pack(fill="x", pady=5)
    boat_var = tk.BooleanVar(value=custom.get("show_boat_icon", False))
    tk.Label(f_boat, text="Show green/red boat icon", anchor="w").pack(side="left")
    boat_checkbox = tk.Checkbutton(f_boat, variable=boat_var)
    boat_checkbox.pack(side="left", padx=5)

    f_error = tk.Frame(e); f_error.pack(fill="x", pady=5)
    error_var = tk.BooleanVar(value=custom.get("show_error_message", False))
    tk.Label(f_error, text='Show "Could not determine" error', anchor="w").pack(side="left")
    error_checkbox = tk.Checkbutton(f_error, variable=error_var)
    error_checkbox.pack(side="left", padx=5)

    tk.Label(e, text="Text Elements:", font=("Helvetica", 12)).pack(pady=(15, 5), anchor="w")

    order = custom.get("text_order", DEFAULT_CUSTOMIZATIONS["text_order"].copy())
    enabled = custom.get("text_enabled", DEFAULT_CUSTOMIZATIONS["text_enabled"].copy())
    text_frame = tk.Frame(e)
    text_frame.pack(fill="x", padx=10)
    check_vars = {}
    buttons = {}

    def redraw_items():
        for w in text_frame.winfo_children():
            w.destroy()
        buttons.clear()
        en = use_var.get()
        for idx, key in enumerate(order):
            frm = tk.Frame(text_frame)
            frm.pack(fill="x", pady=2)
            name = DISPLAY_NAMES.get(key, key)
            var = check_vars.get(key, tk.BooleanVar(value=enabled.get(key, True)))
            check_vars[key] = var
            tk.Checkbutton(frm, text=name, variable=var,
                           state="normal" if en else "disabled").pack(side="left", padx=(0, 15))

            def mk_left(i=idx):
                return lambda: (swap_positions(order, i, -1), redraw_items(), update_state())

            btnL = tk.Button(frm, text="Move left", width=8, command=mk_left())
            btnL.pack(side="left", padx=5)

            def mk_right(i=idx):
                return lambda: (swap_positions(order, i, 1), redraw_items(), update_state())

            btnR = tk.Button(frm, text="Move right", width=8, command=mk_right())
            btnR.pack(side="left", padx=5)
            buttons[key] = (btnL, btnR)

        _apply_eye_button_states()

    def _apply_eye_button_states():
        en = use_var.get()
        for idx, key in enumerate(order):
            if key not in buttons:
                continue
            btnL, btnR = buttons[key]
            btnL.config(state="normal" if (en and idx > 0) else "disabled")
            btnR.config(state="normal" if (en and idx < len(order) - 1) else "disabled")

    redraw_items()

    b = tk.Frame(tab_blind)
    b.pack(padx=10, pady=10, fill="x")

    f_blind = tk.Frame(b); f_blind.pack(fill="x", pady=(5, 0))
    blind_info_var = tk.BooleanVar(value=custom.get("show_blind_info", True))
    tk.Label(f_blind, text="Show blind information", anchor="w").pack(side="left")
    blind_info_checkbox = tk.Checkbutton(f_blind, variable=blind_info_var, relief="flat", bd=0)
    blind_info_checkbox.pack(side="left", padx=5)

    f_blind_sub = tk.Frame(b); f_blind_sub.pack(fill="x", pady=(0, 5))
    blind_hide_after_enabled_var = tk.BooleanVar(value=custom.get("blind_info_hide_after_enabled", False))
    tk.Label(f_blind_sub, text="    •", anchor="w", fg="#000000").pack(side="left")
    blind_hide_after_check = tk.Checkbutton(f_blind_sub, variable=blind_hide_after_enabled_var)
    blind_hide_after_check.pack(side="left")
    blind_hide_after_label = tk.Label(f_blind_sub, text="Hide after", anchor="w")
    blind_hide_after_label.pack(side="left", padx=(4, 5))
    blind_hide_after_var = tk.IntVar(value=custom.get("blind_info_hide_after", 20))
    blind_hide_spinbox = tk.Spinbox(f_blind_sub, from_=1, to=300, textvariable=blind_hide_after_var, width=5)
    blind_hide_spinbox.pack(side="left", padx=5)
    blind_hide_seconds_label = tk.Label(f_blind_sub, text="seconds", anchor="w")
    blind_hide_seconds_label.pack(side="left")

    adv = tk.Frame(tab_advanced)
    adv.pack(padx=10, pady=10, fill="x")

    f_debug = tk.Frame(adv); f_debug.pack(fill="x", pady=5)
    debug_var = tk.BooleanVar(value=custom.get("debug_mode", DEFAULT_CUSTOMIZATIONS["debug_mode"]))
    tk.Label(f_debug, text="Debug mode", anchor="w").pack(side="left")
    tk.Checkbutton(f_debug, variable=debug_var, relief="flat", bd=0).pack(side="left", padx=5)

    f_idle = tk.Frame(adv); f_idle.pack(fill="x", pady=(5, 0))
    tk.Label(f_idle, text="Idle API polling rate (s)", width=26, anchor="w").pack(side="left")
    idle_rate_var = tk.DoubleVar(value=custom.get("idle_api_polling_rate",
                                                   DEFAULT_CUSTOMIZATIONS["idle_api_polling_rate"]))
    idle_rate_entry = tk.Entry(f_idle, textvariable=idle_rate_var, width=8)
    idle_rate_entry.pack(side="left", padx=5)
    idle_rate_hint = tk.Label(adv, text="  Default 0.3s. Higher value = lower CPU usage when idle.",
                              anchor="w", fg="#666666", font=("Helvetica", 9, "italic"))
    idle_rate_hint.pack(fill="x", pady=(0, 5))

    f_max = tk.Frame(adv); f_max.pack(fill="x", pady=(5, 0))
    tk.Label(f_max, text="Max API polling rate (s)", width=26, anchor="w").pack(side="left")
    max_rate_var = tk.DoubleVar(value=custom.get("max_api_polling_rate",
                                                  DEFAULT_CUSTOMIZATIONS["max_api_polling_rate"]))
    max_rate_entry = tk.Entry(f_max, textvariable=max_rate_var, width=8)
    max_rate_entry.pack(side="left", padx=5)
    max_rate_hint = tk.Label(adv, text="  Default 0.15s. The program will never poll slower than this.",
                             anchor="w", fg="#666666", font=("Helvetica", 9, "italic"))
    max_rate_hint.pack(fill="x", pady=(0, 5))

    def update_blind_hide_after_state(*_):
        blind_on = blind_info_var.get() and use_var.get()
        blind_hide_after_check.config(state="normal" if blind_on else "disabled")
        enabled_sub = blind_hide_after_enabled_var.get() and blind_on
        sub_state = "normal" if enabled_sub else "disabled"
        blind_hide_spinbox.config(state=sub_state)
        blind_hide_after_label.config(state=sub_state)
        blind_hide_seconds_label.config(state=sub_state)

    blind_hide_after_enabled_var.trace_add("write", update_blind_hide_after_state)
    blind_info_var.trace_add("write", update_blind_hide_after_state)

    def update_state(*_):
        en = use_var.get()

        font_state = "readonly" if en else "disabled"
        font_dropdown.config(state=font_state)
        font_size_spinbox.config(state="normal" if en else "disabled")
        color_state = "normal" if en else "disabled"
        bg_entry.config(state=color_state)
        bg_choose_btn.config(state=color_state)
        text_entry.config(state=color_state)
        text_choose_btn.config(state=color_state)

        cb_shown.config(state="readonly" if en else "disabled")
        ang_checkbox.config(state="normal" if en else "disabled")
        adj_count_checkbox.config(state="normal" if en else "disabled")
        dim_checkbox.config(state="normal" if en else "disabled")
        boat_checkbox.config(state="normal" if en else "disabled")
        error_checkbox.config(state="normal" if en else "disabled")
        redraw_items()  

        blind_info_checkbox.config(state="normal" if en else "disabled")
        update_blind_hide_after_state()

        idle_rate_entry.config(state="normal" if en else "disabled")

    use_var.trace_add("write", update_state)
    update_state()
    update_blind_hide_after_state()

    def on_save():
        bg_val = bg_var.get().strip()
        txt_val = text_var.get().strip()
        if not is_valid_hex(bg_val):
            messagebox.showerror("Invalid Color", "Background color must be a hex code like #RRGGBB.")
            return
        if not is_valid_hex(txt_val):
            messagebox.showerror("Invalid Color", "Text color must be a hex code like #RRGGBB.")
            return

        try:
            idle_val = float(idle_rate_var.get())
            if idle_val <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid Value", "Idle API polling rate must be a positive number.")
            return

        try:
            max_val = float(max_rate_var.get())
            if max_val <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid Value", "Max API polling rate must be a positive number.")
            return

        custom.update({
            "use_custom_pinned_image": use_var.get(),
            "shown_measurements": shown_var.get(),
            "show_angle_direction": ang_var.get(),
            "show_angle_adjustment_count": adj_count_var.get(),
            "show_coords_based_on_dimension": dim_var.get(),
            "show_boat_icon": boat_var.get(),
            "show_error_message": error_var.get(),
            "show_blind_info": blind_info_var.get(),
            "blind_info_hide_after": blind_hide_after_var.get(),
            "blind_info_hide_after_enabled": blind_hide_after_enabled_var.get(),
            "font_name": system_fonts.get(font_var.get(), ""),
            "font_size": font_size_var.get(),
            "background_color": bg_val,
            "text_color": txt_val,
            "text_order": order,
            "text_enabled": {k: var.get() for k, var in check_vars.items()},
            "debug_mode": debug_var.get(),
            "idle_api_polling_rate": idle_val,
            "max_api_polling_rate": max_val,
        })
        save_customizations(custom)
        messagebox.showinfo("Settings Saved", "Your settings have been saved successfully.")

    def on_reset():
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset to defaults?"):
            save_customizations(DEFAULT_CUSTOMIZATIONS.copy())
            custom.clear()
            custom.update(DEFAULT_CUSTOMIZATIONS)
            use_var.set(custom["use_custom_pinned_image"])
            shown_var.set(custom["shown_measurements"])
            ang_var.set(custom["show_angle_direction"])
            adj_count_var.set(custom["show_angle_adjustment_count"])
            dim_var.set(custom["show_coords_based_on_dimension"])
            boat_var.set(custom["show_boat_icon"])
            error_var.set(custom["show_error_message"])
            font_var.set(font_path_to_display.get(custom["font_name"], ""))
            font_size_var.set(custom["font_size"])
            blind_info_var.set(custom["show_blind_info"])
            blind_hide_after_var.set(custom["blind_info_hide_after"])
            blind_hide_after_enabled_var.set(custom.get("blind_info_hide_after_enabled", False))
            bg_var.set(custom["background_color"])
            text_var.set(custom["text_color"])
            debug_var.set(custom["debug_mode"])
            idle_rate_var.set(custom["idle_api_polling_rate"])
            max_rate_var.set(custom["max_api_polling_rate"])
            order[:] = custom["text_order"]
            for k, var in check_vars.items():
                var.set(custom["text_enabled"].get(k, True))
            redraw_items()
            update_state()
            update_blind_hide_after_state()
            messagebox.showinfo("Reset Complete", "Settings have been reset to defaults.")

    btn_frame = tk.Frame(root)
    btn_frame.pack(side="bottom", fill="x", pady=10, padx=10)
    tk.Button(btn_frame, text="Save Settings", command=on_save).pack(side="left")
    tk.Button(btn_frame, text="Reset", command=on_reset).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Exit", command=root.destroy).pack(side="right")

    def adjust_window_height():
        root.update_idletasks()
        root.geometry("")  

    root.after(150, adjust_window_height)

    root.mainloop()

if __name__ == "__main__":
    main()
