"""
tests/test_trieur.py — Classification logic tests for the Trieur.

The Trieur loads DICO_MATCHING on __init__ via conn.execute.fetchall().
We pre-queue dictionary rows in the fake connection, then test the 5
classification levels: EXACT, EXACT_COURT, NEAR_AUTO, PARTIEL, FUZZY, repli.
"""

import pytest

from logic_sqlite import Trieur, FALLBACK_OUT, FALLBACK_IN


# Dictionary rows as Postgres would return them:
#   (Sens, Mot_Cle, Categorie_Cible, Sous_Categorie_Cible)
DICO_ROWS = [
    ("OUT", "MARJANE",   "Vie Quotidienne", "Courses maison"),
    ("OUT", "CARREFOUR", "Vie Quotidienne", "Courses maison"),
    ("OUT", "PHARMACIE", "Santé",           "Pharmacie"),
    ("OUT", "NETFLIX",   "Abonnements",     "Streaming & TV"),
    ("OUT", "KFC",       "Vie Quotidienne", "Restaurant rapide & fast food"),  # 3 chars → acronyme
    ("OUT", "BIM",       "Vie Quotidienne", "Courses maison"),                  # 3 chars
    ("IN",  "SALAIRE",   "Revenu",          "Salaire"),
]


def _make_trieur(fake_db):
    """Helper: queue DICO rows then instantiate Trieur."""
    fake_db.conn.queue_rows(DICO_ROWS)
    return Trieur(fake_db, user_id=1)


# ── Construction ─────────────────────────────────────────────────────────────

class TestTrieurInit:
    def test_loads_dictionary(self, fake_db):
        t = _make_trieur(fake_db)
        # 5 mots >= 4 chars in fuzzy dict + 2 acronyms (<4 chars)
        assert len(t._dico) == 5
        assert len(t._dico_exact) == 2

    def test_acronyms_separated_from_fuzzy(self, fake_db):
        t = _make_trieur(fake_db)
        # _dico_exact stores acronyms with the same casing as the dict feed
        assert ("KFC", "OUT") in t._dico_exact
        assert ("BIM", "OUT") in t._dico_exact
        # _dico (fuzzy) stores longer words and is keyed the same way
        assert any(k[0].upper() == "MARJANE" and k[1] == "OUT" for k in t._dico)
        assert not any(k[0].upper() == "MARJANE" for k in t._dico_exact)


# ── Niveau 1 : EXACT ─────────────────────────────────────────────────────────

class TestExactMatch:
    def test_exact_word(self, fake_db):
        t = _make_trieur(fake_db)
        res = t.classifier("MARJANE", "OUT")
        assert res.categorie == "Vie Quotidienne"
        assert res.sous_categorie == "Courses maison"
        assert res.methode == "EXACT"
        assert res.score == 100.0

    def test_exact_case_insensitive(self, fake_db):
        t = _make_trieur(fake_db)
        res = t.classifier("marjane", "OUT")
        assert res.methode == "EXACT"

    def test_exact_with_accents(self, fake_db):
        t = _make_trieur(fake_db)
        # "PHARMACIE" matches via normalized comparison
        res = t.classifier("Pharmacie", "OUT")
        assert res.methode == "EXACT"
        assert res.categorie == "Santé"


# ── Niveau 2 : EXACT_COURT (acronymes) ───────────────────────────────────────

class TestAcronymMatch:
    def test_acronym_standalone(self, fake_db):
        t = _make_trieur(fake_db)
        res = t.classifier("KFC", "OUT")
        assert res.methode == "EXACT_COURT"
        assert res.sous_categorie == "Restaurant rapide & fast food"

    def test_acronym_word_boundary_required(self, fake_db):
        """'BIM' should NOT match 'BIMENSUEL' (substring without boundary)."""
        t = _make_trieur(fake_db)
        res = t.classifier("BIMENSUEL", "OUT")
        # No acronym match, no fuzzy match strong enough → repli
        assert res.methode != "EXACT_COURT"

    def test_acronym_inside_phrase(self, fake_db):
        t = _make_trieur(fake_db)
        res = t.classifier("COURSES KFC HAY RIAD", "OUT")
        assert res.methode == "EXACT_COURT"


