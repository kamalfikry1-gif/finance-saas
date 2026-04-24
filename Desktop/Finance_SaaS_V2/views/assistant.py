"""
views/assistant.py — Coach Stratège : interface conversationnelle.

Architecture :
    • st.chat_message()  pour le fil de conversation
    • st.pills()         pour les réponses rapides (quick replies)
    • Formulaires inline dans le chat pour les simulations
    • Toute la logique mathématique reste dans core/assistant_engine.py

Session state :
    chat_node     — id du nœud actif (str, default "root")
    chat_messages — historique [{role, text}]  (greeting exclu — toujours dynamique)
    chat_inputs   — paramètres de simulation (dict)
    chat_result   — résultat resolver en cache (dict | None)
"""

from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.cards import (
    fs_card, alerte_box,
)
from components.charts import _gauge
from components.design_tokens import T
from components.sidebar import _generer_mois_options
from core.assistant_engine import AssistantEngine, RenderType
from core.cache import invalider as _invalider_cache
from components.helpers import dh as _dh, pct as _pct

_ENGINE = AssistantEngine()


# ─────────────────────────────────────────────────────────────────────────────
# HELPER PLOTLY (inchangé)
# ─────────────────────────────────────────────────────────────────────────────

def _playout(**kwargs) -> dict:
    base = dict(
        paper_bgcolor=T.BG_PAGE,
        plot_bgcolor =T.BG_PAGE,
        font_color   =T.TEXT_HIGH,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=T.TEXT_MED)),
        xaxis=dict(gridcolor=T.BORDER, zerolinecolor=T.BORDER_MED),
        yaxis=dict(gridcolor=T.BORDER, zerolinecolor=T.BORDER_MED),
        margin=dict(t=24, b=40, l=0, r=0),
    )
    base.update(kwargs)
    return base


def _section_label(text: str) -> None:
    st.markdown(
        f"<div style='color:{T.TEXT_LOW};font-size:10px;font-weight:700;"
        f"text-transform:uppercase;letter-spacing:2px;margin:20px 0 12px;"
        f"padding-left:2px'>{text}</div>",
        unsafe_allow_html=True,
    )


def _divider_line() -> None:
    st.markdown(
        f"<hr style='border:none;border-top:1px solid {T.BORDER};margin:20px 0'>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RENDERERS DE RÉSULTATS — INCHANGÉS (logique mathématique protégée)
# ─────────────────────────────────────────────────────────────────────────────

def _render_repartition(result: dict, ctx: dict) -> None:
    rept = result.get("rept", [])
    if not rept:
        st.info("Aucune dépense enregistrée ce mois.")
        return

    from components.cards import CAT_COLORS
    df_r = pd.DataFrame(rept)

    cl, cr = st.columns([1, 1])
    with cl:
        fig = px.pie(
            df_r, values="Total_DH", names="Categorie",
            hole=0.6, color_discrete_sequence=CAT_COLORS,
        )
        fig.update_traces(
            textposition="outside", textfont_size=11,
            hovertemplate="%{label}<br>%{value:,.0f} DH<br>%{percent}",
        )
        total = df_r["Total_DH"].sum()
        fig.update_layout(
            showlegend=False,
            **_playout(height=300, margin=dict(t=20, b=20, l=0, r=0)),
            annotations=[dict(
                text=f"<b>{_dh(total)}</b>",
                x=0.5, y=0.5, font_size=14, showarrow=False,
                font_color=T.TEXT_HIGH,
            )],
        )
        st.plotly_chart(fig, use_container_width=True)

    with cr:
        res_sous  = ctx["_q"]("detail_sous_categories", mois=ctx["mois_sel"])
        sous_data = res_sous.get("resultat", [])
        sous_par_cat: dict = {}
        for sc in sous_data:
            sous_par_cat.setdefault(sc["Categorie"], []).append(sc)

        for i, row in enumerate(rept):
            cat    = row["Categorie"]
            couleur = CAT_COLORS[i % len(CAT_COLORS)]
            amt    = _dh(row["Total_DH"])
            sous   = sous_par_cat.get(cat, [])
            with st.expander(f"**{cat}** · {amt} · {row['Poids_Pct']:.1f}%", expanded=False):
                for sc in sous:
                    sc_pct = sc["Total_DH"] / (row["Total_DH"] or 1) * 100
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;"
                        f"padding:4px 0;border-bottom:1px solid {T.BORDER_MED}'>"
                        f"<span style='color:{T.TEXT_MED};font-size:12px'>{sc['Sous_Categorie']}</span>"
                        f"<span style='color:{couleur};font-size:12px;font-weight:700'>"
                        f"{_dh(sc['Total_DH'])} "
                        f"<span style='color:{T.TEXT_LOW};font-weight:400'>({sc_pct:.0f}%)</span></span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )


def _render_top_depenses(result: dict, ctx: dict) -> None:
    from components.cards import CAT_COLORS
    data = result.get("data", [])
    if not data:
        st.info("Aucune dépense à afficher.")
        return

    top_n = st.slider("Nombre de dépenses", 5, 20, 10, key="ast_top_n")
    df    = pd.DataFrame(data[:top_n])
    fig   = px.bar(
        df, x="Montant", y="Libelle", orientation="h",
        color="Poids_vs_Revenus_Pct",
        color_continuous_scale=[T.SUCCESS, T.WARNING, T.DANGER],
        text="Montant",
        hover_data=["Categorie", "Poids_vs_Revenus_Pct"],
    )
    fig.update_traces(texttemplate="%{text:,.0f} DH", textposition="outside")
    fig.update_layout(**_playout(
        xaxis_title="Montant (DH)", yaxis_title="",
        coloraxis_colorbar=dict(title="% Rev."),
        height=max(300, top_n * 34),
        margin=dict(t=20, b=20, r=80),
    ))
    st.plotly_chart(fig, use_container_width=True)


def _render_evolution(result: dict, ctx: dict) -> None:
    data = result.get("data", [])
    if not data:
        st.info("Pas encore assez d'historique — revenez le mois prochain.")
        return

    df  = pd.DataFrame(data)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["Mois"], y=df["Revenus"],
                         name="Revenus", marker_color=T.SUCCESS, opacity=0.85))
    fig.add_trace(go.Bar(x=df["Mois"], y=df["Depenses"],
                         name="Dépenses", marker_color=T.DANGER, opacity=0.85))
    fig.add_trace(go.Scatter(x=df["Mois"], y=df["Solde"],
                              name="Solde net", mode="lines+markers",
                              line=dict(color=T.PRIMARY, width=2),
                              marker=dict(size=7, symbol="circle")))
    fig.update_layout(**_playout(barmode="group", xaxis_title="", yaxis_title="DH", height=360))
    st.plotly_chart(fig, use_container_width=True)


