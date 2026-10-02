"""US AQI categories."""

_BANDS = [
    (50, "Good", "#00e400", "Air quality is satisfactory."),
    (100, "Moderate", "#ffff00", "Air quality is acceptable."),
    (150, "Unhealthy for sensitive groups", "#ff7e00", "Sensitive groups may be affected."),
    (200, "Unhealthy", "#ff0000", "Everyone may be affected."),
    (300, "Very unhealthy", "#8f3f97", "Health alert: everyone may be seriously affected."),
]


def category(aqi: float) -> tuple[str, str, str]:
    """Return (label, hex colour, message) for an AQI value."""
    for upper, label, color, message in _BANDS:
        if aqi <= upper:
            return label, color, message
    return "Hazardous", "#7e0023", "Emergency conditions."
