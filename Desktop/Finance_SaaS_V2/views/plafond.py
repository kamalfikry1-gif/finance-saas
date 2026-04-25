"""
views/plafond.py — Gestion des plafonds budgétaires par catégorie.
Plafond permanent (CATEGORIES.Plafond) — le système alerte quand dépassé.
"""

import logging
import unicodedata
import streamlit as st
from components.design_tokens import T
from components.helpers import dh as _dh, render_page_header
from core.cache import invalider as _invalider_cache, get_plafonds as _get_plafonds, get_depenses_mois as _get_dep

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    """Lowercase + NFC normalize for robust comparisons."""
    return unicodedata.normalize("NFC", str(s)).lower().strip()


def _render_rows(items: list, cat: str, depenses: dict, audit) -> None:
    """Render number_input rows for a list of sub-category items."""
    for item in items:
        scat    = item["sous_cat"]
        plafond = item["plafond"]
        depense = item["depense"]
        key     = f"plafond_{cat}_{scat}"

        pct     = min((depense / plafond * 100) if plafond > 0 else 0, 100)
        couleur = T.SUCCESS if pct < 70 else (T.WARNING if pct < 90 else T.DANGER)

        col_a, col_b, col_c = st.columns([3, 2, 2])
        with col_a:
            st.markdown(
                f'<div style="color:{T.TEXT_HIGH};font-weight:600;'
                f'font-size:13px;padding-top:8px">{scat}</div>',
                unsafe_allow_html=True,
            )
            if plafond > 0:
                st.markdown(
                    f'<div style="background:{T.BORDER};border-radius:{T.RADIUS_PILL};'
                    f'height:6px;margin-top:6px;overflow:hidden">'
                    f'<div style="width:{pct:.0f}%;height:100%;'
                    f'background:{couleur};border-radius:{T.RADIUS_PILL}"></div>'
                    f'</div>'
                    f'<div style="color:{T.TEXT_LOW};font-size:10px;margin-top:3px">'
                    f'{depense:,.0f} / {plafond:,.0f} DH ({pct:.0f}%)</div>'.replace(",", " "),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="color:{T.TEXT_LOW};font-size:10px;margin-top:6px">'
                    f'Dépensé ce mois : {_dh(depense)}</div>',
                    unsafe_allow_html=True,
                )
        with col_b:
            new_val = st.number_input(
                "Plafond (DH)", min_value=0.0, max_value=999_999.0,
                value=plafond, step=100.0, format="%.0f",
                label_visibility="collapsed",
                key=key,
            )
            if new_val != plafond:
                st.session_state.plafond_changes[(cat, scat)] = new_val
        with col_c:
            if (cat, scat) in st.session_state.plafond_changes:
                if st.button("💾 Sauv.", key=f"psave_{cat}_{scat}", use_container_width=True, type="primary"):
                    audit.set_plafond_categorie(cat, scat, new_val)
                    del st.session_state.plafond_changes[(cat, scat)]
                    _invalider_cache()
                    st.success(f"✅ {scat} — plafond : {_dh(new_val)}")
                    st.rerun()
            else:
                if plafond > 0 and pct >= 90:
                    st.markdown(
                        f'<div style="color:{T.DANGER};font-size:11px;'
                        f'font-weight:700;padding-top:8px">⚠️ Limite atteinte</div>',
                        unsafe_allow_html=True,
                    )
                elif plafond > 0 and pct >= 70:
                    st.markdown(
                        f'<div style="color:{T.WARNING};font-size:11px;'
                        f'font-weight:700;padding-top:8px">🔸 Attention</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="color:{T.TEXT_LOW};font-size:11px;'
                        f'padding-top:8px">—</div>',
                        unsafe_allow_html=True,
                    )


# Normalized (lowercase NFC) category names to exclude from plafond
_CATS_EXCLUES_NORM = {
    _norm(c) for c in (
        "Finances & Crédits", "Finances Credits", "Finances & Credits",
        "Epargne", "Épargne", "Divers",
    )
}

# Normalized sub-category names to hide (deprecated or illogical to cap)
_SCATS_OBSOLETES_NORM = {
    _norm(s) for s in (
        "Protéine", "Proteïne", "Proteine",
        "Fruits & légumes", "Fruits & legumes",
        "EPARGNE INVESTISSEMENT", "Epargne & Investissement",
        "Crédit & Remboursement", "Credit & Remboursement",
        "Banque & Assur", "Logiciels & Cloud",
        "Streaming & TV", "Generale", "Général",
        "Frais de dossier",
        "Ciné & Culture", "Cine & Culture",
        "Bien-être & Hygiène", "Bien-etre & Hygiene",
        "Sport & Hobby",
        "Analyses & Radio", "Consultations",
        "Entretien & Lavage",
        "Taxi & Uber", "Tramway & Bus",
        "Sorties & Shopping",
        "Remboursement Dette",
        "Crédit Conso ou Auto", "Credit Conso ou Auto",
        "Impôts", "Impots",
    )
}


