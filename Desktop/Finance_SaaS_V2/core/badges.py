"""
core/badges.py — Badge tracking via PREFERENCES.badges_json.

Badges are awarded once per user, persistent across sessions. Stored as
JSON list in PREFERENCES under the key 'badges_json'.

Format (list of dicts):
    [
        {"id": "premier_pas", "label": "Premier pas", "icon": "🎉",
         "earned_at": "2026-04-26T20:00:00"},
        ...
    ]

API:
    has_badge(audit, badge_id) -> bool
    award_badge(audit, badge_id, label, icon) -> bool   # True if newly awarded
    get_badges(audit) -> list of dicts                  # ordered by earned_at
"""

from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict, List


_PREF_KEY = "badges_json"


def _load(audit) -> List[Dict[str, Any]]:
    raw = audit.db.get_preference(_PREF_KEY, audit.user_id, "[]")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _save(audit, badges: List[Dict[str, Any]]) -> None:
    audit.db.set_preference(_PREF_KEY, json.dumps(badges), audit.user_id)


def has_badge(audit, badge_id: str) -> bool:
    return any(b.get("id") == badge_id for b in _load(audit))


def award_badge(audit, badge_id: str, label: str, icon: str = "🏆") -> bool:
    """Award a badge if not already earned. Returns True if newly awarded."""
    badges = _load(audit)
    if any(b.get("id") == badge_id for b in badges):
        return False
    badges.append({
        "id":        badge_id,
        "label":     label,
        "icon":      icon,
        "earned_at": datetime.now().isoformat(timespec="seconds"),
    })
    _save(audit, badges)
    return True


def get_badges(audit) -> List[Dict[str, Any]]:
    """All badges earned by this user, ordered by earned_at."""
    return sorted(_load(audit), key=lambda b: b.get("earned_at", ""))