def _render_tendances_jours(result: dict, ctx: dict) -> None:
    data = result.get("data", [])
    if not data:
        st.info("Pas encore assez de données pour ce mois.")
        return

    df = pd.DataFrame(data)
    cl, cr = st.columns(2)
    for col_c, y_col, titre, scale in [
        (cl, "Total_DH",   "Total DH / jour",        [T.BG_OVERLAY, T.PRIMARY]),
        (cr, "Moyenne_DH", "Moyenne DH / opération",  [T.BG_OVERLAY, T.SUCCESS]),
    ]:
        with col_c:
            fig = px.bar(df, x="Jour_Nom", y=y_col, color=y_col, text=y_col,
                         color_continuous_scale=scale)
            fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig.update_layout(**_playout(
                title=titre, xaxis_title="", yaxis_title="DH",
                height=300, showlegend=False, margin=dict(t=40, b=20),
            ))
            st.plotly_chart(fig, use_container_width=True)


def _render_epargne(result: dict, ctx: dict) -> None:
    cumul     = result.get("cumul", 0)
    objectifs = result.get("objectifs", [])
    audit     = ctx.get("audit")

    col_ep, col_obj = st.columns(2)
    with col_ep:
        fs_card("Épargne cumulée", _dh(cumul), "historique total", T.PRIMARY)
    with col_obj:
        fs_card("Objectifs actifs", str(len(objectifs)),
                "en cours", T.SUCCESS if objectifs else T.TEXT_LOW)

    if not objectifs:
        st.info("Aucun objectif actif. Lance la simulation depuis le thème Simuler.")
        return

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    for obj in objectifs:
        prog = obj.get("progression_pct", 0)
        cp   = T.SUCCESS if prog >= 80 else T.WARNING if prog >= 50 else T.PRIMARY
        st.markdown(
            f'<div style="background:{T.BG_CARD};border-radius:{T.RADIUS_MD};'
            f'padding:16px 20px;border-left:2px solid {cp};margin-bottom:10px;'
            f'border:1px solid {T.BORDER};border-left:2px solid {cp}">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:8px">'
            f'<span style="color:{T.TEXT_HIGH};font-weight:700">{obj["Nom"]}</span>'
            f'<span style="color:{cp};font-weight:900;font-size:17px">{prog:.1f}%</span>'
            f'</div>'
            f'<div style="background:{T.BG_PAGE};border-radius:{T.RADIUS_PILL};height:5px;'
            f'overflow:hidden;margin-bottom:8px">'
            f'<div style="width:{min(prog,100):.1f}%;height:5px;'
            f'background:{cp};border-radius:{T.RADIUS_PILL}"></div></div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px">'
            f'{obj["Montant_Cible"]:,.0f} DH · échéance {obj["Date_Cible"]} · '
            f'manque {obj.get("manque_dh",0):,.0f} DH</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if audit and st.button("Abandonner", key=f"ab_{obj['id']}", type="secondary"):
            audit.abandonner_objectif(obj["id"])
            _invalider_cache()
            st.session_state.chat_result = None
            st.rerun()


def _render_alertes_budget(result: dict, ctx: dict) -> None:
    alertes = result.get("alertes", [])
    bvr     = result.get("bvr", [])
    badges  = result.get("badges", {})

    if badges:
        _section_label("Plan 50 / 30 / 20")
        gcols = st.columns(len(badges))
        for i, (bucket, info) in enumerate(badges.items()):
            with gcols[i]:
                st.plotly_chart(
                    _gauge(info.get("reel_pct", 0), info.get("cible_pct", 0), bucket),
                    use_container_width=True, key=f"ast_gauge_{bucket}",
                )

    if alertes:
        _section_label(f"🚨 {len(alertes)} alerte(s)")
        for a in alertes:
            alerte_box(a["message"], a["couleur"])
    else:
        st.success("✅ Aucun plafond dépassé ce mois — bonne gestion.")

    if bvr:
        _section_label("Budget vs Réel")
        df = pd.DataFrame(bvr)
        if not df.empty and "Budget_DH" in df.columns:
            fig = go.Figure()
            fig.add_trace(go.Bar(name="Budget", x=df["Sous_Categorie"], y=df["Budget_DH"],
                                 marker_color=T.PRIMARY, opacity=0.4))
            fig.add_trace(go.Bar(name="Réel", x=df["Sous_Categorie"], y=df["Reel_DH"],
                                 marker_color=df["Taux_Consommation_Pct"].apply(
                                     lambda p: T.DANGER if p > 100 else T.WARNING if p > 80 else T.SUCCESS
                                 )))
            fig.update_layout(**_playout(barmode="group", height=300,
                                         xaxis_title="", margin=dict(t=10, b=60)))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aucun plafond défini — configure-en dans la page Plafonds.")


def _render_comparaison(result: dict, ctx: dict) -> None:
    data = result.get("data", [])
    if not data:
        st.info("Pas encore assez d'historique pour comparer.")
        return

    df    = pd.DataFrame(data)
    df_nn = df.dropna(subset=["Ecart_Pct"]).copy()

    if not df_nn.empty:
        fig = px.bar(df_nn, x="Sous_Categorie", y="Ecart_Pct",
                     color="Ecart_Pct",
                     color_continuous_scale=[T.SUCCESS, T.BORDER_MED, T.DANGER],
                     text="Ecart_Pct",
                     hover_data=["Mois_Courant_DH", "Moyenne_Ref_DH"])
        fig.update_traces(texttemplate="%{text:+.1f}%", textposition="outside")
        fig.add_hline(y=0,   line_color=T.BORDER_MED)
        fig.add_hline(y=10,  line_dash="dash", line_color=T.DANGER,
                      annotation_text="+10% seuil hausse", annotation_font_color=T.DANGER)
        fig.add_hline(y=-10, line_dash="dash", line_color=T.SUCCESS,
                      annotation_text="-10% seuil baisse", annotation_font_color=T.SUCCESS)
        fig.update_layout(**_playout(xaxis_title="", yaxis_title="Écart (%)",
                                      height=320, showlegend=False, margin=dict(t=40, b=60)))
        st.plotly_chart(fig, use_container_width=True)

    hausses  = df[df["Tendance"] == "HAUSSE"]["Sous_Categorie"].tolist()
    nouveaux = df[df["Tendance"] == "NOUVEAU"]["Sous_Categorie"].tolist()
    if hausses:  st.warning(f"📈 Hausses détectées : {', '.join(hausses)}")
    if nouveaux: st.info(f"🆕 Nouveaux postes ce mois : {', '.join(nouveaux)}")


def _render_projection(result: dict, ctx: dict) -> None:
    proj    = result.get("proj", {})
    bilan   = result.get("bilan", {})
    charges = result.get("charges", [])

    p1, p2, p3, p4 = st.columns(4)
    with p1: fs_card("Mois écoulé",      _pct(proj.get("pct_mois_ecoule", 0)),
                     f"J{proj.get('jours_ecoules','?')}/{proj.get('jours_total','?')}", T.PRIMARY)
    with p2: fs_card("Rythme / jour",    _dh(proj.get("taux_journalier", 0)), "DH/jour", T.WARNING)
    with p3:
        pdh = proj.get("projection_fin_mois", 0)
        fs_card("Projection dépenses",   _dh(pdh), "fin de mois",
                T.SUCCESS if pdh <= bilan.get("revenus", 0) else T.DANGER)
    with p4:
        sp = proj.get("solde_projete", 0)
        fs_card("Solde projeté",         _dh(sp), "fin de mois",
                T.SUCCESS if sp >= 0 else T.DANGER)

    if charges:
        _section_label("🔁 Charges fixes détectées")
        df_c = pd.DataFrame(charges)
        if not df_c.empty:
            df_d = df_c[["Libelle", "Nb_Mois", "Montant_Moyen"]].copy()
            df_d.columns = ["Libellé", "Mois", "Moy. DH"]
            df_d["Moy. DH"] = df_d["Moy. DH"].map("{:,.0f}".format)
            st.dataframe(df_d, use_container_width=True, hide_index=True, height=200)


def _render_sim_impact(result: dict, ctx: dict) -> None:
    d      = result.get("data", {})
    inputs = result.get("inputs", {})
    if not d:
        st.error("Impossible d'exécuter la simulation.")
        return

    nb  = d.get("mois_pour_rembourser")
    sa  = d.get("solde_avec_projet", 0)
    h_p = int(inputs.get("mois_cibles", 12))
    cf  = T.SUCCESS if d.get("faisable") else T.DANGER

    c1, c2, c3 = st.columns(3)
    with c1: fs_card("Épargne moy./mois",   _dh(d.get("epargne_mensuelle_actuelle", 0)), "actuelle", T.PRIMARY)
    with c2: fs_card("Remboursement",        f"{nb} mois" if nb else "Impossible", "à rythme actuel", cf)
    with c3: fs_card(f"Solde dans {h_p} mois", _dh(sa), "avec projet", T.SUCCESS if sa >= 0 else T.DANGER)

    ep     = d.get("epargne_mensuelle_actuelle", 0)
    mr     = list(range(h_p + 1))
    m_proj = float(inputs.get("montant_projet", 0))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=mr, y=[ep * m for m in mr],
                              name="Sans projet",
                              line=dict(color=T.SUCCESS, width=2, dash="dot")))
    fig.add_trace(go.Scatter(x=mr, y=[max(0, ep * m - m_proj) for m in mr],
                              name="Avec projet",
                              line=dict(color=T.DANGER, width=2),
                              fill="tonexty", fillcolor=T.DANGER_GLO))
    fig.add_hline(y=0, line_color=T.BORDER_MED)
    fig.update_layout(**_playout(xaxis_title="Mois", yaxis_title="Épargne (DH)", height=280))
    st.plotly_chart(fig, use_container_width=True)

    if d.get("faisable"):
        st.success(f"✅ Projet faisable — remboursé en {nb} mois.")
    else:
        st.error("❌ Difficile à absorber au rythme d'épargne actuel.")


