# CLAUDE.md — Qualifay: Full Technical Build Contract

> **Brand:** Qualifay  
> **Server:** 80.225.65.148 (IP only — no domain during build)  
> AI-powered B2B lead generation + WhatsApp CRM · Egypt-first · Multi-tenant  
> Phase 1 + Phase 2 combined in one build

---

## 0. What Qualifay Is

Qualifay is a fully automated B2B lead generation and CRM SaaS for the Egyptian market.

**Flow:** Scrape → Enrich → AI-qualify → Human reviews → Approve → Outreach via WhatsApp
→ AI handles replies → Books appointments → Tracks in CRM pipeline

**Key principle — Human in the loop:**  
AI scores and qualifies leads. The user decides whether to approve each lead for outreach.
No message is sent without explicit user approval (or a tenant-level "auto-approve" toggle).

**Multi-tenant:** each client gets their own workspace, WhatsApp instance, pipeline, and data.

**Business model:** 30-day free trial. Three tiers:
- Starter — 500 leads/mo, 1 WhatsApp instance, manual approval only
- Growth — 5 000 leads/mo, 3 instances, auto-approve toggle, full AI suite
- Agency — unlimited, white-label, reseller portal

---

## 1. Server

```
Host:      80.225.65.148
SSH Port:  2222  ← ALWAYS specify -p 2222
User:      ubuntu
Key:       ssh-key-2026-03-05.key

SSH:       ssh -i "ssh-key-2026-03-05.key" -p 2222 ubuntu@80.225.65.148

OS:        Ubuntu 22.04.5 LTS
Arch:      aarch64 (Neoverse-N1)  ← all Docker images must support linux/arm64
CPU:       4 vCPU
RAM:       24 GB (13 GB available)
Disk:      97 GB / 47 GB free
Swap:      4 GB
Docker:    29.6.0 · Compose v5.1.4
```

**No domain configured yet. All access via IP: `http://80.225.65.148`**

Access map:
| Service | URL |
|---|---|
| Qualifay app | `http://80.225.65.148` (nginx proxies to Next.js :3000) |
| API docs | `http://80.225.65.148/api/docs` |
| Evolution manager | `http://80.225.65.148:8080/manager` |
| MinIO console | `http://80.225.65.148:9001` |
| n8n | `http://80.225.65.148:5678` |

---

## 2. Existing Services on Server — What to Reuse vs. Avoid

### The Evolution API — REUSE THIS (do not deploy a new one)

```
Container:    evolution_api
Image:        evoapicloud/evolution-api:v2.3.7 (reports as v2.2.3 at runtime)
Network:      host  ← binds directly to host port 8080, no port mapping needed
Port:         8080 (directly on host)
API key:      REDACTED_EVOLUTION_KEY  (from /home/ubuntu/evolution-api/.env)
Database:     PostgreSQL on 127.0.0.1:5434 (container: evolution_postgres)
Redis:        127.0.0.1:6381 (container: evolution_redis)
Proxy:        Tor SOCKS5 on 127.0.0.1:9050 (container: evolution_tor) — ALREADY enabled!
Server URL:   https://api.alsakronline.com (Cloudflare tunnel)
Compose:      /home/ubuntu/evolution-api/docker-compose.yml
```

**Critical facts:**
- Running in `network_mode: host` — it IS the host network. Reach it at `http://localhost:8080`
- Tor proxy is already active for all WhatsApp connections (anti-ban)
- The `fetchInstances` 401 is because the `clientName` (`evolution_exchange`) requires a
  tenant-level instance key, not the global key, for some endpoints. Use global key for
  create/delete; use instance key for send/receive.
- Do NOT restart or recreate this container. It has live WhatsApp sessions.
- Qualifay backend connects to it via `EVOLUTION_API_URL=http://localhost:8080`
  and `EVOLUTION_API_KEY=REDACTED_EVOLUTION_KEY`

### Other existing services
| Container | Reuse? | How |
|---|---|---|
| `evolution_tor` | YES | Tor SOCKS5 at 127.0.0.1:9050 — scrapers can use this |
| `redis` (ai-stack, port 6380) | YES | Qualifay cache/queue prefix: `qualifay:` |
| `qdrant` (port 6333) | YES | RAG vector store — already running |
| `n8n` (port 5678) | YES | Workflow automation |
| Host nginx | YES | Add Qualifay site block, it stays on 80/443 |
| `evolution_postgres` (5434) | NO | Belongs to Evolution, don't write to it |
| MariaDB, PHP-FPM | NO | WordPress only |

---

## 3. Technology Stack

**Backend:** FastAPI (Python) — extends the existing `/qualifay` codebase  
**Frontend:** Next.js 14 (App Router + TypeScript) — replaces the React Vite frontend  
**Workers:** Celery (Python) — scraping + AI batch jobs  
**No local AI models** — API-only (see Section 7)

