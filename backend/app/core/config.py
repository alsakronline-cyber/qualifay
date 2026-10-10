from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    APP_NAME: str = "Qualifay"
    ENVIRONMENT: str = "production"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    SERVER_IP: str = "80.225.65.148"
    # Public base URL of the app (for building invite/accept links). Falls back to the IP.
    APP_BASE_URL: str = ""

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str
    REDIS_KEY_PREFIX: str = "qualifay:"

    # Evolution API (existing on server, host network)
    EVOLUTION_API_URL: str = "http://localhost:8080"
    EVOLUTION_API_KEY: str  # required — set in .env

    # AI — Groq (real-time)
    GROQ_API_KEY: str
    # NOTE: llama-3.3-70b-versatile was decommissioned by Groq — every call 404'd with
    # "model does not exist", which silently emptied all AI output (BANT, intent, replies,
    # AIDA copy) because the OpenRouter fallback is disabled. Verified against Groq's
    # /models endpoint; keep this in sync when Groq retires a model.
    GROQ_MODEL_REALTIME: str = "openai/gpt-oss-120b"

    # AI — OpenRouter (reasoning + batch)
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL_REASONING: str = "meta-llama/llama-3.3-70b-instruct:free"
    OPENROUTER_MODEL_FAST: str = "meta-llama/llama-3.3-70b-instruct"
    # OpenRouter's free tier is no longer available on this account — every ":free" model
    # returns 404 ("unavailable for free"). So OpenRouter is OFF by default and Groq (which
    # works on the free tier) is primary for the fast + reasoning paths. Re-enable by setting
    # OPENROUTER_ENABLED=true AND a valid (likely paid) model slug in the two vars above.
    OPENROUTER_ENABLED: bool = False

    # Scraping
    GOOGLE_MAPS_API_KEY: str = ""
    APOLLO_API_KEY: str = ""
    # Apollo's People Search API requires a PAID Apollo plan (free plan -> 403 API_INACCESSIBLE).
    # Leave off until on a paid plan; then set APOLLO_ENABLED=true to use Apollo instead of the
    # free OpenStreetMap fallback for the "apollo" source.
    APOLLO_ENABLED: bool = False
    HUNTER_API_KEY: str = ""
    TOR_PROXY: str = "socks5://127.0.0.1:9050"
    PROXY_POOL: str = ""
    # Optional session cookies for sites that block unauthenticated scraping.
    # LinkedIn: the "li_at" cookie value (or full cookie string). Facebook: "c_user=...; xs=...".
    LINKEDIN_COOKIE: str = ""
    FACEBOOK_COOKIE: str = ""
    # Facebook Ad Library API (free, official — replaces web scraping of the Ad Library).
    FACEBOOK_ADLIB_TOKEN: str = ""
    # Google Programmable Search (Custom Search JSON API) for LinkedIn discovery via search
    # results — free 100 queries/day. CX is the search-engine id; the key can reuse the Maps key.
    GOOGLE_CSE_API_KEY: str = ""
    GOOGLE_CSE_CX: str = ""

    # Storage
    MINIO_ENDPOINT: str = "http://127.0.0.1:9000"
    MINIO_USER: str = "qualifay"
    MINIO_PASSWORD: str = ""

    # Off-box backup target (S3-compatible: Backblaze B2, AWS S3, Wasabi…). Optional —
    # when the endpoint + keys are set, nightly DB dumps are also pushed here so a lost
    # server disk doesn't take the backups (which live on the same box in MinIO) with it.
    BACKUP_S3_ENDPOINT: str = ""          # e.g. s3.us-west-004.backblazeb2.com  (no https://)
    BACKUP_S3_BUCKET: str = ""
    BACKUP_S3_ACCESS_KEY: str = ""
    BACKUP_S3_SECRET_KEY: str = ""
    BACKUP_S3_SECURE: bool = True         # TLS to the remote endpoint

    # Qdrant
    QDRANT_URL: str = "http://127.0.0.1:6333"

    # Email (SMTP outreach)
    SMTP_HOST: str = "smtp.hostinger.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""          # real SMTP login password (set in .env, read via celery env_file)
    SMTP_APP_PASSWORD: str = ""      # legacy name, kept as a fallback
    SMTP_FROM: str = ""              # from address (defaults to SMTP_USER)
    SMTP_FROM_NAME: str = "Qualifay"
    # IMAP — for receiving replies. Defaults to the Hostinger mailbox matching SMTP.
    IMAP_HOST: str = "imap.hostinger.com"
    IMAP_PORT: int = 993
    IMAP_POLL_ENABLED: bool = True
    # Pause a tenant's email sending for the day once this many bounces are seen — a
    # spike means bad addresses / reputation trouble, so stop before it gets worse.
    EMAIL_BOUNCE_PAUSE_THRESHOLD: int = 10
    RESEND_API_KEY: str = ""
    # Hard ceiling on drip-campaign emails per tenant per day, applied ON TOP of the
    # account's warmup cap (lower wins). The account warmup counts calendar days since its
    # first-ever send, so a mailbox that has barely sent anything can look "fully warm" and
    # allow 250/day of cold email — enough to get the domain blacklisted. Raise gradually
    # (~25%/week) only while bounces stay low.
    DRIP_EMAIL_DAILY_MAX: int = 30
    # Same idea for WhatsApp: a per-campaign ceiling below the number's warmup cap, so a drip
    # can run conservatively without throttling the number's manual sends and replies.
    DRIP_WA_DAILY_MAX: int = 30

    # Payments
    PAYMOB_API_KEY: str = ""
    PAYMOB_INTEGRATION_ID: str = ""
    PAYMOB_HMAC_SECRET: str = ""
    # Intention API (Unified Checkout) — used by the Site Factory to sell websites.
    PAYMOB_SECRET_KEY: str = ""
    PAYMOB_PUBLIC_KEY: str = ""

    # Site Factory — public base URL for preview/live site links (e.g. https://sites.example.com).
    # Defaults to APP_BASE_URL. Previews are served by this backend at /api/v1/site-factory/p/<token>.
    SITE_FACTORY_PUBLIC_URL: str = ""
    SITE_FACTORY_BRAND_URL: str = ""
    FAWRY_MERCHANT_CODE: str = ""
    FAWRY_SECURITY_KEY: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Compliance
    ETA_CLIENT_ID: str = ""
    ETA_CLIENT_SECRET: str = ""
    ETA_EIN: str = ""

    # App behaviour
    AI_AUTO_REPLY_ENABLED: bool = False   # off by default — human approval required
    AI_AUTO_REPLY_DELAY_SECONDS: int = 3
    AI_CONFIDENCE_THRESHOLD: float = 0.75
    MIN_BANT_SCORE_FOR_REVIEW: int = 50   # leads below this are auto-archived

    # WhatsApp warmup daily caps by day_of_life
    WA_WARMUP_CAPS: dict = {
        "7": 10, "14": 30, "21": 75, "30": 150, "999": 200
    }

    # Email daily cap
    EMAIL_DAILY_CAP_DEFAULT: int = 50

    # Admin seed
    DEFAULT_ADMIN_EMAIL: str = "admin@qualifay.io"
    DEFAULT_ADMIN_PASSWORD: str  # required — set in .env

    CORS_ORIGINS: List[str] = ["http://80.225.65.148", "http://localhost:3000"]

    @property
    def app_base_url_effective(self) -> str:
        """Public base URL for building links in emails (invites). Defaults to the IP."""
        return (self.APP_BASE_URL or f"http://{self.SERVER_IP}").rstrip("/")

    @property
    def cors_origins_effective(self) -> List[str]:
        """In production, don't trust localhost origins (they're only needed when running
        `next dev` against a remote backend). Deployments are reached via the server IP."""
        if self.ENVIRONMENT == "production":
            return [o for o in self.CORS_ORIGINS if "localhost" not in o and "127.0.0.1" not in o]
        return self.CORS_ORIGINS

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()

