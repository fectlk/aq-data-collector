"""Collect real-time air pollution readings from the OpenWeather Air Pollution API (free).

One call per city in config/cities.csv (limit: 60/min). OpenWeather returns modelled
concentrations and its own 1-5 index; we also compute a US AQI from PM2.5 and PM10 so the
map uses the same colours as the others.

Needs the OPENWEATHER_API_KEY environment variable (new keys can take up to ~2 h to activate).
"""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from pathlib import Path

import requests

from .aqi import us_aqi
from .collector import TZ, load_cities, make_session

URL = "https://api.openweathermap.org/data/2.5/air_pollution"

FIELDS = ["collected_at", "observed_at", "province", "city", "lat", "lon", "us_aqi",
          "owm_aqi", "pm2_5", "pm10", "o3", "no2", "so2", "co"]


def parse_item(item: dict, city: dict, now: datetime) -> dict | None:
    comp = item.get("components") or {}
    aqi = us_aqi(comp.get("pm2_5"), comp.get("pm10"))
    if aqi is None:
        return None
    return {
        "collected_at": now.isoformat(timespec="seconds"),
        "observed_at": datetime.fromtimestamp(item["dt"], TZ).strftime("%Y-%m-%dT%H:%M"),
        "province": city["province"], "city": city["city"],
        "lat": city["lat"], "lon": city["lon"],
        "us_aqi": aqi,
        "owm_aqi": (item.get("main") or {}).get("aqi"),
        "pm2_5": comp.get("pm2_5"), "pm10": comp.get("pm10"), "o3": comp.get("o3"),
        "no2": comp.get("no2"), "so2": comp.get("so2"), "co": comp.get("co"),
    }


def collect_openweather(cities_path="config/cities.csv", data_dir="data/openweather",
                        api_key=None, session=None, delay: float = 1.1) -> int:
    key = api_key or os.environ.get("OPENWEATHER_API_KEY")
    if not key:
        raise RuntimeError("OPENWEATHER_API_KEY is not set")
    session = session or make_session()
    now = datetime.now(TZ)
    path = Path(data_dir) / f"{now:%Y-%m}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str]] = set()
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            seen = {(r["city"], r["observed_at"]) for r in csv.DictReader(f)}

    rows = []
    for i, city in enumerate(load_cities(cities_path)):
        if i and delay:
            time.sleep(delay)
        try:
            body = session.get(URL, params={"lat": city["lat"], "lon": city["lon"],
                                            "appid": key}, timeout=30).json()
        except (requests.RequestException, ValueError) as exc:
            print(f"OpenWeather: {city['city']}: {exc}")
            continue
        if str(body.get("cod")) == "401":
            print(f"OpenWeather: {body.get('message')} (new keys can take ~2 h to activate)")
            break
        items = body.get("list") or []
        row = parse_item(items[0], city, now) if items else None
        if not row:
            print(f"OpenWeather: {city['city']}: no data ({body.get('message', '')})")
            continue
        k = (row["city"], row["observed_at"])
        if k not in seen:
            seen.add(k)
            rows.append(row)

    if rows:
        new_file = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerows(rows)
    return len(rows)
