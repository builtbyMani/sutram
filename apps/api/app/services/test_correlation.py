"""Self-test for correlation.py (Phase 3, Tasks 3.1/3.2).

Run:  cd apps/api && .venv/bin/python app/services/test_correlation.py
Exit code 0 = all assertions passed.

Covers (per 03-01-PLAN.md acceptance criteria):
  - "M. Sharma" / "Manish Sharma" + same phone -> ONE PERSON identity,
    2 merged members, canonical = longest mention.
  - same_identifier edge (PERSON <-> PHONE) and co_occurrence edges exist.
  - Idempotency: two runs -> byte-identical output.
  - Negative pair (different phones, dissimilar names) does NOT merge
    (requires the real MiniLM model).
  - Exact-name merge works without the model; fuzzy threshold mechanics
    verified with a stub embed_fn.
  - build_graph_data emits the exact GET /api/graph shape.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from correlation import (  # noqa: E402
    build_graph_data,
    normalize_value,
    resolve_identities,
)

PHONE = "9876543201"

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL {name} {detail}")


def base_entities():
    """Two chat exports sharing one phone; artifact 1 also has an email."""
    return [
        {"id": 1, "artifact_id": 1, "kind": "PERSON", "value": "M. Sharma"},
        {"id": 2, "artifact_id": 1, "kind": "PHONE", "value": PHONE},
        {"id": 3, "artifact_id": 1, "kind": "EMAIL",
         "value": "M.Sharma@Example.com"},
        {"id": 4, "artifact_id": 2, "kind": "PERSON", "value": "Manish Sharma"},
        {"id": 5, "artifact_id": 2, "kind": "PHONE", "value": PHONE},
    ]


def ident_by_kind(identities, kind):
    return [i for i in identities if i["kind"] == kind]


def test_normalize():
    print("== normalize_value ==")
    check("phone digits-only",
          normalize_value("PHONE", "+91 98765 43201") == "919876543201")
    check("email lower+strip",
          normalize_value("EMAIL", "  Foo@Bar.COM ") == "foo@bar.com")
    check("person lower+strip",
          normalize_value("PERSON", "  Alice Kapoor ") == "alice kapoor")
    check("org lower+strip",
          normalize_value("ORG", "Acme Ltd.") == "acme ltd.")
    check("ip strip", normalize_value("IP", " 10.0.0.1\n") == "10.0.0.1")


def test_deterministic_merge():
    print("== deterministic merge (shared phone) ==")
    identities, relations = resolve_identities(base_entities())

    persons = ident_by_kind(identities, "PERSON")
    check("exactly one PERSON identity", len(persons) == 1,
          f"got {len(persons)}")
    if persons:
        p = persons[0]
        check("PERSON has 2 merged members",
              p["member_entity_ids"] == [1, 4], f"got {p['member_entity_ids']}")
        check("canonical = longest mention",
              p["canonical_value"] == "Manish Sharma",
              f"got {p['canonical_value']!r}")
        check("PERSON spans both artifacts",
              p["artifact_ids"] == [1, 2], f"got {p['artifact_ids']}")
        check("deterministic confidence 1.0", p["confidence"] == 1.0,
              f"got {p['confidence']}")

    phones = ident_by_kind(identities, "PHONE")
    check("exactly one PHONE identity", len(phones) == 1)
    if phones:
        check("PHONE has 2 merged members",
              phones[0]["member_entity_ids"] == [2, 5])

    emails = ident_by_kind(identities, "EMAIL")
    check("EMAIL stays its own identity",
          len(emails) == 1 and emails[0]["member_entity_ids"] == [3])

    # Identity ids are deterministic: ordered by min member entity id.
    check("identity ids deterministic",
          [i["id"] for i in identities] == [1, 2, 3],
          f"got {[i['id'] for i in identities]}")


def test_relations():
    print("== relations ==")
    identities, relations = resolve_identities(base_entities())
    by_kind = {i["kind"]: i["id"] for i in identities}
    person, phone, email = by_kind["PERSON"], by_kind["PHONE"], by_kind["EMAIL"]

    same = [r for r in relations if r["relation_type"] == "same_identifier"]
    check("same_identifier edge PERSON<->PHONE exists",
          any({r["a"], r["b"]} == {person, phone} for r in same),
          f"edges: {[(r['a'], r['b'], r['relation_type']) for r in relations]}")
    if same:
        check("same_identifier confidence 1.0",
              all(r["confidence"] == 1.0 for r in same))
        check("same_identifier evidence names the phone",
              same[0]["evidence"].get("identifier_value") == PHONE,
              f"got {same[0]['evidence']}")

    co = [r for r in relations if r["relation_type"] == "co_occurrence"]
    co_pairs = [{r["a"], r["b"]} for r in co]
    check("co_occurrence EMAIL<->PERSON", {email, person} in co_pairs)
    check("co_occurrence EMAIL<->PHONE", {email, phone} in co_pairs)
    check("no duplicate PERSON<->PHONE co_occurrence (dedup vs same_identifier)",
          {person, phone} not in co_pairs)
    check("relation ids sequential from 1",
          [r["id"] for r in relations] == list(range(1, len(relations) + 1)))


def test_idempotency():
    print("== idempotency ==")
    ents = base_entities()
    run1 = resolve_identities(ents)
    run2 = resolve_identities(list(reversed(ents)))  # input order shuffled
    check("two runs byte-identical",
          json.dumps(run1, sort_keys=True) == json.dumps(run2, sort_keys=True))


def test_negative_pair():
    print("== negative pair (real MiniLM model) ==")
    ents = base_entities() + [
        {"id": 6, "artifact_id": 3, "kind": "PERSON", "value": "Alice Kapoor"},
        {"id": 7, "artifact_id": 3, "kind": "PHONE", "value": "9000000001"},
        {"id": 8, "artifact_id": 4, "kind": "PERSON", "value": "Bob Sharma"},
        {"id": 9, "artifact_id": 4, "kind": "PHONE", "value": "9000000002"},
    ]
    identities, _ = resolve_identities(ents)
    persons = ident_by_kind(identities, "PERSON")
    check("three distinct PERSON identities", len(persons) == 3,
          f"got {[(p['canonical_value'], p['member_entity_ids']) for p in persons]}")
    manish = next(p for p in persons if 4 in p["member_entity_ids"])
    check("'Bob Sharma' NOT merged into 'Manish Sharma'",
          8 not in manish["member_entity_ids"],
          f"manish members: {manish['member_entity_ids']}")
    phones = ident_by_kind(identities, "PHONE")
    check("three distinct PHONE identities", len(phones) == 3,
          f"got {len(phones)}")


def test_exact_merge_without_model():
    print("== exact-name merge (no model needed) ==")
    zero_vec = lambda texts: [[0.0] * 8 for _ in texts]  # noqa: E731
    ents = [
        {"id": 10, "artifact_id": 5, "kind": "PERSON", "value": "  ALICE kapoor "},
        {"id": 11, "artifact_id": 5, "kind": "PERSON", "value": "alice kapoor"},
    ]
    identities, _ = resolve_identities(ents, embed_fn=zero_vec)
    check("case/space variants merge exactly",
          len(identities) == 1 and identities[0]["member_entity_ids"] == [10, 11],
          f"got {[(i['member_entity_ids']) for i in identities]}")
    check("exact merge confidence 1.0", identities[0]["confidence"] == 1.0)


def test_fuzzy_mechanism_with_stub():
    print("== fuzzy threshold mechanics (stub embeddings) ==")
    # 2-D vectors with hand-computed cosines: 0.9 (merge) vs -1.0 (no merge).
    # NOTE: "beta" is antiparallel on purpose — fuzzy merge is transitive via
    # union-find, so the negative vector must be far from BOTH other vectors.
    vecs = {
        "alpha": [1.0, 0.0],
        "alpah": [0.9, 0.4359],   # cosine ~0.9 >= 0.85
        "beta": [-1.0, 0.0],      # cosine -1.0 / -0.9 < 0.85
    }
    stub = lambda texts: [vecs[t] for t in texts]  # noqa: E731
    ents = [
        {"id": 20, "artifact_id": 10, "kind": "PERSON", "value": "alpha"},
        {"id": 21, "artifact_id": 10, "kind": "PERSON", "value": "alpah"},
        {"id": 22, "artifact_id": 11, "kind": "PERSON", "value": "beta"},
    ]
    identities, _ = resolve_identities(ents, embed_fn=stub)
    merged = [i for i in identities if 20 in i["member_entity_ids"]]
    check("0.9-similarity pair merges", len(merged) == 1 and
          merged[0]["member_entity_ids"] == [20, 21])
    if merged:
        check("fuzzy confidence = cosine",
              abs(merged[0]["confidence"] - 0.9) < 0.01,
              f"got {merged[0]['confidence']}")
    alone = [i for i in identities if i["member_entity_ids"] == [22]]
    check("antiparallel entity stays separate", len(alone) == 1)


def test_graph_shape():
    print("== build_graph_data shape ==")
    identities, relations = resolve_identities(base_entities())
    g = build_graph_data(identities, relations)
    check("top-level keys", set(g.keys()) == {"nodes", "edges"})
    check("node keys",
          all(set(nd.keys()) == {"id", "kind", "canonical_value",
                                 "artifact_count"} for nd in g["nodes"]))
    check("edge keys",
          all(set(e.keys()) == {"a", "b", "relation_type", "confidence"}
              for e in g["edges"]))
    person_node = next(nd for nd in g["nodes"] if nd["kind"] == "PERSON")
    check("artifact_count = 2 for merged person",
          person_node["artifact_count"] == 2)
    json.dumps(g)  # must be JSON-serializable
    check("payload JSON-serializable", True)


def test_input_validation():
    print("== input validation ==")
    try:
        resolve_identities([{"id": 1, "kind": "PERSON", "value": "x"}])
        check("missing artifact_id raises", False)
    except ValueError:
        check("missing artifact_id raises", True)
    try:
        resolve_identities([
            {"id": 1, "artifact_id": 1, "kind": "PERSON", "value": "x"},
            {"id": 1, "artifact_id": 1, "kind": "PERSON", "value": "y"},
        ])
        check("duplicate id raises", False)
    except ValueError:
        check("duplicate id raises", True)
    check("empty input -> empty output", resolve_identities([]) == ([], []))


if __name__ == "__main__":
    test_normalize()
    test_deterministic_merge()
    test_relations()
    test_idempotency()
    test_negative_pair()
    test_exact_merge_without_model()
    test_fuzzy_mechanism_with_stub()
    test_graph_shape()
    test_input_validation()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", FAIL)
        sys.exit(1)
    print("ALL CORRELATION TESTS PASSED")
