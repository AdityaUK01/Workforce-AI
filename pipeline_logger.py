import logging
from pathlib import Path

# Create logs folder
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "pipeline.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
    force=True,
)

logger = logging.getLogger("WorkforceIQ")


def pipeline_started():
    logger.info("=" * 60)
    logger.info("WorkforceIQ AI pipeline started")


def pipeline_succeeded():
    logger.info("Pipeline completed successfully")
    logger.info("=" * 60)


def pipeline_failed(error):
    logger.exception("Pipeline failed: %s", error)
    logger.info("=" * 60)


if __name__ == "__main__":
    pipeline_started()
    pipeline_succeeded()
