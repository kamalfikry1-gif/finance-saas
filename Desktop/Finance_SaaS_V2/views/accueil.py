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
    """Legacy 3-level color (kept for any old callers)."""
    if score_val >= 75:
        return T.SUCCESS
    if score_val >= SCORE_SEUIL_ORANGE:
        return T.WARNING
    return T.DANGER


def _statut_color(statut: str) -> str:
    """5-level color from v2 statut (CRITIQUE/FAIBLE/MOYEN/BON/EXCELLENT)."""
    return {
        "EXCELLENT": T.SUCCESS,
        "BON":       T.PRIMARY,
        "MOYEN":     T.WARNING,
        "FAIBLE":    T.DANGER,
        "CRITIQUE":  T.DANGER,
    }.get(statut, T.PRIMARY)


def _statut_pill_class(statut: str) -> str:
    """Map v2 statut to mood-pill CSS class."""
    return {
        "EXCELLENT": "cool",
        "BON":       "bon",
        "MOYEN":     "neutre",
        "FAIBLE":    "faible",
        "CRITIQUE":  "serieux",
    }.get(statut, "neutre")


_STATUT_FR = {
    "EXCELLENT": "Excellent",
    "BON":       "Bon",
    "MOYEN":     "Moyen",
    "FAIBLE":    "Faible",
    "CRITIQUE":  "Critique",
}


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


def _sparkline_svg(values: list) -> str:
    """Small inline SVG polyline (non-bg use)."""
    W, H = 110, 44
    n = len(values)
    if n < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = (mx - mn) or 1.0
    pts = []
    for i, v in enumerate(values):
        x = round(i / (n - 1) * W, 1)
        y = round(H - 5 - ((v - mn) / rng) * (H - 10), 1)
        pts.append(f"{x},{y}")
    color = T.SUCCESS if values[-1] >= values[0] else T.DANGER
    return (
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        f'<polyline points="{" ".join(pts)}" fill="none" '
        f'stroke="{color}" stroke-width="2.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


def _sparkline_bg_style(values: list) -> str:
    """CSS background-image string — embedded SVG data URI, no DOM positioning."""
    W, H = 300, 80
    n = len(values)
    if n < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = (mx - mn) or 1.0
    pts = []
    for i, v in enumerate(values):
        x = round(i / (n - 1) * W, 1)
        y = round(H - 3 - ((v - mn) / rng) * (H - 6), 1)
        pts.append(f"{x},{y}")
    # rgba avoids # encoding issues in data URI
    c = "rgba(0,229,160" if values[-1] >= values[0] else "rgba(244,63,94"
    pts_str = " ".join(pts)
    fill_pts = f"{pts_str} {W},{H} 0,{H}"
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' "
        f"preserveAspectRatio='none'>"
        f"<polygon points='{fill_pts}' fill='{c},0.13)'/>"
        f"<polyline points='{pts_str}' fill='none' stroke='{c},0.45)' "
        f"stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/>"
        f"</svg>"
    )
    encoded = svg.replace("<", "%3C").replace(">", "%3E").replace('"', "%22")
    return (
        f"background-image:url(\"data:image/svg+xml,{encoded}\");"
        f"background-repeat:no-repeat;"
        f"background-size:100% 65%;"
        f"background-position:bottom center;"
    )