def _render_sim_objectif(result: dict, ctx: dict) -> None:
    d      = result.get("data", {})
    inputs = result.get("inputs", {})
    audit  = ctx.get("audit")
    if not d:
        st.error("Impossible d'exécuter la simulation.")
        return

    eff  = d.get("effort_mensuel_requis", 0)
    ce   = T.SUCCESS if d.get("atteignable") else T.DANGER
    nb_m = int(inputs.get("nb_mois", 24))

    c1, c2, c3 = st.columns(3)
    with c1: fs_card("Épargne actuelle",  _dh(d.get("epargne_actuelle_cumul", 0)), "cumul", T.PRIMARY)
    with c2: fs_card("Il manque",         _dh(d.get("manque_a_epargner", 0)), "pour l'objectif", T.WARNING)
    with c3: fs_card("Effort mensuel",    _dh(eff), "requis", ce)

    if d.get("atteignable"):
        st.success(f"✅ Objectif atteignable en {nb_m} mois.")
    else:
        ep_a = d.get("epargne_mensuelle_actuelle", 0)
        st.warning(
            f"⚠️ Effort requis ({eff:,.0f} DH) > épargne actuelle "
            f"({ep_a:,.0f} DH/mois). Allonge le délai ou réduis la cible."
        )

    for red in d.get("reductions_suggerees", []):
        st.markdown(
            f"- **{red['sous_categorie']}** — "
            f"économiser **{red['reduction_suggeree_15pct']:,.0f} DH** "
            f"(–15% sur {red['depense_actuelle']:,.0f} DH)"
        )

    if audit:
        _section_label("💾 Sauvegarder cet objectif")
        with st.form("ast_creer_obj"):
            nom_o = st.text_input("Nom de l'objectif", placeholder="Voyage Tokyo, PC Gaming…")
            cs1, cs2 = st.columns(2)
            with cs1:
                cible_s = st.number_input("Montant (DH)", min_value=100.0,
                                          value=float(inputs.get("cible_dh", 25000.0)), step=1000.0)
            with cs2:
                mois_opts = _generer_mois_options()
                date_s = st.selectbox(
                    "Mois cible",
                    [m["value"] for m in mois_opts[::-1]],
                    format_func=lambda v: datetime.strptime(v, "%m/%Y").strftime("%B %Y").capitalize(),
                )
            if st.form_submit_button("Créer l'objectif", use_container_width=True, type="primary"):
                if nom_o:
                    audit.creer_objectif_v2(nom_o, "EPARGNE", cible_s, date_s)
                    st.success(f"✅ '{nom_o}' créé — visible dans la page Objectif.")
                    _invalider_cache()
                    st.rerun()
                else:
                    st.warning("Renseigne un nom pour l'objectif.")


