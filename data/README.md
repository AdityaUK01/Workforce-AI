# WorkforceIQ AI — Synthetic Enterprise Workforce Dataset

## What this is
A generated, fictional enterprise-style dataset for a portfolio project demonstrating Data Engineering, business analytics, AI-assisted reporting, and dashboard development.

**All people, KPI observations, scores, targets, locations, and pipeline logs are synthetic. This is not real company data and must not be represented as real employment records.**

## Dataset size
- Employees: 720
- Departments: 8
- Roles: 24
- KPI definitions: 40
- Role-specific KPI targets: 120
- Monthly KPI performance records: 40,250
- Employee-month summaries: 8,050
- Pipeline run logs: 180
- Performance period: January–December 2025
- Pipeline run log period: July–December 2025

## Files
- `departments.csv`: department master
- `roles.csv`: role definitions by department
- `employees.csv`: synthetic employee master records
- `kpi_definitions.csv`: KPI categories, units, and whether higher/lower values are better
- `kpi_targets.csv`: role-specific target values
- `performance_records.csv`: one row per employee/KPI/month
- `employee_monthly_summary.csv`: unweighted employee-month summary for dashboards
- `pipeline_runs.csv`: synthetic pipeline run history with success/failure examples
- `data_dictionary.csv`: column-level index
- `workforceiq_dataset.xlsx`: workbook containing all tables as sheets

## Data modeling notes
- `employees.employee_id` is the employee key.
- `departments.department_id` links employees to departments.
- `roles.role_id` links employees and targets to role definitions.
- `kpi_definitions.kpi_id` identifies a KPI.
- `performance_records` references employee, department, role, and KPI keys.
- `achievement_pct` is direction-aware: for higher-is-better KPIs it is actual/target × 100; for lower-is-better KPIs it is target/actual × 100. Values are capped at 150 for analysis.
- `employee_monthly_summary.summary_score_0_100` is a simple unweighted demo summary capped at 100. It is not a validated employee appraisal score. For production-like scoring, define role-specific KPI weights and normalize measures carefully.
- `performance_status` uses thresholds: On Target >= 95%, Watch >= 80%, Below Target < 80%.
- Some employees have deliberately introduced synthetic performance changes in selected months to support anomaly detection demos. These are not causal claims.

## Suggested dashboard pages
1. Company overview: headcount, average KPI achievement, monthly trends.
2. Department analysis: department KPI performance and trend comparison.
3. Employee drill-down: role-specific KPI history.
4. KPI explorer: target vs actual by category and month.
5. Pipeline monitoring: run status, duration, rejected records.
6. AI analyst: natural-language questions answered using SQL-derived facts.

## Suggested engineering tasks
1. Load CSVs into MySQL with primary and foreign keys.
2. Add incremental-load and deduplication logic.
3. Create data-quality checks for missing keys, invalid targets, duplicate records, and out-of-range percentages.
4. Build Airflow DAGs for ingestion, validation, transformation, and aggregation.
5. Store curated outputs in Parquet on S3 (optional cloud phase).
6. Add an OpenAI API layer that calls approved analytics functions; don't allow arbitrary unrestricted SQL.
7. Build a Streamlit dashboard with filters and a public demo deployment.

## License / use
Generated for portfolio and educational use. No external dataset is embedded. Check applicable laws and policies before adapting the schema to real employee data.
