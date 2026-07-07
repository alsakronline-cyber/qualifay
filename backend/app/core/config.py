from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    APP_NAME: str = "Qualifay"
    ENVIRONMENT: str = "production"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    SERVER_IP: str = "80.225.65.148"

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
    GROQ_MODEL_REALTIME: str = "llama-3.3-70b-versatile"

    # AI — OpenRouter (reasoning + batch)
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL_REASONING: str = "deepseek/deepseek-r1"
    OPENROUTER_MODEL_FAST: str = "meta-llama/llama-3.3-70b-instruct"

    # Scraping
    GOOGLE_MAPS_API_KEY: str = ""
    APOLLO_API_KEY: str = ""
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

    # Payments
    PAYMOB_API_KEY: str = ""
    PAYMOB_INTEGRATION_ID: str = ""
    PAYMOB_HMAC_SECRET: str = ""
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

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()

