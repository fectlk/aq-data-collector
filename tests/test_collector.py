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


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def _city_body(city, state, lon, lat, aqi):
    return {"status": "success", "data": {
        "city": city, "state": state, "country": "Sri Lanka",
        "location": {"type": "Point", "coordinates": [lon, lat]},
        "current": {
            "pollution": {"ts": "2026-10-10T09:00:00.000Z", "aqius": aqi, "mainus": "p2"},
            "weather": {"ts": "2026-10-10T09:00:00.000Z", "tp": 29, "hu": 80,
                        "ws": 3, "pr": 1008}}}}


class _FakeIQAir:
    """Fake IQAir API. discovery=False makes states/cities fail (permission-style error)."""

    def __init__(self, discovery=True):
        self.discovery = discovery
        self.calls = []

    def get(self, url, params=None, timeout=None):
        ep = url.rsplit("/", 1)[1]
        self.calls.append(ep)
        if ep in ("states", "cities") and not self.discovery:
            return _Resp({"status": "fail", "data": {"message": "permission_denied"}})
        if ep == "states":
            return _Resp({"status": "success",
                          "data": [{"state": "Western Province"}, {"state": "Central"}]})
        if ep == "cities":
            names = {"Western Province": ["Colombo", "Negombo"], "Central": ["Kandy"]}
            return _Resp({"status": "success",
                          "data": [{"city": c} for c in names[params["state"]]]})
        if ep == "city":
            return _Resp(_city_body(params["city"], params["state"], 80.0, 7.0, 71))
        return _Resp(_city_body("Colombo", "Western Province", 79.86, 6.93, 71))  # nearest_city


def test_iqair_discovers_cities_once_and_collects(tmp_path):
    from fect_weather.iqair import collect_iqair

    cities = tmp_path / "cities.csv"
    cities.write_text("province,city,lat,lon\nWestern,Colombo,6.9,79.8\n")
    iq_file, iq = tmp_path / "iqair_cities.csv", tmp_path / "data" / "iqair"
    api = _FakeIQAir()
    kw = {"api_key": "x", "session": api, "delay": 0, "iqair_cities": iq_file}

    assert collect_iqair(cities, iq, **kw) == 3
    assert len(iq_file.read_text(encoding="utf-8").splitlines()) == 4  # header + 3 cities
    assert collect_iqair(cities, iq, **kw) == 0  # same hour -> no duplicates
    assert api.calls.count("states") == 1  # discovery is cached in the file


def test_iqair_falls_back_to_nearest_city(tmp_path, monkeypatch):
    from fect_weather.iqair import collect_iqair

    cities = tmp_path / "cities.csv"
    cities.write_text("province,city,lat,lon\nWestern,Colombo,6.9,79.8\nWestern,Negombo,7.2,79.8\n")
    iq = tmp_path / "data" / "iqair"
    n = collect_iqair(cities, iq, api_key="x", session=_FakeIQAir(discovery=False),
                      delay=0, iqair_cities=tmp_path / "none.csv")
    assert n == 1  # both towns map to Colombo, stored once
    assert not (tmp_path / "none.csv").exists()

    monkeypatch.setattr(collector, "fetch_current", _fake_fetch)
    collector.collect(cities, tmp_path / "data", session=object())
    out = build_map(tmp_path / "data", tmp_path / "docs" / "index.html")
    html = out.read_text(encoding="utf-8")
    assert 'id="map2"' in html and "Western Province" in html


def test_collect_survives_weather_timeout(tmp_path, monkeypatch):
    import requests

    def fetch(session, url, cities, variables):
        if url == collector.WEATHER_URL:
            raise requests.ConnectionError("timed out")
        return _fake_fetch(session, url, cities, variables)

    monkeypatch.setattr(collector, "fetch_current", fetch)
    cities = tmp_path / "cities.csv"
    cities.write_text("province,city,lat,lon\nWestern,Colombo,6.9,79.8\n")
    assert collector.collect(cities, tmp_path / "data", session=object()) == 1
