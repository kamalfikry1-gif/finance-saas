"""
views/daret.py — Daret / Jam'iya Tracker.

Le Daret est une tontine marocaine : un groupe de personnes verse un montant
fixe chaque mois et à tour de rôle l'un d'eux reçoit toute la cagnotte.

Fonctionnalités :
    · Créer un daret (nom, montant, membres, date de début)
    · Voir qui reçoit la cagnotte ce mois
    · Avancer le tour
    · Voir la progression et le total épargné
    · Clôturer un daret terminé
"""

import json
from datetime import date, datetime
import streamlit as st
from components.design_tokens import T
from components.helpers import dh as _dh
from core.cache import get_darets as _get_darets


def render(ctx: dict) -> None:
    audit = ctx["audit"]

    st.markdown(
        f'<h2 style="color:{T.TEXT_HIGH};font-weight:900;'
        f'font-size:24px;margin-bottom:4px">🔄 Daret & Tontine</h2>'
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:20px">'
        f'Gérez vos cercles d\'épargne communautaire — qui reçoit la cagnotte ce mois ?</p>',
        unsafe_allow_html=True,
    )

    try:
        darets = _get_darets(audit, audit.user_id)
    except Exception:
        st.warning("Impossible de charger les darets — réessayez dans quelques secondes.")
        return

    # ── Formulaire création ───────────────────────────────────────────────────
    with st.expander("➕ Nouveau Daret", expanded=(not darets)):
        _render_form_creation(audit)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if not darets:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:40px;text-align:center;margin-top:12px">'
            f'<div style="font-size:36px;margin-bottom:10px">🤝</div>'
            f'<div style="color:{T.TEXT_MED};font-size:14px;margin-bottom:6px">'
            f'Aucun daret actif.</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:12px">'
            f'Créez votre premier daret pour suivre votre tontine.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Liste des darets actifs ───────────────────────────────────────────────
    for d in darets:
        _render_daret_card(audit, d)


def _render_form_creation(audit) -> None:
    c1, c2 = st.columns(2)
    with c1:
        nom = st.text_input("Nom du daret", placeholder="ex: Daret Famille, Daret Bureau…",
                            key="dr_nom")
    with c2:
        montant = st.number_input("Cotisation mensuelle (DH)", min_value=1.0,
                                  step=100.0, format="%.0f",
                                  value=None, placeholder="0",
                                  key="dr_montant")

    membres_raw = st.text_input(
        "Membres (séparés par des virgules)",
        placeholder="ex: Toi, Karim, Fatima, Ahmed, Sara",
        key="dr_membres",
    )
    membres = [m.strip() for m in membres_raw.split(",") if m.strip()] if membres_raw else []

    c3, c4 = st.columns(2)
    with c3:
        date_debut = st.date_input("Date de début", value=date.today(), key="dr_date")
    with c4:
        notes = st.text_input("Notes (optionnel)", placeholder="ex: ordre de passage…",
                              key="dr_notes")

    if membres:
        st.markdown(
            f'<div style="background:{T.BG_CARD_ALT};border-radius:{T.RADIUS_SM};'
            f'padding:8px 12px;font-size:12px;color:{T.TEXT_MED};margin-top:4px">'
            f'<b>{len(membres)} membre(s)</b> · Cagnotte mensuelle : '
            f'<b style="color:{T.PRIMARY}">{_dh((montant or 0) * len(membres))}</b>'
            f' DH</div>',
            unsafe_allow_html=True,
        )

    if st.button("Créer le daret", key="dr_save", type="primary"):
        if not nom.strip():
            st.warning("Nom requis.")
        elif not montant or montant <= 0:
            st.warning("Cotisation > 0 DH requise.")
        elif len(membres) < 2:
            st.warning("Au moins 2 membres requis.")
        else:
            audit.creer_daret(
                nom=nom.strip(),
                montant_mensuel=float(montant),
                membres=membres,
                date_debut=str(date_debut),
                notes=notes.strip(),
            )
            st.success(f"✅ Daret « {nom.strip()} » créé avec {len(membres)} membres.")
            st.rerun()


