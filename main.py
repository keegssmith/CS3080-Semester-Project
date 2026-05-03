"""Project entrypoint.

Parses arguments and dispatches to either the CLI or the tkinter GUI.
"""

from __future__ import annotations
import argparse
from weather_app.cli import run_cli
from weather_app.gui import run_gui


def main() -> None:
    parser = argparse.ArgumentParser(description="Weather app (OpenWeatherMap).")
    parser.add_argument("--city", type=str, default=None, help="City name (e.g. 'Salt Lake City').")
    parser.add_argument(
        "--units",
        type=str,
        choices=["imperial", "metric"],
        default="imperial",
        help="Units for API results.",
    )
    parser.add_argument("--gui", action="store_true", help="Launch tkinter GUI.")
    args = parser.parse_args()

    if args.gui:
        run_gui(default_units=args.units, default_city=args.city)
        return

    run_cli(city=args.city, units=args.units)


if __name__ == "__main__":
    main()
