"""
Qualifay B2B Lead Generation SaaS — SQLAlchemy Models
Multi-tenant architecture with BANT scoring, WhatsApp warmup, lead pool
"""
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float,
    DateTime, ForeignKey, JSON, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import enum

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────

class Plan(str, enum.Enum):
    trial = "trial"
    starter = "starter"
    growth = "growth"
    agency = "agency"


class LeadSource(str, enum.Enum):
    google_maps = "google_maps"
    linkedin = "linkedin"
    apollo = "apollo"
    web_scrape = "web_scrape"
    manual = "manual"
    pool = "pool"
    referral = "referral"
    inbound_wa = "inbound_wa"
    tender = "tender"
    facebook = "facebook"
    directories = "directories"
    enrichment = "enrichment"
    competitor_ads = "competitor_ads"
    yellowpages = "yellowpages"


class LeadStage(str, enum.Enum):
    new = "new"
    qualifying = "qualifying"
    pending_review = "pending_review"
    approved = "approved"
    outreach = "outreach"
    replied = "replied"
    meeting = "meeting"
    proposal = "proposal"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"
    archived = "archived"
    manual = "manual"


class LeadStatus(str, enum.Enum):
    active = "active"
    unsubscribed = "unsubscribed"
    invalid = "invalid"
    duplicate = "duplicate"


class ConversationStatus(str, enum.Enum):
    open = "open"
    pending = "pending"
    resolved = "resolved"
    ai_handling = "ai_handling"


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class NotificationType(str, enum.Enum):
    leads_ready = "leads_ready"
    wa_limit = "wa_limit"
    wa_warmup = "wa_warmup"
    wa_connected = "wa_connected"
    wa_disconnected = "wa_disconnected"
    consent_issue = "consent_issue"
    campaign_done = "campaign_done"
    pool_match = "pool_match"
    system = "system"


# ─── Tenant ───────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=gen_uuid)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    plan = Column(SAEnum(Plan), default=Plan.trial, nullable=False)
    language = Column(String, default="ar")
    trial_ends_at = Column(DateTime, nullable=True)
    auto_approve = Column(Boolean, default=False)
    min_bant_score = Column(Integer, default=50)
    contribute_to_pool = Column(Boolean, default=True)
    # When this tenant first sent an outreach email — anchors the email warmup ramp.
    email_started_at = Column(DateTime, nullable=True)
    # AI Setup Consultant: structured business profile captured in the conversational
    # onboarding interview, injected as context into every agent so copy is on-brand.
    tenant_profile = Column(JSON, nullable=True)
    # How much the system runs on its own: full (autopilot) | copilot (approve+send) | manual.
    autonomy = Column(String, default="copilot")
    onboarding_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Browser-extension automation agent (LinkedIn/Facebook sourcing — see AgentTask)
    agent_key = Column(String, unique=True, nullable=True, index=True)
    agent_daily_cap_linkedin = Column(Integer, default=80)
    agent_daily_cap_facebook = Column(Integer, default=150)
    agent_min_interval_seconds = Column(Integer, default=45)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="tenant", cascade="all, delete-orphan")
    wa_instances = relationship("WaInstance", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="tenant", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    scrape_jobs = relationship("ScrapeJob", back_populates="tenant", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="tenant", cascade="all, delete-orphan")


# ─── User ─────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    # Optional — lets a user log in with phone instead of email (E.164, normalized).
    phone = Column(String, unique=True, nullable=True, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    is_tenant_admin = Column(Boolean, default=False)
    language = Column(String, default="ar")
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant", back_populates="users")
    assigned_leads = relationship("Lead", back_populates="assigned_user", foreign_keys="Lead.assigned_to")
    notifications = relationship("Notification", back_populates="user")


# ─── Lead ─────────────────────────────────────────────────────

class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    source = Column(SAEnum(LeadSource), default=LeadSource.manual)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True, index=True)          # E.164
    email = Column(String, nullable=True)
    # WhatsApp reachability: NULL = not checked yet, True/False = verified via Evolution.
    wa_reachable = Column(Boolean, nullable=True)
    company = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    company_size = Column(String, nullable=True)
    city = Column(String, nullable=True)
    governorate = Column(String, nullable=True)
    website = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)

    # BANT
    bant_score = Column(Integer, default=0)                    # 0-100
    bant_budget = Column(String, nullable=True)
    bant_authority = Column(String, nullable=True)
    bant_need = Column(String, nullable=True)
    bant_timeline = Column(String, nullable=True)
    bant_reason = Column(Text, nullable=True)

    stage = Column(SAEnum(LeadStage), default=LeadStage.new)
    status = Column(SAEnum(LeadStatus), default=LeadStatus.active)
    language = Column(String, default="ar")

    # Consent (GDPR/PDPA compliance)
    consent_at = Column(DateTime, nullable=True)
    consent_method = Column(String, nullable=True)
    consent_ip = Column(String, nullable=True)

    # Lead Pool
    pool_contributed = Column(Boolean, default=False)
    pool_entry_id = Column(String, ForeignKey("lead_pool.id"), nullable=True)

    assigned_to = Column(String, ForeignKey("users.id"), nullable=True)
    raw_data = Column(JSON, default=dict)
    ai_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="leads")
    assigned_user = relationship("User", back_populates="assigned_leads", foreign_keys=[assigned_to])
    pool_entry = relationship("LeadPool", foreign_keys=[pool_entry_id])
    consent_logs = relationship("ConsentLog", back_populates="lead", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="lead")


