"""tkinter GUI.

- Network calls run in a background thread so the UI remains responsive.
- "Hourly" uses the 3-hour forecast blocks from OpenWeatherMap's free endpoint.
"""

from __future__ import annotations
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .config import DEFAULT_DAILY_COUNT, DEFAULT_HOURLY_COUNT, ConfigError
from .formatting import format_local_time, format_temp
from .owm_client import OpenWeatherMapClient, WeatherApiError


def run_gui(*, default_units: str = "imperial", default_city: str | None = None) -> None:
    app = WeatherApp(default_units=default_units, default_city=default_city)
    app.root.mainloop()


class _GlassCard(tk.Canvas):
    def __init__(self, master, *, bg, card_bg, border, radius=18, padding=16):
        super().__init__(master, highlightthickness=0, bd=0, bg=bg)
        self._card_bg = card_bg
        self._border = border
        self._radius = radius
        self._pad = padding
        self._container = tk.Frame(self, bg=card_bg)
        self._card_id = self._border_id = self._shine_id = None
        self._window_id = self.create_window(0, 0, anchor="nw", window=self._container)
        self.bind("<Configure>", lambda _e: self._redraw())

    @property
    def body(self):
        return self._container

    def _rounded_rect_points(self, x1, y1, x2, y2, r):
        r = max(2, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
        return [
            x1+r, y1,   x2-r, y1,   x2,  y1,   # top
            x2,  y1+r,  x2,  y2-r,  x2,  y2,   # right
            x2-r, y2,   x1+r, y2,   x1,  y2,   # bottom
            x1,  y2-r,  x1,  y1+r,  x1,  y1,   # left
        ]

    def _redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        pad = self._pad
        x1, y1 = pad, pad
        x2, y2 = w - pad, h - pad
        r = self._radius
        pts = self._rounded_rect_points(x1, y1, x2, y2, r)
        if self._card_id is None:
            self._card_id   = self.create_polygon(pts, smooth=True, fill=self._card_bg, outline="")
            self._border_id = self.create_polygon(pts, smooth=True, fill="", outline=self._border, width=1)
            self._shine_id  = self.create_line(x1+r, y1+2, x2-r, y1+2, fill=self._border, width=2, capstyle="round")
        else:
            self.coords(self._card_id, *pts)
            self.coords(self._border_id, *pts)
            self.coords(self._shine_id, x1+r, y1+2, x2-r, y1+2)
        inner_w = max(0, (x2 - x1) - (pad * 2))
        inner_h = max(0, (y2 - y1) - (pad * 2))
        self.itemconfigure(self._window_id, width=inner_w, height=inner_h)
        self.coords(self._window_id, x1 + pad, y1 + pad)


class WeatherApp:
    def __init__(self, *, default_units: str, default_city: str | None) -> None:
        self.client = OpenWeatherMapClient()
        self.root = tk.Tk()
        self.root.title("Weather")
        self.root.minsize(720, 520)
        self.root.geometry("820x600")

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.colors = {
            "bg":     "#070B14",
            "bg2":    "#0A1020",
            "glass":  "#0F1A33",
            "glass2": "#111F3D",
            "border": "#2A3B66",
            "text":   "#EAF0FF",
            "muted":  "#A9B6D6",
            "accent": "#7AA6FF",
            "accent2":"#9FE7FF",
        }

        self.root.configure(bg=self.colors["bg"])

        self.font_title = ("Helvetica", 18, "bold")
        self.font_temp  = ("Helvetica", 48, "bold")
        self.font_body  = ("Helvetica", 12)
        self.font_muted = ("Helvetica", 11)

        self._apply_styles(style)

        self.units_var   = tk.StringVar(value=default_units if default_units in ("imperial", "metric") else "imperial")
        self.city_var    = tk.StringVar(value=(default_city or ""))
        self.loading_var = tk.StringVar(value="")

        self._build_layout()

        self.root.bind("<Return>", lambda _e: self.search())
        self._ensure_visible_on_startup()
        if default_city:
            self.search()

    def _ensure_visible_on_startup(self) -> None:
        # the window can start hidden behind other windows; bring it forward after the loop starts.
        def _show():
            try:
                self.root.update_idletasks()
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
                self.root.attributes("-topmost", True)
                self.root.after(100, lambda: self.root.attributes("-topmost", False))
            except tk.TclError:
                pass
        self.root.after(0, _show)

    def _apply_styles(self, style: ttk.Style) -> None:
        c = self.colors
        style.configure("TFrame",            background=c["bg"])
        style.configure("TLabel",            background=c["bg"],    foreground=c["text"])
        style.configure("Muted.TLabel",      background=c["bg"],    foreground=c["muted"])
        style.configure("Glass.TLabel",      background=c["glass"], foreground=c["text"])
        style.configure("GlassMuted.TLabel", background=c["glass"], foreground=c["muted"])

        style.configure(
            "Glass.TButton",
            background=c["glass"], foreground=c["text"],
            bordercolor=c["border"], focusthickness=0, padding=(14, 10),
        )
        style.map("Glass.TButton", background=[("active", c["glass2"])])

        style.configure(
            "Glass.TEntry",
            fieldbackground=c["glass"], background=c["glass"],
            foreground=c["text"], insertcolor=c["text"],
            bordercolor=c["border"], padding=(14, 8),
        )

        # Use tk.Radiobutton for the unit toggle — ttk themes can override colors on macOS.

        style.configure(
            "Glass.Treeview",
            background=c["glass"], fieldbackground=c["glass"],
            foreground=c["text"], bordercolor=c["border"], rowheight=30,
        )
        style.configure(
            "Glass.Treeview.Heading",
            background=c["bg2"], foreground=c["muted"], relief="flat",
        )
        style.map(
            "Glass.Treeview.Heading",
            background=[("active", c["bg2"]), ("pressed", c["bg2"])],
            foreground=[("active", c["muted"]), ("pressed", c["muted"])],
        )
        style.map(
            "Glass.Treeview",
            background=[("selected", c["glass2"])],
            foreground=[("selected", c["text"])],
        )

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        # Single glass surface for the whole page.
        page = _GlassCard(outer, bg=self.colors["bg"], card_bg=self.colors["glass"],
                          border=self.colors["border"], radius=26, padding=16)
        page.pack(fill="both", expand=True)

        content = tk.Frame(page.body, bg=self.colors["glass"])
        content.pack(fill="both", expand=True)
        content.grid_columnconfigure(0, weight=1)

        # ── Search bar ──────────────────────────────────────────────────────────
        top = tk.Frame(content, bg=self.colors["glass"])
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        self.city_entry = ttk.Entry(top, textvariable=self.city_var, style="Glass.TEntry")
        self.city_entry.configure(font=("Helvetica", 13))  # prevents vertical clipping on some Tk builds
        self.city_entry.grid(row=0, column=0, sticky="ew", padx=(0, 12), ipady=6)
        self.city_entry.focus_set()

        ttk.Button(top, text="Search", command=self.search, style="Glass.TButton").grid(row=0, column=1, sticky="e")

        # tk.Radiobutton gives reliable color control; ttk can override on macOS.
        units_frame = tk.Frame(top, bg=self.colors["glass"])
        units_frame.grid(row=0, column=2, sticky="e", padx=(14, 0))
        rb_kw = {
            "bg": self.colors["glass"], "fg": self.colors["muted"],
            "activebackground": self.colors["glass"], "activeforeground": self.colors["muted"],
            "selectcolor": self.colors["glass"], "highlightthickness": 0,
            "bd": 0, "font": ("Helvetica", 12),
        }
        tk.Radiobutton(units_frame, text="°F", value="imperial", variable=self.units_var,
                       command=self._on_units_change, **rb_kw).pack(side="left")
        tk.Radiobutton(units_frame, text="°C", value="metric",   variable=self.units_var,
                       command=self._on_units_change, **rb_kw).pack(side="left", padx=(8, 0))

        self.loading_label = ttk.Label(content, textvariable=self.loading_var,
                                       font=self.font_muted, style="GlassMuted.TLabel")
        self.loading_label.grid(row=1, column=0, sticky="w", pady=(10, 0))

        # ── Current conditions ──────────────────────────────────────────────────
        self.now_section = tk.Frame(content, bg=self.colors["glass"])
        self.now_section.grid(row=2, column=0, sticky="ew", pady=(14, 14))
        self.now_section.grid_columnconfigure(0, weight=1)

        self.location_label = tk.Label(self.now_section, text="", font=self.font_title,
                                       bg=self.colors["glass"], fg=self.colors["text"])
        self.location_label.grid(row=0, column=0, sticky="w")

        self.now_row = tk.Frame(self.now_section, bg=self.colors["glass"])
        self.now_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.now_row.grid_columnconfigure(0, weight=0)
        self.now_row.grid_columnconfigure(1, weight=1)

        self.temp_label = tk.Label(self.now_row, text="", font=self.font_temp,
                                   bg=self.colors["glass"], fg=self.colors["text"])
        self.temp_label.grid(row=0, column=0, sticky="w")

        self.now_right = tk.Frame(self.now_row, bg=self.colors["glass"])
        self.now_right.grid(row=0, column=1, sticky="w", padx=(18, 0))

        self.status_label = tk.Label(self.now_right, text="", font=self.font_body,
                                     bg=self.colors["glass"], fg=self.colors["text"])
        self.status_label.grid(row=0, column=0, sticky="w")

        self.details_label = tk.Label(self.now_right, text="", font=self.font_muted,
                                      bg=self.colors["glass"], fg=self.colors["muted"])
        self.details_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ── Forecast section ────────────────────────────────────────────────────
        # Fixed height keeps the layout stable when switching Hourly / Daily tabs.
        self.forecast_section = tk.Frame(content, bg=self.colors["glass"])
        self.forecast_section.grid(row=3, column=0, sticky="nsew")
        content.grid_rowconfigure(3, weight=1)
        self.forecast_section.grid_propagate(False)
        self.forecast_section.configure(height=360)
        self.forecast_section.grid_rowconfigure(1, weight=1)
        self.forecast_section.grid_columnconfigure(0, weight=1)

        # Custom segmented control — more reliable than ttk.Notebook on macOS Tk.
        self.forecast_view = tk.StringVar(value="hourly")
        seg = tk.Frame(self.forecast_section, bg=self.colors["glass"])
        seg.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))
        seg.grid_columnconfigure(0, weight=1)

        self.seg_shell = tk.Frame(seg, bg=self.colors["border"])
        self.seg_shell.pack(side="left")
        self.seg_body = tk.Frame(self.seg_shell, bg=self.colors["bg2"])
        self.seg_body.pack(padx=1, pady=1)

        self.hourly_btn = tk.Label(self.seg_body, text="Hourly",
                                   bd=0, highlightthickness=0, padx=14, pady=8, font=("Helvetica", 12, "bold"))
        self.daily_btn  = tk.Label(self.seg_body, text="Daily",
                                   bd=0, highlightthickness=0, padx=14, pady=8, font=("Helvetica", 12, "bold"))
        self.hourly_btn.pack(side="left")
        self.daily_btn.pack(side="left")
        self.hourly_btn.bind("<Button-1>", lambda _e: self._set_forecast_view("hourly"))
        self.daily_btn.bind("<Button-1>",  lambda _e: self._set_forecast_view("daily"))

        self.view_stack = tk.Frame(self.forecast_section, bg=self.colors["glass"])
        self.view_stack.grid(row=1, column=0, sticky="nsew")
        self.view_stack.grid_rowconfigure(0, weight=1)
        self.view_stack.grid_columnconfigure(0, weight=1)

        self.hourly_frame = tk.Frame(self.view_stack, bg=self.colors["glass"])
        self.daily_frame  = tk.Frame(self.view_stack, bg=self.colors["glass"])
        for frame in (self.hourly_frame, self.daily_frame):
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_propagate(False)

        pad = 10
        hourly_inner = tk.Frame(self.hourly_frame, bg=self.colors["glass"])
        hourly_inner.pack(fill="both", expand=True, padx=pad, pady=pad)
        daily_inner = tk.Frame(self.daily_frame, bg=self.colors["glass"])
        daily_inner.pack(fill="both", expand=True, padx=pad, pady=pad)

        self.hourly_tree = ttk.Treeview(hourly_inner, columns=("time", "temp", "status"),
                                        show="headings", height=12, style="Glass.Treeview")
        self.hourly_tree.heading("time",   text="Time",   anchor="center")
        self.hourly_tree.heading("temp",   text="Temp",   anchor="center")
        self.hourly_tree.heading("status", text="Status", anchor="center")
        for col in ("time", "temp", "status"):
            self.hourly_tree.column(col, anchor="center", stretch=True, minwidth=80, width=180)
        self.hourly_tree.pack(fill="both", expand=True)
        self._bind_equal_columns(self.hourly_tree, ("time", "temp", "status"))

        self.daily_tree = ttk.Treeview(daily_inner, columns=("date", "range", "status"),
                                       show="headings", height=12, style="Glass.Treeview")
        self.daily_tree.heading("date",   text="Date",    anchor="center")
        self.daily_tree.heading("range",  text="Min/Max", anchor="center")
        self.daily_tree.heading("status", text="Status",  anchor="center")
        for col in ("date", "range", "status"):
            self.daily_tree.column(col, anchor="center", stretch=True, minwidth=80, width=180)
        self.daily_tree.pack(fill="both", expand=True)
        self._bind_equal_columns(self.daily_tree, ("date", "range", "status"))

        self._set_forecast_view("hourly")
        self._set_now_placeholder()

    def _bind_equal_columns(self, tree: ttk.Treeview, columns: tuple[str, ...]) -> None:
        def on_resize(_e):
            w = tree.winfo_width()
            if w <= 20:
                return
            each = max(80, int(w / len(columns)) - 2)
            for col in columns:
                tree.column(col, width=each)
        tree.bind("<Configure>", on_resize, add=True)

    def _set_now_placeholder(self) -> None:
        self.location_label.config(text="Search for a city", fg=self.colors["muted"])
        self.temp_label.config(text="")
        self.status_label.config(text="")
        self.details_label.config(text="")
        self.now_right.grid_remove()

    def _set_forecast_view(self, view: str) -> None:
        view = "daily" if view == "daily" else "hourly"
        self.forecast_view.set(view)

        for btn, name in ((self.hourly_btn, "hourly"), (self.daily_btn, "daily")):
            selected = view == name
            btn.configure(
                bg=self.colors["glass2" if selected else "bg2"],
                fg=self.colors["text"   if selected else "muted"],
                cursor="arrow",
            )

        (self.daily_frame if view == "daily" else self.hourly_frame).tkraise()

    def _on_units_change(self) -> None:
        if self.city_var.get().strip():
            self.search()

    def set_loading(self, text: str) -> None:
        self.loading_var.set(text)
        try:
            self.loading_label.configure(foreground=self.colors["accent"] if text else self.colors["muted"])
        except tk.TclError:
            pass

    def search(self) -> None:
        city = self.city_var.get().strip()
        if not city:
            messagebox.showinfo("Weather", "Enter a city name.")
            return

        self.set_loading("Loading…")
        self._set_enabled(False)
        units = self.units_var.get()

        def worker():
            try:
                locs = self.client.geocode_city(city)
                if not locs:
                    raise WeatherApiError(f"No matches found for '{city}'.")
                loc = locs[0]

                current, tz_current  = self.client.get_current(loc, units=units)
                entries,  tz_forecast = self.client.get_forecast(loc, units=units)
                tz_offset = tz_forecast if tz_forecast is not None else tz_current

                hourly = entries[:DEFAULT_HOURLY_COUNT]
                daily  = self.client.build_daily_summaries(entries, timezone_offset_s=tz_offset, days=DEFAULT_DAILY_COUNT)

                self.root.after(0, lambda: self._render(current, hourly, daily, tz_offset, units))
            except (ConfigError, WeatherApiError) as exc:
                msg = str(exc)
                self.root.after(0, lambda m=msg: self._show_error(m))
            except Exception as exc:
                msg = f"Unexpected error: {exc}"
                self.root.after(0, lambda m=msg: self._show_error(m))

        threading.Thread(target=worker, daemon=True).start()

    def _render(self, current, hourly, daily, tz_offset: int, units: str) -> None:
        self.location_label.config(text=current.location_name, fg=self.colors["text"])
        self.temp_label.config(text=format_temp(current.temperature, units=units))
        self.status_label.config(text=current.status)

        details = []
        if current.feels_like is not None:
            details.append(f"Feels like {format_temp(current.feels_like, units=units)}")
        if current.humidity is not None:
            details.append(f"Humidity {current.humidity}%")
        if current.wind_speed is not None:
            details.append(f"Wind {current.wind_speed:.0f}")
        self.details_label.config(text=" • ".join(details))

        if self.status_label.cget("text") or self.details_label.cget("text"):
            self.now_right.grid()
        else:
            self.now_right.grid_remove()

        for tree in (self.hourly_tree, self.daily_tree):
            tree.delete(*tree.get_children())

        for e in hourly:
            self.hourly_tree.insert("", "end", values=(
                format_local_time(e, timezone_offset_s=tz_offset),
                format_temp(e.temperature, units=units),
                e.status,
            ))

        for d in daily:
            self.daily_tree.insert("", "end", values=(
                d.date_local,
                f"{format_temp(d.temp_min, units=units)} / {format_temp(d.temp_max, units=units)}",
                d.status,
            ))

        self.set_loading("")
        self._set_enabled(True)

    def _show_error(self, msg: str) -> None:
        self.set_loading("")
        self._set_enabled(True)
        messagebox.showerror("Weather", msg)

    def _set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        def apply(widget):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
            for child in widget.winfo_children():
                apply(child)
        for child in self.root.winfo_children():
            apply(child)