def _render_sim_crash(result: dict, ctx: dict) -> None:
    d      = result.get("data", {})
    inputs = result.get("inputs", {})
    if not d:
        st.error("Impossible d'exécuter la simulation.")
        return

    statut = d.get("statut", "FRAGILE")
    col_st = {"RESISTANT": T.SUCCESS, "FRAGILE": T.WARNING, "CRITIQUE": T.DANGER}.get(statut, T.PRIMARY)
    nb_c   = int(inputs.get("nb_mois_sans_revenu", 3))

    st.markdown(
        f"<div style='text-align:center;padding:32px 0;"
        f"background:{T.BG_CARD};border-radius:{T.RADIUS_LG};margin-bottom:16px;"
        f"border:1px solid {T.BORDER};border-top:2px solid {col_st}'>"
        f"<div style='font-size:48px;font-weight:900;color:{col_st};"
        f"letter-spacing:2px'>{statut}</div>"
        f"<div style='color:{T.TEXT_LOW};margin-top:8px;font-size:13px'>"
        f"Résistance : <b style='color:{col_st}'>{d.get('mois_de_resistance', 0)} mois</b></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1: fs_card("Solde actuel",    _dh(d.get("solde_actuel", 0)), "", T.PRIMARY)
    with c2: fs_card("Dép. moy./mois",  _dh(d.get("depenses_mensuelles_moyennes", 0)), "3 derniers mois", T.WARNING)
    with c3:
        mq = d.get("manque_prevu", 0)
        fs_card(f"Manque ({nb_c} mois)", _dh(mq), "", T.SUCCESS if mq == 0 else T.DANGER)

    dep = d.get("date_epuisement_estimee")
    if dep:
        st.info(f"📅 Solde épuisé estimé : **{dep}**")

    mois_res = min(d.get("mois_de_resistance", 0), 24)
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number",
        value=mois_res,
        number={"suffix": " mois", "font": {"size": 32, "color": T.TEXT_HIGH}},
        title={"text": "Mois de résistance", "font": {"color": T.TEXT_MED}},
        gauge={
            "axis":  {"range": [0, 24], "tickcolor": T.TEXT_LOW},
            "bar":   {"color": col_st},
            "bgcolor": T.BG_CARD,
            "threshold": {"line": {"color": T.PRIMARY, "width": 2}, "value": nb_c},
            "steps": [
                {"range": [0, 3],  "color": T.DANGER_GLO},
                {"range": [3, 6],  "color": T.WARNING_GLO},
                {"range": [6, 24], "color": T.SUCCESS_GLO},
            ],
        },
    ))
    fig_g.update_layout(height=220, paper_bgcolor=T.BG_PAGE, font_color=T.TEXT_HIGH,
                        margin=dict(t=40, b=0, l=40, r=40))
    st.plotly_chart(fig_g, use_container_width=True)


