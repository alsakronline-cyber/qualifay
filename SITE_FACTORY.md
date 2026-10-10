# Site Factory

Finds Egyptian businesses (manufacturers, local stores, clinics) that have **no website** or
**no Google Business Profile**, builds each one a private preview website, and sells it through a
**consent-first** WhatsApp conversation. It runs as a Qualifay module: `backend/app/site_factory/`
and the dashboard page `/site-factory`.

## The funnel

```
found → built → awaiting_approval ──(you approve)──► intro_sent ──"نعم"──► opted_in → preview_sent
                                                                                   │ "عجبني" → ask to proceed
                                                                                   │ "عايز اكمل" → payment_sent → paid → live
                                                                                   │ "عدّل…" → changes_requested → (you edit) → preview_sent
any stage: "لا" / "إيقاف" / "إلغاء" / silence after one follow-up → data deleted + number suppressed
```

| Step | What happens | Where |
|---|---|---|
| Discover (daily 08:30) | Google Maps places **without** `websiteUri` → `no_website`; OSM businesses cross-checked against Maps → `no_gbp` if not on Maps. Mobile numbers only; skips known/unsubscribed/suppressed numbers. | `service.discover` |
| Build (every 10 min) | WhatsApp check, Place Details (hours, category), facts-only AI copy (fallback copy if the LLM fails), one-file bilingual HTML stored in MinIO. | `service.build`, `builder.py` |
| **Approve (you)** | Dashboard → *بانتظار الموافقة* → select → **موافقة**. Nothing is ever sent without this. | `api.approve_intros` |
| Intro (every 15 min, 10:00–19:59) | Asks permission only — no link. Respects the WhatsApp warmup cap and the campaign's daily intro cap, 40–110 s apart. | `service.send_intro` |
| Reply handling | Rules for Arabic/Egyptian/English (`replies.py`), LLM second opinion, then a human notification if still unclear. | `service.handle_reply` |
| Follow-up / expiry (hourly) | One follow-up per phase, then expire → purge. Previews expire after 14 days. | `state.due_action`, `service.tick` |
| Payment | Paymob Unified Checkout link (`sf-<id>` reference, handled by `/webhook/paymob`) and/or InstaPay; **سجّل الدفع** marks a manual payment. On payment the site is published at `/api/v1/site-factory/s/<slug>`. | `payments.py`, `service.mark_paid` |

## The client website (what each business gets)
A complete static site per business (`builder.py`), Arabic at `/`, English at `/en/`:

| Page | Content |
|---|---|
| Home | headline + intro, WhatsApp/phone CTAs, Google rating line (linked, not re-published), services, contact cards, CTA band |
| About | about paragraphs + quick-facts card (category, city, address, phone) |
| Services | all services + **one page per service** (description, "how to request" steps, other services) |
| FAQ | built only from facts (hours, location, how to order/book/quote, services) + `FAQPage` schema |
| Contact | address/phone/hours cards, **WhatsApp form** (composes a message — no backend, nothing stored), map |
| Privacy | plain-language policy matching what the site actually does |
| + | 404, `sitemap.xml` with hreflang, `robots.txt`, `assets/site.css`, `assets/site.js` |

SEO: unique title/description per page, canonical, hreflang (ar/en/x-default), Open Graph, `LocalBusiness`/`MedicalClinic`/`Dentist`/`Store` + `BreadcrumbList` + `Service` + `FAQPage` JSON-LD, local keywords (name + city) in copy. No review markup (Google reviews can't be republished as your own structured data). Previews: `noindex` + `Disallow: /` + banner on every page.

Data collected per business (`profile`): Arabic + English name, phone, address, city, coordinates, category, opening hours, Google rating + review count, Maps place id, Facebook/Instagram links (from OSM tags). Copy is written from these facts only; the owner's edits replace it before publishing.

## Who's worth it, who handles it, what to sell (`insights.py`)
- **Score 0–100** with readable reasons: segment value, website/Google gap, review volume, rating, hours/address present, WhatsApp reachability, existing social pages. Tiers: hot ≥ 70, warm 50–69, cold < 50. Not on WhatsApp → 0.
- **Recommended services** from the data gaps, each with the reason and the campaign's price: website (always), Google profile (create if missing, fix if < 10 reviews or no hours), social pages (if none found), WhatsApp catalogue / booking / quote replies (if on WhatsApp).
- **Assignment**: assign one or many prospects to any team member; filter *mine / unassigned / hot only*; sorted best-first.

## Sdiek Marketing workspace
Separate company inside Qualifay, created once on the server:
```
SDIEK_ADMIN_PASSWORD='…' python -m app.site_factory.setup_workspace --email you@example.com --name "Mohamed Ramadan"
```
Creates the workspace, your owner login, and three small trial campaigns (manufacturers 10th of Ramadan / 6th of October, stores Nasr City / Maadi, clinics Maadi / Heliopolis) with default prices (website 4,500 · Google 1,500 · social 2,500 · WhatsApp 2,000 EGP — edit per campaign).

## Compliance built in
- **Egypt PDPL 151/2020 / WhatsApp policy:** human approval before first contact; first message
  identifies the sender, asks permission, and offers *إيقاف*; link only after an explicit yes;
  max one follow-up; send window 10:00–19:59 Cairo; warmup caps.
- **Right to stop / erasure:** stop/no/cancel/expiry deletes the profile, copy and preview; only a
  SHA-256 hash of the number is kept (`site_suppressions`) so it is never contacted again.
- **No impersonation:** previews are private (unguessable token, `noindex`, banner "معاينة خاصة —
  غير منشورة"); nothing is published until the owner pays.
- **No third-party photos** (Google/Facebook images belong to the business/photographer).
- **Clinics:** facts-only copy, no medical claims, disclaimer on the page.

## Configuration (`backend/.env`)
```
GOOGLE_MAPS_API_KEY=...            # Places API (New): search + details (billed per call)
PAYMOB_SECRET_KEY=...              # Intention API (optional — without it, InstaPay/manual only)
PAYMOB_PUBLIC_KEY=...
PAYMOB_INTEGRATION_ID=...          # existing
PAYMOB_HMAC_SECRET=...             # existing; required for the webhook
SITE_FACTORY_PUBLIC_URL=https://...  # base for preview/live links (defaults to APP_BASE_URL)
SITE_FACTORY_BRAND_URL=https://alsakronline-cyber.github.io/sdiek-marketing/
```
Tables are created automatically on startup (`create_all`). Celery beat jobs are registered in
`app/workers/celery_app.py`.

## Before going live
1. Verify the Paymob Intention request body against your account's docs (`payments.py`).
2. Run one campaign at small caps (e.g. 10 intros/day) on a **warmed** number.
3. Read every intro batch before approving for the first week.
4. Point `SITE_FACTORY_PUBLIC_URL` at an HTTPS domain — WhatsApp users won't open a bare IP link.

## Tests
`backend/tests/test_site_factory.py` — reply understanding, consent gates, transitions, timing,
HTML escaping, clinic disclaimer, opt-out wording (pure logic, no DB).
