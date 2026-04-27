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
- [x] Show factor breakdown on score click (transparency = trust)
- [x] **Consolidate Objectif Dépense → Plafond** (delete duplicate tab)
- [ ] End-of-sprint review Friday (no code)

---

## 📅 4-sprint plan

### Sprint 1 — Wire the brain + clean up _(current)_
See "CURRENT SPRINT" above.

### Sprint 2 — Onboarding wizard v2 + coach copy
- [x] Wizard v2 shell + badges/hints foundations (commit 1)
- [x] Wizard v2 full content: 4 steps, real récurrents form, 4 sliders, score reveal (commit 2)
- [x] Step 2 utilities (Électricité + Eau) + step 3 live donut (commit 2.1)
- [ ] **Write the 5 status-level coach messages first** (CRITIQUE/FAIBLE/MOYEN/BON/EXCELLENT) — replaces `[À écrire]` at the score reveal climax
- [ ] Replace remaining 19 `[À écrire]` in `core/coach_messages.py`
- [x] Sprinkle 6 contextual hints throughout app (commit 3a)
- [ ] Delete legacy `views/onboarding.py` once v2 confirmed stable (commit 3b)
- [ ] Add "abonnement detection" popup on duplicate sub-categories
- [ ] Build mini-onboarding catch-up flow (when `jours_inactif >= 7`)
- [ ] **Dashboard preview screen before "Découvrir l'app"** — small mockup of Accueil with their data ("voici ce qui t'attend") to reduce post-onboarding shock
- [ ] **Reference points on estimation sliders** — "Moyenne MA pour ce revenu = X DH" hints to help users who don't know their numbers

### Sprint 3 — Mon compte + month visibility lite + Daret Manager
- [x] Mon compte: real name, email, change password (bcrypt-aware) — commit A1
- [x] Mon compte: data export button (JSON download) — commit A2
- [x] Mon compte: delete account flow (type-SUPPRIMER confirmation) — commit A3
- [x] Customizable: fonds d'urgence target (default 3 mois) — commit B1
- [x] Customizable: 50/30/20 category overrides UI + compute_score integration — commit B2
- [x] **Block C — Tendances page** (Month visibility, shipped):
  - [x] db_manager: `get_solde_mensuel_histo()` + `get_cashflow_mensuel()` (~6 mois)
  - [x] Hero monthly sparkline upgraded to monthly data (replaces 7-day flux)
  - [x] New page `views/tendances.py` with 5 sections:
    - [x] Up/down monthly bars chart (revenus green up, dépenses red down)
    - [x] **Velocity card**: Daily Avg + Safe-to-Spend
    - [x] **Subscription leakage card**: récurrents via `get_charges_fixes` + total + count
    - [x] **Top 3 lists**: top catégories ce mois + top 3 plus grosses transactions 6m
    - [x] N-month KPI strip with 3/6/12 selector
  - [x] Added to sidebar nav (📈 Tendances) + first-visit hint
- [ ] **Bonus polish**: enrich the 5 status coach messages with 3-part structure (Diagnostic / Plan d'Action / Vision) — ~30 min, big quality jump
- [ ] **Categories restructure** — rename "Vie Quotidienne" → "Courses maison" + split subcats (Alimentation / Produits ménagers) + extract Transport as own category. Updates: CATEGORIES table, DICO_MATCHING, DEFAULT_503020_MAPPING in config.py, existing transactions migration.
- [ ] **Daret Manager (solo, ~3 days)**:
  - [ ] Tirage au sort algorithm (random turn order, seed stored for proof)
  - [ ] Bloomberg-style status table (members × months grid: 🟢/🟡/🔴)
  - [ ] Manager log button (mark as paid / declared / pending)
  - [ ] Timeline view (current month, next, total remaining, end date)
  - [ ] Export récap to clipboard (paste into WhatsApp group)
  - V2 multi-user version (invite links, real-time) → BACKLOG.md flagship v1.5

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
