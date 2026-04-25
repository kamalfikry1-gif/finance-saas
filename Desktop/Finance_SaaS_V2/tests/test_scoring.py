"""
tests/test_scoring.py — Critical tests for scoring and humeur logic.

These 5 tests cover the 3 bugs that have already hit production:
  1. No explicit savings → should NOT be SERIEUX
  2. Projected solde used as fallback (not live solde)
  3. effective_savings fallback in humeur
  4. Negative solde → always SERIEUX
  5. Explicit savings transactions → used directly, no fallback

Run with: pytest tests/test_scoring.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_score(taux_ep: float, score: float = 80.0, niveau: str = "BON") -> dict:
    return {"taux_epargne_pct": taux_ep, "score": score, "niveau": niveau}


def _make_bilan(solde: float, revenus: float = 10_500.0):
    b = MagicMock()
    b.evolution_dh = solde
    b.revenus      = revenus
    b.epargne_reelle = 0.0
    return b


def _make_bvr_5030(savings_pct: float = 0.0) -> dict:
    return {
        "buckets": {
            "Savings": {"reel_pct": savings_pct, "cible_pct": 20.0, "reel_dh": 0},
            "Needs":   {"reel_pct": 12.0, "cible_pct": 50.0, "reel_dh": 1280},
            "Wants":   {"reel_pct": 0.0,  "cible_pct": 30.0, "reel_dh": 0},
        }
    }


# ── Load AuditMiddleware with mocked DB ───────────────────────────────────────

from config import IDENTITES_COACH, HUMEUR_COOL, HUMEUR_NEUTRE, HUMEUR_SERIEUX


def _make_audit(identite: str = "EQUILIBRE") -> "AuditMiddleware":
    from audit import AuditMiddleware
    from logic_sqlite import MoteurAnalyse

    db = MagicMock()
    db.get_preference.return_value = identite

    fake_conn = MagicMock()
    fake_conn.__enter__ = lambda s: fake_conn
    fake_conn.__exit__ = MagicMock(return_value=False)
    fake_conn.execute.return_value = MagicMock(
        fetchone=lambda: None, fetchall=lambda: []
    )
    db.connexion.return_value = fake_conn

    audit = AuditMiddleware.__new__(AuditMiddleware)
    audit.db              = db
    audit.user_id         = 1
    audit._identite_cache = identite   # bypass DB call in get_identite()
    audit.moteur          = MagicMock(spec=MoteurAnalyse)
    return audit


# ── Test 1: No explicit savings → humeur should NOT be SERIEUX ───────────────

def test_no_explicit_savings_not_serieux():
    """
    Regression: with 87.8% implicit savings and score=95, humeur must be COOL
    not SERIEUX. Bug was savings_reel_pct=0 triggering SERIEUX gate.
    """
    audit = _make_audit("BATISSEUR")
    score  = _make_score(taux_ep=87.8, score=95.0, niveau="EXCELLENT")
    bilan  = _make_bilan(solde=9_220.0)
    bvr    = _make_bvr_5030(savings_pct=0.0)   # no explicit savings bucket

    humeur = audit._calculer_humeur(score, bilan, bvr)
    assert humeur != HUMEUR_SERIEUX, (
        f"Got SERIEUX at score=95 and taux_ep=87.8% — effective_savings fallback broken"
    )


# ── Test 2: Projected solde used, not live solde ─────────────────────────────

def test_projected_solde_used_as_fallback():
    """
    Score fallback should use solde_projete (end-of-month estimate),
    not bilan.evolution_dh (live snapshot). At day 25/30 these differ.
    """
    from logic_sqlite import MoteurAnalyse

    moteur = MagicMock(spec=MoteurAnalyse)
    moteur.get_bilan_mensuel.return_value = _make_bilan(solde=9_220.0, revenus=10_500.0)
    moteur.get_budget_vs_reel.return_value = MagicMock(
        __len__=lambda s: 0,
        **{"__bool__": lambda s: False}
    )

    import pandas as pd
    moteur.get_budget_vs_reel.return_value = pd.DataFrame()
    moteur.get_repartition_par_categorie.return_value = pd.DataFrame()
    moteur.get_projection_fin_mois.return_value = {
        "solde_projete": 8_964.0,   # lower than live solde — projection is honest
        "projection_fin_mois": 1_536.0,
    }

    from logic_sqlite import MoteurAnalyse as MA
    result = MA.get_score_sante_financiere(moteur, mois="04/2026")

    taux = result["taux_epargne_pct"]
    expected = round(8_964.0 / 10_500.0 * 100, 1)   # 85.4%
    assert abs(taux - expected) < 0.5, (
        f"Expected taux_ep≈{expected}% (projected), got {taux}% (live solde used instead)"
    )


# ── Test 3: Negative solde → always SERIEUX ───────────────────────────────────

def test_negative_solde_always_serieux():
    """Negative balance must always produce SERIEUX regardless of score."""
    audit = _make_audit("EQUILIBRE")
    score  = _make_score(taux_ep=5.0, score=80.0)
    bilan  = _make_bilan(solde=-500.0)
    bvr    = _make_bvr_5030(savings_pct=10.0)

    humeur = audit._calculer_humeur(score, bilan, bvr)
    assert humeur == HUMEUR_SERIEUX, (
        f"Expected SERIEUX on negative solde, got {humeur}"
    )


# ── Test 4: Explicit savings transactions take priority over fallback ──────────

def test_explicit_savings_take_priority():
    """
    When epargne_reelle > 0 (explicit savings transactions exist),
    taux_ep must be computed from that, not from solde_projete.
    """
    from logic_sqlite import MoteurAnalyse

    bilan_mock = _make_bilan(solde=5_000.0, revenus=10_000.0)
    bilan_mock.epargne_reelle = 3_000.0   # explicit: 30%

    moteur = MagicMock(spec=MoteurAnalyse)
    moteur.get_bilan_mensuel.return_value = bilan_mock
    moteur.get_budget_vs_reel.return_value = __import__("pandas").DataFrame()
    moteur.get_repartition_par_categorie.return_value = __import__("pandas").DataFrame()
    moteur.get_projection_fin_mois.return_value = {"solde_projete": 9_000.0}

    result = MoteurAnalyse.get_score_sante_financiere(moteur, mois="04/2026")
    taux = result["taux_epargne_pct"]

    # Must be 30% (from epargne_reelle=3000/10000), NOT 90% (from solde_projete=9000)
    assert abs(taux - 30.0) < 0.5, (
        f"Expected taux_ep=30% from explicit savings, got {taux}% — fallback overriding explicit"
    )


# ── Test 5: COOL requires all conditions met ──────────────────────────────────

def test_cool_requires_all_conditions():
    """
    COOL requires: solde > 0 AND score >= seuil AND effective_savings >= target*0.6.
    Failing any one condition should NOT produce COOL.
    """
    audit = _make_audit("EQUILIBRE")

    # Condition: score below seuil (EQUILIBRE seuil = 60 typically)
    score_low = _make_score(taux_ep=80.0, score=30.0)
    bilan_pos  = _make_bilan(solde=5_000.0)
    bvr_good   = _make_bvr_5030(savings_pct=20.0)

    humeur = audit._calculer_humeur(score_low, bilan_pos, bvr_good)
    assert humeur != HUMEUR_COOL, (
        f"Expected NOT COOL when score=30 (below seuil), got {humeur}"
    )

    # Condition: all good → should be COOL
    score_good = _make_score(taux_ep=80.0, score=90.0)
    humeur2 = audit._calculer_humeur(score_good, bilan_pos, bvr_good)
    assert humeur2 == HUMEUR_COOL, (
        f"Expected COOL with score=90, solde>0, savings=20%, got {humeur2}"
    )
