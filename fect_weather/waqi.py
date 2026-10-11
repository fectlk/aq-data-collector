"""Collect real-time STATION readings from the AQICN / WAQI API (free token).

A single `map/bounds` call returns every monitoring station inside a box around Sri Lanka.
Needs the WAQI_TOKEN environment variable. Non-commercial use; credit the World Air Quality
Index project (terms: https://aqicn.org/api/).
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

import requests

from .collector import TZ, make_session

URL = "https://api.waqi.info/map/bounds/"
BOUNDS = "5.7,79.4,10.0,82.0"  # lat1,lng1,lat2,lng2 - the island of Sri Lanka

FIELDS = ["collected_at", "observed_at", "uid", "station", "lat", "lon", "us_aqi"]


def _observed(station: dict, now: datetime) -> str:
    try:
        return datetime.fromisoformat(station["time"]).astimezone(TZ).strftime("%Y-%m-%dT%H:%M")
    except (KeyError, TypeError, ValueError):
        return now.strftime("%Y-%m-%dT%H:00")


def parse_stations(body: dict, now: datetime) -> list[dict]:
    rows = []
    for s in body.get("data") or []:
        try:
            aqi = round(float(s["aqi"]))  # "-" when the station has no current reading
        except (KeyError, TypeError, ValueError):
            continue
        station = s.get("station") or {}
        rows.append({
            "collected_at": now.isoformat(timespec="seconds"),
            "observed_at": _observed(station, now),
            "uid": s["uid"], "station": station.get("name", f"Station {s['uid']}"),
            "lat": s["lat"], "lon": s["lon"], "us_aqi": aqi,
        })
    return rows


def collect_waqi(data_dir="data/waqi", token=None, session=None) -> int:
    token = token or os.environ.get("WAQI_TOKEN")
    if not token:
        raise RuntimeError("WAQI_TOKEN is not set")
    session = session or make_session()
    now = datetime.now(TZ)
    try:
        body = session.get(URL, params={"latlng": BOUNDS, "token": token}, timeout=30).json()
    except (requests.RequestException, ValueError) as exc:
        print(f"WAQI: {exc}")
        return 0
    if body.get("status") != "ok":
        print(f"WAQI: API said {body.get('status')!r}: {body.get('data')}")
        return 0
    stations = body.get("data") or []

    path = Path(data_dir) / f"{now:%Y-%m}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str]] = set()
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            seen = {(r["uid"], r["observed_at"]) for r in csv.DictReader(f)}
    parsed = parse_stations(body, now)
    print(f"WAQI: {len(stations)} stations in the box, {len(parsed)} with a current reading")
    rows = []
    for row in parsed:
        k = (str(row["uid"]), row["observed_at"])
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
