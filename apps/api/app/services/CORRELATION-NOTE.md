# CORRELATION-NOTE.md — wiring instructions for the Phase 3 integrator

Module: `apps/api/app/services/correlation.py` (pure Python, no DB/FastAPI imports).
Self-test: `apps/api/app/services/test_correlation.py` — **38/38 pass**, including
the real MiniLM model (verified 2026-10-19 with `all-MiniLM-L6-v2`, 384-dim).

## 1. Exact function signatures

```python
normalize_value(kind: str, value: str) -> str
```
Normalization by kind: PERSON/ORG → strip+lowercase; PHONE → digits only;
EMAIL → strip+lowercase; IP/other → strip. Raises `ValueError` on non-str.

```python
resolve_identities(
    entities: Sequence[Dict],
    embed_fn: Optional[Callable[[Sequence[str]], List[List[float]]]] = None,
) -> Tuple[List[Dict], List[Dict]]
```
- `entities`: list of dicts, each with keys `id`, `artifact_id`, `kind`,
  `value` (all required; `ValueError` otherwise). Optional `embedding` key
  (list of floats) on a PERSON/ORG dict is reused instead of re-encoding.
- `embed_fn`: override for the MiniLM encoder (tests). When `None`, the real
  `all-MiniLM-L6-v2` model loads lazily on first fuzzy comparison; a load
  failure raises `RuntimeError` with an actionable message (model must be
  baked into the Docker image — see §3).
- Returns `(identities, relations)`:
  - identity: `{"id", "kind", "canonical_value", "member_entity_ids",
    "artifact_ids", "confidence"}`. `canonical_value` = longest observed raw
    mention (ties → lowest entity id). `confidence` = min merge confidence
    (1.0 = purely deterministic merges; fuzzy merges record cosine).
  - relation: `{"id", "a", "b", "relation_type", "evidence", "confidence"}`.
    `relation_type` ∈ `{"same_identifier", "co_occurrence"}`.
- **Deterministic**: identical input → byte-identical output (verified by test).
  Safe for the idempotent `POST /api/correlate`.

```python
build_graph_data(identities: Sequence[Dict], relations: Sequence[Dict]) -> Dict
```
Returns exactly the `GET /api/graph` payload:
`{"nodes": [{"id","kind","canonical_value","artifact_count"}],
  "edges": [{"a","b","relation_type","confidence"}]}`.

Module constants: `IDENTIFIER_KINDS = {"PHONE","EMAIL","IP"}`,
`NAME_KINDS = {"PERSON","ORG"}`, `FUZZY_THRESHOLD = 0.85`,
`MODEL_NAME = "all-MiniLM-L6-v2"`, `EMBEDDING_DIM = 384`.

## 2. Merge semantics (what the wiring phase must know)

- **Deterministic merges (confidence 1.0)**: identifier entities with equal
  normalized values; name entities with equal normalized values; name
  entities linked through the **same identifier identity** (e.g. "M. Sharma"
  + "Manish Sharma" merge because both co-occur with the same phone —
  transitive via union-find).
- **Fuzzy merges (confidence = cosine)**: PERSON/ORG of the same kind with
  MiniLM cosine ≥ 0.85. Verified: "Bob Sharma" does **not** merge into
  "Manish Sharma" (shared surname correctly rejected).
- **`same_identifier` edges**: name identity ↔ identifier identity, emitted
  **only when ≥2 member mentions of the name link through that identifier**
  (corroborated attribution — merge-grade evidence). Single-mention links
  surface as `co_occurrence` instead.
- **`co_occurrence` edges**: identities sharing an artifact; pairs already
  linked by `same_identifier` are not duplicated; artifact ids accumulate.
- Entity kinds outside PERSON/ORG/PHONE/EMAIL/IP (e.g. URL) are **not merged** —
  each becomes its own identity (deliberate; plan only specifies the five kinds).
- Phone normalization is digits-only: `+91 98765 43201` ≠ `9876543201`
  (documented limitation; country-code-aware normalization is future work).

## 3. DB tables/columns the wiring phase must create FIRST

Additive only (never redesign `artifacts`/`entities`):

