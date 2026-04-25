"""
views/epargne.py — Page Épargne.

Regroupe les deux onglets épargne d'objectif.py :
    · Objectifs Épargne   — créer / suivre des objectifs de constitution
    · Historique Épargne  — suivi mensuel + graphique cumulé
"""

import streamlit as st
from components.helpers import render_page_header
from views.objectif import _tab_epargne, _tab_histo_epargne


def render(ctx: dict) -> None:
    audit = ctx["audit"]

    render_page_header("💰", "Épargne", "Objectifs et historique de votre épargne")

    tab_obj, tab_histo = st.tabs(["🎯 Objectifs Épargne", "📈 Historique"])

    with tab_obj:
        _tab_epargne(audit)

    with tab_histo:
        _tab_histo_epargne(audit)