def _render_hero_zone(bilan: dict, proj: dict, score: dict, mois_lbl: str,
                       sparkline: list = None, epargne_mois: float = 0.0,
                       streak_jours: int = 0, mois_verts: int = 0) -> None:
    """Hero + KPI strip in one card. Sparkline via CSS bg-image (no DOM positioning)."""
    solde      = bilan["solde"]
    sign       = "+" if solde >= 0 else "−"
    sclass     = "pos" if solde >= 0 else "neg"
    proj_v     = proj.get("projection_fin_mois", 0) or 0
    # v1 had taux_epargne_pct (0–100), v2 has taux_epargne (0–1) — bridge both
    taux_ep    = float(
        score.get("taux_epargne_pct")
        or (score.get("taux_epargne", 0) or 0) * 100
    )
    revenus    = bilan["revenus"]
    depenses   = bilan["depenses"]
    je         = int(proj.get("jours_ecoules", 0) or 0)
    jours_rest = max(0, int(proj.get("jours_total", 30) or 30) - je)
    reste      = max(0.0, revenus - max(depenses, float(proj_v)))
    ep_color   = T.SUCCESS if epargne_mois > 0 else T.TEXT_LOW
    ep_sub     = "Ce mois" if epargne_mois > 0 else "Non renseignée"
    bg_style   = _sparkline_bg_style(sparkline or [])

    # Streak badge for hero top-right
    if streak_jours >= 2:
        streak_badge = (
            f'<div style="position:absolute;top:16px;right:20px;z-index:2">'
            f'<span style="background:{T.SUCCESS}18;border:1px solid {T.SUCCESS}35;'
            f'color:{T.SUCCESS};font-size:11px;font-weight:700;padding:4px 10px;'
            f'border-radius:99px">🔥 {streak_jours}j de suite</span>'
            f'</div>'
        )
    elif streak_jours == 1:
        streak_badge = (
            f'<div style="position:absolute;top:16px;right:20px;z-index:2">'
            f'<span style="background:{T.WARNING}18;border:1px solid {T.WARNING}35;'
            f'color:{T.WARNING};font-size:11px;font-weight:700;padding:4px 10px;'
            f'border-radius:99px">🔥 1er jour — bonne reprise !</span>'
            f'</div>'
        )
    else:
        streak_badge = ""

    def _kpi(label, val_html, sub, border=True):
        br = f"border-right:1px solid rgba(255,255,255,0.07);" if border else ""
        return (
            f'<div style="flex:1;padding:0 16px;{br}">'
            f'<div style="color:{T.TEXT_LOW};font-size:9px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1.5px;margin-bottom:5px">{label}</div>'
            f'{val_html}'
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">{sub}</div>'
            f'</div>'
        )

    kpis = (
        f'<div style="display:flex;align-items:stretch;'
        f'border-top:1px solid rgba(255,255,255,0.07);'
        f'margin:16px -40px 0;padding:16px 40px 0">'
        + _kpi("Total Revenus",
               f'<div style="color:{T.SUCCESS};font-size:19px;font-weight:900">'
               f'{_fmt_dh(revenus)} <span style="font-size:11px;font-weight:400">DH</span></div>',
               "Encaissés ce mois")
        + _kpi("Total Dépenses",
               f'<div style="color:{T.WARNING};font-size:19px;font-weight:900">'
               f'{_fmt_dh(depenses)} <span style="font-size:11px;font-weight:400">DH</span></div>',
               f'Sur {je}j · <b style="color:{T.TEXT_MED}">{jours_rest}j restants</b>')
        + _kpi("Reste à vivre",
               f'<div style="color:{T.TEXT_HIGH};font-size:19px;font-weight:900">'
               f'{_fmt_dh(reste)} <span style="font-size:11px;font-weight:400">DH</span></div>',
               f'Proj. {_fmt_dh(proj_v)} DH dépensé')
        + _kpi("Épargne du mois",
               f'<div style="color:{ep_color};font-size:19px;font-weight:900">'
               f'{_fmt_dh(epargne_mois)} <span style="font-size:11px;font-weight:400">DH</span></div>',
               ep_sub, border=False)
        + '</div>'
    )

    st.markdown(
        f'<div class="v1-hero" style="position:relative;padding-bottom:0;{bg_style}">'
        f'{streak_badge}'
        f'  <div class="v1-hero-label">{mois_lbl} · Solde net</div>'
        f'  <div class="v1-hero-amount">'
        f'    <span class="sign {sclass}">{sign}</span>{_fmt_dh(solde)}'
        f'    <span class="unit">DH</span>'
        f'  </div>'
        f'  <div class="v1-hero-sub">'
        f'    <span class="v1-hero-pill">↑ {taux_ep:.1f}% épargne</span>'
        f'    <span>Projection fin de mois <span class="hv warn">{_fmt_dh(proj_v)} DH</span></span>'
        f'  </div>'
        f'{kpis}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_categories(rept: list, ctx: dict) -> None:
    if not rept:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:32px 16px;text-align:center;margin-top:18px">'
            f'<div style="color:{T.TEXT_LOW};font-size:13px">Aucune dépense ce mois.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    total_dep = sum(float(r.get("Total_DH") or 0) for r in rept)
    nb = len(rept)

    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'margin:6px 0 10px">'
        f'<span class="v1-sec-head" style="margin:0">Dépenses par catégorie</span>'
        f'<span style="color:{T.TEXT_LOW};font-size:11px">'
        f'{nb} catégorie{"s" if nb != 1 else ""} · {_fmt_dh(total_dep)} DH</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # First-visit hint — explain categories are clickable
    from components.hints import show_hint
    show_hint(
        ctx["audit"],
        hint_id="hint_categories_clickable",
        title="Clique sur une catégorie",
        body="Chaque ligne s'ouvre pour montrer le détail des sous-catégories de ce mois.",
        icon="👆",
    )

    res_sous  = ctx["_q"]("detail_sous_categories", mois=ctx["mois_sel"])
    sous_data = res_sous.get("resultat", []) if "resultat" in res_sous else []
    sous_par_cat: dict = {}
    for sc in sous_data:
        sous_par_cat.setdefault(sc["Categorie"], []).append(sc)

    for i, row in enumerate(rept):
        cat   = row["Categorie"] or "Non classé"
        color = CAT_COLORS[i % len(CAT_COLORS)]
        total = float(row.get("Total_DH") or 0)
        poids = float(row.get("Poids_Pct") or 0)
        bar_w = min(poids, 100)
        sous  = sous_par_cat.get(cat, [])

        with st.expander(f"**{cat}**  ·  {_fmt_dh(total)} DH  ·  {poids:.1f}%", expanded=False):
            # Colored accent line + progress bar at top of expanded content
            st.markdown(
                f'<div style="height:2px;background:{color};border-radius:99px;'
                f'margin:0 0 12px;opacity:0.7"></div>'
                f'<div class="cat-bar-v2" style="margin-bottom:14px">'
                f'<div class="cat-bar-fill-v2" style="width:{bar_w:.1f}%;background:{color}"></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if not sous:
                st.markdown(
                    f'<div style="color:{T.TEXT_LOW};font-size:12px">Aucun détail.</div>',
                    unsafe_allow_html=True,
                )
                continue

            total_cat = total or 1
            rows_html = ""
            for sc in sous:
                sc_total = float(sc.get("Total_DH") or 0)
                sc_pct   = sc_total / total_cat * 100
                sc_bar   = min(sc_pct, 100)
                rows_html += (
                    f'<div class="cat-sub-row">'
                    f'  <div class="n">{sc["Sous_Categorie"]}</div>'
                    f'  <div class="b"><div class="bf" style="width:{sc_bar:.1f}%;background:{color}"></div></div>'
                    f'  <div class="a" style="color:{color}">{_fmt_dh(sc_total)} DH</div>'
                    f'  <div class="p">{sc_pct:.0f}%</div>'
                    f'</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)


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


def _render_rappels(audit, user_id: int, mois_sel: str, suggested_ep: float = 0.0) -> None:
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
                    value=float(round(suggested_ep)) if suggested_ep > 0 else 0.0,
                    format="%.0f", label_visibility="collapsed",
                )
                submitted = st.form_submit_button("Enregistrer", type="primary",
                                                  use_container_width=True)
                if submitted:
                    try:
                        db.sauvegarder_epargne_mois(user_id, mois_sel, float(montant_ep))
                        st.session_state._rappel_ep_open = False
                        st.success(f"✅ {montant_ep:,.0f} DH enregistrés.")
                        st.rerun()
                    except Exception:
                        st.error("Enregistrement échoué — réessayez.")
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

    # Deduplicate by DB id — user may have created the same goal twice
    seen_ids: set = set()
    unique_goals = []
    for g in goals:
        gid = g.get("id") or g.get("Id")
        if gid not in seen_ids:
            seen_ids.add(gid)
            unique_goals.append(g)

    for g in unique_goals[:1]:
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

    if len(unique_goals) > 1:
        if st.button(f"Voir les {len(unique_goals)} objectifs →", key="acc_goal_all",
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


def _render_coach_panel(
    message: str, humeur: str, identite: str,
    score: dict, audit, user_id: int, mois_sel: str, proj: dict,
    epargne_total: float = 0.0,
) -> None:
    """
    Unified coach panel — 5 sections in one card.

    `score` is the v2 ctx dict from compute_score() — uses 'statut' key
    (CRITIQUE/FAIBLE/MOYEN/BON/EXCELLENT). Falls back to legacy 'niveau'
    for backward compat.
    """
    # First-visit hint — explain the 5-factor scoring
    from components.hints import show_hint
    show_hint(
        audit,
        hint_id="hint_coach_panel_5_factors",
        title="Ton coach analyse 5 facteurs",
        body="Reste à vivre, épargne du mois, fonds d'urgence, dépenses équilibrées, engagement. Chaque facteur = une pierre. L'ensemble fait ta solidité.",
        icon="🧠",
    )
    score_val  = float(score.get("score", 0) or 0)
    statut     = score.get("statut") or score.get("niveau") or "MOYEN"
    score_col  = _statut_color(statut)
    niveau_fr  = _STATUT_FR.get(statut, statut)
    mood_cls   = _statut_pill_class(statut)
    initials   = (identite or "?")[:1].upper()
    suggested_ep = max(0.0, float(proj.get("solde_projete", 0) or 0))

    # Goals data
    try:
        goals = ui_cache.get_objectifs(audit, user_id)
    except Exception:
        goals = []
    seen, unique_goals = set(), []
    for g in goals:
        gid = g.get("id") or g.get("Id")
        if gid not in seen:
            seen.add(gid); unique_goals.append(g)
    first_goal = unique_goals[0] if unique_goals else None

    # Savings status
    try:
        ep = audit.db.get_epargne_mois(user_id, mois_sel)
    except Exception:
        ep = None

    # ── Goal HTML — up to 3 goals ─────────────────────────────────────────────
    if unique_goals:
        goal_html = ""
        for idx, g in enumerate(unique_goals[:3]):
            g_target  = float(g.get("montant_cible") or g.get("Montant_Cible") or 0)
            g_current = float(g.get("montant_actuel") or g.get("Montant_Actuel") or 0)
            g_pct     = min(100, round(g_current / g_target * 100)) if g_target > 0 else 0
            g_nom     = g.get("nom") or g.get("Nom") or "Objectif"
            g_date    = g.get("date_cible") or g.get("Date_Cible") or ""
            sep       = ('<div style="height:1px;background:rgba(255,255,255,0.04);'
                         'margin:10px 0"></div>') if idx > 0 else ""
            goal_html += (
                f'{sep}'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">'
                f'  <span style="font-size:13px;font-weight:600;color:{T.TEXT_HIGH}">🎯 {g_nom}</span>'
                f'  <span style="font-size:11px;color:{T.TEXT_LOW}">{g_date}</span>'
                f'</div>'
                f'<div class="cat-bar-v2" style="margin-bottom:5px">'
                f'  <div class="cat-bar-fill-v2" style="width:{g_pct}%;'
                f'    background:linear-gradient(90deg,{T.PRIMARY},{T.SUCCESS})"></div>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;font-size:12px;color:{T.TEXT_MED}">'
                f'  <span><span style="color:{T.TEXT_HIGH};font-weight:600">{_fmt_dh(g_current)}</span>'
                f'  / {_fmt_dh(g_target)} DH</span>'
                f'  <span>{g_pct}%</span>'
                f'</div>'
            )
    else:
        goal_html = (
            f'<div style="color:{T.TEXT_LOW};font-size:12px;text-align:center;padding:4px 0">'
            f'Aucun objectif défini</div>'
        )

    # ── Épargne breakdown (single source of truth model) ─────────────────────
    epargne_allouee = sum(
        float(g.get("montant_actuel") or g.get("Montant_Actuel") or 0)
        for g in unique_goals
    )
    epargne_libre = max(0.0, epargne_total - epargne_allouee)
    libre_color = (
        T.SUCCESS if epargne_libre >= epargne_total * 0.5
        else T.PRIMARY if epargne_libre > 0
        else T.WARNING
    )
    # Pre-built HTML rows (avoids backslash-in-f-string issues)
    ep_alloc_row = (
        f'<div style="display:flex;justify-content:space-between;'
        f'align-items:center;margin-bottom:10px">'
        f'<span style="color:{T.TEXT_LOW};font-size:12px">→ Objectifs alloués</span>'
        f'<span style="color:{T.WARNING};font-size:13px;font-weight:600">'
        f'− {_fmt_dh(epargne_allouee)} DH</span></div>'
    ) if epargne_allouee > 0 else ""
    ep_sep = (
        '<div style="height:1px;background:rgba(255,255,255,0.08);margin-bottom:10px"></div>'
    ) if epargne_allouee > 0 else ""

    # ── Rappel HTML ───────────────────────────────────────────────────────────
    if ep is not None:
        reel = float(ep.get("Montant_Reel", 0) or 0)
        rappel_html = (
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'  <div>'
            f'    <div style="color:{T.SUCCESS};font-size:10px;font-weight:700;'
            f'      text-transform:uppercase;letter-spacing:1px">💰 Épargne du mois</div>'
            f'    <div style="color:{T.TEXT_LOW};font-size:12px;margin-top:2px">Enregistrée</div>'
            f'  </div>'
            f'  <div style="color:{T.SUCCESS};font-size:18px;font-weight:900">{_dh(reel)}</div>'
            f'</div>'
        )
        rappel_needs_btn = False
    else:
        rappel_html = (
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'  <div>'
            f'    <div style="color:{T.WARNING};font-size:10px;font-weight:700;'
            f'      text-transform:uppercase;letter-spacing:1px">💰 Épargne du mois</div>'
            f'    <div style="color:{T.TEXT_LOW};font-size:12px;margin-top:2px">Non renseignée</div>'
            f'  </div>'
            f'</div>'
        )
        rappel_needs_btn = True

    _div = '<div class="cp-divider"></div>'

    # ── Full card ─────────────────────────────────────────────────────────────
    extra_goals_lbl = (
        f'<div style="color:{T.PRIMARY};font-size:11px;font-weight:600;margin-top:10px">'
        f'+{len(unique_goals) - 3} autres ›</div>'
    ) if len(unique_goals) > 3 else ""

    st.markdown(
        f'<div class="coach-panel">'
        # 1 — Header (💬 icon signals clickability)
        f'  <div class="cp-header">'
        f'    <div class="coach-avatar-v1">{initials}</div>'
        f'    <div class="coach-meta-v1">'
        f'      <div class="name">Coach {identite}</div>'
        f'      <div class="role">Assistant financier</div>'
        f'    </div>'
        f'    <span class="mood-pill-v1 {mood_cls}">{niveau_fr.upper()}</span>'
        f'    <span style="font-size:18px;margin-left:6px;opacity:0.55">💬</span>'
        f'  </div>'
        # 2 — Score bar (compact horizontal — no divider, merges with header)
        f'  <div class="cp-score-row">'
        f'    <div class="cp-score-num" style="color:{score_col}">{score_val:.0f}'
        f'      <span class="cp-score-denom">/100</span>'
        f'    </div>'
        f'    <div style="flex:1">'
        f'      <div style="font-size:10px;font-weight:700;text-transform:uppercase;'
        f'        letter-spacing:1.5px;color:{score_col};margin-bottom:8px">{niveau_fr}</div>'
        f'      <div class="cat-bar-v2" style="height:5px">'
        f'        <div class="cat-bar-fill-v2" style="width:{score_val:.0f}%;background:{score_col}"></div>'
        f'      </div>'
        f'    </div>'
        f'  </div>'
        f'{_div}'
        # 3 — Message
        f'  <div class="cp-message">{message}</div>'
        f'{_div}'
        # 4 — Goal
        f'  <div class="cp-section">'
        f'    <div class="cp-section-lbl">Objectif ›</div>'
        f'    {goal_html}'
        f'    {extra_goals_lbl}'
        f'  </div>'
        f'{_div}'
        # 5 — Épargne breakdown: totale → allouée → libre
        f'  <div class="cp-section">'
        f'    <div class="cp-section-lbl">Épargne</div>'
        f'    <div style="display:flex;justify-content:space-between;'
        f'      align-items:center;margin-bottom:6px">'
        f'      <span style="color:{T.TEXT_LOW};font-size:12px">Totale</span>'
        f'      <span style="color:{T.TEXT_MED};font-size:13px;font-weight:600">'
        f'        {_fmt_dh(epargne_total)} DH</span>'
        f'    </div>'
        f'    {ep_alloc_row}'
        f'    {ep_sep}'
        f'    <div style="display:flex;justify-content:space-between;align-items:center">'
        f'      <span style="color:{T.TEXT_MED};font-size:12px;font-weight:700;'
        f'        text-transform:uppercase;letter-spacing:0.5px">Libre</span>'
        f'      <span style="color:{libre_color};font-size:18px;font-weight:900">'
        f'        {_fmt_dh(epargne_libre)}'
        f'        <span style="font-size:11px;font-weight:400;color:{T.TEXT_LOW}"> DH</span>'
        f'      </span>'
        f'    </div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # "Voir tous les objectifs" — only when overflow beyond 3
    if len(unique_goals) > 3:
        if st.button(f"Voir les {len(unique_goals)} objectifs →", key="cp_more_goals",
                     use_container_width=True, type="secondary"):
            st.session_state.page = "Objectif"
            st.rerun()

    # Coach CTA — 💬 icon style, sits under card
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    if st.button("💬 Parler au Coach", key="coach_cta", use_container_width=True):
        st.session_state.page = "Assistant"
        st.rerun()

    # Rappel action — unchanged (4)
    if rappel_needs_btn:
        if st.button("💰 Renseigner l'épargne →", key="cp_rappel_btn",
                     use_container_width=True, type="secondary"):
            st.session_state._rappel_ep_open = True
            st.rerun()
        if st.session_state.get("_rappel_ep_open"):
            with st.form("form_epargne_panel", clear_on_submit=True):
                montant_ep = st.number_input(
                    "Épargne réelle ce mois (DH)", min_value=0.0, step=100.0,
                    value=float(round(suggested_ep)) if suggested_ep > 0 else 0.0,
                    format="%.0f",
                )
                if st.form_submit_button("Enregistrer", type="primary",
                                         use_container_width=True):
                    try:
                        audit.db.sauvegarder_epargne_mois(user_id, mois_sel, float(montant_ep))
                        st.session_state._rappel_ep_open = False
                        _invalider_cache()
                        st.rerun()
                    except Exception:
                        st.error("Enregistrement échoué.")

    # Goal CTA if none defined
    if not unique_goals:
        if st.button("🎯 Créer un objectif →", key="cp_goal_cta",
                     use_container_width=True, type="secondary"):
            st.session_state.page = "Objectif"
            st.rerun()


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

    # First-visit hints (one-shot, dismissible) — Accueil welcome + quick add
    from components.hints import show_hint
    show_hint(
        audit,
        hint_id="hint_accueil_welcome",
        title="Bienvenue sur ton tableau de bord",
        body="Score, dépenses, conseils — tout ici. Le coach analyse en temps réel tes 5 facteurs.",
        icon="👋",
    )
    show_hint(
        audit,
        hint_id="hint_topbar_quick_add",
        title="Ajoute une dépense en 3 clics",
        body="Le bouton 💸 Dépense en haut ouvre un mini-formulaire. Plus tu logues souvent, plus ton score est fiable.",
        icon="💸",
    )

    try:
        sparkline_data = audit.db.get_solde_7j(ctx["user_id"])
    except Exception:
        sparkline_data = []

    try:
        epargne_total = audit.db.get_cumul_epargne(ctx["user_id"])
    except Exception:
        epargne_total = 0.0

    # Monthly savings for hero KPI
    try:
        _ep_rec = audit.db.get_epargne_mois(ctx["user_id"], ctx["mois_sel"])
        epargne_mois = float(_ep_rec.get("Montant_Reel", 0) or 0) if _ep_rec else 0.0
    except Exception:
        epargne_mois = 0.0

    # Coach v2 — compute_score (5-factor) + select_message (priority-based)
    try:
        from core.assistant_engine import compute_score
        from core.coach_messages import select_message, render_message
        v2_score   = compute_score(audit, ctx["mois_sel"])
        v2_msg_raw = select_message(v2_score)
        v2_msg     = render_message(v2_msg_raw, v2_score)
        score_for_panel   = v2_score          # has 'score' + 'statut'
        message_for_panel = v2_msg["message"]
    except Exception:
        # Fallback to legacy if v2 fails (transition safety)
        score_for_panel   = score
        message_for_panel = message

    _render_hero_zone(bilan, proj, score_for_panel, mois_lbl, sparkline_data, epargne_mois,
                      streak_jours, mois_verts)

    col_cats, col_right = st.columns([3, 2], gap="large")
    with col_cats:
        _render_categories(rept, ctx)
    with col_right:
        _render_coach_panel(
            message_for_panel, humeur, identite, score_for_panel, audit,
            ctx["user_id"], ctx["mois_sel"], proj,
            epargne_total=epargne_total,
        )
        if alertes:
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
            for a in alertes[:2]:
                alerte_box(a["message"], a["couleur"])
