# Backlog — Post-beta v2 wishlist

Things explicitly **NOT in the 85% scope**. Move here anything that comes up
mid-conversation but isn't on the active sprint in `ROADMAP.md`.

The point: keep `ROADMAP.md` short and focused on shipping beta. Everything
else lives here so nothing is forgotten — but nothing is in the way either.

---

## 🇲🇦 Flagship v1.5 — Moroccan Cultural Adaptations

> The real wedge. No Western finance app does these. Each one is a product
> moment Moroccan users will recognize as "wow, this app was made for me".

### 🕌 Cagnottes / Sinking Funds (Projets & Événements)
The biggest budget destroyers in MA aren't daily coffees — they're **seasonal events**:
Aïd El Kebir, Ramadan, La Rentrée Scolaire, Vacances d'été.
- New page "Cagnottes" with visual jars per event
- Pre-filled MA templates: Mouton de l'Aïd, Ramadan, Rentrée, Vacances, Frais Médicaux, Assurance Voiture
- App divides target by months remaining ("Mettre 250 DH/mois pour l'Aïd")
- When the event fires, spending the money doesn't tank the score — coach knows it was planned
- Forces sinking-fund discipline that solves the "Aïd ruined my month" problem

### 🛒 Le Carnet (Moul Lhanout Tracker)
Many Moroccans buy on credit at the local épicier and pay end-of-month. Western apps treat as "debt" = negative.
- New mini-feature: "Ajouter au Carnet" checkbox on transactions
- Coach reminder at month-end: "Tu dois 450 DH à l'épicier — marquer comme payé ?"
- Treats the carnet as a tracked short-term debt, not failure

### 🤝 Famille & Solidarité category
Sadaqa, helping parents/siblings, gifts to family — these are mandatory budget lines in MA culture, not "Divers" or "Loisirs".
- Add `Famille` and `Solidarité (Sadaqa)` as first-class categories
- Coach treats them with respect, not as discretionary
- Could even gamify: "Tu as donné 500 DH ce mois — Sadaqa enregistrée 🤲"

### 🎉 Salary Day Choreography (Le Jour de Paie)
Most emotional day of the month. App should make a moment of it.
- Detect salary input → confetti animation 🎉
- Coach immediately: "Salaire de 6 000 DH arrivé ! Alignons nos troupes — combien on met de côté ?"
- Force zero-based budget distribution on Day 1 (Mette en cagnotte / Épargne / Reste)

### 🎮 Mini-Défis / Challenges (7-day)
- "Défi Semaine sans Livraison" (no Glovo/Wolt → +10 pts + badge)
- "Défi Zéro Espèce" (carte uniquement pour suivi auto)
- "Défi 50 DH par jour" (vivre avec un budget serré, mode coup-de-main)
- Optional, gamified, badge reward

### 🇲🇦 Darija expressions in coach
Even in French interface, weave Darija for warmth:
- "Bsa7a la sortie, mais attention au budget !"
- "Koulchi meziane pour l'instant."
- "Lkher d'che'har approche…"
- Breaks the cold banking atmosphere

### 🛡️ Modest Mode (Essential Mode v2) — IMPLEMENTATION READY

Spec is complete — when picking this up next, just answer the 3 questions
below and execute. ~30 min implementation in 1 commit.

**Detection trigger** (auto-switch to Modest mode when):
- `revenu_total ≤ 4 000 DH/mois` (low income), OR
- `charges_fixes / revenu > 60%` (heavy burden)
- PLUS manual override toggle in Paramètres → Personnalisation

**Score weight changes**:

| Factor | Standard | Modest | Why |
|---|---|---|---|
| Reste à vivre | 25 pts | **35 pts** | Survival > optimization |
| Épargne du mois | 15 pts | **5 pts** | Small wins matter, not big targets |
| Fonds d'urgence | 20 pts | **5 pts** | Survival comes before reserve |
| Dépenses équilibrées (50/30/20) | 25 pts | **0 pts** | Rule doesn't apply at survival income |
| Engagement | 15 pts | **35 pts** | Tracking IS the win at low income |
| Pas de découvert (NEW factor) | — | **20 pts** | `reste_a_vivre ≥ 0` = full marks |
| **Total** | 100 | 100 | |

**UI signal**: small badge "🛡️ Mode Essentiel" next to the score in coach panel
(transparency without shame — user knows the calculation is adapted to their context).

**3 implementation questions to confirm before coding**:
- **Q1**: Auto-detection thresholds — `4 000 DH` and `60% charges fixes` look right
  for MA market? Or different numbers?