# ─── Lead Pool ────────────────────────────────────────────────

class LeadPool(Base):
    """Shared anonymised pool — no personal data (phone/email stripped)."""
    __tablename__ = "lead_pool"

    id = Column(String, primary_key=True, default=gen_uuid)
    contributed_by = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    company = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    company_size = Column(String, nullable=True)
    city = Column(String, nullable=True)
    governorate = Column(String, nullable=True)
    website = Column(String, nullable=True)
    source = Column(SAEnum(LeadSource), nullable=True)
    bant_score = Column(Integer, default=0)
    claimed_count = Column(Integer, default=0)
    verified_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    contributor = relationship("Tenant", foreign_keys=[contributed_by])


# ─── WaInstance ───────────────────────────────────────────────

class WaInstance(Base):
    __tablename__ = "wa_instances"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    instance_name = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    status = Column(String, default="disconnected")
    phone_number = Column(String, nullable=True)
    day_of_life = Column(Integer, default=0)
    daily_wa_cap = Column(Integer, default=10)
    sent_today_wa = Column(Integer, default=0)
    sent_today_email = Column(Integer, default=0)
    last_reset_at = Column(DateTime, nullable=True)
    warmup_complete = Column(Boolean, default=False)
    # Soft pause: stop this number from sending (outreach/AI) while keeping the WhatsApp
    # session connected. Inbound still arrives; no QR re-scan needed. Distinct from
    # status="disconnected" (a real logout).
    paused = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant", back_populates="wa_instances")
    conversations = relationship("Conversation", back_populates="wa_instance")
    campaigns = relationship("Campaign", back_populates="wa_instance")


# ─── Conversion Flows (sector-agnostic actions) ───────────────

class ConversionFlow(Base):
    """A conversion action a tenant offers — differs by sector: services book a
    meeting, e-commerce takes an order, others request a quote/callback. `config`
    holds type-specific setup (e.g. order → product list, booking → hours)."""
    __tablename__ = "conversion_flows"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    type = Column(String, default="booking")   # booking | order | quote | callback | custom
    active = Column(Boolean, default=True, nullable=False, server_default="true")
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=func.now())


class FlowSubmission(Base):
    """A captured conversion — a booked meeting, a placed order, a quote/callback
    request — created from a conversation and tied to the lead."""
    __tablename__ = "flow_submissions"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    flow_id = Column(String, ForeignKey("conversion_flows.id"), nullable=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=True)
    type = Column(String, nullable=False)
    data = Column(JSON, default=dict)           # {datetime}/{items,total}/{notes}...
    status = Column(String, default="confirmed")  # confirmed | pending | cancelled | fulfilled
    created_at = Column(DateTime, default=func.now())


# ─── Sequences (multi-step cadences) ──────────────────────────

