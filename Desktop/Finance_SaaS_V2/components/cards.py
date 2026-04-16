"""
components/cards.py — Composants UI réutilisables et constantes d'affichage.

Exports principaux :
    CAT_COLORS, HUMEUR_ICONE, HUMEUR_COLOR, IDENTITE_LABEL, IDENTITE_DESC, COACH_INTRO
    fs_card(), alerte_box(), cat_row(), afficher_coach()
"""

import streamlit as st

# ─── Constantes d'affichage ──────────────────────────────────────────────────

from components.design_tokens import T

CAT_COLORS = T.CAT_PALETTE

HUMEUR_ICONE = {"COOL": "😎", "NEUTRE": "🤔", "SERIEUX": "⚠️"}
HUMEUR_COLOR = {"COOL": T.SUCCESS, "NEUTRE": T.WARNING, "SERIEUX": T.DANGER}

IDENTITE_LABEL = {
    "BATISSEUR": "🏗️ Bâtisseur",
    "EQUILIBRE":  "⚖️ Équilibré",
    "STRATEGE":   "🎯 Stratège",
    "LIBERE":     "🔓 Libéré",
}
IDENTITE_DESC = {
    "BATISSEUR": "Épargne max — factuel, zéro fioritures",
    "EQUILIBRE":  "50/30/20 standard — bienveillant",
    "STRATEGE":   "Orienté objectif — trajectoire",
    "LIBERE":     "Chasse le gaspillage — direct",
}

# Phrases d'intro du coach selon humeur + identité
COACH_INTRO = {
    ("BATISSEUR", "COOL"):    "Résultats dans les clous. Rien à signaler.",
    ("BATISSEUR", "NEUTRE"):  "Des ajustements sont nécessaires. Voici les chiffres.",
    ("BATISSEUR", "SERIEUX"): "Situation dégradée. Action immédiate requise.",
    ("EQUILIBRE",  "COOL"):   "Khoya, tu gères bien ce mois ! Continue comme ça 💪",
    ("EQUILIBRE",  "NEUTRE"): "Pas mal, mais on peut mieux faire. Quelques ajustements suffisent.",
    ("EQUILIBRE",  "SERIEUX"):"Khoya, là c'est sérieux. Il faut qu'on règle ça ensemble.",
    ("STRATEGE",  "COOL"):    "Trajectoire conforme. Tu avances vers tes objectifs.",
    ("STRATEGE",  "NEUTRE"):  "Légèrement hors trajectoire. Voici le plan de rattrapage.",
    ("STRATEGE",  "SERIEUX"): "Alerte rouge — l'objectif est en danger. Agis maintenant.",
    ("LIBERE",    "COOL"):    "Propre ! T'as bien géré, l'argent travaille pour toi.",
    ("LIBERE",    "NEUTRE"):  "Il y a du gaspillage silencieux. Je te montre où.",
    ("LIBERE",    "SERIEUX"): "Stop. L'argent part n'importe où. On règle ça maintenant.",
}


# ─── Composants ──────────────────────────────────────────────────────────────

def fs_card(label: str, value: str, sub: str = "", accent: str = None) -> None:
    accent = accent or T.PRIMARY
    st.markdown(
        f'<div class="fs-card" style="--accent:{accent}">'
        f'<div class="lbl">{label}</div>'
        f'<div class="val">{value}</div>'
        f'<div class="sub">{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def alerte_box(msg: str, couleur: str = None) -> None:
    couleur = couleur or T.DANGER
    st.markdown(
        f'<div class="fs-alert" style="color:{couleur};'
        f'border-color:{couleur};background:{couleur}15">⚠️ {msg}</div>',
        unsafe_allow_html=True,
    )


def cat_row(nom: str, montant: float, poids: float, couleur: str) -> None:
    bar_w   = min(poids, 100)
    amt_str = f"{abs(montant):,.0f} DH".replace(",", " ")
    st.markdown(
        f'<div class="fs-cat">'
        f'<div class="cat-dot" style="background:{couleur}"></div>'
        f'<div style="flex:1;min-width:0">'
        f'<div class="cat-name">{nom}</div>'
        f'<div class="fs-bar-bg">'
        f'<div class="fs-bar" style="width:{bar_w}%;background:{couleur}"></div>'
        f'</div></div>'
        f'<div class="cat-right">'
        f'<div class="cat-amt">{amt_str}</div>'
        f'<div class="cat-pct">{poids:.1f}%</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def afficher_coach(message: str, humeur: str, identite: str) -> None:
    """
    Affiche le message du coach via st.chat_message.
    L'intro change selon identité × humeur pour donner une vraie personnalité.
    """
    intro   = COACH_INTRO.get((identite, humeur), "")
    icone   = HUMEUR_ICONE.get(humeur, "💬")
    couleur = HUMEUR_COLOR.get(humeur, T.PRIMARY)
    lbl     = IDENTITE_LABEL.get(identite, identite)

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
        f'<span style="font-size:18px">{icone}</span>'
        f'<span style="color:{couleur};font-weight:700;font-size:12px;'
        f'text-transform:uppercase;letter-spacing:1px">{humeur}</span>'
        f'<span style="color:{T.TEXT_MUTED};font-size:11px">· {lbl}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.chat_message("assistant"):
        if intro:
            st.markdown(f"**{intro}**")
        st.write(message)