# ── Niveau 3 : NEAR_AUTO (fuzzy >= 85) ───────────────────────────────────────

class TestFuzzyAutoMatch:
    def test_typo_one_char(self, fake_db):
        t = _make_trieur(fake_db)
        res = t.classifier("MARJAN", "OUT")  # missing one char
        assert res.methode in ("NEAR_AUTO", "EXACT", "PARTIEL")
        assert res.categorie == "Vie Quotidienne"

    def test_prefix_match_user_request(self, fake_db):
        """User reported 'marj' should match MARJANE."""
        t = _make_trieur(fake_db)
        res = t.classifier("marj", "OUT")
        # Whether via NEAR_AUTO or FUZZY fallback, it must NOT be Divers
        assert res.categorie != "Divers", f"'marj' was classified as {res.categorie}/{res.sous_categorie}"


# ── Niveau 4 : PARTIEL (token contenu) ───────────────────────────────────────

class TestPartialMatch:
    def test_keyword_inside_long_label(self, fake_db):
        """Real transaction labels often look like 'CB MARJANE HAY RIAD 150DH'."""
        t = _make_trieur(fake_db)
        res = t.classifier("CB MARJANE HAY RIAD 150", "OUT")
        assert res.categorie == "Vie Quotidienne"
        assert res.sous_categorie == "Courses maison"


# ── Sens filter ──────────────────────────────────────────────────────────────

class TestSensFilter:
    def test_in_dico_does_not_match_out_query(self, fake_db):
        """SALAIRE is in the IN dico — querying 'SALAIRE' as OUT must not match it."""
        t = _make_trieur(fake_db)
        res = t.classifier("SALAIRE", "OUT")
        assert res.categorie != "Revenu"

    def test_out_dico_does_not_match_in_query(self, fake_db):
        """MARJANE is in OUT dico — querying as IN must fall back to IN repli."""
        t = _make_trieur(fake_db)
        res = t.classifier("MARJANE", "IN")
        # IN repli is Revenu/Revenu_Autre via FALLBACK_IN
        assert res.categorie == FALLBACK_IN[0]


# ── Repli (unknown keyword) ──────────────────────────────────────────────────

class TestRepli:
    def test_unknown_out_goes_to_fallback(self, fake_db):
        t = _make_trieur(fake_db)
        res = t.classifier("XYZUNKNOWN123", "OUT")
        assert res.categorie == FALLBACK_OUT[0]
        assert res.sous_categorie == FALLBACK_OUT[1]
        assert res.methode == "INCONNU"

    def test_unknown_in_goes_to_fallback(self, fake_db):
        t = _make_trieur(fake_db)
        res = t.classifier("XYZUNKNOWN123", "IN")
        assert res.categorie == FALLBACK_IN[0]
        assert res.sous_categorie == FALLBACK_IN[1]

    def test_empty_input_goes_to_repli(self, fake_db):
        t = _make_trieur(fake_db)
        res = t.classifier("", "OUT")
        assert res.methode == "INCONNU"


# ── Apprendre (feedback loop) ────────────────────────────────────────────────

class TestApprendre:
    def test_learns_new_keyword(self, fake_db):
        t = _make_trieur(fake_db)
        initial_len = len(t._dico)
        t.apprendre("DOMINO PIZZA", "Vie Quotidienne", "Restaurant rapide & fast food", "OUT")
        assert len(t._dico) == initial_len + 1
        # Verify it now matches
        res = t.classifier("DOMINO PIZZA", "OUT")
        assert res.sous_categorie == "Restaurant rapide & fast food"

    def test_learns_emits_insert(self, fake_db):
        t = _make_trieur(fake_db)
        t.apprendre("DOMINO", "Vie Quotidienne", "Restaurant rapide & fast food", "OUT")
        insert_calls = [c for c in fake_db.conn.calls if "INSERT INTO DICO_MATCHING" in c[0]]
        assert len(insert_calls) == 1