- **Q2**: Manual toggle in Paramètres? My recommendation: yes — auto-detect but
  let user override (some students with rich parents technically have low income
  but aren't in survival mode; some 8K earners with 4 kids ARE).
- **Q3**: Implementation scope:
  - **(a) Just scoring** — same messages, different score weights *(RECOMMENDED for v1)*
  - **(b) Scoring + Modest-specific messages** (celebrating mois-sans-découvert,
    50 DH first savings = "Alerte Héroïsme 👑") *(better but bigger — post-beta polish)*

**Files to touch when implementing**:
- `core/assistant_engine.py:compute_score()` — add Modest mode branch
- `config.py` — add SCORE_V2_MODEST_* weight constants + thresholds
- `views/moi.py` — add Standard/Modest toggle in Personnalisation section
- `views/accueil.py:_render_coach_panel()` — display "🛡️ Mode Essentiel" badge if active
- `core/coach_messages.py` — only if Q3=(b), add Modest-specific messages

**Effort estimate**: ~30 min for Q3=(a), ~2 hours for Q3=(b).

### 🆘 Mode Pause (life happens)
Sometimes life hits hard (medical emergency, job loss, Ramadan splurge). Users feel ashamed to open the app.
- "Mettre mon budget en pause" button in Mon compte
- 30 days no negative score, no alerts
- Coach message: "Mode Pause activé. Prenez soin de vous, on reprendra quand vous serez prêt 💙"
- **Why genius**: prevents shame-driven uninstall = massive retention lift

---

## ⭐ Flagship v1.5 launch — Daret Command Center

> The killer differentiator. No MA fintech does this. Solves the universal
> WhatsApp Daret chaos pain point. Built-in viral loop (each manager onboards
> 5–15 members for free). Natural paid-tier wedge.

**The pitch (for marketing & investor talk):**

The idea isn't to explain what a Daret is — it's to **fix how it's managed**.

- **Zero Casse-Tête.** No more scrolling through 200 WhatsApp messages to find who sent a screenshot.
- **The "Bloomberg" Table.** A single shared screen. 🟢 Green = Paid. 🟡 Yellow = Declared. 🔴 Red = Pending. Total transparency for everyone.
- **The Oracle (Manager).** Only the manager has the "Validate" button. You see the money in your bank, you click, the group is updated instantly.
- **Fair Play.** The app handles the Tirage au sort (Digital Draw). No favoritism, no "I wanted the first month" — the algorithm decides, and it's final.
- **The Viral Link.** You create a Daret, send a link to your group, they join. Boom. The Daret is live and professional in 30 seconds.

**What it requires (be honest):**
- Real-time sync (Supabase realtime or WebSockets) — Streamlit can't do this well
- Magic link / invite link auth + URL routing
- RBAC: manager vs member roles + permission checks at every endpoint
- Notification system (push, email, or SMS) — when a member declares payment, manager and others see immediately
- Cryptographically fair draw with audit trail (so any member can verify "this was fair")
- Mobile-first UX (5 friends checking the table on phones daily)

**Why post-beta:** practically forces the Next.js + FastAPI migration to ship properly. Estimate: 4–6 weeks of focused work after migration is done.

**Pricing wedge:**
- Solo Daret tracker (current) → free tier
- Daret Command Center (multi-user, manager dashboard, invite links) → paid tier (50 DH/month)

**Strategic positioning:** the v1.5 launch story. What you announce to drive press and signups after the private beta is stable.

> **Note**: a simplified **v1 solo version** (manager-only, no real-time, no invite links)
> ships in beta — see `ROADMAP.md` Sprint 3 "Daret Manager (solo)". That captures
> ~80% of the user value with 20% of the technical complexity. The full V2 multi-user
> version stays as the flagship v1.5 launch.

---

## 🚀 Post-beta v2 features

### Banking integration
- [ ] Bank statement CSV import (CIH, Attijari, BMCE export formats)
- [ ] OFX import (more standard but rarer in MA)
- [ ] PDF parsing of bank statements (OCR)

### Notifications & engagement
- [ ] Email reminders (daily log nudge, monthly summary)
- [ ] Push notifications (when mobile app exists)
- [ ] SMS alerts for budget overruns (Maroc Telecom API?)

### Mobile
- [ ] Native iOS/Android app (after Next.js migration)
- [ ] PWA (faster path — install Streamlit page as PWA)

### Daily Mode — 2-tap predictive logging (Next.js cut)
- [ ] Predictive amount pills + category icons UI (time-of-day aware, hides numpad by default, "Custom" button + delayed-undo toast)
- [ ] Engine prototyped 2026-05-03: `core/predictor.py` (time-bucket frequency, 5 buckets, 90d window, round-to-5 DH, cold-start fallback) + `scripts/eval_predictor.py` walk-forward backtest. Uncommitted local draft, not benchmarked. Decision gate: ship UI only if amount hit@6 ≥ 70% on real data.

### Localization
- [ ] Darija (Latin script: "Slm a sahbi") translation
- [ ] Arabic (RTL layout — significant CSS work)
- [ ] English version (international Moroccans, expats)

### Advanced visualizations
- [ ] Drillable Plotly sunburst donut (category → sub-category) on month visibility page
- [ ] Multi-month trend chart (12 months scrollable)
- [ ] Sankey diagram (where does my money flow)
- [ ] **Cashflow waterfall chart** (Monarch-style — income cascades into savings + categories)
- [ ] **Spending Ring** (Revolut-style — fills as month progresses, turns red if over)
- [ ] **Ghost line overlay** (last month's pace vs current as solid line)
- [ ] Heatmap calendar (spending intensity per day)
- [ ] **Net Worth / Asset growth chart** (year-over-year)

### Mon compte enrichments (deferred from Block A)
- [ ] **Discrete mode** toggle — blur all big numbers (solde, salaire) until user taps eye 👁
- [ ] **Pride badge** in profile hero ("🏆 Guerrier du Budget — 14 jours de suite")
- [ ] **Profile picture / avatar** upload
- [ ] **Type de Revenus**: Fixed vs Variables (Freelance/Commerce/Gig)
- [ ] **Charges Fixes Incontournables** input (rent + utilities = survival number)
- [ ] **Taille du Foyer** input (changes coach interpretation of grocery, healthcare spending)
- [ ] **Mode Standard vs Mode Essentiel** toggle (manual override of auto-detection)
- [ ] **Connexion Biométrique** toggle (FaceID / Fingerprint — post-mobile)
- [ ] **Auto-save** on every field change (no Save button, show ✅ Enregistré)

### Smarter coaching
- [ ] LLM-generated personalized advice (vs the static message table)
- [ ] What-if simulator ("Si j'épargne 200 DH/mois de plus, mon score atteint X")
- [ ] **"Can I afford it?" calculator** — user types "Puis-je me payer X DH ?", coach checks reste à vivre + objectifs and replies with tradeoff
- [ ] Anomaly detection + push alert (unusual spending pattern)
- [ ] **Behavioral alerts** ("Tu as pris 4 Ubers cette semaine — il pleut, prends le bus pour rester sous le plafond transport")
- [ ] **Subscription audit** ("Tu paies Adobe depuis 4 mois sans l'utiliser — annuler ?")
- [ ] **"Wasted Money" calculator** — late fees, ATM fees, unused subs over a year
- [ ] **Lifestyle creep alert** ("Tes charges fixes ont augmenté de 8% vs l'an dernier")
- [ ] **Bill & cashflow forecasting** ("Ta facture de 120 DH passe demain mais ton solde est de 90 DH")
- [ ] **Year-end recap "Spotify Wrapped" style** — fun shareable slideshow ("Tu étais un Foodie cette année — 30% en restos")
- [ ] **Salary increase popup** ("Félicitations ! +1 000 DH — allouer à l'épargne pour éviter l'inflation du style de vie ?")
- [ ] **Salary decrease popup** ("Mode Essentiel activé automatiquement — on est ensemble 🤝")
- [ ] **Family change popup** ("Mabrouk ! 🍼 Coach a ajusté tes seuils supermarché et santé")

### Premium tier features
- [ ] Multi-account aggregation (link multiple bank cards)
- [ ] Family/couple shared budget
- [ ] Tax export (compatible with MA tax filing)
- [ ] Advanced Daret features (multi-Daret tracking) — see also flagship "Daret Command Center" above

### Trust & compliance
- [ ] Security audit by external firm (badge for landing page)
- [ ] CNDP compliance (Moroccan data protection)
- [ ] 2FA login
- [ ] Session management ("active devices" page)
- [ ] Audit log exposed to user (who did what when)

### Infrastructure
- [ ] Migration to Next.js + FastAPI (CLAUDE.md plan)
- [ ] Local payment processor integration (CMI / PayZone / Lydia)
- [ ] Pricing page + subscription management
- [ ] Customer support flow (intercom / crisp / email)
- [ ] Marketing site (separate from app)
- [ ] Analytics (Plausible or PostHog)

---

## 💭 Ideas / wishlist (no priority)

- [ ] Coach personality variants (more humor / more serious)
- [ ] Gamified achievements page (badges for milestones)
- [ ] Public profile / leaderboard (opt-in, anonymous)
- [ ] Investment tracking (CDM, BMCE Capital, crypto)
- [ ] Goal sharing with family ("on save together for hajj")
- [ ] Voice input for transactions (especially Darija)
- [ ] Receipt photo + OCR
- [ ] Recurring transaction templates (auto-create monthly)

---

## ❌ Cut from beta scope (reason logged)

| Feature | Why cut |
|---|---|
| Bank statement import | Engineering time (~2 weeks) doesn't justify for 5 beta users — manual entry acceptable |
| Notification system | Beta users will check willingly. Add when retention is the bottleneck |
| Mobile native app | Web on mobile works for beta. Native is post-launch v2 |
| Darija/Arabic | French audience is the beta target. Localization is post-launch |
| Drillable sunburst | Cool but not on critical path. Flat sparkline + bars is enough for v1 |
| Investment tracking | Out of scope for personal budgeting v1 |

---

## 🐛 Known issues to fix later (non-blocking)

- [ ] Active vs inactive nav item visual inconsistency (active=HTML div, inactive=st.button)
- [ ] Sparkline currently uses 7-day daily flux — replace with monthly when month visibility ships
- [ ] `_suggestions_live` in sidebar — needs testing to confirm suggestions appear correctly
- [ ] Assistant page not in sidebar nav (intentional — accessible only via Coach CTA)
