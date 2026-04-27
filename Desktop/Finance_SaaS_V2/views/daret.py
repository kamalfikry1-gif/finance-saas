"""
views/daret.py — Daret / Jam'iya Tracker.

Le Daret est une tontine marocaine : un groupe de personnes verse un montant
fixe chaque mois et à tour de rôle l'un d'eux reçoit toute la cagnotte.

Fonctionnalités :
    · Créer un daret (nom, montant, membres, date de début)
    · Voir qui reçoit la cagnotte ce mois
    · Avancer le tour
    · Voir la progression et le total épargné
    · Clôturer un daret terminé
"""

import json
from datetime import date, datetime
import streamlit as st
from components.design_tokens import T
from components.helpers import dh as _dh, render_page_header
from core.cache import get_darets as _get_darets


def render(ctx: dict) -> None:
    audit = ctx["audit"]

    render_page_header("🔄", "Daret & Tontine", "Gérez vos cercles d'épargne communautaire")

    # First-visit hint — explain the current solo Daret + V2 roadmap
    from components.hints import show_hint
    show_hint(
        audit,
        hint_id="hint_daret_solo_v1",
        title="Daret simplifié",
        body="Pour l'instant, tu logues manuellement qui a payé chaque mois. Une version multi-utilisateurs avec invite link et table partagée arrive plus tard.",
        icon="🔄",
    )

    try:
        darets = _get_darets(audit, audit.user_id)
    except Exception:
        st.warning("Impossible de charger les darets — réessayez dans quelques secondes.")
        return

    # ── Formulaire création ───────────────────────────────────────────────────
    with st.expander("➕ Nouveau Daret", expanded=(not darets)):
        _render_form_creation(audit)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if not darets:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:40px;text-align:center;margin-top:12px">'
            f'<div style="font-size:36px;margin-bottom:10px">🤝</div>'
            f'<div style="color:{T.TEXT_MED};font-size:14px;margin-bottom:6px">'
            f'Aucun daret actif.</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:12px">'
            f'Créez votre premier daret pour suivre votre tontine.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # ── Liste des darets actifs ───────────────────────────────────────────────
    for d in darets:
        _render_daret_card(audit, d)


def _render_form_creation(audit) -> None:
    """2-step wizard for creating a daret."""
    if "dr_wiz_step" not in st.session_state:
        st.session_state.dr_wiz_step = 1
    if "dr_wiz_data" not in st.session_state:
        st.session_state.dr_wiz_data = {}
    if "dr_wiz_done" not in st.session_state:
        st.session_state.dr_wiz_done = None

    # Success state — show invite link prominently
    if st.session_state.dr_wiz_done:
        _wiz_success(audit)
        return

    step = st.session_state.dr_wiz_step
    _wiz_progress(step, total=2)

    if step == 1:
        _wiz_step1(audit)
    elif step == 2:
        _wiz_step2(audit)