```sql
-- new column on entities (plan Task 3.2):
ALTER TABLE entities ADD COLUMN embedding BLOB NULL;
-- 384-dim float32, L2-normalized; written at ingest for PERSON/ORG.
-- Pack with struct.pack('384f', *vec); unpack with struct.unpack.

CREATE TABLE identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    canonical_value TEXT NOT NULL,
    merged_entity_ids_json TEXT NOT NULL   -- JSON list of entity ids
                                           -- (= member_entity_ids from resolve_identities)
);
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_a_id INTEGER NOT NULL,         -- = relation["a"]
    identity_b_id INTEGER NOT NULL,         -- = relation["b"]
    relation_type TEXT NOT NULL,            -- "same_identifier" | "co_occurrence"
    evidence_json TEXT NOT NULL,            -- JSON of relation["evidence"]
    confidence REAL NOT NULL
);
```

Field mapping: identity dict `member_entity_ids` → `merged_entity_ids_json`
(JSON-encode); relation dict `evidence` → `evidence_json` (JSON-encode).
`artifact_ids` and per-identity `confidence` are **not** separate columns in
the plan's schema — recompute `artifact_ids` from member entities when
needed, or store them inside a JSON sidecar if you add one (your call;
document it).

## 4. New pip dependencies (verified versions — add to requirements.txt)

```
sentence-transformers==6.1.0
```
plus CPU-only torch. Install torch from the CPU index **before**
sentence-transformers so pip does not pull the CUDA build:

```
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers==6.1.0
```
Verified working: `torch 2.14.1+cpu`, `sentence-transformers 6.1.0`.
**Dockerfile must**: prime the model cache at build time
(`python -c "from sentence_transformers import SentenceTransformer;
SentenceTransformer('all-MiniLM-L6-v2')"`), torch CPU index. No runtime
download — the module raises `RuntimeError` otherwise.

Environment quirk found during verification: this sandbox sets
`no_proxy`/`NO_PROXY` with bracketed IPv6 literals (`[::1]`), which crashes
this httpx version (`InvalidURL: Invalid port: ':1]'`) when
huggingface_hub builds its client. Workaround for any HF download step:
`env -u no_proxy -u NO_PROXY ...`. The API itself is unaffected at runtime
once the model is baked into the image.

## 5. Precise integration instructions

**`POST /api/correlate`** (idempotent):
1. `rows = SELECT id, artifact_id, kind, value FROM entities` → list of dicts.
2. `identities, relations = resolve_identities(rows)` — no `embed_fn`
   (uses the real model; it is baked into the image). Optionally pass
   stored ingest-time embeddings through each dict's `embedding` key to
   skip re-encoding (Task 3.2 writes them; the resolver honors them).
3. `DELETE FROM relations; DELETE FROM identities;` then insert per §3
   mapping. (Clear-and-rebuild = idempotent by construction; resolver
   output is deterministic.)
4. Return `{"identities": <count>, "relations": <count>}`.

**`GET /api/graph`**: read both tables, rebuild the dict shapes from §1,
return `build_graph_data(identities, relations)`.

**`GET /api/identities/{id}/artifacts`**: look up the identity's
`merged_entity_ids_json` → entity ids → their `artifact_id`s →
`SELECT id, filename, source_type, sha256 FROM artifacts WHERE id IN (...)`.
Return `{"identity": {...}, "artifacts": [...]}`.

**Task 3.2 (embeddings at ingest)**: in the extraction service, for each
PERSON/ORG entity, encode the mention once (truncate to 256 tokens) with
the same `all-MiniLM-L6-v2` model and store the 384-float32 L2-normalized
vector in `entities.embedding` (BLOB). The resolver will reuse these via
the `embedding` dict key — no code change needed in `correlation.py`.

## 6. Deviations from 03-01-PLAN.md (all verified by test)

1. **Pure-function boundary**: the module takes/returns plain dicts and never
   touches the DB — the plan's "create correlation.py" step is done; table
   creation + endpoint wiring is explicitly left to the integrator (§3, §5).
2. **`same_identifier` corroboration rule**: emitted only when ≥2 member
   mentions link through the identifier (not on every co-occurrence). Rationale
   documented in §2; keeps the relation meaningful for Phase 5's
   `shared-identifier-link` finding rule.
3. **Deterministic name merge through shared identifiers** (transitive
   union-find): this is what makes the "M. Sharma"/"Manish Sharma" fixture
   merge with confidence 1.0 instead of depending on fragile fuzzy similarity
   of abbreviated names.
4. Test fixture phones use the concrete value `9876543201` (the plan's
   `98XXXXXX01` is a masked placeholder, not a runnable fixture).
5. `embed_fn` injection + per-entity `embedding` passthrough are additions
   for testability and ingest-time efficiency; the default path is exactly
   the plan's lazy MiniLM encoder.