def _render_daret_card(audit, d: dict) -> None:
    nom         = d.get("Nom", "—")
    montant     = float(d.get("Montant_Mensuel", 0))
    nb          = int(d.get("Nb_Membres", 1)) or 1
    tour        = int(d.get("Tour_Actuel", 0))
    date_debut  = d.get("Date_Debut", "")[:10]
    notes       = d.get("Notes", "") or ""
    daret_id    = d.get("id")

    try:
        membres = json.loads(d.get("Membres_JSON", "[]"))
    except (json.JSONDecodeError, TypeError):
        membres = []

    if not membres:
        membres = [f"Membre {i+1}" for i in range(nb)]

    tour_idx   = tour % len(membres)
    beneficiaire = membres[tour_idx]
    cagnotte   = montant * nb
    total_verse = montant * tour        # what the group has paid in total so far
    tours_rest = len(membres) - tour_idx - 1

    # Progress through the cycle
    pct = (tour_idx / len(membres)) * 100

    # Is it my turn?
    mon_nom    = membres[0]  # convention: first member = "toi"
    mon_tour   = (tour_idx == 0)

    couleur = T.SUCCESS if mon_tour else T.PRIMARY

    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-left:3px solid {couleur};border-radius:{T.RADIUS_LG};'
        f'padding:20px;margin-bottom:14px">',
        unsafe_allow_html=True,
    )

    # Header
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown(
            f'<div style="color:{T.TEXT_HIGH};font-weight:800;font-size:16px">'
            f'🔄 {nom}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
            f'{nb} membres · {_dh(montant)} DH/mois · début {date_debut}</div>',
            unsafe_allow_html=True,
        )
    with h2:
        st.markdown(
            f'<div style="text-align:right">'
            f'<div style="color:{couleur};font-weight:900;font-size:20px">{_dh(cagnotte)}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:10px">cagnotte du mois</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Beneficiary this month
    badge_color = T.SUCCESS if mon_tour else T.WARNING
    badge_text  = "🎉 C'est TON tour !" if mon_tour else f"👤 Ce mois : {beneficiaire}"
    st.markdown(
        f'<div style="background:{badge_color}18;border:1px solid {badge_color}40;'
        f'border-radius:{T.RADIUS_MD};padding:10px 14px;margin:12px 0;'
        f'color:{badge_color};font-weight:700;font-size:13px">{badge_text}</div>',
        unsafe_allow_html=True,
    )

    # Progress bar through cycle
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;'
        f'color:{T.TEXT_LOW};font-size:10px;margin-bottom:4px">'
        f'<span>Tour {tour_idx + 1} / {len(membres)}</span>'
        f'<span>{tours_rest} tour(s) restant(s)</span>'
        f'</div>'
        f'<div style="background:{T.BORDER};border-radius:{T.RADIUS_PILL};'
        f'height:6px;overflow:hidden;margin-bottom:12px">'
        f'<div style="width:{pct:.1f}%;height:6px;background:{couleur};'
        f'border-radius:{T.RADIUS_PILL}"></div></div>',
        unsafe_allow_html=True,
    )

    # Members list
    pills_html = ""
    for i, m in enumerate(membres):
        idx = i
        is_done    = (idx < tour_idx)
        is_current = (idx == tour_idx)
        bg    = T.SUCCESS    if is_done    else (T.PRIMARY if is_current else T.BG_CARD_ALT)
        col   = T.TEXT_HIGH  if is_current else (T.TEXT_MED if not is_done else T.TEXT_LOW)
        check = "✓ " if is_done else ("▶ " if is_current else "")
        pills_html += (
            f'<span style="background:{bg}22;color:{col};'
            f'font-size:11px;padding:3px 9px;border-radius:{T.RADIUS_PILL};'
            f'margin:2px;border:1px solid {bg}44;display:inline-block">'
            f'{check}{m}</span>'
        )

    st.markdown(
        f'<div style="margin-bottom:12px">{pills_html}</div>',
        unsafe_allow_html=True,
    )

    if notes:
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:11px;font-style:italic;'
            f'margin-bottom:10px">{notes}</div>',
            unsafe_allow_html=True,
        )

    # ── Intelligence ──────────────────────────────────────────────────────────
    if mon_tour:
        st.markdown(
            f'<div style="background:{T.SUCCESS}15;border:1px solid {T.SUCCESS}40;'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-bottom:10px;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="color:{T.SUCCESS};font-weight:700;font-size:13px">'
            f'🎉 C\'est ton tour — tu reçois la cagnotte !</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
            f'Pense à le placer sur un objectif ou en épargne.</div>'
            f'</div>'
            f'<div style="color:{T.SUCCESS};font-size:22px;font-weight:900">'
            f'{_dh(cagnotte)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("🎯 Placer en objectif", key=f"dr_obj_now_{daret_id}",
                     use_container_width=True, type="secondary"):
            date_cible = date.today().replace(day=28).isoformat()
            audit.creer_objectif_v2(
                nom=f"Cagnotte Daret — {nom}",
                type_obj="EPARGNE",
                montant_cible=cagnotte,
                date_cible=date_cible,
            )
            st.success(f"✅ Objectif créé — {_dh(cagnotte)}")
    else:
        tours_until_mine = len(membres) - tour_idx
        monthly_needed   = round(cagnotte / tours_until_mine) if tours_until_mine > 0 else 0
        st.markdown(
            f'<div style="background:{T.PRIMARY}10;border:1px solid {T.PRIMARY}30;'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-bottom:10px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="color:{T.PRIMARY};font-weight:700;font-size:13px">'
            f'⏳ Ton tour dans {tours_until_mine} mois</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
            f'Mets de côté <b style="color:{T.TEXT_HIGH}">{_dh(monthly_needed)}/mois</b> '
            f'pour être prêt à recevoir la cagnotte.</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div style="color:{T.TEXT_HIGH};font-size:18px;font-weight:900">'
            f'{_dh(cagnotte)}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:10px">à recevoir</div>'
            f'</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("🎯 Créer objectif Daret", key=f"dr_obj_{daret_id}",
                     use_container_width=True, type="secondary"):
            from datetime import date as _date
            from dateutil.relativedelta import relativedelta
            date_cible = (_date.today() + relativedelta(months=tours_until_mine)).isoformat()
            audit.creer_objectif_v2(
                nom=f"Daret — {nom} (dans {tours_until_mine} mois)",
                type_obj="EPARGNE",
                montant_cible=cagnotte,
                date_cible=date_cible,
            )
            from core.cache import invalider as _inv
            _inv()
            st.success(f"✅ Objectif créé — {_dh(cagnotte)} dans {tours_until_mine} mois")

    # Actions
    confirm_next  = st.session_state.get(f"dr_confirm_next_{daret_id}", False)
    confirm_close = st.session_state.get(f"dr_confirm_close_{daret_id}", False)

    if confirm_next:
        st.warning(f"Passer au tour suivant ? **{beneficiaire}** ne sera plus bénéficiaire.")
        ca, cb, _ = st.columns([1, 1, 3])
        with ca:
            if st.button("✅ Confirmer", key=f"dr_next_ok_{daret_id}",
                         use_container_width=True, type="primary"):
                audit.avancer_tour_daret(daret_id)
                st.session_state[f"dr_confirm_next_{daret_id}"] = False
                st.rerun()
        with cb:
            if st.button("❌ Annuler", key=f"dr_next_no_{daret_id}", use_container_width=True):
                st.session_state[f"dr_confirm_next_{daret_id}"] = False
                st.rerun()
    elif confirm_close:
        st.warning(f"Clôturer le daret **{nom}** ? Cette action est irréversible.")
        ca, cb, _ = st.columns([1, 1, 3])
        with ca:
            if st.button("✅ Clôturer", key=f"dr_close_ok_{daret_id}",
                         use_container_width=True, type="primary"):
                audit.cloturer_daret(daret_id)
                st.session_state[f"dr_confirm_close_{daret_id}"] = False
                st.rerun()
        with cb:
            if st.button("❌ Annuler", key=f"dr_close_no_{daret_id}", use_container_width=True):
                st.session_state[f"dr_confirm_close_{daret_id}"] = False
                st.rerun()
    else:
        ba, bb, _ = st.columns([1, 1, 3])
        with ba:
            if st.button("▶ Tour suivant", key=f"dr_next_{daret_id}",
                         use_container_width=True, type="primary"):
                st.session_state[f"dr_confirm_next_{daret_id}"] = True
                st.rerun()
        with bb:
            if st.button("Clôturer", key=f"dr_close_{daret_id}",
                         use_container_width=True, type="secondary"):
                st.session_state[f"dr_confirm_close_{daret_id}"] = True
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
