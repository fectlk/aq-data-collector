# FECT Sri Lanka Air Quality & Weather Data

Open dataset and live map of air quality (US AQI, PM2.5, PM10, ozone, NO₂, SO₂, CO) and weather
for 28 cities across all 9 provinces of Sri Lanka. Built for [FECT](https://github.com/fectlk).

**Live map:** `https://fectlk.github.io/iqair-data-scraper/`

## How it works

| Step | What | Schedule (Sri Lanka time) |
|------|------|---------------------------|
| Collect | GitHub Actions calls the [Open-Meteo](https://open-meteo.com/) API (2 requests for all cities) and appends rows to `data/YYYY-MM.csv` | every 3 hours |
| Prune | Deletes data older than 7 days (`python -m fect_weather prune`) | after each collection |
| Map | Rebuilds `docs/index.html`: live map plus a left menu of past snapshots (one file, published with GitHub Pages) | after each collection |
| Report | Weekly Excel summary in `reports/` | Mondays 08:00 |

No web scraping and no API key. The old IQAir page scraper was replaced after the source blocked it.
Old files are kept in `archive/`.

## Data

`data/YYYY-MM.csv`, one row per city per observation.

| Column | Meaning |
|--------|---------|
| `collected_at` / `observed_at` | when we fetched / when the source measured (Sri Lanka time) |
| `province`, `city`, `lat`, `lon` | location |
| `us_aqi` | US Air Quality Index |
| `pm2_5`, `pm10`, `ozone`, `nitrogen_dioxide`, `sulphur_dioxide`, `carbon_monoxide` | µg/m³ |
| `temperature_2m` (°C), `relative_humidity_2m` (%), `precipitation` (mm), `wind_speed_10m` (km/h), `weather_code` | weather |

> Open-Meteo air quality values are **model-based estimates** (CAMS), not readings from physical
> monitors. Treat them as indicative.

## Run locally

```bash
pip install -r requirements.txt
python -m fect_weather collect   # fetch and append data
python -m fect_weather iqair     # IQAir city readings (needs IQAIR_API_KEY)
python -m fect_weather prune     # drop data older than 7 days
python -m fect_weather map       # build docs/index.html
python -m fect_weather report    # last week's Excel summary
```

Add or remove cities in `config/cities.csv` (`province,city,lat,lon`).

## Develop

```bash
pip install -r requirements-dev.txt
ruff check . && pytest
```

## Setup (one time)

1. Repo → **Settings → Pages** → Source: *Deploy from a branch* → `main` / `/docs`.
2. Repo → **Settings → Actions → General** → Workflow permissions: *Read and write*.
3. **Actions → Collect AQI data → Run workflow** to test.

## Credits & license

Data: [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0, non-commercial use). Code: MIT.
