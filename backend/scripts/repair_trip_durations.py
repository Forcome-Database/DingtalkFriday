"""Repair legacy trip durations from authoritative totals after database migrations."""

import argparse
import asyncio
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(arguments):
    from app.database import engine
    from app.dingtalk.client import dingtalk_client
    from app.services.trip_repair import repair_trip_durations

    try:
        report = await repair_trip_durations(
            year=arguments.year,
            dry_run=not arguments.apply,
            only_missing_source=not arguments.all_records,
            max_requests=arguments.max_requests,
            minimum_work_date=arguments.minimum_work_date,
        )
        print(json.dumps(report, ensure_ascii=True, indent=2))
        skipped_conflicts = any(item["localConsistency"] != "consistent" for item in report["skippedSources"])
        return 2 if report["unresolved"] or skipped_conflicts else 0
    finally:
        await dingtalk_client.close()
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, help="Limit reads and updates to existing rows in this year")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read authoritative values and preview changes (default)")
    mode.add_argument("--apply", action="store_true", help="Apply verified corrections to existing rows")
    parser.add_argument("--all-records", action="store_true", help="Recheck approvals even when source metadata already exists")
    parser.add_argument("--max-requests", type=int, help="Limit logical attendance API calls")
    parser.add_argument("--minimum-work-date", type=date.fromisoformat, help="Earliest queryable attendance date (YYYY-MM-DD); older-only approvals are retained and reported")
    arguments = parser.parse_args()
    if arguments.year is not None and not 1 <= arguments.year <= 9999:
        parser.error("--year must be between 1 and 9999")
    if arguments.max_requests is not None and arguments.max_requests < 0:
        parser.error("--max-requests must be non-negative")
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    return asyncio.run(run(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
