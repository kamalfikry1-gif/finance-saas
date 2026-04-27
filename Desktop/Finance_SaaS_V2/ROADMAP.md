# Roadmap — Path to 85% beta

**Status**: ~85% in code · target = **shipping private beta**
**Project started**: 2026-04-06
**Realistic beta date**: ~2 weeks if Sprint 4 (testing) starts soon

---

## 📍 Definition of beta-ready

- Every user flow works end-to-end without `[À écrire]` placeholders or known bugs
- 5 real users (friends/family) can sign up, onboard, log a week of expenses, and understand their score **without you guiding them**
- All pages have consistent UX (typography, spacing, colors)
- No TODO left in the critical user path

Anything beyond is **post-beta v2** → goes to `BACKLOG.md`.

---

## 🔄 What's left to ship beta

### A. Sprint 2 polish remaining (small, ~1 session)
- [ ] Onboarding "abonnement detection" popup (when user adds a duplicate sub-cat)
- [ ] Mini-onboarding catch-up flow (when `jours_inactif ≥ 7`)
- [ ] Dashboard preview screen before "Découvrir l'app" in onboarding
- [ ] Reference points on estimation sliders ("Moyenne MA pour ce revenu = X DH")
- [ ] Delete legacy `views/onboarding.py` (kept as `?onboarding=v1` fallback for now)
- [ ] Bonus: enrich the 5 status messages with 3-part structure (Diagnostic / Plan / Vision)

### B. Sprint 4 — Bug bash + 5 real users (the real work, ~1 week)
- [ ] Use the app yourself daily for 7 days, log everything
- [ ] Recruit 5 beta users (friends, family)
- [ ] Watch each one onboard (no guidance) — note every friction point
- [ ] Fix ONLY what real users trip on (not imagined issues)
- [ ] Final UX consistency pass across all 9 pages
- [ ] Ship beta 🚀

---

## ✅ Already shipped (24 days, 2026-04-06 → today)

**Foundation**
- PostgreSQL multi-tenant (15 tables), bcrypt auth, Streamlit Cloud deploy
- Custom design system (T tokens, dark theme, 5 color zones)
- Audit middleware (gateway, validator, anomaly, snapshot, query, anticipation)
- 5-factor scoring engine (`core/assistant_engine.compute_score`)
- Coach message library — **24/24 messages written**, light + honest + encouraging
- Badges + hints persistence (`core/badges.py`, `core/hints.py`)

**UX system**
- Topbar (🏠 Dépense · Revenu · Moi · Historique · Mois · Année)
- Sidebar (logo + Paramètres + 8 nav items + + Transaction form)
- Hero + KPI strip with monthly sparkline
- Categories drill-down (expandable + grocery sub-cat quick-pick after merchant transactions)
- Coach panel (5 sections: header / score / message / objectif / épargne libre breakdown)

**Pages built (10)**
Accueil · Historique · **Tendances** · Journal · Objectif · Épargne · Plafond · **Daret (+public read-only view)** · Mon compte · Assistant · Onboarding v2

**Mon compte** — name/email/password change · data export (JSON) · delete account · fonds d'urgence target customization · 50/30/20 category overrides

**Tendances** — KPI strip · cashflow up/down monthly bars · velocity (daily avg + safe-to-spend) · subscription leakage · top 3 lists · 3/6/12 month selector

**Daret v1.5** — 2-step creation wizard · tirage au sort with verifiable seed · Bloomberg-style status table · invite token + public read-only view at `?daret=TOKEN`

**6 contextual hints** sprinkled across the app (Accueil welcome / coach panel / categories / topbar / Plafond / Daret)

**Admin** — DICO CRUD · Référentiel · A_Classifier · Audit Log · 🚨 Reset (test) tab

---

## 🚦 Discipline rules

1. **One sprint focus per week.** Anything off-sprint goes straight to `BACKLOG.md`.
2. **Lead messages with `[Sprint N]`** when starting a session — keeps both of us aligned.
3. **Friday review, no code.** Look at sprint, tick what's done, plan next.
4. **Define "done" before starting** each task. Don't move on until truly done.

---

## ✋ Definition of done (per task)

A task is **done** when:
- Code shipped and pushed
- Manually verified on Streamlit Cloud (not just locally)
- No `[À écrire]` or `# TODO` left in the changed files
- Doesn't break any previously-shipped feature
