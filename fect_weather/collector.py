"""Collect current air quality + weather for all configured cities.

Uses Open-Meteo (no API key). All cities are requested in ONE call per
dataset, so each run makes only 2 HTTP requests.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TZ = ZoneInfo("Asia/Colombo")
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "FECT-AQI-Collector/2.0 (+https://github.com/fectlk/iqair-data-scraper)"
CHUNK = 50  # max locations per request

AIR_VARS = ["us_aqi", "pm2_5", "pm10", "ozone",
            "nitrogen_dioxide", "sulphur_dioxide", "carbon_monoxide"]
WEATHER_VARS = ["temperature_2m", "relative_humidity_2m", "precipitation",
                "wind_speed_10m", "weather_code"]

FIELDS = ["collected_at", "observed_at", "province", "city", "lat", "lon",
          *AIR_VARS, *WEATHER_VARS]


def load_cities(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            {"province": r["province"], "city": r["city"],
             "lat": float(r["lat"]), "lon": float(r["lon"])}
            for r in csv.DictReader(f)
        ]


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=3,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = USER_AGENT
    return s


def fetch_current(session, url: str, cities: list[dict], variables: list[str]) -> list[dict]:
    """Return one `current` dict per city, in the same order as `cities`."""
    out: list[dict] = []
    for i in range(0, len(cities), CHUNK):
        chunk = cities[i:i + CHUNK]
        params = {
            "latitude": ",".join(str(c["lat"]) for c in chunk),
            "longitude": ",".join(str(c["lon"]) for c in chunk),
            "current": ",".join(variables),
            "timezone": "Asia/Colombo",
        }
        resp = session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):  # single location -> dict, not list
            data = [data]
        if len(data) != len(chunk):
            raise ValueError(f"Expected {len(chunk)} results, got {len(data)}")
        out.extend(d.get("current", {}) for d in data)
    return out


def _existing_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["city"], r["observed_at"]) for r in csv.DictReader(f)}


def collect(cities_path: str | Path = "config/cities.csv",
            data_dir: str | Path = "data", session=None) -> int:
    """Fetch and append new rows to data/YYYY-MM.csv. Returns rows written."""
    session = session or make_session()
    cities = load_cities(cities_path)
    air = fetch_current(session, AIR_URL, cities, AIR_VARS)
    try:
        weather = fetch_current(session, WEATHER_URL, cities, WEATHER_VARS)
    except requests.RequestException as exc:  # weather is secondary: keep the air data
        print(f"Weather request failed ({type(exc).__name__}); saving air quality only")
        weather = [{} for _ in cities]

    now = datetime.now(TZ)
    path = Path(data_dir) / f"{now:%Y-%m}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = _existing_keys(path)

    rows = []
    for city, a, w in zip(cities, air, weather):
        observed = a.get("time", "")
        if (city["city"], observed) in seen:
            continue  # already stored -> no duplicates
        rows.append({
            "collected_at": now.isoformat(timespec="seconds"),
            "observed_at": observed,
            **{k: city[k] for k in ("province", "city", "lat", "lon")},
            **{k: a.get(k) for k in AIR_VARS},
            **{k: w.get(k) for k in WEATHER_VARS},
        })

    if rows:
        new_file = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerows(rows)
    return len(rows)
