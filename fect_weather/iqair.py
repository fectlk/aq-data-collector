"""Collect real-time readings from the IQAir (AirVisual) API - free Community plan.

The Community plan has CITY-level data only (the station endpoints need a paid plan). We
call `nearest_city` with each configured location; IQAir answers with the nearest city it
monitors, so several of our cities can map to the same IQAir city (stored once).

Needs the IQAIR_API_KEY environment variable. Limits: 5 calls/min, 500/day, 10,000/month,
so we make one call every ~13 s (28 cities = about 6 minutes per run).
"""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from pathlib import Path

import requests

from .collector import TZ, load_cities, make_session

URL = "https://api.airvisual.com/v2/nearest_city"
DELAY = 13.0

FIELDS = ["collected_at", "observed_at", "province", "query_city", "iq_city", "iq_state",
          "lat", "lon", "us_aqi", "main_pollutant", "temp_c", "humidity", "wind_ms",
          "pressure_hpa"]


def _local(ts: str) -> str:
    """'2026-10-10T09:00:00.000Z' -> '2026-10-10T14:30' (Sri Lanka time)."""
    dt = datetime.fromisoformat(ts).astimezone(TZ)
    return dt.strftime("%Y-%m-%dT%H:%M")


def parse_city(payload: dict, city: dict, now: datetime) -> dict | None:
    """Turn one nearest_city response into a CSV row (None if it has no pollution data)."""
    data = payload.get("data") or {}
    cur = data.get("current") or {}
    pol, wea = cur.get("pollution") or {}, cur.get("weather") or {}
    if "aqius" not in pol or "ts" not in pol:
        return None
    lon, lat = data["location"]["coordinates"][:2]
    return {
        "collected_at": now.isoformat(timespec="seconds"),
        "observed_at": _local(pol["ts"]),
        "province": city["province"],
        "query_city": city["city"],
        "iq_city": data.get("city", ""),
        "iq_state": data.get("state", ""),
        "lat": lat, "lon": lon,
        "us_aqi": pol["aqius"],
        "main_pollutant": pol.get("mainus"),
        "temp_c": wea.get("tp"),
        "humidity": wea.get("hu"),
        "wind_ms": wea.get("ws"),
        "pressure_hpa": wea.get("pr"),
    }


def _existing_keys(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["iq_city"], r["iq_state"], r["observed_at"]) for r in csv.DictReader(f)}


def _fetch(session, city: dict, key: str) -> dict | None:
    """One API call. Waits and retries once if the per-minute limit is hit."""
    params = {"lat": city["lat"], "lon": city["lon"], "key": key}
    for attempt in (1, 2):
        resp = session.get(URL, params=params, timeout=30)
        body = resp.json()
        if body.get("status") == "success":
            return body
        reason = (body.get("data") or {}).get("message", body.get("status"))
        if reason in ("call_limit_reached", "too_many_requests") and attempt == 1:
            time.sleep(65)
            continue
        print(f"IQAir: {city['city']}: {reason}")
        return None
    return None


def collect_iqair(cities_path="config/cities.csv", data_dir="data/iqair", api_key=None,
                  session=None, delay: float = DELAY) -> int:
    """Fetch IQAir data for all cities and append new rows. Returns rows written."""
    key = api_key or os.environ.get("IQAIR_API_KEY")
    if not key:
        raise RuntimeError("IQAIR_API_KEY is not set")
    session = session or make_session()
    cities = load_cities(cities_path)
    now = datetime.now(TZ)
    path = Path(data_dir) / f"{now:%Y-%m}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = _existing_keys(path)

    rows = []
    for i, city in enumerate(cities):
        if i and delay:
            time.sleep(delay)
        try:
            body = _fetch(session, city, key)
        except (requests.RequestException, ValueError) as exc:  # skip this city, keep going
            print(f"IQAir: {city['city']}: {exc}")
            continue
        row = parse_city(body, city, now) if body else None
        if not row:
            continue
        k = (row["iq_city"], row["iq_state"], row["observed_at"])
        if k in seen:  # same IQAir city already stored for this hour
            continue
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