class Sequence(Base):
    """A multi-step follow-up cadence. Leads are enrolled and stepped through
    automatically until they reply/book or the steps run out."""
    __tablename__ = "sequences"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    active = Column(Boolean, default=True, nullable=False, server_default="true")
    created_at = Column(DateTime, default=func.now())

    steps = relationship("SequenceStep", back_populates="sequence",
                         cascade="all, delete-orphan", order_by="SequenceStep.step_order")


class SequenceStep(Base):
    __tablename__ = "sequence_steps"

    id = Column(String, primary_key=True, default=gen_uuid)
    sequence_id = Column(String, ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order = Column(Integer, default=0)          # 0-based position
    delay_hours = Column(Integer, default=0)          # wait before THIS step (0 = immediate)
    channel = Column(String, default="auto")          # auto | whatsapp | email
    template_id = Column(String, ForeignKey("message_templates.id"), nullable=True)
    subject = Column(String, nullable=True)           # inline (email) if no template
    body = Column(Text, nullable=True)                # inline if no template

    sequence = relationship("Sequence", back_populates="steps")


class SequenceEnrollment(Base):
    __tablename__ = "sequence_enrollments"
    __table_args__ = (
        UniqueConstraint("sequence_id", "lead_id", name="uq_enrollment_sequence_lead"),
    )

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    sequence_id = Column(String, ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    current_step = Column(Integer, default=0)
    status = Column(String, default="active", index=True)   # active | completed | stopped | replied | paused
    next_run_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())


# ─── Message Template ─────────────────────────────────────────

class MessageTemplate(Base):
    """Reusable message template for WhatsApp/email outreach and replies. Body may use
    {{name}} {{company}} {{industry}} {{city}} placeholders, filled from the lead."""
    __tablename__ = "message_templates"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    channel = Column(String, default="both")      # email | whatsapp | both
    category = Column(String, nullable=True)       # e.g. outreach | follow_up | meeting
    subject = Column(String, nullable=True)        # email only
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant")


# ─── Email Account ────────────────────────────────────────────

class EmailAccount(Base):
    """A sending identity (mailbox) for a tenant. Multiple accounts let outreach rotate
    across identities and scale volume, each warming up independently."""
    __tablename__ = "email_accounts"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    from_name = Column(String, nullable=True)
    from_email = Column(String, nullable=False)
    smtp_host = Column(String, nullable=False)
    smtp_port = Column(Integer, default=465)
    smtp_user = Column(String, nullable=False)
    smtp_password_enc = Column(Text, nullable=False)   # Fernet-encrypted
    imap_host = Column(String, nullable=True)
    imap_port = Column(Integer, default=993)
    status = Column(String, default="active")           # active | disabled
    paused = Column(Boolean, default=False, nullable=False, server_default="false")
    email_started_at = Column(DateTime, nullable=True)  # anchors this account's warmup
    sent_today = Column(Integer, default=0)
    last_reset_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant")


# ─── Conversation ─────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "instance_name", "wa_jid", name="uq_conversation_tenant_instance_jid"),
    )

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True)
    wa_instance_id = Column(String, ForeignKey("wa_instances.id"), nullable=True)
    instance_name = Column(String, nullable=False)
    wa_jid = Column(String, nullable=False, index=True)
    # "whatsapp" (wa_jid = phone JID) or "email" (instance_name='email', wa_jid = the
    # contact's email address). Lets the WhatsApp and email threads share one inbox.
    channel = Column(String, default="whatsapp", nullable=False, server_default="whatsapp")
    contact_name = Column(String, nullable=True)
    status = Column(SAEnum(ConversationStatus), default=ConversationStatus.open)
    ai_enabled = Column(Boolean, default=False)
    last_message = Column(Text, nullable=True)
    unread_count = Column(Integer, default=0)
    sentiment = Column(String, default="neutral")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="conversations")
    lead = relationship("Lead", back_populates="conversations")
    wa_instance = relationship("WaInstance", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan",
                            order_by="Message.created_at")


