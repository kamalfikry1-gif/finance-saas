"""
views/accueil.py — Page Accueil du Dashboard.

Layout : port of the "Calme" design variation (2026-04-18 design handoff).
Sections, top to bottom :
    1. Hero solde net              (big 84px amount + épargne pill + flow summary)
    2. 4 KPIs                      (Revenus, Dépenses, Reste à vivre, Épargne cumulée)
    3. Body : categories list      (left) + Coach + Score + Plan + Goals (right)
    4. Donut dépenses              (bas de page)

All CSS classes live in components/styles.py (the `v1-*`, `cat-*`, `coach-*-v1`,
`gauge-*`, `plan-row-v1`, `goal-*-v1` blocks). This file only emits structure.
"""

from __future__ import annotations

import math

import streamlit as st
import pandas as pd
import plotly.express as px

from config import SCORE_SEUIL_ORANGE, HUMEUR_COOL, HUMEUR_NEUTRE, HUMEUR_SERIEUX
from components.cards import CAT_COLORS, alerte_box
from components.design_tokens import T
from components.helpers import dh as _dh
from core import cache as ui_cache
from core.cache import invalider as _invalider_cache


# Plan 50/30/20 display colours (match the Calme design)
_PLAN_COLORS = {
    "Needs":   "#4FD1C5",  # maps to "Besoins"
    "Wants":   "#8E8CFF",  # maps to "Envies"
    "Savings": "#F5B947",  # maps to "Épargne"
}
_PLAN_LABELS = {"Needs": "Besoins", "Wants": "Envies", "Savings": "Épargne"}

