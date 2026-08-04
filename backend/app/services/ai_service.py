"""
AI Service — Groq (real-time) + OpenRouter (reasoning/batch)
16 agents covering full B2B lead qualification pipeline
"""
import json
import logging
from typing import Optional
from groq import AsyncGroq
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self):
        self.reset()

    def reset(self):
        """(Re)create the SDK clients. Their underlying httpx connections bind to the
        current event loop on first use, so Celery workers must call this at the start
        of each task's fresh loop to avoid "Future attached to a different loop" errors."""
        self.groq = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.openrouter = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://qualifay.io",
                "X-Title": "Qualifay",
            },
        )

    # ─── Internal Helpers ─────────────────────────────────────

    async def _groq(self, messages: list, max_tokens: int = 512) -> str:
        """Call Groq (real-time speed), fallback to OpenRouter fast on error."""
        try:
            resp = await self.groq.chat.completions.create(
                model=settings.GROQ_MODEL_REALTIME,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Groq failed: {e} — falling back to OpenRouter fast")
            return await self._or_fast(messages, max_tokens)

    async def _groq_only(self, messages: list, max_tokens: int) -> str:
        """Call Groq and return its text, or "" on failure. No cross-fallback — used as the
        terminal provider so the fallback chains can't loop."""
        try:
            resp = await self.groq.chat.completions.create(
                model=settings.GROQ_MODEL_REALTIME,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq call failed: {e}")
            return ""

    async def _or_reason(self, messages: list, max_tokens: int = 1024) -> str:
        """Reasoning path. OpenRouter free tier is unavailable, so Groq is primary unless
        OPENROUTER_ENABLED is set (then try OpenRouter first, Groq as fallback)."""
        if settings.OPENROUTER_ENABLED:
            try:
                resp = await self.openrouter.chat.completions.create(
                    model=settings.OPENROUTER_MODEL_REASONING,
                    messages=messages, max_tokens=max_tokens, temperature=0.3,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"OR reasoning model failed: {e} — falling back to Groq")
        return await self._groq_only(messages, max_tokens)

    async def _or_fast(self, messages: list, max_tokens: int = 512) -> str:
        """Fast/batch path. OpenRouter free tier is unavailable, so Groq is primary unless
        OPENROUTER_ENABLED is set (then try OpenRouter first, Groq as fallback)."""
        if settings.OPENROUTER_ENABLED:
            try:
                resp = await self.openrouter.chat.completions.create(
                    model=settings.OPENROUTER_MODEL_FAST,
                    messages=messages, max_tokens=max_tokens, temperature=0.3,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"OR fast model failed: {e} — falling back to Groq")
        return await self._groq_only(messages, max_tokens)

    def _parse_json(self, text: str, fallback: dict) -> dict:
        """Parse JSON from LLM response, stripping markdown fences. Returns fallback on failure."""
        if not text:
            return fallback
        try:
            cleaned = text.strip()
            # Strip markdown code fences
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()
            # Find first { or [
            start = min(
                (cleaned.find("{") if "{" in cleaned else len(cleaned)),
                (cleaned.find("[") if "[" in cleaned else len(cleaned)),
            )
            if start < len(cleaned):
                cleaned = cleaned[start:]
            return json.loads(cleaned)
        except Exception as e:
            logger.warning(f"JSON parse failed: {e} | text={text[:200]}")
            return fallback

    # ─── 16 Agent Methods ─────────────────────────────────────

    async def classify_intent(self, message: str, contact_name: str = "") -> dict:
        """
        Fast intent classification using Groq.
        Returns: {intent, confidence, language, sentiment, requires_human, summary}
        """
        system = """You are a WhatsApp B2B lead intent classifier for an Egyptian sales CRM.
Analyze the message and return ONLY valid JSON with these exact fields:
{
  "intent": "greeting|question|purchase_intent|complaint|followup|booking|objection|unsubscribe|spam|farewell|other",
  "confidence": 0.0-1.0,
  "language": "ar|en|fr|auto",
  "sentiment": "positive|neutral|negative",
  "requires_human": true|false,
  "summary": "one sentence summary in English"
}
Rules:
- requires_human = true if: complaint, complex technical question, angry, or booking with specific dates
- Arabic messages with Arabic intent should still return fields in English
- Return ONLY the JSON object, no explanation"""

        prompt = f"Contact: {contact_name or 'Unknown'}\nMessage: {message}"
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=256,
        )
        return self._parse_json(result, {
            "intent": "other",
            "confidence": 0.5,
            "language": "auto",
            "sentiment": "neutral",
            "requires_human": True,
            "summary": message[:100],
        })

    async def quality_gate(self, lead_data: dict) -> dict:
        """
        Quality gate using OR fast model. Filters out junk/spam leads.
        Returns: {keep: bool, reason: str, quality_score: int}
        """
        system = """You are a B2B lead quality gate for an Egyptian sales CRM.
Evaluate if this lead is worth processing (real business, reachable, relevant).
Return ONLY valid JSON:
{
  "keep": true|false,
  "reason": "short explanation",
  "quality_score": 0-100
}
Reject if: no company name AND no phone, obviously fake data, personal (not business), competitor, or duplicate signals."""

        prompt = f"Lead data:\n{json.dumps(lead_data, ensure_ascii=False, indent=2)}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return self._parse_json(result, {"keep": True, "reason": "Quality gate error — defaulting to keep", "quality_score": 50})

    async def score_bant(self, lead_data: dict, messages: list = []) -> dict:
        """
        BANT scoring using OR reasoning model.
        Returns: {score, budget, authority, need, timeline, reason}
        """
        system = """You are a B2B BANT (Budget, Authority, Need, Timeline) scoring expert for the Egyptian market.
Analyze the lead data and any conversation messages to produce a BANT score.
Return ONLY valid JSON:
{
  "score": 0-100,
  "budget": "confirmed|likely|unclear|unlikely",
  "authority": "decision_maker|influencer|end_user|unknown",
  "need": "urgent|moderate|low|none",
  "timeline": "immediate|1_3_months|3_6_months|6_plus_months|unknown",
  "reason": "2-3 sentence explanation of score"
}
Scoring guide: budget(25pts) + authority(25pts) + need(30pts) + timeline(20pts) = 100"""

        history_text = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Agent'}: {m.get('content', '')}"
            for m in messages[-15:]
        ])
        prompt = f"Lead:\n{json.dumps(lead_data, ensure_ascii=False)}"
        if history_text:
            prompt += f"\n\nConversation:\n{history_text}"

        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=512,
        )
        return self._parse_json(result, {
            "score": 0,
            "budget": "unknown",
            "authority": "unknown",
            "need": "none",
            "timeline": "unknown",
            "reason": "Scoring failed — manual review required",
            "scoring_failed": True,
        })

    async def enrich_lead(self, raw_data: dict) -> dict:
        """
        Enrich/normalize lead data using OR fast.
        Returns: {company, industry, company_size, city, website, email_pattern, language}
        """
        system = """You are a B2B data enrichment specialist for the Egyptian market.
Given raw lead data, extract and normalize structured fields.
Return ONLY valid JSON:
{
  "company": "cleaned company name or null",
  "industry": "one of: tech|retail|manufacturing|construction|healthcare|education|finance|hospitality|logistics|real_estate|other",
  "company_size": "one of: 1-10|11-50|51-200|201-1000|1000+|unknown",
  "city": "Egyptian city name in English or null",
  "governorate": "Egyptian governorate in English or null",
  "website": "clean URL or null",
  "email_pattern": "e.g. firstname.lastname@company.com or null",
  "language": "ar|en|mixed"
}
If a field cannot be determined, use null. Do NOT invent data."""

        prompt = f"Raw lead data:\n{json.dumps(raw_data, ensure_ascii=False, indent=2)}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return self._parse_json(result, {
            "company": raw_data.get("company"),
            "industry": "other",
            "company_size": "unknown",
            "city": None,
            "governorate": None,
            "website": None,
            "email_pattern": None,
            "language": "ar",
        })

    async def generate_wa_reply(
        self,
        message: str,
        contact_name: str,
        history: list,
        language: str = "auto",
        tenant_context: str = "",
    ) -> Optional[str]:
        """
        Generate a WhatsApp reply using Groq.
        Returns reply string or None if should not reply.
        """
        history_text = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Agent'}: {m.get('content', '')}"
            for m in history[-10:]
        ])

        lang_instruction = "Respond in the same language as the customer." if language == "auto" else _lang_instruction(language)

        brand = f"\nYou represent this business — stay on-brand and specific to it:\n{tenant_context}\n" if tenant_context else ""
        system = f"""You are a professional B2B sales assistant for an Egyptian company.
{brand}{lang_instruction}
Rules:
- Be concise, warm, and professional (max 3 sentences)
- Never claim to be AI unless directly asked
- If booking/demo requested: confirm interest and say a human will follow up shortly
- If complaint: acknowledge, apologize briefly, escalate to human
- Return ONLY the reply text, no labels or quotes"""

        messages = [{"role": "system", "content": system}]
        if history_text:
            messages.append({"role": "user", "content": f"Conversation so far:\n{history_text}"})
            messages.append({"role": "assistant", "content": "Understood."})
        messages.append({"role": "user", "content": f"{contact_name}: {message}"})

        reply = await self._groq(messages, max_tokens=300)
        return reply if reply else None

    async def write_aida_message(self, lead: dict, context: str = "", language: str = "ar") -> str:
        """
        Write an AIDA-format outreach message using OR fast, in the tenant's chosen output
        language (ar = فصحى | en = English | masri = عامية مصرية).
        Returns outreach message string (max 3 sentences).
        """
        system = f"""You are a B2B copywriter specializing in WhatsApp outreach for Egyptian businesses.
Write a short, personalised outreach message using the AIDA framework (Attention, Interest, Desire, Action).
Rules:
- {_lang_instruction(language)}
- Maximum 3 sentences
- No emojis unless the brand context suggests it
- Sound human, not robotic
- Include a soft CTA (e.g., a question, not a hard sell)
- Return ONLY the message text, no labels"""

        prompt = f"""Lead info: {json.dumps(lead, ensure_ascii=False)}
{f'Additional context: {context}' if context else ''}
Write the outreach message:"""

        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return result or "مرحباً، كنا نود مشاركتك فرصة قد تناسب عملكم. هل لديكم دقيقة للحديث؟"

    async def expand_search_queries(self, industry: str, cities: str, n: int = 8) -> list:
        """Turn a broad industry + region into concrete search queries a maps/directory scraper
        can actually use. A query like "e-commerce, industrial automation" over "Middle East"
        finds almost nothing; "industrial automation suppliers in Cairo" finds real businesses.
        Each query names ONE narrow niche and ONE specific city. Returns [] on failure."""
        system = (
            "You expand a company's broad B2B target into concrete lead-search queries for "
            "scrapers (Google Maps / business directories) in Egypt and the Middle East. Split a "
            "broad industry into specific sub-niches, and a broad region into specific CITIES. "
            "Every query must name ONE niche and ONE city, e.g. \"restaurants in Cairo\" or "
            "\"industrial automation suppliers in Riyadh\". Prefer Egyptian cities when the region "
            "is Egypt or unspecified. Return ONLY JSON: {\"queries\": [\"...\"]}"
        )
        prompt = f"Industry/offering: {industry}\nRegion/cities: {cities or 'Egypt'}\nProduce {n} queries."
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=400,
        )
        data = self._parse_json(result, {"queries": []})
        qs = data.get("queries") if isinstance(data, dict) else None
        return [str(q).strip() for q in (qs or []) if str(q).strip()][:n]

    async def translate_arabic(self, text: str, direction: str = "en_to_ar") -> str:
        """
        Translate text using OR fast.
        direction: 'en_to_ar' or 'ar_to_en'
        Returns translated string.
        """
        if direction == "en_to_ar":
            system = "Translate the following text to formal Egyptian business Arabic (فصحى مبسطة). Return ONLY the translation."
        else:
            system = "Translate the following Arabic text to professional English. Return ONLY the translation."

        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": text}],
            max_tokens=500,
        )
        return result or text

    async def analyze_conversation_for_pipeline(self, messages: list, contact_name: str = "") -> dict:
        """Read a WhatsApp conversation and decide whether it's a real sales lead and, if
        so, which CRM pipeline stage it belongs in. One Groq call (fast, reliable).
        Returns: {is_lead, intent, score, stage, reason}."""
        convo = "\n".join(
            f"{'Customer' if m.get('direction') == 'inbound' else 'Us'}: {m.get('content','')}"
            for m in messages[-20:] if m.get('content')
        )
        system = (
            "You analyze a WhatsApp sales conversation for an Egyptian B2B company. "
            "Decide if the OTHER party is a genuine sales lead (interest, product/pricing "
            "questions, availability, booking) vs spam/wrong-number/no-intent chatter.\n"
            "Return ONLY valid JSON:\n"
            '{"is_lead": true/false, "intent": "pricing|product_info|booking|complaint|greeting|spam|other", '
            '"score": 0-100, "stage": "replied|qualifying|meeting|proposal|negotiation|won|lost", '
            '"reason": "one short sentence"}\n'
            "Stage guidance: general reply/interest=replied; qualifying questions=qualifying; "
            "asked for/agreed a meeting=meeting; asked for a formal offer=proposal; "
            "haggling on price/terms=negotiation; confirmed purchase=won; explicitly declined=lost."
        )
        prompt = f"Contact: {contact_name}\nConversation:\n{convo}"
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return self._parse_json(result, {
            "is_lead": False, "intent": "other", "score": 0,
            "stage": "replied", "reason": "Analysis unavailable",
        })

    async def classify_buyer_intent(self, post_text: str) -> dict:
        """Confirm whether a social/group post is a genuine buying request and extract what
        the person wants. One Groq call. Returns:
        {is_buyer, wants, budget, urgency, score, reason}."""
        system = (
            "You analyze Facebook group posts (Egyptian Arabic or English) to find people "
            "who want to BUY or are ASKING for a product/service. Ignore sellers, ads, "
            "greetings, and spam.\nReturn ONLY valid JSON:\n"
            '{"is_buyer": true/false, "wants": "short desc of what they want", '
            '"budget": "stated budget or null", "urgency": "high|medium|low", '
            '"score": 0-100, "reason": "one short sentence"}'
        )
        result = await self._groq(
            [{"role": "system", "content": system},
             {"role": "user", "content": post_text[:1500]}],
            max_tokens=200,
        )
        return self._parse_json(result, {
            "is_buyer": False, "wants": None, "budget": None,
            "urgency": "low", "score": 0, "reason": "Analysis unavailable",
        })

    async def analyze_sentiment(self, history: list) -> dict:
        """
        Analyze sentiment trend from conversation history using OR fast.
        Returns: {sentiment, trend, score}
        """
        system = """You are a conversation sentiment analyst for B2B sales.
Analyze the conversation history and return ONLY valid JSON:
{
  "sentiment": "positive|neutral|negative",
  "trend": "improving|stable|worsening",
  "score": -1.0 to 1.0
}"""

        history_text = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Agent'}: {m.get('content', '')}"
            for m in history[-20:]
        ])
        result = await self._or_fast(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Conversation:\n{history_text}"},
            ],
            max_tokens=150,
        )
        return self._parse_json(result, {"sentiment": "neutral", "trend": "stable", "score": 0.0})

    async def schedule_followup(self, lead: dict, history: list) -> dict:
        """
        Suggest optimal follow-up timing using OR fast.
        Returns: {days_wait, message, reason}
        """
        system = """You are a B2B sales timing expert for the Egyptian market.
Based on the lead profile and conversation history, suggest the optimal follow-up.
Return ONLY valid JSON:
{
  "days_wait": 1-30,
  "message": "suggested follow-up message (max 2 sentences)",
  "reason": "why this timing"
}"""

        history_text = "\n".join([m.get("content", "") for m in history[-10:]])
        prompt = f"Lead: {json.dumps(lead, ensure_ascii=False)}\nRecent messages: {history_text}"

        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=250,
        )
        return self._parse_json(result, {
            "days_wait": 3,
            "message": "متابعة بخصوص حديثنا السابق، هل يمكننا تحديد موعد مناسب؟",
            "reason": "Standard follow-up interval",
        })

    async def write_proposal(self, lead: dict, tenant_context: str = "") -> str:
        """
        Write a full business proposal in Markdown using OR reasoning (DeepSeek-R1).
        Returns full proposal string.
        """
        system = """You are an expert B2B proposal writer for Egyptian businesses.
Write a professional business proposal in Markdown format.
Structure: Executive Summary → Problem Statement → Our Solution → Value Proposition → Pricing Options → Next Steps → About Us
Use Arabic where appropriate for an Egyptian audience. Be specific, not generic."""

        prompt = f"""Lead/Client info: {json.dumps(lead, ensure_ascii=False, indent=2)}
{f'Our company context: {tenant_context}' if tenant_context else ''}
Write the full proposal:"""

        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return result or "# Proposal\n\nError generating proposal. Please try again."

    async def plan_campaign(self, leads: list, goal: str) -> dict:
        """
        Plan a multi-step outreach campaign using OR reasoning.
        Returns: {sequence: [{day, message, channel}], total_days}
        """
        system = """You are a B2B outreach campaign strategist for Egyptian market.
Design a multi-touch outreach sequence for the given leads and goal.
Return ONLY valid JSON:
{
  "sequence": [
    {"day": 1, "message": "message text", "channel": "whatsapp|email"},
    ...
  ],
  "total_days": number
}
Rules: max 5 touchpoints, vary channels if possible, respect Egyptian business culture (no Friday messages)"""

        lead_summary = [{"company": l.get("company"), "industry": l.get("industry"), "stage": l.get("stage")} for l in leads[:10]]
        prompt = f"Goal: {goal}\nLead sample: {json.dumps(lead_summary, ensure_ascii=False)}"

        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=800,
        )
        return self._parse_json(result, {
            "sequence": [
                {"day": 1, "message": "Initial outreach message", "channel": "whatsapp"},
                {"day": 4, "message": "Follow-up message", "channel": "whatsapp"},
                {"day": 10, "message": "Final follow-up", "channel": "email"},
            ],
            "total_days": 10,
        })

    async def match_tender(self, tender: dict, tenant_profile: dict) -> dict:
        """
        Assess tender match using OR reasoning.
        Returns: {match_score, bid_notes, requirements_gap}
        """
        system = """You are a tender evaluation expert for Egyptian government and private tenders.
Assess how well the company profile matches the tender requirements.
Return ONLY valid JSON:
{
  "match_score": 0-100,
  "bid_notes": "key points to address in the bid",
  "requirements_gap": "what the company is missing or needs to clarify"
}"""

        prompt = f"Tender:\n{json.dumps(tender, ensure_ascii=False)}\n\nCompany Profile:\n{json.dumps(tenant_profile, ensure_ascii=False)}"
        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=600,
        )
        return self._parse_json(result, {
            "match_score": 0,
            "bid_notes": "Unable to evaluate — manual review required",
            "requirements_gap": "Unknown",
        })

    async def analyze_competitor_ad(self, ad_data: dict) -> dict:
        """
        Analyze a competitor ad using OR reasoning.
        Returns: {insights, counter_strategy, opportunity}
        """
        system = """You are a competitive intelligence analyst specializing in the Egyptian B2B market.
Analyze the competitor ad/content and provide strategic insights.
Return ONLY valid JSON:
{
  "insights": "key observations about their positioning and messaging",
  "counter_strategy": "how to differentiate and counter their approach",
  "opportunity": "market gap or weakness we can exploit"
}"""

        prompt = f"Competitor ad data:\n{json.dumps(ad_data, ensure_ascii=False, indent=2)}"
        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=600,
        )
        return self._parse_json(result, {
            "insights": "Analysis failed",
            "counter_strategy": "Manual review required",
            "opportunity": "Unknown",
        })

    async def find_email_patterns(self, company: str, domain: str) -> list:
        """
        Suggest likely email patterns for a company using OR fast.
        Returns list of pattern strings.
        """
        system = """You are a B2B email intelligence specialist.
Given a company name and domain, suggest the 3 most likely email address formats used at that company.
Return ONLY a valid JSON array of 3 strings:
["firstname.lastname@domain.com", "f.lastname@domain.com", "firstname@domain.com"]
Base your suggestions on the company's size, region (Egypt), and industry norms."""

        prompt = f"Company: {company}\nDomain: {domain}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=150,
        )
        parsed = self._parse_json(result, [])
        if isinstance(parsed, list) and parsed:
            return parsed[:3]
        return [
            f"firstname.lastname@{domain}",
            f"f.lastname@{domain}",
            f"info@{domain}",
        ]

    async def check_consent_compliance(self, lead: dict, method: str) -> dict:
        """
        Check GDPR/PDPA consent compliance using OR fast.
        Returns: {compliant: bool, reason: str, action_needed: str}
        """
        system = """You are a data privacy compliance officer specializing in Egyptian and international regulations (PDPA Egypt 151/2020, GDPR principles).
Evaluate if the lead acquisition method and consent data comply with applicable regulations.
Return ONLY valid JSON:
{
  "compliant": true|false,
  "reason": "explanation referencing specific compliance requirements",
  "action_needed": "what must be done before contacting this lead, or 'none' if compliant"
}"""

        prompt = f"Lead data: {json.dumps(lead, ensure_ascii=False)}\nConsent method: {method}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=250,
        )
        return self._parse_json(result, {
            "compliant": False,
            "reason": "Compliance check failed — defaulting to non-compliant for safety",
            "action_needed": "Manual compliance review required before contacting",
        })

    async def suggest_replies(self, message: str, history: list) -> list:
        """
        Generate 3 quick reply suggestions using Groq.
        Returns list of 3 reply strings.
        """
        history_text = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Agent'}: {m.get('content', '')}"
            for m in history[-5:]
        ])
        system = """You are a B2B sales assistant. Suggest 3 short, natural reply options for the sales agent.
The replies should vary in tone: one professional, one warm, one asking a qualifying question.
Return ONLY a JSON array of exactly 3 strings: ["reply1", "reply2", "reply3"]
Match the language of the customer (Arabic or English)."""

        prompt = f"Recent history:\n{history_text}\n\nCustomer's latest message: {message}"
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=300,
        )
        parsed = self._parse_json(result, [])
        if isinstance(parsed, list) and len(parsed) >= 1:
            return parsed[:3]
        return [
            "شكراً لتواصلك معنا. سنرد عليك في أقرب وقت.",
            "يسعدنا مساعدتك. هل يمكنك إخبارنا بمزيد من التفاصيل؟",
            "ما هو الموعد المناسب لك للحديث مع أحد مستشارينا؟",
        ]


    # ─── AI Setup Consultant ──────────────────────────────────

    async def interview_turn(self, history: list, profile: dict) -> dict:
        """One turn of the onboarding interview. Given the conversation so far and the
        profile gathered, ask the next question (or wrap up) and extract new fields.
        Returns {reply, done, profile_patch}."""
        system = """أنت مستشار أعمال ذكي في منصة Qualifay لتوليد العملاء وإدارة المبيعات عبر واتساب.
مهمتك: إجراء مقابلة قصيرة وودّية مع صاحب العمل لفهم نشاطه، حتى نبني له النظام كاملاً.
اجمع تدريجياً: اسم النشاط، المجال/الصناعة، ما الذي يبيعه، نطاق الأسعار، المدن المستهدفة،
العميل المثالي (الصناعة/الحجم/المنصب)، مشاكل العميل، قيمة العرض (لماذا يختارونه)،
مصادر العملاء الحالية، الهدف الشهري للعملاء، حجم فريق المبيعات، ونبرة التواصل المفضلة.
اطرح سؤالاً واحداً في كل مرة، بلغة صاحب العمل نفسها. خصّص الأسئلة حسب المجال
(مثلاً: مقاولات → المناقصات؛ عيادة → الحجوزات).
عندما تجمع ما يكفي (8+ حقول)، اجعل done=true وقدّم ملخصاً ودوداً.
أعد فقط JSON صالح:
{
  "reply": "ردّك/سؤالك التالي بلغة صاحب العمل",
  "done": true|false,
  "profile_patch": { الحقول الجديدة أو المحدّثة فقط، بمفاتيح إنجليزية: business_name, industry, sells, price_range, cities, ideal_customer, pain_points, value_prop, current_sources, monthly_lead_target, team_size, tone, recommended_autonomy(full|copilot|manual) }
}"""
        convo = "\n".join([f"{m.get('role')}: {m.get('content','')}" for m in history[-12:]])
        prompt = f"الملف المجمّع حتى الآن:\n{json.dumps(profile, ensure_ascii=False)}\n\nالمحادثة:\n{convo}"
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=700,
        )
        return self._parse_json(result, {
            "reply": "عذراً، لم أستطع المتابعة الآن. هل يمكنك إعادة صياغة إجابتك؟",
            "done": False, "profile_patch": {},
        })

    async def generate_build_plan(self, profile: dict) -> dict:
        """From the finished business profile, draft the whole workspace: ICP + scoring,
        scrape plans, message templates (in the owner's voice), a follow-up sequence, a
        conversion flow, and an A/B test. Returned as drafts for the owner to review."""
        system = """أنت خبير نمو مبيعات B2B للسوق المصري. من ملف نشاط تجاري، صمّم مساحة عمل جاهزة للإطلاق.
أعد فقط JSON صالح بهذا الشكل بالضبط:
{
  "icp": {"summary": "وصف العميل المثالي", "min_bant_score": 40-70},
  "scrape_plans": [{"query": "كلمة بحث", "city": "المدينة"}],
  "templates": [
    {"name": "افتتاحية", "channel": "whatsapp", "subject": null, "body": "نص يستخدم {{name}} {{company}} بنبرة صاحب العمل"},
    {"name": "متابعة", "channel": "whatsapp", "subject": null, "body": "..."},
    {"name": "إعادة تفعيل", "channel": "whatsapp", "subject": null, "body": "..."}
  ],
  "sequence": {"name": "التسلسل الافتراضي", "steps": [
    {"delay_hours": 0, "channel": "whatsapp", "template_ref": 0},
    {"delay_hours": 72, "channel": "whatsapp", "template_ref": 1},
    {"delay_hours": 168, "channel": "whatsapp", "template_ref": 2}
  ]},
  "flow": {"type": "booking|order|quote|callback", "name": "..."},
  "ab_test": {"name": "اختبار الافتتاحية", "variant_b_body": "صيغة بديلة للافتتاحية"},
  "campaign_name": "حملتي الأولى"
}
اكتب كل النصوص بلغة الملف (عربي غالباً)، ونبرة مطابقة لحقل tone. اجعل الرسائل قصيرة وطبيعية بدون روابط في أول رسالة."""
        prompt = f"ملف النشاط:\n{json.dumps(profile, ensure_ascii=False)}"
        result = await self._or_reason(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return self._parse_json(result, {})


    async def supervise_message(self, text: str, tenant_context: str = "", first_contact: bool = False) -> dict:
        """Critic gate before an autonomous send: check a drafted message against brand +
        compliance + anti-ban rules. Returns {ok, reason, revised}. `revised` is a safe
        rewrite when the issue is fixable, else None. Keeps full-autopilot sends safe."""
        rules = (
            "- No links/URLs in a first-contact message (anti-ban).\n"
            "- No price or hard sell in a first message.\n"
            "- On-brand, professional tone; matches the business.\n"
            "- No invented facts, guarantees, or claims the business didn't state.\n"
            "- Not spammy, not more than a few sentences."
        )
        system = f"""You are a compliance + brand supervisor for outbound B2B WhatsApp/email in Egypt.
Business context:
{tenant_context or '(none provided)'}

Check the DRAFT message against these rules{' (this is a FIRST-contact message)' if first_contact else ''}:
{rules}
Return ONLY valid JSON:
{{"ok": true|false, "reason": "short reason", "revised": "a corrected safe version, or null if already fine or unfixable"}}"""
        result = await self._groq(
            [{"role": "system", "content": system}, {"role": "user", "content": f"DRAFT:\n{text}"}],
            max_tokens=400,
        )
        out = self._parse_json(result, {"ok": True, "reason": "", "revised": None})
        # Fail OPEN on a broken critic response (don't block real sends over a parse blip),
        # but honour an explicit block.
        if not isinstance(out, dict) or "ok" not in out:
            return {"ok": True, "reason": "supervisor-unavailable", "revised": None}
        return out


    async def extract_learning(self, lead: dict, outcome: str, history: list) -> dict:
        """From a won/lost lead + its conversation, distill ONE concise, reusable lesson
        the agents can apply to future leads. Returns {kind, content} or {} if nothing useful."""
        convo = "\n".join([
            f"{'Customer' if m.get('direction') == 'inbound' else 'Us'}: {m.get('content','')}"
            for m in history[-15:]
        ])
        system = """You distill sales lessons for an Egyptian B2B business. From one closed
lead and its WhatsApp conversation, extract ONE short, reusable lesson for future outreach.
Return ONLY valid JSON:
{"kind": "win_reason|loss_reason|objection|insight", "content": "one concise actionable sentence in Arabic"}
If there is no useful lesson, return {"kind":"none","content":""}."""
        prompt = f"Outcome: {outcome}\nLead: {json.dumps(lead, ensure_ascii=False)}\nConversation:\n{convo or '(none)'}"
        result = await self._or_fast(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=200,
        )
        out = self._parse_json(result, {})
        if not isinstance(out, dict) or out.get("kind") in (None, "none", "") or not out.get("content"):
            return {}
        return out


def _lang_instruction(language: str) -> str:
    """The one place that defines how each output-language choice is phrased to the model.
    ar = formal simplified Arabic · en = English · masri = Egyptian colloquial (عامية مصرية)."""
    if language == "en":
        return "Write in professional English."
    if language == "masri":
        return "اكتب بالعامية المصرية الدارجة (اللهجة المصرية) بأسلوب ودّي واحترافي، وليس بالفصحى."
    return "اكتب بالعربية الفصحى المبسّطة المناسبة للأعمال في مصر."


def tenant_context_str(profile: dict) -> str:
    """Condense a tenant's onboarding profile into a short brand brief that is injected
    into outreach/reply copy so every message sounds like THIS business, not a generic bot."""
    if not profile:
        return ""
    fields = [
        ("business_name", "Business"), ("industry", "Industry"), ("sells", "Sells"),
        ("value_prop", "Why customers choose us"), ("ideal_customer", "Ideal customer"),
        ("tone", "Preferred tone"), ("price_range", "Price range"),
    ]
    parts = []
    for key, label in fields:
        val = profile.get(key)
        if val:
            parts.append(f"{label}: {val}")
    return "\n".join(parts)


# Singleton
ai_service = AIService()
