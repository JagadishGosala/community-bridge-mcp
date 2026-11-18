import logging
import sys

from cb import config, db, seed

log = logging.getLogger(__name__)


def main() -> None:
    """cb-reset: recreate the database file with the schema and seed data (A-17)."""
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        if p.exists():
            p.unlink()
            log.info("deleted %s", p)

    # connect() uses mode=rw and never creates the file, so create it empty here.
    path.touch()
    conn = db.connect(path)
    try:
        with db.transaction(conn):
            db.create_schema(conn)
            seed.insert_seed(conn)
    finally:
        conn.close()
    log.info("created schema and seed data in %s", path.resolve())
