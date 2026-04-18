"""
views/onboarding.py — Onboarding 2 étapes.

Étape 1 — Revenus
    · Salaire principal + autres revenus dynamiques

Étape 2 — Dépenses du mois en cours
    · Catégories affichées directement avec sous-catégories dépliables
    · L'utilisateur remplit les montants qu'il se rappelle
    · Chaque montant > 0 crée une transaction Source=ONBOARDING
    · Pas de date (auto), pas de catégorisation manuelle
"""

from datetime import date, datetime
import streamlit as st

from core.data_input import (
    lister_categories,
    sauvegarder_revenus,
    marquer_onboarding_fait,
    enregistrer_transaction,
    enregistrer_transaction_categorisee,
)
from components.design_tokens import T
from components.helpers import dh as _dh
from core.cache import invalider as _invalider_cache

COULEURS_CAT = {
    "Logement":           T.PRIMARY,
    "Vie Quotidienne":    T.SUCCESS,
    "Transport":          T.WARNING,
    "Loisirs":            T.DANGER,
    "Santé":              T.BLUE,
    "Abonnements":        T.CAT_PALETTE[7],   # Teal vert
    "Finances & Crédits": T.PURPLE,
    "Divers":             T.TEXT_MED,
}




# ─────────────────────────────────────────────────────────────────────────────
# BARRE D'ÉTAPES
# ─────────────────────────────────────────────────────────────────────────────