def _wiz_progress(step: int, total: int = 2) -> None:
    pct = int(step / total * 100)
    st.markdown(
        f'<div style="margin-bottom:14px">'
        f'  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">'
        f'    <span style="color:{T.TEXT_LOW};font-size:11px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1.5px">Étape {step} / {total}</span>'
        f'    <span style="color:{T.PRIMARY};font-size:11px;font-weight:700">{pct}%</span>'
        f'  </div>'
        f'  <div style="height:3px;background:{T.BG_INPUT};border-radius:99px;overflow:hidden">'
        f'    <div style="width:{pct}%;height:100%;background:{T.PRIMARY};'
        f'      transition:width 0.3s ease"></div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _wiz_step1(audit) -> None:
    d = st.session_state.dr_wiz_data

    st.markdown(
        f'<div style="color:{T.TEXT_HIGH};font-size:14px;font-weight:600;margin-bottom:8px">'
        f"⚙️ Configuration de base</div>",
        unsafe_allow_html=True,
    )

    nom = st.text_input(
        "Nom du daret",
        value=d.get("nom", ""),
        placeholder="ex: Daret Famille",
        key="dr_wiz_nom",
    )

    c1, c2 = st.columns(2)
    with c1:
        montant = st.number_input(
            "Cotisation mensuelle (DH)",
            min_value=1.0, step=100.0, format="%.0f",
            value=float(d.get("montant", 100.0) or 100.0),
            key="dr_wiz_montant",
        )
    with c2:
        nb = st.number_input(
            "Nombre de participants",
            min_value=2, max_value=20, step=1,
            value=int(d.get("nb", 5)),
            key="dr_wiz_nb",
        )

    date_debut = st.date_input(
        "Mois de début",
        value=d.get("date_debut", date.today()),
        key="dr_wiz_date",
    )

    if montant > 0 and nb >= 2:
        cagnotte = montant * nb
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_SM};padding:10px 14px;margin-top:8px">'
            f'  <div style="display:flex;justify-content:space-between">'
            f'    <span style="color:{T.TEXT_LOW};font-size:11px">'
            f"      {nb} mois × {nb} membres × {_dh(montant)} DH/mois"
            f'    </span>'
            f'    <span style="color:{T.PRIMARY};font-size:14px;font-weight:700">'
            f"      Cagnotte: {_dh(cagnotte)} DH"
            f'    </span>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    valid = bool(nom.strip()) and montant > 0 and nb >= 2

    if st.button("Suivant →", type="primary", use_container_width=True,
                 key="dr_wiz_s1_next", disabled=not valid):
        d["nom"]        = nom.strip()
        d["montant"]    = float(montant)
        d["nb"]         = int(nb)
        d["date_debut"] = date_debut
        st.session_state.dr_wiz_step = 2
        st.rerun()


def _wiz_step2(audit) -> None:
    d = st.session_state.dr_wiz_data
    nb = int(d.get("nb", 5))

    st.markdown(
        f'<div style="color:{T.TEXT_HIGH};font-size:14px;font-weight:600;margin-bottom:4px">'
        f"👥 Membres ({nb})</div>"
        f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-bottom:10px">'
        f"Tape le prénom (ou pseudo) de chaque participant."
        f"</div>",
        unsafe_allow_html=True,
    )

    # Init/grow names list to match nb
    membres = list(d.get("membres", []))
    while len(membres) < nb:
        membres.append("")
    membres = membres[:nb]

    # 2-column grid of name inputs
    placeholders = ["ex: Toi (Kamal)", "ex: Karim", "ex: Sara", "ex: Fatima",
                    "ex: Ali", "ex: Yassine", "ex: Amine", "ex: Hajar"]
    for i in range(0, nb, 2):
        cols = st.columns(2)
        with cols[0]:
            membres[i] = st.text_input(
                f"Membre {i+1}",
                value=membres[i] or "",
                placeholder=placeholders[i] if i < len(placeholders) else "",
                key=f"dr_wiz_membre_{i}",
            )
        if i + 1 < nb:
            with cols[1]:
                membres[i+1] = st.text_input(
                    f"Membre {i+2}",
                    value=membres[i+1] or "",
                    placeholder=placeholders[i+1] if i+1 < len(placeholders) else "",
                    key=f"dr_wiz_membre_{i+1}",
                )

    notes = st.text_input(
        "Notes (optionnel)",
        value=d.get("notes", ""),
        placeholder="ex: Daret familial — pour Aïd 2027",
        key="dr_wiz_notes",
    )

    tirage = st.checkbox(
        "🎲 Tirage au sort (ordre aléatoire des bénéficiaires)",
        value=d.get("tirage", True),
        key="dr_wiz_tirage",
        help="L'app mélange l'ordre avec un seed vérifiable. "
             "Décoche si tu as un ordre précis à respecter.",
    )

    valid = all(m.strip() for m in membres)
    if not valid:
        st.warning("⚠️ Tous les membres doivent avoir un nom.")

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← Retour", key="dr_wiz_s2_back", use_container_width=True):
            d["membres"] = membres
            d["notes"]   = notes
            d["tirage"]  = tirage
            st.session_state.dr_wiz_step = 1
            st.rerun()
    with c2:
        if st.button("Créer le daret →", type="primary",
                     use_container_width=True, key="dr_wiz_s2_create",
                     disabled=not valid):
            import random, secrets
            final = [m.strip() for m in membres]
            seed = None
            if tirage:
                seed = secrets.randbits(31)
                random.Random(seed).shuffle(final)

            result = audit.creer_daret(
                nom=d["nom"],
                montant_mensuel=float(d["montant"]),
                membres=final,
                date_debut=str(d["date_debut"]),
                notes=notes.strip(),
                tirage_seed=seed,
            )

            st.session_state.dr_wiz_done = {
                "nom":     d["nom"],
                "membres": final,
                "seed":    seed,
                "token":   (result or {}).get("invite_token", ""),
                "id":      (result or {}).get("id"),
            }
            st.rerun()


