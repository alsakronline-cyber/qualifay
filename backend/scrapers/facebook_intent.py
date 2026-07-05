"""Facebook group BUYER-INTENT scraper.

Reads posts from Facebook groups (that the logged-in account has joined) and keeps only the
ones where someone wants to buy or is asking for a product/service, then turns each into a
lead. Requires a Facebook session cookie (c_user + xs) — there is no free API for group
content, and groups can only be read by a member. High ban risk: use a secondary account and
keep volumes/pacing modest.

config keys:
  session_cookie : str   — "c_user=...; xs=..." (or falls back to settings.FACEBOOK_COOKIE)
  group_ids      : str   — comma/space separated group IDs or URLs the account has joined
  query          : str   — optional keyword to also require in the post
  max_results    : int   — max intent leads to return (default 20)
  use_ai         : bool  — AI-confirm each keyword candidate (default True)
"""
import logging
import re
from typing import AsyncGenerator, List

from scrapers.base import BaseScraper, RawLead, BlockedError
from scrapers.intent import detect_buyer_intent, extract_phone_from_text, normalize_ar
from app.lib.phone import normalize_egyptian_phone

logger = logging.getLogger(__name__)

FB_BLOCKED_SIGNALS = [
    "you must log in", "log into facebook", "create new account",
    "checkpoint", "security check", "confirm your identity", "captcha",
]

# Generic DOM extraction — grab every article's text, its author, and a permalink. Kept
# resilient to markup changes by reading innerText + any post/permalink anchor.
_EXTRACT_JS = """
() => {
  const out = [];
  const arts = document.querySelectorAll('[role="article"]');
  for (const a of arts) {
    const text = (a.innerText || '').trim();
    if (!text) continue;
    let url = '';
    const link = a.querySelector(
      'a[href*="/permalink/"], a[href*="/posts/"], a[href*="story_fbid"], a[href*="/groups/"][href*="/posts/"]'
    );
    if (link) url = link.href;
    let author = '';
    const au = a.querySelector('h2 a, h3 a, strong a, span strong');
    if (au) author = (au.innerText || '').trim();
    out.push({ text, url, author });
  }
  return out;
}
"""


def _parse_group_ids(raw: str) -> List[str]:
    ids = []
    for token in re.split(r"[,\s]+", (raw or "").strip()):
        token = token.strip()
        if not token:
            continue
        m = re.search(r"groups/([^/?&]+)", token)
        ids.append(m.group(1) if m else token)
    return ids


class FacebookGroupIntentScraper(BaseScraper):
    source = "facebook_intent"
    use_tor = False  # authenticated session — go direct (Tor gets blocked)
    delay_min = 3.0
    delay_max = 6.0

    async def scrape(self, config: dict, tenant_id: str) -> AsyncGenerator[RawLead, None]:
        from playwright.async_api import async_playwright
        from app.core.config import settings

        cookie_str = (config.get("session_cookie") or settings.FACEBOOK_COOKIE or "").strip()
        if not cookie_str:
            raise BlockedError(
                "Facebook group scraping needs a session cookie. Add your Facebook cookie "
                "(c_user + xs) via FACEBOOK_COOKIE (use a secondary account) to enable this."
            )

        group_ids = _parse_group_ids(config.get("group_ids", ""))
        query = (config.get("query") or "").strip()
        max_results = min(int(config.get("max_results", 20)), 100)
        use_ai = config.get("use_ai", True)
        query_norm = normalize_ar(query) if query else ""

        if not group_ids and not query:
            raise ValueError("Provide group_ids and/or a query for the Facebook intent scraper")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
            )
            try:
                context = await browser.new_context(
                    user_agent=self.random_ua(),
                    viewport={"width": 412, "height": 900},
                    locale="en-US",
                )
                await context.add_cookies(self.parse_cookie_string(cookie_str, ".facebook.com"))

                # Build the list of feeds to read: each group, plus (optionally) in-group search.
                targets = []
                for gid in group_ids:
                    if query:
                        targets.append(f"https://m.facebook.com/groups/{gid}/search/?q={query}")
                    else:
                        targets.append(f"https://m.facebook.com/groups/{gid}")
                if not group_ids and query:
                    targets.append(f"https://m.facebook.com/search/posts/?q={query}")

                count = 0
                seen = set()
                for url in targets:
                    if count >= max_results:
                        break
                    posts = await self._read_feed(context, url)
                    for post in posts:
                        if count >= max_results:
                            break
                        text = post.get("text", "")
                        key = (post.get("author", ""), text[:80])
                        if not text or key in seen:
                            continue
                        seen.add(key)

                        # Keyword pre-filter (+ require the query term if given).
                        if query_norm and query_norm not in normalize_ar(text):
                            continue
                        if not detect_buyer_intent(text):
                            continue

                        wants = None
                        urgency = None
                        score = 60
                        if use_ai:
                            try:
                                from app.services.ai_service import ai_service
                                a = await ai_service.classify_buyer_intent(text)
                                if not a.get("is_buyer"):
                                    continue
                                wants = a.get("wants")
                                urgency = a.get("urgency")
                                score = int(a.get("score") or 60)
                            except Exception as e:
                                logger.debug(f"intent AI classify failed: {e}")

                        raw_phone = extract_phone_from_text(text)
                        phone = normalize_egyptian_phone(raw_phone) if raw_phone else None

                        yield RawLead(
                            source=self.source,
                            name=post.get("author") or None,
                            phone=phone,
                            company=None,
                            industry=wants or query or "buyer intent",
                            raw_data={
                                "post_text": text[:1000],
                                "post_url": post.get("url"),
                                "wants": wants,
                                "urgency": urgency,
                                "intent_score": score,
                                "source": "fb_group_intent",
                            },
                        )
                        count += 1
                    await self.delay()
            finally:
                await browser.close()

    async def _read_feed(self, context, url: str) -> list:
        """Open a group/search feed, scroll to load posts, and extract them."""
        page = await context.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            body = (await page.content()).lower()
            if any(s in body for s in FB_BLOCKED_SIGNALS) or "login" in page.url:
                raise BlockedError("Facebook session cookie rejected or expired — refresh c_user/xs.")
            if resp and self.is_blocked(resp.status, body):
                raise BlockedError(f"Facebook HTTP {resp.status}")

            # Scroll to load a few screens of posts.
            for _ in range(6):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(1500)

            return await page.evaluate(_EXTRACT_JS)
        finally:
            await page.close()
