"""Build the latest-readings map (docs/index.html, served by GitHub Pages)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import folium
import pandas as pd

from .aqi import category
from .collector import TZ


def load_all(data_dir: str | Path) -> pd.DataFrame:
    files = sorted(Path(data_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files in {data_dir}")
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def latest_rows(data_dir: str | Path) -> pd.DataFrame:
    df = load_all(data_dir).sort_values("observed_at")
    return df.groupby("city", as_index=False).tail(1)


def build_map(data_dir="data", out_file="docs/index.html") -> Path:
    df = latest_rows(data_dir)
    m = folium.Map(location=[7.8731, 80.7718], zoom_start=8)

    for r in df.itertuples():
        if pd.isna(r.us_aqi):
            continue
        aqi = round(r.us_aqi)
        label, color, message = category(aqi)
        text = "#fff" if aqi > 200 else "#000"
        tooltip = (
            f"<div style='font-family:Arial;width:220px'>"
            f"<b>{r.city}</b> <small>({r.province})</small><br>"
            f"<span style='font-size:28px;font-weight:bold'>{aqi}</span> US AQI<br>"
            f"{label}<br><small>{message}</small><br>"
            f"<small>PM2.5: {r.pm2_5} &micro;g/m&sup3; &middot; "
            f"{r.temperature_2m}&deg;C<br>Observed {r.observed_at}</small></div>"
        )
        icon = folium.DivIcon(
            icon_size=(32, 32), icon_anchor=(16, 16),
            html=(f"<div style='background:{color};color:{text};width:32px;height:32px;"
                  f"border-radius:50%;text-align:center;line-height:32px;"
                  f"font-weight:800;border:1px solid #555'>{aqi}</div>"),
        )
        folium.Marker([r.lat, r.lon], icon=icon,
                      tooltip=folium.Tooltip(tooltip)).add_to(m)

    stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    m.get_root().html.add_child(folium.Element(
        "<div style='position:fixed;bottom:8px;left:8px;z-index:9999;background:#fff;"
        "padding:6px 10px;font:12px Arial;border-radius:6px'>"
        f"FECT Sri Lanka AQI &middot; updated {stamp} (SLST) &middot; "
        "Data: <a href='https://open-meteo.com/'>Open-Meteo</a> (CC BY 4.0)</div>"))

    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(out)
    return out
