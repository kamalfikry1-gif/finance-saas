"""
core/cache.py — Caches Streamlit centralisés + invalidation ciblée.

Règle : tout `st.cache_data` vit ici. Les écritures utilisent `invalider()`
au lieu de `st.cache_data.clear()` pour n'invalider que les caches UI,
sans toucher aux caches futurs (données de référence, etc.).

TTL strategy:
  STREAMLIT_CACHE_TTL (300s) — données qui changent après chaque écriture user
  3600s                      — données de référence quasi-statiques (catégories)
"""

from typing import Dict, List
import streamlit as st

from config import STREAMLIT_CACHE_TTL


# ── Dashboard & analytics ─────────────────────────────────────────────────────

@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_state(_audit, mois: str, identite: str, uid: int) -> Dict:
    return _audit.get_ui_state(mois)


@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def query(_audit, demande: str, uid: int, **kw) -> Dict:
    return _audit.query(demande, **kw)


# ── Objectifs ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_objectifs(_audit, uid: int) -> List:
    return _audit.get_objectifs_v2() or []


@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_objectifs_type(_audit, type_obj: str, uid: int) -> List:
    return _audit.get_objectifs_v2(type_obj) or []


# ── Plafonds & dépenses ───────────────────────────────────────────────────────

@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_plafonds(_audit, uid: int) -> List:
    return _audit.get_plafonds_categories()


@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_depenses_mois(_audit, mois: str, uid: int) -> Dict:
    return _audit.get_depenses_mois(mois)


# ── Référentiel (quasi-statique — TTL long) ───────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_categories(_audit, uid: int) -> List[str]:
    return _audit.get_categories()


@st.cache_data(ttl=3600, show_spinner=False)
def get_sous_categories(_audit, categorie: str, uid: int) -> List[str]:
    return _audit.get_sous_categories(categorie)


# ── Daret & Journal ───────────────────────────────────────────────────────────

@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_darets(_audit, uid: int) -> List:
    return _audit.get_darets()


@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_journal(_audit, uid: int) -> List:
    return _audit.get_journal(limit=200)


# ── Invalidation ─────────────────────────────────────────────────────────────

def invalider() -> None:
    """Clear all UI-state caches — à appeler après toute écriture."""
    get_state.clear()
    query.clear()
    get_objectifs.clear()
    get_objectifs_type.clear()
    get_plafonds.clear()
    get_depenses_mois.clear()
    get_darets.clear()
    get_journal.clear()
    # get_categories / get_sous_categories intentionally NOT cleared here —
    # they have a 1h TTL and only change at schema migration time.
