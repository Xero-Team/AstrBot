# Data isolation, persistence, and lifecycle hunting

## When to use

The target stores access-controlled data, derives search/index/cache/analytics
copies, issues object links, exports or restores records, migrates schemas, or
promises deletion, revocation, and retention. This domain follows one data item
through every copy and state transition.

Use `web-and-dashboard.md` for endpoint-level access control and
`agent-and-llm.md` for context and memory scoping.

Source map: `astrbot/core/knowledge_base/` (`kb_helper.py`, `kb_mgr.py`,
`kb_db_sqlite.py`, `retrieval/`), `astrbot/core/db/` (`vec_db/`,
`migrations/`, `stores/`, `po/`), `astrbot/core/config/migrations/`,
`astrbot/core/conversation_mgr.py`, `astrbot/core/utils/trace_store.py`,
`astrbot/core/utils/storage_cleaner.py`, `astrbot/core/backup/`,
`astrbot/dashboard/api/knowledge_bases.py`,
`astrbot/dashboard/services/log_service.py`.

## Core discipline

- A tenant or owner field on a record is not isolation. Find the query, key,
  path, policy, or row-level control that enforces it for each read and write.
- Trace derived copies. Sanitized primary data can become unsafe in search,
  cache, analytics, exports, previews, logs, replicas, and backups with
  different ACL and retention rules.
- Deletion and revocation are lifecycle contracts. Check current, historical,
  cached, indexed, exported, restored, and queued copies within the product's
  stated boundary.
- A privacy or retention preference is not automatically a vulnerability.
  Require an explicit data-access boundary or deletion/revocation guarantee and
  an unauthorized reader or later operation.
- `confirmed` needs complete source-visible lineage and a bounded dummy-data
  test. `needs_validation` when external storage policy, retention, CDN
  behavior, replica lag, or backup access is unavailable.

## Tenant and object-isolation classes

**Missing owner enforcement.** A read, update, delete, list, count, or bulk
query identifies an object without binding it to the authenticated owner.
`ConversationManager.get_conversation` looks up by id and leaves origin
ownership to callers; every caller must check it. Compare direct lookup,
nested relationship, background, admin, import, and legacy paths.

**Knowledge-base scope.** A KB owns `<kb_root>/<kb_id>/{medias,files}`; metadata
lookups are `kb_id`-scoped; retrieval passes `metadata_filters={"kb_id": ...}`
per base; the tool prefers the session's `kb_config.kb_ids` and falls back to
global names only when unset. Check a query that omits the filter, a session
list that can name another user's base, a cache key without `kb_id`, and a
document identity lookup that crosses bases.

**Composite-key and namespace collision.** Cache keys, object paths, database
uniqueness, search document ids, temp files, or deduplication keys omit tenant
or environment. Two principals can overwrite or retrieve the same logical key
even though application records carry separate owners.

**Policy and query disagreement.** Row-level policy, ORM default scopes,
authorization filters, and raw/bypass clients apply different predicates.
Check joins, aggregates, aliases, views, transactions, service clients, and
error paths where context is missing. Dashboard KB resources are authorized as
`config_id`-scoped objects; a direct service call must not skip that.

**Blob and signed-reference overreach.** Object keys, attachment ids, version
ids, shared links, or signed URLs permit operations or namespaces beyond the
issuing principal, or remain valid after the underlying ACL changes. Shares
store only `token_hash` with optional expiry/revocation; verify the redemption
path checks both and binds the share to the intended conversation.

## Derived-data and disclosure classes

**Search, cache, and index ACL drift.** A primary record's ACL or lifecycle
changes without invalidating a searchable, cached, embedded, thumbnail, RSS,
preview, or index copy. Validate filtering at retrieval time as well as at
ingestion and invalidation. The BM25 cache is invalidated only after a
successful vector write; a failure between the two is a candidate.

**Analytics, logs, traces, and diagnostics as alternate readers.** Private
content or credentials emitted into systems with broader access, longer
retention, or tenant mixing. `trace_store` retention deletes whole old traces
and enforces a page budget; the diagnostic export redacts credentials, tokens,
and public-IP aliases and writes a `0o700` archive under `data/temp/log_exports`.
Check a new field that bypasses redaction, a raw trace detail endpoint, and an
export path reachable by a lower-trust scope.

