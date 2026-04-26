# Roadmap — Finance SaaS V2

**Status**: 75% → target **85% (private beta-ready)**
**Project started**: 2026-04-06
**Target beta launch**: ~2026-05-24 (4 sprints)

---

## 📍 Definition of "85%"

Private beta-ready means:
- Every user flow works end-to-end without `[À écrire]` placeholders or known bugs
- 5 real users (friends/family) can sign up, onboard, log a week of expenses, and understand their score **without you guiding them**
- All 9 pages have consistent UX (typography, spacing, colors)
- No TODO left in the critical user path

Anything beyond is **post-beta v2** → goes to `BACKLOG.md`.

---

## 🔄 CURRENT SPRINT: 1 — Wire the brain + clean up

**Started**: _(set when you start)_
**Target end**: 1 week from start

- [x] Built scoring engine v2 (`core/assistant_engine.py:compute_score`)
- [x] Created `coach_messages.py` table (24 entries)
- [x] Created `BACKLOG.md`
- [x] Created `ROADMAP.md`
- [x] Wire `compute_score()` into accueil coach panel (replace v1)
- [x] Display 5 statuts (CRITIQUE/FAIBLE/MOYEN/BON/EXCELLENT) with proper colors
- [ ] Show factor breakdown on score click (transparency = trust)
- [ ] **Consolidate Objectif Dépense → Plafond** (delete duplicate page)
- [ ] End-of-sprint review Friday (no code)

---

## 📅 4-sprint plan

### Sprint 1 — Wire the brain + clean up _(current)_
See "CURRENT SPRINT" above.

### Sprint 2 — Onboarding wizard v2 + coach copy
- [x] Wizard v2 shell + badges/hints foundations (commit 1)
- [x] Wizard v2 full content: 4 steps, real récurrents form, 4 sliders, score reveal (commit 2)
- [ ] Sprinkle 6 hints throughout app + delete legacy onboarding (commit 3)
- [ ] Replace all `[À écrire]` in `core/coach_messages.py` (24 messages)
- [ ] Add "abonnement detection" popup on duplicate sub-categories
- [ ] Build mini-onboarding catch-up flow (when `jours_inactif >= 7`)

### Sprint 3 — Mon compte + month visibility lite
- [ ] Mon compte: real name, email, change password (bcrypt-aware)
- [ ] Mon compte: delete account flow (with confirmation)
- [ ] Mon compte: data export button (trust signal)
- [ ] Customizable: fonds d'urgence target (default 3 mois)
- [ ] Customizable: 50/30/20 category overrides UI
- [ ] Month visibility: monthly sparkline (replace 7-day flux)
- [ ] Month visibility: monthly cashflow chart (revenus up / dépenses down)

### Sprint 4 — Bug bash + 5 real users
- [ ] Use the app yourself daily for 7 days, log everything
- [ ] Recruit 5 beta users (friends, family)
- [ ] Watch each one onboard (no guidance) — note every friction point
- [ ] Fix ONLY what real users trip on (not imagined issues)
- [ ] Final UX consistency pass across all 9 pages
- [ ] Ship beta 🚀

---

## ✅ Already shipped (3 weeks, 2026-04-06 → 2026-04-26)

**Foundation**
- PostgreSQL multi-tenant (15 tables), bcrypt auth, deployed on Streamlit Cloud
- Custom design system (T tokens, dark theme, 5 color zones)
- Audit middleware (gateway, validator, anomaly detector, snapshot, query, anticipation)

**UX system**
- Topbar (Dépense / Revenu / Moi / Historique / Mois / Année + 🏠)
- Sidebar (logo + Paramètres + nav + + Transaction form)
- Hero + KPI strip (1 unified card with sparkline bg)
- Categories drill-down (flat cards + expandable sub-categories)
- Coach panel (5 sections: header / score / message / objectif / épargne)

**Brain**
- 5-factor scoring engine (`compute_score`) with edge cases (reste négatif cap, first-month grace, stale flag)
- 50/30/20 default category mapping in `config.py`
- Coach message table (24 entries, priority-based selector)
- Single-source-of-truth épargne model (totale − allouée = libre)

**Pages built**
- Accueil, Historique, Journal, Objectif, Épargne, Plafond, Daret, Moi, Assistant, Onboarding, Admin

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
