"""Base scraper with proxy, rate limiting, block detection, retry logic"""
import asyncio
import random
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class RawLead:
    source: str
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    city: Optional[str] = None
    governorate: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    raw_data: dict = field(default_factory=dict)


class BlockedError(Exception):
    pass


class BaseScraper:
    source: str = "base"
    use_tor: bool = False
    delay_min: float = 2.0
    delay_max: float = 8.0
    max_retries: int = 3

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    ]

    def random_ua(self) -> str:
        return random.choice(self.USER_AGENTS)

    async def delay(self):
        await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))

    def get_proxy(self) -> Optional[str]:
        from app.core.config import settings
        if self.use_tor:
            return settings.TOR_PROXY  # socks5://127.0.0.1:9050
        if settings.PROXY_POOL:
            proxies = settings.PROXY_POOL.split(",")
            p = random.choice(proxies).strip()
            parts = p.split(":")
            if len(parts) == 4:
                return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        return None

    @staticmethod
    def parse_cookie_string(cookie_str: str, domain: str, default_name: str = "") -> list:
        """Turn a raw cookie string into Playwright cookie dicts for `domain`.

        Accepts either a full "name=value; name2=value2" string, or (when a single bare
        token is given and `default_name` is set) treats it as `default_name=<token>`.
        """
        cookies = []
        cookie_str = (cookie_str or "").strip()
        if not cookie_str:
            return cookies
        if "=" not in cookie_str and default_name:
            cookie_str = f"{default_name}={cookie_str}"
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            name, value = name.strip(), value.strip()
            if not name or not value:
                continue
            cookies.append({
                "name": name, "value": value,
                "domain": domain, "path": "/",
                "httpOnly": False, "secure": True,
            })
        return cookies

    def is_blocked(self, status_code: int, text: str) -> bool:
        if status_code in (403, 429, 503):
            return True
        blocked_signals = [
            "captcha", "verify you are human", "access denied",
            "too many requests", "rate limit", "please log in",
        ]
        return any(s in text.lower() for s in blocked_signals)

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        raise NotImplementedError
        yield  # make this a generator
