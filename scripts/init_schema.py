import logging
import os
import sys
from contextlib import closing
from pathlib import Path


os.environ["SKIP_SCHEMA_INIT"] = "0"
os.environ.setdefault("RUN_SCHEMA_MIGRATIONS_ON_STARTUP", "1")
os.environ.setdefault("STRICT_SCHEMA_INIT", "1")
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.database import get_connection


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("gentstation.schema_init")


def main():
    logger.info("Initializing PostgreSQL schema...")
    with closing(get_connection()) as conn:
        conn.rollback()
    logger.info("PostgreSQL schema is ready.")


if __name__ == "__main__":
    main()
