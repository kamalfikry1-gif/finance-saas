"""
views/objectif.py — Objectifs financiers.
Tab 1 — Dépense : réduire une catégorie sous un seuil cible.
Tab 2 — Épargne : accumuler un montant d'ici une deadline (vacances, voiture…).
"""

import logging
from datetime import date, datetime
import streamlit as st
from components.design_tokens import T
from components.helpers import dh as _dh, render_page_header
from core.cache import (invalider as _invalider_cache,
                        get_objectifs_type as _get_objs,
                        get_depenses_mois as _get_dep,
                        get_categories as _get_cats)

logger = logging.getLogger(__name__)

# ── Palette icônes prédéfinis pour les objectifs épargne ──────────────────────
_ICONES_EPARGNE = ["🏖️", "🚗", "🏠", "📱", "🎓", "💍", "✈️", "🏋️", "🎸", "💼", "🛡️", "🎯"]
_COULEURS       = [T.PRIMARY, T.SUCCESS, T.WARNING, T.DANGER,
                   T.BLUE, T.PURPLE, T.CAT_PALETTE[6], T.CAT_PALETTE[7]]


def _progress_bar(pct: float, couleur: str) -> str:
    pct = min(pct, 100)
    return (
        f'<div style="background:{T.BORDER};border-radius:{T.RADIUS_PILL};'
        f'height:8px;overflow:hidden;margin:8px 0">'
        f'<div style="width:{pct:.1f}%;height:100%;'
        f'background:{couleur};border-radius:{T.RADIUS_PILL};'
        f'transition:width 0.6s ease"></div></div>'
    )


def _get_depenses_cat_mois(audit, categorie: str, mois: str) -> float:
    try:
        depenses = _get_dep(audit, mois, audit.user_id)
        return sum(v for (cat, _), v in depenses.items() if cat == categorie)
    except Exception:
        return 0.0


def _get_categories_out(audit) -> list:
    try:
        return [c for c in _get_cats(audit, audit.user_id)
                if c not in {"Finances & Crédits", "Finances Credits", "Divers"}]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# TAB DÉPENSE
# ─────────────────────────────────────────────────────────────────────────────

