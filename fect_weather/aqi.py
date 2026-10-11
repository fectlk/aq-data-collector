"""US AQI categories and a PM-based US AQI calculation."""

import math

BANDS = [
    (50, "Good", "#00e400", "Air quality is satisfactory."),
    (100, "Moderate", "#ffff00", "Air quality is acceptable."),
    (150, "Unhealthy for sensitive groups", "#ff7e00", "Sensitive groups may be affected."),
    (200, "Unhealthy", "#ff0000", "Everyone may be affected."),
    (300, "Very unhealthy", "#8f3f97", "Health alert: everyone may be seriously affected."),
]


def category(aqi: float) -> tuple[str, str, str]:
    """Return (label, hex colour, message) for an AQI value."""
    for upper, label, color, message in BANDS:
        if aqi <= upper:
            return label, color, message
    return "Hazardous", "#7e0023", "Emergency conditions."


# US EPA breakpoints (PM2.5 uses the 2024 revision): (conc_lo, conc_hi, aqi_lo, aqi_hi)
_PM25 = [(0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
         (55.5, 125.4, 151, 200), (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 400),
         (325.5, 500.4, 401, 500)]
_PM10 = [(0, 54, 0, 50), (55, 154, 51, 100), (155, 254, 101, 150), (255, 354, 151, 200),
         (355, 424, 201, 300), (425, 504, 301, 400), (505, 604, 401, 500)]


def _sub_index(conc: float, table) -> int:
    for lo, hi, ilo, ihi in table:
        if lo <= conc <= hi:
            return round((ihi - ilo) / (hi - lo) * (conc - lo) + ilo)
    return 500


def us_aqi(pm25: float | None = None, pm10: float | None = None) -> int | None:
    """US AQI from PM2.5 and/or PM10 (the higher sub-index wins). None if neither is given."""
    subs = []
    if pm25 is not None:
        subs.append(_sub_index(math.floor(round(pm25 * 10, 6)) / 10, _PM25))
    if pm10 is not None:
        subs.append(_sub_index(math.floor(pm10), _PM10))
    return max(subs) if subs else None