def _barre_etapes(etape: int) -> None:
    labels = ["Vos revenus", "Vos dépenses du mois"]
    cols   = st.columns(len(labels))
    for i, (col, lbl) in enumerate(zip(cols, labels)):
        actif   = (i + 1 == etape)
        fait    = (i + 1 < etape)
        couleur = T.PRIMARY if actif else (T.SUCCESS if fait else T.BORDER_MED)
        texte   = T.TEXT_HIGH if actif else (T.SUCCESS if fait else T.TEXT_LOW)
        with col:
            st.markdown(
                f"<div style='text-align:center;padding:10px 0;"
                f"border-bottom:3px solid {couleur};'>"
                f"<span style='color:{texte};font-weight:700;font-size:13px'>"
                f"{'✓ ' if fait else ''}{i+1}. {lbl}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 1 — REVENUS (inchangée)
# ─────────────────────────────────────────────────────────────────────────────

def _etape_revenus() -> None:
    st.markdown(
        f"<h2 style='color:{T.TEXT_HIGH};margin:24px 0 4px'>Vos revenus mensuels 💼</h2>"
        f"<p style='color:{T.TEXT_LOW};font-size:13px;margin-bottom:24px'>"
        f"Ces informations permettent au Coach de calibrer vos budgets "
        f"et de calculer votre taux d'épargne réel."
        f"</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div style='color:{T.TEXT_MED};font-size:11px;font-weight:700;"
        f"text-transform:uppercase;letter-spacing:1px;margin-bottom:6px'>"
        f"Salaire / Revenu principal</div>",
        unsafe_allow_html=True,
    )
    salaire = st.number_input(
        "Salaire mensuel net (DH)",
        min_value=0.0, max_value=500_000.0,
        value=float(st.session_state.get("ob_salaire", 0.0)),
        step=500.0, format="%.0f",
        label_visibility="collapsed", key="ob_salaire_input",
    )
    st.session_state.ob_salaire = salaire

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='color:{T.TEXT_MED};font-size:11px;font-weight:700;"
        f"text-transform:uppercase;letter-spacing:1px;margin-bottom:10px'>"
        f"Autres sources de revenus (optionnel)</div>",
        unsafe_allow_html=True,
    )

    if "ob_extras" not in st.session_state:
        st.session_state.ob_extras = []

    extras      = st.session_state.ob_extras
    a_supprimer = None

    for i, extra in enumerate(extras):
        c_nom, c_mnt, c_del = st.columns([3, 2, 1])
        with c_nom:
            extras[i]["nom"] = st.text_input(
                "Nom", value=extra["nom"],
                placeholder="ex: Loyer perçu, Freelance…",
                key=f"ob_ex_nom_{i}", label_visibility="collapsed",
            )
        with c_mnt:
            extras[i]["montant"] = st.number_input(
                "Montant", min_value=0.0, max_value=500_000.0,
                value=float(extra["montant"]), step=100.0, format="%.0f",
                key=f"ob_ex_mnt_{i}", label_visibility="collapsed",
            )
        with c_del:
            if st.button("✕", key=f"ob_ex_del_{i}", use_container_width=True):
                a_supprimer = i

    if a_supprimer is not None:
        extras.pop(a_supprimer)
        st.session_state.ob_extras = extras
        st.rerun()

    if st.button("+ Ajouter un revenu", key="ob_add_extra", type="secondary"):
        extras.append({"nom": "", "montant": 0.0})
        st.session_state.ob_extras = extras
        st.rerun()

    total_revenus = salaire + sum(float(e["montant"]) for e in extras)
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    couleur_total = T.SUCCESS if total_revenus > 0 else T.TEXT_LOW
    st.markdown(
        f"<div style='background:linear-gradient(135deg,{T.BG_CARD},{T.BG_CARD_ALT});"
        f"border-radius:{T.RADIUS_LG};padding:20px 24px;border:1px solid {T.BORDER_MED};"
        f"display:flex;justify-content:space-between;align-items:center'>"
        f"<div>"
        f"<div style='color:{T.TEXT_MED};font-size:11px;font-weight:700;"
        f"text-transform:uppercase;letter-spacing:1px'>Revenus mensuels totaux</div>"
        f"<div style='color:{couleur_total};font-size:32px;font-weight:900;margin-top:4px'>"
        f"{_dh(total_revenus)}</div>"
        f"</div>"
        f"<div style='color:{T.TEXT_MUTED};font-size:12px;text-align:right'>"
        f"Salaire : {_dh(salaire)}<br>"
        + (f"Autres : {_dh(total_revenus - salaire)}" if total_revenus - salaire > 0 else "") +
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    col_skip, col_next = st.columns([1, 2])
    with col_skip:
        if st.button("Passer pour l'instant", use_container_width=True,
                     type="secondary", key="ob_skip_rev"):
            st.session_state.ob_step = 2
            st.rerun()
    with col_next:
        if st.button("Suivant →", use_container_width=True,
                     type="primary", key="ob_next"):
            if total_revenus <= 0:
                st.warning("Renseignez au moins un revenu pour continuer.")
            else:
                _sauvegarder_revenus()
                st.session_state.ob_step = 2
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 2 — DÉPENSES DU MOIS PAR CATÉGORIE
# ─────────────────────────────────────────────────────────────────────────────

def _etape_depenses(categories: list) -> None:
    now        = datetime.now()
    mois_label = now.strftime("%B %Y").capitalize()

    st.markdown(
        f"<h2 style='color:{T.TEXT_HIGH};margin:24px 0 4px'>"
        f"Vos dépenses de {mois_label} 📋</h2>"
        f"<p style='color:{T.TEXT_LOW};font-size:13px;margin-bottom:6px'>"
        f"Renseignez ce dont vous vous souvenez — laissez à 0 ce que vous ne savez plus."
        f"</p>"
        f"<div style='background:{T.BG_CARD_ALT};border-radius:{T.RADIUS_SM};padding:8px 14px;"
        f"border-left:3px solid {T.PRIMARY};margin-bottom:24px'>"
        f"<span style='color:{T.TEXT_MED};font-size:12px'>"
        f"Chaque montant renseigné crée une transaction dans la bonne catégorie. "
        f"Vous pourrez affiner et ajouter d'autres opérations depuis l'app.</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Regroupement par catégorie (OUT uniquement)
    cats_groupees: dict = {}
    for item in categories:
        if item.get("sens", "OUT") == "IN":
            continue
        cat = item["categorie"]
        if cat not in cats_groupees:
            cats_groupees[cat] = []
        cats_groupees[cat].append(item)

    # Init état montants
    if "ob_montants" not in st.session_state:
        st.session_state.ob_montants = {}

    montants = st.session_state.ob_montants
    total_saisi = 0.0

    for cat, items in cats_groupees.items():
        couleur = COULEURS_CAT.get(cat, T.TEXT_MED)

        # Total de la catégorie
        total_cat = sum(montants.get(f"{cat}|{it['sous_categorie']}", 0.0) for it in items)

        st.markdown(
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"margin:20px 0 0'>"
            f"<div style='display:flex;align-items:center;gap:10px'>"
            f"<div style='width:4px;height:22px;background:{couleur};border-radius:2px'></div>"
            f"<span style='color:{T.TEXT_HIGH};font-weight:700;font-size:16px'>{cat}</span>"
            f"</div>"
            + (f"<span style='color:{couleur};font-size:13px;font-weight:700'>{_dh(total_cat)}</span>"
               if total_cat > 0 else "") +
            f"</div>",
            unsafe_allow_html=True,
        )

        with st.expander(
            f"{'✓ ' if total_cat > 0 else ''}{len(items)} sous-catégorie{'s' if len(items) > 1 else ''}",
            expanded=(total_cat > 0),
        ):
            for item in items:
                sous = item["sous_categorie"]
                cle  = f"{cat}|{sous}"

                c_label, c_input = st.columns([3, 2])
                with c_label:
                    st.markdown(
                        f"<div style='color:{T.TEXT_MED};font-size:13px;padding-top:10px'>"
                        f"{sous}</div>",
                        unsafe_allow_html=True,
                    )
                with c_input:
                    val = st.number_input(
                        sous, min_value=0.0, max_value=500_000.0,
                        value=float(montants.get(cle, 0.0)),
                        step=50.0, format="%.0f",
                        label_visibility="collapsed",
                        key=f"ob_dep_{cle}",
                    )
                    montants[cle] = val

        total_saisi += total_cat

    st.session_state.ob_montants = montants

    # ── Récapitulatif ─────────────────────────────────────────────────────────
    nb_postes = sum(1 for v in montants.values() if v > 0)
    if nb_postes > 0:
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='background:linear-gradient(135deg,{T.BG_CARD},{T.BG_CARD_ALT});"
            f"border-radius:{T.RADIUS_LG};padding:18px 22px;border:1px solid {T.BORDER_MED};"
            f"display:flex;justify-content:space-between;align-items:center'>"
            f"<div style='color:{T.TEXT_MED};font-size:12px'>"
            f"{nb_postes} poste{'s' if nb_postes > 1 else ''} renseigné{'s' if nb_postes > 1 else ''}</div>"
            f"<div style='color:{T.DANGER};font-size:24px;font-weight:900'>{_dh(total_saisi)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Navigation ────────────────────────────────────────────────────────────
    c_back, c_passer, c_valider = st.columns([1, 1, 2])

    with c_back:
        if st.button("← Retour", use_container_width=True,
                     type="secondary", key="ob_back2"):
            st.session_state.ob_step = 1
            st.rerun()

    with c_passer:
        if st.button("Passer", use_container_width=True,
                     type="secondary", key="ob_passer"):
            _finaliser(enregistrer=False)

    with c_valider:
        label = (
            f"Enregistrer {nb_postes} poste{'s' if nb_postes != 1 else ''} et commencer →"
            if nb_postes > 0 else "Commencer →"
        )
        if st.button(label, use_container_width=True,
                     type="primary", key="ob_valider"):
            _finaliser(enregistrer=(nb_postes > 0))


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTANCE
# ─────────────────────────────────────────────────────────────────────────────

def _sauvegarder_revenus() -> None:
    audit   = st.session_state._ob_audit
    salaire = float(st.session_state.get("ob_salaire", 0.0))
    extras  = [
        e for e in st.session_state.get("ob_extras", [])
        if e.get("nom", "").strip() and float(e.get("montant", 0)) > 0
    ]
    # 1. Sauvegarder dans PREFERENCES (référence coach + budget)
    sauvegarder_revenus(audit, salaire, extras)

    # 2. Créer les transactions IN correspondantes pour que le bilan mensuel soit correct
    date_rev = date.today()
    if salaire > 0:
        enregistrer_transaction(
            audit, libelle="Salaire", montant=salaire,
            sens="IN", date_valeur=date_rev, forcer=True, source="ONBOARDING",
        )
    for extra in extras:
        enregistrer_transaction(
            audit, libelle=extra["nom"], montant=float(extra["montant"]),
            sens="IN", date_valeur=date_rev, forcer=True, source="ONBOARDING",
        )


def _finaliser(enregistrer: bool) -> None:
    audit   = st.session_state._ob_audit
    montants = st.session_state.get("ob_montants", {})

    if enregistrer:
        date_ob = date.today()
        for cle, montant in montants.items():
            if montant <= 0:
                continue
            cat, sous = cle.split("|", 1)
            # On connaît déjà cat+sous : on bypasse le Trieur pour éviter "Divers"
            enregistrer_transaction_categorisee(
                audit,
                libelle       = sous,
                montant       = montant,
                sens          = "OUT",
                categorie     = cat,
                sous_categorie= sous,
                date_valeur   = date_ob,
                source        = "ONBOARDING",
            )

    marquer_onboarding_fait(audit)

    for key in list(st.session_state.keys()):
        if key.startswith("ob_") or key.startswith("_ob_"):
            del st.session_state[key]

    _invalider_cache()
    st.success("✅ Bienvenue ! Votre tableau de bord est prêt.")
    st.balloons()
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

def render(audit) -> None:
    st.session_state._ob_audit = audit

    if "ob_step" not in st.session_state:
        st.session_state.ob_step = 1

    # ── Header ────────────────────────────────────────────────────────────────
    _, col_center, _ = st.columns([1, 3, 1])
    with col_center:
        st.markdown(
            f"<div style='text-align:center;padding:28px 0 4px'>"
            f"<div style='color:{T.PRIMARY};font-size:12px;font-weight:700;"
            f"text-transform:uppercase;letter-spacing:2px;margin-bottom:8px'>"
            f"Bienvenue sur Finance SaaS</div>"
            f"<h1 style='color:{T.TEXT_HIGH};font-size:30px;margin:0'>"
            f"Configurons votre profil 🚀</h1>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    _, col_steps, _ = st.columns([1, 3, 1])
    with col_steps:
        _barre_etapes(st.session_state.ob_step)

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    st.divider()

    _, col_main, _ = st.columns([1, 4, 1])
    with col_main:
        if st.session_state.ob_step == 1:
            _etape_revenus()

        elif st.session_state.ob_step == 2:
            categories = lister_categories(audit)
            if not categories:
                st.warning("Aucune catégorie trouvée. Lancez d'abord `python migrate_referentiel.py`.")
                if st.button("Passer l'onboarding", type="secondary"):
                    marquer_onboarding_fait(audit)
                    st.rerun()
            else:
                _etape_depenses(categories)
