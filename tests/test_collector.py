import csv
from datetime import date

from fect_weather import collector
from fect_weather.aqi import category
from fect_weather.mapper import build_map
from fect_weather.report import weekly_report


def test_category():
    assert category(40)[0] == "Good"
    assert category(120)[0] == "Unhealthy for sensitive groups"
    assert category(999)[0] == "Hazardous"


def _fake_fetch(session, url, cities, variables):
    if url == collector.AIR_URL:
        return [{"time": "2026-09-28T10:00", "us_aqi": 60, "pm2_5": 18.0} for _ in cities]
    return [{"temperature_2m": 30.1} for _ in cities]


def test_collect_dedupes(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "fetch_current", _fake_fetch)
    cities = tmp_path / "cities.csv"
    cities.write_text("province,city,lat,lon\nWestern,Colombo,6.9,79.8\n")
    data = tmp_path / "data"

    assert collector.collect(cities, data, session=object()) == 1
    assert collector.collect(cities, data, session=object()) == 0  # same observation

    files = list(data.glob("*.csv"))
    assert len(files) == 1
    with open(files[0], encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["city"] == "Colombo" and rows[0]["us_aqi"] == "60"


def test_map_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "fetch_current", _fake_fetch)
    cities = tmp_path / "cities.csv"
    cities.write_text("province,city,lat,lon\nWestern,Colombo,6.9,79.8\n")
    data = tmp_path / "data"
    collector.collect(cities, data, session=object())

    assert build_map(data, tmp_path / "docs" / "index.html").exists()
    # 2026-09-28 is a Monday; "today" = following Monday -> that week is reported
    out = weekly_report(data, tmp_path / "reports", today=date(2026, 10, 5))
    assert out is not None and out.exists()