def _tab_depense(audit, mois_sel: str, mois_lbl: str) -> None:
    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:13px;margin-bottom:20px">'
        f'Fixez un plafond aspirationnel pour une catégorie. '
        f'Différent du plafond d\'alerte — ici c\'est votre ambition personnelle de réduction.</p>',
        unsafe_allow_html=True,
    )

    # ── Formulaire création ───────────────────────────────────────────────────
    with st.expander("➕ Nouvel objectif de dépense",
                     expanded=st.session_state.get("od_open", False)):
        cats = _get_categories_out(audit)
        d1, d2, d3 = st.columns(3)
        with d1:
            nom_dep = st.text_input("Nom de l'objectif", placeholder="Ex: Réduire les restos",
                                    key="od_nom")
        with d2:
            cat_dep = st.selectbox("Catégorie cible", cats, key="od_cat") if cats else None
        with d3:
            cible_dep = st.number_input("Cible max (DH/mois)", min_value=0.0,
                                        step=100.0, format="%.0f", key="od_cible")

        d4, d5 = st.columns(2)
        with d4:
            icone_dep = st.selectbox("Icône", ["📉", "✂️", "🎯", "💡", "🔻"], key="od_icone")
        with d5:
            date_cible_dep = st.date_input("Objectif atteint avant le",
                                           value=date(date.today().year, 12, 31),
                                           key="od_date")

        if st.button("Créer l'objectif", key="od_save", type="primary"):
            if not nom_dep.strip():
                st.warning("Nom requis")
            elif cible_dep <= 0:
                st.warning("Cible > 0 DH requise")
            else:
                audit.creer_objectif_v2(
                    nom=nom_dep.strip(), type_obj="DEPENSE",
                    montant_cible=cible_dep, date_cible=str(date_cible_dep),
                    categorie=cat_dep or "", icone=icone_dep, couleur=T.WARNING,
                )
                st.session_state.od_open = False
                _invalider_cache()
                st.success("✅ Objectif créé")
                st.rerun()

    # ── Liste objectifs dépense ───────────────────────────────────────────────
    objectifs = _get_objs(audit, "DEPENSE", audit.user_id)
    if not objectifs:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:32px;text-align:center;margin-top:16px">'
            f'<div style="font-size:28px;margin-bottom:8px">✂️</div>'
            f'<div style="color:{T.TEXT_MED};font-size:13px;margin-bottom:12px">'
            f'Aucun objectif de réduction. Créez-en un pour suivre vos efforts !</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("➕ Créer mon premier objectif de dépense", key="od_open_btn",
                     type="primary", use_container_width=True):
            st.session_state.od_open = True
            st.rerun()
        return

    for obj in objectifs:
        oid      = obj["id"]
        nom      = obj["Nom"]
        icone    = obj.get("Icone") or "📉"
        cat      = obj.get("Categorie") or ""
        cible    = float(obj["Montant_Cible"])
        date_c   = obj.get("Date_Cible", "")[:10]
        couleur  = obj.get("Couleur") or T.WARNING

        depense_actuelle = _get_depenses_cat_mois(audit, cat, mois_sel) if cat else 0.0
        ecart = cible - depense_actuelle
        pct   = (depense_actuelle / cible * 100) if cible > 0 else 0
        ok    = depense_actuelle <= cible
        col_stat = T.SUCCESS if ok else T.DANGER
        statut_txt = f"✅ Dans la cible ({_dh(ecart)} de marge)" if ok else f"⚠️ Dépassé de {_dh(-ecart)}"

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-left:3px solid {couleur};'
            f'border-radius:{T.RADIUS_MD};padding:16px;margin-bottom:10px">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
            f'<span style="font-size:22px">{icone}</span>'
            f'<div style="flex:1">'
            f'<div style="color:{T.TEXT_HIGH};font-weight:700;font-size:14px">{nom}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px">{cat} · avant {date_c}</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div style="color:{col_stat};font-weight:700;font-size:13px">{statut_txt}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px">'
            f'Ce mois : {_dh(depense_actuelle)} / cible {_dh(cible)}</div>'
            f'</div></div>'
            f'{_progress_bar(pct, col_stat)}'
            f'</div>',
            unsafe_allow_html=True,
        )

        if st.button("🗑️ Supprimer", key=f"od_del_{oid}"):
            audit.supprimer_objectif(oid)
            _invalider_cache()
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB ÉPARGNE
# ─────────────────────────────────────────────────────────────────────────────

