"""
views/daret_public.py — Public read-only Daret view via invite token.

Anyone with the URL '?daret=TOKEN' can see the daret's payment table without
logging in. The manager (logged-in owner) sees the editable version on the
regular Daret page; this view is what their group members see when they
follow the WhatsApp invite link.

No auth, no edit buttons. Just the facts: members, monthly cagnotte, status grid.
"""

from __future__ import annotations
import json

import streamlit as st

from components.design_tokens import T
from components.helpers import dh as _dh
from components.styles import inject_css


# Status emoji + labels (kept in sync with views/daret.py)
_STATUS_EMOJI = {None: "🔴", "PENDING": "🔴", "DECLARED": "🟡", "PAID": "🟢"}
_STATUS_LABEL = {None: "En attente", "PENDING": "En attente",
                 "DECLARED": "Déclaré", "PAID": "Payé"}


def _generate_months(date_debut_str: str, nb_mois: int) -> list:
    from datetime import datetime, date
    try:
        d = datetime.strptime(date_debut_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        d = date.today()
    out = []
    yr, mo = d.year, d.month
    for _ in range(nb_mois):
        out.append(f"{mo:02d}/{yr}")
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1
    return out


def render_public(db, token: str) -> None:
    """Render the public read-only daret view. db is a DatabaseManager instance."""
    inject_css()

    daret = db.get_daret_by_token(token) if token else None

    # ── Invalid token ───────────────────────────────────────────────────────
    if not daret:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:32px 18px;text-align:center;'
            f'max-width:520px;margin:60px auto">'
            f'  <div style="font-size:36px;margin-bottom:8px">🔗</div>'
            f'  <div style="color:{T.TEXT_HIGH};font-size:16px;font-weight:600;margin-bottom:6px">'
            f"    Lien d'invitation invalide ou expiré</div>"
            f'  <div style="color:{T.TEXT_LOW};font-size:13px">'
            f"    Demande au gestionnaire du daret de te renvoyer un lien à jour."
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    nom         = daret.get("Nom") or "Daret"
    montant     = float(daret.get("Montant_Mensuel", 0) or 0)
    nb          = int(daret.get("Nb_Membres", 0) or 0)
    date_debut  = (daret.get("Date_Debut") or "")[:10]
    cagnotte    = montant * nb
    notes       = daret.get("Notes") or ""

    try:
        membres = json.loads(daret.get("Membres_JSON") or "[]")
    except (json.JSONDecodeError, TypeError):
        membres = []

    months  = _generate_months(date_debut, len(membres) or 1)

    try:
        statuts = db.get_daret_statuts(daret.get("id"))
    except Exception:
        statuts = {}

    # ── Header ──────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="background:linear-gradient(135deg,{T.PRIMARY}22,{T.PURPLE}11);'
        f'border:1px solid {T.PRIMARY}40;border-radius:{T.RADIUS_LG};'
        f'padding:24px 28px;margin-bottom:18px">'
        f'  <div style="color:{T.PRIMARY};font-size:11px;font-weight:700;'
        f'    text-transform:uppercase;letter-spacing:1.5px">🔄 Daret partagé · vue invité</div>'
        f'  <div style="color:{T.TEXT_HIGH};font-size:24px;font-weight:800;margin:6px 0 4px">'
        f'    {nom}</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px">'
        f'    {len(membres)} membres · {_dh(montant)} DH/mois · début {date_debut}'
        f'  </div>'
        f'  <div style="display:flex;gap:24px;margin-top:14px;flex-wrap:wrap">'
        f'    <div>'
        f'      <div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'        text-transform:uppercase;letter-spacing:1px">Cagnotte mensuelle</div>'
        f'      <div style="color:{T.SUCCESS};font-size:20px;font-weight:900;margin-top:2px">'
        f'        {_dh(cagnotte)} DH</div>'
        f'    </div>'
        f'    <div>'
        f'      <div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'        text-transform:uppercase;letter-spacing:1px">Cotisation par membre</div>'
        f'      <div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:900;margin-top:2px">'
        f'        {_dh(montant)} DH</div>'
        f'    </div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if notes:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-left:3px solid {T.PRIMARY};border-radius:{T.RADIUS_MD};'
            f'padding:10px 14px;margin-bottom:18px;color:{T.TEXT_MED};font-size:12px;'
            f'font-style:italic">{notes}</div>',
            unsafe_allow_html=True,
        )

    # ── Bloomberg table (read-only) ─────────────────────────────────────────
    if not membres:
        st.info("Aucun membre dans ce daret.")
        return

    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1.2px;margin-bottom:8px">'
        f'📊 Tableau de paiements'
        f'  <span style="color:{T.TEXT_MED};font-weight:400;text-transform:none;'
        f'    margin-left:8px">🟢 payé · 🟡 déclaré · 🔴 en attente</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Header row
    h_cols = st.columns([2] + [1] * len(months))
    with h_cols[0]:
        st.markdown(
            f'<div style="color:{T.TEXT_MED};font-size:11px;font-weight:600;padding:6px 0">'
            f'Membre</div>',
            unsafe_allow_html=True,
        )
    for i, m in enumerate(months):
        with h_cols[i + 1]:
            st.markdown(
                f'<div style="text-align:center;color:{T.TEXT_MED};font-size:10px;'
                f'font-weight:600;padding:6px 0">{m}</div>',
                unsafe_allow_html=True,
            )

    # Member rows
    for membre in membres:
        cols = st.columns([2] + [1] * len(months))
        with cols[0]:
            st.markdown(
                f'<div style="color:{T.TEXT_HIGH};font-size:13px;padding:10px 0">'
                f'{membre}</div>',
                unsafe_allow_html=True,
            )
        for i, mois in enumerate(months):
            current = statuts.get(mois, {}).get(membre)
            emoji   = _STATUS_EMOJI.get(current, "🔴")
            with cols[i + 1]:
                st.markdown(
                    f'<div style="text-align:center;font-size:18px;padding:8px 0"'
                    f' title="{membre} · {mois} : {_STATUS_LABEL.get(current)}">'
                    f'{emoji}</div>',
                    unsafe_allow_html=True,
                )

    # ── Footer ──────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="margin-top:30px;padding-top:18px;border-top:1px solid {T.BORDER};'
        f'color:{T.TEXT_LOW};font-size:11px;text-align:center">'
        f"Vue partagée · seul le gestionnaire peut modifier les statuts."
        f"<br>Powered by <b style='color:{T.PRIMARY}'>Finance SaaS</b>"
        f'</div>',
        unsafe_allow_html=True,
    )