def _render_mes_objectifs(result: dict, ctx: dict) -> None:
    objectifs  = result.get("objectifs", [])
    audit      = ctx.get("audit")
    en_cours   = [o for o in objectifs if o.get("Statut") == "EN_COURS"]
    historique = [o for o in objectifs if o.get("Statut") != "EN_COURS"]

    if not en_cours:
        st.info("Aucun objectif actif. Lance la simulation depuis le thème Simuler.")
    else:
        for obj in en_cours:
            prog = obj.get("progression_pct", 0)
            cp   = T.SUCCESS if prog >= 80 else T.WARNING if prog >= 50 else T.PRIMARY
            st.markdown(
                f'<div style="background:{T.BG_CARD};border-radius:{T.RADIUS_MD};'
                f'padding:16px 20px;border:1px solid {T.BORDER};'
                f'border-left:2px solid {cp};margin-bottom:10px">'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:center;margin-bottom:8px">'
                f'<span style="color:{T.TEXT_HIGH};font-weight:700">{obj["Nom"]}</span>'
                f'<span style="color:{cp};font-weight:900;font-size:17px">{prog:.1f}%</span>'
                f'</div>'
                f'<div style="background:{T.BG_PAGE};border-radius:{T.RADIUS_PILL};height:5px;'
                f'overflow:hidden;margin-bottom:8px">'
                f'<div style="width:{min(prog,100):.1f}%;height:5px;'
                f'background:{cp};border-radius:{T.RADIUS_PILL}"></div></div>'
                f'<div style="color:{T.TEXT_LOW};font-size:11px">'
                f'{obj["Montant_Cible"]:,.0f} DH · {obj["Date_Cible"]} · '
                f'manque {obj.get("manque_dh",0):,.0f} DH</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if audit and st.button("Abandonner", key=f"mes_ab_{obj['id']}", type="secondary"):
                audit.abandonner_objectif(obj["id"])
                _invalider_cache()
                st.session_state.chat_result = None
                st.rerun()

    if historique:
        with st.expander("Historique"):
            for obj in historique:
                st.markdown(f"- **{obj['Nom']}** · {obj['Montant_Cible']:,.0f} DH · {obj.get('Statut', '')}")


def _render_burn_rate(result: dict, ctx: dict) -> None:
    burn       = result.get("burn_rate", 0)
    depenses   = result.get("depenses", 0)
    revenus    = result.get("revenus", 0)
    projection = result.get("projection", 0)
    je         = result.get("jours_ecoules", 0)
    jt         = result.get("jours_total", 30)
    jr         = result.get("jours_restants", 0)
    solde      = result.get("solde", 0)
    date_epuis = result.get("date_epuis")
    pct_mois   = je / jt * 100 if jt else 0
    pct_budget = projection / revenus * 100 if revenus else 0
    col_proj   = T.SUCCESS if projection <= revenus * 0.85 else T.WARNING if projection <= revenus else T.DANGER

    c1, c2, c3, c4 = st.columns(4)
    with c1: fs_card("Burn Rate",            f"{burn:,.0f} DH/j",  f"{je}j écoulés / {jt}j", T.WARNING)
    with c2: fs_card("Dépenses à ce jour",   _dh(depenses),        "ce mois",                 T.PRIMARY)
    with c3: fs_card("Projection fin mois",  _dh(projection),      "",                        col_proj)
    with c4: fs_card("Jours restants",       str(jr),              "dans le mois",
                     T.SUCCESS if jr > 7 else T.DANGER)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    _section_label(f"Mois écoulé — {pct_mois:.0f}%")
    st.markdown(
        f"<div style='background:{T.BG_CARD};border-radius:{T.RADIUS_PILL};height:10px;"
        f"overflow:hidden;margin-bottom:16px;border:1px solid {T.BORDER}'>"
        f"<div style='width:{min(pct_mois,100):.1f}%;height:10px;"
        f"background:linear-gradient(90deg,{T.PRIMARY},{T.WARNING});"
        f"border-radius:{T.RADIUS_PILL}'></div></div>",
        unsafe_allow_html=True,
    )
    _section_label(f"Projection vs Revenus — {pct_budget:.0f}%")
    st.markdown(
        f"<div style='background:{T.BG_CARD};border-radius:{T.RADIUS_PILL};height:10px;"
        f"overflow:hidden;margin-bottom:16px;border:1px solid {T.BORDER}'>"
        f"<div style='width:{min(pct_budget,100):.1f}%;height:10px;"
        f"background:{col_proj};border-radius:{T.RADIUS_PILL}'></div></div>",
        unsafe_allow_html=True,
    )

    fig = go.Figure()
    x_all = list(range(1, jt + 1))
    fig.add_trace(go.Scatter(x=x_all[:je], y=[depenses / je * d for d in x_all[:je]],
                              name="Réel", line=dict(color=T.PRIMARY, width=2), mode="lines"))
    fig.add_trace(go.Scatter(x=x_all[je - 1:], y=[depenses / je * d for d in x_all[je - 1:]],
                              name="Projection", line=dict(color=T.WARNING, width=2, dash="dot"),
                              mode="lines"))
    fig.add_hline(y=revenus, line_dash="dash", line_color=T.SUCCESS,
                  annotation_text="Revenus", annotation_font_color=T.SUCCESS)
    fig.update_layout(**_playout(xaxis_title="Jour du mois", yaxis_title="Dépenses cumulées (DH)", height=280))
    st.plotly_chart(fig, use_container_width=True)

    if date_epuis:
        st.info(f"📅 À ce rythme, ton solde ({_dh(solde)}) sera épuisé vers le **{date_epuis}**.")
    if projection > revenus:
        st.error(f"⚠️ Tu vas dépenser **{_dh(projection - revenus)} de plus** que tes revenus ce mois.")


def _render_sim_interets(result: dict, ctx: dict) -> None:
    series         = result.get("series", [])
    capital_final  = result.get("capital_final", 0)
    total_investi  = result.get("total_investi", 0)
    interets_gen   = result.get("interets_gen", 0)
    multiplicateur = result.get("multiplicateur", 1)
    inputs         = result.get("inputs", {})

    c1, c2, c3, c4 = st.columns(4)
    with c1: fs_card("Capital final",     _dh(capital_final), "à terme",       T.SUCCESS)
    with c2: fs_card("Total investi",     _dh(total_investi), "de ta poche",   T.PRIMARY)
    with c3: fs_card("Intérêts générés",  _dh(interets_gen),  "gratuits",      T.WARNING)
    with c4: fs_card("Multiplicateur",    f"×{multiplicateur:.1f}", "sur ton épargne",
                     T.SUCCESS if multiplicateur >= 2 else T.WARNING)

    if not series:
        return

    df = pd.DataFrame(series)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["annee"], y=df["avec_interets"],
                              name="Avec intérêts composés",
                              line=dict(color=T.SUCCESS, width=3),
                              fill="tonexty", fillcolor=T.SUCCESS_GLO,
                              mode="lines+markers", marker=dict(size=5)))
    fig.add_trace(go.Scatter(x=df["annee"], y=df["sans_interets"],
                              name="Sans intérêts (épargne simple)",
                              line=dict(color=T.TEXT_LOW, width=2, dash="dot"),
                              mode="lines"))
    fig.update_layout(**_playout(xaxis_title="Années", yaxis_title="Capital (DH)", height=320))
    st.plotly_chart(fig, use_container_width=True)

    _section_label("Projection année par année")
    df_disp = df.copy()
    df_disp.columns = ["Année", "Avec intérêts (DH)", "Sans intérêts (DH)", "Intérêts générés (DH)"]
    for col in ["Avec intérêts (DH)", "Sans intérêts (DH)", "Intérêts générés (DH)"]:
        df_disp[col] = df_disp[col].map("{:,.0f}".format)
    st.dataframe(df_disp, use_container_width=True, hide_index=True, height=220)


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCHER (inchangé)
# ─────────────────────────────────────────────────────────────────────────────

