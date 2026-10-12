
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / "reports"


def save_validation_report(
    status,
    datasets,
    business_checks_passed,
    business_checks_failed,
    records_reconciled,
    score_mismatches,
    incomparable_records,
    duration_seconds,
    error=None,
):
    """Save a timestamped JSON report for a pipeline run."""

    timestamp = datetime.now().astimezone()

    report = {
        "project": "WorkforceIQ AI",
        "run_timestamp": timestamp.isoformat(),
        "status": status,
        "mode": "CSV validation only; MySQL not modified",
        "datasets": datasets,
        "total_rows_inspected": sum(
            item.get("rows", 0)
            for item in datasets.values()
        ),
        "business_checks": {
            "passed": business_checks_passed,
            "failed": business_checks_failed,
            "total": (
                business_checks_passed
                + business_checks_failed
            ),
        },
        "kpi_reconciliation": {
            "records_reconciled": records_reconciled,
            "score_mismatches": score_mismatches,
            "incomparable_records": incomparable_records,
        },
        "duration_seconds": round(duration_seconds, 3),
        "error": str(error) if error else None,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    filename = (
        "validation_"
        + timestamp.strftime("%Y%m%d_%H%M%S_%f")
        + ".json"
    )
    report_path = REPORT_DIR / filename

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nValidation report saved: {report_path}")

    return report_path
