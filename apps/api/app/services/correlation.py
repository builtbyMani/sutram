"""Correlation engine — entity resolution + evidence graph (Phase 3, Tasks 3.1/3.2).

Pure functions over lists of dicts. No database access, no FastAPI imports,
no relative imports: the wiring phase (``POST /api/correlate``) calls
:func:`resolve_identities` and persists the returned identities/relations
into the ``identities`` / ``relations`` tables.

Pipeline
--------
1. Every entity value is normalized by kind (:func:`normalize_value`).
2. Union-find merge passes, applied in deterministic (entity-id) order:
   a. Identifier entities (PHONE/EMAIL/IP) with equal normalized values merge
      (confidence 1.0).
   b. Name entities (PERSON/ORG) with equal normalized values merge (1.0).
   c. Name entities linked through the *same identifier identity* merge (1.0):
      e.g. PERSON "M. Sharma" (artifact 1) and PERSON "Manish Sharma"
      (artifact 2) merge because both co-occur with phone 9876543201.
      This is the deterministic cross-source merge the plan requires.
   d. Name entities (same kind) with MiniLM cosine similarity >= 0.85 merge
      (confidence = cosine). Embeddings are computed once per unique
      normalized name; a caller-supplied ``embedding`` list on the entity
      dict is honored (lets the wiring phase reuse ingest-time vectors).
3. Each union group becomes one identity. Canonical value = longest observed
   raw mention (ties broken by lowest entity id — deterministic).
4. Relations:
   - ``same_identifier``: name identity <-> identifier identity, emitted only
     when >=2 member mentions of the name link through that identifier
     (corroborated attribution — merge-grade evidence, e.g. the phone cited
     beside two independent mentions of the person). Single-mention links
     surface as ``co_occurrence`` instead.
     Evidence: the shared identifier's kind/value.
   - ``co_occurrence``: two identities whose member entities appear in the
     same artifact. Pairs already linked by ``same_identifier`` are not
     duplicated; artifact ids accumulate into one edge per pair.

Everything is order-deterministic: re-running on the same input yields
byte-identical output (required for the idempotent ``POST /api/correlate``).
"""

from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constants (locked by 03-CONTEXT.md / 03-01-PLAN.md)
# ---------------------------------------------------------------------------

IDENTIFIER_KINDS = frozenset({"PHONE", "EMAIL", "IP"})
NAME_KINDS = frozenset({"PERSON", "ORG"})
FUZZY_THRESHOLD = 0.85
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_REQUIRED_KEYS = ("id", "artifact_id", "kind", "value")

# Lazily-loaded SentenceTransformer singleton (see _minilm_encode).
_model = None


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_value(kind: str, value: str) -> str:
    """Normalize an entity value for comparison, by kind.

    PERSON/ORG  -> stripped + lowercased.
    PHONE       -> digits only (``+91 98765 43201`` -> ``919876543201``).
    EMAIL       -> stripped + lowercased.
    IP / other  -> stripped.
    """
    if not isinstance(value, str):
        raise ValueError(f"entity value must be str, got {type(value).__name__}")
    if kind in NAME_KINDS:
        return value.strip().lower()
    if kind == "PHONE":
        return re.sub(r"\D", "", value)
    if kind == "EMAIL":
        return value.strip().lower()
    return value.strip()


# ---------------------------------------------------------------------------
# Embeddings (lazy)
# ---------------------------------------------------------------------------

def _minilm_encode(texts: Sequence[str]) -> List[List[float]]:
    """Encode texts with all-MiniLM-L6-v2, L2-normalized.

    The model is loaded once and cached. Raises RuntimeError with an
    actionable message when sentence-transformers is missing or the model
    cannot be loaded (the wiring phase must bake it into the Docker image —
    no runtime download).
    """
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Install it with a "
                f"CPU-only torch and bake the '{MODEL_NAME}' model weights "
                "into the Docker image at build time (see CORRELATION-NOTE.md)."
            ) from exc
        try:
            _model = _load_minilm_offline()
        except Exception as exc:  # noqa: BLE001 - must surface any load failure
            raise RuntimeError(
                f"Could not load sentence-transformers model '{MODEL_NAME}'. "
                "The model must be pre-downloaded and baked into the image; "
                f"runtime download is not allowed. Original error: {exc}"
            ) from exc
    vecs = _model.encode(list(texts), normalize_embeddings=True,
                         show_progress_bar=False)
    return [[float(x) for x in v] for v in vecs]


