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


def test_prune_keeps_only_last_week(tmp_path):
    from fect_weather.retention import prune

    data = tmp_path / "data"
    data.mkdir()
    head = ",".join(collector.FIELDS)

    def row(day):
        vals = {k: "" for k in collector.FIELDS}
        vals.update(observed_at=f"{day}T10:00", city="Colombo", us_aqi="50")
        return ",".join(vals[k] for k in collector.FIELDS)

    (data / "2026-09.csv").write_text(f"{head}\n{row('2026-09-20')}\n")
    (data / "2026-10.csv").write_text(f"{head}\n{row('2026-10-02')}\n{row('2026-10-09')}\n")

    assert prune(data, days=7, today=date(2026, 10, 10)) == 2
    assert not (data / "2026-09.csv").exists()  # fully expired file is deleted
    with open(data / "2026-10.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["observed_at"] for r in rows] == ["2026-10-09T10:00"]


def test_map_has_sidebar_and_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "fetch_current", _fake_fetch)
    cities = tmp_path / "cities.csv"
    cities.write_text("province,city,lat,lon\nWestern,Colombo,6.9,79.8\n")
    data = tmp_path / "data"
    collector.collect(cities, data, session=object())

    html = build_map(data, tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    assert 'id="navlist"' in html and 'id="livebtn"' in html
    assert "2026-09-28T10:00" in html and "Colombo" in html
