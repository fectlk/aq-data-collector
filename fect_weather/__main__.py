import argparse
import os
import sys

from .collector import collect
from .iqair import collect_iqair, discover_cities
from .mapper import build_map
from .report import weekly_report
from .retention import prune


def main() -> int:
    p = argparse.ArgumentParser(prog="fect_weather")
    p.add_argument("command", choices=["collect", "iqair", "iqair-cities", "prune", "map", "report"])
    args = p.parse_args()

    if args.command == "collect":
        print(f"Wrote {collect()} new rows")
    elif args.command == "iqair":
        if not os.environ.get("IQAIR_API_KEY"):
            print("IQAIR_API_KEY not set - skipping IQAir")
        else:
            print(f"Wrote {collect_iqair()} new IQAir rows")
    elif args.command == "iqair-cities":
        if not os.environ.get("IQAIR_API_KEY"):
            print("IQAIR_API_KEY not set")
        else:
            from .collector import make_session
            found = discover_cities(make_session(), os.environ["IQAIR_API_KEY"])
            print(f"Saved {len(found)} IQAir cities to config/iqair_cities.csv")
    elif args.command == "prune":
        print(f"Removed {prune() + prune('data/iqair')} old rows")
    elif args.command == "map":
        print(f"Saved {build_map()}")
    else:
        path = weekly_report()
        print(f"Saved {path}" if path else "No data for last week")
    return 0


if __name__ == "__main__":
    sys.exit(main())
