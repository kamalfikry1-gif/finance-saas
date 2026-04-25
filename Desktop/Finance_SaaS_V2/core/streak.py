"""
core/streak.py — Streak tracking logic (streak_jours, mois_verts).

Stored in PREFERENCES table (per-user), never in session_state so it
persists across sessions and devices.

Keys written:
    streak_jours           int   — consecutive days with at least 1 transaction
    streak_last_active     str   — ISO date of last active day (YYYY-MM-DD)
    mois_verts             int   — consecutive months with positive solde
    mois_verts_last_check  str   — month last verified (MM/YYYY)

Call actualiser_streak() + actualiser_mois_verts() once per session from app.py.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger("STREAK")


def _prev_month(mois: str) -> str:
    """Return the month before mois (MM/YYYY format)."""
    mm, yyyy = int(mois[:2]), int(mois[3:])
    if mm == 1:
        return f"12/{yyyy - 1}"
    return f"{mm - 1:02d}/{yyyy}"


def actualiser_streak(db, user_id: int) -> None:
    """
    Update streak_jours based on whether the user has transactions today.

    Rules:
    - Has transactions today + last_active was yesterday → streak + 1
    - Has transactions today + last_active was today    → no-op (already counted)
    - Has transactions today + gap > 1 day              → reset to 1
    - No transactions today + gap > 1 day from last_active → reset to 0
    """
    today = date.today()
    today_str = today.isoformat()

    last_active_str = db.get_preference("streak_last_active", user_id)
    streak = int(db.get_preference("streak_jours", user_id, "0") or "0")

    # Check if user has any transactions with Date_Valeur = today
    try:
        with db.connexion() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM TRANSACTIONS WHERE user_id = %s"
                " AND Date_Valeur::date = %s",
                (user_id, today_str),
            )
            has_today = (cur.fetchone()[0] or 0) > 0
    except Exception as e:
        logger.warning("streak check failed: %s", e)
        return

    if not has_today:
        # No activity today — check if the streak is now broken (gap > 1 day)
        if last_active_str:
            try:
                last_date = date.fromisoformat(last_active_str)
                if (today - last_date).days > 1:
                    db.set_preference("streak_jours", "0", user_id)
            except ValueError:
                pass
        return

    # User has transactions today
    if last_active_str == today_str:
        return  # Already processed today

    new_streak = 1
    if last_active_str:
        try:
            last_date = date.fromisoformat(last_active_str)
            if (today - last_date).days == 1:
                new_streak = streak + 1
        except ValueError:
            pass

    db.set_preference("streak_jours", str(new_streak), user_id)
    db.set_preference("streak_last_active", today_str, user_id)
    logger.debug("streak updated: %d days", new_streak)


def actualiser_mois_verts(db, audit, user_id: int) -> None:
    """
    At the turn of each new month, check if the previous month ended with
    a positive solde. If yes, increment mois_verts; otherwise reset to 0.
    """
    current_month = date.today().strftime("%m/%Y")
    last_check = db.get_preference("mois_verts_last_check", user_id)

    if last_check == current_month:
        return  # Already verified this month

    prev = _prev_month(current_month)
    try:
        res = audit.query("bilan_mensuel", mois=prev)
        bilan = res.get("resultat", {})
        if isinstance(bilan, list):
            bilan = bilan[0] if bilan else {}
        solde_prev = float(bilan.get("solde", 0) or 0)
    except Exception as e:
        logger.warning("mois_verts bilan failed: %s", e)
        solde_prev = 0.0

    mois_verts = int(db.get_preference("mois_verts", user_id, "0") or "0")
    mois_verts = mois_verts + 1 if solde_prev > 0 else 0

    db.set_preference("mois_verts", str(mois_verts), user_id)
    db.set_preference("mois_verts_last_check", current_month, user_id)
    logger.debug("mois_verts updated: %d", mois_verts)


def get_streak_data(db, user_id: int) -> tuple[int, int]:
    """Return (streak_jours, mois_verts) as integers."""
    streak = int(db.get_preference("streak_jours", user_id, "0") or "0")
    verts  = int(db.get_preference("mois_verts",  user_id, "0") or "0")
    return streak, verts
