import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

st.set_page_config(page_title="WorkforceIQ AI", page_icon="📊", layout="wide")
st.title("WorkforceIQ AI")
st.caption("Workforce performance analytics and AI-powered insights")


@st.cache_resource
def get_engine():
    db_url = URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "workforceiq"),
        query={"charset": "utf8mb4"},
    )
    return create_engine(db_url, pool_pre_ping=True, pool_recycle=1800)


def read_sql(query, params=None):
    engine = get_engine()
    with engine.connect() as connection:
        result = connection.execute(text(query), params or {})
        rows = result.fetchall()
        columns = result.keys()
    return pd.DataFrame(rows, columns=columns)


def load_dashboard_data():
    # Read existing tables only; no database records are modified.
    return (
        read_sql("SELECT * FROM employees"),
        read_sql("SELECT * FROM departments"),
        read_sql("SELECT * FROM performance_records"),
        read_sql("SELECT * FROM kpi_definitions"),
    )


def find_column(dataframe, candidates):
    mapping = {str(col).lower(): col for col in dataframe.columns}
    for candidate in candidates:
        if candidate.lower() in mapping:
            return mapping[candidate.lower()]
    return None


st.sidebar.header("Dashboard controls")
if st.sidebar.button("Connect / Refresh Dashboard", type="primary"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption("Connected database: workforceiq")

try:
    employees, departments, records, kpi_definitions = load_dashboard_data()
except SQLAlchemyError as exc:
    st.error("Unable to connect to MySQL or load dashboard tables.")
    st.markdown(
        "Check that MySQL is running, the database and tables exist, "
        "your `.env` credentials are correct, and PyMySQL is installed."
    )
    with st.expander("Technical details"):
        st.code(str(exc))
    st.stop()
except Exception as exc:
    st.error("The dashboard could not load its data.")
    with st.expander("Technical details"):
        st.code(str(exc))
    st.stop()


employee_id_col = find_column(employees, ["employee_id", "emp_id", "id"])
employee_dept_col = find_column(employees, ["department_id", "dept_id"])
department_id_col = find_column(departments, ["department_id", "dept_id", "id"])
department_name_col = find_column(
    departments, ["department_name", "name", "department", "dept_name"]
)
record_employee_col = find_column(records, ["employee_id", "emp_id"])
record_score_col = find_column(
    records,
    [
        "achievement_pct", "achievement_percentage", "achievement_percent",
        "achievement", "score", "performance_score", "actual_value",
    ],
)
record_date_col = find_column(
    records, ["reporting_month", "record_date", "performance_date", "date", "month", "period", "record_month"]
)

record_kpi_id_col = find_column(records, ["kpi_id", "metric_id"])
record_department_col = find_column(records, ["department_id", "dept_id"])
record_actual_col = find_column(records, ["actual_value", "actual", "actual_result"])
record_target_col = find_column(records, ["target_value", "target", "target_result"])
record_unit_col = find_column(records, ["unit", "unit_of_measure", "measurement_unit"])
record_status_col = find_column(records, ["performance_status", "status", "kpi_status"])
kpi_definition_id_col = find_column(kpi_definitions, ["kpi_id", "metric_id", "id"])
kpi_name_col = find_column(kpi_definitions, ["kpi_name", "name", "metric_name", "kpi"])


# Rename lookup columns before merge to prevent KeyError from name collisions.
lookup = None
if department_id_col and department_name_col:
    lookup = (
        departments[[department_id_col, department_name_col]]
        .drop_duplicates(subset=[department_id_col])
        .rename(
            columns={
                department_id_col: "_wiq_department_join_id",
                department_name_col: "_wiq_department_label",
            }
        )
    )

filtered_employees = employees.copy()
filtered_records = records.copy()
department_filter_available = bool(employee_dept_col and employee_id_col and lookup is not None)

if department_filter_available:
    employee_joined = employees.merge(
        lookup,
        left_on=employee_dept_col,
        right_on="_wiq_department_join_id",
        how="left",
    )
    department_options = ["All departments"] + sorted(
        employee_joined["_wiq_department_label"].dropna().astype(str).unique().tolist()
    )
    selected_department = st.sidebar.selectbox("Department", department_options)

    if selected_department != "All departments":
        filtered_employees = employee_joined[
            employee_joined["_wiq_department_label"].astype(str) == selected_department
        ][employees.columns].copy()
        if record_employee_col:
            selected_ids = filtered_employees[employee_id_col].dropna()
            filtered_records = records[records[record_employee_col].isin(selected_ids)].copy()
else:
    st.sidebar.info(
        "Department filter unavailable: department ID/name columns were not identified."
    )

# Optional reporting-month and KPI filters.
if record_date_col and not filtered_records.empty:
    month_values = sorted(
        filtered_records[record_date_col].dropna().astype(str).unique().tolist()
    )
    if month_values:
        selected_months = st.sidebar.multiselect(
            "Reporting month",
            options=month_values,
            default=month_values,
            help="Clear selections to show all available months.",
        )
        if selected_months:
            filtered_records = filtered_records[
                filtered_records[record_date_col].astype(str).isin(selected_months)
            ].copy()

if record_kpi_id_col and not filtered_records.empty:
    kpi_options = sorted(
        filtered_records[record_kpi_id_col].dropna().astype(str).unique().tolist()
    )
    if kpi_options:
        selected_kpis = st.sidebar.multiselect(
            "KPI IDs",
            options=kpi_options,
            default=kpi_options,
            help="Choose one or more KPIs. Clear selections to show all KPIs.",
        )
        if selected_kpis:
            filtered_records = filtered_records[
                filtered_records[record_kpi_id_col].astype(str).isin(selected_kpis)
            ].copy()

st.sidebar.caption(f"Filtered performance records: {len(filtered_records):,}")


st.subheader("Workforce overview")
metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("Employees", f"{len(filtered_employees):,}")
metric2.metric("Performance records", f"{len(filtered_records):,}")
metric3.metric(
    "Departments",
    f"{filtered_employees[employee_dept_col].nunique():,}"
    if employee_dept_col else f"{len(departments):,}",
)

if record_score_col and not filtered_records.empty:
    scores = pd.to_numeric(filtered_records[record_score_col], errors="coerce").dropna()
    metric4.metric(
        "Average performance",
        f"{scores.mean():.1f}" if not scores.empty else "N/A",
        help=f"Average of detected column: {record_score_col}",
    )
else:
    metric4.metric("Average performance", "N/A")

st.divider()
left, right = st.columns(2)

with left:
    st.subheader("Employees by department")
    if department_filter_available:
        chart_source = filtered_employees.merge(
            lookup,
            left_on=employee_dept_col,
            right_on="_wiq_department_join_id",
            how="left",
        )
        chart_source["_wiq_department_label"] = (
            chart_source["_wiq_department_label"].fillna("Unknown").astype(str)
        )
        counts = (
            chart_source.groupby("_wiq_department_label", as_index=False)
            .size()
            .rename(columns={"_wiq_department_label": "Department", "size": "Employees"})
        )
        if not counts.empty:
            fig = px.bar(counts, x="Department", y="Employees", title="Employee headcount by department")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No department data is available.")
    else:
        st.info("Required department columns were not detected.")

with right:
    st.subheader("Performance distribution")
    if record_score_col and not filtered_records.empty:
        chart_data = filtered_records.copy()
        chart_data[record_score_col] = pd.to_numeric(chart_data[record_score_col], errors="coerce")
        chart_data = chart_data.dropna(subset=[record_score_col])
        if not chart_data.empty:
            fig = px.histogram(
                chart_data, x=record_score_col, nbins=20,
                title="Distribution of performance scores",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("The detected performance column has no numeric values.")
    else:
        st.info("No recognized numeric performance column was found.")

# ==================================================
# KPI STATUS BREAKDOWN
# ==================================================
st.divider()
st.subheader("KPI status breakdown")
st.caption(
    "Uses performance_status from MySQL when available. Otherwise, achievement_pct "
    "is classified as On Target (>=100%), Watch (90–<100%), or Below Target (<90%)."
)

if not filtered_records.empty and record_score_col:
    status_data = filtered_records.copy()
    status_data["_wiq_score"] = pd.to_numeric(
        status_data[record_score_col], errors="coerce"
    )

    if record_status_col:
        raw_status = status_data[record_status_col].fillna("").astype(str).str.strip()
        normalized = raw_status.str.lower()
        status_map = {
            "on target": "On Target", "met": "On Target", "meeting": "On Target",
            "exceeds": "On Target", "exceeded": "On Target",
            "above target": "On Target", "on track": "On Target",
            "watch": "Watch", "at risk": "Watch", "near target": "Watch",
            "below target": "Below Target", "below": "Below Target",
            "missed": "Below Target", "not met": "Below Target",
            "off track": "Below Target",
        }
        status_data["KPI status"] = normalized.map(status_map)
        unknown = status_data["KPI status"].isna()
        status_data.loc[unknown, "KPI status"] = raw_status[unknown].replace("", "Unclassified")
    else:
        status_data["KPI status"] = "Unclassified"
        valid = status_data["_wiq_score"].notna()
        status_data.loc[valid & (status_data["_wiq_score"] >= 100), "KPI status"] = "On Target"
        status_data.loc[
            valid & (status_data["_wiq_score"] >= 90) & (status_data["_wiq_score"] < 100),
            "KPI status",
        ] = "Watch"
        status_data.loc[valid & (status_data["_wiq_score"] < 90), "KPI status"] = "Below Target"

    status_counts = (
        status_data["KPI status"].value_counts(dropna=False)
        .rename_axis("KPI status")
        .reset_index(name="Records")
    )
    total = int(status_counts["Records"].sum())
    status_counts["Share (%)"] = status_counts["Records"] / total * 100 if total else 0

    metric_cols = st.columns(3)
    for col, label in zip(metric_cols, ["On Target", "Watch", "Below Target"]):
        count = int(status_data["KPI status"].eq(label).sum())
        share = count / total * 100 if total else 0
        col.metric(label, f"{count:,}", f"{share:.1f}% of records")

    status_left, status_right = st.columns([1, 1.4])
    with status_left:
        status_fig = px.pie(
            status_counts, names="KPI status", values="Records",
            hole=0.55, title="KPI status distribution",
        )
        st.plotly_chart(status_fig, use_container_width=True)
    with status_right:
        st.dataframe(status_counts.round(2), use_container_width=True, hide_index=True)

    if record_department_col and department_id_col and department_name_col:
        status_dept = status_data.merge(
            departments[[department_id_col, department_name_col]].drop_duplicates(
                subset=[department_id_col]
            ).rename(columns={
                department_id_col: "_wiq_status_dept_id",
                department_name_col: "Department",
            }),
            left_on=record_department_col,
            right_on="_wiq_status_dept_id",
            how="left",
        )
        status_dept["Department"] = status_dept["Department"].fillna("Unknown")
        status_summary = (
            status_dept.groupby(["Department", "KPI status"], as_index=False)
            .size().rename(columns={"size": "Records"})
        )
        st.subheader("KPI status by department")
        status_dept_fig = px.bar(
            status_summary, x="Department", y="Records", color="KPI status",
            barmode="stack", title="KPI records by status and department",
        )
        st.plotly_chart(status_dept_fig, use_container_width=True)

    st.download_button(
        "Download filtered KPI status data (CSV)",
        data=status_data.to_csv(index=False).encode("utf-8"),
        file_name="workforceiq_kpi_status.csv",
        mime="text/csv",
    )
else:
    st.info("KPI status breakdown requires performance records and a numeric achievement column.")


# ==================================================
# DEPARTMENT PERFORMANCE RANKING
# ==================================================
st.divider()
st.subheader("Department performance ranking")
st.caption(
    "Descriptive, unweighted average across KPI records. Departments may "
    "use different KPIs, so this is not a definitive employee-quality score."
)

if (
    record_department_col and record_score_col
    and department_id_col and department_name_col
):
    dept_perf = (
        filtered_records.groupby(record_department_col, as_index=False)
        .agg(
            average_achievement_pct=(record_score_col, "mean"),
            kpi_records=(record_score_col, "count"),
        )
        .rename(columns={record_department_col: "_wiq_department_id"})
    )

    if record_employee_col:
        employee_counts = (
            filtered_records.groupby(record_department_col)[record_employee_col]
            .nunique()
            .rename("employees")
            .reset_index()
            .rename(columns={record_department_col: "_wiq_department_id"})
        )
        dept_perf = dept_perf.merge(
            employee_counts, on="_wiq_department_id", how="left"
        )

    dept_names = departments[
        [department_id_col, department_name_col]
    ].drop_duplicates(subset=[department_id_col]).rename(
        columns={
            department_id_col: "_wiq_department_id",
            department_name_col: "Department",
        }
    )
    dept_perf = dept_perf.merge(dept_names, on="_wiq_department_id", how="left")
    dept_perf["Department"] = dept_perf["Department"].fillna("Unknown").astype(str)
    dept_perf = dept_perf.sort_values(
        "average_achievement_pct", ascending=False
    ).reset_index(drop=True)
    dept_perf.insert(0, "Rank", range(1, len(dept_perf) + 1))

    display_cols = ["Rank", "Department"]
    if "employees" in dept_perf.columns:
        display_cols.append("employees")
    display_cols += ["kpi_records", "average_achievement_pct"]

    rank_table = dept_perf[display_cols].rename(
        columns={
            "employees": "Employees",
            "kpi_records": "KPI records",
            "average_achievement_pct": "Average achievement (%)",
        }
    )
    rank_left, rank_right = st.columns([1, 1.5])
    with rank_left:
        st.dataframe(rank_table.round(2), use_container_width=True, hide_index=True)
    with rank_right:
        rank_chart = px.bar(
            dept_perf.sort_values("average_achievement_pct"),
            x="average_achievement_pct",
            y="Department",
            orientation="h",
            title="Average KPI achievement by department",
            labels={"average_achievement_pct": "Average achievement (%)"},
        )
        st.plotly_chart(rank_chart, use_container_width=True)
else:
    st.info("Department ranking requires department IDs and achievement_pct.")


# ==================================================
# KPI TARGET VS ACTUAL
# ==================================================
st.divider()
st.subheader("KPI target vs actual")
st.caption(
    "Values are compared within each KPI because KPIs may use different units. "
    "This uses target_value and actual_value stored on performance records."
)

if (
    record_kpi_id_col and record_actual_col and record_target_col
    and kpi_definition_id_col and kpi_name_col
    and not filtered_records.empty
):
    kpi_names = (
        kpi_definitions[[kpi_definition_id_col, kpi_name_col]]
        .drop_duplicates(subset=[kpi_definition_id_col])
        .rename(
            columns={
                kpi_definition_id_col: "_wiq_kpi_id",
                kpi_name_col: "KPI",
            }
        )
    )

    compare_cols = [record_kpi_id_col, record_actual_col, record_target_col]
    if record_unit_col:
        compare_cols.append(record_unit_col)
    compare = filtered_records[compare_cols].copy()

    compare["_wiq_actual"] = pd.to_numeric(compare[record_actual_col], errors="coerce")
    compare["_wiq_target"] = pd.to_numeric(compare[record_target_col], errors="coerce")
    compare = compare.dropna(subset=["_wiq_actual", "_wiq_target"])
    compare = compare.rename(columns={record_kpi_id_col: "_wiq_kpi_id"})
    compare = compare.merge(kpi_names, on="_wiq_kpi_id", how="left")
    compare["KPI"] = compare["KPI"].fillna(compare["_wiq_kpi_id"].astype(str))

    kpi_summary = (
        compare.groupby(["_wiq_kpi_id", "KPI"], as_index=False)
        .agg(
            Average_actual=("_wiq_actual", "mean"),
            Average_target=("_wiq_target", "mean"),
            Records=("_wiq_actual", "count"),
        )
    )
    kpi_summary["Actual_minus_target"] = (
        kpi_summary["Average_actual"] - kpi_summary["Average_target"]
    )

    if record_unit_col and record_unit_col in compare.columns:
        unit_lookup = compare[
            ["_wiq_kpi_id", record_unit_col]
        ].drop_duplicates(subset=["_wiq_kpi_id"]).rename(
            columns={record_unit_col: "Unit"}
        )
        kpi_summary = kpi_summary.merge(
            unit_lookup, on="_wiq_kpi_id", how="left"
        )

    if not kpi_summary.empty:
        selected_kpi = st.selectbox(
            "Choose a KPI",
            sorted(kpi_summary["KPI"].astype(str).unique().tolist()),
        )
        selected_row = kpi_summary[
            kpi_summary["KPI"].astype(str) == selected_kpi
        ].iloc[0]

        actual_metric, target_metric, gap_metric = st.columns(3)
        actual_metric.metric("Average actual", f"{selected_row['Average_actual']:,.2f}")
        target_metric.metric("Average target", f"{selected_row['Average_target']:,.2f}")
        gap_metric.metric(
            "Actual minus target",
            f"{selected_row['Actual_minus_target']:+,.2f}",
        )

        selected_chart_data = pd.DataFrame({
            "Measure": ["Average actual", "Average target"],
            "Value": [
                selected_row["Average_actual"],
                selected_row["Average_target"],
            ],
        })
        target_fig = px.bar(
            selected_chart_data,
            x="Measure",
            y="Value",
            title=f"Average target vs actual — {selected_kpi}",
            text_auto=".2f",
        )
        st.plotly_chart(target_fig, use_container_width=True)

        table_cols = [
            "KPI", "Average_actual", "Average_target",
            "Actual_minus_target", "Records",
        ]
        if "Unit" in kpi_summary.columns:
            table_cols.insert(1, "Unit")

        st.subheader("All KPI comparisons")
        st.dataframe(
            kpi_summary[table_cols].rename(
                columns={
                    "Average_actual": "Average actual",
                    "Average_target": "Average target",
                    "Actual_minus_target": "Actual - target",
                }
            ).round(2),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No numeric actual/target values were found.")
else:
    st.info(
        "Target vs actual needs kpi_id, actual_value, target_value, "
        "and KPI names in kpi_definitions."
    )


st.subheader("Performance trend")

if record_date_col and record_score_col and not filtered_records.empty:
    trend = filtered_records[[record_date_col, record_score_col]].copy()

    # reporting_month can be a SQL date or text such as YYYY-MM.
    trend["_wiq_date"] = pd.to_datetime(
        trend[record_date_col].astype(str),
        errors="coerce",
    )
    trend["_wiq_score"] = pd.to_numeric(
        trend[record_score_col],
        errors="coerce",
    )
    trend = trend.dropna(subset=["_wiq_date", "_wiq_score"])

    if not trend.empty:
        trend["Period"] = trend["_wiq_date"].dt.to_period("M").astype(str)
        trend_summary = (
            trend.groupby("Period", as_index=False)["_wiq_score"]
            .mean()
            .sort_values("Period")
        )

        fig = px.line(
            trend_summary,
            x="Period",
            y="_wiq_score",
            markers=True,
            title="Monthly Average KPI Achievement",
        )
        fig.update_layout(
            xaxis_title="Reporting month",
            yaxis_title="Average KPI achievement (%)",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(
            "The reporting_month values could not be parsed as dates. "
            "Check their format in the database."
        )
else:
    st.info(
        "A reporting month and numeric achievement percentage are required "
        "to display the performance trend."
    )


st.subheader("Employee directory")
search_text = st.text_input("Search employees", placeholder="Search across employee fields...")
employee_view = filtered_employees.copy()
if search_text.strip():
    mask = employee_view.astype(str).apply(
        lambda col: col.str.contains(search_text.strip(), case=False, na=False, regex=False)
    ).any(axis=1)
    employee_view = employee_view[mask]
st.caption(f"Showing {len(employee_view):,} employees")
st.dataframe(employee_view, use_container_width=True, hide_index=True)
st.download_button(
    "Download employee directory (CSV)",
    data=employee_view.to_csv(index=False).encode("utf-8"),
    file_name="workforceiq_employee_directory.csv",
    mime="text/csv",
)

st.divider()
st.subheader("WorkforceIQ AI Analyst")
st.write("Ask about workforce performance. The AI receives aggregate summaries, not the full employee table.")

with st.expander("Quick workforce insights", expanded=True):
    if record_score_col and not filtered_records.empty:
        insight_scores = pd.to_numeric(
            filtered_records[record_score_col], errors="coerce"
        ).dropna()
        if not insight_scores.empty:
            insight_cols = st.columns(3)
            insight_cols[0].metric("Average achievement", f"{insight_scores.mean():.2f}%")
            insight_cols[1].metric("Median achievement", f"{insight_scores.median():.2f}%")
            insight_cols[2].metric(
                "Records at/above 100%",
                f"{int((insight_scores >= 100).sum()):,}",
                f"{(insight_scores >= 100).mean() * 100:.1f}% of valid records",
            )
            st.caption(
                "Descriptive statistics for the current filters; they do not establish causes."
            )
        else:
            st.info("No numeric achievement values are available for the current filters.")
    else:
        st.info("No performance records are available for quick insights.")

question = st.text_area(
    "Your question",
    placeholder="Example: How many employees are in each department?",
    height=90,
)

if st.button("Ask AI Analyst", type="primary"):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.warning("GEMINI_API_KEY is not set in your .env file.")
    elif not question.strip():
        st.warning("Enter a question first.")
    else:
        try:
            from google import genai

            context_parts = [
                f"Filtered employee count: {len(filtered_employees)}",
                f"Filtered performance record count: {len(filtered_records)}",
                f"Employee columns: {list(filtered_employees.columns)}",
                f"Performance record columns: {list(filtered_records.columns)}",
            ]
            if record_score_col and not filtered_records.empty:
                numeric_scores = pd.to_numeric(
                    filtered_records[record_score_col], errors="coerce"
                ).dropna()
                if not numeric_scores.empty:
                    context_parts.append(f"Average performance score: {numeric_scores.mean():.2f}")

            if department_filter_available:
                dept_data = filtered_employees.merge(
                    lookup,
                    left_on=employee_dept_col,
                    right_on="_wiq_department_join_id",
                    how="left",
                )
                dept_summary = (
                    dept_data["_wiq_department_label"].fillna("Unknown").astype(str)
                    .value_counts().to_dict()
                )
                context_parts.append(f"Employee counts by department: {dept_summary}")

            prompt = (
                "You are WorkforceIQ AI, a workforce analytics assistant. "
                "Use only the supplied context; do not invent statistics or claim causation. "
                "If context is insufficient, explain what data is needed.\n\n"
                f"Dashboard context:\n{chr(10).join(context_parts)}\n\n"
                f"User question: {question.strip()}"
            )
            client = genai.Client(api_key=api_key)
            with st.spinner("Analyzing workforce data..."):
                response = client.models.generate_content(
                    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                    contents=prompt,
                )
            st.markdown("### AI response")
            st.write(response.text or "The AI returned an empty response.")
        except Exception as exc:
            st.error("The AI analyst could not complete the request.")
            with st.expander("Technical details"):
                st.code(str(exc))

with st.expander("Database schema diagnostics"):
    st.write("Employees columns")
    st.code(", ".join(map(str, employees.columns)))
    st.write("Departments columns")
    st.code(", ".join(map(str, departments.columns)))
    st.write("Performance records columns")
    st.code(", ".join(map(str, records.columns)))
    st.write("KPI definitions columns")
    st.code(", ".join(map(str, kpi_definitions.columns)))
    st.write("Detected columns")
    st.json({
        "employee_id": str(employee_id_col),
        "employee_department_id": str(employee_dept_col),
        "department_id": str(department_id_col),
        "department_name": str(department_name_col),
        "performance_employee_id": str(record_employee_col),
        "performance_score": str(record_score_col),
        "performance_date": str(record_date_col),
        "performance_status": str(record_status_col),
        "kpi_id": str(record_kpi_id_col),
        "actual_value": str(record_actual_col),
        "target_value": str(record_target_col),
    })

st.caption("WorkforceIQ AI • Metrics reflect data currently available in MySQL.")
