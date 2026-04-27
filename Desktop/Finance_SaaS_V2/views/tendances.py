"""
views/tendances.py — Trend & insights page (Block C of Sprint 3).

5 sections:
    1. KPI strip — total revenus / dépenses / solde cumulé over N months
    2. Cashflow chart — up/down monthly bars (revenus green up, dépenses red down)
    3. Velocity card — Daily Avg Spend + Safe-to-Spend per remaining day
    4. Subscription leakage — récurrents detected via get_charges_fixes
    5. Top 3 lists — most expensive categories, frequent merchants, largest single transactions

Data sources: db.get_cashflow_mensuel() + db.get_solde_mensuel_histo() +
audit.moteur.get_bilan_mensuel() + audit.query("charges_fixes") +
audit.moteur.get_repartition_par_categorie() + raw queries for Top 3.
"""

from __future__ import annotations
from datetime import date

import streamlit as st

from components.design_tokens import T
from components.helpers import dh as _dh, render_page_header
from components.hints import show_hint


def _fmt_dh(n: float) -> str:
    return f"{abs(n):,.0f}".replace(",", " ")


def _french_month_short(month: int, year: int) -> str:
    months = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
              "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
    return f"{months[month-1]} {str(year)[-2:]}"


# ── 1. KPI strip ────────────────────────────────────────────────────────────
def _render_kpi_strip(cashflow: list, nb_mois: int) -> None:
    if not cashflow:
        return
    total_rev = sum(c["revenus"]  for c in cashflow)
    total_dep = sum(c["depenses"] for c in cashflow)
    solde     = total_rev - total_dep
    solde_color = T.SUCCESS if solde >= 0 else T.DANGER

    st.markdown(
        f'<div style="display:flex;gap:12px;margin-bottom:18px">'
        f'  <div style="flex:1;background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'    border-radius:{T.RADIUS_MD};padding:14px 16px">'
        f'    <div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1.2px">Revenus {nb_mois}m</div>'
        f'    <div style="color:{T.SUCCESS};font-size:20px;font-weight:900;'
        f'      margin-top:4px">{_fmt_dh(total_rev)} <span style="font-size:11px;'
        f'      font-weight:400;color:{T.TEXT_MED}">DH</span></div>'
        f'  </div>'
        f'  <div style="flex:1;background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'    border-radius:{T.RADIUS_MD};padding:14px 16px">'
        f'    <div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1.2px">Dépenses {nb_mois}m</div>'
        f'    <div style="color:{T.WARNING};font-size:20px;font-weight:900;'
        f'      margin-top:4px">{_fmt_dh(total_dep)} <span style="font-size:11px;'
        f'      font-weight:400;color:{T.TEXT_MED}">DH</span></div>'
        f'  </div>'
        f'  <div style="flex:1;background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'    border-radius:{T.RADIUS_MD};padding:14px 16px">'
        f'    <div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1.2px">Solde cumulé</div>'
        f'    <div style="color:{solde_color};font-size:20px;font-weight:900;'
        f'      margin-top:4px">{"+"  if solde >= 0 else "−"}{_fmt_dh(solde)} '
        f'      <span style="font-size:11px;font-weight:400;color:{T.TEXT_MED}">DH</span></div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── 2. Cashflow chart — up/down monthly bars ────────────────────────────────
def _render_cashflow_chart(cashflow: list) -> None:
    if not cashflow:
        return
    import plotly.graph_objects as go

    months = [_french_month_short(c["month"], c["year"]) for c in cashflow]
    revenus  = [c["revenus"]    for c in cashflow]
    depenses = [-c["depenses"]  for c in cashflow]  # negative → bars point down

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=months, y=revenus, name="Revenus",
        marker=dict(color=T.SUCCESS, line=dict(color=T.BG_PAGE, width=1)),
        hovertemplate="%{x}<br>+%{y:,.0f} DH<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=months, y=depenses, name="Dépenses",
        marker=dict(color=T.DANGER, line=dict(color=T.BG_PAGE, width=1)),
        hovertemplate="%{x}<br>−%{customdata:,.0f} DH<extra></extra>",
        customdata=[c["depenses"] for c in cashflow],
    ))

    fig.update_layout(
        barmode="relative",
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(color=T.TEXT_MED, size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor=T.BG_PAGE,
        plot_bgcolor=T.BG_PAGE,
        font_color=T.TEXT_MED,
        margin=dict(t=30, b=20, l=20, r=20),
        height=320,
        xaxis=dict(showgrid=False, tickfont=dict(size=11)),
        yaxis=dict(
            showgrid=True,
            gridcolor=T.BORDER,
            zerolinecolor=T.TEXT_MED,
            zerolinewidth=1,
            tickformat=",.0f",
            tickfont=dict(size=10),
        ),
        bargap=0.25,
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── 3. Velocity card — daily avg + safe-to-spend ────────────────────────────
def _render_velocity(audit, mois_sel: str) -> None:
    try:
        bilan = audit.moteur.get_bilan_mensuel(mois_sel)
        proj  = audit.moteur.get_projection_fin_mois(mois_sel)
    except Exception:
        return

    revenus    = float(getattr(bilan, "revenus", 0) or 0)
    depenses   = float(getattr(bilan, "depenses", 0) or 0)
    je         = int(proj.get("jours_ecoules", 0) or 0)
    jt         = int(proj.get("jours_total", 30) or 30)
    jours_rest = max(1, jt - je)  # avoid div by zero

    # Daily avg = depenses to date / days elapsed
    daily_avg = depenses / je if je > 0 else 0.0

    # Safe-to-spend = (revenus - depenses_actuelles) / jours_restants
    safe_to_spend = max(0.0, (revenus - depenses) / jours_rest)

    st.markdown(
        f'<div style="display:flex;gap:12px;margin-bottom:18px">'
        f'  <div style="flex:1;background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'    border-left:3px solid {T.WARNING};border-radius:{T.RADIUS_MD};padding:14px 16px">'
        f'    <div style="color:{T.WARNING};font-size:10px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1.2px">Vitesse de dépense</div>'
        f'    <div style="color:{T.TEXT_HIGH};font-size:18px;font-weight:900;margin-top:4px">'
        f'      {_fmt_dh(daily_avg)} <span style="font-size:11px;font-weight:400;color:{T.TEXT_MED}">DH/jour</span>'
        f'    </div>'
        f'    <div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
        f'      Sur {je}j — moyenne actuelle</div>'
        f'  </div>'
        f'  <div style="flex:1;background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'    border-left:3px solid {T.SUCCESS};border-radius:{T.RADIUS_MD};padding:14px 16px">'
        f'    <div style="color:{T.SUCCESS};font-size:10px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1.2px">Safe to spend</div>'
        f'    <div style="color:{T.TEXT_HIGH};font-size:18px;font-weight:900;margin-top:4px">'
        f'      {_fmt_dh(safe_to_spend)} <span style="font-size:11px;font-weight:400;color:{T.TEXT_MED}">DH/jour</span>'
        f'    </div>'
        f'    <div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
        f'      Pour les {jours_rest}j restants — pour rester en marge</div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── 4. Subscription leakage card ────────────────────────────────────────────
def _render_subscription_leakage(audit) -> None:
    try:
        cf = audit.moteur.get_charges_fixes(nb_mois_min=2)
    except Exception:
        return
    if cf is None or (hasattr(cf, "empty") and cf.empty):
        return

    total = float(cf["Montant_Moyen"].sum())
    nb    = len(cf)

    rows_html = ""
    for _, r in cf.head(5).iterrows():
        lib   = str(r.get("Libelle", ""))[:30]
        mnt   = float(r.get("Montant_Moyen", 0))
        nb_m  = int(r.get("Nb_Mois", 0))
        rows_html += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:5px 0;border-bottom:1px solid {T.BORDER}">'
            f'  <span style="color:{T.TEXT_MED};font-size:12px">{lib}</span>'
            f'  <span style="display:flex;gap:10px;align-items:center">'
            f'    <span style="color:{T.TEXT_HIGH};font-size:12px;font-weight:600">{_fmt_dh(mnt)} DH</span>'
            f'    <span style="color:{T.TEXT_LOW};font-size:10px">{nb_m}×</span>'
            f'  </span>'
            f'</div>'
        )
    extra = (
        f'<div style="color:{T.TEXT_LOW};font-size:11px;text-align:right;padding-top:6px">'
        f'+{nb - 5} autres</div>'
    ) if nb > 5 else ""

    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:16px 18px;margin-bottom:18px">'
        f'  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px">'
        f'    <span style="color:{T.WARNING};font-size:11px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1.2px">📌 Charges fixes détectées</span>'
        f'    <span style="color:{T.TEXT_HIGH};font-size:14px;font-weight:700">'
        f'      {_fmt_dh(total)} DH/mois</span>'
        f'  </div>'
        f'  <div style="color:{T.TEXT_LOW};font-size:11px;margin-bottom:10px">'
        f'    {nb} charge{"s" if nb > 1 else ""} récurrente{"s" if nb > 1 else ""} '
        f'    — passe-les en revue pour identifier les abonnements oubliés.'
        f'  </div>'
        f'  {rows_html}'
        f'  {extra}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── 5. Top 3 lists ──────────────────────────────────────────────────────────
def _render_top3_lists(audit, mois_sel: str) -> None:
    user_id = audit.user_id

    # 5a. Top 3 categories this month
    try:
        repart = audit.moteur.get_repartition_par_categorie(mois_sel)
        top_cats = repart.head(3) if repart is not None and not repart.empty else None
    except Exception:
        top_cats = None

    # 5b. Top 3 largest single transactions in last 6 months
    try:
        with audit.db.connexion() as conn:
            rows_tx = conn.execute("""
                SELECT Libelle, Montant, Categorie, DATE(Date) AS jour
                FROM TRANSACTIONS
                WHERE user_id = %s AND Sens = 'OUT'
                  AND Date >= (CURRENT_DATE - INTERVAL '6 months')
                ORDER BY Montant DESC
                LIMIT 3
            """, (user_id,)).fetchall()
        top_tx = list(rows_tx) if rows_tx else []
    except Exception:
        top_tx = []

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:16px 18px;height:100%">'
            f'  <div style="color:{T.PRIMARY};font-size:11px;font-weight:700;'
            f'    text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px">'
            f'    🏆 Top 3 catégories ce mois</div>',
            unsafe_allow_html=True,
        )
        if top_cats is not None and not top_cats.empty:
            html = ""
            for i, (_, row) in enumerate(top_cats.iterrows(), 1):
                cat = row.get("Categorie") or "Non classé"
                amt = float(row.get("Total_DH") or 0)
                pct = float(row.get("Poids_Pct") or 0)
                html += (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:6px 0;border-bottom:1px solid {T.BORDER}">'
                    f'  <span style="color:{T.TEXT_HIGH};font-size:13px"><b>{i}.</b> {cat}</span>'
                    f'  <span style="display:flex;gap:8px;align-items:center">'
                    f'    <span style="color:{T.TEXT_HIGH};font-size:13px;font-weight:600">{_fmt_dh(amt)} DH</span>'
                    f'    <span style="color:{T.TEXT_LOW};font-size:11px">{pct:.0f}%</span>'
                    f'  </span>'
                    f'</div>'
                )
            st.markdown(html + "</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div style="color:{T.TEXT_LOW};font-size:12px">Aucune donnée pour ce mois.</div></div>',
                unsafe_allow_html=True,
            )

    with c2:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:16px 18px;height:100%">'
            f'  <div style="color:{T.DANGER};font-size:11px;font-weight:700;'
            f'    text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px">'
            f'    💥 Top 3 plus grosses dépenses (6m)</div>',
            unsafe_allow_html=True,
        )
        if top_tx:
            html = ""
            for i, r in enumerate(top_tx, 1):
                lib = str(r["Libelle"] if "Libelle" in r else r[0])[:24]
                mnt = float(r["Montant"] if "Montant" in r else r[1] or 0)
                cat = str(r["Categorie"] if "Categorie" in r else r[2] or "")[:15]
                html += (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:6px 0;border-bottom:1px solid {T.BORDER}">'
                    f'  <div style="display:flex;flex-direction:column;gap:2px">'
                    f'    <span style="color:{T.TEXT_HIGH};font-size:13px"><b>{i}.</b> {lib}</span>'
                    f'    <span style="color:{T.TEXT_LOW};font-size:10px">{cat}</span>'
                    f'  </div>'
                    f'  <span style="color:{T.TEXT_HIGH};font-size:13px;font-weight:600">{_fmt_dh(mnt)} DH</span>'
                    f'</div>'
                )
            st.markdown(html + "</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div style="color:{T.TEXT_LOW};font-size:12px">Pas assez de données.</div></div>',
                unsafe_allow_html=True,
            )