| Layer | Technology | Notes |
|---|---|---|
| Frontend | Next.js 14 App Router + TypeScript | Tailwind CSS + shadcn/ui, RTL Arabic |
| Backend | FastAPI (Python 3.11) | Extends existing /qualifay backend |
| Workers | Celery + Redis | Scraping, AI batch, outreach queue |
| Database | PostgreSQL 16 (Docker, port 5435) | New container, isolated |
| ORM | SQLAlchemy async + Alembic | Existing pattern in /qualifay |
| Cache / Queue | Redis 7 (reuse port 6380) | Key prefix: `qualifay:` |
| WhatsApp | Evolution API v2.3.7 (existing, port 8080) | Reuse — do NOT redeploy |
| Object storage | MinIO (Docker, port 9000/9001) | Documents, exports, media |
| AI real-time | Groq API (llama-3.3-70b-versatile) | <500ms, WA replies, intent |
| AI reasoning | OpenRouter free (deepseek-r1:free) | BANT, proposals, complex tasks |
| AI fast | OpenRouter free (llama-3.3-70b:free) | Classification, copywriting |
| RAG | Qdrant (existing port 6333) + OpenAI embeddings API | Knowledge base per tenant |
| Funnels | Typebot builder + viewer (Docker) | Consent capture, appointment flows |
| Workflow | n8n (existing port 5678) | Ramadan scheduler, drip campaigns |
| Reverse proxy | Host nginx (existing) | Add site block for port 3000 |
| UI | Tailwind CSS + shadcn/ui | Dark/light, Cairo (AR) + Inter (EN) |
| Auth | FastAPI JWT + NextAuth.js v5 | Sessions, tenant isolation |
| Payments | Paymob (EGP card) + Fawry (EGP cash) + Stripe (USD) | |

---

## 4. Architecture Overview

```
Browser → nginx (:80) → Next.js (:3000)
                      → FastAPI (:5000)  [/api/*]
                      → Evolution API (:8080) [/evolution/*]

Next.js (frontend)
  └── API routes  →  FastAPI backend (:5000)
                       ├── PostgreSQL :5435
                       ├── Redis :6380 (queue + cache)
                       ├── Evolution API :8080 (WhatsApp)
                       ├── Groq API (real-time AI)
                       ├── OpenRouter API (reasoning AI)
                       └── Qdrant :6333 (RAG)

Celery workers (background)
  ├── scrape queue → 9 scraper modules → DB
  ├── ai queue    → OpenRouter → lead scoring
  └── outreach queue → warmup limiter → Evolution API → WhatsApp
```

### Lead lifecycle with human approval gate

```
SCRAPE → raw_lead saved
  → QualityGate agent (OpenRouter) → junk? discard
  → LeadEnricher → fill missing phone/email/company
  → BANTScorer → score 0-100
  → if score < tenant.min_score → archive
  → if score ≥ threshold → status = "pending_review"
  → 🔔 notify user: "23 leads ready for review"

USER REVIEWS in dashboard:
  → View lead card: company, score, BANT breakdown, source
  → Options: ✅ Approve for outreach | ❌ Reject | 👤 Assign to self (take manually)
  → "Take manually" → lead moves to CRM pipeline, no automated outreach

ON APPROVAL:
  → ConsentChecker → validates Law 151/2020
  → WarmupLimiter → checks daily cap for WA instance
  → Queue outreach message → WhatsApp send via Evolution API
  → AI handles replies (WhatsAppResponder agent)
  → If booking intent detected → AppointmentBooker → Typebot funnel
```

---

## 5. Multi-Tenancy

**IP-based routing during development (no subdomain yet):**
Each tenant has a unique URL path prefix or tenant ID in auth token.
When domain is added later, middleware switches to subdomain routing automatically.

```
http://80.225.65.148/  → super-admin login or tenant selector
http://80.225.65.148/dashboard  → tenant dashboard (after login)
```

**Database:** every table has `tenant_id UUID NOT NULL`. Prisma/SQLAlchemy middleware
auto-scopes all queries. No cross-tenant reads possible at ORM level.

**Redis:** all keys prefixed `qualifay:{tenant_id}:*`

**MinIO:** one bucket per tenant: `tenant-{slug}`

**WhatsApp:** one Evolution instance per tenant WA connection. Multiple tenants share
the same Evolution API server but have isolated instances.

---

## 6. Repository Structure

