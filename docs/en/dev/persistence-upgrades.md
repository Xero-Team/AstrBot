# Persistence Upgrade and Migration

This page is the contract for how AstrBot handles persistent state across
versions. Read it before changing a database model, a configuration key, or a
data directory layout.

> **Status: implemented.** The per-store runner, ledger, main-database reshape,
> and legacy import have landed. The main database is now `data/astrbot.db`; on
> first startup the old `data/data_v4.db` is imported once and left on disk as a
> backup.

## Goal

AstrBot uses **data-preserving upgrades**: on startup, each persistent store is
brought to the current schema by replaying ordered, recorded migrations, with no
manual deletion. The point is not to ship a script per release. The point is a
deterministic, recoverable startup step where:

- the current state of a store comes from the store itself, never inferred from
  filenames or release numbers;
- a partially applied upgrade is impossible to observe;
- a failure stops startup loudly instead of silently drifting.

## Why not release-version scripts

The earlier idea of one script per release (`mig_4.28.1to4.28.2.py`) is
rejected. It cannot answer the only question that matters — "which changes has
this store already seen?" — for a user who skips versions, applies a hotfix, or
runs a fork build. Mapping release numbers to migration steps also breaks when
one release carries several changes or when a change ships outside a release.

Every production migration tool agrees on the alternative: a monotonic step
identity plus a ledger recording what ran.

### Prior art

| System           | Applied-state store                      | Step identity             | Rollback                                | Lesson we adopt                                                       |
| ---------------- | ---------------------------------------- | ------------------------- | --------------------------------------- | --------------------------------------------------------------------- |
| Django           | `django_migrations` table                | increasing number / graph | rarely used                             | detect and merge concurrent branches                                  |
| Alembic          | `alembic_version` table                  | revision chain            | hand-written `downgrade()`, seldom used | autogeneration must be reviewed; the chain is data                    |
| Flyway           | `flyway_schema_history`                  | `V1__`, `V2__`            | `undo` is paid-only                     | checksum mismatch on an applied script refuses to run                 |
| Liquibase        | `DATABASECHANGELOG`                      | changeset id + author     | supported                               | checksum detects drift                                                |
| golang-migrate   | `schema_migrations` + dirty flag         | timestamp                 | hand-written `down`                     | a failed step leaves a dirty state that must be cleared explicitly    |
| Home Assistant   | config entry `version` / `minor_version` | major + minor             | none; restore from backup               | migration failure enters a distinct error state instead of continuing |
| Homegrown SQLite | `PRAGMA user_version`                    | increasing integer        | none                                    | wrap steps in transactions                                            |

Cross-tool consensus, which this design follows:

1. Applied state lives in the managed store, not in metadata about how the
   store was shipped.
2. Ordering uses a monotonic step identity, not the application version.
   Flyway's `V1` is a migration number, not `4.28.1`.
3. Forward-only. Rollback is restore-from-backup.
4. Each applied step records a checksum, so editing an applied script is
   detected.
5. One transaction per step.
6. Failure is visible and stops startup.
7. Migrations run before the app serves traffic, serialized on a single owner.
8. Destructive changes are split into expand and contract steps.

Anti-patterns confirmed by the same sources: release-version filenames,
signatures over migration scripts without a key-distribution story, hashing a
whole module to decide what ran, and relying on `down` scripts for rollback.

## Design

### One sequence per physical store

Each persistent surface has its own sequence and its own ledger, because they
change on independent timelines. There is no single global version — that was
exactly the flaw in the old `config_version` and `data_v4` scheme.

| Store id | Location                    | Current entry point                                    |
| -------- | --------------------------- | ------------------------------------------------------ |
| `main`   | `data/astrbot.db`           | `astrbot/core/db/schema.py` `initialize_sqlite_schema` |
| `kb`     | `data/knowledge_base/kb.db` | `KBSQLiteDatabase.initialize`                          |
| `doc`    | `<kb>/doc.db`               | `DocumentStorage.initialize`                           |
| `config` | `data/cmd_config.json`      | `AstrBotConfig.__init__`                               |

