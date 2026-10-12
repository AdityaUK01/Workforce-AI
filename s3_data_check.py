
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

BUCKET = "workforceiq-ai-data-2026"
PREFIX = "raw/"
REGION = "ap-south-1"
PROFILE = "workforceiq"

# Expected row counts from the successful local validation.
EXPECTED_ROWS = {
    "departments.csv": 8,
    "roles.csv": 24,
    "kpi_definitions.csv": 40,
    "kpi_targets.csv": 120,
    "employees.csv": 720,
    "performance_records_curated.csv": 40250,
}


def count_csv_rows(path: Path) -> int:
    """Count CSV data rows, excluding the header."""
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        try:
            next(reader)  # Skip the header
        except StopIteration:
            raise ValueError("CSV file is empty and has no header.")

        return sum(1 for _ in reader)


def main() -> int:
    print("=" * 60)
    print("WORKFORCEIQ AI - S3 DATA VERIFICATION")
    print("=" * 60)
    print(f"Bucket:  {BUCKET}")
    print(f"Prefix:  {PREFIX}")
    print(f"Region:  {REGION}")
    print(f"Profile: {PROFILE}")
    print()

    session = boto3.Session(
        profile_name=PROFILE,
        region_name=REGION,
    )
    s3 = session.client("s3")

    failures = []
    total_rows = 0

    # Temporary storage only. Files are removed automatically on exit.
    with tempfile.TemporaryDirectory(prefix="workforceiq_s3_") as temp_dir:
        temp_path = Path(temp_dir)

        for filename, expected_rows in EXPECTED_ROWS.items():
            key = f"{PREFIX}{filename}"
            local_path = temp_path / filename

            try:
                response = s3.head_object(
                    Bucket=BUCKET,
                    Key=key,
                )

                s3.download_file(
                    BUCKET,
                    key,
                    str(local_path),
                )

                actual_rows = count_csv_rows(local_path)
                size_bytes = response["ContentLength"]

                if actual_rows != expected_rows:
                    failures.append(
                        f"{filename}: expected {expected_rows} rows, "
                        f"found {actual_rows}"
                    )
                    status = "FAIL"
                else:
                    status = "PASS"
                    total_rows += actual_rows

                print(
                    f"[{status}] {filename} | "
                    f"Rows: {actual_rows:,} | "
                    f"Size: {size_bytes:,} bytes"
                )

            except (ClientError, BotoCoreError, OSError, ValueError) as exc:
                failures.append(f"{filename}: {exc}")
                print(f"[FAIL] {filename}: {exc}")

    print()
    print("-" * 60)
    print(f"Datasets checked: {len(EXPECTED_ROWS)}")
    print(f"Rows verified:    {total_rows:,}")

    if failures:
        print(f"Failures:         {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        print("FINAL STATUS: FAIL")
        return 1

    print("Failures:         0")
    print("FINAL STATUS: PASS")
    print()
    print("All expected S3 CSV objects were downloaded temporarily")
    print("and their data-row counts matched the expected counts.")
    print("No MySQL tables or source CSV files were modified.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ClientError, BotoCoreError) as exc:
        print(f"AWS connection failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
