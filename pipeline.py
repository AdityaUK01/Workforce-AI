
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline_logger import (
    pipeline_started,
    pipeline_succeeded,
    pipeline_failed,
)
from validation_report import save_validation_report


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

REQUIRED_FILES = {
    "departments": "departments.csv",
    "roles": "roles.csv",
    "kpi_definitions": "kpi_definitions.csv",
    "kpi_targets": "kpi_targets.csv",
    "employees": "employees.csv",
    "performance_records": "performance_records_curated.csv",
}

PRIMARY_KEYS = {
    "departments": "department_id",
    "roles": "role_id",
    "kpi_definitions": "kpi_id",
    "kpi_targets": "target_id",
    "employees": "employee_id",
    "performance_records": "performance_record_id",
}

# Inferred from the existing dataset; confirm against original scoring rules.
SCORE_CAP = 150.0
SCORE_TOLERANCE = 0.02

LAST_BUSINESS_RESULTS = {
    "passed": 0,
    "failed": 0,
}

LAST_RECONCILIATION_RESULTS = {
    "records_reconciled": 0,
    "score_mismatches": 0,
    "incomparable_records": 0,
}


def load_csv_files():
    """Load the six CSV datasets and check their structure."""
    data = {}

    for table, filename in REQUIRED_FILES.items():
        path = DATA_DIR / filename

        if not path.exists():
            raise FileNotFoundError(
                f"Missing CSV file: {path}"
            )

        df = pd.read_csv(path)

        if df.empty:
            raise ValueError(
                f"{filename} contains no rows."
            )

        if df.columns.duplicated().any():
            raise ValueError(
                f"{filename} contains duplicate column names."
            )

        if df.columns.str.strip().tolist() != df.columns.tolist():
            raise ValueError(
                f"{filename} contains column names with extra spaces."
            )

        key_column = PRIMARY_KEYS[table]

        if key_column not in df.columns:
            raise ValueError(
                f"{filename} is missing required column: "
                f"{key_column}"
            )

        print(f"\nDataset: {table}")
        print(f"  File: {filename}")
        print(f"  Rows: {len(df):,}")
        print(f"  Columns: {len(df.columns)}")
        print(
            f"  Missing cells: "
            f"{int(df.isna().sum().sum()):,}"
        )
        print(
            f"  Duplicate rows: "
            f"{int(df.duplicated().sum()):,}"
        )

        data[table] = df

    total_rows = sum(len(df) for df in data.values())

    print("\nCSV structural validation completed.")
    print(f"Total rows inspected: {total_rows:,}")

    return data


