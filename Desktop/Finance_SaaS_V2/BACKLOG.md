# Backlog — Post-beta v2 wishlist

Things explicitly **NOT in the 85% scope**. Move here anything that comes up
mid-conversation but isn't on the active sprint in `ROADMAP.md`.

The point: keep `ROADMAP.md` short and focused on shipping beta. Everything
else lives here so nothing is forgotten — but nothing is in the way either.

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
- [ ] Advanced Daret features (multi-Daret tracking, shared between members)

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
