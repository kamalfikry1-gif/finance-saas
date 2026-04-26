"""
core/hints.py — One-time UI hints tracked per user.

Each hint has a unique ID. First time a hint is shown, it can be marked as
seen via mark_hint_seen() and never shown again to that user. Stored as JSON
list in PREFERENCES under the key 'hints_seen_json'.

API:
    has_seen_hint(audit, hint_id) -> bool
    mark_hint_seen(audit, hint_id) -> None
    nb_hints_seen(audit) -> int                # for "Explorateur" badge
"""

from __future__ import annotations
import json
from typing import List


_PREF_KEY = "hints_seen_json"


def _load_seen(audit) -> List[str]:
    raw = audit.db.get_preference(_PREF_KEY, audit.user_id, "[]")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def has_seen_hint(audit, hint_id: str) -> bool:
    return hint_id in _load_seen(audit)


def mark_hint_seen(audit, hint_id: str) -> None:
    seen = _load_seen(audit)
    if hint_id not in seen:
        seen.append(hint_id)
        audit.db.set_preference(_PREF_KEY, json.dumps(seen), audit.user_id)


def nb_hints_seen(audit) -> int:
    return len(_load_seen(audit))
