"""
views/admin.py — Page d'administration (is_admin=True uniquement).

Tabs :
  1. DICO_MATCHING   — CRUD sur le dictionnaire de classification partagé
  2. RÉFÉRENTIEL     — Lecture seule des stats de fréquence par catégorie
  3. À Classifier    — Vue globale (tous users) des mots-clés inconnus
"""

import streamlit as st
from components.design_tokens import T
from components.helpers import render_page_header
from core.cache import invalider as _invalider_cache


# ── Gate ─────────────────────────────────────────────────────────────────────

def render(ctx: dict) -> None:
    if not st.session_state.get("is_admin"):
        st.error("Accès refusé.")
        st.stop()

    db    = ctx["audit"].db
    audit = ctx["audit"]

    render_page_header("⚙️", "Administration", "Gestion des données et règles")

    tab_dico, tab_ref, tab_clf, tab_log = st.tabs([
        "📖 DICO_MATCHING", "📊 Référentiel",
        "🔍 À Classifier (global)", "📋 Audit Log"
    ])

    with tab_dico:
        _render_dico(db, audit)

    with tab_ref:
        _render_referentiel(db)

    with tab_clf:
        _render_classifier_global(db, audit)

    with tab_log:
        _render_audit_log(db)


# ── Tab 1 : DICO_MATCHING ────────────────────────────────────────────────────

def _render_dico(db, audit) -> None:
    st.markdown(
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:12px">'
        f'Dictionnaire partagé entre tous les utilisateurs. '
        f'Chaque entrée mappe un mot-clé → catégorie.</p>',
        unsafe_allow_html=True,
    )

    # ── Formulaire d'ajout ────────────────────────────────────────────────────
    with st.expander("➕ Ajouter une entrée", expanded=False):
        a1, a2 = st.columns(2)
        with a1:
            new_mot = st.text_input("Mot-clé", placeholder="ex: CARREFOUR",
                                    key="adm_new_mot").strip().upper()
        with a2:
            new_sens = st.selectbox("Sens", ["OUT", "IN"], key="adm_new_sens")

        all_cats  = _get_cats(audit)
        a3, a4 = st.columns(2)
        with a3:
            new_cat = st.selectbox("Catégorie", all_cats, key="adm_new_cat")
        with a4:
            scats   = _get_scats(audit, new_cat)
            new_scat = st.selectbox("Sous-catégorie", scats or ["—"],
                                    key="adm_new_scat")

        if st.button("Ajouter", type="primary", key="adm_add"):
            if not new_mot:
                st.warning("Mot-clé requis.")
            else:
                ok = db.add_dico_entry(new_sens, new_mot, new_cat, new_scat)
                if ok:
                    st.success(f"✅ '{new_mot}' ajouté → {new_cat} / {new_scat}")
                    _invalider_cache()
                    st.rerun()
                else:
                    st.error("Entrée déjà existante pour ce mot-clé + sens.")

    # ── Recherche ─────────────────────────────────────────────────────────────
    search = st.text_input("🔍 Rechercher un mot-clé", placeholder="ex: MARJANE",
                           key="adm_search", label_visibility="collapsed")
    entries = db.get_all_dico(search)

    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-bottom:8px">'
        f'{len(entries)} entrée(s)</div>',
        unsafe_allow_html=True,
    )

    if not entries:
        st.info("Aucun résultat.")
        return

    all_cats  = _get_cats(audit)

    for e in entries:
        eid   = e.get("id")
        sens  = e.get("Sens", "OUT")
        mot   = e.get("Mot_Cle", "")
        cat   = e.get("Categorie_Cible", "")
        scat  = e.get("Sous_Categorie_Cible", "")
        sc    = T.DANGER if sens == "OUT" else T.SUCCESS

        row_key = f"dico_{eid}"
        editing = st.session_state.get(f"adm_edit_{eid}", False)
        confirm_del = st.session_state.get(f"adm_del_{eid}", False)

        if confirm_del:
            st.warning(f"Supprimer **{mot}** ({sens}) ?")
            cd1, cd2, _ = st.columns([1, 1, 4])
            with cd1:
                if st.button("✅ Oui", key=f"adm_del_ok_{eid}", type="primary",
                             use_container_width=True):
                    db.delete_dico_entry(eid)
                    st.session_state[f"adm_del_{eid}"] = False
                    _invalider_cache()
                    st.rerun()
            with cd2:
                if st.button("❌ Non", key=f"adm_del_no_{eid}",
                             use_container_width=True):
                    st.session_state[f"adm_del_{eid}"] = False
                    st.rerun()
            continue

        if editing:
            with st.container():
                st.markdown(
                    f'<div style="background:{T.BG_CARD_ALT};border:1px solid'
                    f' {T.BORDER_MED};border-radius:{T.RADIUS_MD};'
                    f'padding:12px 16px;margin-bottom:4px">',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<span style="color:{T.TEXT_HIGH};font-weight:700">{mot}</span>'
                    f' <span style="color:{sc};font-size:11px">{sens}</span>',
                    unsafe_allow_html=True,
                )
                ec1, ec2 = st.columns(2)
                with ec1:
                    cat_idx  = all_cats.index(cat) if cat in all_cats else 0
                    edit_cat = st.selectbox("Catégorie", all_cats, index=cat_idx,
                                           key=f"adm_ecat_{eid}")
                with ec2:
                    escats    = _get_scats(audit, edit_cat)
                    scat_idx  = escats.index(scat) if scat in escats else 0
                    edit_scat = st.selectbox("Sous-catégorie", escats or ["—"],
                                            index=scat_idx, key=f"adm_escat_{eid}")
                ea, eb = st.columns(2)
                with ea:
                    if st.button("💾 Enregistrer", key=f"adm_save_{eid}",
                                 type="primary", use_container_width=True):
                        db.update_dico_entry(eid, edit_cat, edit_scat)
                        st.session_state[f"adm_edit_{eid}"] = False
                        _invalider_cache()
                        st.rerun()
                with eb:
                    if st.button("❌ Annuler", key=f"adm_ecancel_{eid}",
                                 use_container_width=True):
                        st.session_state[f"adm_edit_{eid}"] = False
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
            continue

        # Normal row
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:10px 16px;margin-bottom:4px;'
            f'display:flex;align-items:center;gap:12px">'
            f'<span style="background:{sc}20;color:{sc};font-size:10px;'
            f'padding:2px 7px;border-radius:{T.RADIUS_PILL};font-weight:700;'
            f'flex-shrink:0">{sens}</span>'
            f'<span style="color:{T.TEXT_HIGH};font-weight:600;font-size:13px;'
            f'flex:1">{mot}</span>'
            f'<span style="color:{T.TEXT_MED};font-size:12px">{cat}</span>'
            f'<span style="color:{T.TEXT_LOW};font-size:11px;min-width:60px;'
            f'text-align:right">{scat}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        ba, bb = st.columns([1, 1])
        with ba:
            if st.button("✏️", key=f"adm_edit_btn_{eid}", use_container_width=True):
                st.session_state[f"adm_edit_{eid}"] = True
                st.rerun()
        with bb:
            if st.button("🗑️", key=f"adm_del_btn_{eid}", use_container_width=True):
                st.session_state[f"adm_del_{eid}"] = True
                st.rerun()