# ─── Message ──────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=gen_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    wa_message_id = Column(String, nullable=True, index=True)
    direction = Column(SAEnum(MessageDirection), nullable=False)
    content = Column(Text, nullable=True)
    message_type = Column(String, default="text")
    media_url = Column(String, nullable=True)
    is_ai_generated = Column(Boolean, default=False)
    ai_confidence = Column(Float, nullable=True)
    transcription = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    conversation = relationship("Conversation", back_populates="messages")


# ─── ScrapeJob ────────────────────────────────────────────────

class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    source = Column(SAEnum(LeadSource), nullable=False)
    config = Column(JSON, default=dict)
    status = Column(String, default="pending")          # pending, running, paused, done, failed
    leads_found = Column(Integer, default=0)
    leads_qualified = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    paused_until = Column(DateTime, nullable=True)
    celery_task_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="scrape_jobs")


# ─── ScrapeSchedule (daily automatic search) ──────────────────

class ScrapeSchedule(Base):
    __tablename__ = "scrape_schedules"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    source = Column(SAEnum(LeadSource), nullable=False)
    config = Column(JSON, default=dict)          # query, location, industry, max_results
    hour_cairo = Column(Integer, default=9)      # 0-23, hour of day in Africa/Cairo
    enabled = Column(Boolean, default=True)
    monthly_cap = Column(Integer, default=1000)  # stop scheduling once this many leads pulled this month
    monthly_count = Column(Integer, default=0)   # leads pulled by this schedule in the current month
    month_key = Column(String, nullable=True)    # "YYYY-MM" the monthly_count applies to
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())


# ─── AgentTask (browser-extension automation — Option A) ──────
#
# The Chrome extension (LinkedIn contact discovery + Facebook group/page buyer-intent
# watching) polls GET /api/v1/agent/tasks/next on its own machine via chrome.alarms —
# no human clicks required after the one-time setup. Each row is one unit of work; a
# "recurring" task (e.g. "watch this FB group") re-arms itself via next_eligible_at
# instead of terminating, so it keeps firing on a cadence without a new row per run.

class AgentPlatform(str, enum.Enum):
    linkedin = "linkedin"
    facebook = "facebook"


class AgentTaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    error = "error"


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    platform = Column(SAEnum(AgentPlatform), nullable=False)
    type = Column(String, nullable=False)  # "linkedin_search" | "facebook_group_watch" | "facebook_page_watch"
    params = Column(JSON, default=dict)    # query/location/group_id/page_id/max_results
    status = Column(String, default="pending", index=True)
    recurring = Column(Boolean, default=False)
    interval_minutes = Column(Integer, default=120)  # re-eligibility gap for recurring tasks
    next_eligible_at = Column(DateTime, nullable=True)
    result_count = Column(Integer, default=0)
    total_results = Column(Integer, default=0)  # cumulative across all recurring runs
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


# ─── Campaign ─────────────────────────────────────────────────

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    wa_instance_id = Column(String, ForeignKey("wa_instances.id"), nullable=True)
    message_template = Column(Text, nullable=True)      # legacy — sequence_id supersedes this
    status = Column(String, default="draft")            # draft, running, paused, done
    target_count = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    replied_count = Column(Integer, default=0)
    channel = Column(String, default="whatsapp")        # whatsapp, email, both
    created_at = Column(DateTime, default=func.now())

    # Orchestration layer: a campaign binds an AUDIENCE (filter over leads) to a
    # SEQUENCE (the multi-step engine that actually sends), so campaigns reuse the
    # enrollment machinery rather than owning a second send path.
    sequence_id = Column(String, ForeignKey("sequences.id"), nullable=True, index=True)
    audience_filter = Column(JSON, nullable=True)       # {stage, source, city, industry, min_score, search}
    instance_ids = Column(JSON, nullable=True)          # WA instance pool for rotation (list of ids)
    auto_enroll = Column(Boolean, default=False)        # keep syncing NEW matching leads while running

    tenant = relationship("Tenant", back_populates="campaigns")
    wa_instance = relationship("WaInstance", back_populates="campaigns")


# ─── ConsentLog ───────────────────────────────────────────────

