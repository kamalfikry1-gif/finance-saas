"""
views/moi.py — Page profil utilisateur.
Revenus, identité coach, ratios 50/30/20, seuil d'alerte.
"""

import json
import logging
import streamlit as st
from components.design_tokens import T
from components.cards import IDENTITE_LABEL, IDENTITE_DESC
from components.helpers import section as _section
from core.cache import invalider as _invalider_cache

logger = logging.getLogger(__name__)


def render(ctx: dict) -> None:
    audit = ctx["audit"]

    st.markdown(
        f'<h2 style="color:{T.TEXT_HIGH};font-weight:900;'
        f'font-size:24px;margin-bottom:4px">👤 Mon Profil</h2>'
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:24px">'
        f'Gérez vos informations personnelles et préférences de l\'application.</p>',
        unsafe_allow_html=True,
    )

    # ── Section 1 : Revenus ──────────────────────────────────────────────────
    _section("Revenus")

    salaire_str = audit.get_preference("revenu_salaire", "0")
    try:
        salaire_actuel = float(salaire_str)
    except ValueError:
        salaire_actuel = 0.0

    extras_str = audit.get_preference("revenu_extras_json", "[]")
    try:
        extras_list = json.loads(extras_str)
        extras_total = sum(float(e.get("montant", 0)) for e in extras_list if isinstance(e, dict))
    except (ValueError, TypeError, json.JSONDecodeError):
        logger.warning("Could not parse revenu_extras_json")
        extras_total = 0.0

    c1, c2 = st.columns(2)
    with c1:
        nouveau_salaire = st.number_input(
            "Salaire mensuel net (DH)",
            min_value=0.0, max_value=999_999.0,
            value=salaire_actuel, step=100.0,
            format="%.0f",
            key="moi_salaire",
        )
    with c2:
        st.metric("Revenus extras (DH)", f"{extras_total:,.0f}".replace(",", " "),
                  help="Modifiez via la saisie de transactions Revenu")

    if st.button("💾 Sauvegarder les revenus", key="btn_save_revenus", type="primary"):
        total = nouveau_salaire + extras_total
        audit.set_preference("revenu_salaire", str(nouveau_salaire))
        audit.set_preference("revenu_total_attendu", str(total))
        _invalider_cache()
        st.success(f"✅ Salaire mis à jour — Total attendu : {total:,.0f} DH".replace(",", " "))

    # ── Section 2 : Identité Coach ───────────────────────────────────────────
    _section("Identité du Coach")

    identite_courante = audit.get_identite()
    opts = list(IDENTITE_LABEL.keys())

    cols = st.columns(len(opts))
    for i, (k, lbl) in enumerate(IDENTITE_LABEL.items()):
        with cols[i]:
            is_sel = k == identite_courante
            border = f"2px solid {T.PRIMARY}" if is_sel else f"1px solid {T.BORDER}"
            bg     = f"{T.PRIMARY}18" if is_sel else T.BG_CARD
            st.markdown(
                f'<div style="background:{bg};border:{border};'
                f'border-radius:{T.RADIUS_MD};padding:14px;text-align:center;'
                f'margin-bottom:8px">'
                f'<div style="font-size:22px;margin-bottom:6px">{lbl.split()[0]}</div>'
                f'<div style="color:{T.PRIMARY if is_sel else T.TEXT_HIGH};'
                f'font-weight:700;font-size:12px">{lbl.split(" ", 1)[1]}</div>'
                f'<div style="color:{T.TEXT_LOW};font-size:10px;margin-top:4px">'
                f'{IDENTITE_DESC[k]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if not is_sel:
                if st.button(f"Choisir", key=f"id_{k}", use_container_width=True):
                    audit.set_identite(k)
                    _invalider_cache()
                    st.rerun()
            else:
                st.markdown(
                    f'<div style="text-align:center;color:{T.PRIMARY};'
                    f'font-size:11px;font-weight:700">✓ Actif</div>',
                    unsafe_allow_html=True,
                )

    # ── Section 3 : Ratios 50/30/20 ─────────────────────────────────────────
    _section("Règle Budgétaire 50 / 30 / 20")

    needs_pct   = int(audit.get_preference("needs_pct",   "50"))
    wants_pct   = int(audit.get_preference("wants_pct",   "30"))
    savings_pct = int(audit.get_preference("savings_pct", "20"))

    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:12px;margin-bottom:12px">'
        f'La somme doit être égale à 100 %. '
        f'Besoins = loyer, alimentation, transport. '
        f'Envies = loisirs, restos. '
        f'Épargne = investissement, remboursements.</p>',
        unsafe_allow_html=True,
    )

    r1, r2, r3 = st.columns(3)
    with r1:
        new_needs = st.number_input(
            "🏠 Besoins (%)", min_value=0, max_value=100,
            value=needs_pct, step=5, key="moi_needs"
        )
    with r2:
        new_wants = st.number_input(
            "🎭 Envies (%)", min_value=0, max_value=100,
            value=wants_pct, step=5, key="moi_wants"
        )
    with r3:
        new_savings = st.number_input(
            "💰 Épargne (%)", min_value=0, max_value=100,
            value=savings_pct, step=5, key="moi_savings"
        )

    total_pct = new_needs + new_wants + new_savings
    if total_pct != 100:
        st.warning(f"⚠️ Total : {total_pct} % — doit être égal à 100 %")
    else:
        # Barre visuelle
        st.markdown(
            f'<div style="display:flex;height:10px;border-radius:{T.RADIUS_PILL};overflow:hidden;margin:10px 0">'
            f'<div style="width:{new_needs}%;background:{T.PRIMARY}"></div>'
            f'<div style="width:{new_wants}%;background:{T.WARNING}"></div>'
            f'<div style="width:{new_savings}%;background:{T.SUCCESS}"></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if st.button("💾 Sauvegarder les ratios", key="btn_save_ratios", type="primary",
                 disabled=(total_pct != 100)):
        audit.set_preference("needs_pct",   str(new_needs))
        audit.set_preference("wants_pct",   str(new_wants))
        audit.set_preference("savings_pct", str(new_savings))
        _invalider_cache()
        st.success("✅ Ratios 50/30/20 mis à jour")

    # ── Section 4 : Seuil d'alerte ───────────────────────────────────────────
    _section("Seuil d'Alerte Dépense")

    seuil_actuel = int(audit.get_preference("seuil_alerte", "80"))
    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:12px;margin-bottom:12px">'
        f'Le coach vous alerte quand une catégorie dépasse ce pourcentage de son plafond.</p>',
        unsafe_allow_html=True,
    )
    new_seuil = st.slider(
        "Seuil d'alerte (%)", min_value=50, max_value=100,
        value=seuil_actuel, step=5, key="moi_seuil"
    )
    if st.button("💾 Sauvegarder le seuil", key="btn_save_seuil", type="primary"):
        audit.set_preference("seuil_alerte", str(new_seuil))
        _invalider_cache()
        st.success(f"✅ Seuil d'alerte : {new_seuil} %")