# ── Entry point ─────────────────────────────────────────────────────────────
def render(ctx: dict) -> None:
    audit    = ctx["audit"]
    mois_sel = ctx["mois_sel"]
    user_id  = ctx["user_id"]

    render_page_header("📈", "Tendances", "Vue 6 mois — flux, vitesse, top dépenses")

    # First-visit hint
    show_hint(
        audit,
        hint_id="hint_tendances_intro",
        title="Vue d'ensemble sur 6 mois",
        body="Cashflow mensuel, vitesse de dépense, top catégories — pour repérer les patterns et planifier la suite.",
        icon="📊",
    )

    # Period selector
    nb_mois = st.selectbox(
        "Période",
        options=[3, 6, 12],
        index=1,
        format_func=lambda n: f"{n} derniers mois",
        key="tend_nb_mois",
        label_visibility="collapsed",
    )

    # Fetch data once
    try:
        cashflow = audit.db.get_cashflow_mensuel(user_id, nb_mois=nb_mois)
    except Exception:
        cashflow = []

    if not cashflow or all(c["revenus"] == 0 and c["depenses"] == 0 for c in cashflow):
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:32px 18px;text-align:center;margin-top:18px">'
            f'  <div style="font-size:32px;margin-bottom:8px">📉</div>'
            f'  <div style="color:{T.TEXT_HIGH};font-size:14px;font-weight:600;margin-bottom:6px">'
            f'    Pas encore assez de données</div>'
            f'  <div style="color:{T.TEXT_LOW};font-size:12px">'
            f"    Logue tes transactions pendant un mois pour voir tes tendances apparaître ici."
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # 1. KPI strip
    _render_kpi_strip(cashflow, nb_mois)

    # 2. Cashflow chart
    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px">'
        f'Flux mensuel</div>',
        unsafe_allow_html=True,
    )
    _render_cashflow_chart(cashflow)

    # 3. Velocity (only meaningful if current month has data)
    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1.5px;margin:18px 0 8px">'
        f'Rythme du mois en cours</div>',
        unsafe_allow_html=True,
    )
    _render_velocity(audit, mois_sel)

    # 4. Subscription leakage
    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1.5px;margin:6px 0 8px">'
        f'Charges récurrentes</div>',
        unsafe_allow_html=True,
    )
    _render_subscription_leakage(audit)

    # 5. Top 3 lists
    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1.5px;margin:6px 0 8px">'
        f'Champions de la dépense</div>',
        unsafe_allow_html=True,
    )
    _render_top3_lists(audit, mois_sel)
