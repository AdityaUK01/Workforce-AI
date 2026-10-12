
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"

DATASETS = {
    "departments": "departments.csv",
    "roles": "roles.csv",
    "kpi_definitions": "kpi_definitions.csv",
    "kpi_targets": "kpi_targets.csv",
    "employees": "employees.csv",
    "performance_records": "performance_records_curated.csv",
}


def inspect_dataset(name, filename):
    path = DATA_DIR / filename

    if not path.exists():
        return {
            "file": filename,
            "status": "FAIL",
            "error": "File not found",
        }

    try:
        df = pd.read_csv(path)

        missing_by_column = {
            str(column): int(count)
            for column, count in df.isna().sum().items()
            if count > 0
        }

        duplicate_rows = int(df.duplicated().sum())

        return {
            "file": filename,
            "status": "PASS" if not df.empty else "FAIL",
            "rows": len(df),
            "columns": len(df.columns),
            "duplicate_rows": duplicate_rows,
            "missing_cells": int(df.isna().sum().sum()),
            "missing_by_column": missing_by_column,
            "memory_usage_mb": round(
                df.memory_usage(deep=True).sum() / (1024 ** 2),
                3,
            ),
        }

    except Exception as error:
        return {
            "file": filename,
            "status": "FAIL",
            "error": str(error),
        }


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    results = {
        name: inspect_dataset(name, filename)
        for name, filename in DATASETS.items()
    }

    total_rows = sum(
        item.get("rows", 0)
        for item in results.values()
    )

    total_missing = sum(
        item.get("missing_cells", 0)
        for item in results.values()
    )

    total_duplicates = sum(
        item.get("duplicate_rows", 0)
        for item in results.values()
    )

    failed_datasets = [
        name
        for name, item in results.items()
        if item["status"] != "PASS"
    ]

    report = {
        "project": "WorkforceIQ AI",
        "report_type": "Data Quality Summary",
        "generated_at": datetime.now().astimezone().isoformat(),
        "overall_status": (
            "PASS" if not failed_datasets else "FAIL"
        ),
        "summary": {
            "datasets_inspected": len(results),
            "datasets_failed": len(failed_datasets),
            "total_rows": total_rows,
            "total_missing_cells": total_missing,
            "total_duplicate_rows": total_duplicates,
        },
        "datasets": results,
        "notes": [
            "Missing cells are reported, not automatically treated as errors.",
            "Blank effective_to values in KPI targets may be intentional.",
            "Duplicate rows are exact full-row duplicates.",
        ],
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = REPORT_DIR / f"data_quality_{timestamp}.json"

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 55)
    print("WORKFORCEIQ AI — DATA QUALITY SUMMARY")
    print("=" * 55)

    for name, item in results.items():
        print(f"\nDataset: {name}")
        print(f"Status: {item['status']}")

        if "error" in item:
            print(f"Error: {item['error']}")
            continue

        print(f"Rows: {item['rows']:,}")
        print(f"Columns: {item['columns']}")
        print(f"Missing cells: {item['missing_cells']:,}")
        print(f"Duplicate rows: {item['duplicate_rows']:,}")
        print(f"Memory usage: {item['memory_usage_mb']} MB")

        if item["missing_by_column"]:
            print("Missing values by column:")
            for column, count in item["missing_by_column"].items():
                print(f"  {column}: {count}")

    print("\n" + "=" * 55)
    print(f"Overall status: {report['overall_status']}")
    print(f"Total rows: {total_rows:,}")
    print(f"Total missing cells: {total_missing:,}")
    print(f"Total duplicate rows: {total_duplicates:,}")
    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