```
qualifay/
├── CLAUDE.md                         ← this file
├── START_HERE.md                     ← onboarding brief
├── docker-compose.yml                ← new Qualifay services only
├── .env.example
├── .env                              ← NEVER commit
├── Makefile
│
├── backend/                          ← FastAPI (extends existing /qualifay backend)
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   └── redis.py
│   │   ├── models/
│   │   │   ├── models.py             ← SQLAlchemy models (all with tenant_id)
│   │   │   └── lead_pool.py          ← shared lead pool model
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   ├── auth.py
│   │   │   ├── leads.py              ← lead management + review queue
│   │   │   ├── outreach.py           ← campaign management
│   │   │   ├── contacts.py           ← CRM contacts
│   │   │   ├── conversations.py      ← WhatsApp inbox
│   │   │   ├── messages.py
│   │   │   ├── instances.py          ← WA instance management
│   │   │   ├── pipeline.py           ← CRM pipeline
│   │   │   ├── ai.py                 ← AI endpoints
│   │   │   ├── webhook.py            ← Evolution + payment webhooks
│   │   │   ├── billing.py            ← subscriptions
│   │   │   └── dashboard.py
│   │   ├── services/
│   │   │   ├── ai_service.py         ← Groq + OpenRouter (no local models)
│   │   │   ├── evolution_service.py  ← WhatsApp via existing Evolution API
│   │   │   ├── warmup_service.py     ← WA + email daily limit enforcer
│   │   │   ├── lead_pool_service.py  ← shared qualified lead pool
│   │   │   └── notification_service.py
│   │   └── workers/
│   │       ├── celery_app.py
│   │       ├── scrape_tasks.py       ← 9 scraper modules
│   │       ├── ai_tasks.py           ← qualification pipeline
│   │       └── outreach_tasks.py     ← warmup-aware send queue
│   ├── scrapers/
│   │   ├── base.py                   ← base class: rate limit, proxy, retry
│   │   ├── google_maps.py
│   │   ├── websites.py
│   │   ├── directories.py
│   │   ├── tenders.py
│   │   ├── apollo.py
│   │   ├── linkedin.py
│   │   ├── facebook_groups.py
│   │   ├── enrichment.py
│   │   └── competitor_ads.py
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── bant_scorer.py
│   │   ├── aida_writer.py
│   │   ├── quality_gate.py
│   │   ├── whatsapp_responder.py
│   │   ├── appointment_booker.py
│   │   ├── proposal_writer.py
│   │   ├── lead_enricher.py
│   │   ├── sentiment_analyzer.py
│   │   ├── followup_scheduler.py
│   │   ├── intent_classifier.py
│   │   ├── competitor_analyst.py
│   │   ├── tender_matcher.py
│   │   ├── arabic_translator.py
│   │   ├── email_finder.py
│   │   ├── campaign_planner.py
│   │   └── consent_checker.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                         ← Next.js 14 (replaces React Vite)
│   ├── app/
│   │   ├── (auth)/
│   │   │   ├── login/
│   │   │   └── register/
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx              ← main dashboard
│   │   │   ├── leads/                ← scrape + review queue + pool
│   │   │   ├── inbox/                ← WhatsApp CRM inbox (Phase 2)
│   │   │   ├── contacts/             ← CRM contacts
│   │   │   ├── pipeline/             ← Kanban board
│   │   │   ├── outreach/             ← campaigns
│   │   │   ├── instances/            ← WA instance management
│   │   │   ├── billing/
│   │   │   └── settings/
│   │   ├── (admin)/                  ← super-admin
│   │   └── api/
│   │       └── auth/[...nextauth]/
│   ├── components/
│   │   ├── ui/                       ← shadcn/ui
│   │   ├── lead-review-card/         ← approve / reject / take manually
│   │   ├── warmup-indicator/         ← shows daily WA/email usage
│   │   ├── whatsapp-inbox/
│   │   └── rtl-provider/
│   ├── lib/
│   │   └── api.ts                    ← typed API client
│   ├── Dockerfile
│   ├── next.config.js
│   ├── tailwind.config.js
│   └── package.json
│
├── services/
│   └── faster-whisper/               ← Arabic voice → text
│       ├── main.py
│       ├── Dockerfile
│       └── requirements.txt
│
├── nginx/
│   └── qualifay.conf                 ← added to /etc/nginx/sites-enabled/
│
└── scripts/
    ├── deploy.sh
    └── seed.py
```

---

## 7. AI Service — API Only (No Local Models)

**No Ollama. No local inference.** All AI calls go to external free-tier APIs.

```python
# backend/app/services/ai_service.py

# Groq — real-time (<500ms), WA replies, intent classification
# Model: llama-3.3-70b-versatile
# Free tier: 6000 req/min, 500k tokens/day — more than enough

# OpenRouter — reasoning tasks, BANT scoring, proposals
# Model: deepseek/deepseek-r1:free  (primary reasoning)
# Model: meta-llama/llama-3.3-70b-instruct:free  (copywriting, translation)
# Free tier: per-model daily limits, rotate between models if needed

# Fallback chain: Groq → OpenRouter → Together AI free
```

### Model routing per agent

