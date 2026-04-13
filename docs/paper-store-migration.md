# Paper Store Migration Notes

## Current authority

After `introduce-sqlite-paper-store-and-vector-backend-abstraction`, the SQLite paper store under `data/processed/paper_store.sqlite3` is the authority for:

- paper identity and stable source path
- paper lifecycle state
- topic membership
- chunk ownership
- per-paper artifact status
- current vector backend metadata

Compatibility files such as `data/processed/papers.json` and `data/library_topics.json` remain available, but they are derived exports and must not be treated as the source of truth.

## Migration path

The store can be bootstrapped from existing files:

- `data/processed/papers.json`
- `data/library_topics.json`
- `data/processed/chunks.jsonl`
- `data/processed/chunks_clean.jsonl`
- `data/processed/paper_summary.json`
- `data/processed/structure_index.json`

When repairing historical PDF records, the migration prefers:

1. an explicit stable path map supplied by the caller
2. a matching basename under `data/raw/imported`
3. a matching fingerprint under `data/raw/imported`

If none of these work, the original path is preserved and the record should be treated as needing manual review.

## Rollback and rebuild

If the new SQLite-backed path fails:

1. Preserve `data/processed/paper_store.sqlite3` for inspection.
2. Keep existing compatibility files and index artifacts in place.
3. Regenerate the SQLite store from compatibility files by calling the paper store sync path again.
4. Fall back to file-based readers only as a temporary read-only compatibility path.

The intended recovery order is:

- rebuild SQLite from exported files
- verify paper list and topic mappings
- verify vector backend metadata
- resume normal reads through SQLite-backed APIs

## Upgrade path for Qdrant

The current vector backend is intentionally exposed through a stable abstraction.

Future `add-qdrant-vector-backend` work should:

- add a new backend implementation behind the same vector backend contract
- keep `paper_id`-scoped delete and filter semantics unchanged
- continue writing backend metadata into the SQLite paper store
- avoid changing planner or frontend contracts just because the vector backend changes
