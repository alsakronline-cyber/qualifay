"""Site Factory — find businesses without a website, build them a private preview site, and
sell it through a consent-first WhatsApp conversation.

Pure modules (no DB / network imports — unit-testable on their own):
  state.py     funnel statuses, allowed transitions, consent + timing policy
  replies.py   understands Arabic / Egyptian / English replies per funnel stage
  segments.py  per-segment search keywords, design themes, fallback copy
  builder.py   renders the one-file bilingual preview site (escaped, noindex)
  messages.py  the WhatsApp texts the system sends

Integration modules:
  payments.py  Paymob intention → checkout link (InstaPay as manual fallback)
  service.py   discovery, enrichment, build, send, reply handling, expiry (DB)
  tasks.py     Celery beat jobs
  api.py       dashboard + public preview routes
"""
