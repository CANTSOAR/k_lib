from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.ingest.base import DEFAULT_DB_PATH, parse_date, run_source
from backend.ingest.registry import list_public_academic_sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ingest jobs for public academic sources.")
    parser.add_argument("--start-date", help="Inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", help="Inclusive end date in YYYY-MM-DD format.")
    parser.add_argument("--bucket-root", default="backend/ingest_bucket", help="Root directory for output.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite database for ingested PDFs.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    bucket_root = Path(args.bucket_root)
    db_path = Path(args.db_path)

    results = []
    for source in list_public_academic_sources():
        results.append(run_source(source, start_date=start_date, end_date=end_date, bucket_root=bucket_root, db_path=db_path))

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
