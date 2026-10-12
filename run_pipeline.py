
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports"

LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "orchestrator.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)

logger = logging.getLogger("workforceiq.orchestrator")


def run_step(name: str, script: str) -> bool:
    """Run a script and verify its success."""

    script_path = BASE_DIR / script

    if not script_path.is_file():
        logger.error("%s: script not found: %s", name, script_path)
        return False

    command = [sys.executable, str(script_path)]

    # Safely validate data without loading it into MySQL.
    if script == "pipeline.py":
        command.append("--validate-only")

    logger.info("=" * 60)
    logger.info("STARTING: %s", name)
    logger.info("Command: %s", subprocess.list2cmdline(command))

    try:
        result = subprocess.run(
            command,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Display output in the terminal.
        if stdout:
            print(stdout, end="" if stdout.endswith("\n") else "\n")

        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n")

        # Save both output streams to the orchestrator log.
        if stdout.strip():
            logger.info("%s stdout:\n%s", name, stdout.rstrip())

        if stderr.strip():
            logger.info("%s stderr:\n%s", name, stderr.rstrip())

        # An unsuccessful process must never be marked as PASS.
        if result.returncode != 0:
            logger.error(
                "%s FAILED with exit code %s",
                name,
                result.returncode,
            )
            return False

        # Combine stdout and stderr because Python logging may write
        # its messages to stderr.
        output = stdout + "\n" + stderr

        if script == "pipeline.py":
            required_markers = [
                "Business checks failed: 0",
                "Score mismatches: 0",
                "Rows not safely comparable: 0",
                "Pipeline completed successfully",
            ]

            missing = [
                marker
                for marker in required_markers
                if marker not in output
            ]

            if missing:
                logger.error(
                    "%s did not confirm all required checks. "
                    "Missing markers: %s",
                    name,
                    ", ".join(missing),
                )
                return False

        elif script == "data_quality_summary.py":
            if "Overall status: PASS" not in output:
                logger.error(
                    "%s did not report Overall status: PASS",
                    name,
                )
                return False

        logger.info("%s PASSED", name)
        return True

    except subprocess.TimeoutExpired:
        logger.error("%s timed out after 600 seconds.", name)
        return False

    except Exception:
        logger.exception("%s failed unexpectedly.", name)
        return False


def main() -> int:
    started = datetime.now().astimezone()

    logger.info(
        "WorkforceIQ AI orchestration started at %s",
        started.isoformat(),
    )

    steps = [
        ("Structural and business validation", "pipeline.py"),
        ("Data quality summary", "data_quality_summary.py"),
    ]

    results: list[tuple[str, bool]] = []

    for name, script in steps:
        passed = run_step(name, script)
        results.append((name, passed))

        if not passed:
            logger.error(
                "Stopping orchestration because '%s' failed.",
                name,
            )
            break

    logger.info("=" * 60)
    logger.info("FINAL PIPELINE SUMMARY")

    for name, passed in results:
        logger.info(
            "%s: %s",
            name,
            "PASS" if passed else "FAIL",
        )

    success = (
        len(results) == len(steps)
        and all(passed for _, passed in results)
    )

    finished = datetime.now().astimezone()
    duration = (finished - started).total_seconds()

    logger.info("Duration: %.2f seconds", duration)
    logger.info("Log file: %s", LOG_FILE)
    logger.info(
        "FINAL STATUS: %s",
        "SUCCESS" if success else "FAILED",
    )

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