class ConsentLog(Base):
    __tablename__ = "consent_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    lead_id = Column(String, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    method = Column(String, nullable=False)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    consent_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    lead = relationship("Lead", back_populates="consent_logs")


# ─── Notification ─────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    type = Column(SAEnum(NotificationType), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    data = Column(JSON, default=dict)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    tenant = relationship("Tenant", back_populates="notifications")
    user = relationship("User", back_populates="notifications")


# ─── Subscription ─────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, unique=True)
    provider = Column(String, nullable=True)                    # paymob, fawry, stripe
    external_id = Column(String, nullable=True)
    status = Column(String, default="trial")                    # trial, active, past_due, cancelled
    currency = Column(String, default="EGP")
    plan = Column(SAEnum(Plan), default=Plan.trial)
    current_period_end = Column(DateTime, nullable=True)
    eta_invoice_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="subscription")


# ─── Activity Log ─────────────────────────────────────────────

class ActivityType(str, enum.Enum):
    lead_scraped = "lead_scraped"
    lead_qualified = "lead_qualified"
    lead_approved = "lead_approved"
    lead_rejected = "lead_rejected"
    lead_updated = "lead_updated"
    message_sent = "message_sent"
    message_received = "message_received"
    ai_suggested = "ai_suggested"
    ai_sent = "ai_sent"
    scrape_started = "scrape_started"
    scrape_completed = "scrape_completed"
    instance_connected = "instance_connected"
    instance_disconnected = "instance_disconnected"
    appointment_booked = "appointment_booked"


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True)
    activity_type = Column(SAEnum(ActivityType), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(String, nullable=True, index=True)
    summary = Column(String(500), nullable=False)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)


# ─── Webhooks (n8n / Zapier / custom) ─────────────────────────

class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, nullable=False, index=True)
    url = Column(String(1000), nullable=False)
    events = Column(JSON, nullable=False, default=list)  # list of event names, ["*"] = all
    secret = Column(String, nullable=True)               # for HMAC signature
    active = Column(Boolean, default=True)
    description = Column(String(255), nullable=True)
    last_status = Column(Integer, nullable=True)         # last HTTP status delivered
    last_fired_at = Column(DateTime, nullable=True)
    failure_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())


# ─── A/B Testing (outreach message variants) ──────────────────

class ABTest(Base):
    __tablename__ = "ab_tests"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    channel = Column(String(20), default="whatsapp")  # whatsapp | email
    status = Column(String(20), default="active")      # active | paused | done
    created_at = Column(DateTime, default=func.now())

    variants = relationship("ABVariant", back_populates="test", cascade="all, delete-orphan")


class ABVariant(Base):
    __tablename__ = "ab_variants"

    id = Column(String, primary_key=True, default=gen_uuid)
    test_id = Column(String, ForeignKey("ab_tests.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(80), nullable=False)          # "A", "B", ...
    subject = Column(String(300), nullable=True)        # email only
    body = Column(Text, nullable=False)                 # supports {{name}} {{company}} ...
    sent_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)

    test = relationship("ABTest", back_populates="variants")


class ABAssignment(Base):
    __tablename__ = "ab_assignments"
    __table_args__ = (UniqueConstraint("test_id", "lead_id", name="uq_abtest_lead"),)

    id = Column(String, primary_key=True, default=gen_uuid)
    test_id = Column(String, index=True, nullable=False)
    variant_id = Column(String, index=True, nullable=False)
    lead_id = Column(String, index=True, nullable=False)
    replied = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())


# ─── Agent Runtime (autonomous orchestrator activity log) ─────

class AgentRun(Base):
    """Every autonomous decision cycle the orchestrator makes for a tenant is logged
    here — the transparency layer that turns 'the AI did something' into a coworker's
    readable report. The activity feed is built from these rows."""
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=gen_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String, default="orchestrator")   # orchestrator | digest | ...
    status = Column(String, default="idle")          # idle | acted | alerted
    summary = Column(Text, nullable=False)           # human-readable, in the tenant's language
    actions = Column(JSON, default=list)             # [{type, detail}] — what it actually did
    metrics = Column(JSON, default=dict)             # state snapshot at decision time
    created_at = Column(DateTime, default=func.now(), index=True)
