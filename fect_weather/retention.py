"""Keep only the last N days of data (Sri Lanka dates).

Pruning works on whole days: a row is kept if its observation date is on or after
`today - days`. With days=7 this keeps last Monday on a Monday morning, so the weekly
report (previous Mon-Sun) still sees the full week before old days drop off.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from .collector import TZ

RETENTION_DAYS = 7


def prune(data_dir: str | Path = "data", days: int = RETENTION_DAYS,
          today: date | None = None) -> int:
    """Drop rows older than the window; delete files left empty. Returns rows removed."""
    today = today or datetime.now(TZ).date()
    cutoff = (today - timedelta(days=days)).isoformat()
    removed = 0
    for path in sorted(Path(data_dir).glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)
        keep = [r for r in rows if r["observed_at"][:10] >= cutoff]
        removed += len(rows) - len(keep)
        if not keep:
            path.unlink()
        elif len(keep) != len(rows):
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(keep)
    return removed