_RENDERERS = {
    RenderType.REPARTITION:     _render_repartition,
    RenderType.TOP_DEPENSES:    _render_top_depenses,
    RenderType.EVOLUTION:       _render_evolution,
    RenderType.TENDANCES_JOURS: _render_tendances_jours,
    RenderType.EPARGNE:         _render_epargne,
    RenderType.ALERTES_BUDGET:  _render_alertes_budget,
    RenderType.COMPARAISON:     _render_comparaison,
    RenderType.PROJECTION:      _render_projection,
    RenderType.SIM_IMPACT:      _render_sim_impact,
    RenderType.SIM_OBJECTIF:    _render_sim_objectif,
    RenderType.SIM_CRASH:       _render_sim_crash,
    RenderType.MES_OBJECTIFS:   _render_mes_objectifs,
    RenderType.BURN_RATE:       _render_burn_rate,
    RenderType.SIM_INTERETS:    _render_sim_interets,
}


def _dispatch_result(result: dict, ctx: dict) -> None:
    rtype    = result.get("type", "ERROR")
    renderer = _RENDERERS.get(rtype)
    if renderer:
        renderer(result, ctx)
    else:
        st.error(f"Renderer inconnu : {rtype}\n{result.get('message', '')}")


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — ÉTAT & NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

