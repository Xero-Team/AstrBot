"""Apply ordered, recorded SQLite migrations for one persistent store.

Each persistent store owns a sequence of forward-only migrations with a
monotonic integer ``revision``. Applied state lives in the store's own
``_schema_migrations`` ledger, so the store reports where it is; startup never
infers it from filenames or release numbers.

The runner is deliberately small: it validates the sequence, refuses to run
when an applied step changed or the store is ahead of the code, and applies
each pending step in its own transaction together with its ledger row. It does
not write ``downgrade``; rollback is restore-from-backup.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger("astrbot")

LEDGER_TABLE = "_schema_migrations"

_LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    store       TEXT    NOT NULL,
    revision    INTEGER NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    checksum    TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL,
    PRIMARY KEY (store, revision)
)
"""


class MigrationError(RuntimeError):
    """Raised when a migration sequence cannot be applied safely."""


@dataclass(frozen=True)
class Migration:
    """One forward-only migration step for a store.

    Attributes:
        revision: Monotonic revision, starting at 1.
        description: Short human-readable summary.
        upgrade: Async callable taking an open connection and performing the
            forward change. It runs inside a transaction with the ledger row.
    """

    revision: int
    description: str
    upgrade: Callable[[AsyncConnection], Awaitable[None]]

    @property
    def checksum(self) -> str:
        """Return the sha256 of the step source, detecting later edits."""
        source = inspect.getsource(self.upgrade)
        return hashlib.sha256(source.encode("utf-8")).hexdigest()


async def _ensure_ledger(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(_LEDGER_DDL))


async def _load_applied(
    engine: AsyncEngine,
    store: str,
) -> dict[int, tuple[str, str]]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    f"SELECT revision, checksum, applied_at FROM {LEDGER_TABLE} "
                    "WHERE store = :store",
                ),
                {"store": store},
            )
        ).fetchall()
    return {int(row[0]): (str(row[1]), str(row[2])) for row in rows}


def _validate_sequence(steps: Sequence[Migration]) -> list[Migration]:
    ordered = sorted(steps, key=lambda step: step.revision)
    revisions = [step.revision for step in ordered]
    if len(set(revisions)) != len(revisions):
        raise MigrationError("duplicate migration revision in store sequence")
    if revisions and revisions[0] < 1:
        raise MigrationError("migration revision must be >= 1")
    return ordered


async def run_migrations(
    engine: AsyncEngine,
    store: str,
    steps: Sequence[Migration],
) -> int:
    """Bring one store to the code's head revision.

    Args:
        engine: Async engine bound to the store's SQLite file.
        store: Stable store id, for example ``main``, ``kb`` or ``doc``.
        steps: The store's migration sequence, in any order.

    Returns:
        The number of migrations applied.

    Raises:
        MigrationError: When an applied step is missing or changed, the store is
            newer than the code, or the sequence is malformed.
    """
    ordered = _validate_sequence(steps)
    await _ensure_ledger(engine)
    applied = await _load_applied(engine, store)
    head = ordered[-1].revision if ordered else 0
    current = max(applied, default=0)

    if current > head:
        raise MigrationError(
            f"store {store!r} is at revision {current}, newer than this build's "
            f"{head}; restore a backup or upgrade the application",
        )

    if applied and set(applied) != set(range(1, current + 1)):
        # A contiguous ledger is the invariant of forward-only revisions. A gap
        # would otherwise let ``current`` skip an unapplied step silently.
        raise MigrationError(
            f"store {store!r} has a gap in its applied revisions; restore a backup",
        )

    pending = [step.revision for step in ordered if step.revision > current]
    if pending != list(range(current + 1, head + 1)):
        # The steps about to run must bridge ``current`` to ``head`` without a
        # hole. Otherwise a first startup applies the later steps and writes a
        # gapped ledger, and every following startup fails the check above.
        raise MigrationError(
            f"store {store!r} migration sequence has a gap between revision "
            f"{current + 1} and {head}; restore a backup or fix the build",
        )

    by_revision = {step.revision: step for step in ordered}
    for revision in sorted(applied):
        step = by_revision.get(revision)
        if step is None:
            raise MigrationError(
                f"applied migration {revision} for store {store!r} is missing "
                "from this build",
            )
        if step.checksum != applied[revision][0]:
            raise MigrationError(
                f"migration {revision} for store {store!r} changed after it was "
                "applied; refusing to start",
            )

    applied_count = 0
    for step in ordered:
        if step.revision <= current:
            continue
        await _apply_step(engine, store, step)
        logger.info(
            "applied migration %s rev %s (%s)",
            store,
            step.revision,
            step.description,
        )
        applied_count += 1
    return applied_count


async def _apply_step(
    engine: AsyncEngine,
    store: str,
    step: Migration,
) -> None:
    """Run one step and its ledger row in a single DDL-covering transaction.

    pysqlite only opens a transaction before DML, so ``engine.begin()`` would
    commit a bare ``CREATE TABLE`` even when the block raises. We emit an
    explicit ``BEGIN`` at the driver level so SQLite rolls back schema changes
    together with the ledger row.
    """
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            await step.upgrade(conn)
            await conn.execute(
                text(
                    f"INSERT INTO {LEDGER_TABLE}"
                    "(store, revision, description, checksum, applied_at) "
                    "VALUES (:store, :revision, :description, :checksum, :applied_at)",
                ),
                {
                    "store": store,
                    "revision": step.revision,
                    "description": step.description,
                    "checksum": step.checksum,
                    "applied_at": datetime.now(UTC).isoformat(),
                },
            )
        except BaseException:
            await conn.exec_driver_sql("ROLLBACK")
            raise
        else:
            await conn.exec_driver_sql("COMMIT")
