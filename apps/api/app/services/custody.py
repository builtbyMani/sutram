"""Append-only chain-of-custody logging (INT-02).

Every touch of an artifact is recorded. Rows are insert-only by convention:
no code path may UPDATE or DELETE custody_log rows.
"""

from datetime import datetime, timezone

from ..models import CustodyLog

# Locked custody vocabulary (02-CONTEXT.md).
ACTIONS = ("ingest", "view", "extract", "analyze")


def log_custody(session, artifact_id: int, action: str, detail: str = "",
                actor: str = "investigator") -> CustodyLog:
    """Append one custody entry. Caller owns the transaction (no commit here)."""
    if action not in ACTIONS:
        raise ValueError(f"unknown custody action: {action!r}")
    entry = CustodyLog(
        artifact_id=artifact_id,
        action=action,
        actor=actor,
        ts=datetime.now(timezone.utc).isoformat(),
        detail=detail,
    )
    session.add(entry)
    return entry