**Enumeration and aggregate oracles.** Counts, filters, ordering, errors,
unique constraints, timings, notification behavior, or existence checks
disclose protected state. Require a concrete confidential predicate and an
observable distinction, not general response variance.

## Export, backup, restore, and migration classes

**Export and backup scope expansion.** The backup allowlist includes named
main-DB models, KB metadata, vector index files, media, and selected
directories; `dashboard_trusted_devices` is deliberately excluded. Check an
export that includes another tenant, inaccessible fields, soft-deleted data,
secret values, or history above the requester's access; check per-item
authorization after selection and authorization to download the final artifact.

**Import and restore authority expansion.** Restore clears main-DB rows and KB
data before importing; `pre_check` and version validation run first. Validate
archive contents as untrusted, authorize the resulting operation rather than
trusting prior provenance, and check a restore that recreates records in a
tenant the requester cannot write or resurrects revoked device trust.

**Migration defaults and ownership.** The main DB uses a forward-only migration
ledger with per-step checksums; KB metadata and per-KB document stores have
their own ledgers. Config documents use `schema_revision` (currently 6),
forward-only, and refuse a revision newer than the build. Old records that lack
owner/ACL/lifecycle fields, colliding ids, partial rollout, and rollback are
candidates. Do not edit an applied step.

**Credential lifecycle.** Dashboard JWTs are stateless; step-up credentials
store only a hash and are single-use; trusted devices hash the token and the
current TOTP secret; API keys store only a hash. Check a rotation, revocation,
account disable, password change, or TOTP reset that leaves a session, device,
share, or step-up proof valid beyond its promised lifetime.

## Deletion, revocation, and retention classes

**Soft-delete and tombstone bypass.** A direct lookup, search, relation
traversal, object link, background processor, or restore ignores the lifecycle
predicate and returns a deleted/revoked record. KB deletion stages a tombstone
and finalizes only after metadata deletion; a crash must not leave a queryable
partial base.

**Upload and replace compensation.** A KB upload spans parsed media, metadata,
vectors, and source blobs; the size/shape validation runs before document
writes, metadata commits in one transaction, and `_cleanup_failed_upload`
compensates vectors, rows, media, then blobs. A replace path keeps a marker and
recovers on startup. Check an upload failure that leaves a queryable partial
document, a replace crash that loses the old version, and a cleanup that misses
a store.

**Retention and queued-work overrun.** Deletion completes in primary storage
while queued processors, retries, exports, analytics, or generated artifacts
recreate or retain data. `storage_cleaner` covers logs, cache, and traces and
must learn every new unbounded store. Main-DB history, attachments, memory, and
KV growth are outside it; a new store without a cleanup owner is a candidate
when it can grow unbounded from untrusted input.

**Restore reintroduces invalid state.** Backup, undo, undelete, or replica
recovery restores data, credentials, memberships, or permissions that current
policy no longer allows. Re-authorize restored state and reapply lifecycle
changes made after the snapshot.

## Universal moves

- Pick one protected record and draw primary write, query, cache, index, event,
  export, backup, deletion, and restore paths. Mark principal and scope at every
  edge.
- Compare two dummy accounts or tenants through the same local service methods,
  then repeat after ACL change, deletion, account switch, and restore.
- Start at bypass clients, background jobs, migrations, global uniqueness, and
  cache keys. These commonly omit request-scoped identity that interactive
  endpoints carry.

## Validation rules

1. Name the attacker or lower-trust principal, protected data/state, affected
   owner, alternate copy or operation, and unauthorized disclosure or mutation.
2. Cite both the intended source-of-truth policy and the path that omits or
   disagrees with it. Confirm another layer does not enforce the same condition.
3. Use local dummy tenants and non-sensitive fixtures to prove cross-scope
   access or stale lifecycle behavior. Stop at the minimum record or operation.
4. For upload/replace claims, cite the ordering and the store that remains
   inconsistent; a failed upload with full compensating cleanup is not a
   finding.
5. If external cache, object storage, replicas, analytics, backup, or retention
   policy is required, use `needs_validation` and state the owner-observed
   check.
6. Return `confirmed` only with complete lineage and concrete boundary impact.