def validate_business_rules(data):
    """Run 25 business-rule checks and retain their results."""
    results = []

    def check(label, failures, details):
        passed = failures == 0
        results.append((label, passed))

        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {label}: {details}")

    # Checks 1-6: Primary keys
    for table, key in PRIMARY_KEYS.items():
        df = data[table]

        missing = int(df[key].isna().sum())
        duplicate = int(df[key].duplicated(keep=False).sum())

        check(
            f"{table} primary key",
            missing + duplicate,
            f"{missing} missing key values; "
            f"{duplicate} rows with repeated key values",
        )

    # Check 7: KPI target values
    targets = data["kpi_targets"]

    target_values = pd.to_numeric(
        targets["target_value"],
        errors="coerce",
    )

    invalid_targets = int(
        (target_values.isna() | (target_values <= 0)).sum()
    )

    check(
        "KPI target values",
        invalid_targets,
        f"{invalid_targets} missing, non-numeric, "
        "or non-positive values",
    )

    # Checks 8-10: Performance numeric values
    records = data["performance_records"]

    for column in [
        "target_value",
        "actual_value",
        "achievement_pct",
    ]:
        values = pd.to_numeric(
            records[column],
            errors="coerce",
        )

        invalid = int(values.isna().sum())

        if column == "achievement_pct":
            invalid += int((values < 0).sum())

        check(
            f"Performance {column}",
            invalid,
            f"{invalid} missing, non-numeric, or invalid values",
        )

    # Check 11: Scoring directions
    definitions = data["kpi_definitions"]

    directions = (
        definitions["better_direction"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    invalid_directions = int(
        (~directions.isin({"higher", "lower"})).sum()
    )

    check(
        "KPI scoring directions",
        invalid_directions,
        f"{invalid_directions} values outside higher/lower",
    )

    # Check 12: Target start dates
    start_dates = pd.to_datetime(
        targets["effective_from"],
        errors="coerce",
    )

    invalid_starts = int(start_dates.isna().sum())

    check(
        "KPI target start dates",
        invalid_starts,
        f"{invalid_starts} missing or invalid start dates",
    )

    # Check 13: Target end dates
    # Blank effective_to values are valid for open-ended targets.
    end_dates = pd.to_datetime(
        targets["effective_to"],
        errors="coerce",
    )

    has_end_date = targets["effective_to"].notna()

    invalid_ends = int(
        (has_end_date & end_dates.isna()).sum()
    )

    reversed_dates = int(
        (
            has_end_date
            & start_dates.notna()
            & end_dates.notna()
            & (end_dates < start_dates)
        ).sum()
    )

    check(
        "KPI target end dates",
        invalid_ends + reversed_dates,
        f"{invalid_ends} invalid end dates; "
        f"{reversed_dates} end dates before start dates",
    )

    # Checks 14-23: Relationships between datasets
    relationships = [
        (
            "Employee department IDs",
            data["employees"]["department_id"],
            data["departments"]["department_id"],
        ),
        (
            "Employee role IDs",
            data["employees"]["role_id"],
            data["roles"]["role_id"],
        ),
        (
            "Role department names",
            data["roles"]["department_name"],
            data["departments"]["department_name"],
        ),
        (
            "KPI department names",
            definitions["department_name"],
            data["departments"]["department_name"],
        ),
        (
            "Target role IDs",
            targets["role_id"],
            data["roles"]["role_id"],
        ),
        (
            "Target KPI IDs",
            targets["kpi_id"],
            definitions["kpi_id"],
        ),
        (
            "Performance employee IDs",
            records["employee_id"],
            data["employees"]["employee_id"],
        ),
        (
            "Performance department IDs",
            records["department_id"],
            data["departments"]["department_id"],
        ),
        (
            "Performance role IDs",
            records["role_id"],
            data["roles"]["role_id"],
        ),
        (
            "Performance KPI IDs",
            records["kpi_id"],
            definitions["kpi_id"],
        ),
    ]

    for label, values, reference_values in relationships:
        invalid = int(
            (
                values.isna()
                | (~values.isin(reference_values))
            ).sum()
        )

        check(
            label,
            invalid,
            f"{invalid} unmatched or missing values",
        )

    # Check 24: Employee manager IDs
    employees = data["employees"]
    managers = employees["manager_employee_id"]

    known_employees = set(
        employees["employee_id"].dropna()
    )

    invalid_managers = int(
        (
            managers.notna()
            & (~managers.isin(known_employees))
        ).sum()
    )

    check(
        "Employee manager IDs",
        invalid_managers,
        f"{invalid_managers} references to unknown employees",
    )

    # Check 25: Reporting months
    months = pd.to_datetime(
        records["reporting_month"],
        errors="coerce",
    )

    invalid_months = int(months.isna().sum())

    check(
        "Performance reporting months",
        invalid_months,
        f"{invalid_months} missing or invalid dates",
    )

    failed = [
        label
        for label, passed in results
        if not passed
    ]

    passed_count = len(results) - len(failed)

    LAST_BUSINESS_RESULTS["passed"] = passed_count
    LAST_BUSINESS_RESULTS["failed"] = len(failed)

    print("\n" + "=" * 55)
    print(
        f"Business checks passed: "
        f"{passed_count}/{len(results)}"
    )
    print(f"Business checks failed: {len(failed)}")

    if failed:
        raise ValueError(
            "Business validation failed: "
            + ", ".join(failed)
        )


def reconcile_achievement_scores(data):
    """
    Recalculate and compare achievement scores.

    Higher-is-better: actual / target * 100
    Lower-is-better: target / actual * 100

    Expected scores are capped at SCORE_CAP.
    The cap is inferred from the current dataset.
    """
    records = data["performance_records"]

    actual = pd.to_numeric(
        records["actual_value"],
        errors="coerce",
    )

    target = pd.to_numeric(
        records["target_value"],
        errors="coerce",
    )

    stored = pd.to_numeric(
        records["achievement_pct"],
        errors="coerce",
    )

    direction = (
        records["better_direction"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    higher = direction.eq("higher")
    lower = direction.eq("lower")

    valid_target = (
        target.notna()
        & np.isfinite(target)
        & (target > 0)
    )

    valid_actual = (
        actual.notna()
        & np.isfinite(actual)
    )

    valid_stored = (
        stored.notna()
        & np.isfinite(stored)
    )

    higher_valid = (
        higher
        & valid_target
        & valid_actual
    )

    lower_valid = (
        lower
        & valid_target
        & valid_actual
        & (actual > 0)
    )

    supported = higher_valid | lower_valid

    expected = pd.Series(
        np.nan,
        index=records.index,
        dtype="float64",
    )

    expected.loc[higher_valid] = np.minimum(
        (
            actual.loc[higher_valid]
            / target.loc[higher_valid]
            * 100.0
        ),
        SCORE_CAP,
    )

    expected.loc[lower_valid] = np.minimum(
        (
            target.loc[lower_valid]
            / actual.loc[lower_valid]
            * 100.0
        ),
        SCORE_CAP,
    )

    valid_expected = pd.Series(
        np.isfinite(expected.to_numpy()),
        index=records.index,
    )

    comparable = (
        supported
        & valid_stored
        & valid_expected
    )

    difference = (stored - expected).abs()

    mismatches = (
        comparable
        & (difference > SCORE_TOLERANCE)
    )

    invalid_rows = ~comparable

    mismatch_count = int(mismatches.sum())
    invalid_count = int(invalid_rows.sum())
    checked_count = int(comparable.sum())

    LAST_RECONCILIATION_RESULTS.update({
        "records_reconciled": checked_count,
        "score_mismatches": mismatch_count,
        "incomparable_records": invalid_count,
    })

    print("\n" + "=" * 55)
    print("KPI ACHIEVEMENT RECONCILIATION")
    print(f"Rows in dataset: {len(records):,}")
    print(f"Rows compared: {checked_count:,}")
    print(f"Score mismatches: {mismatch_count:,}")
    print(f"Rows not safely comparable: {invalid_count:,}")
    print(f"Achievement cap: {SCORE_CAP:.1f}%")
    print(
        f"Allowed difference: {SCORE_TOLERANCE:.2f} "
        "percentage points"
    )

    if mismatch_count:
        sample = records.loc[
            mismatches,
            [
                "performance_record_id",
                "actual_value",
                "target_value",
                "better_direction",
                "achievement_pct",
            ],
        ].head(10).copy()

        sample["expected_achievement_pct"] = (
            expected.loc[sample.index].round(4)
        )

        sample["absolute_difference"] = (
            difference.loc[sample.index].round(4)
        )

        print("\nSample score mismatches:")
        print(sample.to_string(index=False))

    if invalid_count:
        sample = records.loc[
            invalid_rows,
            [
                "performance_record_id",
                "actual_value",
                "target_value",
                "better_direction",
                "achievement_pct",
            ],
        ].head(10)

        print("\nSample rows that could not be reconciled:")
        print(sample.to_string(index=False))

    passed = (
        mismatch_count == 0
        and invalid_count == 0
    )

    status = "PASS" if passed else "FAIL"

    print(
        f"[{status}] KPI achievement reconciliation: "
        f"{mismatch_count} mismatches; "
        f"{invalid_count} rows not safely comparable"
    )

    if not passed:
        raise ValueError(
            "KPI achievement reconciliation failed. "
            "Inspect the diagnostic rows before changing data."
        )


def main():
    parser = argparse.ArgumentParser(
        description="WorkforceIQ AI data validation pipeline"
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate CSV files without modifying MySQL",
    )

    args = parser.parse_args()

    start_time = time.perf_counter()
    data = {}
    status = "FAIL"
    error_message = None

    datasets = {
        name: {
            "file": filename,
            "rows": 0,
            "columns": 0,
        }
        for name, filename in REQUIRED_FILES.items()
    }

    LAST_BUSINESS_RESULTS.update({
        "passed": 0,
        "failed": 0,
    })

    LAST_RECONCILIATION_RESULTS.update({
        "records_reconciled": 0,
        "score_mismatches": 0,
        "incomparable_records": 0,
    })

    pipeline_started()

    try:
        if not args.validate_only:
            raise RuntimeError(
                "Safe mode: database loading is disabled. "
                "Run with --validate-only."
            )

        data = load_csv_files()

        for name, df in data.items():
            datasets[name]["rows"] = len(df)
            datasets[name]["columns"] = len(df.columns)
            datasets[name]["missing_cells"] = int(
                df.isna().sum().sum()
            )

        validate_business_rules(data)
        reconcile_achievement_scores(data)

        status = "PASS"
        pipeline_succeeded()

    except Exception as error:
        error_message = str(error)
        pipeline_failed(error)
        raise

    finally:
        elapsed = time.perf_counter() - start_time

        print(f"\nExecution time: {elapsed:.2f} seconds")

        try:
            save_validation_report(
                status=status,
                datasets=datasets,
                business_checks_passed=(
                    LAST_BUSINESS_RESULTS["passed"]
                ),
                business_checks_failed=(
                    LAST_BUSINESS_RESULTS["failed"]
                ),
                records_reconciled=(
                    LAST_RECONCILIATION_RESULTS[
                        "records_reconciled"
                    ]
                ),
                score_mismatches=(
                    LAST_RECONCILIATION_RESULTS[
                        "score_mismatches"
                    ]
                ),
                incomparable_records=(
                    LAST_RECONCILIATION_RESULTS[
                        "incomparable_records"
                    ]
                ),
                duration_seconds=elapsed,
                error=error_message,
            )

        except Exception as report_error:
            print(
                "WARNING: Could not save validation report: "
                f"{report_error}"
            )


if __name__ == "__main__":
    main()
