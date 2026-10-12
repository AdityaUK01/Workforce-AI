from pathlib import Path
from getpass import getpass

import pandas as pd
import mysql.connector

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

TABLE_FILES = {
    "departments": "departments.csv",
    "roles": "roles.csv",
    "kpi_definitions": "kpi_definitions.csv",
    "kpi_targets": "kpi_targets.csv",
    "employees": "employees.csv",
    "performance_records": "performance_records_curated.csv",
}

# Explicit column order prevents accidental column misalignment.
COLUMNS = {
    "departments": [
        "department_id", "department_name", "business_function"
    ],
    "roles": [
        "role_id", "department_name", "role_name", "role_level"
    ],
    "kpi_definitions": [
        "kpi_id", "department_name", "kpi_name", "kpi_category",
        "unit", "better_direction", "default_target",
        "measurement_frequency"
    ],
    "kpi_targets": [
        "target_id", "role_id", "kpi_id", "target_value",
        "effective_from", "effective_to", "target_owner",
        "synthetic_record"
    ],
    "employees": [
        "employee_id", "employee_name", "department_id",
        "department_name", "role_id", "job_title",
        "manager_employee_id", "location", "employment_type",
        "hire_date", "employment_status", "synthetic_record"
    ],
    "performance_records": [
        "performance_record_id", "employee_id", "department_id",
        "role_id", "kpi_id", "reporting_month", "target_value",
        "actual_value", "unit", "better_direction",
        "achievement_pct", "performance_status", "source_type",
        "synthetic_record"
    ],
}


def python_value(value):
    """Convert Pandas missing values to SQL NULL."""
    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def main():
    password = getpass("Enter your MySQL password: ")

    connection = mysql.connector.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=password,
        database="workforceiq",
    )

    cursor = connection.cursor()

    try:
        # Preflight: read and validate every file before inserting.
        dataframes = {}

        for table, filename in TABLE_FILES.items():
            path = DATA_DIR / filename

            if not path.exists():
                raise FileNotFoundError(f"Missing file: {path}")

            df = pd.read_csv(path)

            missing_columns = set(COLUMNS[table]) - set(df.columns)
            if missing_columns:
                raise ValueError(
                    f"{filename} is missing columns: {missing_columns}"
                )

            dataframes[table] = df[COLUMNS[table]].copy()
            print(f"Prepared {table}: {len(df):,} rows")

        # Load parent tables before dependent tables.
        # Disable FK checks only during the controlled load transaction.
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        try:
            connection.start_transaction()

            # This loader expects empty tables.
            for table in TABLE_FILES:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                existing = cursor.fetchone()[0]

                if existing != 0:
                    raise RuntimeError(
                        f"Table {table} already has {existing} rows. "
                        "Stop and decide whether to reload or preserve them."
                    )

            for table in [
                "departments",
                "roles",
                "kpi_definitions",
                "kpi_targets",
                "employees",
                "performance_records",
            ]:
                df = dataframes[table]
                cols = COLUMNS[table]

                column_sql = ", ".join(f"`{c}`" for c in cols)
                placeholders = ", ".join(["%s"] * len(cols))

                sql = (
                    f"INSERT INTO `{table}` ({column_sql}) "
                    f"VALUES ({placeholders})"
                )

                rows = [
                    tuple(python_value(v) for v in row)
                    for row in df.itertuples(index=False, name=None)
                ]

                if rows:
                    cursor.executemany(sql, rows)

                print(f"Inserted {table}: {cursor.rowcount:,} rows")

            # Validate foreign-key relationships explicitly.
            relationship_checks = {
                "Invalid employee departments": """
                    SELECT COUNT(*)
                    FROM employees e
                    LEFT JOIN departments d
                      ON e.department_id = d.department_id
                    WHERE d.department_id IS NULL
                """,
                "Invalid employee roles": """
                    SELECT COUNT(*)
                    FROM employees e
                    LEFT JOIN roles r ON e.role_id = r.role_id
                    WHERE r.role_id IS NULL
                """,
                "Invalid employee managers": """
                    SELECT COUNT(*)
                    FROM employees e
                    LEFT JOIN employees m
                      ON e.manager_employee_id = m.employee_id
                    WHERE e.manager_employee_id IS NOT NULL
                      AND m.employee_id IS NULL
                """,
                "Invalid performance employees": """
                    SELECT COUNT(*)
                    FROM performance_records p
                    LEFT JOIN employees e ON p.employee_id = e.employee_id
                    WHERE e.employee_id IS NULL
                """,
                "Invalid performance KPIs": """
                    SELECT COUNT(*)
                    FROM performance_records p
                    LEFT JOIN kpi_definitions k ON p.kpi_id = k.kpi_id
                    WHERE k.kpi_id IS NULL
                """,
            }

            for label, query in relationship_checks.items():
                cursor.execute(query)
                failures = cursor.fetchone()[0]

                print(f"{label}: {failures}")

                if failures:
                    raise ValueError(
                        f"{label}: {failures} records failed validation"
                    )

            connection.commit()
            print("\nTransaction committed successfully.")

        except Exception:
            connection.rollback()
            print("Load failed; transaction rolled back.")
            raise

        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        # Verify final counts.
        print("\nFinal database row counts:")
        for table in TABLE_FILES:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            print(f"{table}: {cursor.fetchone()[0]:,}")

    finally:
        cursor.close()
        connection.close()
        print("\nDatabase connection closed.")


if __name__ == "__main__":
    main()
