"""
tests/test_audit.py — AuditMiddleware tests.

Covers:
  - _valider_input (pure validation logic)
  - _mois_jusqu_a (static helper for objectif delta)
  - Construction: Trieur + ComptableBudget must init cleanly with mocked DB.

AuditMiddleware.__init__ triggers:
  1. Trieur(...) → loads DICO_MATCHING
  2. ComptableBudget(...) → _charger_ids_epargne queries REFERENTIEL
So we queue two result sets (DICO first, REFERENTIEL second) on the fake DB.
"""

from datetime import datetime

import pytest

from audit import AuditMiddleware


# Minimal dico + referentiel so both inner constructors finish cleanly.
DICO_ROWS = [
    ("OUT", "MARJANE", "Vie Quotidienne", "Courses maison"),
]
REFERENTIEL_ROWS = [
    ("Epargne", "Epargne & Investissement"),
]


def _make_audit(fake_db, user_id=1):
    fake_db.conn.queue_rows(DICO_ROWS)
    fake_db.conn.queue_rows(REFERENTIEL_ROWS)
    return AuditMiddleware(fake_db, user_id=user_id)


# ── Construction ─────────────────────────────────────────────────────────────

class TestInit:
    def test_builds_with_mocked_db(self, fake_db):
        audit = _make_audit(fake_db)
        assert audit.user_id == 1
        assert audit.trieur is not None
        assert audit.comptable is not None
        assert audit.moteur is not None

    def test_user_id_threaded_to_components(self, fake_db):
        audit = _make_audit(fake_db, user_id=42)
        assert audit.user_id == 42
        assert audit.trieur.user_id == 42
        assert audit.comptable.user_id == 42


# ── _valider_input ───────────────────────────────────────────────────────────

class TestValiderInput:
    @pytest.fixture
    def audit(self, fake_db):
        return _make_audit(fake_db)

    def test_valid_input_returns_none(self, audit):
        assert audit._valider_input("MARJANE", 45.50, "OUT") is None

    def test_empty_mot_cle_rejected(self, audit):
        assert audit._valider_input("", 10, "OUT") is not None
        assert audit._valider_input("   ", 10, "OUT") is not None

    def test_non_string_mot_cle_rejected(self, audit):
        assert audit._valider_input(None, 10, "OUT") is not None
        assert audit._valider_input(123, 10, "OUT") is not None

    def test_montant_zero_rejected(self, audit):
        err = audit._valider_input("MARJANE", 0, "OUT")
        assert err is not None and "positif" in err.lower()

    def test_montant_negative_rejected(self, audit):
        assert audit._valider_input("MARJANE", -10, "OUT") is not None

    def test_montant_non_numeric_rejected(self, audit):
        err = audit._valider_input("MARJANE", "abc", "OUT")
        assert err is not None and "nombre" in err.lower()

    def test_montant_too_large_rejected(self, audit):
        assert audit._valider_input("MARJANE", 9_999_999, "OUT") is not None

    def test_sens_invalid_rejected(self, audit):
        err = audit._valider_input("MARJANE", 10, "INVALIDE")
        assert err is not None and "sens" in err.lower()

    def test_sens_lowercase_accepted(self, audit):
        # _valider_input uppercases sens before checking
        assert audit._valider_input("MARJANE", 10, "out") is None
        assert audit._valider_input("MARJANE", 10, "in") is None


# ── _mois_jusqu_a ────────────────────────────────────────────────────────────

class TestMoisJusquA:
    def test_future_month(self):
        now = datetime.now()
        target_m = now.month
        target_y = now.year + 1
        cible = f"{target_m:02d}/{target_y}"
        assert AuditMiddleware._mois_jusqu_a(cible) == 12

    def test_current_month_returns_min_one(self):
        now = datetime.now()
        cible = f"{now.month:02d}/{now.year}"
        # Same month → delta=0, clamped to 1
        assert AuditMiddleware._mois_jusqu_a(cible) == 1

    def test_past_month_clamped_to_one(self):
        # Well in the past → still returns 1
        assert AuditMiddleware._mois_jusqu_a("01/2000") == 1

    def test_invalid_format_returns_default(self):
        assert AuditMiddleware._mois_jusqu_a("bogus") == 12
        assert AuditMiddleware._mois_jusqu_a("") == 12