# ── Tab 2 : RÉFÉRENTIEL ───────────────────────────────────────────────────────

def _render_referentiel(db) -> None:
    st.markdown(
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:12px">'
        f'Statistiques de fréquence par catégorie — lecture seule.</p>',
        unsafe_allow_html=True,
    )

    rows = db.get_referentiel()
    if not rows:
        st.info("Référentiel vide.")
        return

    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-bottom:8px">'
        f'{len(rows)} catégorie(s)</div>',
        unsafe_allow_html=True,
    )

    for r in rows:
        cat   = r.get("Categorie", "")
        scat  = r.get("Sous_Categorie", "")
        sens  = r.get("Sens", "OUT")
        freq  = r.get("Frequence", "")
        ctn   = int(r.get("Compteur_N", 0) or 0)
        cumul = float(r.get("Montant_Cumule", 0) or 0)
        sc    = T.DANGER if sens == "OUT" else T.SUCCESS

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:10px 16px;margin-bottom:4px;'
            f'display:flex;align-items:center;gap:12px">'
            f'<span style="background:{sc}20;color:{sc};font-size:10px;'
            f'padding:2px 7px;border-radius:{T.RADIUS_PILL};font-weight:700;'
            f'flex-shrink:0">{sens}</span>'
            f'<span style="color:{T.TEXT_HIGH};font-size:13px;flex:1">'
            f'{cat} / {scat}</span>'
            f'<span style="color:{T.TEXT_MED};font-size:11px">{freq}</span>'
            f'<span style="color:{T.TEXT_LOW};font-size:11px">{ctn}× · '
            f'{cumul:,.0f} DH</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Tab 3 : A_CLASSIFIER global ───────────────────────────────────────────────