| Agent | API | Model | Why |
|---|---|---|---|
| WhatsAppResponder | Groq | llama-3.3-70b-versatile | <500ms mandatory |
| IntentClassifier | Groq | llama-3.3-70b-versatile | Real-time |
| AppointmentBooker | Groq | llama-3.3-70b-versatile | Real-time |
| QualityGate | OpenRouter | llama-3.3-70b:free | Batch, fast enough |
| BANTScorer | OpenRouter | deepseek-r1:free | Reasoning |
| ProposalWriter | OpenRouter | deepseek-r1:free | Long-form reasoning |
| TenderMatcher | OpenRouter | deepseek-r1:free | Reasoning |
| CompetitorAnalyst | OpenRouter | deepseek-r1:free | Reasoning |
| CampaignPlanner | OpenRouter | deepseek-r1:free | Reasoning |
| AIDAWriter | OpenRouter | llama-3.3-70b:free | Copywriting |
| ArabicTranslator | OpenRouter | llama-3.3-70b:free | Translation |
| LeadEnricher | OpenRouter | llama-3.3-70b:free | Structured extraction |
| SentimentAnalyzer | OpenRouter | llama-3.3-70b:free | Classification |
| FollowUpScheduler | OpenRouter | llama-3.3-70b:free | Scheduling logic |
| EmailFinder | OpenRouter | llama-3.3-70b:free | Pattern guessing |
| ConsentChecker | OpenRouter | llama-3.3-70b:free | Rule checking |

### Rate limit handling
```python
# ai_service.py: exponential backoff on 429
# Track daily token usage per model in Redis
# If model daily limit hit → switch to fallback automatically
# Alert admin (not tenant) if all fallbacks exhausted
```

---

## 8. The 9 Scraping Modules

Location: `backend/scrapers/`. All extend `BaseScraper`.

```python
class BaseScraper:
    # Built-in: rotating delays, proxy rotation, user-agent rotation
    # Proxy options in priority order:
    #   1. Tor SOCKS5 (127.0.0.1:9050) — already on server, use for LinkedIn/FB
    #   2. Configurable proxy pool (PROXY_POOL env var)
    #   3. Direct (only for APIs with official rate limits)
    delay_range = (2, 8)      # random seconds between requests
    max_retries = 3
    retry_backoff = (30, 120)  # seconds to wait after block detection
```

| # | Scraper | Anti-blocking strategy | Proxy needed |
|---|---|---|---|
| 1 | **Google Maps** | Official Places API — rate limit = 1 req/s | No proxy — API handles it |
| 2 | **Business websites** | Playwright stealth, random UA, 3-8s delays | Optional |
| 3 | **Directories** | Cheerio + rotating UA, respectful crawl | Optional |
| 4 | **Tenders** | RSS feeds + official portals, no blocking risk | No proxy |
| 5 | **Apollo.io** | Official REST API, tenant API key, 50 req/day free | No proxy |
| 6 | **LinkedIn** | Playwright + puppeteer-extra-stealth + **Tor** + session rotation | **Tor mandatory** |
| 7 | **Facebook Groups** | Playwright + stealth + **Tor** + account rotation | **Tor mandatory** |
| 8 | **Enrichment** | Hunter.io API + Clearbit free API | No proxy |
| 9 | **Competitor Ads** | FB Ad Library API (public) + Google Transparency | No proxy |

### Block detection and recovery
```python
# Block signals: 403, 429, captcha page, redirect to login
# On block detected:
#   1. Pause this scraper for this tenant for 30min (Redis TTL)
#   2. Notify user: "LinkedIn scraper paused — resuming at 14:30"
#   3. Retry with fresh Tor circuit (send NEWNYM to Tor control port)
#   4. If 3 blocks in 24h → pause for 24h, notify user to check proxy settings
```

### Tor circuit management
```python
# backend/services/tor_service.py
# Send NEWNYM signal to get fresh circuit before each LinkedIn/FB session
# Tor control port: 127.0.0.1:9051 (evolution_tor container exposes this)
# Use stem library: Controller.from_port(port=9051).signal(Signal.NEWNYM)
```

### Playwright setup (ARM64)
```python
# Use playwright Python library with chromium
# Install in backend Dockerfile:
# RUN playwright install chromium --with-deps
# Stealth: page.set_extra_http_headers() + custom viewport + disabling automation flags
```

---

## 9. WhatsApp Daily Limits & Warmup

### Sending limits per WhatsApp instance

```python
# backend/services/warmup_service.py

WARMUP_SCHEDULE = {
    # day_of_life: (whatsapp_limit, email_limit)
    range(1, 8):    (10,  50),   # week 1
    range(8, 15):   (30,  100),  # week 2
    range(15, 22):  (75,  200),  # week 3
    range(22, 30):  (150, 300),  # week 4
    range(30, 999): (200, 500),  # stable
}

# Tracked per WA instance in DB: wa_instances.day_of_life, sent_today, sent_today_email
# Reset at midnight Cairo time (Africa/Cairo)
# Hard block: attempt to send when limit reached → queued for next day
```

