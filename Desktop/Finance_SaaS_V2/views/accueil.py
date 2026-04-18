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

    k1, k2, k3, k4 = st.columns(4, gap="small")
    with k1:
        st.markdown(
            _card("success", "Revenus", revenus,
                  f'<span class="up">ce mois · {proj.get("jours_ecoules", "?")} j</span>'),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            _card("warn", "Dépenses", depenses,
                  f'<span class="warn">↑ {jours_rest} j restants</span>'),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            _card("", "Reste à vivre", reste_a_vivre,
                  f'pour {jours_rest} jours restants'),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            _card("violet", "Épargne cumulée", epargne_cumul,
                  f'<span class="up">+{_fmt_dh(epargne_mois)} ce mois</span>'),
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

    plan_rows = ""
    for key in ("Needs", "Wants", "Savings"):
        info = badges.get(key)
        if not info:
            continue
        rp = float(info.get("reel_pct", 0) or 0)
        cp = float(info.get("cible_pct", 0) or 0)
        amt = float(info.get("reel_dh", 0) or 0)
        dot = _PLAN_COLORS[key]
        over = rp > cp
        amt_color = T.WARNING if over else T.TEXT_HIGH
        plan_rows += (
            f'<div class="plan-row-v1">'
            f'  <div class="k"><span class="dot" style="background:{dot}"></span>{_PLAN_LABELS[key]}</div>'
            f'  <div class="v">'
            f'    <span class="pct">{rp:.1f}% / {cp:.0f}%</span>'
            f'    <span class="amt" style="color:{amt_color}">{_fmt_dh(amt)} DH</span>'
            f'  </div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="gauge-card" style="margin-top:14px">'
        f'  <div class="gauge-title">Score Santé Financière</div>'
        f'  <div class="gauge-wrap">'
        f'    {_gauge_svg(score_val, color)}'
        f'    <div class="gauge-text">'
        f'      <div class="gauge-num" style="color:{color}">{score_val:.0f}</div>'
        f'      <div class="gauge-total">sur 100</div>'
        f'      <div class="gauge-label" style="color:{color}">{level}</div>'
        f'    </div>'
        f'  </div>'
        f'  <div style="margin-top:14px">'
        f'    <div class="gauge-title" style="margin-bottom:8px">Plan 50 / 30 / 20</div>'
        f'    {plan_rows}'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_goals(audit) -> None:
    try:
        goals = audit.get_objectifs_v2() or []
    except Exception:
        goals = []
    if not goals:
        return

    st.markdown(
        '<div class="v1-sec-head" style="margin-top:18px">Objectifs d\'épargne</div>',
        unsafe_allow_html=True,
    )
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

    _render_hero(bilan, proj, score, mois_lbl)
    _render_kpis(bilan, proj)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    col_cats, col_right = st.columns([3, 2], gap="large")
    with col_cats:
        _render_categories(rept, ctx)
    with col_right:
        _render_coach(message, humeur, identite)
        _render_score_plan(score, badges)
        _render_goals(audit)
        if alertes:
            st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
            for a in alertes[:3]:
                alerte_box(a["message"], a["couleur"])

    _render_donut(rept)
