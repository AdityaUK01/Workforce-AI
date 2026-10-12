import json
import sys
import tempfile
import time
import traceback
from contextlib import redirect_stdout
from pathlib import Path

import boto3
import pandas as pd
from botocore.exceptions import BotoCoreError, ClientError


BASE_DIR = Path(__file__).resolve().parent
BUCKET_NAME = "workforceiq-ai-data-2026"
AWS_REGION = "ap-south-1"
AWS_PROFILE = "workforceiq"

REQUIRED_FILES = {
    "departments": "departments.csv",
    "roles": "roles.csv",
    "kpi_definitions": "kpi_definitions.csv",
    "kpi_targets": "kpi_targets.csv",
    "employees": "employees.csv",
    "performance_records": "performance_records_curated.csv",
}

REPORT_DIR = BASE_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)


def main():
    started = time.perf_counter()
    status = "FAIL"
    error_message = None
    data = {}
    business_results = {"passed": 0, "failed": 0}
    reconciliation_results = {
        "records_reconciled": 0,
        "score_mismatches": 0,
        "incomparable_records": 0,
    }
    datasets = {}

    print("=" * 65)
    print("WorkforceIQ AI — S3 VALIDATION PIPELINE")
    print("=" * 65)
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Region: {AWS_REGION}")
    print("Mode: READ-ONLY — no MySQL writes")

    try:
        # Reuse the existing business validation functions.
        import pipeline

        session = boto3.Session(
            profile_name=AWS_PROFILE,
            region_name=AWS_REGION,
        )
        s3 = session.client("s3")

        with tempfile.TemporaryDirectory(
            prefix="workforceiq_s3_"
        ) as temporary_directory:
            temp_dir = Path(temporary_directory)

            # Download the six source files to temporary storage.
            print("\nSTEP 1: Downloading datasets from S3")

            for name, filename in REQUIRED_FILES.items():
                key = f"raw/{filename}"
                local_path = temp_dir / filename

                print(f"Downloading s3://{BUCKET_NAME}/{key}")
                s3.download_file(
                    BUCKET_NAME,
                    key,
                    str(local_path),
                )

            # Verify file structure and load from the temporary
            # directory by overriding the module's data path.
            original_data_dir = pipeline.DATA_DIR
            original_report_function = (
                pipeline.save_validation_report
            )

            report_path = (
                REPORT_DIR / "s3_validation_report.json"
            )

            def save_s3_report(**kwargs):
                """Write the S3 run report separately."""
                report = {
                    "source": "Amazon S3",
                    "bucket": BUCKET_NAME,
                    "region": AWS_REGION,
                    "status": kwargs.get("status"),
                    "datasets": kwargs.get("datasets"),
                    "business_checks_passed": kwargs.get(
                        "business_checks_passed"
                    ),
                    "business_checks_failed": kwargs.get(
                        "business_checks_failed"
                    ),
                    "records_reconciled": kwargs.get(
                        "records_reconciled"
                    ),
                    "score_mismatches": kwargs.get(
                        "score_mismatches"
                    ),
                    "incomparable_records": kwargs.get(
                        "incomparable_records"
                    ),
                    "duration_seconds": kwargs.get(
                        "duration_seconds"
                    ),
                    "error": kwargs.get("error"),
                }

                report_path.write_text(
                    json.dumps(report, indent=2, default=str),
                    encoding="utf-8",
                )

            try:
                pipeline.DATA_DIR = temp_dir
                pipeline.save_validation_report = save_s3_report

                print("\nSTEP 2: Structural validation")
                data = pipeline.load_csv_files()

                for name, df in data.items():
                    datasets[name] = {
                        "file": REQUIRED_FILES[name],
                        "rows": int(len(df)),
                        "columns": int(len(df.columns)),
                        "missing_cells": int(
                            df.isna().sum().sum()
                        ),
                    }

                print("\nSTEP 3: Business-rule validation")
                pipeline.validate_business_rules(data)

                print("\nSTEP 4: KPI achievement reconciliation")
                pipeline.reconcile_achievement_scores(data)

                business_results = dict(
                    pipeline.LAST_BUSINESS_RESULTS
                )
                reconciliation_results = dict(
                    pipeline.LAST_RECONCILIATION_RESULTS
                )

                status = "PASS"

            finally:
                # Restore the original module configuration.
                pipeline.DATA_DIR = original_data_dir
                pipeline.save_validation_report = (
                    original_report_function
                )

        print("\nSTEP 5: Saving S3 validation report")

    except (ClientError, BotoCoreError) as exc:
        error_message = f"AWS/S3 error: {exc}"
        print(f"\nERROR: {error_message}")

    except Exception as exc:
        error_message = str(exc)
        print(f"\nERROR: {error_message}")
        traceback.print_exc()

        # Preserve counters even if a business check fails.
        try:
            import pipeline

            business_results = dict(
                pipeline.LAST_BUSINESS_RESULTS
            )
            reconciliation_results = dict(
                pipeline.LAST_RECONCILIATION_RESULTS
            )
        except Exception:
            pass

    finally:
        elapsed = time.perf_counter() - started

        report = {
            "source": "Amazon S3",
            "bucket": BUCKET_NAME,
            "region": AWS_REGION,
            "status": status,
            "datasets": datasets,
            "total_rows": sum(
                item.get("rows", 0)
                for item in datasets.values()
            ),
            "business_checks_passed": business_results["passed"],
            "business_checks_failed": business_results["failed"],
            "records_reconciled": reconciliation_results[
                "records_reconciled"
            ],
            "score_mismatches": reconciliation_results[
                "score_mismatches"
            ],
            "incomparable_records": reconciliation_results[
                "incomparable_records"
            ],
            "duration_seconds": round(elapsed, 2),
            "error": error_message,
        }

        final_report_path = REPORT_DIR / "s3_validation_report.json"
        final_report_path.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )

        print("\n" + "=" * 65)
        print(f"FINAL STATUS: {status}")
        print(f"Datasets inspected: {len(datasets)}/6")
        print(f"Rows inspected: {report['total_rows']:,}")
        print(
            "Business checks passed: "
            f"{business_results['passed']}"
        )
        print(
            "Business checks failed: "
            f"{business_results['failed']}"
        )
        print(
            "KPI records reconciled: "
            f"{reconciliation_results['records_reconciled']:,}"
        )
        print(
            "Score mismatches: "
            f"{reconciliation_results['score_mismatches']}"
        )
        print(f"Duration: {elapsed:.2f} seconds")
        print(f"Report: {final_report_path}")
        print("MySQL writes: NONE")
        print("=" * 65)

    if status != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()