def _render_classifier_global(db, audit) -> None:
    st.markdown(
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:12px">'
        f'Mots-clés inconnus de tous les utilisateurs. '
        f'Promouvoir un mot-clé l\'ajoute au dictionnaire partagé (DICO_MATCHING).</p>',
        unsafe_allow_html=True,
    )

    rows = db.get_all_a_classifier_global()
    if not rows:
        st.success("✅ Aucun mot-clé inconnu en attente.")
        return

    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-bottom:8px">'
        f'{len(rows)} mot(s)-clé(s) en attente</div>',
        unsafe_allow_html=True,
    )

    all_cats = _get_cats(audit)

    for r in rows:
        mot      = r.get("Mot_Cle_Inconnu", "")
        sens     = r.get("Sens", "OUT")
        nb       = int(r.get("Nb_Occurrences", 1))
        username = r.get("username", "?")
        auto_cat = r.get("Categorie_Auto", "")
        auto_scat = r.get("Sous_Categorie_Auto", "")
        sc = T.DANGER if sens == "OUT" else T.SUCCESS

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-bottom:4px">',
            unsafe_allow_html=True,
        )
        h1, h2 = st.columns([3, 1])
        with h1:
            st.markdown(
                f'<span style="color:{T.TEXT_HIGH};font-weight:700;font-size:13px">'
                f'{mot}</span>'
                f' <span style="background:{sc}20;color:{sc};font-size:10px;'
                f'padding:2px 7px;border-radius:{T.RADIUS_PILL};font-weight:700">'
                f'{sens}</span>',
                unsafe_allow_html=True,
            )
        with h2:
            st.markdown(
                f'<div style="text-align:right;color:{T.TEXT_LOW};font-size:11px">'
                f'{nb}× · {username}</div>',
                unsafe_allow_html=True,
            )

        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        with c1:
            cat_idx = all_cats.index(auto_cat) if auto_cat in all_cats else 0
            p_cat   = st.selectbox("Catégorie", all_cats, index=cat_idx,
                                   key=f"gadm_cat_{mot}_{sens}")
        with c2:
            scats   = _get_scats(audit, p_cat)
            scat_idx = scats.index(auto_scat) if auto_scat in scats else 0
            p_scat  = st.selectbox("Sous-catégorie", scats or ["—"],
                                   index=scat_idx, key=f"gadm_scat_{mot}_{sens}")
        with c3:
            if st.button("📖 Promouvoir", key=f"gadm_ok_{mot}_{sens}",
                         type="primary", use_container_width=True):
                db.promote_to_dico(mot, sens, p_cat, p_scat)
                _invalider_cache()
                st.success(f"'{mot}' ajouté au dictionnaire.")
                st.rerun()
        with c4:
            if st.button("Ignorer", key=f"gadm_skip_{mot}_{sens}",
                         use_container_width=True):
                with db.connexion() as conn:
                    conn.execute(
                        "UPDATE A_CLASSIFIER SET Enrichi=1"
                        " WHERE Mot_Cle_Inconnu=%s AND Sens=%s",
                        (mot, sens),
                    )
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# ── Tab 4 : Audit Log ────────────────────────────────────────────────────────

def _render_audit_log(db) -> None:
    st.markdown(
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:12px">'
        f'Journal immutable de toutes les actions — 200 dernières entrées.</p>',
        unsafe_allow_html=True,
    )

    rows = db.get_audit_log(limit=200)
    if not rows:
        st.info("Aucune entrée dans l'audit log.")
        return

    STATUT_COLOR = {
        "OK":     T.SUCCESS,
        "WARN":   T.WARNING,
        "ERREUR": T.DANGER,
        "BLOQUE": T.DANGER,
    }

    for r in rows:
        ts      = str(r.get("Timestamp", ""))[:19]
        role    = r.get("Role", "")
        action  = r.get("Action", "")
        methode = r.get("Methode") or ""
        score   = r.get("Score")
        statut  = r.get("Statut", "OK")
        user    = r.get("username") or "—"
        color   = STATUT_COLOR.get(statut, T.TEXT_LOW)

        score_html = (
            f'<span style="color:{T.TEXT_MED};font-size:10px;margin-left:8px">'
            f'score {float(score):.0f}</span>'
            if score is not None else ""
        )
        methode_html = (
            f'<span style="color:{T.TEXT_LOW};font-size:10px;margin-left:8px">'
            f'{methode}</span>'
            if methode else ""
        )

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-left:3px solid {color};border-radius:{T.RADIUS_MD};'
            f'padding:8px 14px;margin-bottom:4px;'
            f'display:flex;align-items:center;gap:10px">'
            f'<span style="color:{T.TEXT_LOW};font-size:10px;white-space:nowrap">{ts}</span>'
            f'<span style="background:{color}20;color:{color};font-size:10px;'
            f'padding:1px 7px;border-radius:{T.RADIUS_PILL};font-weight:700;'
            f'flex-shrink:0">{statut}</span>'
            f'<span style="color:{T.TEXT_MED};font-size:11px;flex-shrink:0">{role}</span>'
            f'<span style="color:{T.TEXT_HIGH};font-size:12px;font-weight:600;flex:1">'
            f'{action}</span>'
            f'{methode_html}{score_html}'
            f'<span style="color:{T.TEXT_LOW};font-size:10px;'
            f'white-space:nowrap">👤 {user}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_cats(audit) -> list:
    from core.cache import get_categories
    return get_categories(audit, audit.user_id)


def _get_scats(audit, cat: str) -> list:
    from core.cache import get_sous_categories
    return get_sous_categories(audit, cat, audit.user_id)
