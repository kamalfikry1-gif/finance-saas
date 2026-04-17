"""
tests/test_douane.py — Pure-logic tests for the Douane normalizer.

No DB, no mocks — just input → expected output.
"""

from datetime import date

import pytest

from logic_sqlite import Douane


# ── normaliser_texte ─────────────────────────────────────────────────────────

class TestNormaliserTexte:
    def test_uppercases(self):
        assert Douane.normaliser_texte("marjane") == "MARJANE"

    def test_strips_whitespace(self):
        assert Douane.normaliser_texte("  hello  ") == "HELLO"

    def test_removes_accents(self):
        assert Douane.normaliser_texte("Épicerie") == "EPICERIE"
        assert Douane.normaliser_texte("Café") == "CAFE"

    def test_collapses_inner_whitespace(self):
        assert Douane.normaliser_texte("MARJANE   CITE    YACOUB") == "MARJANE CITE YACOUB"

    def test_strips_special_characters(self):
        # punctuation that isn't word/space/hyphen/apos/dot/slash → replaced by space
        assert Douane.normaliser_texte("ZARA!!!") == "ZARA"
        assert Douane.normaliser_texte("H&M") == "H M"

    def test_preserves_hyphens_and_apostrophes(self):
        assert Douane.normaliser_texte("drive-in") == "DRIVE-IN"
        assert Douane.normaliser_texte("l'épicerie") == "L'EPICERIE"

    def test_empty_input_returns_empty(self):
        assert Douane.normaliser_texte("") == ""
        assert Douane.normaliser_texte("   ") == ""

    def test_none_or_nan_returns_empty(self):
        import numpy as np
        assert Douane.normaliser_texte(np.nan) == ""


# ── normaliser_montant ───────────────────────────────────────────────────────

class TestNormaliserMontant:
    def test_plain_float(self):
        assert Douane.normaliser_montant(12.50) == 12.50

    def test_string_with_comma(self):
        assert Douane.normaliser_montant("12,50") == 12.50

    def test_string_with_spaces(self):
        assert Douane.normaliser_montant("1 000,50") == 1000.50

    def test_string_with_thousand_separator(self):
        # "1.000,50" European format: dot = thousands, comma = decimal
        assert Douane.normaliser_montant("1.000,50") == 1000.50

    def test_invalid_string_returns_none(self):
        assert Douane.normaliser_montant("abc") is None
        assert Douane.normaliser_montant("") is None

    def test_non_breaking_space_stripped(self):
        assert Douane.normaliser_montant("1\u00a0000,00") == 1000.00

    def test_rounds_to_two_decimals(self):
        assert Douane.normaliser_montant(12.3456) == 12.35


# ── normaliser_date ──────────────────────────────────────────────────────────

class TestNormaliserDate:
    @pytest.mark.parametrize("raw,expected", [
        ("17/04/2026", date(2026, 4, 17)),
        ("17-04-2026", date(2026, 4, 17)),
        ("2026-04-17", date(2026, 4, 17)),
        ("17.04.2026", date(2026, 4, 17)),
        ("2026/04/17", date(2026, 4, 17)),
    ])
    def test_accepts_common_formats(self, raw, expected):
        assert Douane.normaliser_date(raw) == expected

    def test_two_digit_year(self):
        assert Douane.normaliser_date("17/04/26") == date(2026, 4, 17)

    def test_invalid_returns_none(self):
        assert Douane.normaliser_date("not a date") is None
        assert Douane.normaliser_date("") is None
        assert Douane.normaliser_date("32/13/2026") is None


# ── supprimer_accents ────────────────────────────────────────────────────────

class TestSupprimerAccents:
    @pytest.mark.parametrize("raw,expected", [
        ("café", "cafe"),
        ("épicerie", "epicerie"),
        ("hôpital", "hopital"),
        ("naïve", "naive"),
        ("piñata", "pinata"),
        ("plain", "plain"),
    ])
    def test_removes_diacritics(self, raw, expected):
        assert Douane.supprimer_accents(raw) == expected