# Accent colour per KPI slot
_KPI_ACCENT_CLASSES = ["success", "warn", "", "violet"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_dh(n: float) -> str:
    """French-style thousand-separated DH amount (no currency suffix)."""
    return f"{abs(n):,.0f}".replace(",", " ")


def _score_color(score_val: float) -> str:
    if score_val >= 75:
        return T.SUCCESS
    if score_val >= SCORE_SEUIL_ORANGE:
        return T.WARNING
    return T.DANGER


def _mood_class(humeur: str) -> str:
    if humeur == HUMEUR_COOL:
        return "cool"
    if humeur == HUMEUR_SERIEUX:
        return "serieux"
    return "neutre"


def _gauge_svg(score_val: float, color: str) -> str:
    """Render a 270° arc gauge as inline SVG."""
    size, stroke = 140, 10
    r = (size - stroke) / 2
    c = 2 * math.pi * r
    arc = c * 0.75  # 270° sweep
    anim = max(0.0, min(1.0, score_val / 100))
    return (
        f'<svg width="{size}" height="{int(size * 0.78)}" '
        f'viewBox="0 0 {size} {int(size * 0.85)}" '
        f'style="transform:rotate(135deg);transform-origin:center;margin-top:8px">'
        f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" '
        f'stroke="{T.BG_INPUT}" stroke-width="{stroke}" '
        f'stroke-dasharray="{arc} {c}" stroke-linecap="round"/>'
        f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" '
        f'stroke-dasharray="{arc * anim} {c}" stroke-linecap="round"/>'
        f'</svg>'
    )


# ── Sections ──────────────────────────────────────────────────────────────────

def _render_streak_banner(streak_jours: int, mois_verts: int, username: str) -> None:
    """One-line motivational banner — only visible when there's something to show."""
    parts = []
    if streak_jours >= 2:
        parts.append(f"🔥 {streak_jours} jours de suite")
    elif streak_jours == 1:
        parts.append("🔥 1er jour — bonne reprise !")
    if mois_verts >= 2:
        parts.append(f"✅ {mois_verts} mois verts consécutifs")
    elif mois_verts == 1:
        parts.append("✅ 1er mois vert")

    if not parts:
        return

    nom = (username or "").capitalize()
    suffix = (
        f" — Continue comme ça{', ' + nom if nom else ''} !"
        if (streak_jours >= 5 or mois_verts >= 3)
        else ""
    )
    text = " · ".join(parts)
    st.markdown(
        f'<div style="background:{T.SUCCESS}12;border-left:3px solid {T.SUCCESS};'
        f'border-radius:{T.RADIUS_MD};padding:9px 14px;margin-bottom:10px;'
        f'display:flex;align-items:center;gap:10px">'
        f'<span style="color:{T.SUCCESS};font-size:13px;font-weight:700">{text}</span>'
        f'<span style="color:{T.TEXT_LOW};font-size:12px">{suffix}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_charges_fixes(audit) -> None:
    """Recurring fixed charges card — surfaces the hidden get_charges_fixes() intelligence."""
    try:
        res = audit.query("charges_fixes", nb_mois_min=2)
        charges = res.get("resultat", [])
    except Exception:
        return

    if not charges:
        return

    total_mensuel = sum(float(c.get("Montant_Moyen", 0)) for c in charges)
    nb = len(charges)

    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:14px 16px;margin-top:14px">'
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">'
        f'📌 Charges fixes détectées</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'margin-bottom:10px">'
        f'<span style="color:{T.TEXT_MED};font-size:12px">'
        f'{nb} charge{"s" if nb > 1 else ""} récurrente{"s" if nb > 1 else ""}</span>'
        f'<span style="color:{T.TEXT_HIGH};font-size:15px;font-weight:700">'
        f'{_dh(total_mensuel)}/mois</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    for c in charges[:5]:
        lib  = (c.get("Libelle") or "")[:28]
        mnt  = float(c.get("Montant_Moyen", 0))
        nb_m = int(c.get("Nb_Mois", 0))
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:4px 0;border-bottom:1px solid {T.BORDER}">'
            f'<span style="color:{T.TEXT_MED};font-size:12px">{lib}</span>'
            f'<span style="display:flex;gap:10px;align-items:center">'
            f'<span style="color:{T.TEXT_HIGH};font-size:12px;font-weight:600">{_dh(mnt)}</span>'
            f'<span style="color:{T.TEXT_LOW};font-size:10px">{nb_m}×</span>'
            f'</span></div>',
            unsafe_allow_html=True,
        )
    if len(charges) > 5:
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:11px;text-align:right;padding-top:4px">'
            f'+{len(charges) - 5} autres</div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_quick_transaction(audit) -> None:
    """Collapsed quick-entry form on the dashboard — minimal 3 fields."""
    from datetime import date as _date

    if "dash_sens" not in st.session_state:
        st.session_state.dash_sens = "OUT"
    if "dash_ctr" not in st.session_state:
        st.session_state.dash_ctr = 0
    if "dash_confirmer" not in st.session_state:
        st.session_state.dash_confirmer = None

    with st.expander("➕ Nouvelle transaction", expanded=False):
        _k = st.session_state.dash_ctr
        d1, d2 = st.columns([3, 1])
        with d1:
            libelle = st.text_input(
                "Libellé", placeholder="ex: CARREFOUR, Loyer…",
                key=f"dash_lib_{_k}", label_visibility="collapsed",
            )
        with d2:
            montant_str = st.text_input(
                "Montant", placeholder="0.00",
                key=f"dash_mnt_{_k}", label_visibility="collapsed",
            )

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button(
                "💸 Dépense", use_container_width=True,
                type="primary" if st.session_state.dash_sens == "OUT" else "secondary",
                key="dash_btn_dep",
            ):
                st.session_state.dash_sens = "OUT"
                st.rerun()
        with c2:
            if st.button(
                "💰 Revenu", use_container_width=True,
                type="primary" if st.session_state.dash_sens == "IN" else "secondary",
                key="dash_btn_rev",
            ):
                st.session_state.dash_sens = "IN"
                st.rerun()
        with c3:
            dv = st.date_input(
                "Date", value=_date.today(),
                label_visibility="collapsed",
                key=f"dash_date_{_k}",
            )

        # ── Tags & Contact (optionnel, caché) ─────────────────────────────────
        with st.expander("🏷️ Tags & Contact", expanded=False):
            dash_tags = st.text_input(
                "Tags", placeholder="hanout, famille, boulot…",
                key=f"dash_tags_{_k}", label_visibility="collapsed",
            )
            dash_contact = st.text_input(
                "Contact", placeholder="ex: Karim, Hanout Derb Omar…",
                key=f"dash_contact_{_k}", label_visibility="collapsed",
            )

        if st.session_state.dash_confirmer:
            p = st.session_state.dash_confirmer
            if st.button("Confirmer quand même", key="dash_btn_forcer", type="secondary",
                         use_container_width=True):
                res2 = audit.recevoir(p["libelle"], p["montant"], p["sens"], p["dv"], forcer=True)
                if res2.get("action") == "OK":
                    tx_id = res2.get("id_unique")
                    if tx_id and (p.get("tags", "").strip() or p.get("contact", "").strip()):
                        audit.update_tags_contact(tx_id, p.get("tags", ""), p.get("contact", ""))
                    st.success(f"✅ **{res2.get('categorie')}** · {res2.get('sous_categorie')}")
                    st.session_state.dash_confirmer = None
                    st.session_state.dash_ctr += 1
                    _invalider_cache()
                    st.rerun()

        if st.button("Enregistrer ↵", use_container_width=True,
                     type="primary", key="dash_btn_enreg"):
            try:
                montant = float(montant_str.replace(",", ".").replace(" ", "")) if montant_str.strip() else 0.0
            except ValueError:
                montant = 0.0

            if not libelle.strip():
                st.warning("Libellé requis.")
            elif montant <= 0:
                st.warning("Montant > 0 requis.")
            else:
                with st.spinner("Traitement…"):
                    res = audit.recevoir(libelle.strip(), montant,
                                         st.session_state.dash_sens, dv)
                action = res.get("action")
                if action == "OK":
                    tx_id = res.get("id_unique")
                    if tx_id and (dash_tags.strip() or dash_contact.strip()):
                        audit.update_tags_contact(tx_id, dash_tags, dash_contact)
                    st.success(
                        f"✅ **{res.get('categorie')}** · {res.get('sous_categorie')}"
                    )
                    st.session_state.dash_ctr += 1
                    _invalider_cache()
                    st.rerun()
                elif action == "CONFIRMER":
                    st.session_state.dash_confirmer = {
                        "libelle": libelle.strip(), "montant": montant,
                        "sens": st.session_state.dash_sens, "dv": dv,
                        "tags": dash_tags, "contact": dash_contact,
                    }
                    st.warning(f"⚠️ {res.get('message', '')}")
                elif action == "BLOQUER":
                    st.session_state.dash_confirmer = None
                    st.error(f"🚫 {res.get('message', 'Doublon détecté')}")
                else:
                    st.error(res.get("erreur", "Erreur inconnue"))


def _render_hero(bilan: dict, proj: dict, score: dict, mois_lbl: str) -> None:
    solde  = bilan["solde"]
    sign   = "+" if solde >= 0 else "−"
    sclass = "pos" if solde >= 0 else "neg"
    proj_v = proj.get("projection_fin_mois", 0) or 0
    taux_ep = float(score.get("taux_epargne_pct", 0) or 0)

    st.markdown(
        f'<div class="v1-hero">'
        f'  <div class="v1-hero-label">{mois_lbl} · Solde net</div>'
        f'  <div class="v1-hero-amount">'
        f'    <span class="sign {sclass}">{sign}</span>{_fmt_dh(solde)}'
        f'    <span class="unit">DH</span>'
        f'  </div>'
        f'  <div class="v1-hero-sub">'
        f'    <span class="v1-hero-pill">↑ {taux_ep:.1f}% épargne</span>'
        f'    <span>Projection fin de mois <span class="hv warn">{_fmt_dh(proj_v)} DH</span></span>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_kpis(bilan: dict, proj: dict) -> None:
    revenus = bilan["revenus"]
    depenses = bilan["depenses"]
    epargne_cumul = bilan["epargne_cumul"]
    proj_v = proj.get("projection_fin_mois", 0) or 0
    jours_rest = max(
        0,
        int(proj.get("jours_total", 0) or 0) - int(proj.get("jours_ecoules", 0) or 0),
    )
    reste_a_vivre = max(0.0, revenus - max(depenses, proj_v))
    epargne_mois = max(0.0, revenus - depenses)

    def _card(accent_cls: str, label: str, value_dh: float, delta_html: str) -> str:
        return (
            f'<div class="v1-kpi">'
            f'  <div class="v1-kpi-accent {accent_cls}"></div>'
            f'  <div class="lbl">{label}</div>'
            f'  <div class="val">{_fmt_dh(value_dh)}<span class="u"> DH</span></div>'
            f'  <div class="delta">{delta_html}</div>'
            f'</div>'
        )

    je         = int(proj.get("jours_ecoules", 0) or 0)
    jours_total = int(proj.get("jours_total", 30) or 30)

    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        st.markdown(
            _card("success", "Revenus du mois", revenus,
                  f'<span class="up">Total encaissé ce mois</span>'),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            _card("warn", "Dépenses", depenses,
                  f'<span class="warn">Dépensé sur {je}j — {jours_rest}j restants</span>'),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            _card("", "Reste à vivre", reste_a_vivre,
                  f'Projection fin de mois : {_fmt_dh(proj_v)} DH dépensé'),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            _card("violet", "Épargne cumulée", epargne_cumul,
                  f'<span class="up">+{_fmt_dh(epargne_mois)} DH ce mois</span>'),
            unsafe_allow_html=True,
        )


def _render_categories(rept: list, ctx: dict) -> None:
    st.markdown(
        '<div class="v1-sec-head">Dépenses par catégorie</div>',
        unsafe_allow_html=True,
    )
    if not rept:
        st.info("Aucune dépense ce mois.")
        return

    res_sous  = ctx["_q"]("detail_sous_categories", mois=ctx["mois_sel"])
    sous_data = res_sous.get("resultat", []) if "resultat" in res_sous else []
    sous_par_cat: dict = {}
    for sc in sous_data:
        sous_par_cat.setdefault(sc["Categorie"], []).append(sc)

    for i, row in enumerate(rept):
        cat     = row["Categorie"] or "Non classé"
        couleur = CAT_COLORS[i % len(CAT_COLORS)]
        total   = float(row.get("Total_DH") or 0)
        poids   = float(row.get("Poids_Pct") or 0)
        bar_w   = min(poids, 100)
        sous    = sous_par_cat.get(cat, [])

        # Head row (always visible)
        head = (
            f'<div class="cat-row-head">'
            f'  <span class="cat-swatch" style="background:{couleur}"></span>'
            f'  <span class="cat-name">{cat}</span>'
            f'  <span class="cat-amt">{_fmt_dh(total)} DH</span>'
            f'  <span class="cat-pct">{poids:.1f}%</span>'
            f'</div>'
            f'<div class="cat-bar">'
            f'  <div class="cat-bar-fill" '
            f'       style="width:{bar_w:.1f}%;background:{couleur}"></div>'
            f'</div>'
        )

        with st.expander(f"**{cat}** · {_fmt_dh(total)} DH · {poids:.1f}%", expanded=False):
            st.markdown(head, unsafe_allow_html=True)
            if not sous:
                st.markdown(
                    f'<div style="color:{T.TEXT_LOW};font-size:12px;padding:4px 0">'
                    f'Aucun détail disponible.</div>',
                    unsafe_allow_html=True,
                )
                continue
            total_cat = total or 1
            for sc in sous:
                sc_total = float(sc.get("Total_DH") or 0)
                sc_pct   = sc_total / total_cat * 100
                sc_bar   = min(sc_pct, 100)
                st.markdown(
                    f'<div class="cat-sub-row">'
                    f'  <div class="n">{sc["Sous_Categorie"]}</div>'
                    f'  <div class="b"><div class="bf" '
                    f'       style="width:{sc_bar:.1f}%;background:{couleur}"></div></div>'
                    f'  <div class="a" style="color:{couleur}">{_fmt_dh(sc_total)} DH</div>'
                    f'  <div class="p">{sc_pct:.0f}%</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def _render_coach(message: str, humeur: str, identite: str) -> None:
    initials = (identite or "?")[:1].upper()
    st.markdown(
        f'<div class="coach-card-v1">'
        f'  <div class="coach-head-v1">'
        f'    <div class="coach-avatar-v1">{initials}</div>'
        f'    <div class="coach-meta-v1">'
        f'      <div class="name">Coach {identite}</div>'
        f'      <div class="role">Assistant financier</div>'
        f'    </div>'
        f'    <span class="mood-pill-v1 {_mood_class(humeur)}">{humeur}</span>'
        f'  </div>'
        f'  <div class="coach-quote-v1">{message}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_score_plan(score: dict, badges: dict) -> None:
    score_val = float(score.get("score", 0) or 0)
    color     = _score_color(score_val)
    level     = score.get("niveau", "")
    niveau_fr = {"EXCELLENT": "Excellent", "BON": "Bon", "MOYEN": "Moyen", "CRITIQUE": "Critique"}.get(level, level)

    st.markdown(
        f'<div class="gauge-card" style="margin-top:14px">'
        f'  <div class="gauge-title">Score Santé Financière</div>'
        f'  <div class="gauge-wrap">'
        f'    {_gauge_svg(score_val, color)}'
        f'    <div class="gauge-text">'
        f'      <div class="gauge-num" style="color:{color}">{score_val:.0f}</div>'
        f'      <div class="gauge-total">sur 100</div>'
        f'      <div class="gauge-label" style="color:{color}">{niveau_fr}</div>'
        f'    </div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_daret_teaser(audit, user_id: int) -> None:
    """Compact Daret intelligence card — shows nearest upcoming turn."""
    import json
    try:
        from core.cache import get_darets as _get_darets
        darets = _get_darets(audit, user_id)
    except Exception:
        return

    best = None  # closest upcoming turn
    for d in darets:
        try:
            membres = json.loads(d.get("Membres_JSON", "[]") or "[]")
        except Exception:
            membres = []
        if not membres:
            continue
        nb       = len(membres)
        tour_idx = int(d.get("Tour_Actuel", 0)) % nb
        mon_tour = (tour_idx == 0)
        if mon_tour:
            continue  # already surfaced on the daret card
        tours_until = nb - tour_idx
        cagnotte    = float(d.get("Montant_Mensuel", 0)) * nb
        if best is None or tours_until < best["tours"]:
            best = {
                "nom": d.get("Nom", "Daret"),
                "tours": tours_until,
                "cagnotte": cagnotte,
                "monthly": round(cagnotte / tours_until) if tours_until else 0,
            }

    if best is None:
        return

    st.markdown(
        f'<div style="background:{T.PRIMARY}08;border:1px solid {T.PRIMARY}25;'
        f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-top:14px;'
        f'display:flex;justify-content:space-between;align-items:center">'
        f'<div>'
        f'<div style="color:{T.PRIMARY};font-size:11px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1px">🔄 {best["nom"]}</div>'
        f'<div style="color:{T.TEXT_LOW};font-size:12px;margin-top:2px">'
        f'Ton tour dans <b style="color:{T.TEXT_HIGH}">{best["tours"]} mois</b> '
        f'— mets de côté <b style="color:{T.TEXT_HIGH}">{_dh(best["monthly"])}/mois</b>'
        f'</div>'
        f'</div>'
        f'<div style="color:{T.TEXT_HIGH};font-size:16px;font-weight:900">'
        f'{_dh(best["cagnotte"])}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_rappels(audit, user_id: int, mois_sel: str) -> None:
    """Rappels épargne + objectif — cartes cliquables si données manquantes."""
    db = audit.db

    # ── Rappel épargne du mois ────────────────────────────────────────────────
    try:
        ep = db.get_epargne_mois(user_id, mois_sel)
    except Exception:
        ep = None
    if ep is None:
        st.markdown(
            f'<div style="background:{T.WARNING}10;border:1px solid {T.WARNING}30;'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-top:14px;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="color:{T.WARNING};font-size:11px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1px">💰 Épargne du mois</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:12px;margin-top:2px">'
            f'Non renseignée pour ce mois</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Renseigner →", key="rappel_ep_btn", type="secondary"):
            st.session_state._rappel_ep_open = True
        st.markdown("</div>", unsafe_allow_html=True)

        if st.session_state.get("_rappel_ep_open"):
            with st.form("form_epargne_rappel", clear_on_submit=True):
                st.markdown(
                    f'<div style="color:{T.TEXT_HIGH};font-weight:700;'
                    f'margin-bottom:8px">Épargne réelle ce mois (DH)</div>',
                    unsafe_allow_html=True,
                )
                montant_ep = st.number_input(
                    "Montant épargné", min_value=0.0, step=100.0,
                    format="%.0f", label_visibility="collapsed",
                )
                submitted = st.form_submit_button("Enregistrer", type="primary",
                                                  use_container_width=True)
                if submitted:
                    db.sauvegarder_epargne_mois(user_id, mois_sel, float(montant_ep))
                    st.session_state._rappel_ep_open = False
                    st.success(f"✅ {montant_ep:,.0f} DH enregistrés.")
                    st.rerun()
    else:
        reel = float(ep.get("Montant_Reel", 0) or 0)
        st.markdown(
            f'<div style="background:{T.SUCCESS}10;border:1px solid {T.SUCCESS}30;'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-top:14px;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'<div style="color:{T.SUCCESS};font-size:11px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1px">💰 Épargne enregistrée</div>'
            f'<div style="color:{T.SUCCESS};font-size:16px;font-weight:900">'
            f'{_dh(reel)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Rappel objectif ───────────────────────────────────────────────────────
    try:
        from core import cache as ui_cache
        goals = ui_cache.get_objectifs(audit, user_id)
    except Exception:
        goals = []

    if not goals:
        st.markdown(
            f'<div style="background:{T.PRIMARY}08;border:1px solid {T.PRIMARY}25;'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-top:8px;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="color:{T.PRIMARY};font-size:11px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1px">🎯 Objectifs</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:12px;margin-top:2px">'
            f'Aucun objectif défini</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Créer →", key="rappel_obj_btn", type="secondary"):
            st.session_state.page = "Objectif"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def _render_goals(audit, user_id: int) -> None:
    try:
        goals = ui_cache.get_objectifs(audit, user_id)
    except Exception:
        goals = []

    st.markdown(
        '<div class="v1-sec-head" style="margin-top:18px">Objectifs d\'épargne</div>',
        unsafe_allow_html=True,
    )

    if not goals:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:16px;text-align:center;margin-bottom:6px">'
            f'<div style="color:{T.TEXT_LOW};font-size:12px">'
            f'Aucun objectif d\'épargne défini.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("🎯 Créer mon premier objectif →", key="acc_goal_cta",
                     use_container_width=True):
            st.session_state.page = "Objectif"
            st.rerun()
        return

    for g in goals[:2]:
        target = float(g.get("montant_cible") or g.get("Montant_Cible") or 0)
        current = float(g.get("montant_actuel") or g.get("Montant_Actuel") or 0)
        if target <= 0:
            continue
        pct  = min(100, round(current / target * 100))
        nom  = g.get("nom") or g.get("Nom") or "Objectif"
        dcib = g.get("date_cible") or g.get("Date_Cible") or ""
        st.markdown(
            f'<div class="goal-card-v1">'
            f'  <div class="goal-head-v1">'
            f'    <div class="goal-title-v1">{nom}</div>'
            f'    <div class="goal-date-v1">{dcib}</div>'
            f'  </div>'
            f'  <div class="goal-bar-v1">'
            f'    <div class="goal-bar-fill-v1" style="width:{pct}%"></div>'
            f'  </div>'
            f'  <div class="goal-foot-v1">'
            f'    <span><span class="cur">{_fmt_dh(current)}</span> / {_fmt_dh(target)} DH</span>'
            f'    <span>{pct}%</span>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if len(goals) > 2:
        if st.button(f"Voir les {len(goals)} objectifs →", key="acc_goal_all",
                     use_container_width=True):
            st.session_state.page = "Objectif"
            st.rerun()


def _render_radar(audit, proj: dict) -> None:
    """⚡ Radar — upcoming recurring bills in the next 7 days."""
    import calendar
    from datetime import date, timedelta

    today     = date.today()
    days_left = int(proj.get("jours_total", 30) or 30) - int(proj.get("jours_ecoules", 0) or 0)
    if days_left <= 0:
        return

    try:
        res = audit.query("radar_factures", nb_mois_min=2)
        charges = res.get("resultat", [])
    except Exception:
        return

    if not charges:
        return

    upcoming = []
    for c in charges:
        jour = c.get("Jour_Habituel")
        if jour is None:
            continue
        jour = int(round(float(jour)))
        # Days until next occurrence
        if jour >= today.day:
            delta = jour - today.day
        else:
            # Next month
            nm = today.month + 1 if today.month < 12 else 1
            ny = today.year if today.month < 12 else today.year + 1
            jour_clamp = min(jour, calendar.monthrange(ny, nm)[1])
            delta = (date(ny, nm, jour_clamp) - today).days

        if delta <= 7:
            upcoming.append({**c, "delta": delta})

    if not upcoming:
        return

    st.markdown(
        f'<div style="background:{T.WARNING}10;border:1px solid {T.WARNING}40;'
        f'border-radius:{T.RADIUS_MD};padding:14px 16px;margin-top:14px">'
        f'<div style="color:{T.WARNING};font-size:11px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">'
        f'⚡ Radar — Factures dans les 7 prochains jours</div>',
        unsafe_allow_html=True,
    )
    for item in upcoming:
        label  = item.get("Libelle", "")[:28]
        mnt    = float(item.get("Montant_Moyen", 0))
        delta  = item["delta"]
        urgence = T.DANGER if delta <= 2 else T.WARNING
        timing  = "demain" if delta == 1 else ("aujourd'hui" if delta == 0 else f"dans {delta}j")
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;padding:4px 0;border-bottom:1px solid {T.BORDER_MED}">'
            f'<span style="color:{T.TEXT_MED};font-size:12px">{label}</span>'
            f'<span style="display:flex;gap:12px;align-items:center">'
            f'<span style="color:{T.TEXT_HIGH};font-size:12px;font-weight:600">{_dh(mnt)}</span>'
            f'<span style="color:{urgence};font-size:11px;font-weight:700">{timing}</span>'
            f'</span></div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_age_of_money(audit, bilan: dict, proj: dict) -> None:
    """⏱ Age of Money — how long money sits before being spent."""
    solde = bilan.get("solde", 0)
    burn  = float(proj.get("taux_journalier", 0) or 0)
    age   = audit.age_of_money(solde, burn)

    if age is None:
        return

    if age >= 30:
        color, label = T.SUCCESS, "Excellent — tu vis sur le mois précédent"
    elif age >= 15:
        color, label = T.WARNING, "Bien — vise 30 jours pour plus de sérénité"
    else:
        color, label = T.DANGER, "Fragile — tu vis au jour le jour"

    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:14px 16px;margin-top:14px">'
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">⏱ Âge de ton argent</div>'
        f'<div style="display:flex;align-items:baseline;gap:6px">'
        f'<span style="color:{color};font-size:28px;font-weight:900">{age}</span>'
        f'<span style="color:{T.TEXT_LOW};font-size:13px">jours</span>'
        f'</div>'
        f'<div style="color:{color};font-size:11px;margin-top:4px">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_donut(rept: list) -> None:
    if not rept:
        return
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    df_r = pd.DataFrame(rept)
    fig  = px.pie(
        df_r, values="Total_DH", names="Categorie",
        hole=0.62,
        color_discrete_sequence=CAT_COLORS,
    )
    fig.update_traces(
        textposition="outside", textfont_size=11,
        hovertemplate="%{label}<br>%{value:,.0f} DH<br>%{percent}",
    )
    total_dep = df_r["Total_DH"].sum()
    fig.update_layout(
        showlegend=True,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=T.TEXT_MED, size=11)),
        paper_bgcolor=T.BG_PAGE, plot_bgcolor=T.BG_PAGE,
        font_color=T.TEXT_HIGH,
        margin=dict(t=20, b=20, l=0, r=0),
        height=280,
        annotations=[dict(
            text=f"<b>{_dh(total_dep)}</b><br>"
                 f"<span style='font-size:11px'>dépenses</span>",
            x=0.5, y=0.5, font_size=14,
            showarrow=False, font_color=T.TEXT_HIGH,
        )],
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def render(ctx: dict) -> None:
    bilan    = ctx["bilan"]
    mois_lbl = ctx["mois_lbl"]
    proj     = ctx["proj"]
    rept     = ctx["rept"]
    score    = ctx["score"]
    badges   = ctx["badges"]
    alertes  = ctx["alertes"]
    humeur   = ctx["humeur"]
    message  = ctx["message"]
    identite = ctx["identite_active"]
    audit    = ctx["audit"]
    streak_jours, mois_verts = ctx.get("streak", (0, 0))

    _render_streak_banner(streak_jours, mois_verts, ctx.get("username", ""))
    _render_quick_transaction(audit)
    _render_hero(bilan, proj, score, mois_lbl)
    _render_kpis(bilan, proj)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    col_cats, col_right = st.columns([3, 2], gap="large")
    with col_cats:
        _render_categories(rept, ctx)
    with col_right:
        _render_radar(audit, proj)
        _render_charges_fixes(audit)
        _render_coach(message, humeur, identite)
        if st.button("🤖 Parler au Coach →", key="coach_cta",
                     use_container_width=True):
            st.session_state.page = "Assistant"
            st.rerun()
        _render_score_plan(score, badges)
        _render_age_of_money(audit, bilan, proj)
        _render_daret_teaser(audit, ctx["user_id"])
        _render_goals(audit, ctx["user_id"])
        _render_rappels(audit, ctx["user_id"], ctx["mois_sel"])
        if alertes:
            st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
            for a in alertes[:3]:
                alerte_box(a["message"], a["couleur"])

    _render_donut(rept)
