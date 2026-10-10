"""Collect real-time CITY readings from the IQAir (AirVisual) API - free Community plan.

The free plan has city-level data only (station endpoints need a paid plan). IQAir's own list
of monitored Sri Lankan cities is discovered once (`states` + `cities` endpoints) and saved to
config/iqair_cities.csv; every run then calls `city` for each of them. If discovery fails we
fall back to `nearest_city` for each location in config/cities.csv.

Needs the IQAIR_API_KEY environment variable. Limits: 5 calls/min, 500/day, 10,000/month,
so we make one call every ~13 s.
"""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from pathlib import Path

import requests

from .collector import TZ, load_cities, make_session

BASE = "https://api.airvisual.com/v2/"
COUNTRY = "Sri Lanka"
CITIES_FILE = "config/iqair_cities.csv"
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


def _call(session, endpoint: str, params: dict, key: str, label: str = "") -> dict | None:
    """One API call. Waits and retries once if the per-minute limit is hit."""
    params = {**params, "key": key}
    for attempt in (1, 2):
        body = session.get(BASE + endpoint, params=params, timeout=30).json()
        if body.get("status") == "success":
            return body
        reason = (body.get("data") or {}).get("message", body.get("status"))
        if reason in ("call_limit_reached", "too_many_requests") and attempt == 1:
            time.sleep(65)
            continue
        print(f"IQAir {endpoint} {label}: {reason}")
        return None
    return None


def discover_cities(session, key: str, path: str | Path = CITIES_FILE,
                    delay: float = DELAY) -> list[dict]:
    """Ask IQAir which Sri Lankan cities it monitors and save them to `path`."""
    body = _call(session, "states", {"country": COUNTRY}, key)
    states = [d["state"] for d in (body or {}).get("data", [])]
    found: list[dict] = []
    complete = bool(states)
    for state in states:
        time.sleep(delay)
        body = _call(session, "cities", {"state": state, "country": COUNTRY}, key, state)
        complete = complete and body is not None
        found += [{"state": state, "city": d["city"]} for d in (body or {}).get("data", [])]
    if found and complete:  # only cache a full list, otherwise try again next run
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["state", "city"])
            writer.writeheader()
            writer.writerows(found)
    return found


def _targets(session, key, cities_path, iqair_cities, delay) -> list[dict]:
    """[{'endpoint', 'params', 'province', 'city'}] - one API call each."""
    path = Path(iqair_cities)
    found: list[dict] = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            found = list(csv.DictReader(f))
    else:
        try:
            found = discover_cities(session, key, path, delay)
        except (requests.RequestException, ValueError) as exc:
            print(f"IQAir discovery failed: {exc}")
        if found:
            time.sleep(delay)
    if found:
        return [{"endpoint": "city", "province": c["state"], "city": c["city"],
                 "params": {"city": c["city"], "state": c["state"], "country": COUNTRY}}
                for c in found]
    return [{"endpoint": "nearest_city", "province": c["province"], "city": c["city"],
             "params": {"lat": c["lat"], "lon": c["lon"]}} for c in load_cities(cities_path)]


def collect_iqair(cities_path="config/cities.csv", data_dir="data/iqair", api_key=None,
                  session=None, delay: float = DELAY, iqair_cities=CITIES_FILE) -> int:
    """Fetch IQAir data for all cities and append new rows. Returns rows written."""
    key = api_key or os.environ.get("IQAIR_API_KEY")
    if not key:
        raise RuntimeError("IQAIR_API_KEY is not set")
    session = session or make_session()
    targets = _targets(session, key, cities_path, iqair_cities, delay)
    now = datetime.now(TZ)
    path = Path(data_dir) / f"{now:%Y-%m}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = _existing_keys(path)

    rows = []
    for i, t in enumerate(targets):
        if i and delay:
            time.sleep(delay)
        try:
            body = _call(session, t["endpoint"], t["params"], key, t["city"])
        except (requests.RequestException, ValueError) as exc:  # skip this city, keep going
            print(f"IQAir: {t['city']}: {exc}")
            continue
        row = parse_city(body, t, now) if body else None
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