### User notifications
```python
# Notify when:
# 1. Daily WA limit reached → "WhatsApp limit reached (75/75). Queued 12 messages for tomorrow."
# 2. Instance warming up → "Your WhatsApp is warming up. Day 8/30. Current limit: 30/day."
# 3. Warmup milestone → "🎉 WhatsApp warmup complete! Sending limit: 200/day."
# 4. Block detected → "⚠️ WhatsApp instance may be flagged. Paused for 4 hours."
# 5. New day reset → "New day! 75 WhatsApp messages available."

# Notification channels: in-app toast + DB notification table
# Stored in: notifications table (tenant_id, type, message, read_at, created_at)
```

### Message content rules (anti-ban)
```python
# Enforced before every send:
# - No URLs in first 3 messages to a new contact
# - No identical messages to more than 5 contacts in 1 hour (variation required)
# - AIDAWriter adds natural variation to every message (no two identical)
# - Messages with "STOP" / "إيقاف" response → instant unsubscribe + cancel all tasks
# - Warm contacts (replied before) → higher daily priority
# - Egyptian phone numbers only accepted in E.164: +201XXXXXXXXX
```

### Email daily limits
```python
# Gmail SMTP: 500/day total, 50/day conservative start
# Resend free: 100/day, 3000/month
# Per-tenant limits stored in tenant.email_daily_limit
# Increase by 25% every 7 days if delivery rate > 95%
```

---

## 10. Shared Lead Pool

After a lead is AI-qualified AND user-approved, sanitised data goes into the shared pool.

### What gets saved to pool (privacy-safe only)
```python
# lead_pool table — accessible across tenants
{
  "company": "Al Nour Contracting",
  "industry": "Construction",
  "company_size": "11-50",
  "city": "Cairo",
  "governorate": "Cairo",
  "website": "alnourcontracting.com",
  "bant_score": 72,
  "source": "google_maps",
  "verified_at": "2026-06-28T...",
  "claimed_by_tenants": ["tenant_abc"],  # list of tenant IDs that already used this
  # NEVER saved to pool: personal phone, personal email, contact name
}
```

### Pool access rules
```python
# Tenants can:
# - Search pool by industry, city, score, size
# - "Claim" a lead → copies to their leads table (adds their enrichment data)
# - A lead can be claimed by max 3 tenants total (prevents over-saturation)
# - Tenant who originally scraped the lead gets "source credit" badge

# Pool is NOT visible across tenants for the personal/contact fields
# Pool does NOT replace scraping — it accelerates it with already-qualified data
# Tenant can opt OUT of contributing to pool (GDPR/151 cautious clients)
```

### Pool economics
```python
# Contributing to pool costs 0 credits
# Claiming from pool costs X credits depending on plan
# Pool quality maintained by: min bant_score=60 to enter, 90-day expiry on stale data
```

---

## 11. The 16 AI Agents

Location: `backend/agents/`. All extend `BaseAgent`.

```python
class BaseAgent:
    def run(self, input: dict, tenant_id: str) -> dict: ...
    # Automatic: token tracking, error handling, fallback model
```

| # | Agent | Trigger | Output |
|---|---|---|---|
| 1 | `QualityGate` | After every scrape | keep / discard + reason |
| 2 | `LeadEnricher` | After quality gate | filled company/phone/email fields |
| 3 | `BANTScorer` | After enrichment | score 0-100 + B/A/N/T breakdown |
| 4 | `ConsentChecker` | Before any outreach | approved / blocked + reason |
| 5 | `AIDAWriter` | After user approval | outreach message (AIDA format) |
| 6 | `ArabicTranslator` | When lead language = AR | translated message |
| 7 | `IntentClassifier` | Every inbound WA message | intent + language + sentiment |
| 8 | `WhatsAppResponder` | Inbound WA (auto-reply on) | reply text |
| 9 | `AppointmentBooker` | Booking intent detected | Typebot link + calendar slot |
| 10 | `SentimentAnalyzer` | After every conversation turn | sentiment trend |
| 11 | `FollowUpScheduler` | No reply after N days | follow-up message + timing |
| 12 | `ProposalWriter` | On-demand / hot lead | full proposal document |
| 13 | `CampaignPlanner` | New campaign creation | message sequence + schedule |
| 14 | `TenderMatcher` | New tender scraped | match score + bid strategy |
| 15 | `CompetitorAnalyst` | New competitor ad scraped | insights + counter-strategy |
| 16 | `EmailFinder` | When Hunter returns nothing | guessed email patterns to verify |

### Human approval gate (key requirement)
```python
# After BANTScorer runs:
# - score < tenant.min_approval_score (default 50) → auto-archive, not shown
# - score ≥ min_approval_score → status = "pending_review", notification sent
# - User sees review queue in dashboard
# - User actions:
#   APPROVE → outreach pipeline starts
#   REJECT  → archived (feedback stored to improve future scoring)
#   TAKE MANUALLY → moved to CRM pipeline, AI outreach disabled for this lead
#                   user handles via WhatsApp inbox manually
```