def _wiz_success(audit) -> None:
    info    = st.session_state.dr_wiz_done
    nom     = info.get("nom", "")
    membres = info.get("membres", [])
    seed    = info.get("seed")
    token   = info.get("token", "")

    st.markdown(
        f'<div style="text-align:center;padding:14px 0 10px">'
        f'  <div style="font-size:36px;margin-bottom:6px">🎉</div>'
        f'  <div style="color:{T.SUCCESS};font-size:16px;font-weight:700">'
        f"    Daret « {nom} » créé !</div>"
        f'</div>',
        unsafe_allow_html=True,
    )

    if seed:
        st.markdown(
            f'<div style="background:{T.PRIMARY_GLO};border-left:3px solid {T.PRIMARY};'
            f'padding:10px 14px;border-radius:{T.RADIUS_SM};margin-bottom:14px">'
            f'  <div style="color:{T.TEXT_HIGH};font-size:12px;margin-bottom:4px">'
            f"    🎲 Ordre tiré au sort (seed <code>{seed}</code>)"
            f'  </div>'
            f'  <div style="color:{T.TEXT_MED};font-size:11px">'
            f"    {' → '.join(membres)}"
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if token:
        st.markdown(
            f'<div style="color:{T.TEXT_HIGH};font-size:13px;font-weight:600;margin-bottom:6px">'
            f"📋 Lien d'invitation à partager :"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.code(f"?daret={token}", language=None)
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-bottom:14px">'
            f"Ajoute ce paramètre à l'URL de l'app puis partage le lien complet "
            f"dans ton groupe WhatsApp. Toi seul peux marquer les paiements."
            f"</div>",
            unsafe_allow_html=True,
        )

    if st.button("➕ Créer un autre daret", key="dr_wiz_again",
                 use_container_width=True, type="secondary"):
        for k in ("dr_wiz_step", "dr_wiz_data", "dr_wiz_done"):
            st.session_state.pop(k, None)
        # Also clear the field-level keys so the form starts fresh
        for k in list(st.session_state.keys()):
            if k.startswith("dr_wiz_membre_") or k in (
                "dr_wiz_nom", "dr_wiz_montant", "dr_wiz_nb",
                "dr_wiz_date", "dr_wiz_notes", "dr_wiz_tirage",
            ):
                st.session_state.pop(k, None)
        st.rerun()


def _render_daret_card(audit, d: dict) -> None:
    nom         = d.get("Nom", "—")
    montant     = float(d.get("Montant_Mensuel", 0))
    nb          = int(d.get("Nb_Membres", 1)) or 1
    tour        = int(d.get("Tour_Actuel", 0))
    date_debut  = d.get("Date_Debut", "")[:10]
    notes       = d.get("Notes", "") or ""
    daret_id    = d.get("id")

    try:
        membres = json.loads(d.get("Membres_JSON", "[]"))
    except (json.JSONDecodeError, TypeError):
        membres = []

    if not membres:
        membres = [f"Membre {i+1}" for i in range(nb)]

    tour_idx   = tour % len(membres)
    beneficiaire = membres[tour_idx]
    cagnotte   = montant * nb
    total_verse = montant * tour        # what the group has paid in total so far
    tours_rest = len(membres) - tour_idx - 1

    # Progress through the cycle
    pct = (tour_idx / len(membres)) * 100

    # Is it my turn?
    mon_nom    = membres[0]  # convention: first member = "toi"
    mon_tour   = (tour_idx == 0)

    couleur = T.SUCCESS if mon_tour else T.PRIMARY

    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-left:3px solid {couleur};border-radius:{T.RADIUS_LG};'
        f'padding:20px;margin-bottom:14px">',
        unsafe_allow_html=True,
    )

    # Header
    h1, h2 = st.columns([3, 1])
    with h1:
        seed = d.get("Tirage_Seed")
        seed_html = (
            f' · <span style="color:{T.PRIMARY}" '
            f'title="Vérifiable: random.Random({seed}).shuffle(membres) reproduit cet ordre">'
            f'🎲 tirage seed {seed}</span>'
        ) if seed else ""
        st.markdown(
            f'<div style="color:{T.TEXT_HIGH};font-weight:800;font-size:16px">'
            f'🔄 {nom}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
            f'{nb} membres · {_dh(montant)} DH/mois · début {date_debut}{seed_html}</div>',
            unsafe_allow_html=True,
        )
    with h2:
        st.markdown(
            f'<div style="text-align:right">'
            f'<div style="color:{couleur};font-weight:900;font-size:20px">{_dh(cagnotte)}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:10px">cagnotte du mois</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Beneficiary this month
    badge_color = T.SUCCESS if mon_tour else T.WARNING
    badge_text  = "🎉 C'est TON tour !" if mon_tour else f"👤 Ce mois : {beneficiaire}"
    st.markdown(
        f'<div style="background:{badge_color}18;border:1px solid {badge_color}40;'
        f'border-radius:{T.RADIUS_MD};padding:10px 14px;margin:12px 0;'
        f'color:{badge_color};font-weight:700;font-size:13px">{badge_text}</div>',
        unsafe_allow_html=True,
    )

    # Progress bar through cycle
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;'
        f'color:{T.TEXT_LOW};font-size:10px;margin-bottom:4px">'
        f'<span>Tour {tour_idx + 1} / {len(membres)}</span>'
        f'<span>{tours_rest} tour(s) restant(s)</span>'
        f'</div>'
        f'<div style="background:{T.BORDER};border-radius:{T.RADIUS_PILL};'
        f'height:6px;overflow:hidden;margin-bottom:12px">'
        f'<div style="width:{pct:.1f}%;height:6px;background:{couleur};'
        f'border-radius:{T.RADIUS_PILL}"></div></div>',
        unsafe_allow_html=True,
    )

    # Members list
    pills_html = ""
    for i, m in enumerate(membres):
        idx = i
        is_done    = (idx < tour_idx)
        is_current = (idx == tour_idx)
        bg    = T.SUCCESS    if is_done    else (T.PRIMARY if is_current else T.BG_CARD_ALT)
        col   = T.TEXT_HIGH  if is_current else (T.TEXT_MED if not is_done else T.TEXT_LOW)
        check = "✓ " if is_done else ("▶ " if is_current else "")
        pills_html += (
            f'<span style="background:{bg}22;color:{col};'
            f'font-size:11px;padding:3px 9px;border-radius:{T.RADIUS_PILL};'
            f'margin:2px;border:1px solid {bg}44;display:inline-block">'
            f'{check}{m}</span>'
        )

    st.markdown(
        f'<div style="margin-bottom:12px">{pills_html}</div>',
        unsafe_allow_html=True,
    )

    if notes:
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:11px;font-style:italic;'
            f'margin-bottom:10px">{notes}</div>',
            unsafe_allow_html=True,
        )

    # ── Intelligence ──────────────────────────────────────────────────────────
    if mon_tour:
        st.markdown(
            f'<div style="background:{T.SUCCESS}15;border:1px solid {T.SUCCESS}40;'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-bottom:10px;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="color:{T.SUCCESS};font-weight:700;font-size:13px">'
            f'🎉 C\'est ton tour — tu reçois la cagnotte !</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
            f'Pense à le placer sur un objectif ou en épargne.</div>'
            f'</div>'
            f'<div style="color:{T.SUCCESS};font-size:22px;font-weight:900">'
            f'{_dh(cagnotte)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("🎯 Placer en objectif", key=f"dr_obj_now_{daret_id}",
                     use_container_width=True, type="secondary"):
            try:
                date_cible = date.today().replace(day=28).isoformat()
                audit.creer_objectif_v2(
                    nom=f"Cagnotte Daret — {nom}",
                    type_obj="EPARGNE",
                    montant_cible=cagnotte,
                    date_cible=date_cible,
                )
                st.success(f"✅ Objectif créé — {_dh(cagnotte)}")
            except Exception:
                st.error("Impossible de créer l'objectif — réessayez.")
    else:
        tours_until_mine = len(membres) - tour_idx
        monthly_needed   = round(cagnotte / tours_until_mine) if tours_until_mine > 0 else 0
        st.markdown(
            f'<div style="background:{T.PRIMARY}10;border:1px solid {T.PRIMARY}30;'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin-bottom:10px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="color:{T.PRIMARY};font-weight:700;font-size:13px">'
            f'⏳ Ton tour dans {tours_until_mine} mois</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
            f'Mets de côté <b style="color:{T.TEXT_HIGH}">{_dh(monthly_needed)}/mois</b> '
            f'pour être prêt à recevoir la cagnotte.</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div style="color:{T.TEXT_HIGH};font-size:18px;font-weight:900">'
            f'{_dh(cagnotte)}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:10px">à recevoir</div>'
            f'</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("🎯 Créer objectif Daret", key=f"dr_obj_{daret_id}",
                     use_container_width=True, type="secondary"):
            try:
                from datetime import date as _date
                from dateutil.relativedelta import relativedelta
                date_cible = (_date.today() + relativedelta(months=tours_until_mine)).isoformat()
                audit.creer_objectif_v2(
                    nom=f"Daret — {nom} (dans {tours_until_mine} mois)",
                    type_obj="EPARGNE",
                    montant_cible=cagnotte,
                    date_cible=date_cible,
                )
                from core.cache import invalider as _inv
                _inv()
                st.success(f"✅ Objectif créé — {_dh(cagnotte)} dans {tours_until_mine} mois")
            except Exception:
                st.error("Impossible de créer l'objectif — réessayez.")

    # Actions
    confirm_next  = st.session_state.get(f"dr_confirm_next_{daret_id}", False)
    confirm_close = st.session_state.get(f"dr_confirm_close_{daret_id}", False)

    if confirm_next:
        st.warning(f"Passer au tour suivant ? **{beneficiaire}** ne sera plus bénéficiaire.")
        ca, cb, _ = st.columns([1, 1, 3])
        with ca:
            if st.button("✅ Confirmer", key=f"dr_next_ok_{daret_id}",
                         use_container_width=True, type="primary"):
                audit.avancer_tour_daret(daret_id)
                st.session_state[f"dr_confirm_next_{daret_id}"] = False
                st.rerun()
        with cb:
            if st.button("❌ Annuler", key=f"dr_next_no_{daret_id}", use_container_width=True):
                st.session_state[f"dr_confirm_next_{daret_id}"] = False
                st.rerun()
    elif confirm_close:
        st.warning(f"Clôturer le daret **{nom}** ? Cette action est irréversible.")
        ca, cb, _ = st.columns([1, 1, 3])
        with ca:
            if st.button("✅ Clôturer", key=f"dr_close_ok_{daret_id}",
                         use_container_width=True, type="primary"):
                audit.cloturer_daret(daret_id)
                st.session_state[f"dr_confirm_close_{daret_id}"] = False
                st.rerun()
        with cb:
            if st.button("❌ Annuler", key=f"dr_close_no_{daret_id}", use_container_width=True):
                st.session_state[f"dr_confirm_close_{daret_id}"] = False
                st.rerun()
    else:
        ba, bb, _ = st.columns([1, 1, 3])
        with ba:
            if st.button("▶ Tour suivant", key=f"dr_next_{daret_id}",
                         use_container_width=True, type="primary"):
                st.session_state[f"dr_confirm_next_{daret_id}"] = True
                st.rerun()
        with bb:
            if st.button("Clôturer", key=f"dr_close_{daret_id}",
                         use_container_width=True, type="secondary"):
                st.session_state[f"dr_confirm_close_{daret_id}"] = True
                st.rerun()

    # ── Bloomberg-style status table + invite link ──────────────────────────
    _render_bloomberg_table(audit, d, membres)
    _render_invite_link(d)


