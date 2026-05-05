"""tkinter GUI.

Network calls run in a background thread so the UI remains responsive.
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

class WeatherApp:
    def __init__(self, default_units: str, default_city: str | None):
        self.client = OpenWeatherMapClient()
        self.root = tk.Tk()
        self.root.title("Weather")
        self.root.geometry("800x600")

        # Initialize the application with a default dark theme background.
        self.root.configure(bg="#242424")

        # Configure native ttk styles to ensure UI elements blend smoothly into the dark theme.
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("TFrame", background="#242424")
        style.configure("TLabel", background="#242424", foreground="#E0E0E0")
        style.configure("Treeview", background="#1E1E1E", fieldbackground="#1E1E1E", foreground="#FFF", rowheight=30)
        style.configure("Treeview.Heading", background="#2C2C2C", foreground="#FFF")

        # Variables connected directly to the tkinter UI components.
        self.city_name = tk.StringVar(value=default_city or "")
        self.unit_choice = tk.StringVar(value=default_units if default_units in ["imperial", "metric"] else "imperial")
        self.loading_text = tk.StringVar(value="")

        self.build_ui()

        # Bind the Enter key
        self.root.bind("<Return>", lambda event: self.fetch_weather())
        if default_city:
            self.fetch_weather()

    def build_ui(self):
        # Constructs the primary layout and layout containers for the weather application.
        main_container = ttk.Frame(self.root, padding=20)
        main_container.pack(fill="both", expand=True)

        # -- Top Bar Section --
        # Contains the search input, submit button, and unit selection toggles.
        top_bar = ttk.Frame(main_container)
        top_bar.pack(fill="x", pady=(0, 20))

        # Input field for the city to search.
        self.city_input = ttk.Entry(top_bar, textvariable=self.city_name, font=("Helvetica", 14), width=30)
        self.city_input.pack(side="left", padx=(0, 10))

        ttk.Button(top_bar, text="Search", command=self.fetch_weather).pack(side="left")

        # Unit selection toggles aligned to the right side of the top bar.
        self.rb_f = tk.Radiobutton(top_bar, text="°F", variable=self.unit_choice, value="imperial", bg="#242424", fg="#FFF", selectcolor="#1E1E1E", command=self.fetch_weather)
        self.rb_f.pack(side="right")
        self.rb_c = tk.Radiobutton(top_bar, text="°C", variable=self.unit_choice, value="metric", bg="#242424", fg="#FFF", selectcolor="#1E1E1E", command=self.fetch_weather)
        self.rb_c.pack(side="right")

        # Loading indicator that displays when network requests are running.
        ttk.Label(main_container, textvariable=self.loading_text, foreground="#7AA6FF").pack(anchor="w")

        # -- Current Weather Section --
        # Displays the current location, main temperature, and other weather conditions.
        self.location_label = tk.Label(main_container, font=("Helvetica", 24, "bold"), bg="#242424", fg="#FFF")
        self.location_label.pack(anchor="w")

        info_wrapper = ttk.Frame(main_container)
        info_wrapper.pack(fill="x", pady=10)

        # Main temperature display.
        self.temp_label = tk.Label(info_wrapper, font=("Helvetica", 56, "bold"), bg="#242424", fg="#FFF")
        self.temp_label.pack(side="left", padx=(0, 20))

        # Supplementary weather details such as conditions, humidity, and wind speed.
        self.details_label = tk.Label(info_wrapper, font=("Helvetica", 14), bg="#242424", fg="#A0A0A0", justify="left")
        self.details_label.pack(side="left")

        # -- Forecast Section --
        # Tabbed interface using a Notebook to alternate between hourly and daily forecasts.
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill="both", expand=True, pady=(20, 0))

        self.hourly_tree = self._make_tree(notebook, "Hourly", ["Time", "Temp", "Status"])
        self.daily_tree = self._make_tree(notebook, "Daily", ["Date", "Min/Max", "Status"])

    def _make_tree(self, parent, title, columns):
        # Utility method to initialize and format a Treeview widget for forecast tables.
        frame = ttk.Frame(parent)
        parent.add(frame, text=title)
        tree = ttk.Treeview(frame, columns=columns, show="headings", style="Treeview")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor="center")
        tree.pack(fill="both", expand=True)
        return tree

    def fetch_weather(self):
        # Initiates a background thread to fetch weather data for the requested city.
        city = self.city_name.get().strip()
        if not city:
            messagebox.showinfo("Input Required", "Please enter a city name first.")
            return

        self.loading_text.set("Fetching latest weather...")
        units = self.unit_choice.get()

        # Execute the API requests in a background thread to keep the main UI responsive.
        def background_fetch():
            try:
                locs = self.client.geocode_city(city)
                if not locs:
                    raise WeatherApiError(f"Could not locate '{city}'.")

                cur, tz_cur = self.client.get_current(locs[0], units=units)
                ent, tz_f = self.client.get_forecast(locs[0], units=units)
                tz_off = tz_f if tz_f is not None else tz_cur

                hourly = ent[:DEFAULT_HOURLY_COUNT]
                daily = self.client.build_daily_summaries(ent, timezone_offset_s=tz_off, days=DEFAULT_DAILY_COUNT)

                # Dispatch UI updates back to the main thread once data is ready.
                self.root.after(0, self.update_ui, cur, hourly, daily, tz_off, units)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)) or self.loading_text.set(""))

        threading.Thread(target=background_fetch, daemon=True).start()

    def update_ui(self, current, hourly, daily, tz_offset, units):
        # Refreshes the user interface components with the retrieved weather data.
        # Map current weather conditions to specific background colors.
        theme_map = {"Clear": "#0C4A6E", "Clouds": "#3F3F46", "Rain": "#1E1B4B", "Snow": "#334155"}
        bg = next((v for k, v in theme_map.items() if k in current.status), "#242424")

        self.root.configure(bg=bg)
        ttk.Style().configure("TFrame", background=bg)
        ttk.Style().configure("TLabel", background=bg)
        for widget in (self.location_label, self.temp_label, self.details_label, self.rb_f, self.rb_c):
            widget.config(bg=bg)
            if isinstance(widget, tk.Radiobutton): widget.config(selectcolor=bg)

        # Update the current weather UI components.
        self.location_label.config(text=current.location_name)
        self.temp_label.config(text=format_temp(current.temperature, units=units))

        details = [current.status]
        if current.feels_like is not None: details.append(f"Feels like {format_temp(current.feels_like, units=units)}")
        if current.humidity is not None: details.append(f"Humidity: {current.humidity}%")
        if current.wind_speed is not None: details.append(f"Wind: {current.wind_speed:.0f}")
        self.details_label.config(text="\\n".join(details))

        # Clear existing data from the forecast tables.
        for item in self.hourly_tree.get_children(): self.hourly_tree.delete(item)
        for item in self.daily_tree.get_children(): self.daily_tree.delete(item)

        # Populate the forecast tables with the newly fetched data.
        for h in hourly:
            self.hourly_tree.insert("", "end", values=(format_local_time(h, timezone_offset_s=tz_offset), format_temp(h.temperature, units=units), h.status))

        for d in daily:
            self.daily_tree.insert("", "end", values=(d.date_local, f"{format_temp(d.temp_min, units=units)} / {format_temp(d.temp_max, units=units)}", d.status))

        self.loading_text.set("")