---

## 12. Prisma / SQLAlchemy Schema

Using SQLAlchemy async (existing pattern from /qualifay backend).

```python
# Key models — all have tenant_id

class Tenant(Base):
    id, slug, name, plan, trial_ends_at
    language = "ar"        # ar | en
    auto_approve = False   # if True, skip review queue (Growth+ only)
    min_approval_score = 50
    contribute_to_pool = True

class Lead(Base):
    id, tenant_id, source (ScraperType), name, phone (+E.164), email
    company, industry, city, website
    bant_score: int         # 0-100
    stage: PipelineStage    # NEW | PENDING_REVIEW | APPROVED | REJECTED | MANUAL | OUTREACH | REPLIED | BOOKED | WON | LOST
    status: LeadStatus      # ACTIVE | UNSUBSCRIBED | BLOCKED | INVALID
    consent_at: datetime
    language: str           # ar | en
    raw_data: JSON          # full scraped payload
    pool_contributed: bool  # whether pushed to shared pool
    assigned_to: uuid       # if MANUAL, which user took it

class WaInstance(Base):
    id, tenant_id, instance_name  # Evolution API instance name
    status: str                   # connected | disconnected | qr_pending
    day_of_life: int              # 1 = first day, for warmup
    daily_wa_cap: int             # computed from warmup schedule
    sent_today_wa: int
    sent_today_email: int
    last_reset_at: datetime

class LeadPool(Base):
    # Shared across tenants — no personal data
    id, company, industry, company_size, city, governorate, website
    bant_score, source, verified_at, expires_at (90 days)
    claimed_count: int   # max 3
    contributed_by: uuid # original tenant

class Notification(Base):
    id, tenant_id, user_id, type, message, read_at, created_at

class ConsentLog(Base):
    id, tenant_id, lead_id, method, ip, user_agent, consent_text, created_at

class Subscription(Base):
    id, tenant_id, provider (paymob|fawry|stripe)
    external_id, status, currency, plan
    current_period_end, eta_invoice_id
```

---

## 13. Docker Compose — New Qualifay Services

These are added alongside existing server services. They do NOT touch evolution_api, n8n, qdrant, or evolution_tor.

```yaml
# docker-compose.yml

networks:
  qualifay:
    driver: bridge

services:

  postgres:
    image: postgres:16-alpine
    platform: linux/arm64
    container_name: qualifay_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: qualifay
      POSTGRES_USER: qualifay
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - qualifay_postgres:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5435:5432"   # 5433+5434 are taken
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U qualifay"]
      interval: 10s
      retries: 5

  minio:
    image: minio/minio:latest
    platform: linux/arm64
    container_name: qualifay_minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD}
    volumes:
      - qualifay_minio:/data
    ports:
      - "127.0.0.1:9000:9000"
      - "0.0.0.0:9001:9001"   # console accessible on IP

  typebot_builder:
    image: baptistearno/typebot-builder:latest
    platform: linux/arm64
    container_name: qualifay_typebot_builder
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://qualifay:${POSTGRES_PASSWORD}@postgres:5432/qualifay
      NEXTAUTH_SECRET: ${TYPEBOT_SECRET}
      NEXTAUTH_URL: http://80.225.65.148:3001
    ports:
      - "127.0.0.1:3001:3000"
    networks: [qualifay]

  typebot_viewer:
    image: baptistearno/typebot-viewer:latest
    platform: linux/arm64
    container_name: qualifay_typebot_viewer
    restart: unless-stopped
    ports:
      - "127.0.0.1:3002:3000"
    networks: [qualifay]

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    platform: linux/arm64
    container_name: qualifay_backend
    restart: unless-stopped
    network_mode: host        # host mode to reach evolution_api on localhost:8080
    environment:
      DATABASE_URL: postgresql+asyncpg://qualifay:${POSTGRES_PASSWORD}@127.0.0.1:5435/qualifay
      REDIS_URL: redis://127.0.0.1:6380
      EVOLUTION_API_URL: http://localhost:8080
      EVOLUTION_API_KEY: ${EVOLUTION_API_KEY}
      GROQ_API_KEY: ${GROQ_API_KEY}
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
      SECRET_KEY: ${SECRET_KEY}
      MINIO_ENDPOINT: http://localhost:9000
      TOR_PROXY: socks5://127.0.0.1:9050    # reuse evolution_tor
      QDRANT_URL: http://localhost:6333
      ENVIRONMENT: production
    depends_on:
      - postgres

  celery_worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    platform: linux/arm64
    container_name: qualifay_celery
    restart: unless-stopped
    network_mode: host
    command: celery -A app.workers.celery_app worker --loglevel=info --concurrency=3 -Q scrape,ai,outreach,default
    environment:
      DATABASE_URL: postgresql+asyncpg://qualifay:${POSTGRES_PASSWORD}@127.0.0.1:5435/qualifay
      REDIS_URL: redis://127.0.0.1:6380
      EVOLUTION_API_URL: http://localhost:8080
      EVOLUTION_API_KEY: ${EVOLUTION_API_KEY}
      GROQ_API_KEY: ${GROQ_API_KEY}
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
      TOR_PROXY: socks5://127.0.0.1:9050
      SECRET_KEY: ${SECRET_KEY}
    deploy:
      resources:
        limits:
          memory: 2G

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    platform: linux/arm64
    container_name: qualifay_frontend
    restart: unless-stopped
    environment:
      NEXT_PUBLIC_API_URL: http://80.225.65.148/api
      NEXT_PUBLIC_WS_URL: ws://80.225.65.148/ws
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET}
      NEXTAUTH_URL: http://80.225.65.148
    ports:
      - "127.0.0.1:3000:3000"

  whisper:
    build:
      context: ./services/faster-whisper
    platform: linux/arm64
    container_name: qualifay_whisper
    restart: unless-stopped
    network_mode: host
    ports:
      - "127.0.0.1:8001:8001"
    deploy:
      resources:
        limits:
          memory: 2G

volumes:
  qualifay_postgres:
  qualifay_minio:
```