def _local_snapshot():
    """Return the local HF-cache snapshot dir for MODEL_NAME, or None.

    Scans $HF_HUB_CACHE (default ~/.cache/huggingface/hub) for a complete
    snapshot (config.json + weights). Pure filesystem read, no network.
    """
    import os
    cache = os.environ.get(
        "HF_HUB_CACHE",
        os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"),
    )
    repo = "models--sentence-transformers--" + MODEL_NAME.replace("/", "--")
    snaps = os.path.join(cache, repo, "snapshots")
    if not os.path.isdir(snaps):
        return None
    cands = sorted(
        (os.path.join(snaps, d) for d in os.listdir(snaps)),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    for cand in cands:
        has_cfg = os.path.isfile(os.path.join(cand, "config.json"))
        has_w = os.path.isfile(os.path.join(cand, "model.safetensors")) or \
                os.path.isfile(os.path.join(cand, "pytorch_model.bin"))
        if has_cfg and has_w:
            return cand
    return None


def _load_minilm_offline():
    """Load the baked-in MiniLM model without any network access.

    Guards: this sandbox (and possibly the demo venue) exports
    no_proxy/NO_PROXY values containing bracketed IPv6 literals ('[::1]'),
    which crash the httpx client huggingface_hub builds at load time
    ('InvalidURL: Invalid port'). We strip those vars and force HF
    offline mode around the load; the weights come from the local cache.
    """
    import os
    from sentence_transformers import SentenceTransformer
    saved = {}
    for var in ("no_proxy", "NO_PROXY", "http_proxy", "https_proxy",
                "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        saved[var] = os.environ.pop(var, None)
    saved_hf = os.environ.get("HF_HUB_OFFLINE")
    saved_tf = os.environ.get("TRANSFORMERS_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        # Prefer the baked-in local snapshot path: avoids the Hub client's
        # network retries entirely (74s -> 23s in this environment).
        return SentenceTransformer(_local_snapshot() or MODEL_NAME)
    finally:
        for var, val in saved.items():
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val
        if saved_hf is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = saved_hf
        if saved_tf is None:
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
        else:
            os.environ["TRANSFORMERS_OFFLINE"] = saved_tf


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for arbitrary numeric sequences (pure Python)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    # Clamp for float safety; cosine of normalized vectors stays in [-1, 1].
    return max(-1.0, min(1.0, dot / (na * nb)))


# ---------------------------------------------------------------------------
# Union-find
# ---------------------------------------------------------------------------

class _UnionFind:
    """Deterministic union-find over indices 0..n-1 with merge confidences."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
        # min merge confidence per root (1.0 = purely deterministic merges)
        self.min_conf: Dict[int, float] = {i: 1.0 for i in range(n)}

    def find(self, x: int) -> int:
        parent = self.parent
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    def union(self, a: int, b: int, confidence: float = 1.0) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            # Still tighten the recorded confidence for repeated evidence.
            self.min_conf[ra] = min(self.min_conf[ra], confidence)
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        self.min_conf[ra] = min(self.min_conf[ra], self.min_conf[rb], confidence)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _validate_entities(entities: Sequence[Dict]) -> List[Dict]:
    """Return entities sorted by id; raise ValueError on malformed input."""
    ents = list(entities)
    seen = set()
    for e in ents:
        for k in _REQUIRED_KEYS:
            if k not in e:
                raise ValueError(f"entity missing required key {k!r}: {e!r}")
        if e["id"] in seen:
            raise ValueError(f"duplicate entity id: {e['id']!r}")
        seen.add(e["id"])
        if not isinstance(e["value"], str):
            raise ValueError(
                f"entity id={e['id']!r} value must be str, "
                f"got {type(e['value']).__name__}"
            )
    return sorted(ents, key=lambda e: e["id"])


def resolve_identities(
    entities: Sequence[Dict],
    embed_fn: Optional[Callable[[Sequence[str]], List[List[float]]]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """Resolve entities into canonical identities + relations.

    Args:
        entities: list of dicts with keys ``id``, ``artifact_id``, ``kind``,
            ``value``. An optional ``embedding`` key (list of floats) on a
            PERSON/ORG entity is reused instead of re-encoding it.
        embed_fn: ``(texts) -> vectors`` override for the MiniLM encoder,
            used by tests. When None, the real model loads lazily; a load
            failure raises RuntimeError.

    Returns:
        ``(identities, relations)`` where each identity is a dict with keys
        ``id, kind, canonical_value, member_entity_ids, artifact_ids,
        confidence`` and each relation a dict with keys ``id, a, b,
        relation_type, evidence, confidence``. Output is deterministic:
        identical input always yields identical output.
    """
    ents = _validate_entities(entities)
    n = len(ents)
    if n == 0:
        return [], []

    normed = [normalize_value(e["kind"], e["value"]) for e in ents]
    kinds = [e["kind"] for e in ents]
    uf = _UnionFind(n)

    def union_exact(idxs: Sequence[int]) -> None:
        by_value: Dict[Tuple[str, str], List[int]] = {}
        for i in idxs:
            by_value.setdefault((kinds[i], normed[i]), []).append(i)
        for group in by_value.values():
            for j in group[1:]:
                uf.union(group[0], j, 1.0)

    # (2a) identifier entities: exact normalized match.
    union_exact([i for i in range(n) if kinds[i] in IDENTIFIER_KINDS])
    # (2b) name entities: exact normalized match.
    union_exact([i for i in range(n) if kinds[i] in NAME_KINDS])

    # (2c) names linked through the same identifier identity.
    # identifier_root -> name indices that co-occur with one of its entities.
    # name_to_ident_roots records, per name entity, every identifier group it
    # links through (used later for same_identifier corroboration).
    art_to_ident_idxs: Dict[int, List[int]] = {}
    for i in range(n):
        if kinds[i] in IDENTIFIER_KINDS:
            art_to_ident_idxs.setdefault(ents[i]["artifact_id"], []).append(i)
    ident_root_to_names: Dict[int, List[int]] = {}
    name_to_ident_roots: Dict[int, set] = {}
    for i in range(n):
        if kinds[i] not in NAME_KINDS:
            continue
        roots = set()
        for j in art_to_ident_idxs.get(ents[i]["artifact_id"], []):
            roots.add(uf.find(j))
        if roots:
            name_to_ident_roots[i] = roots
        for r in roots:
            ident_root_to_names.setdefault(r, []).append(i)
    for name_idxs in ident_root_to_names.values():
        for j in name_idxs[1:]:
            uf.union(name_idxs[0], j, 1.0)

    # (2d) fuzzy merge for PERSON/ORG on MiniLM cosine >= threshold.
    # Candidate pairs are fixed up front (same kind, different groups); the
    # encoder only runs when at least one candidate pair exists, so purely
    # deterministic inputs never touch the model.
    name_idxs = [i for i in range(n) if kinds[i] in NAME_KINDS]
    by_kind: Dict[str, List[int]] = {}
    for i in name_idxs:
        by_kind.setdefault(kinds[i], []).append(i)
    cand_pairs: List[Tuple[int, int]] = []
    for kind_group in by_kind.values():
        for a_pos in range(len(kind_group)):
            for b_pos in range(a_pos + 1, len(kind_group)):
                a, b = kind_group[a_pos], kind_group[b_pos]
                if uf.find(a) != uf.find(b):
                    cand_pairs.append((a, b))
    if cand_pairs:
        uniq_names = sorted({normed[i] for a, b in cand_pairs for i in (a, b)})
        if embed_fn is None:
            vectors = dict(zip(uniq_names, _minilm_encode(uniq_names)))
        else:
            vectors = dict(zip(uniq_names, embed_fn(uniq_names)))

        def vec_for(i: int) -> List[float]:
            pre = ents[i].get("embedding")
            if pre is not None:
                return [float(x) for x in pre]
            return vectors[normed[i]]

        for a, b in cand_pairs:
            if uf.find(a) == uf.find(b):
                continue
            sim = _cosine(vec_for(a), vec_for(b))
            if sim >= FUZZY_THRESHOLD:
                uf.union(a, b, sim)

    # ---- identities -------------------------------------------------------
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    ordered = sorted(groups.values(),
                     key=lambda idxs: min(ents[i]["id"] for i in idxs))

    ent_idx_to_ident: Dict[int, int] = {}
    identities: List[Dict] = []
    ident_id_to_root: Dict[int, int] = {}  # identity id -> union-find root
    for gid, idxs in enumerate(ordered, start=1):
        member_ids = sorted(ents[i]["id"] for i in idxs)
        # Canonical value: longest observed raw mention; ties -> lowest id.
        canon_idx = sorted(idxs, key=lambda i: (-len(ents[i]["value"]),
                                                ents[i]["id"]))[0]
        art_ids = sorted({ents[i]["artifact_id"] for i in idxs})
        root = uf.find(idxs[0])
        identities.append({
            "id": gid,
            "kind": kinds[idxs[0]],  # uniform by construction
            "canonical_value": ents[canon_idx]["value"],
            "member_entity_ids": member_ids,
            "artifact_ids": art_ids,
            "confidence": round(uf.min_conf[root], 4),
        })
        for i in idxs:
            ent_idx_to_ident[i] = gid
        if kinds[idxs[0]] in IDENTIFIER_KINDS:
            ident_id_to_root[gid] = root

    # ---- relations --------------------------------------------------------
    # (4a) same_identifier: a name identity gets this edge to an identifier
    # identity only when >=2 of its member mentions link through that
    # identifier (corroborated attribution, e.g. the same phone cited beside
    # two independent mentions of the person). Single-mention links are just
    # co_occurrence (below). This keeps the two relation types meaningful:
    # same_identifier is merge-grade evidence; co_occurrence is not.
    id_to_idx = {e["id"]: i for i, e in enumerate(ents)}
    ident_by_id = {i["id"]: i for i in identities}
    seen_pairs = set()
    relations: List[Dict] = []
    for ident in identities:
        if ident["kind"] not in NAME_KINDS:
            continue
        member_idxs = [id_to_idx[eid] for eid in ident["member_entity_ids"]]
        for y_gid, y_root in sorted(ident_id_to_root.items()):
            linked = sorted(idx for idx in member_idxs
                            if y_root in name_to_ident_roots.get(idx, ()))
            if len(linked) < 2:
                continue
            y_ident = ident_by_id[y_gid]
            pair = (min(ident["id"], y_gid), max(ident["id"], y_gid))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            relations.append({
                "a": pair[0],
                "b": pair[1],
                "relation_type": "same_identifier",
                "evidence": {
                    "identifier_kind": y_ident["kind"],
                    "identifier_value": y_ident["canonical_value"],
                    "via_entity_ids": [ents[idx]["id"] for idx in linked],
                },
                "confidence": 1.0,
            })

    # (4b) co_occurrence: identities sharing an artifact (dedup vs 4a).
    art_to_idents: Dict[int, set] = {}
    for i in range(n):
        art_to_idents.setdefault(ents[i]["artifact_id"],
                                 set()).add(ent_idx_to_ident[i])
    co_evidence: Dict[Tuple[int, int], set] = {}
    for art_id in sorted(art_to_idents):
        ids_here = sorted(art_to_idents[art_id])
        for x in range(len(ids_here)):
            for y in range(x + 1, len(ids_here)):
                pair = (ids_here[x], ids_here[y])
                if pair in seen_pairs:
                    continue
                co_evidence.setdefault(pair, set()).add(art_id)
    for pair in sorted(co_evidence):
        relations.append({
            "a": pair[0],
            "b": pair[1],
            "relation_type": "co_occurrence",
            "evidence": {"artifact_ids": sorted(co_evidence[pair])},
            "confidence": 1.0,
        })

    relations.sort(key=lambda r: (r["a"], r["b"], r["relation_type"]))
    for rid, r in enumerate(relations, start=1):
        r["id"] = rid

    return identities, relations


# ---------------------------------------------------------------------------
# Graph payload (exact shape served by GET /api/graph)
# ---------------------------------------------------------------------------

def build_graph_data(identities: Sequence[Dict],
                     relations: Sequence[Dict]) -> Dict:
    """Build the ``GET /api/graph`` payload from identities + relations."""
    return {
        "nodes": [
            {
                "id": ident["id"],
                "kind": ident["kind"],
                "canonical_value": ident["canonical_value"],
                "artifact_count": len(ident["artifact_ids"]),
            }
            for ident in identities
        ],
        "edges": [
            {
                "a": rel["a"],
                "b": rel["b"],
                "relation_type": rel["relation_type"],
                "confidence": rel["confidence"],
            }
            for rel in relations
        ],
    }
