"""Weekly Excel report (Mon-Sun, Sri Lanka time) built from data/*.csv."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .collector import TZ
from .mapper import load_all


def weekly_report(data_dir="data", out_dir="reports", today: date | None = None) -> Path | None:
    today = today or datetime.now(TZ).date()
    monday = today - timedelta(days=today.weekday() + 7)
    sunday = monday + timedelta(days=6)

    df = load_all(data_dir)
    df["observed_at"] = pd.to_datetime(df["observed_at"])
    day = df["observed_at"].dt.date
    week = df[(day >= monday) & (day <= sunday)]
    if week.empty:
        return None

    hourly = week.pivot_table(index="city", columns="observed_at", values="us_aqi")
    hourly.columns = [c.strftime("%Y-%m-%d %H:%M") for c in hourly.columns]

    daily = (week.assign(date=week["observed_at"].dt.strftime("%Y-%m-%d"))
             .pivot_table(index="city", columns="date", values="us_aqi", aggfunc="mean")
             .round(0))

    summary = (week.groupby(["province", "city"])["us_aqi"]
               .agg(mean="mean", max="max", min="min").round(1).reset_index())
    worst = summary.loc[summary.groupby("province")["mean"].idxmax()]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"AQI_Weekly_{monday}_to_{sunday}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        hourly.to_excel(xw, sheet_name="AQI timeseries")
        daily.to_excel(xw, sheet_name="Daily mean")
        summary.to_excel(xw, sheet_name="City summary", index=False)
        worst.to_excel(xw, sheet_name="Most polluted per province", index=False)
    return path