def _chat_init() -> None:
    ss = st.session_state
    if "chat_node"     not in ss: ss.chat_node     = "root"
    if "chat_messages" not in ss: ss.chat_messages  = []
    if "chat_inputs"   not in ss: ss.chat_inputs    = {}
    if "chat_result"   not in ss: ss.chat_result    = None


def _chat_go_theme(node_id: str, user_label: str, coach_reply: str) -> None:
    ss = st.session_state
    ss.chat_messages.append({"role": "user",      "text": user_label})
    ss.chat_messages.append({"role": "assistant",  "text": coach_reply})
    ss.chat_node    = node_id
    ss.chat_inputs  = {}
    ss.chat_result  = None
    st.rerun()


def _chat_go_leaf(node_id: str, user_label: str) -> None:
    ss = st.session_state
    ss.chat_messages.append({"role": "user", "text": user_label})
    ss.chat_node   = node_id
    ss.chat_inputs = {}
    ss.chat_result = None
    st.rerun()


def _chat_back() -> None:
    ss      = st.session_state
    node_id = ss.chat_node
    is_leaf = _ENGINE.is_leaf(node_id)
    n_pop   = 1 if is_leaf else 2
    ss.chat_messages = ss.chat_messages[:-n_pop] if len(ss.chat_messages) >= n_pop else []
    parent           = _ENGINE.get_parent_id(node_id)
    ss.chat_node     = parent if parent else "root"
    ss.chat_inputs   = {}
    ss.chat_result   = None
    st.rerun()


def _chat_reset() -> None:
    ss = st.session_state
    ss.chat_node     = "root"
    ss.chat_messages = []
    ss.chat_inputs   = {}
    ss.chat_result   = None
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — PERSONA & TEXTES (Stratège / Sérieux)
# ─────────────────────────────────────────────────────────────────────────────

_THEME_INTRO = {
    "A": "Analyse en cours. Cinq angles disponibles — lequel t'intéresse ?",
    "B": "Pilotage budgétaire. Sur quoi veux-tu porter le regard ?",
    "C": "Simulations. Testons tes hypothèses avant d'agir.",
}

_FORM_INTRO = {
    "C1": "Pour mesurer l'impact réel sur ton épargne, j'ai besoin du montant du projet et de ton horizon de remboursement.",
    "C2": "Pour calculer l'effort mensuel exact, indique le montant cible et le délai que tu te fixes.",
    "C3": "Je vais simuler un arrêt total de revenus. Combien de mois veux-tu tester ?",
    "C5": "Simulation intérêts composés. Renseigne ton capital de départ, ton versement mensuel et l'horizon d'investissement.",
}


