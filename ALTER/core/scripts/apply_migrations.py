from __future__ import annotations

import os
from pathlib import Path

from psycopg import connect


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def apply_migration(dsn: str, path: Path) -> None:
    """Apply one migration in autocommit mode for concurrent index builds."""
    sql = path.read_text(encoding="utf-8").strip()
    if not sql:
        return
    with connect(dsn, autocommit=True) as conn:
        conn.execute(sql)


def main() -> None:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is required to apply ALTER migrations.")
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migrations:
        raise SystemExit("No ALTER migrations were found.")
    for migration in migrations:
        apply_migration(dsn, migration)
        print(f"Applied {migration.name}")


if __name__ == "__main__":
    main()
