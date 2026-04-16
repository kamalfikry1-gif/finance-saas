"""
views/objectif.py — Objectifs financiers.
Tab 1 — Dépense : réduire une catégorie sous un seuil cible.
Tab 2 — Épargne : accumuler un montant d'ici une deadline (vacances, voiture…).
"""

from datetime import date, datetime
import streamlit as st
from components.design_tokens import T


# ── Palette icônes prédéfinis pour les objectifs épargne ──────────────────────
_ICONES_EPARGNE = ["🏖️", "🚗", "🏠", "📱", "🎓", "💍", "✈️", "🏋️", "🎸", "💼", "🛡️", "🎯"]
_COULEURS       = [T.PRIMARY, T.SUCCESS, T.WARNING, T.DANGER,
                   T.BLUE, T.PURPLE, T.CAT_PALETTE[6], T.CAT_PALETTE[7]]


def _dh(v) -> str:
    v = 0.0 if v is None else float(v)
    return f"{v:,.0f} DH".replace(",", " ")


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
        parts   = mois.split("/")
        mois_db = f"{parts[1]}-{parts[0]}"
        with audit.db.connexion() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(Montant),0) FROM TRANSACTIONS
                   WHERE Sens='OUT' AND user_id=? AND Categorie=? AND Date_Valeur LIKE ?""",
                (audit.user_id, categorie, f"{mois_db}%")
            ).fetchone()
        return float(row[0])
    except Exception:
        return 0.0


def _get_categories_out(audit) -> list:
    try:
        with audit.db.connexion() as conn:
            rows = conn.execute(
                """SELECT DISTINCT c.Categorie FROM CATEGORIES c
                   JOIN REFERENTIEL r ON c.Categorie=r.Categorie
                   WHERE r.Sens='OUT' ORDER BY c.Categorie"""
            ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# TAB DÉPENSE
# ─────────────────────────────────────────────────────────────────────────────

def _tab_depense(audit, mois_sel: str, mois_lbl: str) -> None:
    db      = audit.db
    user_id = audit.user_id
    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:13px;margin-bottom:20px">'
        f'Fixez un plafond aspirationnel pour une catégorie. '
        f'Différent du plafond d\'alerte — ici c\'est votre ambition personnelle de réduction.</p>',
        unsafe_allow_html=True,
    )

    # ── Formulaire création ───────────────────────────────────────────────────
    with st.expander("➕ Nouvel objectif de dépense", expanded=False):
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
                db.creer_objectif_v2(
                    nom=nom_dep.strip(), type_obj="DEPENSE",
                    montant_cible=cible_dep, date_cible=str(date_cible_dep),
                    user_id=user_id,
                    categorie=cat_dep or "", icone=icone_dep, couleur=T.WARNING,
                )
                st.success("✅ Objectif créé")
                st.rerun()

    # ── Liste objectifs dépense ───────────────────────────────────────────────
    objectifs = db.get_objectifs_v2(user_id=user_id, type_obj="DEPENSE")
    if not objectifs:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:32px;text-align:center;margin-top:16px">'
            f'<div style="font-size:28px;margin-bottom:8px">✂️</div>'
            f'<div style="color:{T.TEXT_MED};font-size:13px">'
            f'Aucun objectif de réduction. Créez-en un pour suivre vos efforts !</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    for obj in objectifs:
        oid      = obj["id"]
        nom      = obj["Nom"]
        icone    = obj.get("Icone") or "📉"
        cat      = obj.get("Categorie") or ""
        cible    = float(obj["Montant_Cible"])
        date_c   = obj.get("Date_Cible", "")[:10]
        couleur  = obj.get("Couleur") or T.WARNING

        # Dépense réelle ce mois dans la catégorie
        depense_actuelle = _get_depenses_cat_mois(audit, cat, mois_sel) if cat else 0.0
        # Pour un objectif dépense : succès si dépensé < cible
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
            db.supprimer_objectif(oid, user_id)
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB ÉPARGNE
# ─────────────────────────────────────────────────────────────────────────────

def _tab_epargne(audit) -> None:
    db      = audit.db
    user_id = audit.user_id
    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:13px;margin-bottom:20px">'
        f'Suivez vos projets d\'épargne : vacances, voiture, urgence, … '
        f'Mettez à jour le montant épargné à votre rythme.</p>',
        unsafe_allow_html=True,
    )

    # ── Formulaire création ───────────────────────────────────────────────────
    with st.expander("➕ Nouvel objectif d'épargne", expanded=False):
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
            format_func=lambda c: c,
            key="oe_couleur"
        )

        if st.button("Créer le projet", key="oe_save", type="primary"):
            if not nom_ep.strip():
                st.warning("Nom requis")
            elif cible_ep <= 0:
                st.warning("Montant cible > 0 requis")
            else:
                db.creer_objectif_v2(
                    nom=nom_ep.strip(), type_obj="EPARGNE",
                    montant_cible=cible_ep, date_cible=str(date_ep),
                    user_id=user_id,
                    icone=icone_ep, couleur=couleur_ep,
                )
                st.success("✅ Projet créé")
                st.rerun()

    # ── Liste objectifs épargne ───────────────────────────────────────────────
    objectifs = db.get_objectifs_v2(user_id=user_id, type_obj="EPARGNE")
    if not objectifs:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:32px;text-align:center;margin-top:16px">'
            f'<div style="font-size:28px;margin-bottom:8px">🏖️</div>'
            f'<div style="color:{T.TEXT_MED};font-size:13px">'
            f'Aucun projet d\'épargne. Définissez votre premier objectif !</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
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

        pct      = min(actuel / cible * 100, 100) if cible > 0 else 0
        restant  = max(cible - actuel, 0)
        atteint  = statut == "ATTEINT" or actuel >= cible

        # Jours restants
        try:
            delta = (datetime.strptime(date_c, "%Y-%m-%d").date() - date.today()).days
            delai_txt = f"{delta} jours restants" if delta >= 0 else "Date dépassée"
        except Exception:
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
            f'<div style="color:{couleur};font-weight:900;font-size:18px">{pct:.0f}%</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px">'
            f'{_dh(actuel)} / {_dh(cible)}</div>'
            f'</div></div>'
            f'{_progress_bar(pct, couleur)}'
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

        # Mise à jour montant
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
                    audit.db.maj_objectif_actuel(oid, new_actuel, user_id)
                    st.session_state.oe_update_id = None
                    st.rerun()
            else:
                if st.button("✏️ Mettre à jour", key=f"oe_upd_{oid}", use_container_width=True):
                    st.session_state.oe_update_id = oid
                    st.rerun()
        with uc:
            if st.button("🗑️ Supprimer", key=f"oe_del_{oid}", use_container_width=True):
                db.supprimer_objectif(oid, user_id)
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def render(ctx: dict) -> None:
    audit    = ctx["audit"]
    mois_sel = ctx["mois_sel"]
    mois_lbl = ctx["mois_lbl"]

    st.markdown(
        f'<h2 style="color:{T.TEXT_HIGH};font-weight:900;'
        f'font-size:24px;margin-bottom:4px">🎯 Objectifs</h2>'
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:20px">'
        f'Suivez vos ambitions financières — réduction des dépenses et constitution d\'épargne.</p>',
        unsafe_allow_html=True,
    )

    tab_dep, tab_ep = st.tabs(["💸 Objectif Dépense", "💰 Objectif Épargne"])

    with tab_dep:
        _tab_depense(audit, mois_sel, mois_lbl)

    with tab_ep:
        _tab_epargne(audit)