def _scat_visible(scat: str) -> bool:
    """Return False for internal _autre suffixes and known deprecated entries."""
    n = _norm(scat)
    if n in _SCATS_OBSOLETES_NORM:
        return False
    if n.endswith("_autre"):
        return False
    return True


def _cat_visible(cat: str) -> bool:
    return _norm(cat) not in _CATS_EXCLUES_NORM


def render(ctx: dict) -> None:
    audit    = ctx["audit"]
    mois_sel = ctx["mois_sel"]
    mois_lbl = ctx["mois_lbl"]

    render_page_header("🔔", "Plafonds Budgétaires", f"Limites par sous-catégorie · {mois_lbl}")

    try:
        cats     = _get_plafonds(audit, audit.user_id)
        depenses = _get_dep(audit, mois_sel, audit.user_id)
    except Exception:
        st.warning("Impossible de charger les plafonds — réessayez dans quelques secondes.")
        return
    categories  = {}

    for row in cats:
        cat  = row["Categorie"]
        scat = row["Sous_Categorie"]
        if not _cat_visible(cat):
            continue
        if not _scat_visible(scat):
            continue
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "sous_cat": scat,
            "plafond":  float(row["Plafond"] or 0),
            "depense":  depenses.get((cat, scat), 0.0),
        })

    if not categories:
        st.info("Aucune catégorie de dépense trouvée. Commencez par saisir des transactions.")
        return

    if "plafond_changes" not in st.session_state:
        st.session_state.plafond_changes = {}

    # ── Separate active (plafond > 0) from inactive per category ─────────────
    cats_actives  = {c: items for c, items in categories.items()
                     if any(i["plafond"] > 0 for i in items)}
    cats_inactives = {c: items for c, items in categories.items()
                      if not any(i["plafond"] > 0 for i in items)}

    # ── Empty state: no active limits at all ──────────────────────────────────
    if not cats_actives:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:28px;text-align:center;margin-bottom:20px">'
            f'<div style="font-size:28px;margin-bottom:8px">🔔</div>'
            f'<div style="color:{T.TEXT_MED};font-size:13px;margin-bottom:4px">'
            f'Aucun plafond actif.</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:12px">'
            f'Définissez un plafond ci-dessous pour que le coach vous alerte '
            f'automatiquement quand vous approchez de la limite.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Render categories with at least one active limit ─────────────────────
    for cat, items in cats_actives.items():
        actifs   = [i for i in items if i["plafond"] > 0]
        inactifs = [i for i in items if i["plafond"] == 0]

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:20px;margin-bottom:12px">',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="color:{T.PRIMARY};font-size:14px;font-weight:700;'
            f'margin-bottom:14px;text-transform:uppercase;letter-spacing:1px">{cat}</div>',
            unsafe_allow_html=True,
        )

        _render_rows(actifs, cat, depenses, audit)

        if inactifs:
            n = len(inactifs)
            with st.expander(
                f"+ Définir un plafond pour {n} autre{'s' if n > 1 else ''} "
                f"sous-catégorie{'s' if n > 1 else ''}",
                expanded=False,
            ):
                _render_rows(inactifs, cat, depenses, audit)

        st.markdown("</div>", unsafe_allow_html=True)

    # ── All-inactive categories grouped in one "configure" expander ───────────
    if cats_inactives:
        nb_sous = sum(len(items) for items in cats_inactives.values())
        nb_cats = len(cats_inactives)
        with st.expander(
            f"Configurer d'autres plafonds — {nb_cats} catégorie{'s' if nb_cats > 1 else ''} "
            f"sans limite ({nb_sous} sous-catégorie{'s' if nb_sous > 1 else ''})",
            expanded=False,
        ):
            for cat, items in cats_inactives.items():
                st.markdown(
                    f'<div style="color:{T.PRIMARY};font-size:13px;font-weight:700;'
                    f'margin:12px 0 8px;text-transform:uppercase;letter-spacing:1px">{cat}</div>',
                    unsafe_allow_html=True,
                )
                _render_rows(items, cat, depenses, audit)

    st.divider()
    n_changes = len(st.session_state.plafond_changes)
    if n_changes > 0:
        st.info(f"{n_changes} modification(s) non sauvegardée(s) — cliquez sur 💾 Sauv. pour chaque ligne.")
