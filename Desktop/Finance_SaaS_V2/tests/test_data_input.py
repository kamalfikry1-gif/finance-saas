"""
tests/test_data_input.py — core/data_input.py front-door validation.

enregistrer_transaction is the thin wrapper views call before delegating
to audit.recevoir. We only test its own guard clauses here — audit is
already covered in test_audit.py.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from core.data_input import enregistrer_transaction


@pytest.fixture
def audit_stub():
    """Minimal audit stub — we only care that recevoir is (or isn't) called."""
    audit = MagicMock()
    audit.recevoir.return_value = {"action": "OK", "categorie": "Vie Quotidienne"}
    return audit


class TestGuardClauses:
    def test_empty_libelle_rejected_without_calling_audit(self, audit_stub):
        res = enregistrer_transaction(audit_stub, "", 10, "OUT", date.today())
        assert res["action"] == "ERREUR"
        audit_stub.recevoir.assert_not_called()

    def test_whitespace_libelle_rejected(self, audit_stub):
        res = enregistrer_transaction(audit_stub, "   ", 10, "OUT", date.today())
        assert res["action"] == "ERREUR"
        audit_stub.recevoir.assert_not_called()

    def test_zero_montant_rejected(self, audit_stub):
        res = enregistrer_transaction(audit_stub, "MARJANE", 0, "OUT", date.today())
        assert res["action"] == "ERREUR"
        audit_stub.recevoir.assert_not_called()

    def test_negative_montant_rejected(self, audit_stub):
        res = enregistrer_transaction(audit_stub, "MARJANE", -5, "OUT", date.today())
        assert res["action"] == "ERREUR"
        audit_stub.recevoir.assert_not_called()

    def test_invalid_sens_rejected(self, audit_stub):
        res = enregistrer_transaction(audit_stub, "MARJANE", 10, "XYZ", date.today())
        assert res["action"] == "ERREUR"
        audit_stub.recevoir.assert_not_called()


class TestDelegation:
    def test_valid_input_delegates_to_audit(self, audit_stub):
        res = enregistrer_transaction(audit_stub, "MARJANE", 45.50, "OUT", date.today())
        assert res["action"] == "OK"
        audit_stub.recevoir.assert_called_once()

    def test_libelle_trimmed_before_delegation(self, audit_stub):
        enregistrer_transaction(audit_stub, "  MARJANE  ", 10, "OUT", date.today())
        called_args = audit_stub.recevoir.call_args
        assert called_args[0][0] == "MARJANE"

    def test_forcer_flag_propagated(self, audit_stub):
        enregistrer_transaction(audit_stub, "MARJANE", 10, "OUT", date.today(), forcer=True)
        assert audit_stub.recevoir.call_args.kwargs["forcer"] is True

    def test_source_propagated(self, audit_stub):
        enregistrer_transaction(audit_stub, "MARJANE", 10, "OUT", date.today(), source="IMPORT")
        assert audit_stub.recevoir.call_args.kwargs["source"] == "IMPORT"
