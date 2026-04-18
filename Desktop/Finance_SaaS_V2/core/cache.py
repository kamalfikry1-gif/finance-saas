"""
core/cache.py — Caches Streamlit centralisés + invalidation ciblée.

Règle : tout `st.cache_data` vit ici. Les écritures utilisent `invalider()`
au lieu de `st.cache_data.clear()` pour n'invalider que les caches UI,
sans toucher aux caches futurs (données de référence, etc.).
"""

from typing import Dict
import streamlit as st

from config import STREAMLIT_CACHE_TTL


@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_state(_audit, mois: str, identite: str, uid: int) -> Dict:
    return _audit.get_ui_state(mois)


@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def get_anticipation(_audit, mois: str, identite: str, uid: int) -> Dict:
    return _audit.get_anticipation(mois)


@st.cache_data(ttl=STREAMLIT_CACHE_TTL, show_spinner=False)
def query(_audit, demande: str, uid: int, **kw) -> Dict:
    return _audit.query(demande, use_cache=True, **kw)


def invalider() -> None:
    """Clear only the UI-state caches — à appeler après toute écriture."""
    get_state.clear()
    get_anticipation.clear()
    query.clear()