---

## 14. Nginx Site Config (add to existing host nginx)

File: `/etc/nginx/sites-enabled/qualifay.conf`

```nginx
server {
    listen 80;
    server_name 80.225.65.148;
    client_max_body_size 50M;

    # Next.js frontend
    location / {
        proxy_pass         http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }

    # FastAPI backend
    location /api/ {
        proxy_pass         http://127.0.0.1:5000/api/;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
    }

    # WebSocket (live inbox)
    location /ws {
        proxy_pass         http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_read_timeout 3600s;
    }

    # Evolution API manager (proxied, not exposed raw)
    location /evolution/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
    }
}
```

**Note:** The existing nginx config for `alsakronline.com`, `autospark.conf`, `evolution.conf`,
`n8n.conf` stays untouched. This new block adds Qualifay routing for the server IP only.

---

## 15. Environment Variables

```bash
# ── Database ─────────────────────────────────────────────────
POSTGRES_PASSWORD=              # generate: openssl rand -hex 24

# ── App auth ─────────────────────────────────────────────────
SECRET_KEY=                     # generate: openssl rand -hex 32
NEXTAUTH_SECRET=                # generate: openssl rand -hex 32

# ── WhatsApp — uses existing Evolution API ────────────────────
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=REDACTED_EVOLUTION_KEY   # existing key from server

# ── AI APIs ──────────────────────────────────────────────────
GROQ_API_KEY=                   # free: console.groq.com
OPENROUTER_API_KEY=             # free: openrouter.ai

# ── Scraping APIs ────────────────────────────────────────────
GOOGLE_MAPS_API_KEY=            # Google Cloud console (Places API)
APOLLO_API_KEY=                 # apollo.io free (50 contacts/day)
HUNTER_API_KEY=                 # hunter.io free (25 searches/month)
PROXY_POOL=                     # optional: host:port:user:pass,... for extra proxies
                                # Tor on 127.0.0.1:9050 is always available

# ── Object storage ───────────────────────────────────────────
MINIO_USER=qualifay
MINIO_PASSWORD=                 # strong password

# ── Payments ─────────────────────────────────────────────────
PAYMOB_API_KEY=
PAYMOB_INTEGRATION_ID=
PAYMOB_HMAC_SECRET=
FAWRY_MERCHANT_CODE=
FAWRY_SECURITY_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# ── Services ─────────────────────────────────────────────────
TYPEBOT_SECRET=                 # generate: openssl rand -hex 32
N8N_PASSWORD=                   # strong password

# ── Email ────────────────────────────────────────────────────
SMTP_USER=                      # Gmail address
SMTP_APP_PASSWORD=              # Gmail App Password
RESEND_API_KEY=                 # optional: resend.com free tier

# ── Compliance ───────────────────────────────────────────────
ETA_CLIENT_ID=
ETA_CLIENT_SECRET=
ETA_EIN=                        # Egyptian Tax ID

# ── Server ───────────────────────────────────────────────────
SERVER_IP=80.225.65.148
```

---

## 16. Egypt-Specific Requirements

### Law 151/2020 — Personal Data Protection
- Explicit opt-in before any outreach (Typebot flow captures + timestamps it)
- `ConsentLog` table: `{lead_id, tenant_id, method, ip, consent_text, created_at}`
- `ConsentChecker` agent validates before every campaign batch
- Opt-out endpoint: `GET /api/unsubscribe?token=<signed-JWT>`
- Inbound `"إيقاف"` or `"STOP"` → hard-coded match (before AI) → immediate unsubscribe + cancel all tasks