def _tab_epargne(audit) -> None:
    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:13px;margin-bottom:20px">'
        f'Suivez vos projets d\'épargne : vacances, voiture, urgence, … '
        f'Mettez à jour le montant épargné à votre rythme.</p>',
        unsafe_allow_html=True,
    )

    # ── Formulaire création ───────────────────────────────────────────────────
    _COULEUR_NOMS = {
        T.PRIMARY: "Bleu-vert", T.SUCCESS: "Vert", T.WARNING: "Ambre",
        T.DANGER: "Rouge", T.BLUE: "Bleu", T.PURPLE: "Violet",
        T.CAT_PALETTE[6]: "Couleur 7", T.CAT_PALETTE[7]: "Couleur 8",
    }

    with st.expander("➕ Nouvel objectif d'épargne",
                     expanded=st.session_state.get("oe_open", False)):
        e1, e2 = st.columns(2)
        with e1:
            nom_ep = st.text_input("Nom du projet", placeholder="Ex: Vacances Turquie",
                                   key="oe_nom")
            icone_ep = st.selectbox("Icône", _ICONES_EPARGNE, key="oe_icone")
        with e2:
            cible_ep = st.number_input("Montant cible (DH)", min_value=1.0,
                                       step=500.0, format="%.0f", key="oe_cible")
            date_ep  = st.date_input("Date cible",
                                     value=date(date.today().year + 1, 6, 1),
                                     key="oe_date")

        couleur_ep = st.selectbox(
            "Couleur", _COULEURS,
            format_func=lambda c: _COULEUR_NOMS.get(c, c),
            key="oe_couleur"
        )

        if st.button("Créer le projet", key="oe_save", type="primary"):
            if not nom_ep.strip():
                st.warning("Nom requis")
            elif cible_ep <= 0:
                st.warning("Montant cible > 0 requis")
            else:
                audit.creer_objectif_v2(
                    nom=nom_ep.strip(), type_obj="EPARGNE",
                    montant_cible=cible_ep, date_cible=str(date_ep),
                    icone=icone_ep, couleur=couleur_ep,
                )
                st.session_state.oe_open = False
                _invalider_cache()
                st.success("✅ Projet créé")
                st.rerun()

    # ── Liste objectifs épargne ───────────────────────────────────────────────
    objectifs = _get_objs(audit, "EPARGNE", audit.user_id)
    if not objectifs:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:32px;text-align:center;margin-top:16px">'
            f'<div style="font-size:28px;margin-bottom:8px">🏖️</div>'
            f'<div style="color:{T.TEXT_MED};font-size:13px;margin-bottom:12px">'
            f'Aucun projet d\'épargne. Définissez votre premier objectif !</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("➕ Créer mon premier projet d'épargne", key="oe_open_btn",
                     type="primary", use_container_width=True):
            st.session_state.oe_open = True
            st.rerun()
        return

    update_id = st.session_state.get("oe_update_id")

    for obj in objectifs:
        oid     = obj["id"]
        nom     = obj["Nom"]
        icone   = obj.get("Icone") or "🎯"
        cible   = float(obj["Montant_Cible"])
        actuel  = float(obj.get("Montant_Actuel") or 0)
        date_c  = obj.get("Date_Cible", "")[:10]
        couleur = obj.get("Couleur") or T.PRIMARY
        statut  = obj.get("Statut", "EN_COURS")

        pct_val  = min(actuel / cible * 100, 100) if cible > 0 else 0
        restant  = max(cible - actuel, 0)
        atteint  = statut == "ATTEINT" or actuel >= cible

        try:
            delta = (datetime.strptime(date_c, "%Y-%m-%d").date() - date.today()).days
            delai_txt = f"{delta} jours restants" if delta >= 0 else "Date dépassée"
        except ValueError:
            delai_txt = ""

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-left:3px solid {couleur};'
            f'border-radius:{T.RADIUS_MD};padding:16px;margin-bottom:10px">'
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">'
            f'<span style="font-size:28px">{icone}</span>'
            f'<div style="flex:1">'
            f'<div style="color:{T.TEXT_HIGH};font-weight:700;font-size:15px">{nom}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px">{delai_txt} · avant {date_c}</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div style="color:{couleur};font-weight:900;font-size:18px">{pct_val:.0f}%</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px">'
            f'{_dh(actuel)} / {_dh(cible)}</div>'
            f'</div></div>'
            f'{_progress_bar(pct_val, couleur)}'
            f'<div style="color:{T.TEXT_MED};font-size:11px;margin-top:4px">'
            f'Encore {_dh(restant)} à épargner</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if atteint:
            st.markdown(
                f'<div style="color:{T.SUCCESS};font-weight:700;font-size:12px;'
                f'margin-bottom:8px">🎉 Objectif atteint !</div>',
                unsafe_allow_html=True,
            )

        ua, ub, uc = st.columns([2, 1, 1])
        with ua:
            if update_id == oid:
                new_actuel = st.number_input(
                    "Montant épargné (DH)", min_value=0.0, max_value=float(cible) * 2,
                    value=actuel, step=100.0, format="%.0f",
                    key=f"oe_mnt_{oid}"
                )
        with ub:
            if update_id == oid:
                if st.button("💾 OK", key=f"oe_save_{oid}", type="primary", use_container_width=True):
                    audit.maj_objectif_actuel(oid, new_actuel)
                    _invalider_cache()
                    st.session_state.oe_update_id = None
                    st.rerun()
            else:
                if st.button("✏️ Mettre à jour", key=f"oe_upd_{oid}", use_container_width=True):
                    st.session_state.oe_update_id = oid
                    st.rerun()
        with uc:
            if st.button("🗑️ Supprimer", key=f"oe_del_{oid}", use_container_width=True):
                audit.supprimer_objectif(oid)
                _invalider_cache()
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
# TAB HISTORIQUE ÉPARGNE
# ─────────────────────────────────────────────────────────────────────────────

