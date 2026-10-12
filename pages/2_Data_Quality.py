
import json
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = BASE_DIR / "reports"

st.set_page_config(
    page_title="Data Quality | WorkforceIQ AI",
    page_icon="🔍",
    layout="wide",
)

st.title("WorkforceIQ AI")
st.subheader("Data Quality Monitor")
st.caption(
    "Monitor dataset completeness, duplicate rows, "
    "record volumes, and validation status."
)


def get_latest_report():
    reports = list(
        REPORT_DIR.glob("data_quality_*.json")
    )

    if not reports:
        return None

    latest = max(
        reports,
        key=lambda path: path.stat().st_mtime,
    )

    with latest.open("r", encoding="utf-8") as file:
        return json.load(file), latest


result = get_latest_report()

if result is None:
    st.warning(
        "No data-quality report found. "
        "Run `python data_quality_summary.py` first."
    )
    st.stop()

report, report_path = result
summary = report["summary"]
datasets = report["datasets"]

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Total Rows",
    f"{summary['total_rows']:,}",
)

col2.metric(
    "Datasets",
    summary["datasets_inspected"],
)

col3.metric(
    "Missing Cells",
    f"{summary['total_missing_cells']:,}",
)

col4.metric(
    "Duplicate Rows",
    f"{summary['total_duplicate_rows']:,}",
)

st.divider()

if report["overall_status"] == "PASS":
    st.success("Overall data-quality status: PASS")
else:
    st.error("Overall data-quality status: FAIL")

st.caption(
    f"Last report: {report['generated_at']}"
)
st.caption(f"Report file: {report_path.name}")

st.subheader("Dataset Overview")

rows = []

for name, item in datasets.items():
    rows.append({
        "Dataset": name,
        "Status": item.get("status", "UNKNOWN"),
        "Rows": item.get("rows", 0),
        "Columns": item.get("columns", 0),
        "Missing Cells": item.get("missing_cells", 0),
        "Duplicate Rows": item.get("duplicate_rows", 0),
        "Memory (MB)": item.get("memory_usage_mb", 0),
    })

df = pd.DataFrame(rows)

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)

st.subheader("Missing Values by Dataset")

missing_rows = []

for name, item in datasets.items():
    for column, count in item.get(
        "missing_by_column", {}
    ).items():
        missing_rows.append({
            "Dataset": name,
            "Column": column,
            "Missing Values": count,
        })

if missing_rows:
    missing_df = pd.DataFrame(missing_rows)

    st.dataframe(
        missing_df,
        use_container_width=True,
        hide_index=True,
    )

    st.bar_chart(
        missing_df.set_index("Column")["Missing Values"]
    )
else:
    st.success("No missing values found.")

st.subheader("Dataset Details")

selected_dataset = st.selectbox(
    "Choose a dataset",
    list(datasets.keys()),
)

selected = datasets[selected_dataset]

st.json(selected)

st.divider()

st.caption(
    "This page reads the latest JSON report. "
    "It does not modify CSV files or the MySQL database."
)

if st.button("Refresh report"):
    st.rerun()