def _build_greeting(ctx: dict) -> str:
    bilan    = ctx.get("bilan", {})
    solde    = bilan.get("solde", 0)
    revenus  = bilan.get("revenus", 0)
    depenses = abs(bilan.get("depenses", 0))
    mois_lbl = ctx.get("mois_lbl", "")
    message  = ctx.get("message", "")
    sign     = "+" if solde >= 0 else ""

    username = st.session_state.get("username", "").strip().capitalize()
    salut    = f"Bonjour {username}." if username else "Bonjour."

    return (
        f"{salut} **{mois_lbl}** — "
        f"Solde net : **{sign}{_dh(solde)}** · "
        f"Revenus : {_dh(revenus)} · "
        f"Dépenses : {_dh(depenses)}.\n\n"
        f"*{message}*\n\n"
        f"Sur quoi veux-tu travailler ?"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHAT — COMPOSANTS UI
# ─────────────────────────────────────────────────────────────────────────────

def _render_quick_replies(node_id: str) -> None:
    children      = _ENGINE.get_children(node_id)
    options       = [c["label"] for c in children]
    label_to_child = {c["label"]: c for c in children}

    sel = st.pills(
        "Réponses rapides",
        options,
        label_visibility="collapsed",
        key=f"qr_{node_id}",
    )

    if sel:
        child    = label_to_child[sel]
        child_id = child["id"]
        if _ENGINE.is_leaf(child_id):
            _chat_go_leaf(child_id, sel)
        else:
            reply = _THEME_INTRO.get(child_id, "Voici les options disponibles.")
            _chat_go_theme(child_id, sel, reply)


def _render_inline_form(node: dict, node_id: str) -> None:
    intro = _FORM_INTRO.get(
        node_id,
        "Pour calculer cela avec précision, j'ai besoin de quelques paramètres.",
    )

    with st.chat_message("assistant", avatar="🧠"):
        st.markdown(intro)

    spec = node.get("input_spec", {})
    if not spec:
        return

    with st.container():
        st.markdown(
            f"<div style='background:{T.BG_CARD};border:1px solid {T.BORDER};"
            f"border-radius:{T.RADIUS_LG};padding:20px 24px;margin:12px 0 20px'>",
            unsafe_allow_html=True,
        )
        with st.form(f"chat_form_{node_id}"):
            fields = list(spec.items())
            # Render number inputs in a row, sliders full-width
            numbers = [(k, v) for k, v in fields if v.get("type") == "number"]
            sliders = [(k, v) for k, v in fields if v.get("type") == "slider"]

            if numbers:
                cols = st.columns(len(numbers))
                for col, (fk, fc) in zip(cols, numbers):
                    with col:
                        st.number_input(
                            fc.get("label", fk),
                            min_value=float(fc.get("min", 0)),
                            max_value=float(fc.get("max", 1_000_000)),
                            value=float(st.session_state.chat_inputs.get(fk, fc.get("default", 0))),
                            step=float(fc.get("step", 1)),
                            format="%.0f",
                            key=f"cf_{node_id}_{fk}",
                        )

            for fk, fc in sliders:
                st.slider(
                    fc.get("label", fk),
                    min_value=int(fc.get("min", 1)),
                    max_value=int(fc.get("max", 60)),
                    value=int(st.session_state.chat_inputs.get(fk, fc.get("default", 1))),
                    step=int(fc.get("step", 1)),
                    key=f"cf_{node_id}_{fk}",
                )

            submitted = st.form_submit_button(
                "Calculer →", use_container_width=True, type="primary",
            )

        st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        inputs = {}
        for fk, fc in spec.items():
            inputs[fk] = st.session_state.get(f"cf_{node_id}_{fk}", fc.get("default", 0))
        st.session_state.chat_inputs = inputs
        st.session_state.chat_result = None
        st.rerun()


def _render_result_block(node_id: str, ctx: dict) -> None:
    if st.session_state.chat_result is None:
        with st.spinner("Calcul en cours…"):
            st.session_state.chat_result = _ENGINE.resolve(
                node_id, ctx, st.session_state.chat_inputs,
            )

    result = st.session_state.chat_result

    with st.chat_message("assistant", avatar="🧠"):
        st.markdown(result.get("message", ""), unsafe_allow_html=True)
        st.markdown(
            f"<hr style='border:none;border-top:1px solid {T.BORDER};margin:16px 0'>",
            unsafe_allow_html=True,
        )
        _dispatch_result(result, ctx)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    if st.button("↺ Nouvelle question", key="chat_new_q",
                 use_container_width=True, type="secondary"):
        _chat_reset()


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def render(ctx: dict) -> None:
    _chat_init()

    # ── Greeting — toujours dynamique (jamais stocké dans chat_messages) ──────
    with st.chat_message("assistant", avatar="🧠"):
        st.markdown(_build_greeting(ctx))

    # ── Historique de la conversation ─────────────────────────────────────────
    for msg in st.session_state.chat_messages:
        role   = msg["role"]
        avatar = "🧠" if role == "assistant" else "👤"
        with st.chat_message(role, avatar=avatar):
            st.markdown(msg["text"])

    # ── Élément interactif courant ────────────────────────────────────────────
    node_id     = st.session_state.chat_node
    node        = _ENGINE.get_node(node_id)
    is_leaf     = _ENGINE.is_leaf(node_id)
    needs_input = node.get("requires_input", False)
    has_inputs  = bool(st.session_state.chat_inputs)

    if not is_leaf:
        _render_quick_replies(node_id)

    elif needs_input and not has_inputs:
        _render_inline_form(node, node_id)

    else:
        _render_result_block(node_id, ctx)

    # ── Barre de navigation (visible dès qu'on a navigué) ────────────────────
    if st.session_state.chat_messages:
        st.markdown(
            f"<hr style='border:none;border-top:1px solid {T.BORDER};margin:28px 0 12px'>",
            unsafe_allow_html=True,
        )
        c_back, c_reset, _ = st.columns([1, 1, 5])
        with c_back:
            if st.button("← Retour", key="chat_back", use_container_width=True):
                _chat_back()
        with c_reset:
            if st.button("⌂ Accueil", key="chat_home",
                         use_container_width=True, type="secondary"):
                _chat_reset()
