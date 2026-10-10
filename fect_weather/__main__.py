import argparse
import sys

from .collector import collect
from .mapper import build_map
from .report import weekly_report
from .retention import prune


def main() -> int:
    p = argparse.ArgumentParser(prog="fect_weather")
    p.add_argument("command", choices=["collect", "prune", "map", "report"])
    args = p.parse_args()

    if args.command == "collect":
        print(f"Wrote {collect()} new rows")
    elif args.command == "prune":
        print(f"Removed {prune()} old rows")
    elif args.command == "map":
        print(f"Saved {build_map()}")
    else:
        path = weekly_report()
        print(f"Saved {path}" if path else "No data for last week")
    return 0


if __name__ == "__main__":
    sys.exit(main())
