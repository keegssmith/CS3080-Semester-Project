# Weather App (Python)

A simple weather app using the OpenWeatherMap API.

- CLI
- `tkinter` GUI
- Current conditions + 5-day/3-hour forecast (used for “hourly” and daily summary)

## Setup

1. Create an OpenWeatherMap API key.
2. Export it as an environment variable:

```bash
export OPENWEATHER_API_KEY="YOUR_KEY_HERE"
```

3. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Run (CLI)

```bash
python main.py --city "Salt Lake City"
```

Units:

```bash
python main.py --city "Salt Lake City" --units metric
python main.py --city "Salt Lake City" --units imperial
```

If you omit `--city`, it will prompt you.

## Run (GUI)

```bash
python main.py --gui
```

## Notes

- “Hourly” is shown as **3-hour blocks** because the free OpenWeatherMap forecast endpoint returns 3-hour intervals.
- “Daily” is derived by grouping those 3-hour blocks per day and computing min/max + dominant condition.