### Arabic RTL
- `next/middleware.ts` sets `dir="rtl"` and `lang="ar"` based on tenant setting
- Cairo font (Arabic) via `next/font/google`, Inter for English
- All shadcn/ui components tested RTL before merge

### Phone normalisation
All phones normalised to E.164 (`+201XXXXXXXXX`) before any DB write or WA send:
```python
# lib/phone.py: handles 01X, 001X, +201X, 00201X, 201X → +201XXXXXXXXX
# Invalid → stored in invalid_phones log, never sent
```

### Ramadan calendar
- n8n cron reads Islamic calendar API before queuing outreach
- During Ramadan: no daytime outreach (8AM–6PM Cairo)
- Shifts to 8PM–11PM Cairo (`Africa/Cairo` timezone)
- Replies to inbound messages are unaffected (always respond)

### WhatsApp warming (detailed — Section 9)
- Day 1-7: 10 WA/day
- Day 8-14: 30 WA/day
- Day 15-21: 75 WA/day
- Day 22-30: 150 WA/day
- Day 31+: 200 WA/day (stable cap)
- User notified at every threshold change

### ETA E-Invoicing
- XML invoice generated on subscription payment
- Submitted to ETA production API
- UUID stored per transaction in `subscriptions.eta_invoice_id`

---

## 17. Build Order

Execute phases in strict order. Run verification after each. Fix all errors before proceeding.

| Phase | Name | Deliverables |
|---|---|---|
| **0** | Server check + foundation | Verify specs, install Node 20, UFW rules, check all existing services |
| **1** | Docker Compose up | postgres, minio, typebot, backend, celery, frontend, whisper |
| **2** | Database schema | Alembic migrations, all tables created, seed admin user |
| **3** | FastAPI backend | All /api/* routes, JWT auth, tenant middleware, Evolution API connection test |
| **4** | 16 AI agents | All agent classes, prompts hardcoded, unit test each with mock input |
| **5** | 9 scraping modules | Each exports scrape(), BullMQ wired, 1 test scrape per module |
| **6** | Warmup + limits | WarmupService, daily cap enforcement, notification system |
| **7** | Shared lead pool | LeadPool model, contribute/claim logic, privacy sanitisation |
| **8** | Human approval flow | Review queue API, approve/reject/take-manually endpoints |
| **9** | Next.js frontend | All 9 dashboard screens, lead review card, warmup indicator |
| **10** | Payments | Paymob + Fawry + Stripe webhooks, trial management, ETA invoicing |
| **11** | Egypt compliance | Law 151 consent flow, STOP handler, phone normaliser, Ramadan scheduler |
| **12** | Nginx config | Add qualifay.conf to sites-enabled, test reload |
| **13** | End-to-end test | Scrape → qualify → review → approve → WA send → reply → book |

---

## 18. Key Constraints & Decisions

| Decision | Rationale |
|---|---|
| Reuse existing `evolution_api` | Already running with live sessions, Tor proxy built-in, changing it risks WA bans |
| `network_mode: host` for backend | Evolution API is host-networked. Only way backend can reach it at `localhost:8080` |
| API-only LLMs (no Ollama) | Server RAM is tight (13GB available). Groq+OpenRouter are free and faster than local 7B models |
| Redis port 6380 (existing) | Reuse. Prefix all keys with `qualifay:` to avoid collision |
| PostgreSQL port 5435 | 5433 and 5434 are taken by evolution containers |
| Tor (9050) for LinkedIn/FB scrapers | Already on server, free, rotatable via NEWNYM signal |
| Human-in-the-loop approval | Core product requirement. No automated outreach without user seeing the lead first |
| Shared pool = no personal data | Law 151/2020 compliance + prevents tenant data leakage |
| IP-only access now | Domain + SSL added later (1 nginx config change + Certbot). Build everything domain-agnostic |
| Phase 1 + 2 in one build | Backend is FastAPI either way. CRM inbox reuses the same Evolution/WA setup. No reason to split. |

---

## 19. Development Commands

```bash
# SSH
ssh -i "ssh-key-2026-03-05.key" -p 2222 ubuntu@80.225.65.148

# Docker
docker compose up -d
docker compose logs -f backend
docker compose logs -f celery_worker
docker compose ps

# Database
cd backend && alembic upgrade head         # apply migrations
alembic revision --autogenerate -m "name"  # create migration

# Check Evolution API (existing)
curl http://localhost:8080/                 # should return version JSON
curl -H "apikey: REDACTED_EVOLUTION_KEY" http://localhost:8080/instance/fetchInstances

# Check Tor proxy
curl --socks5 127.0.0.1:9050 https://check.torproject.org/api/ip

# Monitor RAM
docker stats --no-stream
watch -n5 free -h

# Nginx
sudo nginx -t && sudo systemctl reload nginx
```