# ── Bloomberg per-month-per-member status table ─────────────────────────────
STATUS_CYCLE = {None: "DECLARED", "PENDING": "DECLARED", "DECLARED": "PAID", "PAID": "PENDING"}
STATUS_EMOJI = {None: "🔴", "PENDING": "🔴", "DECLARED": "🟡", "PAID": "🟢"}
STATUS_LABEL = {None: "En attente", "PENDING": "En attente",
                "DECLARED": "Déclaré", "PAID": "Payé"}


def _generate_months(date_debut_str: str, nb_mois: int) -> list:
    """Generate `nb_mois` consecutive 'MM/YYYY' strings starting from date_debut."""
    try:
        d = datetime.strptime(date_debut_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        d = date.today()
    out = []
    yr, mo = d.year, d.month
    for _ in range(nb_mois):
        out.append(f"{mo:02d}/{yr}")
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1
    return out


def _render_bloomberg_table(audit, d: dict, membres: list, editable: bool = True) -> None:
    """Members × months payment status grid. Manager (editable=True) clicks
    cells to cycle through PENDING → DECLARED → PAID → PENDING."""
    daret_id = d.get("id")
    if not daret_id or not membres:
        return

    months = _generate_months(d.get("Date_Debut", "") or "", len(membres))
    statuts = audit.db.get_daret_statuts(daret_id)

    st.markdown(
        f'<div style="margin-top:14px;color:{T.TEXT_LOW};font-size:10px;'
        f'font-weight:700;text-transform:uppercase;letter-spacing:1.2px;'
        f'margin-bottom:8px">📊 Tableau de paiements'
        f'  <span style="color:{T.TEXT_MED};font-weight:400;text-transform:none;'
        f'    margin-left:8px">🟢 payé · 🟡 déclaré · 🔴 en attente</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Header row: Membre + months
    h_cols = st.columns([2] + [1] * len(months))
    with h_cols[0]:
        st.markdown(
            f'<div style="color:{T.TEXT_MED};font-size:11px;font-weight:600;'
            f'padding:6px 0">Membre</div>',
            unsafe_allow_html=True,
        )
    for i, m in enumerate(months):
        with h_cols[i + 1]:
            st.markdown(
                f'<div style="text-align:center;color:{T.TEXT_MED};font-size:10px;'
                f'font-weight:600;padding:6px 0">{m}</div>',
                unsafe_allow_html=True,
            )

    # Row per member
    for membre in membres:
        cols = st.columns([2] + [1] * len(months))
        with cols[0]:
            st.markdown(
                f'<div style="color:{T.TEXT_HIGH};font-size:13px;'
                f'padding:8px 0">{membre}</div>',
                unsafe_allow_html=True,
            )
        for i, mois in enumerate(months):
            current = statuts.get(mois, {}).get(membre)
            emoji   = STATUS_EMOJI.get(current, "🔴")
            with cols[i + 1]:
                if editable:
                    if st.button(
                        emoji,
                        key=f"dr_cell_{daret_id}_{i}_{membre}",
                        help=f"{membre} · {mois} : {STATUS_LABEL.get(current)} (clic pour changer)",
                        use_container_width=True,
                    ):
                        new = STATUS_CYCLE.get(current, "DECLARED")
                        audit.db.update_daret_statut(daret_id, mois, membre, new)
                        st.rerun()
                else:
                    st.markdown(
                        f'<div style="text-align:center;font-size:18px;padding:6px 0">'
                        f'{emoji}</div>',
                        unsafe_allow_html=True,
                    )


def _render_invite_link(d: dict) -> None:
    """Display the public invite token + URL helper."""
    token = d.get("invite_token") or ""
    if not token:
        return
    with st.expander("📋 Lien d'invitation pour le groupe", expanded=False):
        st.markdown(
            f'<div style="color:{T.TEXT_MED};font-size:12px;line-height:1.5;margin-bottom:10px">'
            f"Partage ce lien dans ton groupe WhatsApp. Toute personne avec le lien "
            f"verra la table en lecture seule. Toi seul peux marquer les paiements."
            f'</div>',
            unsafe_allow_html=True,
        )
        st.code(f"?daret={token}", language=None)
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:6px">'
            f"💡 Ajoute ce paramètre à l'URL de l'app puis copie le lien complet "
            f"(ex: <code>https://ton-app.streamlit.app/?daret={token[:6]}…</code>)."
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
