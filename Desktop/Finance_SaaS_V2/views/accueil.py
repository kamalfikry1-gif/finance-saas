"""
views/accueil.py — Page Accueil du Dashboard.

Reçoit ctx dict (construit dans app.py) et affiche :
    - Hero solde net
    - KPIs (revenus, dépenses, projection, épargne)
    - Catégories + Coach + Score + Plan 50/30/20
    - Donut dépenses bas de page
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from config import COLOR_WARNING, COLOR_DANGER, SCORE_SEUIL_ORANGE
from components.cards import fs_card, alerte_box, cat_row, afficher_coach, CAT_COLORS


def _dh(v: float) -> str:
    return f"{abs(v):,.0f} DH".replace(",", " ")

def _pct(v: float) -> str:
    return f"{v:.1f}%"


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

    solde     = bilan["solde"]
    col_solde = "#22c55e" if solde >= 0 else "#ef4444"
    signe     = "+" if solde >= 0 else "-"

    # ── Hero solde ────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="fs-hero">'
        f'<div class="h-lbl">{mois_lbl} · Solde net</div>'
        f'<div class="h-val" style="color:{col_solde}">'
        f'{signe}{abs(solde):,.0f}'
        f'<span style="font-size:22px;font-weight:400;margin-left:6px">DH</span>'
        f'</div>'
        f'<div class="h-sub">'
        f'Revenus {_dh(bilan["revenus"])} &nbsp;·&nbsp; '
        f'Dépenses {_dh(bilan["depenses"])}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── KPIs ──────────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        fs_card("Revenus", _dh(bilan["revenus"]), mois_lbl, "#22c55e")
    with k2:
        fs_card("Dépenses", _dh(bilan["depenses"]), mois_lbl, "#ef4444")
    with k3:
        pdh   = proj.get("projection_fin_mois", 0)
        col_p = "#f59e0b" if pdh <= bilan["revenus"] else "#ef4444"
        fs_card("Projection", _dh(pdh),
                f"J{proj.get('jours_ecoules','?')}/{proj.get('jours_total','?')}",
                col_p)
    with k4:
        fs_card("Épargne cumulée", _dh(bilan["epargne_cumul"]),
                "historique total", "#6366f1")

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Catégories + Coach ────────────────────────────────────────────────────
    col_cats, col_right = st.columns([3, 2], gap="large")

    with col_cats:
        st.markdown(
            "<div style='color:#64748b;font-size:11px;font-weight:700;"
            "text-transform:uppercase;letter-spacing:1px;margin-bottom:10px'>"
            "Dépenses par catégorie</div>",
            unsafe_allow_html=True,
        )
        if rept:
            # Sous-catégories chargées une seule fois
            res_sous  = ctx["_q"]("detail_sous_categories", mois=ctx["mois_sel"])
            sous_data = res_sous.get("resultat", []) if "resultat" in res_sous else []
            sous_par_cat: dict = {}
            for sc in sous_data:
                sous_par_cat.setdefault(sc["Categorie"], []).append(sc)

            for i, row in enumerate(rept):
                cat     = row["Categorie"]
                couleur = CAT_COLORS[i % len(CAT_COLORS)]
                amt_str = f"{abs(row['Total_DH']):,.0f} DH".replace(",", " ")
                bar_w   = min(row["Poids_Pct"], 100)
                sous    = sous_par_cat.get(cat, [])
                nb_sous = len(sous)

                with st.expander(
                    f"**{cat}** &nbsp;·&nbsp; {amt_str} &nbsp;·&nbsp; {row['Poids_Pct']:.1f}%",
                    expanded=False,
                ):
                    # Barre catégorie
                    st.markdown(
                        f"<div style='background:#0a0a14;border-radius:99px;"
                        f"height:5px;overflow:hidden;margin-bottom:14px'>"
                        f"<div style='width:{bar_w:.1f}%;height:5px;background:{couleur};"
                        f"border-radius:99px'></div></div>",
                        unsafe_allow_html=True,
                    )
                    if sous:
                        total_cat = row["Total_DH"] or 1
                        for sc in sous:
                            sc_pct  = sc["Total_DH"] / total_cat * 100
                            sc_bar  = min(sc_pct, 100)
                            sc_amt  = f"{abs(sc['Total_DH']):,.0f} DH".replace(",", " ")
                            st.markdown(
                                f"<div style='display:flex;align-items:center;gap:10px;"
                                f"margin-bottom:9px'>"
                                f"<div style='color:#94a3b8;font-size:12px;min-width:160px;"
                                f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
                                f"{sc['Sous_Categorie']}</div>"
                                f"<div style='flex:1;background:#0a0a14;border-radius:99px;"
                                f"height:4px;overflow:hidden'>"
                                f"<div style='width:{sc_bar:.1f}%;height:4px;background:{couleur};"
                                f"border-radius:99px'></div></div>"
                                f"<div style='color:{couleur};font-size:12px;font-weight:700;"
                                f"min-width:85px;text-align:right'>{sc_amt}</div>"
                                f"<div style='color:#475569;font-size:11px;min-width:36px;"
                                f"text-align:right'>{sc_pct:.0f}%</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.markdown(
                            "<div style='color:#334155;font-size:12px;padding:4px 0'>"
                            "Aucun détail disponible.</div>",
                            unsafe_allow_html=True,
                        )
        else:
            st.info("Aucune dépense ce mois.")

    with col_right:
        st.markdown(
            "<div style='color:#64748b;font-size:11px;font-weight:700;"
            "text-transform:uppercase;letter-spacing:1px;margin-bottom:10px'>"
            "Coach</div>",
            unsafe_allow_html=True,
        )
        afficher_coach(message, humeur, identite)

        # Score santé
        score_val = score.get("score", 0)
        col_sc    = ("#22c55e" if score_val >= 70 else
                     COLOR_WARNING if score_val >= SCORE_SEUIL_ORANGE else COLOR_DANGER)
        st.markdown(
            f'<div class="fs-card" style="--accent:{col_sc};margin-top:10px">'
            f'<div class="lbl">Score santé</div>'
            f'<div style="display:flex;align-items:baseline;gap:6px;margin:6px 0 4px">'
            f'<span style="font-size:38px;font-weight:900;color:{col_sc}">'
            f'{score_val:.0f}</span>'
            f'<span style="color:#334155;font-size:16px">/100</span>'
            f'<span style="margin-left:8px;color:{col_sc};font-size:12px;'
            f'font-weight:700">{score.get("niveau","")}</span>'
            f'</div>'
            f'<div class="fs-bar-bg">'
            f'<div class="fs-bar" style="width:{score_val}%;background:{col_sc}"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Plan 50/30/20 compact
        if badges:
            st.markdown(
                "<div style='color:#64748b;font-size:11px;font-weight:700;"
                "text-transform:uppercase;letter-spacing:1px;"
                "margin:14px 0 8px'>Plan 50/30/20</div>",
                unsafe_allow_html=True,
            )
            for bucket, info in badges.items():
                rp  = info.get("reel_pct", 0)
                cp  = info.get("cible_pct", 0)
                ep  = info.get("ecart_pct", 0)
                cb  = ("#22c55e" if abs(ep) <= 5 else
                       "#f59e0b" if abs(ep) <= 15 else "#ef4444")
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:center;margin:3px 0">'
                    f'<span style="color:#94a3b8;font-size:12px">{bucket}</span>'
                    f'<span style="color:{cb};font-weight:700;font-size:13px">{rp:.1f}%</span>'
                    f'<span style="color:#334155;font-size:11px">/ {cp:.0f}%</span>'
                    f'</div>'
                    f'<div class="fs-bar-bg" style="margin-bottom:5px">'
                    f'<div class="fs-bar" style="width:{min(rp,100):.1f}%;'
                    f'background:{cb}"></div></div>',
                    unsafe_allow_html=True,
                )

        # Alertes (max 3)
        if alertes:
            st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
            for a in alertes[:3]:
                alerte_box(a["message"], a["couleur"])

    # ── Donut bas de page ──────────────────────────────────────────────────────
    if rept:
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
            legend=dict(bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#94a3b8", size=11)),
            paper_bgcolor="#0a0a14", plot_bgcolor="#0a0a14",
            font_color="#f1f5f9",
            margin=dict(t=20, b=20, l=0, r=0),
            height=280,
            annotations=[dict(
                text=f"<b>{_dh(total_dep)}</b><br>"
                     f"<span style='font-size:11px'>dépenses</span>",
                x=0.5, y=0.5, font_size=14,
                showarrow=False, font_color="#f1f5f9",
            )],
        )
        st.plotly_chart(fig, use_container_width=True)