def _tab_histo_epargne(audit) -> None:
    import plotly.graph_objects as go

    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:13px;margin-bottom:16px">'
        f'Votre épargne mois par mois — enregistrée via le rappel sur le dashboard.</p>',
        unsafe_allow_html=True,
    )

    rows = audit.db.get_epargne_histo(audit.user_id, nb_mois=12)

    if not rows:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:40px;text-align:center">'
            f'<div style="font-size:32px;margin-bottom:10px">📈</div>'
            f'<div style="color:{T.TEXT_MED};font-size:14px;margin-bottom:6px">'
            f'Aucun historique enregistré.</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:12px">'
            f'Utilisez le rappel sur le Dashboard pour renseigner votre épargne mensuelle.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # Chronological order for chart
    rows_asc = list(reversed(rows))
    mois_labels = [r.get("Mois", "") for r in rows_asc]
    reels       = [float(r.get("Montant_Reel", 0) or 0) for r in rows_asc]
    vises       = [float(r.get("Montant_Vise", 0) or 0) for r in rows_asc]

    fig = go.Figure()
    if any(v > 0 for v in vises):
        fig.add_trace(go.Bar(
            x=mois_labels, y=vises,
            name="Objectif", marker_color=T.BORDER_MED,
            opacity=0.5,
        ))
    fig.add_trace(go.Bar(
        x=mois_labels, y=reels,
        name="Réel", marker_color=T.SUCCESS,
    ))
    fig.update_layout(
        barmode="overlay",
        paper_bgcolor=T.BG_PAGE, plot_bgcolor=T.BG_PAGE,
        font_color=T.TEXT_MED,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=T.TEXT_MED)),
        margin=dict(t=20, b=20, l=0, r=0),
        height=240,
        yaxis=dict(gridcolor=T.BORDER),
        xaxis=dict(gridcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Summary table
    total_reel = sum(reels)
    cumul_last = float(rows[0].get("Cumul_Total", 0) or 0)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:14px;text-align:center">'
            f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1px">Total sur {len(rows)} mois</div>'
            f'<div style="color:{T.SUCCESS};font-size:24px;font-weight:900;margin-top:4px">'
            f'{_dh(total_reel)}</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:14px;text-align:center">'
            f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1px">Cumul total</div>'
            f'<div style="color:{T.PRIMARY};font-size:24px;font-weight:900;margin-top:4px">'
            f'{_dh(cumul_last)}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    for r in rows:
        mois  = r.get("Mois", "")
        reel  = float(r.get("Montant_Reel", 0) or 0)
        vise  = float(r.get("Montant_Vise", 0) or 0)
        color = T.SUCCESS if (vise == 0 or reel >= vise) else T.WARNING
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:10px 16px;margin-bottom:4px;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'<span style="color:{T.TEXT_MED};font-size:13px">{mois}</span>'
            f'<span style="display:flex;gap:20px;align-items:center">'
            + (f'<span style="color:{T.TEXT_LOW};font-size:11px">Objectif {_dh(vise)}</span>'
               if vise > 0 else '') +
            f'<span style="color:{color};font-size:14px;font-weight:700">{_dh(reel)}</span>'
            f'</span></div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────

def render(ctx: dict) -> None:
    audit    = ctx["audit"]
    mois_sel = ctx["mois_sel"]
    mois_lbl = ctx["mois_lbl"]

    render_page_header("🎯", "Objectifs", "Réduction des dépenses et constitution d'épargne")

    tab_dep, tab_ep, tab_histo = st.tabs([
        "💸 Objectif Dépense", "💰 Objectif Épargne", "📈 Historique Épargne"
    ])

    with tab_dep:
        _tab_depense(audit, mois_sel, mois_lbl)

    with tab_ep:
        _tab_epargne(audit)

    with tab_histo:
        _tab_histo_epargne(audit)
