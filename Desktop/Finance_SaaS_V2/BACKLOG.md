# Backlog — Post-beta v2 wishlist

Things explicitly **NOT in the 85% scope**. Move here anything that comes up
mid-conversation but isn't on the active sprint in `ROADMAP.md`.

The point: keep `ROADMAP.md` short and focused on shipping beta. Everything
else lives here so nothing is forgotten — but nothing is in the way either.

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

### Localization
- [ ] Darija (Latin script: "Slm a sahbi") translation
- [ ] Arabic (RTL layout — significant CSS work)
- [ ] English version (international Moroccans, expats)

### Advanced visualizations
- [ ] Drillable Plotly sunburst donut (category → sub-category) on month visibility page
- [ ] Multi-month trend chart (12 months scrollable)
- [ ] Sankey diagram (where does my money flow)
- [ ] Heatmap calendar (spending intensity per day)

### Smarter coaching
- [ ] LLM-generated personalized advice (vs the static message table)
- [ ] What-if simulator ("Si j'épargne 200 DH/mois de plus, mon score atteint X")
- [ ] Anomaly detection + push alert (unusual spending pattern)
- [ ] Year-end recap (Spotify Wrapped style)

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