`data/astrbot.db` is this fork's new main-database name. The old
`data/data_v4.db` is no longer opened directly; it is imported once on first
startup (see [Legacy import](#legacy-import)).

### Revision and ledger

- Each store has a **monotonic integer `revision`**, starting at 1, only
  increasing. It is not an application version.
- SQLite stores use a ledger table so the record carries a description and a
  checksum, which a single `user_version` integer cannot:

```sql
CREATE TABLE IF NOT EXISTS _schema_migrations (
    store       TEXT    NOT NULL,
    revision    INTEGER NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    checksum    TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL,
    PRIMARY KEY (store, revision)
);
```

- The `config` store is a file, so its ledger is an integer
  `schema_revision` inside `cmd_config.json`, with the same semantics. Because a
  file cannot share the SQLite transaction, the migrated values and
  `schema_revision` are written in one atomic snapshot through
  `AstrBotConfig.save_config` (temporary file, `fsync`, `os.replace`); never
  write the revision and the values as two separate files. A non-integer,
  boolean, or negative revision is treated as unset and migrated; a revision
  newer than the code refuses startup.

### Step modules

```text
astrbot/core/db/migrations/
  __init__.py
  runner.py     # shared executor: run_migrations / Migration
  main.py       # main store sequence MIGRATIONS
  kb.py         # knowledge-base metadata sequence MIGRATIONS
  doc.py        # document store sequence MIGRATIONS
  bootstrap.py  # one-time data_v4.db import
astrbot/core/config/migrations/
  __init__.py   # migrate_config_dict / CONFIG_SCHEMA_REVISION
```

Each store module exports a `MIGRATIONS` tuple ordered by revision. A step
carries its identity and one forward function:

```python
async def _add_duration_ms(conn: AsyncConnection) -> None:
    await conn.exec_driver_sql(
        "ALTER TABLE provider_stats ADD COLUMN duration_ms INTEGER",
    )


MIGRATIONS = (
    Migration(1, "create current schema", _initial_schema),
    Migration(2, "add provider_stats.duration_ms", _add_duration_ms),
)
```

- Ordering uses `revision` only; filenames and tuple position are for humans.
- One step does one thing. A destructive change is split into expand and
  contract steps.
- No `downgrade`.
- `upgrade` receives one open `AsyncConnection` and runs SQL inside it.

### Runner behavior

`run_migrations(engine, store, steps)` does:

1. Validate the sequence (unique revisions, all `>= 1`).
2. Ensure `_schema_migrations` exists.
3. Read the store's applied revisions; `current = max(applied)`, or 0.
4. If `current` is higher than the code's maximum revision, fail immediately
   with a restore-or-upgrade hint.
5. Verify every applied step's checksum against the code; a missing or changed
   step, or a gap in the applied revisions, fails startup. The pending steps
   must also bridge `current + 1` to the head without a hole, so a declared gap
   is rejected before any step runs instead of applying the later steps and then
   failing the next startup's ledger check.
6. For each `revision > current`, ascending:
   - emit a driver-level `BEGIN`;
   - run `upgrade(conn)`, then write the ledger row;
   - `COMMIT` on success; on failure `ROLLBACK`, raise, and stop startup.
7. No pending steps means a no-op.

Implementation notes:

- The ledger row commits in the same transaction as the step, so a crash cannot
  record a step that only half-applied.
- SQLite does **not** roll back DDL under `engine.begin()` (pysqlite only opens a
  transaction before DML). The runner therefore uses an explicit driver-level
  `BEGIN` to put DDL and the ledger row in one transaction instead. Do not change
  it back to `engine.begin()`.
- The checksum is the `sha256` of the `upgrade` source, detecting edits to an
  applied step. **Editing an applied step fails startup**; that is intentional.
- A failure refuses startup instead of continuing in a drifting state. This is
  the Home Assistant `MIGRATION_ERROR` idea, made strict because there is no
  running UI to surface it.
- No signatures. Without a key-distribution chain, signing scripts is theater;
  a checksum is the honest tool.

### Concurrency and timing

- Migrations run serially and asynchronously before any read or write: inside
  each store's `initialize()`, and for config before `AstrBotConfig` first reads
  a value.
- Each store's `initialize()` guards with a lock so it runs once per process;
  process-level serialization comes from the startup order.
- `config` migration runs before logging is configured, because log settings
  come from config.

### Relationship to `create_all`

`create_all` still creates missing tables; migrations handle the difference
between an old store and the current one. The alternative — dropping
`create_all` and letting migration step `0001` own table creation — would
duplicate the 35-table schema definition and split the source of truth, so it
is rejected. Today `main/0001` is itself the `create_all` baseline step. The
cost of keeping `create_all` is that "a fresh store" and "a migrated store" must
be proven equivalent; see [Verification](#verification).

### Legacy import

The old main database `data/data_v4.db` has the pre-reshape shape (no surrogate
`id`, no foreign keys, different timestamp ordering). Because there are no
historical users to replay version-by-version, the reshape is a one-time import
rather than several SQLite steps:

1. It runs when the target `data/astrbot.db` is empty and `data/data_v4.db`
   exists.
2. `run_migrations` first creates the current schema and records `main`
   revision 1.
3. Legacy rows are read table by table in `SQLModel.metadata.sorted_tables`
   dependency order.
4. `LEGACY_COLUMN_RENAMES` maps renamed columns (five tables' `inner_*` to
   `id`).
5. Legacy columns absent from the target are dropped; NOT NULL target columns
   that carry a Python default and are missing from the legacy row (for example
   the timestamps later added to `session_project_relations`) are filled in.
6. The whole copy runs in **one transaction** with `PRAGMA foreign_keys=OFF`
   temporarily, because legacy rows may reference parents that no longer exist.
7. Rows are inserted with driver-level parameters to keep SQLite's on-disk
   representation: legacy `DATETIME` columns hold ISO text and legacy `JSON`
   columns hold JSON text, which is exactly what the current columns expect.
   Routing through SQLAlchemy bind processors would instead reject that
   already-serialized text.
8. The copied rows and an import-completion ledger row
   (`main_legacy_import`) commit in the **same transaction**, so a crash cannot
   record a completed import that only half-copied.
9. `SQLiteDatabase.initialize()` retries the import when the completion marker
   is absent and no user rows exist, so a crash between the baseline schema and
   the copy does not leave a silently empty store.
10. The legacy file is kept on disk as a backup; it is not deleted.

`SQLiteDatabase` imports only when the caller passes a legacy path explicitly.
`runtime_services` passes `LEGACY_DB_PATH`; tests and secondary stores pass
`None`, so they never read the checkout's `data/`.

## Contributor rules

1. **A schema or config-shape change is a breaking change that needs a step.**
   Append a new revision with its `upgrade` function to the right store's
   `MIGRATIONS`. Do not mutate an applied step; its checksum would fail startup.
2. **Declare the current schema on the model.** Columns, generated columns,
   unique constraints, and ordinary indexes live on the SQLModel definition so
   a fresh store is correct. Migration steps only bridge old stores forward.
3. **Never swallow migration errors.** A failure must abort startup, not hide
   in a bare `try/except: pass`.
4. **One step, one change.** Split destructive changes into expand then
   contract. Take the pre-step snapshot before anything irreversible.
5. **Keep the backup path current.** Update the export/import maps in
   `astrbot/core/backup/` when a table or column changes.
6. **Delete obsolete conversion code.** Once a step covers all reachable old
   versions, remove the loading-time shim it replaced.
7. **Add tests.** A new step needs: fresh store to head, re-run no-op, edited
   applied step fails, and rollback leaves the ledger unchanged. A schema change
   also updates the schema-equivalence test.

## Verification

These tests lock the migration system:

- `tests/unit/db/test_migrations_runner.py`: fresh run, no-op re-run, checksum
  drift, store ahead of code, missing step, ledger gap, declared-sequence gap,
  failed-step rollback.
- `tests/unit/db/test_migrations_equivalence.py`: a `create_all` store and a
  store migrated to head have identical tables, columns, indexes, unique
  constraints, and foreign keys.
- `tests/unit/db/test_migrations_bootstrap.py`: an old-shape `data_v4.db`
  imports into `astrbot.db`, covering column renames, dropped legacy columns,
  filled new NOT NULL defaults, and preserved JSON/timestamp types; no import
  happens without an explicit legacy path.
- `tests/unit/db/test_foreign_keys.py`: `PRAGMA foreign_keys=ON` is enforced and
  deleting a parent cascades to children.
- `tests/unit/test_config_migrations.py`: flat legacy config moves to groups,
  keeps user values, is idempotent, and writes back `schema_revision` on load.

## Related pages

- [Project Architecture](./architecture) — storage layout and startup order.
- [AstrBot Configuration File](./astrbot-config) — the config surface.
- [Backup and restore](/en/deploy/astrbot/backup) — the supported way to carry
  data between installs.
