# Persistence Upgrade and Migration

This page is the contract for how AstrBot handles persistent state across
versions. Read it before changing a database model, a configuration key, or a
data directory layout.

> **Status: design. Not implemented yet.** The migration runner described here
> does not exist in the tree today. Until it lands, the current behavior is the
> rebuild-not-migrate fallback in
> [Before the migration system exists](#before-the-migration-system-exists).

## Goal

AstrBot is moving to **data-preserving upgrades**: on startup, each persistent
store is brought to the current schema by replaying ordered, recorded
migrations, with no manual deletion. The point is not to ship a script per
release. The point is a deterministic, recoverable startup step where:

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
| `main`   | `data/data_v4.db`           | `astrbot/core/db/schema.py` `initialize_sqlite_schema` |
| `kb`     | `data/knowledge_base/kb.db` | `KBSQLiteDatabase.initialize`                          |
| `doc`    | `<kb>/doc.db`               | `DocumentStorage.initialize`                           |
| `config` | `data/cmd_config.json`      | `AstrBotConfig.__init__`                               |

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
  `schema_revision` inside `cmd_config.json`, with the same semantics. A file
  cannot share the runner's SQLite transaction, so a step must write the
  migrated values and `schema_revision` in one atomic snapshot through
  `AstrBotConfig.save_config` (temporary file, `fsync`, `os.replace`); writing
  the revision and the values separately can leave them out of sync after a
  crash.

### Step modules

```text
astrbot/core/db/migrations/
  __init__.py
  runner.py          # shared executor
  main/0001_initial.py
  main/0002_....py
  kb/0001_initial.py
  doc/0001_initial.py
astrbot/core/config/migrations/
  0001_....py
```

A step exports its identity and one forward function:

```python
revision = 2
description = "add provider_stats.duration_ms"


def upgrade(conn) -> None: ...
```

- Ordering uses `revision` only. The `NNNN` filename prefix is for humans.
- One step does one thing. A destructive change is split into expand and
  contract steps.
- No `downgrade`.

### Runner behavior

```text
run_migrations(engine, store, steps):
  1. take the process lock
  2. ensure the ledger table
  3. current = max(revision), or 0
  4. verify every applied step's checksum matches the code; mismatch -> fail fast
  5. if current > max(code revision): fail fast, tell the user to restore a backup
  6. for each revision > current, ascending:
       - snapshot the store to data/backups/ before a destructive step
       - BEGIN -> upgrade(conn) -> write the ledger row -> COMMIT
       - on error -> ROLLBACK, raise, do not start
  7. no pending steps -> no-op
```

- The ledger row is committed in the same transaction as the step, so a crash
  cannot record a step that only half-applied.
- Checksum is the sha256 of the step source, detecting silent edits to an
  applied step.
- A failure refuses startup instead of continuing in a drifting state. This is
  the Home Assistant `MIGRATION_ERROR` idea, made strict because there is no
  running UI to surface it.
- No signatures. Without a key-distribution chain, signing scripts is theater;
  a checksum is the honest tool.

### Concurrency and timing

- Reuse the existing `runtime_instance_lock`, so migration runs on one process
  only.
- Migrations run serially and asynchronously before any read or write: inside
  each store's `initialize()`, and for config before `AstrBotConfig` first
  reads a value.
- `config` migration runs before logging is configured, because log settings
  come from config.

### Relationship to `create_all`

`create_all` still creates missing tables; migrations handle the difference
between an old store and the current one. The alternative — dropping
`create_all` and letting migration step `0001` own table creation — would
duplicate the 35-table schema definition and split the source of truth, so it
is rejected. The cost of keeping `create_all` is that "a fresh store" and "a
migrated store" must be proven equivalent; see [Verification](#verification).

### First rollout on stores that predate the runner

The first release with the runner must not replay `0001_initial` onto a
populated store that already has those tables. Rollout therefore adopts each
pre-runner store by inspecting its schema, never by assuming its revision is
zero:

- **Empty store:** run `create_all` via `0001_initial`, then record the
  baseline in the ledger.
- **Populated pre-runner store:** recognize the known pre-runner shape and
  either record the baseline or run the steps that bridge it forward:
  - `main`: the only supported populated pre-runner file is
    `data/data_v4.db`. Its shape differs from the current one (no surrogate
    `id`, no foreign keys), so it is adopted by the one-time import rather than
    by replaying `0001`; the import records the `main` baseline itself.
  - `kb`: a pre-runner `kb.db` carries the old `kb_media` without
    `updated_at`; `0002` adds it conditionally, so a populated store can start
    the chain at `0001` safely.
  - `doc` and `config`: the baseline is idempotent (`create_all` and the
    flat-to-grouped step), so an existing store is adopted in place.
- **Unknown shape:** a populated store that matches no known pre-runner shape
  is treated as newer than the code and refuses startup, instead of guessing.

Before the runner ships, add a fixture for every supported pre-runner store
shape, in addition to the historical-revision fixtures, and assert each migrates
to head without losing rows.

## Contributor rules

1. **A schema or config-shape change is a breaking change that needs a step.**
   Add a new revision with its `upgrade` function. Do not mutate an applied
   step; its checksum would fail startup.
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

## Before the migration system exists

Until the runner lands, the current policy applies: stores are created from
their current definition, and a breaking change meant deleting the affected
store. That was acceptable only because there were no users. As soon as
user data must survive, this section stops applying and the design above takes
over.

## Verification

The migration system is only correct if each of these is tested:

- Fresh store runs every step once and ends at the head revision.
- Re-running is a no-op.
- Editing an applied step fails startup.
- A store revision newer than the code fails startup with a restore hint.
- A failing step rolls back and leaves the ledger unchanged.
- **Schema equivalence:** a `create_all` store and a store migrated from
  `0001` to head have identical tables, columns, and indexes.
- **Upgrade paths:** a fixture store per historical revision migrates the full
  chain to head.
- **Rollout adoption:** a populated fixture per supported pre-runner store
  shape migrates to head without losing rows, and an unknown shape refuses
  startup.

## Related pages

- [Project Architecture](./architecture) — storage layout and startup order.
- [AstrBot Configuration File](./astrbot-config) — the config surface.
- [Backup and restore](/en/deploy/astrbot/backup) — the supported way to carry
  data between installs.
